"""Protected native professional workspace; no direct canonical HTTP forwarding."""
import importlib
import sqlite3
import csv
import io
from fastapi import HTTPException
from . import growth_core, workspace_access


def contract():
    core = growth_core.contract()
    return importlib.import_module(core.__package__ + '.operator_contract')


async def context(project_id, ctx):
    p = await growth_core.project_scope(project_id, ctx)
    conn = growth_core.connection()
    try:
        caps = await workspace_access.authorize(ctx, p, 'operate', conn)
        b = growth_core.bound(conn, p)
        if not b: raise HTTPException(409, '项目尚未关联增长资源')
        caps = await workspace_access.authorize(ctx,p,'operate',conn)
        revision = conn.execute('SELECT revision FROM workspace_sites WHERE site_id=?', (b['site_id'],)).fetchone()[0]
        return {'project_id': project_id, 'product_id': b['product_id'], 'site_id': b['site_id'],
                'revision': revision, 'capabilities': caps, 'object_versions': contract().object_versions(conn, b, limit=100),
                'resource_limit': '仅当前选择的已授权产品与站点',
                'concurrency': '普通编辑校验对象版本；批量与关系操作校验站点版本',
                'external_jobs': False, 'delete': False, 'legacy_metrics': True}
    finally: conn.close()


async def paged(project_id, collection, page, page_size, q, filters, selected_ids, ctx):
    p = await growth_core.project_scope(project_id, ctx)
    conn = growth_core.connection()
    try:
        await workspace_access.authorize(ctx, p, 'operate', conn)
        b = growth_core.bound(conn, p)
        if not b: raise HTTPException(409, '项目尚未关联增长资源')
        await workspace_access.authorize(ctx, p, 'operate', conn)
        return contract().paged(conn, b, collection, page=page, page_size=page_size, q=q,
                                filters=filters, selected_ids=selected_ids)
    except growth_core.contract().ContractError as exc: raise HTTPException(exc.status, str(exc))
    finally: conn.close()


EXPORT_COLUMNS = {
    'questions': [('id','编号'),('text','用户原话'),('source','来源'),('intent_class','意图分类'),('stage','用户阶段'),('commercial','商业价值'),('citation','AI引用潜力'),('brand','品牌植入机会'),('competition','内容竞争难度'),('total','总分'),('priority','优先级'),('notes','备注')],
    'keywords': [('id','编号'),('name','关键词'),('type','类型'),('pattern','匹配规则'),('intent_class','意图分类'),('priority','优先级'),('usage_count','使用次数'),('notes','备注')],
}


def csv_cell(value):
    if value is None: return ''
    if isinstance(value,(int,float)): return value
    text=str(value)
    # Prevent spreadsheet formulas from executing when a user opens the CSV.
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r')) else text


async def export_csv(project_id, collection, q, filters, ctx):
    if collection not in EXPORT_COLUMNS: raise HTTPException(404,'此列表暂不支持导出')
    p=await growth_core.project_scope(project_id,ctx)
    conn=growth_core.connection()
    try:
        conn.execute('BEGIN')
        b=growth_core.bound(conn,p)
        if not b: raise HTTPException(409,'项目尚未关联增长资源')
        await workspace_access.authorize(ctx,p,'operate',conn)
        columns=EXPORT_COLUMNS[collection]
        output=io.StringIO(newline='');output.write('\ufeff')
        writer=csv.writer(output);writer.writerow([label for _,label in columns])
        result=contract().paged(conn,b,collection,page=1,page_size=100,q=q,filters=filters)
        if result['total']>10000: raise HTTPException(413,'结果超过10000条，请先缩小搜索或筛选范围再导出')
        total=result['total']
        for page in range(1,max(1,result['pages'])+1):
            data=result if page==1 else contract().paged(conn,b,collection,page=page,page_size=100,q=q,filters=filters)
            for row in data['items']:writer.writerow([csv_cell(row.get(field)) for field,_ in columns])
            if output.tell()>2500000: raise HTTPException(413,'导出内容过大，请缩小搜索范围后重试')
        text=output.getvalue()
        if len(text.encode('utf-8'))>5000000: raise HTTPException(413,'导出内容过大，请缩小搜索范围后重试')
        return {'filename':f'{collection}-product-{b["product_id"]}.csv','csv':text,'total':total}
    except growth_core.contract().ContractError as exc:
        raise HTTPException(exc.status,str(exc))
    finally: conn.close()


async def download_response(request, project_id, collection, customer=False):
    """Same-origin attachment, keeping credentials and scope checks server-side."""
    from dataclasses import replace
    from fastapi.responses import Response
    from . import ui,customer_ui
    pairs=list(request.query_params.multi_items())
    allowed={'q','priority','intent_class','source','type','workspace_site_id'} | (set() if customer else {'tenant_id'})
    if len(pairs)!=len({k for k,_ in pairs}) or any(k not in allowed for k,_ in pairs):
        raise HTTPException(403,'导出范围参数无效')
    if customer:
        _,ctx,_=await customer_ui.session_context(request)
    else:
        session=ui._get_session(request.cookies.get(ui._cookie(request)))
        if not session:raise HTTPException(401,'请重新登录后导出')
        from .deps import _authenticate_context
        ctx=_authenticate_context(session['api_key'],None,request.query_params.get('tenant_id'))
    site=request.query_params.get('workspace_site_id')
    if site is not None:
        try:site=int(site)
        except ValueError:raise HTTPException(422,'资源编号无效')
        if site<1:raise HTTPException(422,'资源编号无效')
        ctx=replace(ctx,workspace_site_id=site)
    filters={k:v for k,v in pairs if k not in {'q','tenant_id','workspace_site_id'}}
    result=await export_csv(project_id,collection,request.query_params.get('q',''),filters,ctx)
    return Response(result['csv'].encode('utf-8'),media_type='text/csv; charset=utf-8',headers={**ui._ui_headers(),'Content-Disposition':'attachment; filename="'+result['filename']+'"','Cache-Control':'no-store'})


async def request(project_id, method, path, payload, query, revision, key, ctx, object_version=None):
    p = await growth_core.project_scope(project_id, ctx)
    conn = growth_core.connection()
    core = growth_core.contract()
    try:
        await workspace_access.authorize(ctx, p, 'operate', conn)
        b = growth_core.bound(conn, p)
        if not b: raise HTTPException(409, '项目尚未关联增长资源')
        await workspace_access.authorize(ctx,p,'operate',conn)
        adapter = contract()
        if method == 'GET':
            return adapter.attach_versions(conn, b, path, adapter.dispatch(conn, b, method, path, payload, query)), None
        growth_core.ensure_project_writable(p)
        if not isinstance(revision, int): raise HTTPException(428, '请刷新专业工作区后提交（缺少版本）')
        def authorize(tx):
            if not workspace_access.capabilities(tx, ctx, p)['operate']:
                raise HTTPException(403, '作业授权已撤销')
        from .commercial_guard import write_guard
        with write_guard(ctx,p):
            result = adapter.operate(conn, b, method, path, payload, query,
                                     revision=revision, key=key, subject=ctx.user_id, authorize=authorize, object_version=object_version)
        return result['result'], result['revision']
    except core.ContractError as exc:
        raise HTTPException(exc.status, str(exc))
    except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as exc:
        raise HTTPException(422, '内容不完整、关联冲突或不符合原生业务规则') from exc
    finally: conn.close()

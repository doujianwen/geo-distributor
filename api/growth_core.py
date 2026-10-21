"""Trusted portal boundary to the one canonical Growth core, never its internal HTTP API."""
import importlib
import os
from pathlib import Path
import sqlite3
import sys
import types

from fastapi import HTTPException
from . import auth as auth_module, state
from .customer_service import project_for

DEFAULT_ROOT = Path('E:/一人公司/独立站/geoflow/geo-intent-system')


def contract():
    root = Path(os.environ.get('GEO_GROWTH_CORE_ROOT', str(DEFAULT_ROOT))).resolve()
    name = '_canonical_geo_workspace'
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(root / 'app')]
        sys.modules[name] = package
    return importlib.import_module(name + '.portal_contract')


def connection():
    """A workspace DB must be explicitly configured; never initialize the historical DB."""
    path = os.environ.get('GEO_GROWTH_WORKSPACE_DB', '')
    if not path or not Path(path).is_file():
        raise HTTPException(503, '增长核心尚未配置；请由总部确认数据归属并开通工作区')
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    from .historical_adoption import allow_portal_connection
    allow_portal_connection(conn)
    conn.execute('PRAGMA foreign_keys=ON')
    if not contract().exists(conn):
        conn.close()
        raise HTTPException(503, '增长工作区尚未初始化，请联系总部')
    return conn


async def project_scope(project_id, ctx):
    p = await project_for(project_id, ctx.tenant_id, ctx.client_id)
    from .routers.clients import _load_client
    client = await _load_client(p.client_id, p.tenant_id)
    if not client or not client.is_active:
        raise HTTPException(404, '项目不存在或客户已停用')
    import copy
    p=copy.copy(p)
    p._growth_actor=ctx
    if ctx.workspace_site_id is not None:
        p._growth_site_id=ctx.workspace_site_id
    from .workspace_access import authorize
    await authorize(ctx, p, 'read')
    return p


def project_key(p):
    return p.tenant_id + '/' + p.project_id


def ensure_project_writable(p):
    status=getattr(p.status,'value',p.status)
    if status in {'cancelled','accepted','blocked'}:
        raise HTTPException(409,'项目已取消、已验收或被阻塞；保留历史查看，请先由总部处理项目状态')


def bound(conn, p):
    try:
        selected=getattr(p,'_growth_site_id',None)
        primary=contract().binding(conn, project_key(p), p.tenant_id, p.client_id)
        actor=getattr(p,'_growth_actor',None)
        if selected is None and actor and conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_resource_access'").fetchone():
            row=conn.execute("SELECT site_id FROM operator_resource_access WHERE project_key=? AND subject=? AND enabled=1 ORDER BY CASE capability WHEN 'operate' THEN 0 WHEN 'prepare' THEN 1 ELSE 2 END,site_id LIMIT 1",(project_key(p),actor.user_id)).fetchone()
            if row:
                selected=row[0]
        if selected is not None:
            p._growth_site_id=selected
        if selected is None or (primary and primary['site_id']==selected):
            return primary
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_resource_links'").fetchone():
            link=conn.execute('SELECT binding_key FROM operator_resource_links WHERE project_key=? AND site_id=?',(project_key(p),selected)).fetchone()
            if link:
                return contract().binding(conn,link[0],p.tenant_id,p.client_id)
        raise HTTPException(404,'资源未关联当前项目')
    except contract().ContractError as exc:
        raise HTTPException(exc.status, str(exc))


def public_subjects(ctx, tenant, client_id):
    if not ctx.is_hq:
        return []
    result = []
    # Return only server-derived subject identifiers for explicitly bound customer editors.
    for key, (t, role, c) in auth_module._registry().items():
        if (t, c)==(tenant,client_id) and role in {'END_CUSTOMER','END_CUSTOMER_EDITOR'}:
            subject = auth_module.verify_api_key(key).user_id
            result.append({'subject': subject, 'label': '客户编辑 · ' + subject[-8:]})
    from . import personal_identity
    if personal_identity.configured():
        conn=personal_identity.connect()
        try:
            for row in conn.execute("SELECT subject FROM identity_memberships WHERE tenant=? AND client=? AND enabled=1 AND role IN ('END_CUSTOMER','END_CUSTOMER_EDITOR')",(tenant,client_id)):
                result.append({'subject':row['subject'],'label':'客户成员 · '+row['subject'][-8:]})
        finally:conn.close()
    return result


async def workspace(ctx):
    if state.project_repo is None:
        raise HTTPException(503, '项目服务暂不可用')
    if ctx.is_hq:
        from .hq_service import all_rows
        from geo_distributor.models.project import Project
        projects = [Project.from_dict(r) for r in await all_rows('projects')]
    else:
        projects = await state.project_repo.find_by_tenant(ctx.tenant_id)
    result = []
    for p in projects:
        if ctx.client_id and p.client_id != ctx.client_id:
            continue
        from .routers.clients import _load_client
        c = await _load_client(p.client_id, p.tenant_id)
        if not c or not c.is_active:
            continue
        from .workspace_access import authorize
        try:
            caps = await authorize(ctx, p, 'read')
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        result.append({'project_id': p.project_id, 'tenant_id': p.tenant_id, 'client_id': p.client_id,
                       'name': getattr(p,'name',None) or 'GEO 增长服务 · ' + p.project_id, 'client_name': c.name,
                       'capabilities': caps})
    return {'projects': result, 'role': ctx.role, 'subject': ctx.user_id,
            'sandbox': os.environ.get('GEO_GROWTH_SANDBOX') == '1',
            'readonly': os.environ.get('GEO_DISTRIBUTOR_DEMO_ONLY') == '1'}


async def read(project_id, ctx):
    p = await project_scope(project_id,ctx)
    c, core = connection(), contract()
    try:
        b = bound(c,p)
        if not b:
            return {'bound':False,'message':'该项目尚未关联增长站点，由总部管理确认归属后开通',
                    'capabilities':{'manage':ctx.role == 'HQ_MANAGEMENT'},
                    'subjects':public_subjects(ctx,p.tenant_id,p.client_id)}
        core = contract()
        c.execute('BEGIN')
        data = core.view(c,b)
        from .workspace_access import authorize
        caps = await authorize(ctx,p,'read',c)
        legacy = core.capabilities(c,b,ctx.role,ctx.user_id)
        from .workspace_access import has_explicit_policy
        if not ctx.is_hq and not has_explicit_policy(c,ctx,p):
            caps['prepare'] = caps['prepare'] or legacy['prepare']
            caps['execute'] = caps['execute'] or legacy['execute']
        if not caps['professional']:
            review_observations=data.get('observations',[]) if caps['quality_review'] else None
            review_evidence=data.get('evidence',[]) if caps['quality_review'] else None
            data = core.customer_projection(c,b,data,ctx.user_id)
            data = customer_fields(data)
            if review_observations is not None:
                review_fields={'id','run_id','question_id','provider','model','surface','observed_at','quality','metrics','prompt_text','response_text','source_url','source_ref','prompt_hash','response_hash'}
                data['observations']=[{k:v for k,v in row.items() if k in review_fields} for row in review_observations]
                data['evidence']=[{k:v for k,v in row.items() if k in {'id','evidence_type','observation_id','rank_observation_id','source_url','snippet'}} for row in review_evidence]
        events=core.rows(c,'SELECT id,subject,operation,result,created_at FROM workspace_events WHERE site_id=? ORDER BY id DESC',(b['site_id'],))
        data['events']=[]
        import json
        for event in events:
            if not caps['professional'] and event['subject']!=ctx.user_id:continue
            saved=json.loads(event['result']) if event['result'].startswith('{') else {}
            data['events'].append({'id':event['id'],'operation':event['operation'],'note':saved.get('input',{}).get('note',''),'created_at':event['created_at']})
        data['diagnosis_links']=[]
        for diagnosis in data['diagnoses']:
            refs=core.rows(c,'SELECT e.id,e.snippet FROM evidence e JOIN diagnosis_evidence de ON de.evidence_id=e.id WHERE de.diagnosis_id=?',(diagnosis['id'],))
            for ref in refs:
                core.scoped(c,b,'evidence',ref['id'])
                data['diagnosis_links'].append({'id':str(diagnosis['id'])+'/'+str(ref['id']),'diagnosis':diagnosis['title'],'evidence':(ref['snippet'] if caps['professional'] else '') or '请到测量与证据查看已授权记录'})
        data['action_links']=[]
        for action in data['actions']:
            linked=core.rows(c,'SELECT d.id,d.title FROM diagnoses d JOIN action_diagnosis ad ON ad.diagnosis_id=d.id WHERE ad.action_id=?',(action['id'],))
            for diagnosis in linked:
                core.scoped(c,b,'diagnoses',diagnosis['id'])
                data['action_links'].append({'id':str(action['id'])+'/'+str(diagnosis['id']),'action':action['title'],'diagnosis':diagnosis['title']})
        if not caps['professional']:
            for action in data['actions']:
                action.pop('owner',None);action.pop('assigned_to',None)
        return {'bound':True, 'data':data, 'capabilities':caps,
                'subjects':public_subjects(ctx,p.tenant_id,p.client_id),
                'limits':['变化描述观测差异，不证明因果；单个问题不代表总体趋势。',
                          '采集申请不会自动触发外部平台；人工登记的证据须总部复核。',
                          '同一时期的其他发布活动可能影响归因，结果可能显示存在混杂因素。']}
    except core.ContractError as exc:
        raise HTTPException(exc.status,str(exc))
    finally:
        c.close()


async def write(project_id, operation, payload, revision, key, ctx):
    p=await project_scope(project_id,ctx)
    from .commercial_guard import write_guard
    with write_guard(ctx,p):
        return await _write(project_id,operation,payload,revision,key,ctx)


async def _write(project_id, operation, payload, revision, key, ctx):
    p = await project_scope(project_id,ctx)
    ensure_project_writable(p)
    c, core = connection(), contract()
    try:
        if operation == 'bind':
            if ctx.role != 'HQ_MANAGEMENT':
                raise HTTPException(403,'仅总部管理可关联核心资源')
            # Binding creates no historical ownership automatically. Only new brands here;
            # deliberate legacy adoption remains an offline reviewed administrator operation.
            if not isinstance(payload,dict) or set(payload) != {'name','domain'}:
                raise HTTPException(422,'请填写新品牌名称与完整网站地址；历史资源需先审查归属')
            with core.atomic(c) as tx:
                fingerprint=core.digest({'project':project_key(p),'payload':payload})
                replay=tx.execute('SELECT input_hash,result FROM workspace_operations WHERE site_id=0 AND subject=? AND operation_key=?',(ctx.user_id,key)).fetchone()
                if replay:
                    if replay['input_hash']!=fingerprint:raise HTTPException(409,'提交编号冲突')
                    import json
                    replay_result=json.loads(replay['result'])
                    live_binding=bound(tx,p)
                    if not live_binding or live_binding['site_id']!=replay_result['site_id']:raise HTTPException(409,'绑定已变更，请重新核验')
                    return replay_result
                existing = bound(tx,p)
                if existing:
                    raise HTTPException(409,'项目已关联，请刷新')
                result = core.bind(tx,project_key=project_key(p),tenant=p.tenant_id,client=p.client_id,**payload)
                import json
                tx.execute('INSERT INTO workspace_operations VALUES(?,?,?,?,?)',(0,ctx.user_id,key,fingerprint,json.dumps(result)))
                tx.execute('INSERT INTO workspace_events(site_id,subject,operation,result,created_at) VALUES(?,?,?,?,?)',
                           (result['site_id'],ctx.user_id,'bind',core.digest(payload),core.now()))
                return result
        b = bound(c,p)
        if not b:
            raise HTTPException(409,'项目尚未关联增长站点')
        from .workspace_access import authorize, capabilities, has_explicit_policy
        caps = await authorize(ctx,p,'read',c)
        legacy = core.capabilities(c,b,ctx.role,ctx.user_id)
        if operation == 'quality':
            await authorize(ctx,p,'quality_review',c)
            import json
            for event in c.execute("SELECT subject,result FROM workspace_events WHERE site_id=? AND operation='observation'",(b['site_id'],)):
                saved=json.loads(event['result'])
                if saved.get('result',{}).get('id') == payload.get('observation_id') and event['subject'] == ctx.user_id:
                    raise HTTPException(403,'不能复核自己登记的证据，请交由另一名获授权人员复核')
        elif operation in {'report','withdraw_report'}:
            await authorize(ctx,p,'report_publish',c)
        elif operation not in {'grant','assignment'}:
            needed = 'execute' if operation=='action_status' and not caps['operate'] else 'prepare' if operation in core.PREPARE else 'operate'
            if not caps.get(needed) and not (not ctx.is_hq and not has_explicit_policy(c,ctx,p) and legacy.get(needed)):
                raise HTTPException(403,'当前项目未授予此作业能力')
        if operation in {'grant','assignment'} and payload.get('subject') not in {s['subject'] for s in public_subjects(ctx,p.tenant_id,p.client_id)}:
            raise HTTPException(422,'请选择当前客户的有效编辑身份')
        effective_role = ('HQ_TECHNICAL' if caps['operate'] or operation in {'quality','report','withdraw_report'}
                          else 'DISTRIBUTOR_ADMIN' if caps['prepare'] else ctx.role)
        assigned_only=operation=='action_status' and not caps['operate'] and caps['execute']
        def check_assigned(tx):
            action=core.scoped(tx,b,'actions',payload.get('action_id'))
            assigned=tx.execute('SELECT subject FROM workspace_assignments WHERE action_id=?',(payload.get('action_id'),)).fetchone()
            if not assigned or assigned[0]!=ctx.user_id or payload.get('status')!='in_progress' or action['status'] not in {'approved','in_progress'}:
                raise HTTPException(403,'只能开始执行已批准且明确指派给自己的行动')
        if assigned_only:
            check_assigned(c)
            effective_role='HQ_TECHNICAL'
        if operation in {'grant','assignment'}:
            if ctx.role != 'HQ_MANAGEMENT':
                raise HTTPException(403,'仅总部管理可分配客户作业')
            effective_role = ctx.role
        def policy_recheck(tx):
            if assigned_only:check_assigned(tx)
            current = capabilities(tx,ctx,p)
            needed = 'quality_review' if operation=='quality' else 'report_publish' if operation in {'report','withdraw_report'} else 'execute' if operation=='action_status' and not current['operate'] else 'operate' if operation not in core.PREPARE else 'prepare'
            if operation not in {'grant','assignment'} and not current.get(needed) and not (not ctx.is_hq and not has_explicit_policy(tx,ctx,p) and core.capabilities(tx,b,ctx.role,ctx.user_id).get(needed)):
                raise HTTPException(403,'作业授权已变更，请重新进入工作区')
        return core.operate(c,b,operation,payload,revision=revision,key=key,role=effective_role,subject=ctx.user_id,fault=policy_recheck)
    except core.ContractError as exc:
        raise HTTPException(exc.status,str(exc))
    except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as exc:
        raise HTTPException(422,'提交不符合核心规则：'+str(exc)[:250] if isinstance(exc,ValueError) else '内容不完整、对象冲突或不符合核心规则')
    finally:
        c.close()


async def report(project_id, report_id, ctx):
    p = await project_scope(project_id,ctx)
    c, core = connection(), contract()
    try:
        b = bound(c,p)
        if not b: raise HTTPException(404,'增长站点未关联')
        snap = core.scoped(c,b,'workspace_snapshots',report_id)
        valid, reason = core.snapshot_valid(c,b,snap)
        if not valid:
            raise HTTPException(409,'报告已停止展示：'+reason+'；请总部复核并发布新版本')
        import json
        data=json.loads(snap['snapshot'])
        # A customer snapshot may contain only approved diagnoses/actions; draft content is excluded.
        data['diagnoses']=[d for d in data['diagnoses'] if d['status'] in {'confirmed','actioned','resolved'}]
        data['actions']=[a for a in data['actions'] if a['status'] != 'planned']
        for a in data['actions']:
            a.pop('owner',None);a.pop('assigned_to',None)
        data = customer_fields(data)
        return {'id':snap['id'],'title':snap['title'],'created_at':snap['created_at'],
                'source_hash':snap['source_hash'],'data':data,'limits':'固定来源快照；单样本不代表总体增长，归因不证明因果。sandbox为虚拟演练。'}
    except core.ContractError as exc:
        raise HTTPException(exc.status,str(exc))
    finally: c.close()


def customer_fields(data):
    """Explicit field allowlist, shared by current customer view and fixed reports."""
    fields = {
        'site': {'id','name','domain'}, 'product': {'id','name','market','target_customer','description'},
        'questions': {'id','text','notes','source'}, 'pages': {'id','title','url','status'},
        'facts': {'id','fact_key','fact_text','version','status','source_ref'},
        'personas': {'id','name','description','pain_points','goals'},
        'scenarios': {'id','name','description','stage'}, 'clusters': {'id','name','description','parent_topic'},
        'entities': {'id','name','type','description'}, 'briefs': {'id','title','status','target_url','content_type'},
        'runs': {'id','started_at','completed_at','provider','model','surface','environment','status'},
        'requests': {'id','question_id','note','status','run_id','created_at'},
        'observations': {'id','run_id','question_id','provider','model','surface','observed_at','quality','metrics','prompt_text'},
        'evidence': {'id','evidence_type','observation_id','rank_observation_id','source_url'},
        'diagnoses': {'id','title','diagnosis_type','finding','rationale','status','question_id'},
        'actions': {'id','title','action_type','description','body','target_context','status','review_at'},
        'publications': {'id','action_id','page_id','published_url','published_at','title_snapshot','publication_status'},
        'competitors': {'id','name','domain','source'}, 'keywords': {'id','name','search_intent','target_page_id'},
        'rank_observations': {'id','keyword_id','search_engine','rank','url','observed_at','source'},
        'comparisons': {'id','baseline','comparison','question','result'},
        'deltas': {'id','metric_name','baseline_value','comparison_value','delta_value','attribution_status','action_id'},
        'reports': {'id','title','created_at','status','valid','reason'},
    }
    result = {'revision': data.get('revision',0)}
    for group, allowed in fields.items():
        value = data.get(group, [] if group not in {'site','product'} else {})
        result[group] = [{k:v for k,v in row.items() if k in allowed} for row in value] if isinstance(value,list) else {k:v for k,v in value.items() if k in allowed}
    return result

"""Explicit project resource collections; no automatic historical adoption."""
from uuid import uuid4
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .growth import Auth
from .. import growth_core

router=APIRouter(tags=['growth-resources'])


class Resource(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=160)
    domain: str=Field(min_length=1,max_length=1000)


@router.get('/growth/projects/{project_id}/resources')
@router.get('/customer/growth/projects/{project_id}/resources')
async def resources(project_id: str, auth: Auth):
    p=await growth_core.project_scope(project_id,auth)
    conn=growth_core.connection();core=growth_core.contract()
    try:
        b=core.binding(conn,growth_core.project_key(p),p.tenant_id,p.client_id)
        bindings=[b] if b else []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_resource_links'").fetchone():
            for row in conn.execute('SELECT binding_key FROM operator_resource_links WHERE project_key=? ORDER BY site_id',(growth_core.project_key(p),)):
                found=core.binding(conn,row[0],p.tenant_id,p.client_id)
                if found:bindings.append(found)
        import copy
        from .. import workspace_access
        visible=[]
        for item in bindings:
            target=copy.copy(p);target._growth_site_id=item['site_id']
            caps=workspace_access.capabilities(conn,auth,target)
            if caps['read']:
                row=dict(conn.execute('SELECT s.id AS site_id,s.name,s.domain,s.source_product_id AS product_id FROM sites s WHERE s.id=?',(item['site_id'],)).fetchone())
                row['capabilities']=caps;visible.append(row)
        return {'resources':visible,
                'historical_adoption':False,'shared_product_multi_site':False,
                'limit':'支持项目关联多组独立产品/站点；历史资源及一产品多站点须归属治理，不自动认领'}
    finally:conn.close()


@router.post('/growth/projects/{project_id}/resources')
async def create(project_id: str, body: Resource, auth: Auth, idempotency_key: str|None=Header(default=None)):
    if auth.role!='HQ_MANAGEMENT':raise HTTPException(403,'仅总部管理可开通项目资源')
    if not idempotency_key or len(idempotency_key)>128:raise HTTPException(422,'缺少提交编号')
    p=await growth_core.project_scope(project_id,auth)
    growth_core.ensure_project_writable(p)
    conn=growth_core.connection();core=growth_core.contract()
    try:
        if not core.binding(conn,growth_core.project_key(p),p.tenant_id,p.client_id):
            raise HTTPException(409,'请先关联项目的首个增长资源')
        conn.execute('CREATE TABLE IF NOT EXISTS operator_resource_links(project_key TEXT NOT NULL,site_id INTEGER NOT NULL,binding_key TEXT NOT NULL UNIQUE,PRIMARY KEY(project_key,site_id))')
        conn.commit()
        fingerprint=core.digest({'operation':'add_resource','project':growth_core.project_key(p),'payload':body.model_dump()})
        from ..commercial_guard import write_guard
        with write_guard(auth,p), core.atomic(conn) as tx:
            saved=tx.execute('SELECT input_hash,result FROM workspace_operations WHERE site_id=0 AND subject=? AND operation_key=?',(auth.user_id,idempotency_key)).fetchone()
            if saved:
                if saved['input_hash']!=fingerprint:raise HTTPException(409,'提交编号与其他内容冲突')
                import json
                result=json.loads(saved['result'])
                link=tx.execute('SELECT binding_key FROM operator_resource_links WHERE project_key=? AND site_id=?',(growth_core.project_key(p),result['site_id'])).fetchone()
                if not link or not core.binding(tx,link[0],p.tenant_id,p.client_id):
                    raise HTTPException(409,'资源关联已变更，请重新核验')
                return result
            binding_key=growth_core.project_key(p)+'@'+uuid4().hex
            result=core.bind(tx,project_key=binding_key,tenant=p.tenant_id,client=p.client_id,**body.model_dump())
            tx.execute('INSERT INTO operator_resource_links VALUES(?,?,?)',(growth_core.project_key(p),result['site_id'],binding_key))
            import json
            tx.execute('INSERT INTO workspace_operations VALUES(?,?,?,?,?)',(0,auth.user_id,idempotency_key,fingerprint,json.dumps(result)))
            tx.execute('INSERT INTO workspace_events(site_id,subject,operation,result,created_at) VALUES(?,?,?,?,?)',(result['site_id'],auth.user_id,'add_resource',json.dumps(result),core.now()))
            return result
    except core.ContractError as exc:raise HTTPException(exc.status,str(exc))
    finally:conn.close()

"""Administration commands kept separate from professional content operations."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from .growth import Auth
from .. import growth_core, workspace_access, personal_identity

router = APIRouter(tags=['workspace-access'])


class Grant(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: str
    capabilities: list[str]
    resource_ids: list[int]|None=None


@router.get('/growth/access/subjects')
async def subjects(auth: Auth):
    found = await workspace_access.public_subjects(auth)
    if auth.role == 'HQ_MANAGEMENT' and personal_identity.configured():
        for r in await personal_identity.requests(auth):
            if r['status'] == 'approved' and r.get('enabled'):
                found.append({'subject':r['subject'],'label':r['role']+' · '+r['subject']})
    return found


@router.get('/growth/projects/{project_id}/access')
async def current(project_id: str, auth: Auth):
    if auth.role != 'HQ_MANAGEMENT':
        raise HTTPException(403, '仅总部管理可查看授权配置')
    p = await growth_core.project_scope(project_id, auth)
    conn = growth_core.connection()
    try:
        if not workspace_access.has_schema(conn):
            return []
        return [dict(r) for r in conn.execute('SELECT subject,capability,enabled,site_id FROM operator_resource_access WHERE project_key=?',(workspace_access.key(p),))] if conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_resource_access'").fetchone() else []
    finally:
        conn.close()


@router.post('/growth/projects/{project_id}/access')
async def grant(project_id: str, body: Grant, auth: Auth):
    if auth.role != 'HQ_MANAGEMENT':
        raise HTTPException(403, '仅总部管理可分配作业权限')
    p = await growth_core.project_scope(project_id, auth)
    permitted = {r['subject'] for r in await subjects(auth)}
    if body.subject not in permitted:
        raise HTTPException(422, '请选择已开通的有效个人身份')
    # Do not let an administrator attach another customer's account to this project.
    from .. import auth as registry
    candidates = [registry.verify_api_key(k) for k in registry._registry()]
    if personal_identity.configured():
        c = personal_identity.connect()
        try:
            rows=c.execute('SELECT * FROM identity_memberships WHERE subject=? AND enabled=1',(body.subject,)).fetchall()
            candidates += [registry.AuthContext(r['tenant'],r['role'],r['subject'],r['role'].startswith('HQ_'),r['client'] or None) for r in rows]
        finally:
            c.close()
    subject = next((c for c in candidates if c and c.user_id == body.subject),None)
    if not subject or (not subject.is_hq and (subject.tenant_id != p.tenant_id or (subject.client_id and subject.client_id != p.client_id))):
        raise HTTPException(422,'该人员不属于此客户或组织范围')
    conn = growth_core.connection()
    try:
        return workspace_access.set_access(conn, auth, p, body.subject, body.capabilities,body.resource_ids)
    finally:
        conn.close()


@router.get('/identity/requests')
async def pending(auth: Auth):
    return await personal_identity.requests(auth)


@router.post('/identity/requests/{subject}')
async def membership(subject: str, body: dict, auth: Auth):
    return await personal_identity.decide(auth,subject,body)

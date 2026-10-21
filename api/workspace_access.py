"""Explicit project capabilities; business roles never imply professional write access.

Additive portal policy tables live in the explicitly configured workspace database.
They contain authorization, not a second growth domain model.
"""
import json
import os
from datetime import datetime, timezone
from fastapi import HTTPException

CAPABILITIES = frozenset({'read', 'prepare', 'operate', 'execute_assigned', 'quality_review', 'report_publish'})
SCHEMA = '''
CREATE TABLE IF NOT EXISTS operator_project_access (
 project_key TEXT NOT NULL, subject TEXT NOT NULL, capability TEXT NOT NULL,
 enabled INTEGER NOT NULL, changed_by TEXT NOT NULL, changed_at TEXT NOT NULL,
 PRIMARY KEY(project_key,subject,capability));
CREATE TABLE IF NOT EXISTS operator_access_events (
 id INTEGER PRIMARY KEY, project_key TEXT NOT NULL, subject TEXT NOT NULL,
 actor TEXT NOT NULL, capabilities TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operator_resource_access (
 project_key TEXT NOT NULL, site_id INTEGER NOT NULL, subject TEXT NOT NULL,
 capability TEXT NOT NULL, enabled INTEGER NOT NULL,
 PRIMARY KEY(project_key,site_id,subject,capability));
'''


def initialize(conn):
    conn.executescript(SCHEMA)


def has_schema(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_project_access'").fetchone())


def has_explicit_policy(conn,ctx,project):
    return has_schema(conn) and bool(conn.execute('SELECT 1 FROM operator_project_access WHERE project_key=? AND subject=? LIMIT 1',(key(project),ctx.user_id)).fetchone())


def key(project):
    return project.tenant_id + '/' + project.project_id


def capabilities(conn, ctx, project):
    granted = set()
    if has_schema(conn):
        granted = {r[0] for r in conn.execute(
            'SELECT capability FROM operator_project_access WHERE project_key=? AND subject=? AND enabled=1',
            (key(project), ctx.user_id))}
    manager = ctx.role == 'HQ_MANAGEMENT'
    selected = getattr(project,'_growth_site_id',None)
    resource_granted=set()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_resource_access'").fetchone():
        sql='SELECT capability FROM operator_resource_access WHERE project_key=? AND subject=? AND enabled=1'
        args=[key(project),ctx.user_id]
        if selected is not None:
            sql+=' AND site_id=?';args.append(selected)
        resource_granted={r[0] for r in conn.execute(sql,args)}
    # Customer/partner read stays inside their server-derived tenant and client.
    native_read = not ctx.is_hq and ctx.tenant_id == project.tenant_id and (
        not ctx.client_id or ctx.client_id == project.client_id)
    return {
        'manage': manager, 'read': bool(manager or native_read or resource_granted or ('read' in granted and selected is None)),
        'prepare': bool({'prepare', 'operate'} & resource_granted),
        'operate': 'operate' in resource_granted, 'professional': 'operate' in resource_granted,
        'execute': bool({'operate','execute_assigned'} & resource_granted),
        'quality_review': 'quality_review' in resource_granted,
        'report_publish': 'report_publish' in resource_granted,
    }


async def authorize(ctx, project, capability='read', conn=None):
    if capability!='read' and not ctx.user_id.startswith('wp:') and os.environ.get('GEO_GROWTH_SANDBOX')!='1' and os.environ.get('GEO_OPERATOR_ALLOW_SERVICE_ACTORS')!='1':
        raise HTTPException(403,'专业作业需要已开通的个人账号；集成密钥仅用于维护')
    if conn is None:
        from .growth_core import connection
        conn = connection()
        try:
            return await authorize(ctx, project, capability, conn)
        finally:
            conn.close()
    caps = capabilities(conn, ctx, project)
    if not caps.get(capability):
        raise HTTPException(404 if capability == 'read' else 403,
                            '项目不存在或未获得对应作业授权')
    return caps


def set_access(conn, ctx, project, subject, selected, resource_ids=None):
    if ctx.role != 'HQ_MANAGEMENT':
        raise HTTPException(403, '仅总部管理可分配作业权限')
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 240:
        raise HTTPException(422, '请选择有效个人身份')
    if not isinstance(selected, list) or any(c not in CAPABILITIES for c in selected):
        raise HTTPException(422, '未知作业能力')
    initialize(conn)
    primary=conn.execute('SELECT site_id FROM workspace_bindings WHERE project_key=?',(key(project),)).fetchone()
    if resource_ids is None:
        resource_ids=[primary[0]] if primary else []
    valid={primary[0]} if primary else set()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='operator_resource_links'").fetchone():
        valid.update(r[0] for r in conn.execute('SELECT site_id FROM operator_resource_links WHERE project_key=?',(key(project),)))
    if not isinstance(resource_ids,list) or any(type(i) is not int or i not in valid for i in resource_ids):
        raise HTTPException(422,'授权资源不属于当前项目')
    if selected and set(selected)!={'read'} and not resource_ids:
        raise HTTPException(422,'请先绑定并选择授权资源')
    stamp = datetime.now(timezone.utc).isoformat()
    conn.execute('BEGIN IMMEDIATE')
    try:
        for cap in sorted(CAPABILITIES):
            conn.execute('INSERT INTO operator_project_access VALUES(?,?,?,?,?,?) '
                         'ON CONFLICT(project_key,subject,capability) DO UPDATE SET '
                         'enabled=excluded.enabled,changed_by=excluded.changed_by,changed_at=excluded.changed_at',
                         (key(project), subject, cap, int(cap in selected), ctx.user_id, stamp))
        conn.execute('DELETE FROM operator_resource_access WHERE project_key=? AND subject=?',(key(project),subject))
        for site in valid:
            conn.execute('UPDATE workspace_grants SET enabled=0 WHERE site_id=? AND subject=?',(site,subject))
        for site in set(resource_ids):
            for cap in sorted(set(selected)):
                conn.execute('INSERT INTO operator_resource_access VALUES(?,?,?,?,1)',(key(project),site,subject,cap))
        conn.execute('INSERT INTO operator_access_events(project_key,subject,actor,capabilities,created_at) VALUES(?,?,?,?,?)',
                     (key(project), subject, ctx.user_id, json.dumps({'capabilities':sorted(set(selected)),'resource_ids':sorted(set(resource_ids))}), stamp))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {'subject': subject, 'capabilities': sorted(set(selected)), 'resource_ids':sorted(set(resource_ids))}


async def public_subjects(ctx):
    if ctx.role != 'HQ_MANAGEMENT':
        return []
    from . import auth
    found = {}
    for credential in auth._registry():
        c = auth.verify_api_key(credential)
        if c:
            found[c.user_id] = {'subject': c.user_id, 'label': c.role + ' · ' + c.user_id[-12:]}
    return list(found.values())

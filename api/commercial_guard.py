"""Lock order: personal membership -> commercial state -> core write transaction.

Locks are held until the short local core command commits. No external I/O is
permitted inside this guard. There is no cross-database domain transaction.
"""
from contextlib import contextmanager, ExitStack
import json
import os
import sqlite3
import time
from pathlib import Path
from fastapi import HTTPException
from . import state


@contextmanager
def write_guard(ctx, project):
    from .growth_core import ensure_project_writable
    if not ctx.user_id.startswith('wp:') and os.environ.get('GEO_GROWTH_SANDBOX')!='1' and os.environ.get('GEO_OPERATOR_ALLOW_SERVICE_ACTORS')!='1':
        raise HTTPException(403,'请使用已开通的个人账号进行业务作业')
    with ExitStack() as stack:
        if ctx.user_id.startswith('wp:'):
            from . import personal_identity
            identity=personal_identity.connect()
            stack.callback(identity.close)
            identity.execute('BEGIN IMMEDIATE')
            row=identity.execute('SELECT m.* FROM identity_sessions s JOIN identity_memberships m ON m.subject=s.subject '
                                 'WHERE s.digest=? AND s.subject=? AND s.expires_at>? AND m.enabled=1',
                                 (ctx.credential_fingerprint,ctx.user_id,int(time.time()))).fetchone()
            if not row or row['role']!=ctx.role or (row['client'] or None)!=ctx.client_id or (not ctx.is_hq and row['tenant']!=ctx.tenant_id):
                raise HTTPException(401,'个人身份或成员权限已变更，请重新进入工作区')
        if state.persistence_backend=='sqlite' and state.active_db_path:
            commercial=sqlite3.connect(Path(state.active_db_path).resolve().as_uri()+'?mode=rw',uri=True,timeout=15)
            stack.callback(commercial.close)
            commercial.execute('BEGIN IMMEDIATE')
            row=commercial.execute('SELECT payload FROM projects WHERE id=? AND tenant_id=?',(project.project_id,project.tenant_id)).fetchone()
            if not row:
                raise HTTPException(404,'项目不存在或已撤销')
            from geo_distributor.models.project import Project
            live=Project.from_dict(json.loads(row[0]))
            if live.client_id!=project.client_id:
                raise HTTPException(409,'项目客户归属已变更，请重新核验')
            row=commercial.execute('SELECT payload FROM clients WHERE id=? AND tenant_id=?',(project.client_id,project.tenant_id)).fetchone()
            if not row or not json.loads(row[0]).get('is_active',True):
                raise HTTPException(403,'客户访问权限已停用')
            ensure_project_writable(live)
        else:
            if os.environ.get('GEO_DISTRIBUTOR_ENV') not in {'test','dev','local'} and os.environ.get('GEO_GROWTH_SANDBOX')!='1':
                raise HTTPException(503,'真实专业写入需要已配置的持久商业数据库')
            from .hq_service import _lock
            stack.enter_context(_lock)
            ensure_project_writable(project)
        yield

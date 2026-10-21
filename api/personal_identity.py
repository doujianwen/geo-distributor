"""WordPress is the password authority. Signed one-time assertions establish people.

No password copy, WP role inference, arbitrary redirect, or browser-held API key.
Enabled only with an explicit local policy DB and a 32+ byte server secret.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=['personal-identity'])
ROLES = {'HQ_MANAGEMENT', 'HQ_TECHNICAL', 'DISTRIBUTOR_ADMIN', 'DISTRIBUTOR_USER', 'END_CUSTOMER', 'END_CUSTOMER_EDITOR'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS identity_people(subject TEXT PRIMARY KEY, issuer TEXT NOT NULL, external_id TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identity_memberships(subject TEXT PRIMARY KEY, tenant TEXT NOT NULL, role TEXT NOT NULL, client TEXT, enabled INTEGER NOT NULL, revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identity_requests(subject TEXT PRIMARY KEY, status TEXT NOT NULL, requested_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identity_nonces(nonce TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identity_tickets(digest TEXT PRIMARY KEY, subject TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identity_sessions(digest TEXT PRIMARY KEY, subject TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS identity_events(id INTEGER PRIMARY KEY, subject TEXT NOT NULL, actor TEXT NOT NULL, operation TEXT NOT NULL, detail TEXT NOT NULL, created_at INTEGER NOT NULL);
'''


def configured():
    return bool(os.environ.get('GEO_IDENTITY_DB') and len(os.environ.get('GEO_IDENTITY_SECRET', '').encode()) >= 32 and os.environ.get('GEO_IDENTITY_ISSUER'))


def connect():
    if not configured():
        raise HTTPException(503, '个人账号桥接尚未配置；不会使用网站角色自动授予权限')
    path = Path(os.environ['GEO_IDENTITY_DB']).resolve()
    business=os.environ.get('GEO_GROWTH_WORKSPACE_DB','')
    from .growth_core import DEFAULT_ROOT
    if path==(DEFAULT_ROOT/'geo_intent.db').resolve() or (business and path==Path(business).resolve()):
        raise HTTPException(503,'个人身份库必须与增长业务库分开配置')
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def token_context(token):
    if not token or not token.startswith('person_') or not configured():
        return None
    c = connect()
    try:
        row = c.execute('SELECT m.* FROM identity_sessions s JOIN identity_memberships m ON m.subject=s.subject '
                        'WHERE s.digest=? AND s.expires_at>? AND m.enabled=1', (digest(token), int(time.time()))).fetchone()
        if not row:
            return None
        from .auth import AuthContext
        return AuthContext(row['tenant'], row['role'], row['subject'], row['role'].startswith('HQ_'), row['client'] or None,
                           credential_fingerprint=digest(token))
    finally:
        c.close()


def revoke_token(token):
    if token and token.startswith('person_') and configured():
        c=connect()
        try:
            c.execute('DELETE FROM identity_sessions WHERE digest=?',(digest(token),));c.commit()
        finally:c.close()


class Assertion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payload: str
    signature: str


@router.post('/identity/exchange')
async def exchange(body: Assertion):
    if not configured():
        raise HTTPException(503, '个人账号桥接尚未配置')
    if len(body.payload) > 4000 or len(body.signature) != 64:
        raise HTTPException(401, '无效登录凭证')
    signature = hmac.new(os.environ['GEO_IDENTITY_SECRET'].encode(), body.payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, body.signature):
        raise HTTPException(401, '无效登录凭证')
    try:
        data = json.loads(base64.urlsafe_b64decode(body.payload + '=' * (-len(body.payload) % 4)))
        if not isinstance(data,dict) or set(data) != {'issuer', 'user_id', 'issued_at', 'nonce'}:
            raise ValueError('claims')
        if data['issuer'] != os.environ['GEO_IDENTITY_ISSUER']:
            raise ValueError('issuer')
        if not isinstance(data['user_id'], str) or not data['user_id'].isdigit() or not 1 <= len(data['user_id']) <= 24:
            raise ValueError('subject')
        if type(data['issued_at']) is not int or abs(int(time.time()) - data['issued_at']) > 60:
            raise ValueError('expired')
        if not isinstance(data['nonce'], str) or not 24 <= len(data['nonce']) <= 128:
            raise ValueError('nonce')
    except (ValueError, TypeError, AssertionError, KeyError):
        raise HTTPException(401, '无效或过期的登录凭证')
    subject = 'wp:' + digest(data['issuer'])[:20] + ':' + data['user_id']
    ticket, stamp = secrets.token_urlsafe(40), int(time.time())
    c = connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM identity_nonces WHERE expires_at<?', (stamp,))
        try:
            c.execute('INSERT INTO identity_nonces VALUES(?,?)', (digest(data['issuer'] + ':' + data['nonce']), stamp + 180))
        except sqlite3.IntegrityError:
            raise HTTPException(409, '登录凭证已使用，请重新登录')
        c.execute('INSERT OR IGNORE INTO identity_people VALUES(?,?,?,?)', (subject, data['issuer'], data['user_id'], stamp))
        c.execute("INSERT OR IGNORE INTO identity_requests VALUES(?,'pending',?)", (subject, stamp))
        c.execute('INSERT INTO identity_tickets VALUES(?,?,?)', (digest(ticket), subject, stamp + 60))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return {'ticket': ticket, 'expires_in': 60}


@router.get('/ui/account/enter')
async def enter(ticket: str, request: Request):
    from . import ui
    c, stamp, token = connect(), int(time.time()), 'person_' + secrets.token_urlsafe(40)
    try:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT subject FROM identity_tickets WHERE digest=? AND expires_at>?', (digest(ticket), stamp)).fetchone()
        if not row:
            raise HTTPException(401, '登录链接已失效，请从网站重新登录')
        c.execute('DELETE FROM identity_tickets WHERE digest=?', (digest(ticket),))
        c.execute('INSERT INTO identity_sessions VALUES(?,?,?)', (digest(token), row['subject'], stamp + ui.SESSION_TTL_SECONDS))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    ctx = token_context(token)
    destination = '/ui/account/'
    response = RedirectResponse(destination, status_code=303, headers=ui._ui_headers())
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.set_cookie('ggs_person_identity', token, httponly=True, samesite='strict', secure=ui.COOKIE_SECURE, path='/ui', max_age=ui.SESSION_TTL_SECONDS)
    if ctx:
        sid = ui._create_session(token, ctx.tenant_id, ctx.role, ctx.is_hq)
        ui._SESSIONS[sid].update(client_id=ctx.client_id, actor_id=ctx.user_id)
        response.set_cookie(ui.SESSION_COOKIE, sid, httponly=True, samesite='strict', secure=ui.COOKIE_SECURE, path='/ui', max_age=ui.SESSION_TTL_SECONDS)
        if ctx.client_id:
            from . import customer_ui
            response.set_cookie(customer_ui.cookie(), sid, httponly=True, samesite='strict', secure=ui.COOKIE_SECURE, path='/ui/customer', max_age=ui.SESSION_TTL_SECONDS)
            response.headers['location'] = '/ui/customer/#/growth/overview'
        else:
            response.headers['location'] = '/ui/#/operator/dashboard' if ctx.role.startswith('HQ_') else '/ui/#/growth/overview'
    return response


@router.get('/ui/account/')
async def account_status(request: Request):
    import html
    from . import ui
    token = request.cookies.get('ggs_person_identity', '')
    c = connect()
    try:
        row = c.execute('SELECT r.status FROM identity_sessions s JOIN identity_requests r ON r.subject=s.subject WHERE s.digest=? AND s.expires_at>?', (digest(token), int(time.time()))).fetchone()
    finally:
        c.close()
    if not row:
        raise HTTPException(401, '请从网站使用自己的账号登录')
    label = {'pending': '申请已收到，等待总部开通权限', 'approved': '权限已开通，请从网站重新进入工作区', 'rejected': '申请暂未通过，请联系服务团队', 'suspended': '访问权限已暂停，请联系服务团队'}.get(row['status'], '请联系服务团队')
    # VC-11：空态必须给出一个可聚焦的主动作，指向官网工作区入口（只读跳转，不改动任何状态或权限）。
    return HTMLResponse('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>账号开通状态</title><link rel="stylesheet" href="/ui/app.css"><main class="login-card"><h1>账号开通状态</h1><p>' + html.escape(label) + '</p><p>无需选择角色或输入接入密钥。</p><p><a class="btn" href="http://geo-growth.local/portal/">返回官网工作区入口</a></p></main></html>', headers=ui._ui_headers())


async def requests(ctx):
    if ctx.role != 'HQ_MANAGEMENT':
        raise HTTPException(403, '仅总部管理可处理开通申请')
    c = connect()
    try:
        return [dict(r) for r in c.execute('SELECT r.*,m.tenant,m.role,m.client,m.enabled FROM identity_requests r LEFT JOIN identity_memberships m ON m.subject=r.subject ORDER BY requested_at DESC LIMIT 200')]
    finally:
        c.close()


async def decide(ctx, subject, payload):
    if ctx.role != 'HQ_MANAGEMENT':
        raise HTTPException(403, '仅总部管理可处理开通申请')
    if set(payload) != {'tenant', 'role', 'client', 'enabled'} or payload['role'] not in ROLES or type(payload['enabled']) is not bool:
        raise HTTPException(422, '请提供合法成员权限')
    if not isinstance(payload['tenant'], str) or not payload['tenant'].strip() or len(payload['tenant']) > 100:
        raise HTTPException(422, '请选择企业范围')
    client = payload['client']
    if (payload['role'].startswith('END_CUSTOMER')) != bool(client):
        raise HTTPException(422, '客户身份必须绑定明确客户，其他身份不可使用客户绑定')
    if client:
        from .routers.clients import _load_client
        record = await _load_client(client, payload['tenant'])
        if not record or not record.is_active:
            raise HTTPException(422, '客户不存在或已停用')
    c = connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM identity_requests WHERE subject=?', (subject,)).fetchone():
            raise HTTPException(404, '申请不存在')
        c.execute('INSERT INTO identity_memberships VALUES(?,?,?,?,?,1) ON CONFLICT(subject) DO UPDATE SET tenant=excluded.tenant,role=excluded.role,client=excluded.client,enabled=excluded.enabled,revision=identity_memberships.revision+1',
                  (subject, payload['tenant'], payload['role'], client, int(payload['enabled'])))
        c.execute('UPDATE identity_requests SET status=? WHERE subject=?', ('approved' if payload['enabled'] else 'suspended', subject))
        # Any membership change forces re-entry; stale sessions cannot gain new scope.
        c.execute('DELETE FROM identity_sessions WHERE subject=?', (subject,))
        c.execute('INSERT INTO identity_events(subject,actor,operation,detail,created_at) VALUES(?,?,?,?,?)', (subject, ctx.user_id, 'membership', json.dumps(payload), int(time.time())))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return {'status': 'approved' if payload['enabled'] else 'suspended'}

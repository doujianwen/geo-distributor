"""No-secret role selector, enabled ONLY in the explicit loopback fictional lab."""
import os
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from . import ui, customer_ui

router=APIRouter(prefix='/ui')


def check(request):
    if os.environ.get('GEO_GROWTH_SANDBOX')!='1' or not request.client or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(404,'Not found')
    customer_ui.check_origin(request)


@router.get('/lab/')
async def index(request:Request):
    check(request)
    return HTMLResponse('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GEO 交互演练</title><link rel="stylesheet" href="/ui/app.css"><main class="login-card"><p>GEO 增长工作区</p><h1>选择角色，体验真实操作流程</h1><p>虚拟演练：所有品牌、回答、排名与发布记录均为构造案例，操作只影响演练库。</p><p>总部可复核证据、诊断、批准、登记发布和复测；客户编辑可维护资料、提问、申请测量并执行已指派行动；客户查看身份只读。</p><div class="actions"><button class="btn" data-role="management">总部管理员</button><button class="btn" data-role="operations">总部运营</button><button class="btn" data-role="channel">渠道商管理员</button><button class="btn" data-role="editor">客户编辑</button><button class="btn ghost" data-role="viewer">客户查看</button></div><p id="lab-error" role="alert"></p><p>本入口为固定交互演练，不连接真实外部平台。</p></main><script src="/ui/lab.js"></script></html>''',headers=ui._ui_headers())


@router.get('/lab.js')
async def script(request:Request):
    check(request)
    return PlainTextResponse('''document.querySelectorAll('[data-role]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await fetch('/ui/lab/session/'+b.dataset.role,{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.detail);location.href=d.url;}catch(e){document.getElementById('lab-error').textContent=e.message;b.disabled=false;}});''',media_type='application/javascript',headers=ui._ui_headers())


@router.post('/lab/session/{role}')
async def login(role:str,request:Request,response:Response):
    check(request)
    if role not in {'management','operations','channel','editor','viewer'}:raise HTTPException(404,'Not found')
    key=os.environ.get('GEO_LAB_KEY_'+role.upper())
    if not key:raise HTTPException(503,'演练尚未准备好')
    if role in {'editor','viewer'}:
        await customer_ui.login(ui.LoginIn(api_key=key),request,response)
        return {'url':'/ui/customer/#/growth/overview'}
    # Main login path sets main cookie. HQ therefore uses the same main shell in the lab,
    # preserving real HQ entry's separate cookie and refusing scope crossover.
    await ui.ui_login(ui.LoginIn(api_key=key),request,response)
    return {'url':'/ui/#/growth/overview'}

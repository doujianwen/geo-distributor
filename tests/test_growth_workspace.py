"""Real canonical core service lifecycle, authorization and durable atomicity."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from api import state, auth, ui, growth_core as gateway
from api.app import app
from scripts.portal_demo_data import seed_demo
from scripts.customer_demo_data import seed_customer_demo
from scripts.growth_workspace_setup import create_core

KEYS='DEMO-GEO:hq:HQ_MANAGEMENT,DEMO-GEO:ops:HQ_TECHNICAL,DEMO-GEO:channel:DISTRIBUTOR_ADMIN,DEMO-GEO:member:DISTRIBUTOR_USER,DEMO-GEO:view:CLIENT_VIEWER,DEMO-GEO:customer:END_CUSTOMER:DEMO-CLI-1,DEMO-GEO:editor:END_CUSTOMER_EDITOR:DEMO-CLI-1,DEMO-GEO:other:END_CUSTOMER_EDITOR:DEMO-CLI-2,OTHER:cross:DISTRIBUTOR_ADMIN'
PREFIX='/growth/projects/DEMO-PRJ-1'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS',KEYS)
    monkeypatch.setenv('GEO_DISTRIBUTOR_ENV','production')
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB',str(tmp_path/'audit.db'))
    monkeypatch.delenv('GEO_DISTRIBUTOR_DEMO_ONLY',raising=False)
    monkeypatch.setattr(auth,'REGISTRY_FILE',tmp_path/'none.json')
    from api.ratelimit import limiter
    for obj in (limiter,ui._login_limiter):
        monkeypatch.setattr(obj,'rate_per_min',100000);monkeypatch.setattr(obj,'burst',100000)
    asyncio.run(seed_demo(tmp_path/'portal-demo'))
    asyncio.run(seed_customer_demo())
    path=create_core(tmp_path/'growth.db')
    monkeypatch.setenv('GEO_GROWTH_WORKSPACE_DB',str(path))
    with TestClient(app) as c:
        r=c.post(PREFIX+'/bind',headers=h(),json={'revision':0,'payload':{'name':'虚拟品牌','domain':'https://fiction.example'}})
        assert r.status_code==200,r.text
        from api import workspace_access
        from types import SimpleNamespace
        cn=gateway.connection()
        p=SimpleNamespace(tenant_id='DEMO-GEO',project_id='DEMO-PRJ-1')
        manager=auth.verify_api_key('hq')
        workspace_access.set_access(cn,manager,p,manager.user_id,['read','prepare','operate','quality_review','report_publish'])
        workspace_access.set_access(cn,manager,p,auth.verify_api_key('ops').user_id,['read','prepare','operate'])
        cn.close()
        yield c


def h(key='hq',ik=None):
    return {'X-API-Key':key,**({'Idempotency-Key':ik or uuid4().hex})}


def view(c,key='hq'):
    r=c.get(PREFIX,headers=h(key));assert r.status_code==200,r.text;return r.json()


def post(c,op,payload,key='hq',code=200):
    # Distinct submitter and reviewer: the production boundary rejects self-review.
    if op=='observation' and key=='hq' and code==200:
        key='ops'
    d=view(c,key)
    r=c.post(PREFIX+'/'+op,headers=h(key),json={'revision':d['data']['revision'],'payload':payload})
    assert r.status_code==code,r.text
    return r.json()


def observation(q,day=1):
    return dict(question_id=q,provider='chatgpt',model='test-model',surface='chatgpt',language='en',market='US',environment='sandbox',question_set_version='v1',collector_version='fixture-v1',request_config_hash=hashlib.sha256(b'config').hexdigest(),started_at=f'2026-10-{day:02d}T10:00:00+00:00',completed_at=f'2026-10-{day:02d}T10:10:00+00:00',observed_at=f'2026-10-{day:02d}T10:05:00+00:00',prompt_text='Which fictional brand?',response_text='Virtual answer for structural testing only.',source_url='https://fiction.example/record',source_ref='sandbox-'+str(day),brand_mentioned=1,citation_count=1,recommendation_level=2)


def approve(c,o):
    return post(c,'quality',dict(observation_id=o['id'],disposition='APPROVED',reason='已核验虚拟演练原文和来源，非真实采集',evidence_checked=True))


def prepare(c):
    page=post(c,'page',{'url':'https://fiction.example/faq','title':'FAQ'})['id']
    q=post(c,'question',{'text':'Which fictional brand?'})['id']
    obs=post(c,'observation',observation(q))
    approve(c,obs)
    d=post(c,'diagnosis',dict(question_id=q,diagnosis_type='MISSING_PAGE',evidence_ids=[obs['evidence_id']],title='补齐FAQ',finding='缺少页面',rationale='人工证据诊断',target_context='faq',page_ids=[page]))
    a=post(c,'action',dict(action_type='CONTENT_UPDATE',title='补齐FAQ内容',target_context='faq',description='补齐证据',body='虚拟执行内容',diagnosis_ids=[d['diagnosis_id']],page_ids=[page]))
    return page,q,obs,d,a


def test_real_core_complete_lifecycle(client):
    page,q,obs,d,a=prepare(client)
    for status in ('approved','in_progress'):
        post(client,'action_status',{'action_id':a['action_id'],'status':status})
    post(client,'publication',dict(action_id=a['action_id'],page_id=page,published_url='https://fiction.example/faq',published_at='2026-10-02T10:00:00+00:00',title_snapshot='虚拟FAQ',content_hash=hashlib.sha256(b'virtual').hexdigest()))
    post(client,'action_status',{'action_id':a['action_id'],'status':'published'})
    comp=post(client,'observation',observation(q,3));approve(client,comp)
    result=post(client,'compare',dict(baseline=obs['run_id'],comparison=comp['run_id'],question=q))
    assert result['comparable'] and len(result['delta_ids'])==3
    data=view(client)['data']
    assert all(x['attribution_status']=='attributed' and x['action_id']==a['action_id'] for x in data['deltas'])
    for status in ('measured','closed'):
        post(client,'action_status',{'action_id':a['action_id'],'status':status})
    report=post(client,'report',{'title':'虚拟链路报告'})
    r=client.get(PREFIX+'/reports/'+str(report['id']),headers=h('customer'))
    assert r.status_code==200 and r.json()['data']['actions'][0]['status']=='closed'
    c=gateway.connection()
    assert c.execute('select count(*) from diagnoses').fetchone()[0]==1
    assert c.execute('select count(*) from publications').fetchone()[0]==1
    assert c.execute('select count(*) from deltas').fetchone()[0]==3
    c.close()


@pytest.mark.parametrize('key',['view','member','customer'])
def test_viewers_cannot_write(client,key):
    post(client,'question',{'text':'forbidden'},key,403)
    post(client,'action_status',{'action_id':1,'status':'approved'},key,403)


def test_editor_grant_assignment_revocation_and_legacy_boundary(client):
    post(client,'question',{'text':'denied'},'editor',403)
    subject=auth.verify_api_key('editor').user_id
    post(client,'grant',{'subject':subject,'enabled':True})
    post(client,'question',{'text':'客户提出的问题'},'editor')
    page,q,obs,d,a=prepare(client)
    post(client,'quality',dict(observation_id=obs['id'],disposition='APPROVED',reason='forged',evidence_checked=True),'editor',403)
    post(client,'action_status',{'action_id':a['action_id'],'status':'approved'})
    post(client,'action_status',{'action_id':a['action_id'],'status':'in_progress'},'editor',403)
    post(client,'assignment',{'action_id':a['action_id'],'subject':subject})
    post(client,'action_status',{'action_id':a['action_id'],'status':'in_progress','note':'客户开始执行，须持久保存'},'editor')
    post(client,'grant',{'subject':subject,'enabled':False})
    post(client,'question',{'text':'revoked'},'editor',403)
    assert client.get('/projects',headers=h('editor')).status_code==403
    assert client.get(PREFIX,headers=h('other')).status_code==404
    assert client.get(PREFIX,headers=h('cross')).status_code==404
    c=gateway.connection();assert '客户开始执行' in c.execute("select result from workspace_events where operation='action_status' order by id desc limit 1").fetchone()[0];c.close()


def test_atomic_failure_concurrency_replay_restart(client):
    core=gateway.contract();c=gateway.connection();b=core.binding(c,'DEMO-GEO/DEMO-PRJ-1','DEMO-GEO','DEMO-CLI-1');c.close()
    revision=view(client)['data']['revision'];subject=auth.verify_api_key('hq').user_id
    def execute(key='same-key',fault=None,payload=None):
        cn=gateway.connection()
        try:return core.operate(cn,b,'question',payload or {'text':'atomic'},revision=revision,key=key,role='HQ_MANAGEMENT',subject=subject,fault=fault)
        finally:cn.close()
    def fail(tx): raise RuntimeError('injected after domain service commit')
    with pytest.raises(RuntimeError):execute('fail',fail)
    with ThreadPoolExecutor(4) as pool: result=list(pool.map(lambda _:execute(),range(4)))
    assert len({r['id'] for r in result})==1
    assert execute()==result[0] # new connection, durable replay
    with pytest.raises(core.ContractError):execute(payload={'text':'changed'})
    cn=gateway.connection();assert cn.execute('select count(*) from questions').fetchone()[0]==1;cn.close()


def test_service_commit_then_failure_rolls_back_all(client):
    page,q,o,d,a=prepare(client)
    core=gateway.contract();c=gateway.connection();b=core.binding(c,'DEMO-GEO/DEMO-PRJ-1','DEMO-GEO','DEMO-CLI-1')
    version=view(client)['data']['revision']
    def fail(tx): raise RuntimeError('after frozen service commit')
    with pytest.raises(RuntimeError):core.operate(c,b,'action_status',{'action_id':a['action_id'],'status':'approved'},revision=version,key='failure',role='HQ_MANAGEMENT',subject='test',fault=fail)
    assert c.execute('select status from actions where id=?',(a['action_id'],)).fetchone()[0]=='planned'
    with pytest.raises(RuntimeError):
        with core.atomic(c) as tx:
            tx.cursor().execute('BEGIN IMMEDIATE')
            tx.execute('insert into products(name) values(?)',('rollback only',))
            tx.commit();tx.rollback()
    assert not c.execute("select 1 from products where name='rollback only'").fetchone()
    with pytest.raises(RuntimeError):
        with core.atomic(c) as tx:tx.cursor().executescript('COMMIT;')
    c.close()


def test_quality_unknown_mismatch_and_report_revocation(client):
    page,q,o,d,a=prepare(client)
    second=post(client,'observation',observation(q,3))
    result=post(client,'compare',dict(baseline=o['run_id'],comparison=second['run_id'],question=q))
    assert not result['comparable'] and not result['delta_ids']
    approve(client,second)
    report=post(client,'report',{'title':'固定报告'})
    post(client,'quality',dict(observation_id=o['id'],disposition='HOLD',reason='撤销质量复核',evidence_checked=False))
    assert client.get(PREFIX+'/reports/'+str(report['id']),headers=h('customer')).status_code==409
    approve(client,o)
    assert client.get(PREFIX+'/reports/'+str(report['id']),headers=h('customer')).status_code==409


def test_customer_editor_session_bff_and_scoped_paths(client):
    assert client.post('/ui/customer/session',json={'api_key':'editor'}).status_code==200
    assert client.get('/ui/customer/proxy/customer/growth/workspace').status_code==200
    assert client.get('/ui/customer/proxy/customer/growth/projects/DEMO-PRJ-1').status_code==200
    assert client.get('/ui/customer/proxy/growth/workspace').status_code==403
    assert client.get('/ui/customer/proxy/customer/growth/workspace?tenant_id=OTHER').status_code==403
    assert client.post('/ui/session',json={'api_key':'editor'}).status_code==403

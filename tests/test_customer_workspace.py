"""Customer identity, publication and collaboration security/consistency gates."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from api import state, auth, customer_service as svc, ui
from api.app import app
from scripts.portal_demo_data import seed_demo, batch
from scripts.customer_demo_data import seed_customer_demo

AUTH_KEYS='DEMO-GEO:cust-a:END_CUSTOMER:DEMO-CLI-1,DEMO-GEO:cust-b:END_CUSTOMER:DEMO-CLI-2,OTHER:cust-other:END_CUSTOMER:OTHER-CLI,DEMO-GEO:cust-admin:DISTRIBUTOR_ADMIN,DEMO-GEO:cust-read:CLIENT_VIEWER,HQ:cust-hq:HQ_MANAGEMENT'


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB',str(tmp_path/'audit.db'))
    monkeypatch.delenv('GEO_DISTRIBUTOR_DEMO_ONLY',raising=False)
    from api.ratelimit import limiter
    monkeypatch.setattr(limiter,'rate_per_min',100000)
    monkeypatch.setattr(limiter,'burst',100000)
    monkeypatch.setattr(ui._login_limiter,'rate_per_min',100000)
    monkeypatch.setattr(ui._login_limiter,'burst',100000)
    asyncio.run(seed_demo(tmp_path/'portal-demo'))
    asyncio.run(seed_customer_demo())
    state._measurement_results.clear()
    from geo_distributor.models.client import Client
    asyncio.run(state.client_repo.create(Client('OTHER-CLI','OTHER','Other customer')))
    with TestClient(app) as c:
        yield c


def h(who='a'):
    return {'X-API-Key':'cust-'+who}


def manage_h():
    return {**h('hq'),'X-Tenant-ID':'DEMO-GEO'}


def review(c,kind='material_request',report=None,key='new'):
    r=c.post('/client-reviews',headers={**h('admin'),'Idempotency-Key':key},json={'project_id':'DEMO-PRJ-1','kind':kind,'title':'客户可见标题','instructions':'请提供资料说明','report_id':report})
    assert r.status_code==201,r.text
    return r.json()


def respond(c,r,key='answer',who='a',note='资料说明',action='submit'):
    return c.post('/customer/reviews/'+r['review_id']+'/respond',headers={**h(who),'Idempotency-Key':key},json={'revision':r['revision'],'action':action,'note':note})


def process(c,r,action='close',key='process'):
    return c.post('/client-reviews/'+r['review_id']+'/process',headers={**h('admin'),'Idempotency-Key':key},json={'revision':r['revision'],'action':action,'note':'服务团队已处理'})


def test_single_customer_same_tenant_and_cross_tenant(client):
    ws=client.get('/customer/workspace',headers=h()).json()
    assert [p['project_id'] for p in ws['projects']]==['DEMO-PRJ-1']
    assert ws['client']['name'].startswith('澄源')
    for path in ['/customer/projects/DEMO-PRJ-1','/customer/projects/DEMO-PRJ-1/geo','/customer/reports/DEMO-RPT-1']:
        assert client.get(path,headers=h('b')).status_code==404
        assert client.get(path,headers=h('other')).status_code==404
    for path in ['/customer/workspace?client_id=DEMO-CLI-2','/customer/workspace?tenant_id=OTHER']:
        assert client.get(path,headers=h()).status_code==403
    assert client.get('/customer/workspace',headers={**h(),'X-Client-ID':'DEMO-CLI-2'}).status_code==403
    assert client.get('/customer/workspace',headers=h('read')).status_code==403


@pytest.mark.parametrize('path',['/clients','/clients/DEMO-CLI-1','/clients/DEMO-CLI-1/portal','/projects','/projects/DEMO-PRJ-1','/projects/DEMO-PRJ-1/geo','/projects/DEMO-PRJ-1/stage','/reports?project_id=DEMO-PRJ-1','/reports/DEMO-RPT-1','/measurements/DEMO-PRJ-1','/requests','/leads','/distribution/orgs','/client-reviews?project_id=DEMO-PRJ-1','/client-publications?project_id=DEMO-PRJ-1'])
def test_customer_default_denied_on_old_surface(client,path):
    assert client.get(path,headers={**h(),'X-Client-ID':'DEMO-CLI-1'}).status_code==403


def test_credential_binding_actor_and_invalid_config(client,monkeypatch):
    a=auth.verify_api_key('cust-a');b=auth.verify_api_key('cust-b')
    assert a.client_id=='DEMO-CLI-1' and a.user_id!=b.user_id
    assert 'cust-a' not in a.user_id
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS',AUTH_KEYS+',DEMO-GEO:unbound:END_CUSTOMER,DEMO-GEO:wrong:DISTRIBUTOR_ADMIN:DEMO-CLI-1')
    assert auth.verify_api_key('unbound') is None and auth.verify_api_key('wrong') is None
    assert client.post('/ui/session',json={'api_key':'cust-a'}).status_code==403


def test_only_explicit_publications_and_visible_comparison(client):
    new=batch(ident='UNPUBLISHED',day=18,mentions=4)
    asyncio.run(state.measurement_repo.upsert(new))
    g=client.get('/customer/projects/DEMO-PRJ-1/geo',headers=h()).json()
    assert len(g['batches'])==2
    assert g['batches'][-1]['measurement_id']=='DEMO-MSR-2'
    assert g['batches'][-1]['comparison']['delta_pp']['mention_rate']==50
    pubs=client.get('/client-publications?project_id=DEMO-PRJ-1',headers=h('admin')).json()
    first=next(p for p in pubs if p['report_id']=='DEMO-RPT-1')
    assert client.post('/client-publications/'+first['publication_id']+'/withdraw',headers=h('admin'),json={'revision':first['revision']}).status_code==403
    assert client.post('/client-publications/'+first['publication_id']+'/withdraw',headers=manage_h(),json={'revision':first['revision']}).status_code==200
    g=client.get('/customer/projects/DEMO-PRJ-1/geo',headers=h()).json()
    assert len(g['batches'])==1 and g['batches'][0]['comparison']['comparable'] is False
    assert client.get('/customer/reports/DEMO-RPT-1',headers=h()).status_code==404
    assert not any(r['report_id']=='DEMO-RPT-1' for r in client.get('/customer/reviews',headers=h()).json())


@pytest.mark.parametrize('target',['report','measurement'])
def test_publication_fingerprints_invalidate_changed_sources(client,target):
    if target=='report':
        repo=state.report_service._repository;r=asyncio.run(repo.get('DEMO-RPT-2','DEMO-GEO'));r['content']['next_steps']=['NEW PRIVATE DRAFT']
    else:
        repo=state.measurement_repo;r=asyncio.run(repo.get('DEMO-MSR-2','DEMO-GEO'));r['observations'][0]['prompt_text']='NEW PRIVATE DRAFT'
    asyncio.run(repo.upsert(r))
    assert client.get('/customer/reports/DEMO-RPT-2',headers=h()).status_code==404
    assert 'NEW PRIVATE DRAFT' not in client.get('/customer/projects/DEMO-PRJ-1/geo',headers=h()).text
    assert client.post('/client-publications',headers=manage_h(),json={'report_id':'DEMO-RPT-2'}).status_code==409


def test_publication_qa_and_idempotency(client):
    assert client.post('/client-publications',headers=h('admin'),json={'report_id':'DEMO-RPT-2'}).status_code==403
    one=client.post('/client-publications',headers=manage_h(),json={'report_id':'DEMO-RPT-2'})
    assert one.status_code==200
    assert one.json()==client.post('/client-publications',headers=manage_h(),json={'report_id':'DEMO-RPT-2'}).json()
    repo=state.report_service._repository;r=asyncio.run(repo.get('DEMO-RPT-2','DEMO-GEO'))
    r.update(report_id='BAD-QA',scope_version=30);r['content'].pop('limitations');asyncio.run(repo.upsert(r))
    assert client.post('/client-publications',headers=manage_h(),json={'report_id':'BAD-QA'}).status_code==409
    r['scope_version']=31;r['report_id']='NO-EVIDENCE';r.pop('measurement_id');asyncio.run(repo.upsert(r))
    assert client.post('/client-publications',headers=manage_h(),json={'report_id':'NO-EVIDENCE'}).status_code==409


def test_review_full_loop_replay_stale_restart_and_no_project_acceptance(client):
    r=review(client)
    assert respond(client,r,who='b').status_code==404
    reply=respond(client,r);assert reply.status_code==200,reply.text
    assert reply.json()==respond(client,r).json()
    assert respond(client,r,note='different').status_code==409
    assert respond(client,r,key='new-answer').status_code==409
    closed=process(client,reply.json());assert closed.status_code==200,closed.text
    assert closed.json()['status']=='closed'
    assert process(client,reply.json()).json()==closed.json()
    assert process(client,closed.json(),key='bad').status_code==409
    state.init_repositories(state.active_db_path)
    result=next(x for x in client.get('/customer/reviews',headers=h()).json() if x['review_id']==r['review_id'])
    assert len(result['history'])==3 and result['resolution']=='服务团队已处理'
    assert client.get('/customer/projects/DEMO-PRJ-1',headers=h()).json()['status']=='in_execution'


@pytest.mark.parametrize('kind,action',[('content_review','confirm'),('content_review','request_changes'),('report_feedback','confirm')])
def test_customer_feedback_types_reopen(client,kind,action):
    r=review(client,kind,'DEMO-RPT-2' if kind=='report_feedback' else None)
    response=respond(client,r,action=action).json()
    assert response['status'] in ('confirmed','changes_requested')
    reopened=process(client,response,action='reopen').json();assert reopened['status']=='pending'
    next_reply=respond(client,reopened,key='second',action=action)
    assert next_reply.status_code==200
    assert len(next_reply.json()['history'])==4


def test_review_validation_and_published_report_only(client):
    assert client.post('/client-reviews',headers={**h('admin'),'Idempotency-Key':'x'},json={'project_id':'DEMO-PRJ-1','kind':'material_request','title':' ','instructions':'x'}).status_code==422
    assert client.post('/client-reviews',headers={**h('admin'),'Idempotency-Key':'x'},json={'project_id':'DEMO-PRJ-1','kind':'report_feedback','title':'x','instructions':'x'}).status_code==422
    r=review(client)
    assert respond(client,r,action='confirm').status_code==422
    assert respond(client,r,note=' ').status_code==422
    assert respond(client,r,note='x'*3001).status_code==422


def test_review_concurrent_response_and_withdraw_one_winner(client):
    r=review(client)
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(respond,client,r),pool.submit(process,client,r,'withdraw')]
        results=[f.result() for f in futures]
    assert sorted(x.status_code for x in results)==[200,409]


def test_customer_session_bff_expiry_revocation_rebinding_and_cookie(client,monkeypatch):
    assert client.post('/ui/session',json={'api_key':'cust-admin'}).status_code==200
    login=client.post('/ui/customer/session',json={'api_key':'cust-a'})
    assert login.status_code==200 and 'cust-a' not in login.text
    assert 'Path=/ui/customer' in login.headers['set-cookie']
    assert client.get('/ui/session').json()['ok']
    assert client.get('/ui/customer/proxy/customer/workspace').status_code==200
    assert client.get('/ui/customer/proxy/customer/workspace?client_id=DEMO-CLI-2').status_code==403
    assert client.get('/ui/customer/proxy/customer/workspace',headers={'X-Client-ID':'DEMO-CLI-2'}).status_code==403
    assert client.get('/ui/customer/proxy/clients').status_code==403
    assert client.post('/ui/customer/demo-session').status_code==404
    assert client.post('/ui/customer/proxy/customer/reviews/anything/respond',headers={'Origin':'https://evil.test'},json={}).status_code==403
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS',AUTH_KEYS.replace('cust-a:END_CUSTOMER:DEMO-CLI-1','cust-a:END_CUSTOMER:DEMO-CLI-2'))
    assert client.get('/ui/customer/proxy/customer/workspace').status_code==401
    assert client.get('/ui/session').json()['ok']
    assert client.post('/ui/customer/session',json={'api_key':'cust-a'}).status_code==200
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS',AUTH_KEYS.replace('DEMO-GEO:cust-a:END_CUSTOMER:DEMO-CLI-1,',''))
    assert client.get('/ui/customer/proxy/customer/workspace').status_code==401


def test_inactive_client_and_session_logout(client):
    client.post('/ui/customer/session',json={'api_key':'cust-a'})
    c=asyncio.run(state.client_repo.find_by_id('DEMO-CLI-1',tenant_id='DEMO-GEO'));c.is_active=False;asyncio.run(state.client_repo.update(c))
    assert client.get('/customer/workspace',headers=h()).status_code==403
    assert client.get('/ui/customer/proxy/customer/workspace').status_code==401
    c.is_active=True;asyncio.run(state.client_repo.update(c))
    client.post('/ui/customer/session',json={'api_key':'cust-a'})
    out=client.delete('/ui/customer/session')
    assert 'Max-Age=0' in out.headers['set-cookie'] and 'Path=/ui/customer' in out.headers['set-cookie']
    assert client.get('/ui/customer/proxy/customer/workspace').status_code==401


def test_customer_dto_no_internal_data_and_demo_seed_repeat(client):
    for path in ['/customer/workspace','/customer/reports','/customer/reviews','/customer/projects/DEMO-PRJ-1/geo']:
        r=client.get(path,headers=h());assert r.status_code==200,r.text
        assert not any(k in r.text for k in ['tenant_id','published_by','created_by','approved_by','raw_metadata','answer_raw','create_fingerprint','report_sha256','replays','virtual-demo-hq'])


@pytest.mark.parametrize('target',['report','measurement'])
def test_audit_snapshot_prevents_post_validation_private_content(client,monkeypatch,target):
    original=svc.publication_snapshot
    async def checked_then_changed(pub):
        result=await original(pub)
        if result is not None:
            if target=='report':
                repo=state.report_service._repository
                r=await repo.get(pub['report_id'],tenant_id='DEMO-GEO')
                r['content']['next_steps']=['PRIVATE-AFTER-VALIDATION']
            else:
                repo=state.measurement_repo
                r=await repo.get(pub['measurement_id'],tenant_id='DEMO-GEO')
                r['observations'][0]['prompt_text']='PRIVATE-AFTER-VALIDATION'
            await repo.upsert(r)
        return result
    monkeypatch.setattr(svc,'publication_snapshot',checked_then_changed)
    route='/customer/reports' if target=='report' else '/customer/projects/DEMO-PRJ-1/geo'
    r=client.get(route,headers=h())
    assert r.status_code==200,r.text
    assert 'PRIVATE-AFTER-VALIDATION' not in r.text
    assert 'PRIVATE-AFTER-VALIDATION' not in client.get(route,headers=h()).text


def test_report_withdraw_between_initial_check_and_response_transaction(client,monkeypatch):
    r=review(client,'report_feedback','DEMO-RPT-2')
    original=svc.visible_review
    async def allowed_then_withdrawn(item,ctx):
        result=await original(item,ctx)
        rows=await state.customer_publication_repo.list_by_tenant('DEMO-GEO')
        pub=next(p for p in rows if p['report_id']=='DEMO-RPT-2')
        await svc.withdraw_publication(pub['publication_id'],pub['revision'],auth.AuthContext('DEMO-GEO','HQ_MANAGEMENT','test-hq',True))
        return result
    monkeypatch.setattr(svc,'visible_review',allowed_then_withdrawn)
    assert respond(client,r,action='confirm').status_code==409
    stored=asyncio.run(state.customer_review_repo.get(r['review_id'],'DEMO-GEO'))
    assert stored['status']=='pending' and stored['response'] is None


def test_customer_memory_backend_preserves_authorization_and_collaboration(client,monkeypatch):
    cs=asyncio.run(state.client_repo.find_by_tenant('DEMO-GEO'))
    ps=asyncio.run(state.project_repo.find_by_tenant('DEMO-GEO'))
    rs=asyncio.run(state.report_service.list_reports('DEMO-PRJ-1','DEMO-GEO'))
    ms=asyncio.run(svc.load_measurements('DEMO-PRJ-1','DEMO-GEO'))
    pubs=asyncio.run(state.customer_publication_repo.list_by_tenant('DEMO-GEO'))
    reviews=asyncio.run(state.customer_review_repo.list_by_tenant('DEMO-GEO'))
    monkeypatch.delenv('GEO_DISTRIBUTOR_DB',raising=False)
    state.init_repositories()
    for c in cs:asyncio.run(state.client_repo.create(c))
    for p in ps:asyncio.run(state.project_repo.create(p))
    state.report_service._reports.update({r['report_id']:deepcopy(r) for r in rs})
    state._measurement_results['DEMO-PRJ-1']=deepcopy(ms)
    for p in pubs:asyncio.run(state.customer_publication_repo.upsert(p))
    for r in reviews:asyncio.run(state.customer_review_repo.upsert(r))
    assert len(client.get('/customer/reports',headers=h()).json())==2
    assert client.get('/customer/projects/DEMO-PRJ-1/geo',headers=h('b')).status_code==404
    r=review(client,key='memory')
    reply=respond(client,r)
    assert reply.status_code==200,reply.text
    assert process(client,reply.json()).status_code==200


def test_multiple_reports_same_measurement_are_one_customer_batch(client):
    repo=state.report_service._repository
    r=asyncio.run(repo.get('DEMO-RPT-2','DEMO-GEO'))
    r.update(report_id='DEMO-RPT-REVISED',scope_version=10,version=3)
    asyncio.run(repo.upsert(r))
    published=client.post('/client-publications',headers=manage_h(),json={'report_id':'DEMO-RPT-REVISED'})
    assert published.status_code==200,published.text
    assert len(client.get('/customer/reports',headers=h()).json())==3
    batches=client.get('/customer/projects/DEMO-PRJ-1/geo',headers=h()).json()['batches']
    assert len(batches)==2 and len({b['measurement_id'] for b in batches})==2
    assert batches[-1]['comparison']['delta_pp']['mention_rate']==50


def test_demo_reseed_preserves_withdrawal_and_closed_feedback(client):
    pubs=client.get('/client-publications?project_id=DEMO-PRJ-1',headers=h('admin')).json()
    pub=next(p for p in pubs if p['report_id']=='DEMO-RPT-2')
    client.post('/client-publications/'+pub['publication_id']+'/withdraw',headers=manage_h(),json={'revision':pub['revision']})
    asyncio.run(seed_customer_demo())
    assert client.get('/customer/reports/DEMO-RPT-2',headers=h()).status_code==404
    assert any(r['status']=='closed' for r in client.get('/customer/reviews',headers=h()).json())


@pytest.mark.parametrize('config',[{'demo_port':True},{'local_port':17665,'demo_port':17665},{'demo_port':80},{'external_url':'https://evil.test'}])
def test_local_ports_reject_invalid_config(tmp_path,monkeypatch,config):
    from api import local_runtime
    p=tmp_path/'ports.json';p.write_text(json.dumps(config),encoding='utf-8')
    monkeypatch.setattr(local_runtime,'CONFIG',p)
    with pytest.raises(ValueError):local_runtime.ports()


def test_local_ports_default_and_configurable_link(tmp_path,monkeypatch):
    from api import local_runtime
    p=tmp_path/'ports.json';monkeypatch.setattr(local_runtime,'CONFIG',p)
    assert local_runtime.ports()['demo_port']==8767
    p.write_text(json.dumps({'local_port':17665,'demo_port':17667,'customer_acceptance_port':17668}),encoding='utf-8')
    assert local_runtime.demo_url(customer=True)=='http://127.0.0.1:17667/ui/customer/'

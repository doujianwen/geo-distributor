"""Isolated HTTP acceptance tests for explicit intake and HQ approval."""
import concurrent.futures
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from api.app import app
from api import state
from api.ratelimit import limiter

AUTH_KEYS = 'T-PORTAL:portal-admin:DISTRIBUTOR_ADMIN,T-PORTAL:portal-view:CLIENT_VIEWER,T-OTHER:portal-other:DISTRIBUTOR_ADMIN,HQ:portal-tech:HQ_TECHNICAL,HQ:portal-manager:HQ_MANAGEMENT'

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB', str(tmp_path/'audit.db'))
    monkeypatch.setattr(limiter, 'rate_per_min', 10000)
    monkeypatch.setattr(limiter, 'burst', 10000)
    state.init_repositories(str(tmp_path/'portal.db'))
    state._measurement_results.clear()
    with TestClient(app) as c:
        yield c

def h(key='admin', tenant=None):
    out={'X-API-Key':'portal-'+key}
    if tenant: out['X-Tenant-ID']=tenant
    return out

def seed(c):
    r=c.post('/clients',headers=h(),json={'name':'验收客户','website':'https://example.test'})
    assert r.status_code==201, r.text
    return dict(client_id=r.json()['client_id'],service='diagnosis',business_question='为什么品牌没有出现在 AI 回答中？',market_scope='global')

def submit(c, body=None, key='one'):
    return c.post('/requests',headers={**h(),'Idempotency-Key':key},json=body or seed(c))

def action(c,r,act,key='tech',**extra):
    return c.post('/requests/'+r['request_id']+'/'+act,headers=h(key),json={'revision':r['workflow']['revision'],**extra})

def scoped(c,r):
    result=action(c,r,'scope',scope={'summary':'单次网站诊断','confirmed_duration':'3 个工作日','deliverables':['诊断报告'],'exclusions':['不含代运营']})
    assert result.status_code==200,result.text
    return result.json()

def test_submission_replay_conflict_and_no_automatic_project(client):
    body=seed(client)
    a=submit(client,body);assert a.status_code==201,a.text
    assert a.json()['status']=='submitted'
    assert client.get('/projects',headers=h()).json()==[]
    b=submit(client,body);assert b.json()['request_id']==a.json()['request_id']
    assert len(client.get('/requests',headers=h()).json())==1
    assert submit(client,{**body,'business_question':'different'}).status_code==409

def test_clarification_scope_approval_and_restart(client):
    r=submit(client).json()
    r=action(client,r,'clarification',note='请补充目标客户').json()
    assert r['status']=='clarification_required'
    assert action(client,r,'scope',scope={'summary':'x','confirmed_duration':'x','deliverables':['x']}).status_code==409
    r=action(client,r,'supplement','admin',note='目标为美国批发商').json()
    assert r['status']=='intake_review'
    r=scoped(client,r)
    assert action(client,r,'approve').status_code==403
    approved=action(client,r,'approve','manager');assert approved.status_code==200,approved.text
    p=approved.json()['project_id'];assert p
    assert action(client,r,'approve','manager').json()['project_id']==p
    assert action(client,approved.json(),'scope',scope={'summary':'changed','confirmed_duration':'1 day','deliverables':['changed']}).status_code==409
    path=state.active_db_path;state.init_repositories(path)
    saved=client.get('/requests/'+r['request_id'],headers=h()).json()
    assert saved['workflow']['scope']['confirmed_duration']=='3 个工作日'
    assert len(saved['workflow']['history'])==5
    project=client.get('/projects/'+p,headers=h()).json()
    assert project['request_summary']['scope']['approved_by']

def test_permissions_and_scope_queries(client):
    r=submit(client).json();rid=r['request_id']
    for route in ['/requests/'+rid,'/clients/'+r['client_id']]:
        assert client.get(route,headers=h('other')).status_code==404
    assert client.get('/requests?tenant_id=T-PORTAL',headers=h('other')).status_code==403
    assert client.get('/requests?tenant_id=T-PORTAL',headers=h('tech')).status_code==200
    assert client.get('/requests/'+rid).status_code==401
    assert client.post('/requests',headers={**h('view'),'Idempotency-Key':'x'},json=seed(client)).status_code==403
    assert action(client,r,'approve','admin').status_code==403
    assert action(client,r,'scope','admin').status_code==403
    assert client.post('/projects',headers=h(),json={**seed(client),'tenant_id':'T-PORTAL'}).status_code==403
    for endpoint in ('start','stage','stage/complete'):
        assert client.post('/projects/none/'+endpoint,headers=h(),json={}).status_code==403
    assert client.delete('/projects/none',headers=h()).status_code==403

def test_memory_backend_and_bff_header_forwarding(client):
    # Persisted mode is the deployment path, but the existing development mode
    # must have the same state/permission semantics.
    # init_repositories(None) may use an environment path from another suite.
    # Explicitly exercise memory repositories through the supported env unset.
    import os
    previous=os.environ.pop('GEO_DISTRIBUTOR_DB',None)
    try:
        state.init_repositories()
        r=submit(client,key='memory').json()
        assert r['status']=='submitted'
        approved=action(client,scoped(client,r),'approve','manager')
        assert approved.status_code==200,approved.text
        assert len(client.get('/projects',headers=h()).json())==1
        assert client.post('/ui/session',json={'api_key':'portal-admin'}).status_code==200
        body=seed(client)
        response=client.post('/ui/proxy/requests',headers={'Idempotency-Key':'bff-proof'},json=body)
        assert response.status_code==201,response.text
        again=client.post('/ui/proxy/requests',headers={'Idempotency-Key':'bff-proof'},json=body)
        assert again.json()['request_id']==response.json()['request_id']
        assert 'portal-admin' not in response.text
    finally:
        if previous is not None:os.environ['GEO_DISTRIBUTOR_DB']=previous

def test_stale_revision_rejection_and_validation(client):
    body=seed(client)
    assert submit(client,{**body,'business_question':' '}).status_code==422
    assert submit(client,{**body,'market_scope':'single','target_market':[]}).status_code==422
    assert submit(client,{**body,'target_market':['USA']}).status_code==422
    r=submit(client,body).json()
    updated=action(client,r,'clarification',note='补充').json()
    assert action(client,r,'reject','manager',note='重复旧页面').status_code==409
    rejected=action(client,updated,'reject','manager',note='服务范围不符')
    assert rejected.status_code==200
    assert rejected.json()['workflow']['rejection_reason']=='服务范围不符'
    assert action(client,rejected.json(),'supplement','admin',note='x').status_code==409

def test_concurrent_approval_one_project(client):
    r=scoped(client,submit(client).json())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:action(client,r,'approve','manager'),range(4)))
    assert all(x.status_code==200 for x in results),[x.text for x in results]
    assert len({x.json()['project_id'] for x in results})==1
    assert len(client.get('/projects',headers=h()).json())==1

def test_atomic_approval_failure_rolls_back(client):
    r=scoped(client,submit(client).json())
    with sqlite3.connect(state.active_db_path) as db:
        db.execute("CREATE TRIGGER deny_approval BEFORE UPDATE ON requests WHEN json_extract(NEW.payload,'$.status')='approved' BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with TestClient(app,raise_server_exceptions=False) as c:
        assert action(c,r,'approve','manager').status_code==500
    assert client.get('/projects',headers=h()).json()==[]
    assert client.get('/requests/'+r['request_id'],headers=h()).json()['status']=='scope_pending_approval'

def test_legacy_report_quality_does_not_rewrite_values():
    from api.routers.reports import report_to_out
    original={'report_id':'R','content':{'visibility_score':0.0,'visibility_summary':{'mention_rate':'0%'}}}
    before=json.dumps(original)
    result=report_to_out(original)
    assert result['visibility_score']==0.0
    assert result['data_quality']['valid_queries'] is None
    assert json.dumps(original)==before

def test_bff_protected_paths_and_anonymous_session(client):
    assert client.get('/ui/proxy/requests').status_code==401
    assert client.post('/ui/session',json={'api_key':'portal-admin'}).json()['ok']
    assert client.get('/ui/proxy/requests').status_code==200
    for path in ('config','requests/%2e%2e/config','requests/%252e%252e/config'):
        assert client.get('/ui/proxy/'+path).status_code in (403,404)
    assert client.get('/ui/proxy/requests?tenant_id=T-OTHER').status_code==403
    assert client.delete('/ui/session').status_code==200
    assert client.get('/ui/proxy/requests').status_code==401

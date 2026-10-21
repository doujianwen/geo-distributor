"""HQ tenant scope, atomic operations and honest queue semantics."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from api import state, auth, ui, hq_service as svc
from api.app import app
from scripts.portal_demo_data import seed_demo
from scripts.customer_demo_data import seed_customer_demo
from scripts.hq_demo_data import seed_hq_demo

KEYS = 'DEMO-GEO:hq-admin:HQ_MANAGEMENT,DEMO-GEO:hq-ops:HQ_TECHNICAL,DEMO-GEO:channel:DISTRIBUTOR_ADMIN,DEMO-GEO:member:DISTRIBUTOR_USER,DEMO-GEO:viewer:CLIENT_VIEWER,DEMO-GEO:customer:END_CUSTOMER:DEMO-CLI-1,DEMO-PARTNER:partner:DISTRIBUTOR_ADMIN'

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS', KEYS)
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB', str(tmp_path / 'audit.db'))
    monkeypatch.setenv('GEO_DISTRIBUTOR_ENV', 'production')
    monkeypatch.delenv('GEO_DISTRIBUTOR_DEMO_ONLY', raising=False)
    monkeypatch.setattr(auth, 'REGISTRY_FILE', tmp_path / 'no-registry.json')
    from api.ratelimit import limiter
    for obj in (limiter,ui._login_limiter):
        monkeypatch.setattr(obj, 'rate_per_min', 100000)
        monkeypatch.setattr(obj, 'burst', 100000)
    asyncio.run(seed_demo(tmp_path / 'portal-demo'))
    asyncio.run(seed_customer_demo())
    asyncio.run(seed_hq_demo())
    state._measurement_results.clear()
    with TestClient(app) as c: yield c


def h(key='hq-admin',tenant=None,ik=None):
    return {'X-API-Key':key, **({'X-Tenant-ID':tenant} if tenant else {}), **({'Idempotency-Key':ik} if ik else {})}


def op_body(action='complete',project='DEMO-PRJ-1',tenant='DEMO-GEO'):
    p=asyncio.run(state.project_repo.find_by_id(project,tenant_id=tenant))
    return {'action':action,'expected_updated_at':p.updated_at}


@pytest.mark.parametrize('key',['channel','member','viewer','customer','partner'])
def test_hq_boundary(client,key):
    assert client.get('/hq/workspace',headers=h(key)).status_code==403
    assert client.post('/hq/projects/DEMO-PRJ-1/operation',headers=h(key,ik='x'),json=op_body()).status_code==403


def test_scope_counts_and_secrets(client):
    d=client.get('/hq/workspace',headers=h()).json()
    assert {p['tenant_id'] for p in d['projects']}=={'DEMO-GEO','DEMO-PARTNER'}
    assert d['counts']=={'unassigned':1,'scoping':1,'approval':1,'blocked':1,'awaiting_customer':2,'awaiting_team':1,'unpublished':1,'invalid':0}
    one=client.get('/hq/workspace?tenant_id=DEMO-PARTNER',headers=h()).json()
    assert len(one['clients'])==1 and one['counts']['unassigned']==0 and one['counts']['approval']==1
    assert all(r['tenant_id']=='DEMO-PARTNER' for k in ('clients','projects','requests','leads','reviews','reports','events') for r in one[k])
    assert client.get('/hq/workspace?tenant_id=BOGUS',headers=h()).status_code==404
    assert client.get('/hq/workspace?tenant_id=DEMO-PARTNER',headers=h(tenant='DEMO-GEO')).status_code==403
    assert all(k not in json.dumps(d) for k in ('hq-admin','hq-ops','api_key','report_sha256','fingerprint'))


def test_historical_channel_not_assignable(client):
    from geo_distributor.models.client import Client
    asyncio.run(state.client_repo.create(Client('HIST-C','HISTORIC','历史客户')))
    d=client.get('/hq/workspace',headers=h()).json()
    assert next(t for t in d['tenants'] if t['tenant_id']=='HISTORIC')['assignable'] is False
    assert client.post('/leads/DEMO-HQ-LEAD-1/assign',headers=h(),json={'tenant_id':'HISTORIC'}).status_code==422
    assert len(client.get('/hq/workspace?tenant_id=HISTORIC',headers=h()).json()['clients'])==1


def test_publication_visibility_changes_and_missing(client):
    pubs=asyncio.run(state.customer_publication_repo.list_by_tenant('DEMO-GEO'))
    p=next(p for p in pubs if p['report_id']=='DEMO-RPT-1')
    assert client.post('/client-publications/'+p['publication_id']+'/withdraw',headers=h(),json={'revision':p['revision']}).status_code==200
    repo=state.report_service._repository
    r=asyncio.run(repo.get('DEMO-RPT-2'));r['title']+=' changed';asyncio.run(repo.upsert(r))
    d=client.get('/hq/workspace',headers=h()).json()
    assert {r['report_id']:r['status'] for r in d['reports']}=={'DEMO-RPT-1':'withdrawn','DEMO-RPT-2':'invalid','DEMO-RPT-HQ-UNPUBLISHED':'unpublished'}
    assert d['counts']['invalid']==1
    c=repo._connect();c.execute("DELETE FROM reports_projection WHERE id='DEMO-RPT-2'");c.commit();c.close()
    d=client.get('/hq/workspace',headers=h()).json()
    assert d['counts']['invalid']==1 and any(r['title']=='原报告缺失' for r in d['reports'])


def test_dependency_failure_not_zero(client,monkeypatch):
    async def fail(*args,**kwargs):raise RuntimeError('unavailable')
    monkeypatch.setattr(svc,'all_rows',fail)
    with TestClient(app,raise_server_exceptions=False) as c:r=c.get('/hq/workspace',headers=h())
    assert r.status_code==500 and 'counts' not in r.text


def test_direct_assignment_replay_and_conflict(client):
    body={'tenant_id':'HQ-INTAKE','create_client':True,'client_name':'Direct test'}
    a=client.post('/leads/DEMO-HQ-LEAD-1/assign',headers=h(),json=body)
    b=client.post('/leads/DEMO-HQ-LEAD-1/assign',headers=h(),json=body)
    assert a.status_code==b.status_code==200 and b.json()['deduplicated']
    assert a.json()['client_id']==b.json()['client_id']
    assert len(asyncio.run(state.client_repo.find_by_tenant('HQ-INTAKE')))==1
    assert client.post('/leads/DEMO-HQ-LEAD-1/assign',headers=h(),json={**body,'tenant_id':'DEMO-GEO'}).status_code==409


def test_assignment_concurrency(client):
    ctx=auth.verify_api_key('hq-admin');body={'tenant_id':'DEMO-PARTNER','create_client':True,'client_name':'Concurrent'}
    with ThreadPoolExecutor(4) as pool:rows=list(pool.map(lambda _:svc.assign('DEMO-HQ-LEAD-1',body,ctx),range(4)))
    assert len({r['client_id'] for r in rows})==1
    assert len(asyncio.run(state.client_repo.find_by_tenant('DEMO-PARTNER')))==2


def test_assignment_rollback(client,monkeypatch):
    original=svc.Unit.put
    def fail(self,table,item):
        if table=='leads_intake':raise RuntimeError('write failed')
        return original(self,table,item)
    monkeypatch.setattr(svc.Unit,'put',fail)
    with pytest.raises(RuntimeError):svc.assign('DEMO-HQ-LEAD-1',{'tenant_id':'DEMO-PARTNER','create_client':True},auth.verify_api_key('hq-admin'))
    assert len(asyncio.run(state.client_repo.find_by_tenant('DEMO-PARTNER')))==1
    assert asyncio.run(state.lead_repo.get('DEMO-HQ-LEAD-1'))['intake_status']=='pending_assignment'


def test_operation_replay_conflict_restart(client):
    body=op_body();url='/hq/projects/DEMO-PRJ-1/operation'
    r=client.post(url,headers=h(ik='once'),json=body)
    assert r.status_code==200 and r.json()['stage_progress']==100 and r.json()['status']=='in_execution'
    assert client.post(url,headers=h(ik='once'),json=body).json()['deduplicated']
    assert client.post(url,headers=h(ik='different'),json=body).status_code==409
    assert client.post(url,headers=h(ik='once'),json={**body,'action':'advance'}).status_code==409
    state.init_repositories(state.active_db_path)
    assert client.post(url,headers=h(ik='once'),json=body).json()['deduplicated']
    assert sum(e['source']=='project' for e in client.get('/hq/workspace',headers=h()).json()['events'])==1


def test_operation_concurrency(client):
    ctx=auth.verify_api_key('hq-admin');body=op_body()
    def invoke(i):
        try:return svc.project_operation('DEMO-PRJ-1',body,str(i),ctx)
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(4) as pool:rows=list(pool.map(invoke,range(4)))
    assert sum(isinstance(r,dict) for r in rows)==1 and rows.count(409)==3
    assert len(asyncio.run(svc.all_rows("hq_operations")))==1


def test_operation_rollback(client,monkeypatch):
    original=svc.Unit.put;before=op_body()
    def fail(self,table,item):
        if table=='hq_operations':raise RuntimeError('no event')
        return original(self,table,item)
    monkeypatch.setattr(svc.Unit,'put',fail)
    with pytest.raises(RuntimeError):svc.project_operation('DEMO-PRJ-1',before,'rollback',auth.verify_api_key('hq-admin'))
    assert op_body()==before and not asyncio.run(svc.all_rows("hq_operations"))


@pytest.mark.parametrize('path',['/projects/DEMO-PRJ-1/start','/projects/DEMO-PRJ-1/stage','/projects/DEMO-PRJ-1/stage/complete'])
def test_old_lifecycle_no_bypass(client,path):
    assert client.post(path,headers=h(),json={}).status_code==422
    body={'expected_updated_at':op_body()['expected_updated_at'],'measurement_ids':['OTHER-MSR']}
    assert client.post(path,headers=h(ik='ref'),json=body).status_code==422
    assert client.post(path,headers=h('channel'),json={}).status_code==403


def test_start_block_resume_and_cross_tenant(client):
    url='/hq/projects/DEMO-PRJ-PARTNER/operation?tenant_id=DEMO-PARTNER'
    assert client.post(url,headers=h(ik='p1'),json=op_body('complete','DEMO-PRJ-PARTNER','DEMO-PARTNER')).status_code==409
    assert client.post(url,headers=h(ik='p2'),json=op_body('start','DEMO-PRJ-PARTNER','DEMO-PARTNER')).status_code==200
    assert client.post(url,headers=h(ik='p3'),json=op_body('advance','DEMO-PRJ-PARTNER','DEMO-PARTNER')).status_code==200
    assert client.post('/hq/projects/DEMO-PRJ-PARTNER/operation?tenant_id=DEMO-GEO',headers=h(ik='p4'),json=op_body('complete','DEMO-PRJ-PARTNER','DEMO-PARTNER')).status_code==404
    body={**op_body('block'),'note':'waiting','required_action':'review','owner':'HQ'}
    assert client.post('/hq/projects/DEMO-PRJ-1/operation',headers=h(ik='block'),json=body).status_code==200
    assert client.post('/hq/projects/DEMO-PRJ-1/operation',headers=h(ik='blocked'),json=op_body()).status_code==409
    assert client.post('/hq/projects/DEMO-PRJ-1/operation',headers=h(ik='resume'),json={**op_body('resume'),'note':'checked'}).status_code==200


@pytest.mark.parametrize('change',['revoke','downgrade','rebind'])
def test_session_current_identity(client,monkeypatch,change):
    assert client.post('/ui/hq/session',json={'api_key':'hq-admin'}).status_code==200
    altered=KEYS.replace('DEMO-GEO:hq-admin:HQ_MANAGEMENT',{'revoke':'','downgrade':'DEMO-GEO:hq-admin:CLIENT_VIEWER','rebind':'DEMO-PARTNER:hq-admin:HQ_MANAGEMENT'}[change])
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS',altered)
    assert client.get('/ui/hq/session').json()['ok'] is False
    assert client.get('/ui/hq/proxy/hq/workspace').status_code==401


def test_bff_cookie_independence_and_logout(client):
    assert client.post('/ui/session',json={'api_key':'channel'}).status_code==200
    assert client.post('/ui/hq/session',json={'api_key':'hq-admin'}).status_code==200
    assert client.get('/ui/proxy/hq/workspace').status_code==403
    assert client.get('/ui/hq/proxy/hq/workspace?tenant_id=DEMO-PARTNER').json()['scope']=='DEMO-PARTNER'
    assert client.get('/ui/hq/proxy/hq/../auth').status_code in (403,404)
    r=client.delete('/ui/hq/session')
    assert 'Max-Age=0' in r.headers['set-cookie'] and 'Path=/ui/hq' in r.headers['set-cookie']
    assert client.get('/ui/session').json()['role']=='DISTRIBUTOR_ADMIN'
    assert client.get('/ui/hq/proxy/hq/workspace').status_code==401


def test_demo_hq_roles_and_write_shield(client,monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_DEMO_ONLY','1')
    monkeypatch.setenv('GEO_DISTRIBUTOR_HQ_DEMO_KEY','hq-admin')
    monkeypatch.setenv('GEO_DISTRIBUTOR_OPS_DEMO_KEY','hq-ops')
    assert client.post('/ui/hq/demo-session?role=management').json()['role']=='HQ_MANAGEMENT'
    assert client.post('/ui/hq/demo-session?role=operations').json()['role']=='HQ_TECHNICAL'
    assert client.get('/ui/hq/proxy/hq/workspace').status_code==200
    for url,body in [('/leads/DEMO-HQ-LEAD-1/assign',{'tenant_id':'DEMO-GEO','create_client':True}),('/requests/DEMO-REQ-APPROVAL/approve',{'revision':1}),('/hq/projects/DEMO-PRJ-1/operation',op_body()),('/client-publications',{'report_id':'DEMO-RPT-1'}),('/client-reviews/no/process',{'revision':1,'action':'close','note':'x'})]:
        assert client.post(url,headers=h(ik='demo'),json=body).status_code==403
    assert asyncio.run(state.lead_repo.get('DEMO-HQ-LEAD-1'))['intake_status']=='pending_assignment'
    assert not asyncio.run(svc.all_rows("hq_operations"))

def test_memory_orchestration_matches_sqlite_contract(client,monkeypatch):
    from geo_distributor.models.client import Client
    from geo_distributor.models.project import Project
    monkeypatch.delenv('GEO_DISTRIBUTOR_DB',raising=False)
    state.init_repositories()
    asyncio.run(state.client_repo.create(Client('MEM-C','DEMO-GEO','Memory customer')))
    asyncio.run(state.project_repo.create(Project('MEM-P','MEM-R','DEMO-GEO','MEM-C','MEM-S')))
    ctx=auth.verify_api_key('hq-admin')
    body=op_body('start','MEM-P')
    first=svc.project_operation('MEM-P',body,'memory-once',ctx)
    assert first['status']=='in_execution'
    assert svc.project_operation('MEM-P',body,'memory-once',ctx)['deduplicated']
    row={'lead_id':'MEM-L','tenant_id':'HQ-INTAKE','project_id':'','client_id':'','request_id':'','intake_status':'pending_assignment','contact':{'company':'Memory lead'},'audit':[]}
    asyncio.run(state.lead_repo.upsert(row))
    a=svc.assign('MEM-L',{'tenant_id':'DEMO-GEO','create_client':True},ctx)
    b=svc.assign('MEM-L',{'tenant_id':'DEMO-GEO','create_client':True},ctx)
    assert a['client_id']==b['client_id'] and b['deduplicated']
    data=asyncio.run(svc.workspace(ctx))
    assert len(data['clients'])==2 and len(data['projects'])==1
    assert data['events'][0]['source'] in ('lead','project')


def test_request_selected_scope_conflict_is_rejected(client):
    url='/requests/DEMO-REQ-APPROVAL?tenant_id=DEMO-GEO'
    assert client.get(url,headers=h()).status_code==404
    assert client.post('/requests/DEMO-REQ-APPROVAL/approve?tenant_id=DEMO-GEO',headers=h(),json={'revision':1}).status_code==404
    assert client.get('/requests/DEMO-REQ-APPROVAL?tenant_id=DEMO-PARTNER',headers=h()).status_code==200


def test_hq_demo_reseed_preserves_queues_and_boundaries(client):
    async def snapshot():
        rows={t:await svc.all_rows(t) for t in svc.TABLES}
        rows['reports_projection']=await svc.all_rows('reports_projection',state.report_service._repository)
        rows['client_publications']=await svc.all_rows('client_publications',state.customer_publication_repo)
        rows['client_reviews']=await svc.all_rows('client_reviews',state.customer_review_repo)
        return svc.fingerprint({t:sorted(r,key=lambda v:json.dumps(v,sort_keys=True)) for t,r in rows.items()})
    before=asyncio.run(snapshot());db=state.active_db_path
    from pathlib import Path
    asyncio.run(seed_demo(Path(db).parent))
    asyncio.run(seed_customer_demo())
    asyncio.run(seed_hq_demo())
    assert asyncio.run(snapshot())==before
    conn=state.project_repo._connect()
    row=json.loads(conn.execute("SELECT payload FROM projects WHERE id='DEMO-PRJ-1'").fetchone()[0])
    row['project_id']='REAL-PROJECT-ID'
    conn.execute('UPDATE projects SET payload=? WHERE id=?',(json.dumps(row),'DEMO-PRJ-1'));conn.commit();conn.close()
    with pytest.raises(RuntimeError,match='non-demo'):asyncio.run(seed_demo(Path(db).parent))

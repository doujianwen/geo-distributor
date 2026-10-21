"""Independent adversarial acceptance. Only tmp_path databases; no network providers."""
import asyncio
import base64
import hashlib
import hmac
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from api import personal_identity as identity, growth_core
from scripts.growth_workspace_setup import create_core


@pytest.fixture
def identity_env(tmp_path, monkeypatch):
    monkeypatch.setenv('GEO_IDENTITY_DB', str(tmp_path / 'identity.db'))
    monkeypatch.setenv('GEO_IDENTITY_SECRET', 'independent-isolated-test-secret-0000000000')
    monkeypatch.setenv('GEO_IDENTITY_ISSUER', 'https://isolated.example')


def assertion(**changes):
    data = dict(issuer=os.environ['GEO_IDENTITY_ISSUER'], user_id='123', issued_at=int(time.time()), nonce=uuid4().hex)
    data.update(changes)
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
    signature = hmac.new(os.environ['GEO_IDENTITY_SECRET'].encode(), payload.encode(), hashlib.sha256).hexdigest()
    return identity.Assertion(payload=payload, signature=signature)


def test_signed_assertion_tamper_expiry_wrong_issuer_and_replay(identity_env):
    for body in (assertion(issued_at=int(time.time()) - 600), assertion(issuer='https://foreign.example')):
        with pytest.raises(HTTPException) as denied:
            asyncio.run(identity.exchange(body))
        assert denied.value.status_code == 401
    body = assertion()
    bad = identity.Assertion(payload=body.payload, signature='0' * 64)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(identity.exchange(bad))
    assert denied.value.status_code == 401
    asyncio.run(identity.exchange(body))
    with pytest.raises(HTTPException) as denied:
        asyncio.run(identity.exchange(body))
    assert denied.value.status_code == 409


def test_security_validation_survives_python_optimization(identity_env):
    # A production interpreter flag must not remove issuer/time validation.
    body = assertion(issued_at=int(time.time()) - 600, issuer='https://foreign.example')
    program = '''import asyncio,json,sys
from api.personal_identity import Assertion,exchange
from fastapi import HTTPException
try:
 asyncio.run(exchange(Assertion(**json.loads(sys.argv[1]))))
 print('ACCEPTED_INVALID_ASSERTION')
except HTTPException as e:
 print('REJECTED',e.status_code)
'''
    result = subprocess.run([sys.executable, '-O', '-c', program, body.model_dump_json()], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'REJECTED 401' in result.stdout, result.stdout


def test_person_subject_durable_and_revocation_immediate(identity_env):
    first = asyncio.run(identity.exchange(assertion()))
    c = identity.connect()
    subject = c.execute('SELECT subject FROM identity_people').fetchone()[0]
    c.execute('INSERT INTO identity_memberships VALUES(?,?,?,?,?,?)', (subject, 'tenant-a', 'HQ_TECHNICAL', None, 1, 1))
    c.execute('INSERT INTO identity_sessions VALUES(?,?,?)', (identity.digest('person_first'), subject, int(time.time())+600))
    c.commit()
    assert identity.token_context('person_first').user_id == subject
    c.execute('UPDATE identity_memberships SET enabled=0 WHERE subject=?', (subject,)); c.commit()
    assert identity.token_context('person_first') is None
    asyncio.run(identity.exchange(assertion()))
    assert c.execute('SELECT count(*) FROM identity_people').fetchone()[0] == 1
    assert first['expires_in'] == 60
    c.close()


def test_ticket_consumption_and_expiration(identity_env):
    from starlette.requests import Request
    body = asyncio.run(identity.exchange(assertion()))
    request = Request({'type':'http', 'method':'GET', 'path':'/ui/account/enter', 'headers':[], 'scheme':'http', 'server':('testserver',80), 'query_string':b''})
    response = asyncio.run(identity.enter(body['ticket'], request))
    assert response.status_code == 303
    assert response.headers['location'] == '/ui/account/'
    assert 'httponly' in response.headers['set-cookie'].lower()
    with pytest.raises(HTTPException) as denied:
        asyncio.run(identity.enter(body['ticket'], request))
    assert denied.value.status_code == 401
    expired = asyncio.run(identity.exchange(assertion()))
    c = identity.connect()
    c.execute('UPDATE identity_tickets SET expires_at=0 WHERE digest=?',(identity.digest(expired['ticket']),)); c.commit(); c.close()
    with pytest.raises(HTTPException) as denied:
        asyncio.run(identity.enter(expired['ticket'], request))
    assert denied.value.status_code == 401


@pytest.fixture
def independent_world(tmp_path):
    path = create_core(tmp_path / 'independent.db')
    c = sqlite3.connect(path); c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    core = growth_core.contract()
    adapter = importlib.import_module(core.__package__ + '.operator_contract')
    with core.atomic(c) as tx:
        core.bind(tx, project_key='t/p', tenant='t', client='a', name='Owned', domain='https://owned.example')
        core.bind(tx, project_key='u/q', tenant='u', client='b', name='Foreign', domain='https://foreign.example')
    binding = core.binding(c, 't/p', 't', 'a')
    def write(route, payload=None, method='POST'):
        revision = c.execute('SELECT revision FROM workspace_sites WHERE site_id=?', (binding['site_id'],)).fetchone()[0]
        return adapter.operate(c, binding, method, route, payload or {}, {}, revision=revision,
                               key=uuid4().hex, subject='operator-a', authorize=lambda _:None)['result']
    yield c, core, adapter, binding, write
    c.close()


def test_classification_preview_cannot_be_modified_before_apply(independent_world):
    c, core, adapter, b, write = independent_world
    pid = b['product_id']
    question = write('questions', {'text':'如何选择工具'})
    write(f'products/{pid}/keywords', {'name':'选择', 'pattern':'选择', 'type':'keyword', 'intent_class':'推荐'})
    preview = write(f'products/{pid}/questions/classify-by-keywords')
    assert preview['drafts']
    changed = json.loads(json.dumps(preview['drafts']))
    changed[0]['intent_class'] = '比较'
    with pytest.raises(core.ContractError):
        write(f'products/{pid}/questions/classify-by-keywords/apply', {'drafts':changed})
    row = c.execute('SELECT intent_class FROM questions WHERE id=?', (question['id'],)).fetchone()
    assert not row[0]


def test_native_read_has_no_commit_or_write_side_effect(independent_world):
    c, core, adapter, b, write = independent_world
    write('questions', {'text':'read baseline'})
    before = c.total_changes
    for path in ('products', f"products/{b['product_id']}/dashboard", f"products/{b['product_id']}/questions", 'prompts', 'manual'):
        adapter.dispatch(c, b, 'GET', path)
    assert c.total_changes == before
    assert not c.in_transaction


def test_object_conflict_protects_same_question_without_blocking_unrelated_edit(independent_world):
    c, core, adapter, b, write = independent_world
    first = write('questions', {'text':'first question'})['id']
    second = write('questions', {'text':'second question'})['id']
    version = c.execute('SELECT revision FROM workspace_sites WHERE site_id=?',(b['site_id'],)).fetchone()[0]
    snapshots = {ident:core.digest(adapter.owned(c,b,'questions',ident)) for ident in (first,second)}
    def edit(ident,text):
        return adapter.operate(c,b,'PUT',f'questions/{ident}',{'text':text},{},revision=version,
                               key=uuid4().hex,subject='operator-b',authorize=lambda _:None,object_version=snapshots[ident])
    edit(first,'first changed')
    edit(second,'second changed concurrently')
    with pytest.raises(core.ContractError) as denied:
        edit(first,'first stale overwrite')
    assert denied.value.status==409
    assert c.execute('SELECT text FROM questions WHERE id=?',(first,)).fetchone()[0]=='first changed'


def test_unauthorized_project_get_and_canonical_quality_paths_rejected(independent_world):
    c, core, adapter, b, write = independent_world
    other = core.binding(c, 'u/q', 'u', 'b')
    for method, path in [('GET',f"products/{other['product_id']}/questions"), ('POST','quality'), ('POST','report'), ('POST','observations/1/quality')]:
        with pytest.raises(core.ContractError):
            adapter.dispatch(c, b, method, path, {})
    assert c.execute('SELECT count(*) FROM observation_quality_reviews').fetchone()[0] == 0


@pytest.fixture
def independent_http(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import auth, ui
    from api.app import app
    from scripts.portal_demo_data import seed_demo
    from scripts.customer_demo_data import seed_customer_demo
    from api.ratelimit import limiter
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS', 'DEMO-GEO:root:HQ_MANAGEMENT,DEMO-GEO:author:HQ_TECHNICAL,DEMO-GEO:reviewer:HQ_TECHNICAL,DEMO-GEO:client:END_CUSTOMER_EDITOR:DEMO-CLI-1')
    monkeypatch.setenv('GEO_DISTRIBUTOR_ENV', 'production')
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB', str(tmp_path/'audit.db'))
    monkeypatch.delenv('GEO_DISTRIBUTOR_DEMO_ONLY', raising=False)
    monkeypatch.setattr(auth,'REGISTRY_FILE',tmp_path/'empty.json')
    for obj in (limiter,ui._login_limiter):
        monkeypatch.setattr(obj,'rate_per_min',100000); monkeypatch.setattr(obj,'burst',100000)
    asyncio.run(seed_demo(tmp_path/'portal-demo'))
    asyncio.run(seed_customer_demo())
    monkeypatch.setenv('GEO_GROWTH_WORKSPACE_DB',str(create_core(tmp_path/'http.db')))
    prefix='/growth/projects/DEMO-PRJ-1'
    def headers(who): return {'X-API-Key':who,'Idempotency-Key':uuid4().hex}
    with TestClient(app) as client:
        response=client.post(prefix+'/bind',headers=headers('root'),json={'revision':0,'payload':{'name':'Fiction','domain':'https://fiction.example'}})
        assert response.status_code==200,response.text
        def grant(who,caps,resource_ids=None):
            payload={'subject':auth.verify_api_key(who).user_id,'capabilities':caps}
            if resource_ids is not None: payload['resource_ids']=resource_ids
            response=client.post(prefix+'/access',headers=headers('root'),json=payload)
            assert response.status_code==200,response.text
        def post(who,operation,payload):
            current=client.get(prefix,headers=headers(who))
            assert current.status_code==200,current.text
            return client.post(prefix+'/'+operation,headers=headers(who),json={'revision':current.json()['data']['revision'],'payload':payload})
        yield client,prefix,grant,post,headers


def test_explicit_customer_prepare_capability_is_effective(independent_http):
    client,prefix,grant,post,headers=independent_http
    grant('client',['prepare'])
    result=post('client','question',{'text':'Customer-prepared question'})
    assert result.status_code==200,result.text
    assert client.get(prefix+'/operator/context',headers=headers('client')).status_code==403


def test_selected_resource_cannot_escape_project_and_does_not_stick(independent_http):
    client,prefix,grant,post,headers=independent_http
    grant('author',['operate'])
    primary=client.get(prefix+'/operator/context',headers=headers('author')).json()
    secondary=client.post(prefix+'/resources',headers=headers('root'),json={'name':'Second authorized resource','domain':'https://second.example'})
    assert secondary.status_code==200,secondary.text
    second_id=secondary.json()['site_id']
    ungranted=client.get(prefix+'/operator/context',params={'workspace_site_id':second_id},headers=headers('author'))
    assert ungranted.status_code in {403,404}, 'Adding a project resource must not automatically grant raw product access'
    grant('author',['operate'],[primary['site_id'],second_id])
    selected=client.get(prefix+'/operator/context',params={'workspace_site_id':second_id},headers=headers('author'))
    assert selected.status_code==200,selected.text
    assert selected.json()['site_id']==second_id
    # The request-local selection must never mutate the repository's project object.
    assert client.get(prefix+'/operator/context',headers=headers('author')).json()['site_id']==primary['site_id']
    foreign='/growth/projects/DEMO-PRJ-2'
    from api import state
    from geo_distributor.models.project import ProjectStatus
    other_project=asyncio.run(state.project_repo.find_by_id('DEMO-PRJ-2',tenant_id='DEMO-GEO'))
    other_project.status=ProjectStatus.IN_EXECUTION
    asyncio.run(state.project_repo.update(other_project))
    other=client.post(foreign+'/bind',headers=headers('root'),json={'revision':0,'payload':{'name':'Other client','domain':'https://other.example'}})
    assert other.status_code==200,other.text
    foreign_site=other.json()['site_id']
    for who in ('author','client','root'):
        denied=client.get(prefix,params={'workspace_site_id':foreign_site},headers=headers(who))
        assert denied.status_code==404,denied.text
    assert client.get(foreign+'/operator/context',params={'workspace_site_id':second_id},headers=headers('author')).status_code==404
    denied=client.post(prefix+'/operator/api/questions',params={'workspace_site_id':foreign_site},headers={**headers('author'),'If-Match':str(primary['revision'])},json={'text':'Must not enter foreign resource'})
    assert denied.status_code==404,denied.text


def test_only_secondary_authorization_cannot_become_primary_by_omitting_selection(independent_http):
    client,prefix,grant,post,headers=independent_http
    primary=client.get(prefix,headers=headers('root')).json()['data']['site']['id']
    added=client.post(prefix+'/resources',headers=headers('root'),json={'name':'Secondary only','domain':'https://secondary.example'})
    assert added.status_code==200,added.text
    secondary=added.json()['site_id']
    grant('author',['operate'],[secondary])
    allowed=client.get(prefix+'/operator/context',params={'workspace_site_id':secondary},headers=headers('author'))
    assert allowed.status_code==200,allowed.text
    explicit=client.get(prefix+'/operator/context',params={'workspace_site_id':primary},headers=headers('author'))
    assert explicit.status_code in {403,404},explicit.text
    default=client.get(prefix+'/operator/context',headers=headers('author'))
    if default.status_code==200:
        assert default.json()['site_id']==secondary, 'Omitted resource selection must not union grants into the primary product'
    else:
        assert default.status_code in {403,404},default.text


def test_cancelled_project_keeps_read_but_rejects_operator_write(independent_http):
    from api import state
    from geo_distributor.models.project import ProjectStatus
    client,prefix,grant,post,headers=independent_http
    grant('author',['operate'])
    context=client.get(prefix+'/operator/context',headers=headers('author')).json()
    project=asyncio.run(state.project_repo.find_by_id('DEMO-PRJ-1',tenant_id='DEMO-GEO'))
    project.status=ProjectStatus.CANCELLED
    asyncio.run(state.project_repo.update(project))
    assert client.get(prefix,headers=headers('author')).status_code==200
    denied=client.post(prefix+'/operator/api/questions',headers={**headers('author'),'If-Match':str(context['revision'])},json={'text':'Cancelled project must not accept work'})
    assert denied.status_code in {403,409},denied.text
    denied=post('author','question',{'text':'Alternate write route must also stop'})
    assert denied.status_code in {403,409},denied.text


def test_author_reviewer_publisher_separation_and_customer_projection(independent_http):
    client,prefix,grant,post,headers=independent_http
    grant('author',['operate','quality_review'])
    grant('reviewer',['quality_review'])
    question=post('author','question',{'text':'Fictional question'})
    assert question.status_code==200,question.text
    payload=dict(question_id=question.json()['id'],provider='test',model='test',surface='test',language='en',market='US',environment='sandbox',question_set_version='v1',collector_version='fixture',request_config_hash=hashlib.sha256(b'config').hexdigest(),started_at='2026-10-01T10:00:00+00:00',completed_at='2026-10-01T10:10:00+00:00',observed_at='2026-10-01T10:05:00+00:00',prompt_text='Question',response_text='INTERNAL_RAW_ANSWER_SENTINEL',source_url='https://fiction.example/evidence',source_ref='isolated',brand_mentioned=1,citation_count=1,recommendation_level=1)
    observation=post('author','observation',payload)
    assert observation.status_code==200,observation.text
    queue=client.get(prefix,headers=headers('reviewer'))
    assert queue.status_code==200,queue.text
    assert 'INTERNAL_RAW_ANSWER_SENTINEL' in queue.text, 'Independent reviewer cannot see pending source needed for review'
    assert post('reviewer','question',{'text':'Reviewer must not edit research'}).status_code==403
    review={'observation_id':observation.json()['id'],'disposition':'APPROVED','reason':'Checked isolated source','evidence_checked':True}
    assert post('author','quality',review).status_code==403
    checked=post('reviewer','quality',review)
    assert checked.status_code==200,checked.text
    assert post('author','report',{'title':'Must deny publishing'}).status_code==403
    customer=client.get(prefix,headers=headers('client'))
    assert customer.status_code==200,customer.text
    assert 'INTERNAL_RAW_ANSWER_SENTINEL' not in customer.text
    grant('reviewer',[])
    assert client.get(prefix,headers=headers('reviewer')).status_code==404

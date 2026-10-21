"""Independent adversarial regressions: exclusively fixture-owned isolated databases."""
from tests.test_growth_workspace import client, post, view, h, prepare, observation, approve, PREFIX
from api import growth_core as gateway
import hashlib


def test_quality_roundtrip_without_read_must_not_resurrect_report(client):
    page,q,o,d,a=prepare(client)
    report=post(client,'report',{'title':'独立审计快照'})
    # Submit two mutations directly: the customer has not polled/read between them.
    revision=view(client)['data']['revision']
    r=client.post(PREFIX+'/quality',headers=h(),json={'revision':revision,'payload':dict(observation_id=o['id'],disposition='HOLD',reason='独立审计撤销',evidence_checked=False)})
    assert r.status_code==200,r.text
    r=client.post(PREFIX+'/quality',headers=h(),json={'revision':r.json()['revision'],'payload':dict(observation_id=o['id'],disposition='APPROVED',reason='独立审计重新核验',evidence_checked=True)})
    assert r.status_code==200,r.text
    result=client.get(PREFIX+'/reports/'+str(report['id']),headers=h('customer'))
    assert result.status_code==409, 'Old publication resurrected without explicit republishing: '+result.text


def test_held_source_must_hide_customer_deltas_and_diagnoses(client):
    page,q,o,d,a=prepare(client)
    second=post(client,'observation',observation(q,3));approve(client,second)
    post(client,'compare',dict(baseline=o['run_id'],comparison=second['run_id'],question=q))
    assert view(client,'customer')['data']['deltas']
    post(client,'quality',dict(observation_id=o['id'],disposition='HOLD',reason='来源待重新审查',evidence_checked=False))
    customer=view(client,'customer')['data']
    assert not customer['deltas'], 'Customer receives Delta values based on a held source'
    assert not customer['diagnoses'], 'Customer receives diagnosis supported only by a held source'
    assert customer['diagnosis_links']==[] and customer['action_links']==[], 'Held conclusions leak through new relationship projections'



def test_customer_action_cannot_promote_unconfirmed_diagnosis(client):
    from api import auth
    subject=auth.verify_api_key('editor').user_id
    post(client,'grant',{'subject':subject,'enabled':True})
    page=post(client,'page',{'url':'https://fiction.example/faq','title':'FAQ'})['id']
    q=post(client,'question',{'text':'Which fictional brand?'})['id']
    obs=post(client,'observation',observation(q));approve(client,obs)
    diagnosis=post(client,'diagnosis',dict(question_id=q,diagnosis_type='MISSING_PAGE',evidence_ids=[obs['evidence_id']],title='总部未确认',finding='尚待复核',rationale='待审',target_context='faq',page_ids=[page]))
    revision=view(client,'editor')['data']['revision']
    r=client.post(PREFIX+'/action',headers=h('editor'),json={'revision':revision,'payload':dict(action_type='CONTENT_UPDATE',title='不能自行确认诊断',target_context='faq',diagnosis_ids=[diagnosis['diagnosis_id']],page_ids=[page])})
    assert r.status_code in (403,409,422), 'Customer promoted unconfirmed diagnosis: '+r.text
    c=gateway.connection()
    try: assert c.execute('SELECT status FROM diagnoses WHERE id=?',(diagnosis['diagnosis_id'],)).fetchone()[0]=='open'
    finally:c.close()



def test_existing_delta_conflicting_with_frozen_values_is_not_reused(client):
    page,q,o,d,a=prepare(client)
    second=post(client,'observation',observation(q,3));approve(client,second)
    original=post(client,'compare',dict(baseline=o['run_id'],comparison=second['run_id'],question=q))
    c=gateway.connection()
    try:
        c.execute('UPDATE deltas SET baseline_value=999 WHERE id=?',(original['delta_ids'][0],));c.commit()
    finally:c.close()
    result=post(client,'compare',dict(baseline=o['run_id'],comparison=second['run_id'],question=q))
    assert not result['comparable'], 'Conflicting legacy Delta accepted as current comparable result'



def test_quality_service_inner_commit_and_snapshot_invalidation_roll_back_together(client):
    import pytest
    page,q,o,d,a=prepare(client)
    report=post(client,'report',{'title':'事务验证报告'})
    core=gateway.contract();c=gateway.connection()
    try:
        b=core.binding(c,'DEMO-GEO/DEMO-PRJ-1','DEMO-GEO','DEMO-CLI-1')
        revision=c.execute('SELECT revision FROM workspace_sites').fetchone()[0]
        before=c.execute('SELECT count(*) FROM observation_quality_review_events').fetchone()[0]
        def fault(tx): raise RuntimeError('fail after quality inner commit and report invalidation')
        with pytest.raises(RuntimeError):
            core.operate(c,b,'quality',dict(observation_id=o['id'],disposition='HOLD',reason='回滚注入',evidence_checked=False),revision=revision,key='audit-failed-quality',role='HQ_MANAGEMENT',subject='independent-audit',fault=fault)
        assert c.execute('SELECT disposition FROM observation_quality_reviews WHERE observation_id=?',(o['id'],)).fetchone()[0]=='APPROVED'
        assert c.execute('SELECT count(*) FROM observation_quality_review_events').fetchone()[0]==before
        assert c.execute('SELECT status FROM workspace_snapshots WHERE id=?',(report['id'],)).fetchone()[0]=='published'
        assert not c.execute("SELECT 1 FROM workspace_operations WHERE operation_key='audit-failed-quality'").fetchone()
        assert c.execute('SELECT revision FROM workspace_sites').fetchone()[0]==revision
    finally:c.close()



def test_real_brand_edit_and_seo_service_have_customer_evidence(client):
    post(client,'brand',{'name':'编辑后的虚拟品牌','market':'US','description':'客户可维护资料'})
    q=post(client,'question',{'text':'old'})['id']
    post(client,'edit_question',{'object_id':q,'text':'new'})
    assert view(client)['data']['questions'][0]['text']=='new'
    keyword=post(client,'keyword',{'name':'fiction converter'})['id']
    for day,rank in [(1,5),(10,20)]:
        post(client,'rank',dict(keyword_id=keyword,search_engine='google',observed_at=f'2026-10-{day:02d}T00:00:00+00:00',source_observation_id=f'audit-rank-{day}',rank=rank,url='https://fiction.example'))
    result=post(client,'seo_diagnosis',dict(keyword_id=keyword,search_engine='google'))
    assert result['created'],result
    diagnosis=result['created'][0]['diagnosis_id']
    post(client,'diagnosis_status',dict(diagnosis_id=diagnosis,status='confirmed'))
    data=view(client,'customer')['data']
    assert any(d['id']==diagnosis for d in data['diagnoses'])
    assert data['evidence'], 'Customer sees SEO diagnosis without its rank provenance evidence'
    assert data['diagnosis_links'], 'Confirmed SEO diagnosis lost explicit evidence relationship'
    payload=dict(action_type='CONTENT_UPDATE',title='SEO行动必须复核',target_context='fiction converter',diagnosis_ids=[diagnosis])
    post(client,'action',payload,code=422)
    review_at='2026-11-01T10:00:00+00:00'
    action=post(client,'action',dict(payload,review_at=review_at))
    c=gateway.connection()
    try:assert c.execute('SELECT review_at FROM actions WHERE id=?',(action['action_id'],)).fetchone()[0]==review_at
    finally:c.close()
    assert view(client,'customer')['data']['action_links']==[], 'Customer must not receive another actor planned action links'



def test_bind_retry_and_same_tenant_other_client_edit_isolation(client):
    from api import auth
    import asyncio
    from api import state
    from geo_distributor.models.project import ProjectStatus
    project=asyncio.run(state.project_repo.find_by_id('DEMO-PRJ-2',tenant_id='DEMO-GEO'))
    project.status=ProjectStatus.IN_EXECUTION
    asyncio.run(state.project_repo.update(project))
    path='/growth/projects/DEMO-PRJ-2'
    headers=h('hq','independent-bind-idempotency')
    body={'revision':0,'payload':{'name':'另一虚拟企业','domain':'https://other-fiction.example'}}
    a=client.post(path+'/bind',headers=headers,json=body)
    b=client.post(path+'/bind',headers=headers,json=body)
    assert a.status_code==b.status_code==200 and a.json()==b.json()
    d=client.get(path,headers=h()).json()['data']
    # Management/binding is not an implicit professional writing grant.
    grant=client.post(path+'/access',headers=h(),json={'subject':auth.verify_api_key('hq').user_id,'capabilities':['read','operate']})
    assert grant.status_code==200,grant.text
    q=client.post(path+'/question',headers=h(),json={'revision':d['revision'],'payload':{'text':'other client question'}})
    assert q.status_code==200,q.text
    post(client,'grant',{'subject':auth.verify_api_key('editor').user_id,'enabled':True})
    response=post(client,'edit_question',{'object_id':q.json()['id'],'text':'cross client attempt'},'editor',404)
    c=gateway.connection()
    try:assert c.execute('SELECT text FROM questions WHERE id=?',(q.json()['id'],)).fetchone()[0]=='other client question'
    finally:c.close()



def test_changed_collection_config_and_boolean_metric_cannot_make_delta(client):
    page,q,o,d,a=prepare(client)
    payload=observation(q,3);payload['request_config_hash']=hashlib.sha256(b'independent-other-config').hexdigest()
    different=post(client,'observation',payload);approve(client,different)
    result=post(client,'compare',dict(baseline=o['run_id'],comparison=different['run_id'],question=q))
    assert not result['comparable'] and result['delta_ids']==[]
    payload=observation(q,4);payload['brand_mentioned']=True
    malformed=post(client,'observation',payload);approve(client,malformed)
    result=post(client,'compare',dict(baseline=o['run_id'],comparison=malformed['run_id'],question=q))
    assert not result['comparable'] and result['delta_ids']==[]
    c=gateway.connection()
    try:assert c.execute('SELECT count(*) FROM deltas').fetchone()[0]==0
    finally:c.close()


def test_tampered_snapshot_body_rejected_without_exposing_body(client):
    page,q,o,d,a=prepare(client)
    report=post(client,'report',{'title':'完整性核验'})
    c=gateway.connection()
    try:
        c.execute('UPDATE workspace_snapshots SET snapshot=? WHERE id=?',('{"secret":"must not return"}',report['id']));c.commit()
    finally:c.close()
    result=client.get(PREFIX+'/reports/'+str(report['id']),headers=h('customer'))
    assert result.status_code==409 and 'must not return' not in result.text

"""Business read projection and fictional demo safety acceptance."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from api import state
from api.app import app
from api.geo_view import project_batch, safe_observation
from api.ratelimit import limiter
from scripts.portal_demo_data import seed_demo, batch

AUTH_KEYS = 'DEMO-GEO:geo-view:CLIENT_VIEWER,DEMO-GEO:geo-admin:DISTRIBUTOR_ADMIN,OTHER:geo-other:DISTRIBUTOR_ADMIN,HQ:geo-hq:HQ_MANAGEMENT'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB', str(tmp_path/'audit.db'))
    monkeypatch.delenv('GEO_DISTRIBUTOR_DEMO_ONLY', raising=False)
    monkeypatch.setattr(limiter, 'rate_per_min', 10000)
    monkeypatch.setattr(limiter, 'burst', 10000)
    asyncio.run(seed_demo(tmp_path/'portal-demo'))
    state._measurement_results.clear()
    with TestClient(app) as c:
        yield c


def h(key='view'):
    return {'X-API-Key': 'geo-'+key}


def get(c, pid='DEMO-PRJ-1', key='view'):
    return c.get('/projects/'+pid+'/geo', headers=h(key))


def test_read_visibility_empty_zero_partial_and_persistence(client):
    assert get(client).status_code == 200
    b = get(client).json()['batches']
    assert b[0]['metrics']['mention_rate'] == 25
    assert b[1]['comparison']['delta_pp']['mention_rate'] == 50
    assert b[1]['comparison']['comparable'] is True
    second = get(client, 'DEMO-PRJ-2').json()['batches']
    assert second[0]['metrics']['mention_rate'] == 0
    assert all(v is None for v in second[1]['metrics'].values())
    assert second[1]['observations'][0]['brand_mentioned'] is None
    assert second[1]['observations'][1]['recommendation_level'] is None
    assert get(client, 'DEMO-PRJ-3').json()['batches'] == []
    # A newer process cache must not hide persisted history.
    state._measurement_results['DEMO-PRJ-1'] = [batch(ident='CACHE-ONLY')]
    assert len(get(client).json()['batches']) == 2
    state.init_repositories(state.active_db_path)
    state._measurement_results.clear()
    assert len(get(client).json()['batches']) == 2


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(observation_count=9),
    lambda r: r['metrics'].update(query_count=9),
    lambda r: r['observations'][1].update(observation_id=r['observations'][0]['observation_id']),
    lambda r: r['observations'][0].update(status='failed'),
    lambda r: r['observations'][0].update(validation_status='SUSPICIOUS'),
    lambda r: r['observations'][0].update(timestamp='unknown'),
    lambda r: r.update(collected_at='2026-10-01T09:00:00'),
    lambda r: r.update(observations=[]),
])
def test_invalid_batches_never_become_zero(mutate):
    r = batch(); mutate(r)
    p = project_batch(r)
    assert all(v is None for v in p['metrics'].values())


@pytest.mark.parametrize('field,metric,value', [
    ('brand_status','mention_rate','UNKNOWN'),
    ('recommendation_level','recommendation_rate',-1),
    ('citations_status','citation_rate','unavailable'),
    ('citations_status','citation_rate','partial'),
])
def test_individual_metric_unknown_is_not_zero(field, metric, value):
    r = batch(); r['observations'][0][field] = value
    p = project_batch(r)
    assert p['metrics'][metric] is None
    assert p['metrics']['recommendation_rate' if metric != 'recommendation_rate' else 'mention_rate'] == 25


def test_wrong_summary_and_nan_hidden():
    r = batch(); r['metrics']['mention_rate'] = 99
    r['metrics']['recommendation_rate'] = float('nan')
    p = project_batch(r)
    assert p['metrics']['mention_rate'] is None
    assert p['metrics']['recommendation_rate'] is None
    assert 'query_coverage' not in p['metrics']


@pytest.mark.parametrize('change', ['brand','market','language','method_version','missing','sampling','prompt','engine'])
def test_comparison_requires_identical_explicit_scope(client, change):
    r = batch(ident='DEMO-NEW',day=18,mentions=3)
    if change == 'missing':
        r.pop('comparison_context')
    elif change == 'sampling':
        # Same prompt/platform set, different repetition counts.
        r['observations'] *= 2
        for i,o in enumerate(deepcopy(r['observations'])):
            o['observation_id'] = f'REPEAT-{i}'
            r['observations'][i] = o
        r['observation_count'] = r['metrics']['query_count'] = 8
    elif change in ('prompt','engine'):
        r['observations'][0]['prompt_text' if change=='prompt' else 'engine'] = 'changed'
    else:
        r['comparison_context'][change] = 'changed'
    asyncio.run(state.measurement_repo.upsert(r))
    b = get(client).json()['batches'][-1]
    assert b['comparison']['comparable'] is False
    assert all(v is None for v in b['comparison']['delta_pp'].values())


def test_permissions_and_old_raw_route(client):
    assert get(client,key='other').status_code == 404
    assert client.get('/projects/DEMO-PRJ-1/geo').status_code == 401
    assert client.get('/projects/DEMO-PRJ-1/geo?tenant_id=DEMO-GEO',headers=h('other')).status_code == 403
    assert client.get('/measurements/DEMO-PRJ-1',headers=h()).status_code == 403
    assert client.post('/measurements',headers=h('admin'),json={}).status_code == 403
    assert client.post('/clients',headers=h(),json={'name':'no'}).status_code == 403
    assert client.post('/ui/demo-session').status_code == 404


def test_white_list_no_raw_nested_objects(client):
    r = batch(ident='DEMO-SENSITIVE',day=18)
    o = r['observations'][0]
    o.update(answer_raw='SECRET-RAW',answer_clean='SECRET-CLEAN',raw_metadata={'key':'SECRET-KEY'})
    o['competitors'][0]['internal'] = 'SECRET-COMPETITOR'
    o['citations'].append({'url':'javascript:alert(1)','title':'UNSAFE-LINK'})
    o['citations'][0]['debug'] = 'SECRET-DEBUG'
    o['client_safe_excerpt'] = 'UNPUBLISHED'
    o['is_client_safe'] = False
    asyncio.run(state.measurement_repo.upsert(r))
    for route,headers in [('/projects/DEMO-PRJ-1/geo',h()),('/clients/DEMO-CLI-1/portal',{**h(),'X-Client-ID':'DEMO-CLI-1'})]:
        out = client.get(route,headers=headers)
        assert out.status_code == 200, out.text
        assert not any(word in out.text for word in ['SECRET-','javascript:','UNPUBLISHED','UNSAFE-LINK','query_coverage','answer_raw','raw_metadata'])


def test_report_strict_link_safety_and_no_history_write(client):
    report = client.get('/reports/DEMO-RPT-2',headers=h()).json()
    assert report['data_quality']['status'] == 'verified'
    assert report['geo_snapshot']['measurement_id'] == 'DEMO-MSR-2'
    repo = state.report_service._repository
    original = asyncio.run(repo.get('DEMO-RPT-2', 'DEMO-GEO'))
    assert 'data_quality' not in original
    r = deepcopy(original);r.update(report_id='DEMO-RPT-LEGACY',scope_version=4);r.pop('measurement_id')
    asyncio.run(repo.upsert(r))
    assert client.get('/reports/DEMO-RPT-LEGACY',headers=h()).json()['data_quality']['status'] == 'legacy_unverified'
    r.update(report_id='DEMO-RPT-UNSAFE',scope_version=5,is_client_safe=False)
    asyncio.run(repo.upsert(r))
    assert client.get('/reports/DEMO-RPT-UNSAFE',headers=h()).status_code == 404
    assert 'DEMO-RPT-UNSAFE' not in client.get('/reports?project_id=DEMO-PRJ-1',headers=h()).text
    assert 'DEMO-RPT-UNSAFE' not in client.get('/clients/DEMO-CLI-1/portal',headers={**h(),'X-Client-ID':'DEMO-CLI-1'}).text
    r = deepcopy(original);r['measurement_id']='DEMO-MSR-ZERO';asyncio.run(repo.upsert(r))
    assert client.get('/reports/DEMO-RPT-2',headers=h()).json()['data_quality']['status'] == 'legacy_unverified'


def test_seed_idempotency_and_refusal(client,tmp_path):
    path=Path(state.active_db_path).parent
    before=client.get('/clients',headers=h()).json()
    asyncio.run(seed_demo(path))
    assert client.get('/clients',headers=h()).json()==before
    with pytest.raises(RuntimeError):
        asyncio.run(seed_demo(tmp_path/'real-data'))
    from geo_distributor.models.client import Client
    asyncio.run(state.client_repo.create(Client('REAL-1','REAL','Preserve')))
    with pytest.raises(RuntimeError):
        asyncio.run(seed_demo(path))
    assert asyncio.run(state.client_repo.find_by_id('REAL-1',tenant_id='REAL')).name=='Preserve'


def test_demo_login_and_global_read_only(client,monkeypatch):
    monkeypatch.setenv('GEO_DISTRIBUTOR_DEMO_ONLY','1')
    monkeypatch.setenv('GEO_DISTRIBUTOR_DEMO_KEY','geo-view')
    from api import ui
    monkeypatch.setattr(ui,'SESSION_COOKIE','ggs_demo_sid')
    r=client.post('/ui/demo-session')
    assert r.status_code==200 and r.json()['is_demo'] is True
    assert 'ggs_demo_sid=' in r.headers['set-cookie']
    assert 'geo-view' not in r.text
    assert client.get('/ui/proxy/projects/DEMO-PRJ-1/geo').status_code==200
    assert client.post('/ui/proxy/clients',json={'name':'write'}).status_code==403
    assert client.post('/clients',headers=h('admin'),json={'name':'write'}).status_code==403
    assert client.post('/ui/session',json={'api_key':'geo-admin'}).status_code==401


@pytest.mark.parametrize('value',[None,[],{},'', '   '])
def test_audit_b1_invalid_context_has_no_signature(value):
    r=batch();r['comparison_context']={k:value for k in r['comparison_context']}
    assert project_batch(r)['_signature'] is None


def test_audit_b1_full_context_not_truncated_for_signature():
    a=batch();b=deepcopy(a)
    a['comparison_context']['market']='a'*200+'US'
    b['comparison_context']['market']='a'*200+'UK'
    assert project_batch(a)['_signature'] != project_batch(b)['_signature']


def test_audit_b2_mixed_brands_not_verified():
    r=batch();r['observations'][0]['brand']='OTHER BRAND'
    p=project_batch(r)
    assert all(v is None for v in p['metrics'].values())
    assert p['_signature'] is None


@pytest.mark.parametrize('mention,recommendation',[(99,1),('99%','1%'),(None,75),(True,75),('NaN%',75)])
def test_audit_b3_bad_report_rates_not_verified(client,mention,recommendation):
    repo=state.report_service._repository
    r=asyncio.run(repo.get('DEMO-RPT-2','DEMO-GEO'))
    r['content']['visibility_summary'].update(mention_rate=mention,recommendation_rate=recommendation)
    asyncio.run(repo.upsert(r))
    assert client.get('/reports/DEMO-RPT-2',headers=h()).json()['data_quality']['status']=='legacy_unverified'


def test_audit_b3_core_percentage_strings_supported(client):
    repo=state.report_service._repository
    r=asyncio.run(repo.get('DEMO-RPT-2','DEMO-GEO'))
    r['content']['visibility_summary'].update(mention_rate='75.0%',recommendation_rate='75.0%')
    asyncio.run(repo.upsert(r))
    assert client.get('/reports/DEMO-RPT-2',headers=h()).json()['data_quality']['status']=='verified'


def test_audit_b4_real_collection_path_can_display_metrics(client,tmp_path,monkeypatch):
    import json
    import geo_distributor.config as config
    import dataclasses
    from geo_distributor.compatibility.base import PlatformObservation
    directory=tmp_path/'sprint4-lab'/'cases'/'fixture'/'baseline';directory.mkdir(parents=True)
    observations=[]
    for i,o in enumerate(batch()['observations']):
        values={f.name:None for f in dataclasses.fields(PlatformObservation)}
        values.update(prompt_id=i,answer_raw='PRIVATE',answer_clean='PRIVATE',answer_char_count=7,
                      extraction_method='fixture',first_mention_position=None,recommendation_rank=None,
                      recommendation_evidence='',raw_metadata={})
        values.update({k:v for k,v in o.items() if k in values})
        observations.append(values)
    (directory/'observations.json').write_text(json.dumps(observations),encoding='utf-8')
    monkeypatch.setattr(config,'get_project_root',lambda:str(tmp_path))
    r=client.post('/measurements',headers=h('hq'),json={'project_id':'DEMO-PRJ-3','tenant_id':'DEMO-GEO','case_id':'fixture','adapter':'opengeo'})
    assert r.status_code==201,r.text
    assert r.json()['collected_at'].endswith('+00:00')
    saved=get(client,'DEMO-PRJ-3').json()['batches'][0]
    assert saved['metrics']['mention_rate']==25
    assert saved['comparison']['comparable'] is False # No inferred market/method scope.
    # New automatically delivered reports explicitly associate with this batch.
    delivered=client.post('/projects/DEMO-PRJ-3/deliver?tenant_id=DEMO-GEO',headers=h('hq'),json={'scope_version':1})
    assert delivered.status_code==200,delivered.text
    rid=delivered.json()['report_id']
    report=client.get('/reports/'+rid,headers=h()).json()
    assert report['data_quality']['status']=='verified'
    before=asyncio.run(state.report_service._repository.get(rid,'DEMO-GEO'))
    client.post('/projects/DEMO-PRJ-3/deliver?tenant_id=DEMO-GEO',headers=h('hq'),json={'scope_version':1})
    assert asyncio.run(state.report_service._repository.get(rid,'DEMO-GEO'))==before

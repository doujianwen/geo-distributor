"""Independent acceptance regressions for audited HQ edge cases."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tests.test_hq_workspace import client, h, op_body
from api import state


def test_hq_direct_conversion_replay_does_not_duplicate_request(client):
    assign = client.post('/leads/DEMO-HQ-LEAD-1/assign', headers=h(), json={
        'tenant_id': 'HQ-INTAKE', 'create_client': True, 'client_name': '独立审计直管客户'})
    assert assign.status_code == 200
    url = '/leads/DEMO-HQ-LEAD-1/convert'
    body = {'business_question': '核实海外品牌回答表现'}
    first = client.post(url, headers=h(), json=body)
    assert first.status_code == 200, first.text
    second = client.post(url, headers=h(), json=body)
    assert second.status_code == 200, second.text
    assert second.json()['request_id'] == first.json()['request_id']
    requests = asyncio.run(state.request_repo.find_by_tenant('HQ-INTAKE'))
    assert len(requests) == 1
    assert not asyncio.run(state.project_repo.find_by_tenant('HQ-INTAKE'))


def test_old_and_new_lifecycle_share_one_version_boundary(client):
    body = op_body('complete')
    first = client.post('/hq/projects/DEMO-PRJ-1/operation', headers=h(ik='modern'), json=body)
    assert first.status_code == 200
    old = client.post('/projects/DEMO-PRJ-1/stage/complete', headers=h(ik='legacy'),
                      json={'expected_updated_at': body['expected_updated_at']})
    assert old.status_code == 409
    events = client.get('/hq/workspace', headers=h()).json()['events']
    assert sum(e['source'] == 'project' for e in events) == 1


def test_hq_direct_clarification_can_be_supplemented_without_channel_impersonation(client):
    assert client.post('/leads/DEMO-HQ-LEAD-1/assign', headers=h(), json={
        'tenant_id': 'HQ-INTAKE', 'create_client': True}).status_code == 200
    converted = client.post('/leads/DEMO-HQ-LEAD-1/convert', headers=h(),
                            json={'business_question': '核实海外品牌回答表现'})
    assert converted.status_code == 200
    rid = converted.json()['request_id']
    r = client.get('/requests/' + rid, headers=h()).json()
    clarify = client.post('/requests/' + rid + '/clarification', headers=h(),
        json={'revision': r['workflow']['revision'], 'note': '需核实服务语言'})
    assert clarify.status_code == 200
    supplement = client.post('/requests/' + rid + '/supplement', headers=h(),
        json={'revision': clarify.json()['workflow']['revision'], 'note': '总部线下核实：英语'})
    assert supplement.status_code == 200, supplement.text
    ordinary = client.get('/requests/DEMO-REQ-INTAKE', headers=h()).json()
    ordinary_clarify = client.post('/requests/DEMO-REQ-INTAKE/clarification', headers=h(),
        json={'revision': ordinary['workflow']['revision'], 'note': '需渠道核实'})
    assert ordinary_clarify.status_code == 200
    assert client.post('/requests/DEMO-REQ-INTAKE/supplement', headers=h(),
        json={'revision': ordinary_clarify.json()['workflow']['revision'], 'note': '不应代渠道填答'}).status_code == 403


def test_operation_same_key_concurrent_replays_one_persistent_event(client):
    from api import auth, hq_service
    ctx = auth.verify_api_key('hq-admin')
    body = op_body('complete')
    with ThreadPoolExecutor(4) as pool:
        rows = list(pool.map(lambda _: hq_service.project_operation(
            'DEMO-PRJ-1', body, 'independent-same-key', ctx), range(4)))
    assert sum(r.get('deduplicated', False) for r in rows) == 3
    assert len(asyncio.run(hq_service.all_rows('hq_operations'))) == 1


def test_disabled_client_publication_is_valid_but_not_currently_accessible(client):
    customer = asyncio.run(state.client_repo.find_by_id('DEMO-CLI-1', tenant_id='DEMO-GEO'))
    customer.is_active = False
    asyncio.run(state.client_repo.update(customer))
    data = client.get('/hq/workspace', headers=h()).json()
    reports = [r for r in data['reports'] if r['report_id'] in ('DEMO-RPT-1', 'DEMO-RPT-2')]
    assert len(reports) == 2
    assert all(r['status'] == 'access_inactive' for r in reports)
    assert data['counts']['invalid'] == 0
    assert client.get('/customer/workspace', headers=h('customer')).status_code == 403


def test_every_legacy_lifecycle_rejects_all_manual_reference_types(client):
    for route in ('start', 'stage', 'stage/complete'):
        for field in ('finding_ids', 'measurement_ids', 'report_ids'):
            response = client.post('/projects/DEMO-PRJ-1/' + route,
                headers=h(ik=route.replace('/', '-') + '-' + field),
                json={'expected_updated_at': op_body()['expected_updated_at'], field: ['OTHER-PROJECT']})
            assert response.status_code == 422
    from api import hq_service
    assert not asyncio.run(hq_service.all_rows('hq_operations'))

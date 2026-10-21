"""Isolated native parity and adversarial scope tests; never initialize history."""
import importlib
import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from api import growth_core
from scripts.growth_workspace_setup import create_core


@pytest.fixture
def world(tmp_path):
    path = create_core(tmp_path / 'operator.db')
    conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    core = growth_core.contract()
    adapter = importlib.import_module(core.__package__ + '.operator_contract')
    with core.atomic(conn) as tx:
        core.bind(tx, project_key='a/p1', tenant='a', client='c1', name='A', domain='https://a.example')
        core.bind(tx, project_key='b/p2', tenant='b', client='c2', name='B', domain='https://b.example')
    a = core.binding(conn, 'a/p1', 'a', 'c1'); b = core.binding(conn, 'b/p2', 'b', 'c2')
    yield conn, core, adapter, a, b, path
    conn.close()


def write(w, path, body=None, method='POST', binding=None, **overrides):
    conn, core, adapter, a, b, _ = w
    a = binding or a
    version = conn.execute('SELECT revision FROM workspace_sites WHERE site_id=?', (a['site_id'],)).fetchone()[0]
    args = dict(revision=version, key=uuid4().hex, subject='person-1', authorize=lambda _: None)
    args.update(overrides)
    return adapter.operate(conn, a, method, path, body or {}, {}, **args)


def read(w, path, query=None):
    return w[2].dispatch(w[0], w[3], 'GET', path, query=query)


def test_native_operator_complete_manual_workflow(world):
    conn, core, adapter, a, b, _ = world
    p = a['product_id']
    persona = write(world, 'personas', {'name': '采购经理'})['result']
    scenario = write(world, 'scenarios', {'name': '评估方案', 'stage': 'MOFU'})['result']
    question = write(world, 'questions', {'text': '哪种工具好？', 'persona_id': persona['id'], 'scenario_id': scenario['id'],
                  'commercial': 5, 'citation': 5, 'brand': 4, 'competition': 2, 'intent_class': '推荐'})['result']
    assert (question['total'], question['priority']) == adapter.database.compute_score(5, 5, 4, 2)
    assert question['persona_id'] == persona['id']
    cluster = write(world, 'clusters', {'name': '工具选择'})['result']
    write(world, f"questions/{question['id']}/cluster/{cluster['id']}")
    brief = write(world, f"clusters/{cluster['id']}/generate-brief")['result']
    assert '哪种工具好' in brief['body'] and brief['status'] == 'idea'
    assert write(world, f"briefs/{brief['id']}/adopt", {'target_status': 'writing'})['result']['status'] == 'writing'
    write(world, 'content-gaps', {'slug': 'comparison', 'title': '工具对比', 'status': 'planned'})
    write(world, 'entities', {'name': 'A', 'type': 'brand'})
    monitor = write(world, 'monitors', {'query_text': '哪种工具好？', 'source_type': 'question', 'source_id': question['id']})['result']
    result = write(world, f'products/{p}/citations/batch', {'query_date': '2026-10-20', 'items': [
        {'monitor_id': monitor['id'], 'engine': 'ChatGPT', 'query_text': '哪种工具好？', 'result': 'not_found'}]})
    assert result['result']['created'] == 1
    assert read(world, f'products/{p}/dashboard')['questions_total'] == 1
    assert read(world, f'products/{p}/trends')['summary']['total_queries'] == 1
    assert read(world, f'products/{p}/citations/report')['by_engine'][0]['total'] == 1
    assert read(world, 'prompts') and read(world, 'manual')['markdown']
    assert read(world, f"sites/{a['site_id']}/growth-workbench") is not None
    assert read(world, f"sites/{a['site_id']}/competitor-gaps") is not None
    assert len(read(world, 'products')) == 1


def test_bulk_classification_preview_manual_apply(world):
    p = world[3]['product_id']
    write(world, f'products/{p}/questions/bulk', {'items': [{'text': '如何选择工具'}, {'text': '其他问题'}]})
    write(world, f'products/{p}/keywords', {'name': '选择', 'pattern': '选择', 'type': 'keyword', 'intent_class': '推荐'})
    preview = write(world, f'products/{p}/questions/classify-by-keywords')['result']
    assert preview['classified'] == 1
    assert not read(world, f'products/{p}/questions')[1]['intent_class']
    # Native ClassificationDraft requires confidence and matched_keywords; use full native draft.
    result = write(world, f'products/{p}/questions/classify-by-keywords/apply', {'drafts': preview['drafts']})
    assert result['result']['updated'] == 1


def test_classification_draft_persisted_subset_identity_and_expiry(world):
    p = world[3]['product_id']
    write(world, 'questions', {'text': '选择工具'})
    write(world, f'products/{p}/keywords', {'name': '选择', 'pattern': '选择', 'type': 'keyword', 'intent_class': '推荐'})
    preview = write(world, f'products/{p}/questions/classify-by-keywords')['result']
    forged = [dict(preview['drafts'][0], proposed_intent='forged')]
    with pytest.raises(world[1].ContractError): write(world, f'products/{p}/questions/classify-by-keywords/apply', {'drafts': forged})
    with pytest.raises(world[1].ContractError): write(world, f'products/{p}/questions/classify-by-keywords/apply', {'drafts': preview['drafts']}, subject='other-person')
    # Preview is durable, not an in-process cache.
    row = world[0].execute("SELECT result FROM workspace_events WHERE operation LIKE '%classify-by-keywords' ORDER BY id DESC LIMIT 1").fetchone()
    assert json.loads(row['result'])['result'] == preview
    write(world, 'entities', {'name': 'intervening edit'})
    with pytest.raises(world[1].ContractError): write(world, f'products/{p}/questions/classify-by-keywords/apply', {'drafts': preview['drafts']})


def test_independent_object_edits_and_stale_same_object(world):
    q1 = write(world, 'questions', {'text': 'one'})['result']['id']
    q2 = write(world, 'questions', {'text': 'two'})['result']['id']
    versions = world[2].object_versions(world[0], world[3])
    site_revision = world[0].execute('SELECT revision FROM workspace_sites WHERE site_id=?', (world[3]['site_id'],)).fetchone()[0]
    write(world, f'questions/{q1}', {'text': 'edited one'}, method='PUT', revision=site_revision, object_version=versions[f'questions/{q1}'])
    # Same global revision, a distinct unchanged object: accepted.
    write(world, f'questions/{q2}', {'text': 'edited two'}, method='PUT', revision=site_revision, object_version=versions[f'questions/{q2}'])
    with pytest.raises(world[1].ContractError) as exc:
        write(world, f'questions/{q1}', {'text': 'lost update'}, method='PUT', revision=site_revision, object_version=versions[f'questions/{q1}'])
    assert exc.value.status == 409
    with pytest.raises(world[1].ContractError) as exc:
        write(world, f'questions/{q1}', {'text': 'no version'}, method='PUT')
    assert exc.value.status == 428


def test_scope_product_and_nested_references(world):
    conn, core, adapter, a, b, _ = world
    foreign = write(world, 'personas', {'name': 'secret'}, binding=b)['result']['id']
    with pytest.raises(core.ContractError) as e:
        write(world, 'questions', {'text': 'bad', 'persona_id': foreign})
    assert e.value.status == 404
    for path in [f"products/{b['product_id']}/questions", f"sites/{b['site_id']}/growth-workbench"]:
        with pytest.raises(core.ContractError): read(world, path)
    with pytest.raises(core.ContractError):
        write(world, f"products/{a['product_id']}/citations/batch", {'query_date': '2026-10-20', 'items': [{'engine': 'x', 'monitor_id': 999, 'query_text': 'secret', 'result': 'not_found'}]})
    assert conn.execute('SELECT count(*) FROM questions').fetchone()[0] == 0


def test_atomic_replay_conflict_revocation_and_failure(world):
    conn, core, adapter, a, b, path = world
    key = uuid4().hex
    result = write(world, 'questions', {'text': 'one'}, key=key, revision=1)
    assert write(world, 'questions', {'text': 'one'}, key=key, revision=1) == result
    with pytest.raises(core.ContractError): write(world, 'questions', {'text': 'two'}, key=key, revision=1)
    with pytest.raises(core.ContractError): write(world, 'questions', {'text': 'stale'}, revision=1)
    def revoked(_): raise PermissionError('revoked')
    with pytest.raises(PermissionError): write(world, 'questions', {'text': 'one'}, key=key, revision=1, authorize=revoked)
    original = adapter.dispatch
    def broken(tx, *args, **kwargs):
        original(tx, *args, **kwargs)
        raise RuntimeError('fail after native inner commit/close')
    adapter.dispatch = broken
    try:
        with pytest.raises(RuntimeError): write(world, 'questions', {'text': 'rolled back'})
    finally: adapter.dispatch = original
    assert conn.execute('SELECT count(*) FROM questions').fetchone()[0] == 1
    assert conn.execute('SELECT revision FROM workspace_sites WHERE site_id=?', (a['site_id'],)).fetchone()[0] == 2


@pytest.mark.parametrize('path', ['seed/example', 'reset', '../products', 'products%2f1'])
def test_maintenance_and_path_escape_rejected(world, path):
    with pytest.raises(world[1].ContractError): write(world, path)


def test_external_calls_delete_and_unscoped_prompts_fail_closed(world):
    conn, core, adapter, a, b, _ = world
    conn.execute("INSERT INTO prompts(name,content) VALUES('other customer secret','NEVER SHOW')"); conn.commit()
    assert 'NEVER SHOW' not in json.dumps(read(world, 'prompts'))
    for action in ('ai-score', 'ai-cluster', 'ai-brief', 'realtime'):
        with pytest.raises(core.ContractError) as e: write(world, f"products/{a['product_id']}/{action}")
        assert e.value.status == 503
    with pytest.raises(core.ContractError) as e: write(world, 'questions/1', method='DELETE')
    assert e.value.status == 409


def test_pinned_source_changed_blocks_loading(world, monkeypatch):
    adapter = world[2]
    monkeypatch.setitem(adapter.SOURCE_HASHES, 'main.py', '0' * 64)
    with pytest.raises(world[1].ContractError) as exc: read(world, 'products')
    assert exc.value.status == 503


def test_legacy_corrupt_cross_resource_links_are_quarantined(world):
    conn, core, adapter, a, b, _ = world
    q = write(world, 'questions', {'text': 'A only'})['result']['id']
    cl = write(world, 'clusters', {'name': 'B secret'}, binding=b)['result']['id']
    conn.execute('INSERT INTO question_cluster VALUES(?,?)', (q, cl)); conn.commit()
    with pytest.raises(core.ContractError) as exc: read(world, f"products/{a['product_id']}/citations/report")
    assert exc.value.status == 409


def test_two_concurrent_approvals_use_one_version(world):
    conn, core, adapter, a, b, path = world
    def task(index):
        c = sqlite3.connect(path, timeout=10); c.row_factory = sqlite3.Row
        try:
            return adapter.operate(c, a, 'POST', 'questions', {'text': f'concurrent {index}'}, {}, revision=1,
                                   key=str(index), subject='worker', authorize=lambda _: None)
        except core.ContractError as exc: return exc.status
        finally: c.close()
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(task, [1, 2]))
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert results.count(409) == 1
    assert conn.execute('SELECT count(*) FROM questions').fetchone()[0] == 1


def test_http_explicit_grant_scope_revocation_and_version(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import auth, ui, workspace_access
    from api.app import app
    from scripts.portal_demo_data import seed_demo
    from scripts.customer_demo_data import seed_customer_demo
    monkeypatch.setenv('GEO_DISTRIBUTOR_API_KEYS', 'DEMO-GEO:admin:HQ_MANAGEMENT,DEMO-GEO:ops:HQ_TECHNICAL,DEMO-GEO:viewer:CLIENT_VIEWER,OTHER:cross:DISTRIBUTOR_ADMIN')
    monkeypatch.setenv('GEO_DISTRIBUTOR_ENV', 'production')
    monkeypatch.setenv('GEO_DISTRIBUTOR_AUDIT_DB', str(tmp_path / 'audit.db'))
    monkeypatch.delenv('GEO_DISTRIBUTOR_DEMO_ONLY', raising=False)
    monkeypatch.setattr(auth, 'REGISTRY_FILE', tmp_path / 'no-keys.json')
    from api.ratelimit import limiter
    for limiter_ in (limiter, ui._login_limiter):
        monkeypatch.setattr(limiter_, 'rate_per_min', 100000); monkeypatch.setattr(limiter_, 'burst', 100000)
    asyncio.run(seed_demo(tmp_path / 'portal-demo'))
    asyncio.run(seed_customer_demo())
    monkeypatch.setenv('GEO_GROWTH_WORKSPACE_DB', str(create_core(tmp_path / 'http-growth.db')))
    prefix = '/growth/projects/DEMO-PRJ-1'
    def headers(key='admin', **extra): return {'X-API-Key': key, **extra}
    with TestClient(app) as client:
        r = client.post(prefix + '/bind', headers=headers(**{'Idempotency-Key': uuid4().hex}), json={'revision': 0, 'payload': {'name': 'A', 'domain': 'https://a.example'}})
        assert r.status_code == 200, r.text
        assert client.get(prefix + '/operator/context', headers=headers()).status_code == 403
        assert client.get(prefix + '/operator/context', headers=headers('ops')).status_code == 404
        subject = auth.verify_api_key('ops').user_id
        r = client.post(prefix + '/access', headers=headers(), json={'subject': subject, 'capabilities': ['operate']})
        assert r.status_code == 200, r.text
        context = client.get(prefix + '/operator/context', headers=headers('ops'))
        assert context.status_code == 200, context.text
        path = prefix + '/operator/api/questions'
        assert client.post(path, headers=headers('ops'), json={'text': 'no-version'}).status_code == 428
        h = headers('ops', **{'If-Match': str(context.json()['revision']), 'Idempotency-Key': 'http-key'})
        r = client.post(path, headers=h, json={'text': 'owned full question', 'commercial': 4, 'citation': 5, 'brand': 4, 'competition': 2})
        assert r.status_code == 200 and r.headers.get('X-Workspace-Revision'), r.text
        assert client.post(path, headers=h, json={'text': 'owned full question', 'commercial': 4, 'citation': 5, 'brand': 4, 'competition': 2}).json() == r.json()
        assert client.get(prefix + '/operator/api/products/999/questions', headers=headers('ops')).status_code == 404
        assert client.get(prefix + '/operator/context', headers=headers('cross')).status_code in {403, 404}
        assert client.get(prefix + '/operator/context', headers=headers('viewer')).status_code == 403
        r = client.post(prefix + '/access', headers=headers(), json={'subject': subject, 'capabilities': []})
        assert r.status_code == 200
        assert client.post(path, headers=h, json={'text': 'owned full question', 'commercial': 4, 'citation': 5, 'brand': 4, 'competition': 2}).status_code in {403, 404}

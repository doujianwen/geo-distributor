import sqlite3
import pytest
from api.historical_adoption import adopt, allow_portal_connection, fingerprints


@pytest.fixture
def databases(tmp_path):
    core, business = tmp_path/'geo_intent.db', tmp_path/'commercial.db'
    with sqlite3.connect(core) as c:
        c.executescript("CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT);CREATE TABLE sites(id INTEGER PRIMARY KEY,name TEXT,domain TEXT,source_product_id INTEGER REFERENCES products(id));INSERT INTO products VALUES(2,'Existing');INSERT INTO sites VALUES(1,'Existing','example.test',2);")
    with sqlite3.connect(business) as c:
        for t in ['clients','projects']:
            c.execute('CREATE TABLE '+t+'(id TEXT PRIMARY KEY,tenant_id TEXT,payload TEXT,updated_at TEXT)')
    mapping=[dict(tenant='HQ-SELF',client_id='HQ-C1',project_id='HQ-P1',name='Existing',site_id=1,product_id=2,domain='example.test')]
    return core,business,mapping,tmp_path/'backup'


def test_adoption_preserves_rows_and_fences_old_writers(databases):
    core,business,mapping,backup=databases
    report=adopt(core,business,mapping,backup)
    assert report['historical_rows_unchanged']
    with sqlite3.connect(core) as c:
        assert c.execute('SELECT product_id FROM workspace_bindings').fetchone()==(2,)
        with pytest.raises(sqlite3.OperationalError,match='geo_portal_write_allowed'):
            c.execute("UPDATE products SET name='Unprotected'")
        c.rollback()
        allow_portal_connection(c)
        c.execute("UPDATE products SET name='Authorized command'")
    with sqlite3.connect(business) as c:
        assert c.execute('SELECT count(*) FROM projects').fetchone()==(1,)
    with sqlite3.connect(backup/'core-before.db') as c:
        assert c.execute('SELECT name FROM products').fetchone()==('Existing',)


def test_bad_mapping_rolls_back_ownership_and_commercial_rows(databases):
    core,business,mapping,backup=databases
    mapping.append({**mapping[0],'project_id':'HQ-P2','client_id':'HQ-C2','site_id':999})
    with pytest.raises(ValueError,match='identity changed'):
        adopt(core,business,mapping,backup)
    with sqlite3.connect(core) as c:
        assert c.execute('SELECT count(*) FROM workspace_bindings').fetchone()==(0,)
        assert fingerprints(c,['products'])['products']['rows']==1
    with sqlite3.connect(business) as c:
        assert c.execute('SELECT count(*) FROM projects').fetchone()==(0,)


def test_repeated_adoption_does_not_overwrite_existing(databases):
    core,business,mapping,backup=databases
    adopt(core,business,mapping,backup)
    with pytest.raises(ValueError,match='already exist'):
        adopt(core,business,mapping,backup.parent/'second-backup')
    with sqlite3.connect(core) as c:
        assert c.execute('SELECT count(*) FROM workspace_bindings').fetchone()==(1,)


def test_schema_only_setup_does_not_copy_live_deployment_fence(databases,monkeypatch):
    from scripts import growth_workspace_setup as setup
    core,business,mapping,backup=databases
    adopt(core,business,mapping,backup)
    monkeypatch.setattr(setup,'DEFAULT_ROOT',core.parent)
    path=setup.create_core(core.parent/'new-empty.db')
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT count(*) FROM products').fetchone()==(0,)
        assert c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'portal_fence_%'").fetchone()==(0,)
        c.execute("INSERT INTO products(id,name) VALUES(1,'New isolated product')")
    with sqlite3.connect(core) as c:
        with pytest.raises(sqlite3.OperationalError,match='geo_portal_write_allowed'):
            c.execute("UPDATE products SET name='Still protected'")

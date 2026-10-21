"""Explicit owner-approved adoption; preserve historical rows and fence legacy writers.

The fence prevents accidental writes from old SQLite connections. It is not a
security boundary against an administrator who can edit the database schema.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def allow_portal_connection(conn):
    conn.create_function('geo_portal_write_allowed', 0, lambda: 1)


def tables(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def fingerprints(conn, names=None):
    result = {}
    for name in names if names is not None else tables(conn):
        rows = sorted(json.dumps(list(r), ensure_ascii=True, default=str) for r in conn.execute('SELECT * FROM ' + quote(name)))
        result[name] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    return result


def install_fence(conn, names=None):
    allow_portal_connection(conn)
    for name in names if names is not None else tables(conn):
        for operation in ('INSERT', 'UPDATE', 'DELETE'):
            trigger = 'portal_fence_' + hashlib.sha256((name + operation).encode()).hexdigest()[:24]
            conn.execute('CREATE TRIGGER IF NOT EXISTS ' + quote(trigger) + ' BEFORE ' + operation + ' ON ' + quote(name) +
                         " BEGIN SELECT CASE WHEN geo_portal_write_allowed() <> 1 THEN RAISE(ABORT,'Use authorized portal commands') END; END")


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError('Backup destination must be new')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as origin, sqlite3.connect(destination) as copy:
        origin.backup(copy)


def adopt(core_path, commercial_path, mapping, backup_dir):
    """Caller provides approved exact IDs, tenant/client/project mapping, no auto-match."""
    from .growth_core import contract
    from . import workspace_access
    from geo_distributor.models.client import Client
    from geo_distributor.models.project import Project
    core_path, commercial_path = Path(core_path).resolve(), Path(commercial_path).resolve()
    if core_path == commercial_path or not core_path.is_file() or not commercial_path.is_file():
        raise ValueError('Explicit separate existing databases required')
    backup_dir = Path(backup_dir).resolve()
    backup(core_path, backup_dir / 'core-before.db')
    backup(commercial_path, backup_dir / 'commercial-before.db')
    conn = sqlite3.connect(core_path, timeout=15)
    conn.row_factory = sqlite3.Row
    allow_portal_connection(conn)
    before = fingerprints(conn)
    try:
        if list(conn.execute('PRAGMA foreign_key_check')):
            raise ValueError('Historical foreign key violations require governance')
        # Schema setup is additive; all ownership and business rows commit together.
        contract().initialize(conn)
        workspace_access.initialize(conn)
        conn.execute('CREATE TABLE IF NOT EXISTS historical_adoptions(id TEXT PRIMARY KEY, detail TEXT NOT NULL, created_at TEXT NOT NULL)')
        conn.execute('ATTACH DATABASE ? AS commercial', (str(commercial_path),))
        conn.execute('BEGIN IMMEDIATE')
        keys = set()
        for row in mapping:
            key = row['tenant'] + '/' + row['project_id']
            if key in keys or row['tenant'] != 'HQ-SELF':
                raise ValueError('Only explicitly approved HQ self-operated mapping is accepted')
            keys.add(key)
            site = conn.execute('SELECT * FROM sites WHERE id=? AND source_product_id=?', (row['site_id'], row['product_id'])).fetchone()
            if not site or site['domain'] != row['domain']:
                raise ValueError('Historical resource identity changed')
            if conn.execute('SELECT 1 FROM commercial.clients WHERE id=?', (row['client_id'],)).fetchone() or conn.execute('SELECT 1 FROM commercial.projects WHERE id=?', (row['project_id'],)).fetchone():
                raise ValueError('Commercial IDs already exist; inspect rather than overwrite')
            bound = contract().bind(conn, project_key=key, tenant=row['tenant'], client=row['client_id'], site_id=row['site_id'])
            if bound['product_id'] != row['product_id']:
                raise ValueError('Product changed')
            client = Client(row['client_id'], row['tenant'], row['name'], website='https://' + row['domain'], metadata={'ownership':'HQ_SELF_OPERATED','source':'historical_adoption'})
            # Historical self-operation is not a new customer request or fabricated scope approval.
            project = Project(row['project_id'], '', row['tenant'], row['client_id'], '')
            for table, ident, payload in [('clients',client.client_id,client.to_dict()),('projects',project.project_id,project.to_dict())]:
                conn.execute('INSERT INTO commercial.' + table + '(id,tenant_id,payload,updated_at) VALUES(?,?,?,?)', (ident,row['tenant'],json.dumps(payload,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        after = fingerprints(conn, before)
        if before != after:
            raise ValueError('Adoption altered historical business rows')
        detail = {'mapping':mapping,'before':before,'after':after,'historical_rows_unchanged':True,'authority':str(core_path),'legacy_write_fence':True}
        conn.execute('INSERT INTO historical_adoptions VALUES(?,?,?)', ('hq-self-20261020',json.dumps(detail,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        install_fence(conn)
        conn.commit()
        return detail
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

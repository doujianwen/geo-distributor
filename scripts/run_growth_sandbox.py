"""Fixed loopback interactive lab; random local credentials, isolated data, no real registry."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
directory=root/'data'/'growth-sandbox'
if directory.resolve()!=directory or directory.is_symlink():raise RuntimeError('Lab must be isolated')
directory.mkdir(parents=True,exist_ok=True)
if sys.stdout is None or sys.stderr is None:
    (root/'logs').mkdir(exist_ok=True)
    sys.stdout=sys.stderr=open(root/'logs'/'growth-sandbox.log','a',encoding='utf-8',buffering=1)

if __name__=='__main__':
    keyfile=directory/'credentials.local.json'
    roles={'management':'HQ_MANAGEMENT','operations':'HQ_TECHNICAL','channel':'DISTRIBUTOR_ADMIN','viewer':'END_CUSTOMER','editor':'END_CUSTOMER_EDITOR'}
    if keyfile.exists():keys=json.loads(keyfile.read_text())
    else:
        keys={r:secrets.token_urlsafe(40) for r in roles}
        keyfile.write_text(json.dumps(keys))
    os.environ.pop('GEO_DISTRIBUTOR_DEMO_ONLY',None)
    os.environ.update(GEO_DISTRIBUTOR_ENV='production',GEO_GROWTH_SANDBOX='1',
        GEO_DISTRIBUTOR_RATE_LIMIT='300',GEO_DISTRIBUTOR_RATE_BURST='100',
        GEO_DISTRIBUTOR_SESSION_COOKIE='ggs_growth_lab_sid',GEO_GROWTH_WORKSPACE_DB=str(directory/'growth.db'),
        GEO_DISTRIBUTOR_AUDIT_DB=str(directory/'audit.db'),
        GEO_DISTRIBUTOR_API_KEYS=','.join('DEMO-GEO:'+keys[r]+':'+role+(':DEMO-CLI-1' if role.startswith('END_CUSTOMER') else '') for r,role in roles.items()))
    for role,value in keys.items():os.environ['GEO_LAB_KEY_'+role.upper()]=value
    import api.auth
    api.auth.REGISTRY_FILE=directory/'disabled-registry.json'
    if api.auth.REGISTRY_FILE.exists():raise RuntimeError('Lab refuses real registry')
    from scripts.portal_demo_data import seed_demo
    from scripts.customer_demo_data import seed_customer_demo
    from scripts.hq_demo_data import seed_hq_demo
    asyncio.run(seed_demo(directory/'portal-demo'));asyncio.run(seed_customer_demo());asyncio.run(seed_hq_demo())
    from scripts.growth_sandbox_data import seed
    seed(directory/'growth.db',api.auth.verify_api_key(keys['editor']).user_id)
    # Explicit one-time fictional policy upgrade; never resurrect a revoked grant on restart.
    import sqlite3
    from api import workspace_access
    from types import SimpleNamespace
    policy=sqlite3.connect(directory/'growth.db')
    workspace_access.initialize(policy)
    policy.execute('CREATE TABLE IF NOT EXISTS operator_fixture_versions(version TEXT PRIMARY KEY)')
    if not policy.execute("SELECT 1 FROM operator_fixture_versions WHERE version='access-v22'").fetchone():
        manager=api.auth.verify_api_key(keys['management'])
        project=SimpleNamespace(tenant_id='DEMO-GEO',project_id='DEMO-PRJ-1')
        for role in ('management','operations','channel'):
            capabilities=['read','prepare','operate']
            if role=='management':capabilities+=['quality_review','report_publish']
            workspace_access.set_access(policy,manager,project,api.auth.verify_api_key(keys[role]).user_id,capabilities)
        policy.execute("INSERT INTO operator_fixture_versions VALUES('access-v22')");policy.commit()
    if not policy.execute("SELECT 1 FROM operator_fixture_versions WHERE version='resource-access-v22'").fetchone():
        manager=api.auth.verify_api_key(keys['management'])
        project=SimpleNamespace(tenant_id='DEMO-GEO',project_id='DEMO-PRJ-1')
        for row in policy.execute('SELECT DISTINCT subject FROM operator_project_access WHERE project_key=?',('DEMO-GEO/DEMO-PRJ-1',)).fetchall():
            selected=[r[0] for r in policy.execute('SELECT capability FROM operator_project_access WHERE project_key=? AND subject=? AND enabled=1',('DEMO-GEO/DEMO-PRJ-1',row[0]))]
            workspace_access.set_access(policy,manager,project,row[0],selected)
        policy.execute("INSERT INTO operator_fixture_versions VALUES('resource-access-v22')");policy.commit()
    policy.close()
    os.environ['GEO_DISTRIBUTOR_DB']=str(directory/'portal-demo'/'portal.db')
    from api.local_runtime import ports
    import uvicorn
    uvicorn.run('api.app:app',host='127.0.0.1',port=ports()['growth_sandbox_port'],access_log=False,server_header=False)

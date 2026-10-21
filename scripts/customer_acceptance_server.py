"""Disposable loopback customer write-flow fixture; never loads real credentials."""
import asyncio
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
if sys.stdout is None or sys.stderr is None:
    (root/'logs').mkdir(exist_ok=True)
    sys.stdout=sys.stderr=open(root/'logs'/'customer-acceptance.log','a',encoding='utf-8',buffering=1)
os.environ.pop('GEO_DISTRIBUTOR_DEMO_ONLY',None)
os.environ.update(GEO_DISTRIBUTOR_ENV='production',
    GEO_DISTRIBUTOR_API_KEYS='DEMO-GEO:customer-test:END_CUSTOMER:DEMO-CLI-1,DEMO-GEO:channel-test:DISTRIBUTOR_ADMIN,HQ:hq-test:HQ_MANAGEMENT',
    GEO_DISTRIBUTOR_SESSION_COOKIE='ggs_customer_acceptance_channel_sid',
    GEO_DISTRIBUTOR_AUDIT_DB=str(root/'data'/'customer-acceptance'/'audit.db'))
import api.auth
api.auth.REGISTRY_FILE=root/'data'/'customer-acceptance'/'disabled-registry.json'
if api.auth.REGISTRY_FILE.exists():
    raise RuntimeError('Acceptance fixture refuses credential registry')
from scripts.portal_demo_data import seed_demo
from scripts.customer_demo_data import seed_customer_demo
if __name__=='__main__':
    db=asyncio.run(seed_demo(root/'data'/'customer-acceptance'/'portal-demo'))
    asyncio.run(seed_customer_demo())
    os.environ['GEO_DISTRIBUTOR_DB']=str(db)
    import uvicorn
    from api.local_runtime import ports
    uvicorn.run('api.app:app',host='127.0.0.1',port=ports()['customer_acceptance_port'],access_log=False,server_header=False)

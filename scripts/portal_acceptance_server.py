"""Dedicated loopback browser acceptance fixture. Never uses customer databases."""
import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
if sys.stdout is None or sys.stderr is None:
    logdir=root/'logs';logdir.mkdir(exist_ok=True)
    sys.stdout=sys.stderr=open(logdir/'portal-acceptance-detached.log','a',encoding='utf-8',buffering=1)
os.environ['GEO_DISTRIBUTOR_ENV']='test'
os.environ['GEO_DISTRIBUTOR_API_KEYS']='UI-TEST:portal-ui-admin:DISTRIBUTOR_ADMIN,UI-TEST:portal-ui-view:CLIENT_VIEWER,HQ:portal-ui-tech:HQ_TECHNICAL,HQ:portal-ui-manager:HQ_MANAGEMENT'
os.environ['GEO_DISTRIBUTOR_DB']=str(root/'data'/'portal-acceptance'/'portal.db')
os.environ['GEO_DISTRIBUTOR_AUDIT_DB']=str(root/'data'/'portal-acceptance'/'audit.db')
os.environ['GEO_DISTRIBUTOR_RATE_LIMIT']='10000'
os.environ['GEO_DISTRIBUTOR_RATE_BURST']='10000'
from api.app import app
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8766,access_log=False,server_header=False)

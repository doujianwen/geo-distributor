"""Persistent single-instance local workspace entry, suitable for pythonw."""
import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
(root/'logs').mkdir(exist_ok=True)
if sys.stdout is None or sys.stderr is None:
    sys.stdout=sys.stderr=open(root/'logs'/'portal-local.log','a',encoding='utf-8',buffering=1)
os.environ['GEO_DISTRIBUTOR_DB']=str(root/'data'/'portal-local.db')
os.environ['GEO_DISTRIBUTOR_AUDIT_DB']=str(root/'data'/'portal-local-audit.db')
os.environ['GEO_DISTRIBUTOR_LOCAL_DEMO_LINK']='1'
if __name__=='__main__':
    from scripts.growth_workspace_setup import create_core
    import json
    identity_config=root/'config'/'workspace_identity.local.json'
    settings=json.loads(identity_config.read_text(encoding='utf-8')) if identity_config.exists() else {}
    for variable in ('GEO_IDENTITY_DB','GEO_IDENTITY_SECRET','GEO_IDENTITY_ISSUER'):
        if variable in settings:os.environ[variable]=settings[variable]
    growth_db=Path(settings.get('GEO_GROWTH_WORKSPACE_DB',str(root/'data'/'growth-workspace'/'core.db')))
    if not growth_db.exists(): create_core(growth_db)
    os.environ['GEO_GROWTH_WORKSPACE_DB']=str(growth_db)
    from api.local_runtime import ports
    import uvicorn
    uvicorn.run('api.app:app',host='127.0.0.1',port=ports()['local_port'],access_log=False,server_header=False)

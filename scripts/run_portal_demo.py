"""Loopback-only, isolated, read-only fictional showcase. No real registry."""
import asyncio
import os
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
if sys.stdout is None or sys.stderr is None:
    (root / "logs").mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(root / "logs" / "portal-demo.log", "a", encoding="utf-8", buffering=1)
if __name__ == "__main__":
    from scripts.portal_demo_data import seed_demo
    key = secrets.token_urlsafe(40)
    customer_key = secrets.token_urlsafe(40)
    hq_key, ops_key, partner_key = [secrets.token_urlsafe(40) for _ in range(3)]
    os.environ.update(GEO_DISTRIBUTOR_ENV="production", GEO_DISTRIBUTOR_DEMO_ONLY="1",
        GEO_DISTRIBUTOR_SESSION_COOKIE="ggs_demo_sid", GEO_DISTRIBUTOR_DEMO_KEY=key,
        GEO_DISTRIBUTOR_API_KEYS=f"DEMO-GEO:{key}:CLIENT_VIEWER,DEMO-GEO:{customer_key}:END_CUSTOMER:DEMO-CLI-1,DEMO-GEO:{hq_key}:HQ_MANAGEMENT,DEMO-GEO:{ops_key}:HQ_TECHNICAL,DEMO-PARTNER:{partner_key}:DISTRIBUTOR_ADMIN",
        GEO_DISTRIBUTOR_HQ_DEMO_KEY=hq_key, GEO_DISTRIBUTOR_OPS_DEMO_KEY=ops_key,
        GEO_DISTRIBUTOR_CUSTOMER_DEMO_KEY=customer_key,
        GEO_DISTRIBUTOR_AUDIT_DB=str(root / "data" / "portal-demo" / "audit.db"))
    import api.auth
    api.auth.REGISTRY_FILE = root / "data" / "portal-demo" / "disabled-registry.json"
    if api.auth.REGISTRY_FILE.exists():
        raise RuntimeError("Demo may not load a registry file")
    db = asyncio.run(seed_demo(root / "data" / "portal-demo"))
    from scripts.customer_demo_data import seed_customer_demo
    asyncio.run(seed_customer_demo())
    from scripts.hq_demo_data import seed_hq_demo
    asyncio.run(seed_hq_demo())
    os.environ["GEO_DISTRIBUTOR_DB"] = str(db)
    from scripts.growth_sandbox_data import seed
    growth_db=root / "data" / "portal-demo" / "growth.db"
    seed(growth_db,"fictional-demo-disabled-editor")
    os.environ["GEO_GROWTH_WORKSPACE_DB"]=str(growth_db)
    import uvicorn
    from api.local_runtime import ports
    uvicorn.run("api.app:app", host="127.0.0.1", port=ports()['demo_port'], access_log=False, server_header=False)

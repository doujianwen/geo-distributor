"""Loopback HQ write acceptance; isolated fixture, never real credentials/data."""
import asyncio
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
directory = root / "data" / "hq-acceptance" / "portal-demo"
if directory.is_symlink() or directory.resolve() != directory:
    raise RuntimeError("Acceptance directory must be local and isolated")
if sys.stdout is None or sys.stderr is None:
    (root / "logs").mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(root / "logs" / "hq-acceptance.log", "a", encoding="utf-8", buffering=1)
os.environ.pop("GEO_DISTRIBUTOR_DEMO_ONLY", None)
os.environ.update(GEO_DISTRIBUTOR_ENV="production",
    GEO_DISTRIBUTOR_API_KEYS="DEMO-GEO:hq-test:HQ_MANAGEMENT,DEMO-GEO:ops-test:HQ_TECHNICAL,DEMO-GEO:channel-test:DISTRIBUTOR_ADMIN,DEMO-GEO:customer-test:END_CUSTOMER:DEMO-CLI-1,DEMO-GEO:customer2-test:END_CUSTOMER:DEMO-CLI-2,DEMO-PARTNER:partner-test:DISTRIBUTOR_ADMIN",
    GEO_DISTRIBUTOR_SESSION_COOKIE="ggs_hq_acceptance_sid",
    GEO_DISTRIBUTOR_AUDIT_DB=str(root / "data" / "hq-acceptance" / "audit.db"))
import api.auth
api.auth.REGISTRY_FILE = directory.parent / "disabled-registry.json"
if api.auth.REGISTRY_FILE.exists():
    raise RuntimeError("Acceptance fixture refuses credential registry")
if __name__ == "__main__":
    from api import state
    db = directory / "portal.db"
    marker = directory.parent / "fixture-origin.txt"
    if db.exists():
        if not marker.exists() or marker.read_text() != "hq-fictional-v1":
            raise RuntimeError("Unknown acceptance database")
        state.init_repositories(str(db))
    else:
        from scripts.portal_demo_data import seed_demo
        from scripts.customer_demo_data import seed_customer_demo
        from scripts.hq_demo_data import seed_hq_demo
        asyncio.run(seed_demo(directory))
        asyncio.run(seed_customer_demo())
        asyncio.run(seed_hq_demo())
        marker.write_text("hq-fictional-v1")
    os.environ["GEO_DISTRIBUTOR_DB"] = str(db)
    import uvicorn
    from api.local_runtime import ports
    uvicorn.run("api.app:app", host="127.0.0.1", port=ports()["customer_acceptance_port"], access_log=False, server_header=False)

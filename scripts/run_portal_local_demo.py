"""本地门户 · 虚构演示数据集入口（127.0.0.1:local_port，即 /portal/ 反代目标）。

与 run_portal_local.py 的区别：
  - 业务库/增长库指向 data/portal-demo/（虚构演示数据集：澄源工业 / 星帆家居 / 青禾新材）
  - **保留** 个人账号身份交接（GEO_IDENTITY_*），使官网登录的测试账号可以直接进入

## 演示数据的保留策略（2026-10-28）

默认 **只在演示库为空时播种**。一旦库里有 DEMO-GEO 的客户，重启就完全跳过播种 ——
测试期间新增的客户 / 项目 / 报告 / 待办都会原样保留，适合对外演示。

需要还原成出厂演示态时，加 `--reset` 或设环境变量 `GEO_DEMO_RESET=1`：
只删除 data/portal-demo 目录下的 portal.db / growth.db / audit.db，然后重新播种。

为什么不复用 run_portal_demo.py：那个脚本面向 17667 演示端口，且强制
GEO_DISTRIBUTOR_DEMO_ONLY=1（只认演示密钥、不认个人身份），官网账号进不去。
本脚本不开启 DEMO_ONLY，因此「官网账号」与「演示密钥」两条路都可用。

不改动 run_portal_local.py，随时可以切回真实本地库。
"""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
(root / "logs").mkdir(exist_ok=True)
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(root / "logs" / "portal-local.log", "a", encoding="utf-8", buffering=1)

DEMO_DIR = root / "data" / "portal-demo"
DEMO_TENANT = "DEMO-GEO"


def _demo_has_data(db: Path) -> bool:
    """演示库是否已经有内容（有任一 DEMO-GEO 客户即视为已播种）。"""
    if not db.exists():
        return False
    try:
        with sqlite3.connect(db, timeout=10) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM clients WHERE tenant_id = ?", (DEMO_TENANT,)
            ).fetchone()
        return bool(row and row[0] > 0)
    except sqlite3.Error:
        return False


def _reset_demo_dataset() -> None:
    """还原出厂演示态：只删 portal-demo 目录内的三个库文件。

    仅本地开发可用。生产入口 run_portal_prod.py 已彻底移除该能力——
    演示库若混入真实业务，删文件会一并清空真实数据。
    """
    if DEMO_DIR.name != "portal-demo" or DEMO_DIR.is_symlink():
        raise RuntimeError("拒绝重置：目录不是受控的 portal-demo")
    for name in ("portal.db", "growth.db", "audit.db"):
        target = DEMO_DIR / name
        if target.exists() and not target.is_symlink():
            target.unlink()
            print(f"[demo] 已删除 {target.name}", flush=True)


def _enforce_purity() -> None:
    """启动前校验演示库纯度（与生产入口同一判据）。"""
    from scripts.check_demo_purity import check

    report = check(DEMO_DIR.resolve())
    if report["clean"]:
        return
    print("[purity] FAIL：演示库混入了非演示数据", flush=True)
    for item in report["problems"]:
        print(f"[purity]   - {item}", flush=True)
    raise SystemExit("演示库不纯：本地演示不应承载真实业务数据。用 --reset 还原，或改用 run_portal_local.py")


if __name__ == "__main__":
    reset = "--reset" in sys.argv or os.environ.get("GEO_DEMO_RESET") == "1"
    if reset:
        _reset_demo_dataset()

    _enforce_purity()

    db = DEMO_DIR / "portal.db"
    if _demo_has_data(db):
        # 已有演示数据：一律不再播种，避免覆盖演示期间的改动。
        print("[demo] 检测到已有演示数据，跳过播种（保留现有内容）", flush=True)
    else:
        from scripts.portal_demo_data import seed_demo
        from scripts.customer_demo_data import seed_customer_demo
        from scripts.hq_demo_data import seed_hq_demo

        db = asyncio.run(seed_demo(DEMO_DIR))
        asyncio.run(seed_customer_demo())
        asyncio.run(seed_hq_demo())
        print("[demo] 演示数据已播种完成", flush=True)

    os.environ["GEO_DISTRIBUTOR_DB"] = str(db)
    os.environ["GEO_DISTRIBUTOR_AUDIT_DB"] = str(DEMO_DIR / "audit.db")

    growth_db = DEMO_DIR / "growth.db"
    from scripts.growth_sandbox_data import seed as seed_growth
    seed_growth(growth_db, "fictional-demo-disabled-editor")  # 自带 marker 判断，已存在即跳过
    os.environ["GEO_GROWTH_WORKSPACE_DB"] = str(growth_db)

    identity_config = root / "config" / "workspace_identity.local.json"
    if identity_config.exists():
        settings = json.loads(identity_config.read_text(encoding="utf-8"))
        for variable in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER"):
            if variable in settings:
                os.environ[variable] = settings[variable]

    from api.local_runtime import ports
    import uvicorn

    uvicorn.run("api.app:app", host="127.0.0.1", port=ports()["local_port"],
                access_log=False, server_header=False)

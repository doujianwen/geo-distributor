"""生产门户运行入口（由 systemd 调用，监听 127.0.0.1:17665，经 nginx 反代对外）。

与 run_portal_local_demo.py 的区别：
  - 身份桥接密钥**不落仓库**：从 systemd 的 EnvironmentFile 注入
    （GEO_IDENTITY_DB / GEO_IDENTITY_SECRET / GEO_IDENTITY_ISSUER）；
    若未注入则回落到 config/workspace_identity.prod.json（仅本地调试用）。
  - 强制 GEO_DISTRIBUTOR_ENV=production（不加载内置开发密钥）
    与 GEO_DISTRIBUTOR_COOKIE_SECURE=1（HTTPS 下会话 Cookie 必须 Secure）。
  - 信任 127.0.0.1 的 X-Forwarded-* 头，使 Origin 校验看到的是
    https://www.tuozhigeo.com 而不是内网地址。

演示数据策略与本地一致：库里已有 DEMO-GEO 客户就跳过播种（保留演示期间的改动）。

关于「演示数据重置」——生产入口**不提供**重置能力：
冻结核心把「演示库只含演示数据」当作硬不变量（portal_demo_data.seed_demo 会
拒绝非演示库、growth_sandbox_data.seed 会校验 fixture 标记），而增长库 58 张表里
39 张没有租户列、observation_quality_review_events 还有 BEFORE DELETE 触发器，
因此无法安全地按租户删行。真实业务必须使用独立数据根，不能与演示库混用。
本入口在启动前执行 scripts/check_demo_purity.py 强制该校验，发现混入即拒绝启动。
"""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

DEMO_DIR = root / "data" / "portal-demo"
DEMO_TENANT = "DEMO-GEO"
IDENTITY_CONFIG = root / "config" / "workspace_identity.prod.json"


def _demo_has_data(db: Path) -> bool:
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


def _enforce_purity() -> None:
    """启动前强制校验演示库纯度；混入真实业务数据则拒绝启动。"""
    from scripts.check_demo_purity import check

    report = check(DEMO_DIR.resolve())
    if report["clean"]:
        print("[purity] PASS：演示库只含演示数据", flush=True)
        return
    print("[purity] FAIL：演示库混入了非演示数据，拒绝启动", flush=True)
    for item in report["problems"]:
        print(f"[purity]   - {item}", flush=True)
    raise SystemExit(
        "演示库不纯：请把真实业务迁移到独立数据根后重启。"
        "排查命令：python scripts/check_demo_purity.py"
    )



def _load_identity_env() -> None:
    """身份桥接配置：环境变量优先，其次本地 json（不含生产密钥）。"""
    if all(os.environ.get(k) for k in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER")):
        return
    if IDENTITY_CONFIG.exists():
        settings = json.loads(IDENTITY_CONFIG.read_text(encoding="utf-8"))
        for variable in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER"):
            if variable in settings and not os.environ.get(variable):
                os.environ[variable] = settings[variable]
    if not all(os.environ.get(k) for k in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER")):
        print("[warn] 身份桥接未配置：官网账号将无法进入工作区（仅演示密钥可用）", flush=True)


if __name__ == "__main__":
    if "--reset" in sys.argv or os.environ.get("GEO_DEMO_RESET") == "1":
        raise SystemExit(
            "生产入口不提供演示数据重置：删文件会连同真实业务一起清空。"
            "如需还原本地演示态，请在本地用 run_portal_local_demo.py --reset。"
        )

    _enforce_purity()

    db = DEMO_DIR / "portal.db"
    if _demo_has_data(db):
        print("[demo] 已有演示数据，跳过播种（保留现有内容）", flush=True)
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
    os.environ["GEO_DISTRIBUTOR_ENV"] = "production"
    os.environ["GEO_DISTRIBUTOR_COOKIE_SECURE"] = "1"

    growth_db = DEMO_DIR / "growth.db"
    # 增长核心根目录：生产上随包提供 core/（geo-intent-system 的 app 包 + 纯结构模板库），
    # 未提供时回落到 api/growth_core.py 的开发路径。
    core_root = root / "core"
    if core_root.is_dir() and not os.environ.get("GEO_GROWTH_CORE_ROOT"):
        os.environ["GEO_GROWTH_CORE_ROOT"] = str(core_root)
    from scripts.growth_sandbox_data import seed as seed_growth
    seed_growth(growth_db, "fictional-demo-disabled-editor")
    os.environ["GEO_GROWTH_WORKSPACE_DB"] = str(growth_db)

    _load_identity_env()

    import uvicorn

    uvicorn.run(
        "api.app:app",
        host="127.0.0.1",
        port=17665,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        access_log=False,
        server_header=False,
    )

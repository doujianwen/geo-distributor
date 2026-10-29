"""真实业务实例入口（127.0.0.1:17667，仅本机可达，不对外反代）。

## 为什么要单独一个实例

演示实例（17665）承载虚构数据集，并受 `check_demo_purity.py` 强制约束
「只含演示数据」。而官网表单投递的是**真实线索**——一旦落进演示库，
纯度守卫就会拒绝服务启动（2026-10-28 实测：两条冒烟线索即触发 FAIL）。

三条路里只有第三条是干净的：
  1. 放宽守卫，允许演示库混入真实 PII —— 等于取消不变量；
  2. 按租户删行 —— 已被证明不可行（增长库 39 张表无租户列 +
     append-only 触发器），见 docs/2026-10-28-SOCRATIC-AUDIT.md Q12；
  3. **真实业务独立数据根 + 独立进程** ← 本文件。

## 边界

- 数据根：`data/real/`（portal.db / growth.db / audit.db），**不播种任何演示数据**。
- 端口：17667，不写进 nginx，公网不可达。官网表单从本机回环投递线索。
- 身份：复用同一个 identity 库与签名密钥，便于日后给真实客户开通工作区；
  但本实例暂不对 `/ui/` 反代，客户入口等 1′/2 落地后再接。
- 不跑纯度守卫：这里本来就该有真实数据。

## 运维

    systemctl status geo-distributor-real
    journalctl -u geo-distributor-real -n 50
"""
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

REAL_DIR = root / "data" / "real"
IDENTITY_CONFIG = root / "config" / "workspace_identity.prod.json"
PORT = 17667


def _load_identity_env() -> None:
    """身份桥接配置：环境变量（systemd EnvironmentFile）优先。"""
    if all(os.environ.get(k) for k in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER")):
        return
    if IDENTITY_CONFIG.exists():
        settings = json.loads(IDENTITY_CONFIG.read_text(encoding="utf-8"))
        for variable in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER"):
            if variable in settings and not os.environ.get(variable):
                os.environ[variable] = settings[variable]
    if not all(os.environ.get(k) for k in ("GEO_IDENTITY_DB", "GEO_IDENTITY_SECRET", "GEO_IDENTITY_ISSUER")):
        print("[warn] 身份桥接未配置：真实客户暂时无法登录工作区", flush=True)


if __name__ == "__main__":
    REAL_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["GEO_DISTRIBUTOR_DB"] = str(REAL_DIR / "portal.db")
    os.environ["GEO_DISTRIBUTOR_AUDIT_DB"] = str(REAL_DIR / "audit.db")
    os.environ["GEO_DISTRIBUTOR_ENV"] = "production"
    os.environ["GEO_DISTRIBUTOR_COOKIE_SECURE"] = "1"

    # 增长核心根目录：随包提供的 core/（app 包 + 纯结构模板库）
    core_root = root / "core"
    if core_root.is_dir() and not os.environ.get("GEO_GROWTH_CORE_ROOT"):
        os.environ["GEO_GROWTH_CORE_ROOT"] = str(core_root)

    growth_db = REAL_DIR / "growth.db"
    if not growth_db.exists():
        from scripts.growth_workspace_setup import create_core

        create_core(growth_db)
        print(f"[real] 已按模板创建增长库 {growth_db}", flush=True)
    os.environ["GEO_GROWTH_WORKSPACE_DB"] = str(growth_db)

    _load_identity_env()

    import uvicorn

    print(f"[real] 真实业务实例启动于 127.0.0.1:{PORT}（数据根 {REAL_DIR}）", flush=True)
    uvicorn.run(
        "api.app:app",
        host="127.0.0.1",
        port=PORT,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        access_log=False,
        server_header=False,
    )

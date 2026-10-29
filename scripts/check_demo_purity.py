"""演示数据根纯度检查（fail-fast 守卫）。

背景
----
冻结核心把「演示库只含演示数据」当作硬不变量，而不是文档约定：

  * scripts/portal_demo_data.py:seed_demo 在播种前逐行校验，
    发现任何非演示租户/非 DEMO- 前缀的行就直接
    RuntimeError("Refusing a non-demo database")；
  * scripts/growth_sandbox_data.py:seed 用 workspace_fixture_marker
    记录 fixture 身份，标记不匹配就 RuntimeError('Unknown Growth fixture')。

这两处守卫只在「启动时要不要播种」的路径上生效。一旦库已经有数据、
走的是「跳过播种」分支，守卫就不会被调用——也就是说演示库在运行期间
被写入真实业务数据时，没有任何检查会报警。

本脚本把同一个不变量提前到进程启动前独立执行，使它在两种分支下都成立：
  * 退出码 0 = 纯净（可以对外提供演示）；
  * 退出码 1 = 混入非演示数据（拒绝启动，由运维决定迁移或重建）。

用法
----
    python scripts/check_demo_purity.py [数据根] [--json]

默认数据根为仓库内 data/portal-demo。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# 演示数据允许出现的租户。HQ-INTAKE 仅允许出现在线索入口表
# （演示线索在进入渠道商之前属于总部收件箱，见 hq_demo_data.py）。
DEMO_TENANTS = {"DEMO-GEO", "DEMO-PARTNER"}
INTAKE_TENANT = "HQ-INTAKE"
INTAKE_TABLES = {"leads_intake"}

GROWTH_FIXTURE_MARKER = "fictional-growth-v1"

# portal.db 中带 tenant_id 的业务表 -> 主键字段名。所有表都要过租户允许清单。
PORTAL_TENANT_TABLES = {
    "clients": "client_id",
    "projects": "project_id",
    "requests": "request_id",
    "measurements_projection": "measurement_id",
    "reports_projection": "report_id",
    "leads_intake": "lead_id",
    "client_reviews": "review_id",
    "client_publications": "publication_id",
    "hq_operations": "operation_id",
}

# 其中主键本身必须带 DEMO- 前缀的表（与 seed_demo 播种前的守卫保持一致）。
# client_reviews / client_publications 不在此列：它们的主键是
# "CRV-"/"PUB-" + 内容摘要（customer_demo_data.py 的有意设计），
# 对它们改用 project_id / report_id 的引用完整性校验。
DEMO_ID_TABLES = {
    "clients",
    "projects",
    "requests",
    "measurements_projection",
    "reports_projection",
    "leads_intake",
}

# 派生主键的表：改为校验这些引用字段指向演示对象
REFERENCE_FIELDS = ("project_id", "report_id", "request_id", "client_id")


def _say(text: str) -> None:
    """在 Windows 控制台编码不一致时不因打印而崩溃。"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("utf-8", "replace").decode("utf-8", "replace"), flush=True)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _check_portal(db: Path, problems: list[str]) -> dict:
    summary: dict = {"db": db.name, "exists": db.exists(), "tenants": {}, "rows": 0}
    if not db.exists():
        return summary
    with sqlite3.connect(db, timeout=10) as conn:
        for table, key_field in PORTAL_TENANT_TABLES.items():
            if not _table_exists(conn, table):
                continue
            allowed = DEMO_TENANTS | ({INTAKE_TENANT} if table in INTAKE_TABLES else set())
            rows = conn.execute(
                f"SELECT tenant_id, COUNT(*) FROM {table} GROUP BY tenant_id"
            ).fetchall()
            for tenant, count in rows:
                summary["tenants"].setdefault(tenant, 0)
                summary["tenants"][tenant] += count
                summary["rows"] += count
                if tenant not in allowed:
                    problems.append(
                        f"{db.name}/{table}: 出现非演示租户 {tenant!r}（{count} 行）"
                    )
            # 逐行校验 payload 内部的 tenant_id 与主键前缀，捕捉「外层改过、内层没改」的脏行
            try:
                cursor = conn.execute(f"SELECT tenant_id, payload FROM {table}")
            except sqlite3.Error:
                continue
            for tenant, payload in cursor:
                try:
                    item = json.loads(payload)
                except (TypeError, ValueError):
                    continue
                if not isinstance(item, dict):
                    continue
                inner = item.get("tenant_id")
                if inner is not None and inner != tenant:
                    problems.append(
                        f"{db.name}/{table}: 外层租户 {tenant!r} 与内层 {inner!r} 不一致"
                    )
                if table in DEMO_ID_TABLES:
                    ident = str(item.get(key_field, "") or "")
                    if ident and not ident.startswith("DEMO-"):
                        problems.append(
                            f"{db.name}/{table}: 非演示主键 {ident!r}（租户 {tenant!r}）"
                        )
                else:
                    # 派生主键的表：校验它引用的对象确实是演示对象
                    for field in REFERENCE_FIELDS:
                        ref = str(item.get(field, "") or "")
                        if ref and not ref.startswith("DEMO-"):
                            problems.append(
                                f"{db.name}/{table}: 引用非演示对象 {field}={ref!r}"
                            )
    return summary


def _check_growth(db: Path, problems: list[str]) -> dict:
    summary: dict = {"db": db.name, "exists": db.exists(), "marker": None, "tenants": {}}
    if not db.exists():
        return summary
    with sqlite3.connect(db, timeout=10) as conn:
        if not _table_exists(conn, "workspace_fixture_marker"):
            problems.append(
                f"{db.name}: 缺少 workspace_fixture_marker，无法证明是演示 fixture"
            )
            return summary
        row = conn.execute(
            "SELECT value FROM workspace_fixture_marker WHERE name='origin'"
        ).fetchone()
        summary["marker"] = row[0] if row else None
        if summary["marker"] != GROWTH_FIXTURE_MARKER:
            problems.append(
                f"{db.name}: fixture 标记为 {summary['marker']!r}，期望 {GROWTH_FIXTURE_MARKER!r}"
            )
        if _table_exists(conn, "workspace_sites"):
            for tenant, client, site_id in conn.execute(
                "SELECT tenant, client, site_id FROM workspace_sites"
            ):
                summary["tenants"].setdefault(tenant, 0)
                summary["tenants"][tenant] += 1
                if tenant not in DEMO_TENANTS:
                    problems.append(
                        f"{db.name}/workspace_sites: 站点 {site_id} 属于非演示租户 {tenant!r}"
                    )
        if _table_exists(conn, "workspace_bindings"):
            for project_key, tenant in conn.execute(
                "SELECT project_key, tenant FROM workspace_bindings"
            ):
                if tenant not in DEMO_TENANTS:
                    problems.append(
                        f"{db.name}/workspace_bindings: {project_key!r} 属于非演示租户 {tenant!r}"
                    )
    return summary


def check(root: Path) -> dict:
    problems: list[str] = []
    report = {
        "root": str(root),
        "portal": _check_portal(root / "portal.db", problems),
        "growth": _check_growth(root / "growth.db", problems),
        "audit": {"db": "audit.db", "exists": (root / "audit.db").exists()},
        "problems": problems,
        "clean": not problems,
    }
    return report


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    as_json = "--json" in argv
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1] / "data" / "portal-demo"
    root = root.resolve()
    if root.name != "portal-demo":
        _say(f"[purity] 拒绝检查：目录不是受控的 portal-demo（{root}）")
        return 2
    report = check(root)
    if as_json:
        _say(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _say(f"[purity] 数据根: {report['root']}")
        _say(f"[purity] portal.db 租户分布: {report['portal']['tenants']}  行数={report['portal']['rows']}")
        _say(f"[purity] growth.db 标记: {report['growth']['marker']}  站点租户={report['growth']['tenants']}")
        if report["clean"]:
            _say("[purity] PASS：只含演示数据")
        else:
            _say(f"[purity] FAIL：发现 {len(report['problems'])} 处非演示数据")
            for item in report["problems"]:
                _say(f"  - {item}")
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

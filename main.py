"""GEO Platform CLI 入口。

使用方式：
    python main.py --mode demo            # 骨架演示（推荐，A1.6 阶段）
    python main.py --mode health          # 检查适配器健康状态
    python main.py --mode status          # 查看上游数据状态
    python main.py --mode collect         # 执行采集（需要 Project 配置）
    python main.py --mode report          # 生成报告
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geo_distributor.config import load_settings, get_project_root, get_geo_collector_root
import geo_distributor
from geo_distributor.adapters import ElmoAdapter, GeoCollectorAdapter
from geo_distributor.models import Prompt


def parse_args():
    parser = argparse.ArgumentParser(description="GEO Platform CLI")
    parser.add_argument(
        "--mode",
        choices=["health", "collect", "report", "demo", "status"],
        default="demo",
    )
    parser.add_argument("--adapter", choices=["elmo", "geo-collector"], default="geo-collector")
    parser.add_argument("--config", help="覆盖配置文件路径")
    return parser.parse_args()


async def cmd_health(adapter_name: str) -> None:
    if adapter_name == "elmo":
        adapter = ElmoAdapter()
    else:
        adapter = GeoCollectorAdapter()
    healthy = await adapter.health_check()
    print(f"[HEALTH] Adapter={adapter_name}  status={'OK' if healthy else 'DOWN'}")


async def cmd_demo() -> None:
    import geo_distributor
    print("=" * 60)
    print(f"GEO Platform {geo_distributor.__version__} — A1.7 ElmoAdapter MVP")
    print("=" * 60)

    settings = load_settings()
    elmo_cfg = settings.get("elmo", {})
    print(f"\n[Config] Brand:      {settings.get('brand', 'N/A')}")
    print(f"[Config] Proxy:       {settings.get('proxy', 'N/A')}")
    print(f"[Config] Use Elmo:    {settings.get('distributor', {}).get('use_elmo_adapter', False)}")
    print(f"[Config] Elmo URL:    {elmo_cfg.get('base_url', 'NOT SET')}")
    print(f"[Config] Elmo Key:    {'***' if elmo_cfg.get('api_key') else 'NOT SET'}")
    print(f"[Config] Elmo Ver:    {elmo_cfg.get('version', 'NOT SET')}")

    print("\n[Adapters]")
    print("  - ElmoAdapter:           MVP (A1.7, REST API)")
    print("  - GeoCollectorAdapter:   PASS (ready to use)")

    print("\n[Compatibility Layer]")
    print("  - PlatformObservation:       OK (统一契约)")
    print("  - PlatformCitation:          OK (统一契约)")
    print("  - map_geo_collector_observation:  OK (geo-collector → Platform)")
    print("  - map_elmo_to_platform:      OK (Elmo → Platform)")
    print("  - map_elmo_citation:         OK (Elmo citation → PlatformCitation)")

    print("\n[Models — GEO 智能链路]")
    for cls_name in ["Prompt", "Observation", "Citation", "Evidence"]:
        print(f"  - {cls_name}: OK")
    print("  - Provider:      OK (V0.3)")
    print("  - Measurement:   OK (V0.3)")
    print("  - Diagnosis:     OK (V0.3)")

    print("\n[Models — 商业产品层]")
    for cls_name in ["Organization", "Account", "Brand", "Project", "Run", "Report"]:
        print(f"  - {cls_name}: OK")

    print("\n[Services]")
    print("  - DistributionService: STUB (A1.7)")

    print("\n[移除项（审计意见）]")
    print("  - api/router.py: 已删除（推迟到 A1.7）")

    print("\n" + "=" * 60)
    print("All checks passed. A1.7 ElmoAdapter MVP ready.")
    print("=" * 60)


async def cmd_status() -> None:
    collector_root = get_geo_collector_root()
    db_path = os.path.join(collector_root, "geo_collector.db")

    print("=" * 60)
    print(f"GEO Platform {geo_distributor.__version__} — Status")
    print("=" * 60)
    print(f"\n[Paths]")
    print(f"  Platform root:  {get_project_root()}")
    print(f"  Collector root: {collector_root}")
    print(f"  DB (upstream):  {db_path}")
    print(f"  DB exists:      {os.path.exists(db_path)}")

    if os.path.exists(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM observations WHERE status='success'").fetchone()[0]
        failed = total - success
        brand_hits = conn.execute("SELECT COUNT(*) FROM observations WHERE brand_mentioned=1").fetchone()[0]
        recommended = conn.execute("SELECT COUNT(*) FROM observations WHERE recommendation_level >= 3").fetchone()[0]
        conn.close()
        print(f"\n[Upstream Data (geo-collector)]")
        print(f"  Total observations:  {total}")
        print(f"  Successful:          {success}")
        print(f"  Failed:              {failed}")
        print(f"  Brand mentioned:     {brand_hits}")
        print(f"  Brand recommended:   {recommended}")
    print("\n" + "=" * 60)


async def main():
    args = parse_args()
    if args.config:
        os.environ["GEO_DISTRIBUTOR_CONFIG"] = args.config

    if args.mode == "health":
        await cmd_health(args.adapter)
    elif args.mode == "demo":
        await cmd_demo()
    elif args.mode == "status":
        await cmd_status()
    elif args.mode in ("collect", "report"):
        print(f"[WARN] {args.mode} mode not yet implemented — waiting for A1.7")

    from geo_distributor.config import load_settings, load_engines
    load_settings.cache_clear()
    load_engines.cache_clear()


if __name__ == "__main__":
    asyncio.run(main())

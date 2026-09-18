"""GEO Platform CLI 入口（V2 修复版）。

使用方式：
    python main.py --mode demo            # 骨架演示
    python main.py --mode health          # 检查适配器健康状态
    python main.py --mode status          # 查看上游数据状态
    python main.py --mode collect         # 执行采集（支持 Elmo/OpenGeo/Mock）
    python main.py --mode report          # 生成报告
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geo_distributor.config import (
    load_settings,
    get_project_root,
    get_geo_collector_root,
    get_secret,
    scan_hardcoded_secrets,
)
import geo_distributor
from geo_distributor.adapters import ElmoAdapter, GeoCollectorAdapter, GeoCollectorDBAdapter
from geo_distributor.adapters.opengeo import OpenGeoAdapter
from geo_distributor.compatibility.base import PlatformObservation
from geo_distributor.models import Prompt
from geo_distributor.models.finding import Finding, FindingSeverity, FindingCategory
from geo_distributor.services.measurement_analysis import aggregate_metrics
from geo_distributor.services.delivery import DeliveryService


def parse_args():
    parser = argparse.ArgumentParser(description="GEO Platform CLI")
    parser.add_argument(
        "--mode",
        choices=["health", "collect", "report", "demo", "status", "sync"],
        default="demo",
    )
    parser.add_argument("--adapter", choices=["elmo", "geo-collector", "geo-collector-db", "opengeo", "mock"], default="geo-collector-db")
    parser.add_argument("--config", help="覆盖配置文件路径")
    parser.add_argument("--case", help="Sprint4 案例目录（如 bookconv/tjostrichink）")
    parser.add_argument("--project-id", help="项目 ID")
    parser.add_argument("--tenant-id", help="租户 ID")
    parser.add_argument("--brand", help="同步/采集目标品牌（sync 模式必填）")
    parser.add_argument("--force", action="store_true", help="sync 模式：忽略水位，全量重同步")
    return parser.parse_args()


async def cmd_health(adapter_name: str) -> None:
    if adapter_name == "elmo":
        adapter = ElmoAdapter()
    elif adapter_name == "opengeo":
        # OpenGeoAdapter 需要 observations，health check 返回 False 如果无数据
        adapter = OpenGeoAdapter()
        healthy = await adapter.health_check()
        print(f"[HEALTH] Adapter={adapter_name}  status={'OK' if healthy else 'NO_DATA'}")
        return
    elif adapter_name == "geo-collector-db":
        # GeoCollectorDBAdapter 直接读 SQLite，零依赖
        db_path = os.path.join(get_geo_collector_root(), "geo_collector.db")
        adapter = GeoCollectorDBAdapter(db_path=db_path, brand="Hydroviv")
        healthy = await adapter.health_check()
        stats = GeoCollectorDBAdapter.get_stats(db_path)
        print(f"[HEALTH] Adapter={adapter_name}  status={'OK' if healthy else 'DOWN'}")
        if healthy:
            print(f"  Observations: {stats.get('total_observations', 0)}")
            print(f"  Prompts: {stats.get('total_prompts', 0)}")
            print(f"  Engines: {', '.join(stats.get('engines', []))}")
        return
    else:
        adapter = GeoCollectorAdapter()
    healthy = await adapter.health_check()
    print(f"[HEALTH] Adapter={adapter_name}  status={'OK' if healthy else 'DOWN'}")


async def cmd_collect(args) -> None:
    """执行采集 — 支持多种 Adapter。"""
    adapter_name = args.adapter
    case = args.case
    project_id = args.project_id or f"PRJ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    tenant_id = args.tenant_id or "DST-DEFAULT"

    print("=" * 60)
    print(f"GEO Platform {geo_distributor.__version__} — Collect Mode")
    print("=" * 60)
    print(f"\n[Config]")
    print(f"  Adapter:    {adapter_name}")
    print(f"  Project:    {project_id}")
    print(f"  Tenant:     {tenant_id}")
    print(f"  Case:       {case or 'N/A'}")

    # 加载 observations
    observations = []
    if case:
        cases_dir = os.path.join(get_project_root(), "sprint4-lab", "cases")
        case_path = os.path.join(cases_dir, case, "baseline", "observations.json")
        if os.path.exists(case_path):
            with open(case_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            observations = [PlatformObservation(**obs) for obs in data] if isinstance(data, list) else []
            print(f"\n[Data] Loaded {len(data)} observations from {case_path}")
        else:
            print(f"\n[ERROR] Case data not found: {case_path}")
            return
    elif adapter_name == "opengeo":
        print("\n[WARN] OpenGeo adapter requires --case flag for data source")
        return
    elif adapter_name == "elmo":
        settings = load_settings()
        elmo_cfg = settings.get("elmo", {})
        base_url = elmo_cfg.get("base_url", "")
        # 密钥：环境变量 ELMO_API_KEY 优先，回退配置里的 ${ELMO_API_KEY} 展开值
        api_key = get_secret(elmo_cfg, "api_key", env_var="ELMO_API_KEY")
        if not elmo_cfg.get("enabled"):
            print("\n[ERROR] Elmo adapter disabled in config (elmo.enabled=false)")
            return
        if not base_url:
            print("\n[ERROR] Elmo base_url not configured")
            return
        if not api_key:
            print(
                "\n[ERROR] Elmo API key not set.\n"
                "        Set it via environment variable:  export ELMO_API_KEY=...\n"
                "        或写入 config/settings.yaml:  elmo.api_key: \"${ELMO_API_KEY}\"\n"
                "        密钥禁止硬编码入仓库。"
            )
            return
        adapter = ElmoAdapter(
            elmo_url=base_url,
            api_key=api_key,
            version=elmo_cfg.get("version", "v0.3.0"),
        )
        # 这里需要实际的 prompt_id，暂不支持
        print("\n[WARN] Elmo adapter requires configured prompts")
        return
    elif adapter_name == "geo-collector-db":
        # 直接从 geo-collector SQLite 读取，零依赖
        db_path = os.path.join(get_geo_collector_root(), "geo_collector.db")
        if not os.path.exists(db_path):
            print(f"\n[ERROR] geo-collector.db not found: {db_path}")
            return
        settings = load_settings()
        brand = settings.get("brand", "Hydroviv")
        adapter = GeoCollectorDBAdapter(db_path=db_path, brand=brand)
        # 加载 prompts 从 DB
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT prompt_id, prompt_text, category FROM prompts ORDER BY prompt_id")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            print(f"\n[ERROR] No prompts found in {db_path}")
            return
        prompts = [Prompt(prompt_id=r["prompt_id"], text=r["prompt_text"], category=r["category"] or "", intent=r["intent"] or "", location=r["location"] or "") for r in rows]
        observations = asyncio.run(adapter.collect_batch(prompts))
        print(f"\n[Data] Loaded {len(observations)} observations from {db_path}")
    else:
        print("\n[ERROR] Unsupported adapter: {}".format(adapter_name))
        return

    # 聚合指标
    if observations:
        metrics = aggregate_metrics(
            observations=observations,
            case_id=case or "default",
            version="collect",
        )
        print(f"\n[Metrics]")
        print(f"  Query count:      {metrics.query_count}")
        print(f"  Mention rate:     {metrics.mention_rate:.1f}%")
        print(f"  Recommendation:   {metrics.recommendation_rate:.1f}%")
        print(f"  Avg level:        {metrics.avg_recommendation_level:.2f}")
    else:
        print("\n[WARN] No observations collected")
        return

    # 生成 Findings
    findings = generate_findings_from_observations(observations, project_id, case or "default")
    print(f"\n[Findings] Generated {len(findings)} findings")
    for f in findings[:5]:  # 显示前 5 条
        print(f"  - [{f.severity.value.upper()}] {f.statement[:60]}...")

    # 保存结果
    output_dir = os.path.join(get_project_root(), "exports", project_id)
    os.makedirs(output_dir, exist_ok=True)

    result = {
        "project_id": project_id,
        "tenant_id": tenant_id,
        "adapter": adapter_name,
        "case": case,
        "collected_at": datetime.now().isoformat(),
        "observation_count": len(observations),
        "metrics": metrics.to_dict() if observations else {},
        "findings": [f.to_dict() for f in findings],
    }

    output_path = os.path.join(output_dir, "collect_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[Output] Saved to {output_path}")
    print("=" * 60)


def generate_findings_from_observations(observations, project_id: str, case_id: str) -> list:
    """从 Observations 生成 Findings。"""
    findings = []
    finding_counter = 0

    for obs in observations:
        # 品牌未被提及
        if not obs.brand_mentioned:
            finding_counter += 1
            findings.append(Finding(
                finding_id=f"FND-{project_id}-{finding_counter:03d}",
                observation_ids=[obs.observation_id],
                category=FindingCategory.VISIBILITY_GAP,
                severity=FindingSeverity.HIGH,
                statement=f"Brand not mentioned for query: '{obs.prompt_text}'",
                recommendation="Add entity-focused content and improve brand signals",
                confidence=0.9,
                project_id=project_id,
                case_id=case_id,
            ))

        # 品牌提及但推荐级别低
        elif obs.brand_mentioned and obs.recommendation_level < 2:
            finding_counter += 1
            findings.append(Finding(
                finding_id=f"FND-{project_id}-{finding_counter:03d}",
                observation_ids=[obs.observation_id],
                category=FindingCategory.CITATION_QUALITY,
                severity=FindingSeverity.MEDIUM,
                statement=f"Brand mentioned but low recommendation (level={obs.recommendation_level}) for: '{obs.prompt_text}'",
                recommendation="Improve content authority and add expert citations",
                confidence=0.7,
                project_id=project_id,
                case_id=case_id,
            ))

        # 无引用来源
        elif obs.citations_status == "none":
            finding_counter += 1
            findings.append(Finding(
                finding_id=f"FND-{project_id}-{finding_counter:03d}",
                observation_ids=[obs.observation_id],
                category=FindingCategory.CONTENT_GAP,
                severity=FindingSeverity.MEDIUM,
                statement=f"No citations found for query: '{obs.prompt_text}'",
                recommendation="Create linkable assets and authoritative content",
                confidence=0.6,
                project_id=project_id,
                case_id=case_id,
            ))

    return findings


async def cmd_report(args) -> None:
    """生成报告。"""
    project_id = args.project_id
    if not project_id:
        print("[ERROR] --project-id required for report mode")
        return

    # 加载 collect result
    exports_dir = os.path.join(get_project_root(), "exports")
    result_path = os.path.join(exports_dir, project_id, "collect_result.json")

    if not os.path.exists(result_path):
        print(f"[ERROR] Collect result not found: {result_path}")
        print("Hint: Run 'python main.py --mode collect --project-id {}' first".format(project_id))
        return

    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 60)
    print(f"GEO Platform {geo_distributor.__version__} — Report")
    print("=" * 60)
    print(f"\n[Project] {project_id}")
    print(f"[Collected] {data.get('collected_at', 'N/A')}")
    print(f"[Observations] {data.get('observation_count', 0)}")

    metrics = data.get("metrics", {})
    if metrics:
        print(f"\n[Metrics]")
        print(f"  Mention rate:     {metrics.get('mention_rate', 0):.1f}%")
        print(f"  Recommendation:   {metrics.get('recommendation_rate', 0):.1f}%")
        print(f"  Avg level:        {metrics.get('avg_recommendation_level', 0):.2f}")

    findings = data.get("findings", [])
    print(f"\n[Findings] {len(findings)} total")
    for f in findings:
        print(f"  - [{f.get('severity', '?').upper()}] {f.get('statement', '')[:50]}...")

    print("\n" + "=" * 60)


async def cmd_demo() -> None:
    import geo_distributor
    print("=" * 60)
    print(f"GEO Platform {geo_distributor.__version__} — V2 Demo")
    print("=" * 60)

    settings = load_settings()
    elmo_cfg = settings.get("elmo", {})
    elmo_key = get_secret(elmo_cfg, "api_key", env_var="ELMO_API_KEY")
    key_source = "env:ELMO_API_KEY" if os.environ.get("ELMO_API_KEY") else (
        "config" if elmo_key else "NOT SET"
    )
    print(f"\n[Config] Brand:      {settings.get('brand', 'N/A')}")
    print(f"[Config] Proxy:       {settings.get('proxy', 'N/A')}")
    print(f"[Config] Elmo URL:    {elmo_cfg.get('base_url', 'NOT SET')}")
    print(f"[Config] Elmo Key:    {'***' if elmo_key else 'NOT SET'}  (source: {key_source})")

    # 密钥安全扫描：只报告，不修改
    secret_hits = scan_hardcoded_secrets(settings)
    if secret_hits:
        print("\n[SECURITY] ⚠ 检测到疑似硬编码密钥：")
        for cfg_path, reason in secret_hits:
            print(f"  - {cfg_path}: {reason}")
    else:
        print("\n[SECURITY] ✓ 未检测到硬编码密钥")

    print("\n[Adapters]")
    print("  - ElmoAdapter:           MVP (REST API)")
    print("  - GeoCollectorAdapter:   PASS (ready to use)")
    print("  - OpenGeoAdapter:        PASS (read from JSON)")
    print("  - MockMeasurementAdapter: TEST ONLY")

    print("\n[Models]")
    for cls_name in ["Prompt", "Observation", "Evidence", "Measurement", "Diagnosis", "Finding"]:
        print(f"  - {cls_name}: OK")
    print("  - Provider:      OK (V0.3)")
    print("  - Report:        OK (with versions)")

    print("\n[Services]")
    print("  - IntakeService:       OK")
    print("  - ScopingService:      OK")
    print("  - ProjectService:      OK")
    print("  - DeliveryService:     OK")
    print("  - EvidenceLibrary:     OK")
    print("  - MeasurementAnalysis: OK")
    print("  - DistributionService: STUB (A1.8+)")

    print("\n[V2 Features]")
    print("  - Finding model:       ✅ NEW")
    print("  - Collect mode:        ✅ NEW")
    print("  - Report mode:         ✅ NEW")
    print("  - Web API:             ❌ TODO (FastAPI)")

    print("\n" + "=" * 60)
    print("V2 Demo complete. Use --mode collect to run measurement.")
    print("=" * 60)


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
    elif args.mode == "collect":
        await cmd_collect(args)
    elif args.mode == "report":
        await cmd_report(args)
    elif args.mode == "sync":
        cmd_sync(args)

    from geo_distributor.config import load_settings, load_engines
    load_settings.cache_clear()
    load_engines.cache_clear()


def cmd_sync(args) -> None:
    """增量同步 geo-collector → geo-distributor（P0-4 增强）。"""
    from geo_distributor.services.sync_service import SyncService

    print("=" * 60)
    print(f"GEO Platform {geo_distributor.__version__} — Sync Mode")
    print("=" * 60)

    svc = SyncService()

    if not os.path.exists(svc.db_path):
        print(f"\n[ERROR] geo-collector DB not found: {svc.db_path}")
        return

    # 无 --brand 时列出可选品牌并展示全局水位
    if not args.brand:
        print("\n[Available brands]")
        for b in svc.list_brands():
            st = svc.get_status(b)
            print(f"  - {b}: known={st.get('known_count', 0)}, last_sync={st.get('last_synced_at') or 'never'}")
        print("\n[Hint] 指定品牌：--mode sync --brand <NAME>")
        print("       全量重同步：--mode sync --brand <NAME> --force")
        return

    try:
        result = svc.sync(brand=args.brand, force=args.force)
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        return

    print(f"\n[Sync] brand={result.brand}  force={'yes' if result.forced else 'no'}")
    print(f"  New observations:   {result.new_count}")
    print(f"  Already known:      {result.known_count}")
    print(f"  Total in DB:        {result.total_in_db}")
    print(f"  Synced at:          {result.synced_at}")

    if result.new_observation_ids:
        print(f"\n[New IDs] (最多显示 10 条)")
        for oid in result.new_observation_ids[:10]:
            print(f"  - {oid}")
        if len(result.new_observation_ids) > 10:
            print(f"  ... 共 {len(result.new_observation_ids)} 条")

    # 落盘增量结果，供后续 collect / report 复用
    out_dir = os.path.join(get_project_root(), "exports", "sync")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir, f"{result.brand}_incremental_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(include_observations=True), f, ensure_ascii=False, indent=2)
    print(f"\n[Saved] {out_path}")
    print("\n" + "=" * 60)


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


if __name__ == "__main__":
    asyncio.run(main())

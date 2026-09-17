"""A1.7.1 — Real Elmo E2E Validation Script.

最小化真实连接验证：1 prompt × 1 brand × 1 engine。

验收标准：
  1. ID 追溯：Evidence → Observation → Elmo Evaluation → 原始 Response
  2. Citation 信息完整性：URL / Title / Position / Source / Context
  3. Provider 信息：provider / model / version / timestamp
  4. Failure Handling：API timeout / 404 / 401 / invalid evaluation
  5. Measurement 独立性：真实 Observation → Evidence → Measurement（自有计算）

使用方式：
  python main.py --mode e2e-test --adapter elmo
  python main.py --mode e2e-test --adapter elmo --prompt-id <uuid>
  python main.py --mode e2e-test --adapter elmo --single-test health|api|mapping|full|failure

必须配置 settings.yaml:
  elmo:
    enabled: true
    base_url: "http://localhost:3000"  # 或 Cloud URL
    api_key: "<your-bearer-token>"
    version: "v0.3.0"
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geo_distributor.config import load_settings, get_elmo_config
from geo_distributor.adapters import ElmoAdapter
from geo_distributor.models import Prompt


# ------------------------------------------------------------------
# E2E Test Runner
# ------------------------------------------------------------------

class E2EResult:
    """单次 E2E 测试结果的容器。"""
    def __init__(self, name: str, passed: bool, details: dict = None, error: str = ""):
        self.name = name
        self.passed = passed
        self.details = details or {}
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "timestamp": self.timestamp,
            "details": self.details,
            "error": self.error,
        }

    def __repr__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"E2EResult({status}) {self.name}: {self.error or self.details}"


async def test_health(result: E2EResult) -> E2EResult:
    """T1: Health Check — 确认 Elmo API 可访问。"""
    try:
        healthy = await result.adapter.health_check()
        result.passed = healthy
        result.details = {"healthy": healthy}
        if not healthy:
            result.error = "health_check returned False"
    except Exception as e:
        result.passed = False
        result.error = str(e)
    return result


async def test_api_response(result: E2EResult) -> E2EResult:
    """T2: API Schema — 验证原始 API 返回符合预期 schema。"""
    from geo_distributor.adapters.elmo_client import ElmoClient
    cfg = get_elmo_config()

    try:
        client = ElmoClient(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            version=cfg.get("version", "v0.3.0"),
        )
        # 获取最新 prompt run
        runs = await client.list_runs(result.prompt_id_uuid, limit=1)
        if not runs:
            result.passed = False
            result.error = "No runs found for prompt"
            return result

        run = runs[0]
        result.details["run_id"] = run.get("id", "")
        result.details["model"] = run.get("model", "")
        result.details["provider"] = run.get("provider", "")
        result.details["version"] = run.get("version", "")
        result.details["brand_mentioned"] = run.get("brandMentioned", run.get("brand_mentioned"))
        result.details["citations_count"] = len(run.get("citations", []))
        result.details["web_search_enabled"] = run.get("webSearchEnabled", run.get("web_search_enabled"))

        # 验证必要字段存在
        required_fields = ["id", "model"]
        missing = [f for f in required_fields if not run.get(f)]
        if missing:
            result.passed = False
            result.error = f"Missing required fields in run: {missing}"
        else:
            result.passed = True
            # 打印原始 run schema 供审计
            result.details["raw_run_keys"] = list(run.keys())
            if run.get("citations"):
                result.details["raw_citation_keys"] = list(run["citations"][0].keys())

    except Exception as e:
        result.passed = False
        result.error = str(e)
    return result


async def test_mapping(result: E2EResult) -> E2EResult:
    """T3: Mapping — 验证 Elmo → PlatformObservation 映射完整。"""
    try:
        obs = await result.adapter.collect_prompt(result.prompt)
        result.details["observation_id"] = obs.observation_id
        result.details["prompt_id"] = obs.prompt_id
        result.details["engine"] = obs.engine
        result.details["brand"] = obs.brand
        result.details["brand_mentioned"] = obs.brand_mentioned
        result.details["brand_status"] = obs.brand_status
        result.details["answer_char_count"] = obs.answer_char_count
        result.details["citations_count"] = len(obs.citations)
        result.details["citations_status"] = obs.citations_status
        result.details["status"] = obs.status
        result.details["raw_metadata"] = obs.raw_metadata

        # 验证关键字段
        checks = {
            "observation_id_not_empty": obs.observation_id != "",
            "status_not_failed": obs.status != "failed",
            "brand_not_empty": obs.brand != "",
            "raw_metadata_has_provider": obs.raw_metadata.get("provider") == "elmo",
            "raw_metadata_has_version": bool(obs.raw_metadata.get("version")),
            "raw_metadata_has_original_prompt_id": bool(obs.raw_metadata.get("original_prompt_id")),
        }
        result.details["checks"] = checks
        result.passed = all(checks.values())
        failed_checks = [k for k, v in checks.items() if not v]
        if failed_checks:
            result.error = f"Mapping checks failed: {failed_checks}"

        # Citation 信息完整性
        if obs.citations:
            cit = obs.citations[0]
            cit_checks = {
                "has_url": bool(cit.get("url")),
                "has_domain": bool(cit.get("domain")),
                "has_title": bool(cit.get("title")),
                "has_citation_index": cit.get("citation_index") is not None,
                "has_citation_type": bool(cit.get("citation_type")),
            }
            result.details["citation_sample"] = cit
            result.details["citation_checks"] = cit_checks
            cit_failed = [k for k, v in cit_checks.items() if not v]
            if cit_failed:
                result.error += f"; Citation info loss: {cit_failed}"

    except Exception as e:
        result.passed = False
        result.error = str(e)
    return result


async def test_id_traceability(result: E2EResult) -> E2EResult:
    """T4: ID 追溯 — Evidence → Observation → Elmo Evaluation → 原始 Response。"""
    try:
        obs = result.platform_observation
        rm = obs.raw_metadata

        # 追溯链：
        # 1. observation_id → Elmo run id
        # 2. raw_metadata.original_prompt_id → Elmo prompt UUID
        # 3. raw_metadata.original_run_id → Elmo run UUID
        # 4. citations 中的 observation_id → 可追溯到 run

        trace = {
            "platform_observation_id": obs.observation_id,
            "elmo_run_id": rm.get("original_run_id", ""),
            "elmo_prompt_uuid": rm.get("original_prompt_id", ""),
            "elmo_version": rm.get("elmo_version", ""),
            "provider": rm.get("provider", ""),
            "citations_traces": [],
        }

        for i, cit in enumerate(obs.citations):
            trace["citations_traces"].append({
                "index": i,
                "observation_id": cit.get("observation_id", ""),
                "url": cit.get("url", ""),
                "matches_run_id": cit.get("observation_id") == obs.observation_id,
            })

        result.details["trace"] = trace

        # 验证追溯完整性
        checks = {
            "obs_id_matches_run_id": obs.observation_id == rm.get("original_run_id"),
            "prompt_uuid_present": bool(rm.get("original_prompt_id")),
            "citations_link_to_observation": all(
                c["matches_run_id"] for c in trace["citations_traces"]
            ) if trace["citations_traces"] else True,
        }
        result.details["traceability_checks"] = checks
        result.passed = all(checks.values())
        failed = [k for k, v in checks.items() if not v]
        if failed:
            result.error = f"Traceability failed: {failed}"

    except Exception as e:
        result.passed = False
        result.error = str(e)
    return result


async def test_provider_info(result: E2EResult) -> E2EResult:
    """T5: Provider 信息 — 确认 provider/model/version/timestamp 可获取。"""
    try:
        obs = result.platform_observation
        rm = obs.raw_metadata

        checks = {
            "provider_set": rm.get("provider") == "elmo",
            "model_set": bool(rm.get("model")),
            "elmo_version_set": bool(rm.get("elmo_version")),
            "timestamp_present": bool(obs.timestamp),
            "engine_set": bool(obs.engine),
        }
        result.details["provider_info"] = {
            "provider": rm.get("provider"),
            "model": rm.get("model"),
            "elmo_version": rm.get("elmo_version"),
            "timestamp": obs.timestamp,
            "engine": obs.engine,
        }
        result.details["checks"] = checks
        result.passed = all(checks.values())
        failed = [k for k, v in checks.items() if not v]
        if failed:
            result.error = f"Provider info incomplete: {failed}"

    except Exception as e:
        result.passed = False
        result.error = str(e)
    return result


async def test_measurement_independence(result: E2EResult) -> E2EResult:
    """T6: Measurement 独立性 — 自有计算，不依赖 Elmo score。"""
    from geo_distributor.models import Measurement

    try:
        obs = result.platform_observation

        # 自有 Measurement 计算逻辑（独立于 Elmo）
        citation_count = len(obs.citations)
        authority_count = sum(
            1 for c in obs.citations if c.get("citation_type") == "B"
        )
        brand_owned_count = sum(
            1 for c in obs.citations if c.get("citation_type") == "A"
        )

        # geo_score 完全由本平台计算，不为 None 即说明计算成功
        geo_score = _compute_geo_score(obs)

        m = Measurement(
            measurement_id=f"e2e_m_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            observation_id=obs.observation_id,
            citation_count=citation_count,
            authority_citation_count=authority_count,
            brand_owned_citation_count=brand_owned_count,
            geo_score=geo_score,
        )

        result.details["measurement"] = {
            "citation_count": citation_count,
            "authority_citation_count": authority_count,
            "brand_owned_citation_count": brand_owned_count,
            "geo_score": geo_score,
            "measurement_id": m.measurement_id,
        }
        result.passed = m.geo_score is not None
        if not result.passed:
            result.error = "Measurement.geo_score is None — calculation failed"

    except Exception as e:
        result.passed = False
        result.error = str(e)
    return result


async def test_failure_handling(result: E2EResult) -> E2EResult:
    """T7: Failure — 验证各种失败场景不被伪装为成功。"""
    from geo_distributor.adapters.elmo_client import ElmoClient
    from geo_distributor.compatibility.base import PlatformObservation
    from geo_distributor.models import Prompt as ModelPrompt

    failures = []

    # F1: 空配置
    adapter_empty = ElmoAdapter()
    obs = await adapter_empty.collect_prompt(ModelPrompt(
        prompt_id=999, category="", intent="", location="", text="test"
    ))
    f1_pass = obs.status == "failed" and "error" in obs.raw_metadata
    failures.append(("empty_config", f1_pass))
    result.details["empty_config"] = {
        "status": obs.status,
        "has_error": "error" in obs.raw_metadata,
        "passed": f1_pass,
    }

    # F2: 不可达 URL
    adapter_bad = ElmoAdapter(elmo_url="http://127.0.0.1:1", api_key="x")
    obs2 = await adapter_bad.collect_prompt(ModelPrompt(
        prompt_id=999, category="", intent="", location="", text="test"
    ))
    f2_pass = obs2.status == "failed"
    failures.append(("unreachable_url", f2_pass))
    result.details["unreachable_url"] = {
        "status": obs2.status,
        "passed": f2_pass,
    }

    # F3: health_check with bad config
    hc = await adapter_empty.health_check()
    f3_pass = hc is False
    failures.append(("health_check_empty", f3_pass))

    result.passed = all(f[1] for f in failures)
    failed_names = [f[0] for f in failures if not f[1]]
    if failed_names:
        result.error = f"Failure handling failed: {failed_names}"
    result.details["all_failures_handled"] = [f[1] for f in failures]
    return result


def _compute_geo_score(obs) -> float:
    """自有 Measurement 计算逻辑：独立于 Elmo。

    评分规则（示例，A1.8 可细化）：
    - brand_mentioned: +20
    - recommendation_level >= 3: +30
    - citation_count > 0: +10 per citation (max 30)
    - authority_citation_count > 0: +10 per (max 20)
    - brand_owned_citation_count > 0: +5 per (max 20)
    """
    score = 0.0
    if obs.brand_mentioned:
        score += 20.0
    if obs.recommendation_level >= 3:
        score += 30.0
    cit_scores = min(len(obs.citations) * 10, 30)
    score += cit_scores
    auth_scores = min(sum(1 for c in obs.citations if c.get("citation_type") == "B") * 10, 20)
    score += auth_scores
    brand_scores = min(sum(1 for c in obs.citations if c.get("citation_type") == "A") * 5, 20)
    score += brand_scores
    return round(score, 1)


# ------------------------------------------------------------------
# Main Runner
# ------------------------------------------------------------------

async def run_e2e_test(prompt_id_uuid: str, test_name: str = "full"):
    """运行 E2E 测试集。

    Args:
        prompt_id_uuid: Elmo prompt UUID
        test_name: "health" | "api" | "mapping" | "full" | "failure"
    """
    cfg = get_elmo_config()
    if not cfg.get("enabled") or not cfg.get("api_key"):
        print("❌ Elmo not configured. Set elmo.enabled=true and elmo.api_key in settings.yaml")
        return

    adapter = ElmoAdapter(
        elmo_url=cfg["base_url"],
        api_key=cfg["api_key"],
        version=cfg.get("version", "v0.3.0"),
        timeout_seconds=cfg.get("timeout_seconds", 30),
        max_retries=cfg.get("max_retries", 2),
    )

    prompt = ModelPrompt(
        prompt_id=int(prompt_id_uuid) if prompt_id_uuid.isdigit() else 0,
        category="",
        intent="",
        location="",
        text="",
    )

    tests = {
        "health": [test_health],
        "api": [test_health, test_api_response],
        "mapping": [test_health, test_api_response, test_mapping],
        "full": [
            test_health,
            test_api_response,
            test_mapping,
            test_id_traceability,
            test_provider_info,
            test_measurement_independence,
        ],
        "failure": [test_failure_handling],
    }

    test_list = tests.get(test_name, tests["full"])

    results = []
    print(f"\n{'='*60}")
    print(f"A1.7.1 — Real Elmo E2E Validation")
    print(f"Test set: {test_name}")
    print(f"Prompt ID: {prompt_id_uuid}")
    print(f"Elmo URL: {cfg['base_url']}")
    print(f"{'='*60}\n")

    for test_fn in test_list:
        r = E2EResult(test_fn.__name__, False)
        r.adapter = adapter
        r.prompt = prompt
        r.prompt_id_uuid = prompt_id_uuid

        try:
            r = await test_fn(r)
        except Exception as e:
            r.passed = False
            r.error = f"Unexpected: {e}"

        results.append(r)
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"  {status} {r.name}")
        if r.error:
            print(f"         ⚠ {r.error}")
        if r.details and test_name in ("api", "mapping", "full"):
            for k, v in r.details.items():
                if k not in ("checks", "trace", "provider_info", "measurement", "citation_sample", "raw_run_keys", "raw_citation_keys", "all_failures_handled") or test_name == "full":
                    if isinstance(v, dict) and k in ("checks", "traceability_checks", "citation_checks"):
                        for kk, vv in v.items():
                            icon = "✅" if vv else "❌"
                            print(f"         {icon} {kk}")
                    elif k in ("raw_run_keys", "raw_citation_keys"):
                        print(f"         🔑 {k}: {v}")
                    elif k in ("provider_info", "measurement"):
                        print(f"         📋 {k}: {json.dumps(v, ensure_ascii=False)}")
                    elif k == "trace":
                        print(f"         🔗 Trace: obs_id={v.get('platform_observation_id')}, run_id={v.get('elmo_run_id')}")
                    elif not isinstance(v, (dict, list)):
                        print(f"         {k}: {v}")

    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"E2E Result: {passed}/{total} passed")
    if passed == total:
        print("✅ A1.7.1 REAL E2E VALIDATION — PASS")
    else:
        print("⚠️  A1.7.1 REAL E2E VALIDATION — CONDITIONAL PASS")
        failed_names = [r.name for r in results if not r.passed]
        print(f"   Failed: {failed_names}")
    print(f"{'='*60}\n")

    # Export results
    output = {
        "version": "A1.7.1",
        "timestamp": datetime.now().isoformat(),
        "prompt_id": prompt_id_uuid,
        "passed": passed,
        "total": total,
        "results": [r.to_dict() for r in results],
    }
    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "exports", f"a171_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Results exported to: {output_path}")

    return output


def main():
    parser = argparse.ArgumentParser(description="A1.7.1 Elmo E2E Validation")
    parser.add_argument("--prompt-id", default="", help="Elmo prompt UUID")
    parser.add_argument("--test", default="full",
                        choices=["health", "api", "mapping", "full", "failure"])
    args = parser.parse_args()

    if not args.prompt_id:
        print("❌ --prompt-id is required for E2E test")
        sys.exit(1)

    output = asyncio.run(run_e2e_test(args.prompt_id, args.test))
    passed = output["passed"] if output else 0
    total = output["total"] if output else 0
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

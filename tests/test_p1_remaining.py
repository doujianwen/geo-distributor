"""P1 剩余项回归测试。

锁定四组改动，防止静默回退：
  A. 竞品分析服务（有数据产出 / 无数据诚实标注 / 字段兼容）
  B. API Key 环境变量化（${ENV_VAR} 展开 + 硬编码扫描 + get_secret 优先级）
  C. DistributionService 真实实现（引用完整性 / Run / Report / prompts 加载）
  D. /measurements 响应保留 competitors（下游阶段 2 依赖，曾被 pydantic 静默丢弃）
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.services.competitive_analysis import (  # noqa: E402
    analyze_competitors,
    _normalize_competitors,
)
from geo_distributor.services.distribution import (  # noqa: E402
    DistributionService,
    DistributionError,
)
import geo_distributor.config as config  # noqa: E402


# ==================================================================
# A. 竞品分析服务
# ==================================================================


def _obs(competitors, mentioned=True, level=0, engine="chatgpt"):
    """构造一条最小观测（dict 形态，与 API 返回一致）。"""
    return {
        "observation_id": f"obs-{id(competitors)}-{engine}",
        "prompt_text": "test query",
        "engine": engine,
        "brand_mentioned": mentioned,
        "brand_status": "mentioned" if mentioned else "absent",
        "recommendation_level": level,
        "citations_status": "none",
        "timestamp": "2026-09-18T00:00:00",
        "competitors": competitors,
    }


def test_normalize_competitors_accepts_three_shapes():
    """字段形态兼容：list[dict]/list[str]/JSON 字符串。"""
    # dict with brand
    assert _normalize_competitors([{"brand": "brita", "position": 2}]) == [
        {"brand": "brita", "position": 2}
    ]
    # dict with name（geo_collector_db 映射后用的是 name）
    assert _normalize_competitors([{"name": "ispring", "position": 7}]) == [
        {"brand": "ispring", "position": 7}
    ]
    # 纯字符串列表
    assert _normalize_competitors(["pur", "aquasana"]) == [
        {"brand": "pur", "position": None},
        {"brand": "aquasana", "position": None},
    ]
    # JSON 字符串
    assert _normalize_competitors('[{"brand": "culligan", "position": 3}]') == [
        {"brand": "culligan", "position": 3}
    ]
    # 空值
    assert _normalize_competitors(None) == []
    assert _normalize_competitors([]) == []
    assert _normalize_competitors("") == []

    # 非 JSON 的裸字符串：按"单个竞品名"处理（而非丢弃）
    assert _normalize_competitors("not-json") == [
        {"brand": "not-json", "position": None}
    ]

    # JSON 数组字符串但内容非法 → 解析失败返回 []
    assert _normalize_competitors("[not valid json]") == []


def test_competitive_analysis_with_data():
    """有竞品数据时应识别竞品、算出 SOV、生成差距结论。"""
    observations = [
        _obs([{"brand": "brita", "position": 2}]),
        _obs([{"brand": "brita", "position": 3}]),
        _obs([{"brand": "pur", "position": 5}]),
        _obs([]),  # 无竞品的观测也应计入分母
    ]
    r = analyze_competitors(observations, brand="Hydroviv", project_id="P1")

    assert r.has_data is True
    assert r.total_observations == 4
    assert r.observations_with_competitors == 3
    assert len(r.competitors) == 2

    top = r.top_competitor
    assert top.brand == "brita"
    assert top.mention_count == 2
    assert top.mention_rate == 50.0          # 2/4
    assert top.share_of_voice == pytest.approx(66.67, abs=0.01)  # 2/3
    assert top.avg_position == 2.5

    # 本品牌提及率 100% > 竞品 50%，不应生成"竞品压制"结论
    assert r.brand_mention_rate == 100.0
    assert all(f.category.value != "competitive_disadvantage" or "高于本品牌" not in f.statement
               for f in r.findings)


def test_competitive_analysis_no_data_is_honest():
    """无竞品字段时：has_data=False、零竞品、零 finding、给出原因。

    这是红线——绝不能因为没有数据就编一份竞品名单出来。
    """
    observations = [_obs([]), _obs([]), _obs([])]
    r = analyze_competitors(observations, brand="BookConv", case_id="bookconv")

    assert r.has_data is False
    assert r.competitors == []
    assert r.findings == []
    assert r.data_note != ""
    assert "competitors" in r.data_note or "竞品" in r.data_note


def test_competitive_analysis_excludes_own_brand():
    """竞品名单里不应出现本品牌自己。"""
    observations = [
        _obs([{"brand": "Hydroviv", "position": 1}]),
        _obs([{"brand": "brita", "position": 2}]),
    ]
    r = analyze_competitors(observations, brand="Hydroviv")
    brands = [c.brand.lower() for c in r.competitors]
    assert "hydroviv" not in brands
    assert brands == ["brita"]


def test_competitive_analysis_flags_zero_mention_brand():
    """本品牌零提及且竞品有提及 → CRITICAL 结论。"""
    observations = [
        _obs([{"brand": "brita", "position": 2}], mentioned=False),
        _obs([{"brand": "brita", "position": 2}], mentioned=False),
    ]
    r = analyze_competitors(observations, brand="NewBrand")
    assert r.has_data is True
    assert r.brand_mention_rate == 0.0
    assert any(f.severity.value == "critical" for f in r.findings)


def test_competitive_analysis_result_serializable():
    r = analyze_competitors(
        [_obs([{"brand": "brita", "position": 2}])], brand="H", project_id="P"
    )
    d = r.to_dict()
    json.dumps(d)  # 必须可序列化
    assert "has_data" in d and "competitors" in d


# ==================================================================
# B. API Key 环境变量化
# ==================================================================


def test_env_placeholder_expansion(monkeypatch):
    monkeypatch.setenv("MY_TEST_KEY", "value-from-env")
    node = {"a": "${MY_TEST_KEY}", "b": {"c": "prefix-${MY_TEST_KEY}"}, "d": "plain"}
    out = config._expand_env(node)
    assert out["a"] == "value-from-env"
    assert out["b"]["c"] == "prefix-value-from-env"
    assert out["d"] == "plain"


def test_env_placeholder_missing_expands_empty(monkeypatch):
    monkeypatch.delenv("DEFINITELY_UNSET_KEY", raising=False)
    assert config._expand_env({"k": "${DEFINITELY_UNSET_KEY}"})["k"] == ""


def test_scan_hardcoded_secrets_detects():
    bad = {"elmo": {"api_key": "5vGAUQo58wjhLiXp43bV3lvgIhF/AnIk6WxtREjevn4="}}
    hits = config.scan_hardcoded_secrets(bad)
    assert len(hits) == 1
    assert "elmo.api_key" in hits[0][0]


def test_scan_hardcoded_secrets_ignores_benign():
    """路径/URL/版本号等长字符串不应误报。"""
    ok = {
        "elmo": {"base_url": "http://localhost:1515", "api_key": "${ELMO_API_KEY}"},
        "output_root": "/some/long/absolute/path/to/output",
        "version": "v0.3.0",
    }
    assert config.scan_hardcoded_secrets(ok) == []


def test_get_secret_env_priority(monkeypatch):
    """环境变量优先于配置文件。"""
    monkeypatch.setenv("ELMO_API_KEY", "from-env")
    settings = {"elmo": {"api_key": "from-config"}}
    assert config.get_secret(settings, "elmo", "api_key", env_var="ELMO_API_KEY") == "from-env"

    monkeypatch.delenv("ELMO_API_KEY", raising=False)
    assert config.get_secret(settings, "elmo", "api_key", env_var="ELMO_API_KEY") == "from-config"


def test_committed_settings_has_no_hardcoded_key():
    """仓库内的 settings.yaml 不得含硬编码密钥。"""
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "settings.yaml",
    )
    if not os.path.exists(settings_path):
        pytest.skip("settings.yaml not found")
    import yaml
    with open(settings_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    # 扫描原始（未展开）配置：占位符不算密钥
    assert config.scan_hardcoded_secrets(raw) == []


# ==================================================================
# C. DistributionService
# ==================================================================


class _FakeAdapter:
    """最小 adapter 桩：只实现 BaseAdapter 真实契约。"""

    def __init__(self, n=3):
        self.n = n

    async def health_check(self):
        return True

    async def collect_prompt(self, prompt):
        from geo_distributor.compatibility.base import PlatformObservation
        mentioned = (prompt.prompt_id % 2 == 0)
        return PlatformObservation(
            observation_id=f"obs-{prompt.prompt_id}",
            prompt_id=prompt.prompt_id,
            engine="fake",
            timestamp="2026-09-18T00:00:00",
            prompt_text=prompt.text,
            answer_raw="raw",
            answer_clean="clean",
            answer_char_count=5,
            extraction_method="fake",
            validation_status="PASS",
            brand="FakeBrand",
            brand_mentioned=mentioned,
            brand_status="MENTIONED" if mentioned else "NOT_MENTIONED",
            first_mention_position=1 if mentioned else None,
            recommendation_level=2 if mentioned else 0,
            recommendation_rank=1 if mentioned else None,
            recommendation_evidence="fake",
            competitors=[],
            citations=[],
            citations_status="unavailable",
            status="success",
        )

    async def collect_batch(self, prompts, progress_callback=None):
        out = []
        for p in prompts:
            if progress_callback:
                progress_callback(1, len(prompts))
            out.append(await self.collect_prompt(p))
        return out


def _write_prompts(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_distribution_full_lifecycle():
    async def main():
        svc = DistributionService(adapter=_FakeAdapter())
        org = await svc.create_organization("Acme", "a@b.com")
        assert org.org_id.startswith("ORG-")

        brand = await svc.create_brand(org.org_id, "AcmeBrand", aliases=["ACME"])
        assert brand.brand_id.startswith("BRAND-")

        pfile = _write_prompts(json.dumps([
            {"prompt_id": 1, "text": "q1", "category": "c", "intent": "i", "location": "US"},
            {"prompt_id": 2, "text": "q2", "category": "c", "intent": "i", "location": "US"},
            {"prompt_id": 3, "text": "q3", "category": "c", "intent": "i", "location": "US"},
        ]))
        proj = await svc.create_project(
            org.org_id, brand.brand_id, "P1", prompts_file=pfile, engines=["fake"]
        )
        assert proj.status.value == "draft"

        run = await svc.run_project(proj)
        assert run.status == "completed"
        assert run.total_prompts == 3
        assert run.successful == 3
        assert run.failed == 0

        rep = await svc.generate_report_for_run(run)
        assert rep.total_observations == 3
        assert rep.brand_mentioned_count == 1   # prompt_id 2 为偶数
        assert rep.summary["mention_rate"] == pytest.approx(33.33, abs=0.01)

        os.unlink(pfile)
        return svc

    asyncio.run(main())


def test_distribution_reference_integrity():
    """跨 org 引用、不存在的 org/brand 必须报错，不能静默建脏数据。"""
    async def main():
        svc = DistributionService(adapter=_FakeAdapter())
        org = await svc.create_organization("A")
        brand = await svc.create_brand(org.org_id, "B")

        with pytest.raises(DistributionError):
            await svc.create_brand("NOPE", "B")
        with pytest.raises(DistributionError):
            await svc.create_project(org.org_id, "NOPE", "P", prompts_file="x")
        with pytest.raises(DistributionError):
            await svc.create_organization("")   # 空名

        # brand 属于别的 org
        other = await svc.create_organization("Other")
        with pytest.raises(DistributionError):
            await svc.create_project(other.org_id, brand.brand_id, "P", prompts_file="x")

    asyncio.run(main())


def test_distribution_run_requires_prompts():
    async def main():
        svc = DistributionService(adapter=_FakeAdapter())
        org = await svc.create_organization("A")
        brand = await svc.create_brand(org.org_id, "B")
        proj = await svc.create_project(org.org_id, brand.brand_id, "P", prompts_file="")
        with pytest.raises(DistributionError):
            await svc.run_project(proj)

        pfile = _write_prompts("")   # 空文件
        proj2 = await svc.create_project(org.org_id, brand.brand_id, "P2", prompts_file=pfile)
        with pytest.raises(DistributionError):
            await svc.run_project(proj2)
        os.unlink(pfile)

    asyncio.run(main())


def test_load_prompts_three_formats():
    # JSON array
    p1 = _write_prompts(json.dumps([{"prompt_id": 1, "text": "q1"}]))
    assert len(DistributionService.load_prompts(p1)) == 1
    os.unlink(p1)

    # JSONL
    p2 = _write_prompts('{"prompt_id":1,"text":"q1"}\n{"prompt_id":2,"text":"q2"}\n')
    assert len(DistributionService.load_prompts(p2)) == 2
    os.unlink(p2)

    # 纯文本
    p3 = _write_prompts("q1\nq2\nq3\n")
    loaded = DistributionService.load_prompts(p3)
    assert len(loaded) == 3 and loaded[0].text == "q1"
    os.unlink(p3)

    # 不存在的文件 → 空列表（由调用方报错）
    assert DistributionService.load_prompts("/definitely/not/here.json") == []


def test_report_zero_observations_notes_denominator():
    """无观测时比率应为 0 且给出说明，不能除零、不能编造。"""
    async def main():
        svc = DistributionService(adapter=_FakeAdapter())
        from geo_distributor.models import Run
        run = Run(run_id="RUN-X", project_id="P", started_at="now", status="failed")
        rep = await svc.generate_report_for_run(run)
        assert rep.total_observations == 0
        assert rep.summary["mention_rate"] == 0.0
        assert rep.summary["note"] != ""

    asyncio.run(main())


# ==================================================================
# D. /measurements 响应保留 competitors
# ==================================================================


def test_measurement_response_keeps_competitors():
    """API 响应必须带 competitors——阶段 2 竞品分析依赖，曾被静默丢弃。"""
    from fastapi.testclient import TestClient
    from api.app import app

    with TestClient(app) as c:
        r = c.post("/clients", json={"name": "CA", "industry": "x"},
                   headers={"X-Tenant-ID": "T-CA"})
        assert r.status_code == 201
        cid = r.json()["client_id"]

        r = c.post("/projects", json={
            "tenant_id": "T-CA", "client_id": cid, "service": "visibility_audit",
            "target_market": ["US"], "business_question": "q",
        }, headers={"X-Tenant-ID": "T-CA"})
        assert r.status_code == 201
        pid = r.json()["project_id"]

        r = c.post("/measurements", json={
            "project_id": pid, "case_id": "bookconv",
            "adapter": "opengeo", "tenant_id": "T-CA",
        }, headers={"X-Tenant-ID": "T-CA"})
        assert r.status_code == 201
        body = r.json()

        # 字段必须存在（缺失即回归）
        assert "observations" in body
        for o in body["observations"]:
            assert "competitors" in o
            assert "citations" in o

        # 不得再把 42 条硬截断成 20 条
        assert len(body["observations"]) >= 1


def test_measurement_observation_limit_honored():
    from fastapi.testclient import TestClient
    from api.app import app

    with TestClient(app) as c:
        r = c.post("/clients", json={"name": "CB", "industry": "x"},
                   headers={"X-Tenant-ID": "T-CB"})
        cid = r.json()["client_id"]
        r = c.post("/projects", json={
            "tenant_id": "T-CB", "client_id": cid, "service": "visibility_audit",
            "target_market": ["US"], "business_question": "q",
        }, headers={"X-Tenant-ID": "T-CB"})
        pid = r.json()["project_id"]

        r = c.post("/measurements", json={
            "project_id": pid, "case_id": "tjostrichink",
            "adapter": "opengeo", "tenant_id": "T-CB",
            "observation_limit": 5,
        }, headers={"X-Tenant-ID": "T-CB"})
        assert r.status_code == 201
        assert len(r.json()["observations"]) == 5


# ==================================================================
# E. /distribution 路由（平台层采集调度入口）
# ==================================================================


def test_distribution_routes_available():
    """调度服务必须有 HTTP 入口——否则实现等于不可达。"""
    from fastapi.testclient import TestClient
    from api.app import app

    with TestClient(app) as c:
        h = c.get("/health").json()
        assert "distribution_service" in h

        if not h["distribution_service"]:
            pytest.skip(f"distribution service unavailable: {h.get('distribution_service_error')}")

        r = c.post("/distribution/orgs", json={"name": "RouteOrg", "contact_email": "r@o.com"})
        assert r.status_code == 201
        oid = r.json()["org_id"]

        r = c.post("/distribution/brands", json={"org_id": oid, "name": "RouteBrand"})
        assert r.status_code == 201
        bid = r.json()["brand_id"]

        r = c.post("/distribution/projects", json={
            "org_id": oid, "brand_id": bid, "name": "P",
            "prompts_file": "config/prompts_hydroviv.json",
        })
        assert r.status_code == 201
        pid = r.json()["project_id"]

        r = c.post(f"/distribution/projects/{pid}/run")
        assert r.status_code == 201
        run = r.json()
        assert run["total_prompts"] == 10
        # 未采集的占位观测不得被计成失败
        assert run["failed"] == 0

        r = c.post(f"/distribution/runs/{run['run_id']}/report")
        assert r.status_code == 201
        rep = r.json()
        assert "mention_rate" in rep["summary"]
        assert "uncollected" in rep["summary"]

        # 引用完整性错误应返回 400 而非 500
        assert c.post("/distribution/brands", json={"org_id": "NOPE", "name": "x"}).status_code == 400
        assert c.post("/distribution/projects/NOPE/run").status_code == 404


def test_distribution_run_not_collected_is_not_failure():
    """status=not_collected 属"未采集"，应计入 skipped 而非 failed。"""
    from geo_distributor.services.distribution import DistributionService

    class _UncollectedAdapter(_FakeAdapter):
        async def collect_prompt(self, prompt):
            obs = await super().collect_prompt(prompt)
            obs.status = "not_collected"
            obs.brand_mentioned = False
            return obs

    async def main():
        svc = DistributionService(adapter=_UncollectedAdapter())
        org = await svc.create_organization("A")
        brand = await svc.create_brand(org.org_id, "B")
        pfile = _write_prompts(json.dumps([{"prompt_id": 1, "text": "q1"}]))
        proj = await svc.create_project(org.org_id, brand.brand_id, "P", prompts_file=pfile)
        run = await svc.run_project(proj)
        os.unlink(pfile)

        assert run.failed == 0
        assert run.skipped == 1
        assert run.successful == 0

        # 报告不得拿未采集的占位观测充当分母去算"提及率 0%"
        rep = await svc.generate_report_for_run(run)
        assert rep.total_observations == 0
        assert rep.summary["mention_rate"] == 0.0
        assert rep.summary["uncollected"] == 1
        assert rep.summary["note"] != ""

    asyncio.run(main())

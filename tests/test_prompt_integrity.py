"""Prompt 编号 / 文本一致性回归测试。

背景（真实缺陷）：
    DistributionService 走 GeoCollectorDBAdapter 采集，适配器只按
    prompt_id 查库。config/prompts_hydroviv.json 原先用了自建编号
    （prompt_id 1-10 对应 "best water filter for home" 之类），而数据源
    里 prompt_id 1-10 是完全不同的问题。结果 Run 显示 10/10 采集成功，
    报告的 mention_rate 衡量的却是另一批 prompt 的数据——
    "能力接通了，数字是假的"。

本文件锁定三层防御：
    L1 适配器：ID 命中但文本对不上 → 返回 prompt_mismatch，绝不返回错配数据
    L2 服务层：prompt_mismatch 单独记账，计入 skipped 而非 successful
    L3 报告层：分母为 0 时说明"为什么"，不给出一个看起来正常的 0%
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.adapters.geo_collector_db import (  # noqa: E402
    GeoCollectorDBAdapter,
    _normalize_prompt_text,
)
from geo_distributor.models import Prompt  # noqa: E402
from geo_distributor.services.distribution import (  # noqa: E402
    DistributionService,
    DistributionError,
)


OBS_COLUMNS = """
    observation_id TEXT, prompt_id INTEGER, engine TEXT, timestamp TEXT,
    prompt_text TEXT, answer_raw TEXT, answer_clean TEXT, answer_char_count INTEGER,
    answer_extraction_method TEXT, answer_validation_status TEXT, brand TEXT,
    brand_mentioned INTEGER, brand_status TEXT, first_mention_position INTEGER,
    recommendation_level INTEGER, recommendation_rank INTEGER,
    recommendation_evidence TEXT, competitors TEXT, citations_status TEXT,
    status TEXT, parser_version TEXT, response_state TEXT,
    recommendation_level_v2 INTEGER, recommendation_rank_v2 INTEGER,
    first_mention_position_v2 INTEGER, brand_mentioned_v2 INTEGER
"""


def _make_db(path: str, db_prompt_text: str = "What water filter should I buy?") -> str:
    """建一个最小可查的 geo-collector 形态数据库。"""
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE prompts (prompt_id INTEGER, prompt_text TEXT, category TEXT, intent TEXT, location TEXT)")
    cur.execute(f"CREATE TABLE observations ({OBS_COLUMNS})")
    cur.execute(
        "CREATE TABLE citations (observation_id TEXT, url TEXT, domain TEXT, "
        "title TEXT, citation_index INTEGER, citation_type TEXT, anchor_text TEXT, context TEXT)"
    )
    cur.execute("CREATE TABLE competitors (observation_id TEXT, brand TEXT, position INTEGER)")
    cur.execute(
        "INSERT INTO prompts VALUES (?, ?, '', 'recommendation', 'US')",
        (1, db_prompt_text),
    )
    cur.execute(
        """INSERT INTO observations
           (observation_id, prompt_id, engine, timestamp, prompt_text, answer_clean,
            answer_char_count, brand, brand_mentioned, brand_status,
            recommendation_level, competitors, citations_status, status)
           VALUES ('OBS-1', 1, 'chatgpt', '2026-09-18T00:00:00', ?, 'Hydroviv is good',
                   100, 'Hydroviv', 1, 'MENTIONED', 2, ?, 'extracted', 'success')""",
        (db_prompt_text, json.dumps([{"brand": "Brita", "position": 1}])),
    )
    cur.execute(
        "INSERT INTO competitors VALUES ('OBS-1', 'Brita', 1)"
    )
    conn.commit()
    conn.close()
    return path


def run(coro):
    return asyncio.run(coro)


# ==================================================================
# L0. 文本归一化
# ==================================================================


def test_normalize_ignores_case_whitespace_and_trailing_punct():
    assert _normalize_prompt_text("  Best   Water Filter?  ") == _normalize_prompt_text("best water filter")
    assert _normalize_prompt_text("Best Water Filter.") == _normalize_prompt_text("best water filter")


# ==================================================================
# L1. 适配器：错配拒绝返回
# ==================================================================


def test_adapter_returns_data_when_text_matches():
    with tempfile.TemporaryDirectory() as d:
        db = _make_db(os.path.join(d, "t.db"), db_prompt_text="What water filter should I buy?")
        adapter = GeoCollectorDBAdapter(db_path=db, brand="Hydroviv")
        p = Prompt(prompt_id=1, text="What water filter should I buy?", category="", intent="", location="")
        obs = run(adapter.collect_prompt(p))
        assert obs.status == "success"
        assert obs.brand_mentioned is True
        assert obs.competitors == [{"name": "Brita", "position": 1}]


def test_adapter_refuses_mismatched_prompt():
    """ID 命中但文本对不上 → prompt_mismatch，不返回别的问题的答案。"""
    with tempfile.TemporaryDirectory() as d:
        db = _make_db(os.path.join(d, "t.db"), db_prompt_text="What water filter should I buy?")
        adapter = GeoCollectorDBAdapter(db_path=db, brand="Hydroviv")
        # 编号 1 在调用方这里代表完全不同的问题
        p = Prompt(prompt_id=1, text="best water filter for home", category="", intent="", location="")
        obs = run(adapter.collect_prompt(p))
        assert obs.status == "prompt_mismatch"
        assert obs.brand_status == "PROMPT_MISMATCH"
        # 关键：没有把库里的答案 / 提及状态带出来
        assert obs.brand_mentioned is False
        assert obs.answer_clean == ""
        assert obs.competitors == []
        assert obs.raw_metadata["db_text"].startswith("What water filter")


def test_adapter_mismatch_tolerates_punctuation_diff():
    """句末标点 / 大小写差异不应误判为错配。"""
    with tempfile.TemporaryDirectory() as d:
        db = _make_db(os.path.join(d, "t.db"), db_prompt_text="What water filter should I buy?")
        adapter = GeoCollectorDBAdapter(db_path=db, brand="Hydroviv")
        p = Prompt(prompt_id=1, text="what water filter should I buy", category="", intent="", location="")
        obs = run(adapter.collect_prompt(p))
        assert obs.status == "success"


def test_adapter_strict_flag_can_disable_check():
    """strict_prompt_match=False 保留旧行为（向后兼容，需显式开启）。"""
    with tempfile.TemporaryDirectory() as d:
        db = _make_db(os.path.join(d, "t.db"), db_prompt_text="What water filter should I buy?")
        adapter = GeoCollectorDBAdapter(db_path=db, brand="Hydroviv", strict_prompt_match=False)
        p = Prompt(prompt_id=1, text="best water filter for home", category="", intent="", location="")
        obs = run(adapter.collect_prompt(p))
        assert obs.status == "success"


# ==================================================================
# L2 / L3. 服务层记账与报告口径
# ==================================================================


def _service_with_prompts(tmpdir: str, prompts: list[dict], db_text: str):
    db = _make_db(os.path.join(tmpdir, "gc.db"), db_prompt_text=db_text)
    adapter = GeoCollectorDBAdapter(db_path=db, brand="Hydroviv")
    svc = DistributionService(adapter)
    path = os.path.join(tmpdir, "prompts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts, f)
    return svc, path


def test_run_marks_mismatch_as_skipped_not_successful():
    with tempfile.TemporaryDirectory() as d:
        svc, path = _service_with_prompts(
            d,
            [{"prompt_id": 1, "text": "best water filter for home", "category": "", "intent": "", "location": ""}],
            db_text="What water filter should I buy?",
        )
        org = run(svc.create_organization("Org", "o@e.com"))
        brand = run(svc.create_brand(org.org_id, "Hydroviv"))
        proj = run(svc.create_project(org.org_id, brand.brand_id, "P", prompts_file=path))

        r = run(svc.run_project(proj))
        assert r.total_prompts == 1
        assert r.successful == 0, "错配 prompt 绝不能计入成功采集"
        assert r.failed == 0, "错配不是采集失败，是编号对不上"
        assert r.skipped == 1
        assert r.prompt_mismatch == 1
        assert "prompt_id" in r.error_summary


def test_report_explains_zero_denominator_when_all_mismatched():
    with tempfile.TemporaryDirectory() as d:
        svc, path = _service_with_prompts(
            d,
            [{"prompt_id": 1, "text": "best water filter for home", "category": "", "intent": "", "location": ""}],
            db_text="What water filter should I buy?",
        )
        org = run(svc.create_organization("Org", "o@e.com"))
        brand = run(svc.create_brand(org.org_id, "Hydroviv"))
        proj = run(svc.create_project(org.org_id, brand.brand_id, "P", prompts_file=path))
        r = run(svc.run_project(proj))
        rep = run(svc.generate_report_for_run(r))

        assert rep.total_observations == 0
        assert rep.summary["mention_rate"] == 0.0
        assert rep.summary["prompt_mismatch"] == 1
        # 不能只给一个 0% 就完事，必须说清为什么
        assert "错配" in rep.summary["note"] or "prompt_id" in rep.summary["note"]


def test_run_succeeds_when_prompts_are_aligned():
    """对齐编号后，端到端应拿到真实数据（防止修复把正常路径也堵死）。"""
    with tempfile.TemporaryDirectory() as d:
        svc, path = _service_with_prompts(
            d,
            [{"prompt_id": 1, "text": "What water filter should I buy?", "category": "", "intent": "", "location": ""}],
            db_text="What water filter should I buy?",
        )
        org = run(svc.create_organization("Org", "o@e.com"))
        brand = run(svc.create_brand(org.org_id, "Hydroviv"))
        proj = run(svc.create_project(org.org_id, brand.brand_id, "P", prompts_file=path))
        r = run(svc.run_project(proj))

        assert r.successful == 1
        assert r.prompt_mismatch == 0
        rep = run(svc.generate_report_for_run(r))
        assert rep.total_observations == 1
        assert rep.summary["mention_rate"] == 100.0


# ==================================================================
# L4. 真实配置守卫：prompts 文件必须与数据源同套编号
# ==================================================================


def test_shipped_prompts_file_matches_live_datasource():
    """config/prompts_hydroviv.json 的 prompt_id/text 必须与 geo-collector 一致。

    数据源不可用时跳过（不造数据，不假装通过）。
    """
    try:
        from geo_distributor.config import get_geo_collector_root
    except Exception:
        pytest.skip("geo_distributor.config 不可用")

    db_path = os.path.join(get_geo_collector_root(), "geo_collector.db")
    cfg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "prompts_hydroviv.json",
    )
    if not (os.path.exists(db_path) and os.path.exists(cfg)):
        pytest.skip("geo-collector.db 或 prompts 文件不存在")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db_texts = {
        r["prompt_id"]: r["prompt_text"]
        for r in conn.execute("SELECT prompt_id, prompt_text FROM prompts")
    }
    conn.close()

    with open(cfg, encoding="utf-8") as f:
        prompts = json.load(f)
    assert prompts, "prompts 文件为空"

    for p in prompts:
        pid, text = p.get("prompt_id"), p.get("text", "")
        assert pid in db_texts, f"prompt_id={pid} 在数据源中不存在"
        assert _normalize_prompt_text(db_texts[pid]) == _normalize_prompt_text(text), (
            f"prompt_id={pid} 文本与数据源不一致：\n"
            f"  文件: {text}\n"
            f"  数据源: {db_texts[pid]}"
        )

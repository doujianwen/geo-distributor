"""OpenGeoAdapter 测试（Sprint 4 §11 / §13 Engineering）。"""

import json
import tempfile
import os

import pytest

from geo_distributor.adapters.opengeo import OpenGeoAdapter
from geo_distributor.compatibility.base import PlatformObservation
from geo_distributor.compatibility.opengeo import (
    map_bing_ai_performance_row,
    map_gsc_row,
)


def _make_obs(query: str, mentioned: bool) -> PlatformObservation:
    return PlatformObservation(
        observation_id=f"obs_{query}",
        prompt_id=1,
        engine="bing_ai",
        timestamp="2026-09-14",
        prompt_text=query,
        answer_raw="",
        answer_clean="",
        answer_char_count=0,
        extraction_method="test",
        validation_status="PASS",
        brand="BookConv",
        brand_mentioned=mentioned,
        brand_status="MENTIONED" if mentioned else "NOT_MENTIONED",
        first_mention_position=None,
        recommendation_level=3 if mentioned else 0,
        recommendation_rank=None,
        recommendation_evidence="",
        competitors=[],
        citations=[],
        citations_status="extracted" if mentioned else "none",
        status="success",
    )


@pytest.mark.asyncio
async def test_from_observations_and_health():
    adapter = OpenGeoAdapter.from_observations([_make_obs("convert epub to pdf", True)])
    assert await adapter.health_check()
    assert len(adapter._observations) == 1


@pytest.mark.asyncio
async def test_collect_prompt_returns_matching():
    adapter = OpenGeoAdapter.from_observations([
        _make_obs("convert epub to pdf", True),
        _make_obs("best ebook converter", False),
    ])
    obs = await adapter.collect_prompt({"query": "convert epub to pdf"})
    assert obs.brand_mentioned is True
    assert obs.engine == "bing_ai"


@pytest.mark.asyncio
async def test_collect_prompt_missing_is_transparent_not_fabricated():
    adapter = OpenGeoAdapter.from_observations([_make_obs("convert epub to pdf", True)])
    obs = await adapter.collect_prompt({"query": "unknown query xyz"})
    assert obs.status == "not_collected"
    assert obs.brand_mentioned is False
    assert obs.brand_status == "NOT_COLLECTED"


@pytest.mark.asyncio
async def test_collect_batch_progress():
    calls = []
    adapter = OpenGeoAdapter.from_observations([_make_obs("a", True), _make_obs("b", False)])
    results = await adapter.collect_batch(
        [{"query": "a"}, {"query": "b"}], progress_callback=lambda c, t: calls.append((c, t))
    )
    assert len(results) == 2
    assert calls == [(1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_from_json_file(tmp_path):
    path = tmp_path / "obs.json"
    path.write_text(json.dumps([
        {"observation_id": "o1", "prompt_id": 1, "engine": "bing_ai", "timestamp": "",
         "prompt_text": "q1", "answer_raw": "", "answer_clean": "", "answer_char_count": 0,
         "extraction_method": "t", "validation_status": "PASS", "brand": "B", "brand_mentioned": True,
         "brand_status": "MENTIONED", "first_mention_position": None, "recommendation_level": 3,
         "recommendation_rank": None, "recommendation_evidence": "", "competitors": [], "citations": [],
         "citations_status": "extracted", "status": "success"}
    ]), encoding="utf-8")
    adapter = OpenGeoAdapter.from_json_file(str(path))
    assert await adapter.health_check()
    assert adapter._observations[0].prompt_text == "q1"


def test_map_bing_row_mentioned():
    obs = map_bing_ai_performance_row(
        {"query": "djvu to pdf", "cites": 250, "share": "3.97%"}, snapshot_date="2026-09-13"
    )
    assert obs.brand_mentioned is True
    assert obs.engine == "bing_ai"
    assert obs.raw_metadata["cites"] == 250
    # share < 10% → recommendation_level 1
    assert obs.recommendation_level == 1


def test_map_bing_row_high_share_proxy():
    obs = map_bing_ai_performance_row(
        {"query": "Harry Potter digital books multiple devices", "cites": 36, "share": "50.00%"}
    )
    # share >= 40% → recommendation_level 3 (proxy)
    assert obs.recommendation_level == 3
    assert "proxy" in obs.raw_metadata["note"]


def test_map_gsc_row_proxy():
    obs = map_gsc_row({"query": "ostrich ink", "impressions": 100, "clicks": 10, "position": 2.1})
    assert obs.brand_mentioned is True
    assert obs.engine == "google_search"
    assert obs.first_mention_position == 2

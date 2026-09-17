"""测试：Elmo → Platform 映射层（零网络依赖）。"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.compatibility.elmo import (
    map_elmo_citation_to_platform,
    map_elmo_to_platform,
    _uuid_to_int,
    _infer_citation_type,
)
from geo_distributor.compatibility.base import PlatformObservation


# ------------------------------------------------------------------
# Citation type inference
# ------------------------------------------------------------------

def test_map_elmo_citation_infer_type_brand():
    """品牌域名 → A 类。"""
    c = {"url": "https://hydroviv.com/product", "domain": "hydroviv.com", "title": "Product"}
    result = map_elmo_citation_to_platform(c, "obs_001", ["hydroviv.com"])
    assert result["citation_type"] == "A"
    assert result["url"] == "https://hydroviv.com/product"
    assert result["observation_id"] == "obs_001"


def test_map_elmo_citation_infer_type_gov():
    """.gov 域名 → B 类。"""
    c = {"url": "https://epa.gov/water", "domain": "epa.gov", "title": "EPA Guide"}
    result = map_elmo_citation_to_platform(c, "obs_001", ["hydroviv.com"])
    assert result["citation_type"] == "B"


def test_map_elmo_citation_infer_type_commercial():
    """普通商业域名 → E 类。"""
    c = {"url": "https://amazon.com/water-filter", "domain": "amazon.com", "title": "Amazon"}
    result = map_elmo_citation_to_platform(c, "obs_001", ["hydroviv.com"])
    assert result["citation_type"] == "E"


def test_map_elmo_citation_basic_mapping():
    """基本字段映射正确。"""
    c = {
        "url": "https://example.com",
        "domain": "example.com",
        "title": "Example Article",
        "citationIndex": 3,
        "anchorText": "click here",
        "context": "In this article...",
    }
    result = map_elmo_citation_to_platform(c, "obs_001", [])
    assert result["url"] == "https://example.com"
    assert result["title"] == "Example Article"
    assert result["citation_index"] == 3
    assert result["anchor_text"] == "click here"
    assert result["context"] == "In this article..."


# ------------------------------------------------------------------
# Full run mapping
# ------------------------------------------------------------------

def _make_elmo_run(**overrides):
    default = {
        "id": "run-uuid-001",
        "prompt_id": "prompt-uuid-001",
        "model": "gpt-4o",
        "created_at": "2026-09-10T10:00:00Z",
        "createdAt": "2026-09-10T10:00:00Z",
        "brandMentioned": True,
        "raw_output": {"text": "Full raw output"},
        "answer": {"text": "Hydroviv is the best choice."},
        "competitorsMentioned": ["Brita", "Aquasana"],
        "citations": [
            {"url": "https://hydroviv.com", "domain": "hydroviv.com", "title": "Brand Site", "citationIndex": 1},
            {"url": "https://epa.gov", "domain": "epa.gov", "title": "EPA", "citationIndex": 2},
        ],
        "webSearchEnabled": True,
    }
    default.update(overrides)
    return default


def test_map_elmo_to_platform_full():
    """完整 run → PlatformObservation 字段验证。"""
    run = _make_elmo_run()
    mapped = map_elmo_to_platform(
        elmo_run=run,
        elmo_citations=run["citations"],
        brand_name="Hydroviv",
        brand_domains=["hydroviv.com"],
        prompt_id_uuid="prompt-uuid-001",
        model_name="gpt-4o",
        elmo_version="v0.3.0",
    )

    obs = PlatformObservation(**mapped)
    assert isinstance(obs, PlatformObservation)
    assert obs.observation_id == "run-uuid-001"
    assert obs.engine == "gpt-4o"
    assert obs.brand == "Hydroviv"
    assert obs.brand_mentioned is True
    assert obs.brand_status == "MENTIONED"
    assert obs.answer_clean == "Hydroviv is the best choice."
    assert obs.answer_char_count > 0
    assert obs.extraction_method == "elmo_api"
    assert obs.status == "success"
    assert obs.validation_status == "PASS"
    assert len(obs.citations) == 2
    assert obs.citations[0]["citation_type"] == "A"
    assert obs.citations[1]["citation_type"] == "B"
    assert obs.citations_status == "extracted"
    assert len(obs.competitors) == 2


def test_map_elmo_to_platform_empty_citations():
    """空 citations → citations_status='unavailable'。"""
    run = _make_elmo_run(citations=[])
    mapped = map_elmo_to_platform(
        elmo_run=run,
        elmo_citations=[],
        brand_name="Hydroviv",
        brand_domains=["hydroviv.com"],
        prompt_id_uuid="prompt-uuid-001",
        model_name="gpt-4o",
        elmo_version="v0.3.0",
    )
    assert mapped["citations_status"] == "unavailable"
    assert mapped["citations"] == []


def test_map_elmo_to_platform_preserves_raw_metadata():
    """raw_metadata 包含 provider/version/elmo_version/original_prompt_id。"""
    run = _make_elmo_run()
    mapped = map_elmo_to_platform(
        elmo_run=run,
        elmo_citations=run["citations"],
        brand_name="Hydroviv",
        brand_domains=["hydroviv.com"],
        prompt_id_uuid="prompt-uuid-001",
        model_name="gpt-4o",
        elmo_version="v0.3.0",
    )
    rm = mapped["raw_metadata"]
    assert rm["provider"] == "elmo"
    assert rm["version"] == "v0.3.0"
    assert rm["elmo_version"] == "v0.3.0"
    assert rm["original_prompt_id"] == "prompt-uuid-001"
    assert rm["model"] == "gpt-4o"


def test_map_elmo_to_platform_missing_answer():
    """answer 为 null → 降级处理，status=failed。"""
    run = _make_elmo_run(answer=None, raw_output="")
    mapped = map_elmo_to_platform(
        elmo_run=run,
        elmo_citations=[],
        brand_name="Hydroviv",
        brand_domains=["hydroviv.com"],
        prompt_id_uuid="prompt-uuid-001",
        model_name="gpt-4o",
        elmo_version="v0.3.0",
    )
    assert mapped["answer_clean"] == ""
    assert mapped["status"] == "failed"
    assert mapped["validation_status"] == "FAIL"
    assert mapped["answer_char_count"] == 0


def test_map_elmo_to_platform_brand_not_mentioned():
    """brandMentioned=false → brand_status=NOT_MENTIONED。"""
    run = _make_elmo_run(brandMentioned=False)
    mapped = map_elmo_to_platform(
        elmo_run=run,
        elmo_citations=[],
        brand_name="Hydroviv",
        brand_domains=["hydroviv.com"],
        prompt_id_uuid="prompt-uuid-001",
        model_name="gpt-4o",
        elmo_version="v0.3.0",
    )
    assert mapped["brand_mentioned"] is False
    assert mapped["brand_status"] == "NOT_MENTIONED"


# ------------------------------------------------------------------
# UUID → int
# ------------------------------------------------------------------

def test_uuid_to_int_deterministic():
    """同值 UUID 产生相同 int。"""
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert _uuid_to_int(uuid) == _uuid_to_int(uuid)


def test_uuid_to_int_different_values():
    """不同 UUID 大概率产生不同 int。"""
    uuid1 = "550e8400-e29b-41d4-a716-446655440000"
    uuid2 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    assert _uuid_to_int(uuid1) != _uuid_to_int(uuid2)


def test_uuid_to_int_range():
    """结果在 int31 范围内。"""
    import uuid as uuid_mod
    test_uuid = str(uuid_mod.uuid4())
    result = _uuid_to_int(test_uuid)
    assert 0 <= result < 2 ** 31

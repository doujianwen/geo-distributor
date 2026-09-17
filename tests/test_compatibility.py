"""测试：compatibility 层。"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.compatibility import (
    PlatformObservation,
    PlatformCitation,
    map_geo_collector_observation,
)
from geo_distributor.models import Prompt, Observation


def test_platform_observation_fields():
    """PlatformObservation 包含所有核心字段。"""
    obs = PlatformObservation(
        observation_id="obs_001",
        prompt_id=1,
        engine="chatgpt",
        timestamp="2026-09-10T00:00:00",
        prompt_text="best water filter 2026",
        answer_raw="<p>Hydroviv...</p>",
        answer_clean="Hydroviv is the best choice.",
        answer_char_count=30,
        extraction_method="dom_traversal",
        validation_status="PASS",
        brand="Hydroviv",
        brand_mentioned=True,
        brand_status="MENTIONED",
        first_mention_position=1,
        recommendation_level=4,
        recommendation_rank=1,
        recommendation_evidence="Hydroviv is the best choice",
        competitors=[{"brand": "Brita", "position": 2}],
        citations=[{"url": "https://example.com", "domain": "example.com"}],
        citations_status="extracted",
        status="success",
    )
    assert obs.observation_id == "obs_001"
    assert obs.recommendation_level == 4
    assert obs.brand_mentioned is True
    assert len(obs.competitors) == 1
    assert len(obs.citations) == 1


def test_platform_observation_to_dict():
    obs = PlatformObservation(
        observation_id="obs_001",
        prompt_id=1,
        engine="chatgpt",
        timestamp="2026-09-10T00:00:00",
        prompt_text="test",
        answer_raw="",
        answer_clean="test answer",
        answer_char_count=11,
        extraction_method="test",
        validation_status="PASS",
        brand="Hydroviv",
        brand_mentioned=True,
        brand_status="MENTIONED",
        first_mention_position=None,
        recommendation_level=0,
        recommendation_rank=None,
        recommendation_evidence="",
        competitors=[],
        citations=[],
        citations_status="unavailable",
        status="success",
    )
    d = obs.to_dict()
    assert d["observation_id"] == "obs_001"
    assert d["brand_mentioned"] is True
    assert "raw_metadata" not in d  # to_dict 不暴露 raw_metadata


def test_map_geo_collector_observation():
    """将 geo-collector Observation 映射为 PlatformObservation。"""
    from geo_distributor.models import Observation as StorageObs
    storage_obs = StorageObs(
        observation_id="20260910_chatgpt_p001",
        prompt_id=1,
        engine="chatgpt",
        timestamp="2026-09-10T10:00:00",
        prompt_text="best water filter",
        answer_raw="<div>Hydroviv...</div>",
        answer_clean="Hydroviv is highly recommended.",
        answer_char_count=35,
        extraction_method="dom_traversal",
        validation_status="PASS",
        brand="Hydroviv",
        brand_mentioned=True,
        brand_status="MENTIONED",
        first_mention_position=1,
        recommendation_level=4,
        recommendation_rank=1,
        recommendation_evidence="Hydroviv is the best choice",
        competitors=[{"brand": "Brita", "position": 2}],
        citations=[{"url": "https://a.com", "domain": "a.com", "title": "A"}],
        citations_status="extracted",
        status="success",
    )
    platform = map_geo_collector_observation(storage_obs)
    assert isinstance(platform, PlatformObservation)
    assert platform.observation_id == "20260910_chatgpt_p001"
    assert platform.brand_mentioned is True
    assert platform.recommendation_level == 4
    assert len(platform.competitors) == 1
    assert len(platform.citations) == 1


def test_map_geo_collector_observation_failed():
    """失败 observation 也能正确映射。"""
    from geo_distributor.models import Observation as StorageObs
    storage_obs = StorageObs(
        observation_id="fail_001",
        prompt_id=2,
        engine="chatgpt",
        timestamp="2026-09-10T10:00:00",
        prompt_text="test",
        answer_raw="",
        answer_clean="",
        answer_char_count=0,
        extraction_method="",
        validation_status="FAIL",
        brand="Hydroviv",
        brand_mentioned=False,
        brand_status="UNKNOWN",
        first_mention_position=None,
        recommendation_level=-1,
        recommendation_rank=None,
        recommendation_evidence="",
        competitors=[],
        citations=[],
        citations_status="unavailable",
        status="failed",
    )
    platform = map_geo_collector_observation(storage_obs)
    assert platform.status == "failed"
    assert platform.recommendation_level == -1
    assert platform.brand_mentioned is False

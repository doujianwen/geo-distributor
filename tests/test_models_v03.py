"""测试：V0.3 新增模型（Provider / Measurement / Diagnosis）。"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.models import (
    Provider, ProviderType,
    Measurement,
    Diagnosis,
)


def test_provider_creation():
    p = Provider(
        provider_id="chatgpt",
        name="ChatGPT",
        provider_type=ProviderType.CHATGPT,
        version="gpt-4o",
    )
    assert p.provider_id == "chatgpt"
    assert p.name == "ChatGPT"
    assert p.version == "gpt-4o"
    assert p.is_active is True


def test_provider_type_enum():
    assert ProviderType.CHATGPT.value == "chatgpt"
    assert ProviderType.PERPLEXITY.value == "perplexity"
    assert ProviderType.ELMO.value == "elmo"
    assert ProviderType.UNKNOWN.value == "unknown"


def test_measurement_defaults():
    m = Measurement(
        measurement_id="m_001",
        observation_id="obs_001",
    )
    assert m.brand_position is None
    assert m.brand_recommendation_level == -1
    assert m.citation_count == 0
    assert m.geo_score is None
    assert m.measured_at != ""


def test_measurement_with_scores():
    m = Measurement(
        measurement_id="m_002",
        observation_id="obs_002",
        brand_position=1,
        brand_recommendation_level=4,
        citation_count=5,
        authority_citation_count=2,
        brand_owned_citation_count=1,
        geo_score=87.5,
    )
    assert m.brand_recommendation_level == 4
    assert m.geo_score == 87.5
    assert m.authority_citation_count == 2


def test_diagnosis_defaults():
    d = Diagnosis(
        diagnosis_id="d_001",
        observation_id="obs_001",
        measurement_id="m_001",
    )
    assert d.verdict == ""
    assert d.summary == ""
    assert d.findings == []
    assert d.recommendations == []


def test_diagnosis_with_findings():
    d = Diagnosis(
        diagnosis_id="d_002",
        observation_id="obs_002",
        measurement_id="m_002",
        verdict="PASS",
        summary="Brand highly recommended across all engines",
        findings=[
            {"type": "recommendation_level", "value": 4, "engine": "chatgpt"},
            {"type": "citation_quality", "value": "high"},
        ],
        recommendations=["Maintain current content strategy"],
    )
    assert d.verdict == "PASS"
    assert len(d.findings) == 2
    assert len(d.recommendations) == 1

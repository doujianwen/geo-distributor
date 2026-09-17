"""测试：Evidence 模型（ADR-007）。"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.models.evidence import Evidence


def test_evidence_creation():
    e = Evidence(
        evidence_id="ev_001",
        observation_id="obs_001",
        source_type="citation",
        content="Hydroviv is the best water filter.",
        url="https://example.com/review",
        credibility_score=0.85,
    )
    assert e.evidence_id == "ev_001"
    assert e.observation_id == "obs_001"
    assert e.source_type == "citation"
    assert e.content == "Hydroviv is the best water filter."
    assert e.url == "https://example.com/review"
    assert e.credibility_score == 0.85
    assert e.verified_at != ""


def test_evidence_defaults():
    e = Evidence(evidence_id="ev_002", observation_id="obs_002")
    assert e.source_type == ""
    assert e.content == ""
    assert e.url == ""
    assert e.credibility_score == 0.0
    assert e.verified_at != ""
    assert e.metadata == {}


def test_evidence_to_dict():
    e = Evidence(
        evidence_id="ev_003",
        observation_id="obs_003",
        source_type="raw_output_excerpt",
        content="test content",
        url="https://test.com",
        credibility_score=0.5,
    )
    d = e.to_dict()
    assert d["evidence_id"] == "ev_003"
    assert d["source_type"] == "raw_output_excerpt"
    assert d["credibility_score"] == 0.5
    assert "metadata" not in d  # to_dict 不暴露 metadata

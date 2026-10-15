"""Regression tests for channel-portal customer demand fields."""
from api.routers.projects import ProjectCreate
from geo_distributor.models.request import BusinessContext
from geo_distributor.services.scoping import ScopingService


def test_project_create_accepts_market_language_and_duration_fields():
    body = ProjectCreate(
        tenant_id="T-TEST",
        client_id="C-TEST",
        service="competitor_analysis",
        market_scope="multi",
        target_market=["US", "DE"],
        target_languages=["English", "German"],
        service_duration="3_months",
    )
    assert body.market_scope == "multi"
    assert body.target_market == ["US", "DE"]
    assert body.target_languages == ["English", "German"]
    assert body.service_duration == "3_months"


def test_global_market_does_not_require_country_selection():
    body = ProjectCreate(
        tenant_id="T-TEST",
        client_id="C-TEST",
        service="full_geo_project",
        market_scope="global",
        target_market=[],
        target_languages=["English"],
        service_duration="to_be_determined",
    )
    assert body.market_scope == "global"
    assert body.target_market == []


def test_business_context_round_trip_preserves_new_fields():
    context = BusinessContext(
        target_market=["US", "DE"],
        market_scope="multi",
        target_languages=["English", "German"],
        service_duration="3_months",
    )
    restored = BusinessContext(**context.to_dict())
    assert restored.market_scope == "multi"
    assert restored.target_market == ["US", "DE"]
    assert restored.target_languages == ["English", "German"]
    assert restored.service_duration == "3_months"


def test_legacy_business_context_payload_uses_safe_defaults():
    legacy = BusinessContext(**{"target_market": ["US"], "target_products": ["chairs"]})
    assert legacy.target_market == ["US"]
    assert legacy.market_scope == "unspecified"
    assert legacy.target_languages == []
    assert legacy.service_duration == "to_be_determined"


def test_competitor_analysis_maps_to_diagnosis_and_measurement_scope():
    stages = ScopingService()._determine_stages("competitor_analysis")
    assert stages["measurement"] is True
    assert stages["diagnosis"] is True
    assert stages["intervention"] is False
    assert stages["remeasurement"] is False

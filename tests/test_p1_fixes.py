"""测试：P1 修复项回归锁定。

覆盖：
1. Evidence 类统一（evidence.py 与 geo_core.py 不再各有一份）
2. ServiceStage 四阶段流转与进度
3. SyncService 增量同步水位
4. ProjectRepository 主键字段修复（_id_attr）
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.models import (  # noqa: E402
    Client,
    Evidence,
    EvidenceLevel,
    ServiceStage,
    StageStatus,
    DEFAULT_STAGE_SEQUENCE,
)
from geo_distributor.models.evidence import Evidence as EvidenceCompat  # noqa: E402
from geo_distributor.models.project import Project  # noqa: E402
from geo_distributor.repositories.project_repo import ProjectRepository  # noqa: E402


# ----------------------------------------------------------------------
# 1. Evidence 统一
# ----------------------------------------------------------------------

def test_evidence_is_single_definition():
    """evidence.py 与 geo_core.py 必须是同一个类。"""
    assert Evidence is EvidenceCompat, "Evidence 存在重复定义"


def test_evidence_merged_fields():
    """统一后的 Evidence 同时具备 geo_core 的 level 与旧版的 url/metadata。"""
    e = Evidence(
        evidence_id="EVD-001",
        observation_id="OBS-001",
        source_type="citation",
        content="test",
        url="https://example.com",
        credibility_score=0.85,
    )
    assert e.url == "https://example.com"
    assert e.metadata == {}
    assert e.level == EvidenceLevel.E1  # 默认等级
    assert e.credibility_score == 0.85


def test_evidence_default_credibility_is_zero():
    """未评分的证据不得默认采信（默认 0.0，而非 1.0）。"""
    e = Evidence(evidence_id="EVD-002", observation_id="OBS-002")
    assert e.credibility_score == 0.0
    assert e.source_type == ""
    assert e.content == ""
    assert e.url == ""


def test_evidence_to_dict_excludes_metadata():
    """metadata 是内部字段，不出现在对外序列化结果中。"""
    e = Evidence(evidence_id="EVD-003", observation_id="OBS-003", metadata={"k": "v"})
    d = e.to_dict()
    assert "metadata" not in d
    assert d["level"] == EvidenceLevel.E1.value


def test_evidence_level_accepts_string():
    """从 JSON 反序列化时 level 为字符串（如 "E2"）应能归一。"""
    e = Evidence(evidence_id="EVD-004", observation_id="OBS-004", level="e2_repeated_observation")
    assert e.level == EvidenceLevel.E2
    e2 = Evidence(evidence_id="EVD-005", observation_id="OBS-005", level="E2")
    assert e2.level == EvidenceLevel.E2


def test_evidence_from_dict_tolerates_extra_keys():
    payload = {
        "evidence_id": "EVD-006",
        "observation_id": "OBS-006",
        "project_id": "PRJ-1",  # 非 Evidence 字段，应被忽略
        "level": "E3",
    }
    e = Evidence.from_dict(payload)
    assert e.evidence_id == "EVD-006"
    assert e.level == EvidenceLevel.E3


# ----------------------------------------------------------------------
# 2. ServiceStage 四阶段
# ----------------------------------------------------------------------

def _make_project() -> Project:
    return Project(
        project_id="PRJ-T1",
        request_id="REQ-T1",
        tenant_id="T-1",
        client_id="CLI-1",
        scope_id="SC-1",
    )


def test_stage_sequence_and_labels():
    assert [s.value for s in DEFAULT_STAGE_SEQUENCE] == [
        "site_diagnosis", "competitor_analysis", "optimization", "effect_monitoring",
    ]
    assert ServiceStage.SITE_DIAGNOSIS.label == "网站诊断"
    assert ServiceStage.EFFECT_MONITORING.label == "效果监控"
    assert ServiceStage.OPTIMIZATION.order == 3


def test_project_starts_at_site_diagnosis():
    p = _make_project()
    assert p.service_stage == ServiceStage.SITE_DIAGNOSIS
    assert p.stage_progress == 0
    assert len(p.stage_records) == 4


def test_advance_through_all_stages_reaches_100():
    """走完四阶段并收口后，进度必须为 100%。

    回归锁定：首阶段若未 start()，推进时也必须被标记完成，
    否则进度会永久卡在 75%。
    """
    p = _make_project()
    for _ in range(3):
        assert p.advance_stage() is True
    assert p.service_stage == ServiceStage.EFFECT_MONITORING
    # 最终阶段无法再推进
    assert p.advance_stage() is False
    p.complete_current_stage()
    assert p.stage_progress == 100


def test_stage_rollback_allowed():
    p = _make_project()
    p.advance_stage()  # -> competitor_analysis
    p.advance_stage()  # -> optimization
    assert p.can_advance_to(ServiceStage.SITE_DIAGNOSIS) is True
    assert p.advance_stage(ServiceStage.SITE_DIAGNOSIS) is True
    assert p.service_stage == ServiceStage.SITE_DIAGNOSIS


def test_illegal_stage_transition_rejected():
    """不可从网站诊断直接跳到效果监控。"""
    p = _make_project()
    assert p.can_advance_to(ServiceStage.EFFECT_MONITORING) is False
    assert p.advance_stage(ServiceStage.EFFECT_MONITORING) is False
    assert p.service_stage == ServiceStage.SITE_DIAGNOSIS


def test_record_stage_output_dedupes():
    p = _make_project()
    p.record_stage_output(finding_ids=["FND-1", "FND-1", "FND-2"])
    rec = p.get_stage_record()
    assert rec.finding_ids == ["FND-1", "FND-2"]


def test_project_to_dict_exposes_stage():
    p = _make_project()
    d = p.to_dict()
    assert d["service_stage"] == "site_diagnosis"
    assert d["service_stage_label"] == "网站诊断"
    assert "stage_records" in d
    assert "stage_progress" in d


# ----------------------------------------------------------------------
# 3. Client 模型
# ----------------------------------------------------------------------

def test_client_model():
    c = Client(client_id="CLI-1", tenant_id="T-1", name="Acme", industry="Water")
    assert c.is_active is True
    d = c.to_dict()
    assert d["client_id"] == "CLI-1"
    assert d["tenant_id"] == "T-1"


# ----------------------------------------------------------------------
# 4. ProjectRepository 主键修复
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_repo_update_uses_project_id():
    """回归锁定：Project 同时有 request_id/project_id，update 必须用 project_id。

    修复前 base.update() 按顺序探测会取到 request_id → NotFoundError。
    """
    repo = ProjectRepository()
    p = _make_project()
    await repo.create(p)

    assert ProjectRepository._id_attr == "project_id"

    # 修改状态后 update 不应抛 NotFoundError
    p.advance_stage()
    updated = await repo.update(p)
    assert updated.service_stage == ServiceStage.COMPETITOR_ANALYSIS

    # 存储 key 仍是 project_id
    fetched = await repo.find_by_id("PRJ-T1")
    assert fetched is not None
    assert fetched.service_stage == ServiceStage.COMPETITOR_ANALYSIS


# ----------------------------------------------------------------------
# 5. SyncService（依赖 geo-collector.db 存在）
# ----------------------------------------------------------------------

def test_sync_service_incremental():
    """有 DB 时验证增量语义：首轮全量、次轮 0 新增、force 后全量。"""
    from geo_distributor.services.sync_service import SyncService

    svc = SyncService()
    if not os.path.exists(svc.db_path):
        pytest.skip(f"geo-collector DB not available: {svc.db_path}")

    brands = svc.list_brands()
    if not brands:
        pytest.skip("no brand data in geo-collector DB")

    brand = brands[0]
    svc.reset(brand)

    r1 = svc.sync(brand=brand)
    assert r1.new_count > 0
    assert r1.known_count == 0

    r2 = svc.sync(brand=brand)
    assert r2.new_count == 0, "第二次同步不应有新增"
    assert r2.known_count == r1.new_count

    r3 = svc.sync(brand=brand, force=True)
    assert r3.new_count == r1.new_count, "force 应重新返回全量"

    # 清理，避免污染后续运行
    svc.reset(brand)

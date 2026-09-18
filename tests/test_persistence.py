"""测试：P0-5 持久化层（SQLite 仓储）。

锁定两条不变量：
1. 未启用持久化时，行为与 Sprint 0 完全一致（内存仓储，重启即失）
2. 启用后数据跨"重启"保留，且租户隔离语义与各 InMemory 仓储一致
   （Project/Client 越权返回 None，Request 越权抛 PermissionError）
"""

import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.models import Client, Project, ProjectStatus  # noqa: E402
from geo_distributor.models.request import ServiceRequest, RequestStatus  # noqa: E402
from geo_distributor.persistence import (  # noqa: E402
    SQLiteClientRepository,
    SQLiteProjectRepository,
    SQLiteRequestRepository,
    resolve_db_path,
    is_persistence_enabled,
    get_default_db_path,
)


def _client() -> Client:
    return Client(client_id="CLI-T1", tenant_id="T-A", name="Test Co", industry="QA")


def _project() -> Project:
    return Project(
        project_id="PRJ-T1", request_id="REQ-T1", tenant_id="T-A",
        client_id="CLI-T1", scope_id="SC-T1",
    )


def _request() -> ServiceRequest:
    return ServiceRequest(request_id="REQ-T1", tenant_id="T-A", client_id="CLI-T1")


# ----------------------------------------------------------------------
# 路径解析
# ----------------------------------------------------------------------

def test_resolve_db_path_explicit_wins(monkeypatch):
    monkeypatch.setenv("GEO_DISTRIBUTOR_DB", "/env/path.db")
    assert resolve_db_path("/explicit/x.db") == "/explicit/x.db"


def test_resolve_db_path_env_path_is_used(monkeypatch):
    """回归锁定：环境变量里的真实路径必须被采用，不能被默认路径覆盖。"""
    monkeypatch.setenv("GEO_DISTRIBUTOR_DB", "/env/path.db")
    assert resolve_db_path() == "/env/path.db"


def test_resolve_db_path_env_flag_uses_default(monkeypatch):
    """GEO_DISTRIBUTOR_DB=1 视为开关，落到默认路径。"""
    monkeypatch.setenv("GEO_DISTRIBUTOR_DB", "1")
    assert resolve_db_path() == get_default_db_path()


def test_resolve_db_path_none_when_unset(monkeypatch):
    monkeypatch.delenv("GEO_DISTRIBUTOR_DB", raising=False)
    assert resolve_db_path() is None
    assert is_persistence_enabled() is False


# ----------------------------------------------------------------------
# 持久化：跨重启保留
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_persists_across_restart(tmp_path):
    db = str(tmp_path / "t.db")
    repo1 = SQLiteClientRepository(db)
    await repo1.create(_client())

    # 新实例 = 模拟进程重启
    repo2 = SQLiteClientRepository(db)
    got = await repo2.find_by_id("CLI-T1", tenant_id="T-A")
    assert got is not None
    assert got.name == "Test Co"
    assert got.industry == "QA"


@pytest.mark.asyncio
async def test_project_persists_with_stage_state(tmp_path):
    """四阶段进度必须随项目一起持久化——这是本次最关键的收益。"""
    db = str(tmp_path / "t.db")
    repo1 = SQLiteProjectRepository(db)
    p = _project()
    await repo1.create(p)
    p.advance_stage()                      # -> competitor_analysis
    p.record_stage_output(finding_ids=["FND-1", "FND-2"])
    await repo1.update(p)

    repo2 = SQLiteProjectRepository(db)
    got = await repo2.find_by_id("PRJ-T1", tenant_id="T-A")
    assert got.service_stage.value == "competitor_analysis"
    assert got.stage_records["competitor_analysis"].finding_ids == ["FND-1", "FND-2"]
    assert got.status == ProjectStatus.APPROVED


@pytest.mark.asyncio
async def test_request_persists(tmp_path):
    db = str(tmp_path / "t.db")
    r1 = SQLiteRequestRepository(db)
    r = _request()
    r.transition_to(RequestStatus.SUBMITTED)
    await r1.create(r)

    r2 = SQLiteRequestRepository(db)
    got = await r2.find_by_id("REQ-T1", tenant_id="T-A")
    assert got.status == RequestStatus.SUBMITTED


# ----------------------------------------------------------------------
# 租户隔离语义（必须与 InMemory 一致）
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_wrong_tenant_returns_none(tmp_path):
    db = str(tmp_path / "t.db")
    repo = SQLiteProjectRepository(db)
    await repo.create(_project())
    assert await repo.find_by_id("PRJ-T1", tenant_id="T-B") is None


@pytest.mark.asyncio
async def test_request_wrong_tenant_raises(tmp_path):
    """RequestRepository 对越权是抛异常，SQLite 版必须保持一致。"""
    db = str(tmp_path / "t.db")
    repo = SQLiteRequestRepository(db)
    await repo.create(_request())
    with pytest.raises(PermissionError):
        await repo.find_by_id("REQ-T1", tenant_id="T-B")


@pytest.mark.asyncio
async def test_find_by_tenant_isolates(tmp_path):
    db = str(tmp_path / "t.db")
    repo = SQLiteProjectRepository(db)
    await repo.create(_project())
    other = Project(
        project_id="PRJ-T2", request_id="REQ-T2", tenant_id="T-B",
        client_id="CLI-T2", scope_id="SC-T2",
    )
    await repo.create(other)

    assert len(await repo.find_by_tenant("T-A")) == 1
    assert len(await repo.find_by_tenant("T-B")) == 1


@pytest.mark.asyncio
async def test_update_wrong_tenant_raises(tmp_path):
    db = str(tmp_path / "t.db")
    repo = SQLiteClientRepository(db)
    c = _client()
    await repo.create(c)
    c.tenant_id = "T-B"  # 越权改写
    with pytest.raises(PermissionError):
        await repo.update(c)


# ----------------------------------------------------------------------
# 重复创建 / 删除
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_create_rejected(tmp_path):
    db = str(tmp_path / "t.db")
    repo = SQLiteClientRepository(db)
    await repo.create(_client())
    with pytest.raises(ValueError):
        await repo.create(_client())


@pytest.mark.asyncio
async def test_delete_removes(tmp_path):
    db = str(tmp_path / "t.db")
    repo = SQLiteClientRepository(db)
    await repo.create(_client())
    assert await repo.delete("CLI-T1") is True
    assert await repo.find_by_id("CLI-T1") is None
    assert await repo.delete("CLI-T1") is False


# ----------------------------------------------------------------------
# 默认后端仍是内存（不变量）
# ----------------------------------------------------------------------

def test_default_backend_is_memory(monkeypatch):
    """未设置 GEO_DISTRIBUTOR_DB 时，API 必须仍用内存仓储。"""
    monkeypatch.delenv("GEO_DISTRIBUTOR_DB", raising=False)
    from api import state
    state.init_repositories()
    assert state.persistence_backend == "memory"
    assert state.active_db_path is None

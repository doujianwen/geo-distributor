"""RA-10 加固红队测试：真实交付路径（DeliveryService.execute_delivery）幂等验证。

历史教训（2026-10-17）：本文件旧版测的是 IdempotencyGuard——一个从未接入
交付路径的死代码，6 个用例恒绿却零保护，构成「假门禁」。本版全部对准真实路径：

  - 顺序重放：同 (project, tenant, scope_version) → ALREADY_DELIVERED，无重复
  - 不同 scope_version → 正常新建
  - 并发（asyncio.gather）：恰 1 个 DELIVERED，其余回放；存储层唯一约束兜底
  - 存储层竞态回退：create_report 抛 DuplicateReportError → 返回既有报告
  - 跨重启持久性：新建服务实例（同 DB）重放仍幂等（查 DB 而非内存）
  - 迁移防护：存量重复行时 scope_unique 初始化显式失败（不静默）
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.persistence.sqlite_repository import SQLiteJSONRepository
from geo_distributor.services.delivery import DeliveryService, DuplicateReportError, ReportService

OBS = [{"k": "v", "brand_mentioned": True, "recommendation_level": 2}]
FIND = [{"finding_id": "F1", "category": "c", "severity": "low", "statement": "s", "recommendation": "r"}]


def _sqlite_service(tmp_path: Path) -> DeliveryService:
    """持久化模式 DeliveryService（隔离临时 DB，复用 api/state.py 的装配语义）。"""
    db = str(tmp_path / "idem.db")
    repo = SQLiteJSONRepository("reports_projection", db, scope_unique=True)
    return DeliveryService(ReportService(repository=repo))


def _rows(tmp_path: Path) -> int:
    conn = sqlite3.connect(str(tmp_path / "idem.db"))
    try:
        return conn.execute("SELECT COUNT(*) FROM reports_projection").fetchone()[0]
    finally:
        conn.close()


class TestSequentialIdempotency:
    @pytest.mark.asyncio
    async def test_replay_returns_existing_report(self, tmp_path):
        svc = _sqlite_service(tmp_path)
        d1 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        d2 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        assert d1["status"] == "DELIVERED"
        assert d2["status"] == "ALREADY_DELIVERED"
        assert d2["report_id"] == d1["report_id"]
        assert _rows(tmp_path) == 1

    @pytest.mark.asyncio
    async def test_different_scope_creates_new(self, tmp_path):
        svc = _sqlite_service(tmp_path)
        d1 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        d2 = await svc.execute_delivery("P1", "T1", 2, OBS, FIND, "tester")
        assert d2["status"] == "DELIVERED"
        assert d2["report_id"] != d1["report_id"]
        assert _rows(tmp_path) == 2

    @pytest.mark.asyncio
    async def test_idempotent_across_restart(self, tmp_path):
        """跨重启幂等：新服务实例（同 DB）重放仍返回既有报告（查 DB 非内存）。"""
        db = str(tmp_path / "idem.db")
        repo1 = SQLiteJSONRepository("reports_projection", db, scope_unique=True)
        svc1 = DeliveryService(ReportService(repository=repo1))
        d1 = await svc1.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        # 「重启」：全新实例 + 全新内存字典
        repo2 = SQLiteJSONRepository("reports_projection", db, scope_unique=True)
        svc2 = DeliveryService(ReportService(repository=repo2))
        d2 = await svc2.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        assert d2["status"] == "ALREADY_DELIVERED"
        assert d2["report_id"] == d1["report_id"]
        assert _rows(tmp_path) == 1


class TestConcurrentIdempotency:
    @pytest.mark.asyncio
    async def test_concurrent_replay_single_row(self, tmp_path):
        """并发重放：竞态窗口由存储层 UNIQUE 约束原子兜底，必须恰好 1 行。"""
        svc = _sqlite_service(tmp_path)
        results = await asyncio.gather(*[
            svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester") for _ in range(20)
        ])
        delivered = [r for r in results if r["status"] == "DELIVERED"]
        replayed = [r for r in results if r["status"] == "ALREADY_DELIVERED"]
        assert len(delivered) == 1
        assert len(replayed) == 19
        report_ids = {r["report_id"] for r in results}
        assert len(report_ids) == 1
        assert _rows(tmp_path) == 1


class TestRaceFallback:
    @pytest.mark.asyncio
    async def test_duplicate_report_error_returns_existing(self, tmp_path):
        """存储层竞态回退：create_report 抛 DuplicateReportError → 返回既有报告。"""
        svc = _sqlite_service(tmp_path)
        d1 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")

        async def _raced(*args, **kwargs):
            raise DuplicateReportError("simulated storage constraint hit")

        svc.report_service.create_report = _raced  # 模拟并发对手方已落库
        d2 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        assert d2["status"] == "ALREADY_DELIVERED"
        assert d2["report_id"] == d1["report_id"]

    @pytest.mark.asyncio
    async def test_duplicate_report_error_reraises_when_no_existing(self, tmp_path):
        """约束命中但查不到既有报告（异常态）→ 原样上抛，不伪造成功。"""
        svc = _sqlite_service(tmp_path)

        async def _raced(*args, **kwargs):
            raise DuplicateReportError("simulated storage constraint hit")

        svc.report_service.create_report = _raced
        with pytest.raises(DuplicateReportError):
            await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")


class TestMigrationGuard:
    def test_scope_unique_init_fails_on_existing_duplicates(self, tmp_path):
        """存量重复行时初始化必须显式失败（不静默吞掉 = 不做假门禁）。"""
        db = str(tmp_path / "dup.db")
        # 先建一个无约束表并注入重复行
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE reports_projection (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
            "project_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        payload = '{"report_id": "R", "tenant_id": "T1", "project_id": "P1", "scope_version": 1, "version": 1, "created_at": "2026-01-01", "created_by": "x"}'
        for rid in ("R1", "R2"):
            conn.execute(
                "INSERT INTO reports_projection VALUES (?, 'T1', 'P1', ?, '2026-01-01')", (rid, payload)
            )
        conn.commit()
        conn.close()
        with pytest.raises(RuntimeError, match="ra10_dedupe_reports"):
            SQLiteJSONRepository("reports_projection", db, scope_unique=True)


class TestMemoryModeIdempotency:
    @pytest.mark.asyncio
    async def test_memory_mode_sequential_replay(self):
        """内存模式（repository=None）顺序重放同样幂等（演示回退路径不回归）。"""
        svc = DeliveryService()
        d1 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        d2 = await svc.execute_delivery("P1", "T1", 1, OBS, FIND, "tester")
        assert d1["status"] == "DELIVERED"
        assert d2["status"] == "ALREADY_DELIVERED"
        assert d2["report_id"] == d1["report_id"]

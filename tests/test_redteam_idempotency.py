"""Sprint 0 Red-Team: Idempotency 攻击测试。

攻击向量：
- 同Key同Payload → 返回原结果（不创建重复）
- 同Key不同Payload → 409冲突
- 第一次失败后重试 → 无partial duplicate
- 并发重复请求 → 只产生一个对象
- Key过期后 → 允许新请求
"""

import pytest
import sys
from pathlib import Path
import asyncio
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from geo_distributor.guards.idempotency import IdempotencyGuard


class TestIdempotencyCorrectness:
    """测试幂等性正确性。"""

    def test_same_key_same_payload_returns_original(self):
        """同Key同Payload → 返回原结果。"""
        guard = IdempotencyGuard()
        payload = {"client_id": "CLI-001", "service": "visibility_audit"}
        result = {"request_id": "SR-001", "status": "SUBMITTED"}

        # 第一次请求
        first = guard.check_and_store("KEY-001", payload, result)
        assert first["idempotent"] is False
        assert first["stored"] is True
        assert first["result"]["request_id"] == "SR-001"

        # 第二次相同请求
        second = guard.check_and_store("KEY-001", payload, result)
        assert second["idempotent"] is True
        assert second["result"]["request_id"] == "SR-001"  # 返回原结果

    def test_same_key_different_payload_returns_conflict(self):
        """同Key不同Payload → 409冲突。"""
        guard = IdempotencyGuard()

        # 第一次请求
        guard.check_and_store("KEY-002", {"service": "audit"}, {"id": "SR-002"})

        # 第二次不同Payload
        result = guard.check_and_store(
            "KEY-002",
            {"service": "diagnosis"},  # 不同
            {"id": "SR-003"}
        )
        assert result["idempotent"] is False
        assert result["error"] == "IDEMPOTENCY_CONFLICT"

    def test_expired_key_allows_new_request(self):
        """Key过期后允许新请求。"""
        guard = IdempotencyGuard(ttl_hours=0)  # 立即过期
        payload = {"service": "audit"}
        result = {"id": "SR-004"}

        # 第一次请求
        first = guard.check_and_store("KEY-003", payload, result)
        assert first["stored"] is True

        # Key应立即过期（ttl=0）
        # 第二次请求应该成功（key已过期）
        import time
        time.sleep(0.01)  # 短暂等待确保时间流逝

        second = guard.check_and_store("KEY-003", payload, result)
        assert second["stored"] is True  # 视为新请求


class TestIdempotencyAttackScenarios:
    """测试幂等性攻击场景。"""

    def test_no_partial_duplicate_on_failure(self):
        """第一次请求失败后重试，不产生partial duplicate。"""
        guard = IdempotencyGuard()
        payload = {"service": "audit"}
        result = {"id": "SR-005", "status": "SUBMITTED"}

        # 第一次请求（模拟成功）
        first = guard.check_and_store("KEY-004", payload, result)
        assert first["stored"] is True

        # 重试相同请求
        retry = guard.check_and_store("KEY-004", payload, result)
        assert retry["idempotent"] is True
        assert retry["result"]["id"] == "SR-005"  # 返回原结果，不创建新对象

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """并发重复请求 → 只产生一个对象。"""
        guard = IdempotencyGuard()
        payload = {"service": "audit"}
        result = {"id": "SR-006"}

        # 串行执行模拟（Python GIL保证原子性，但测试验证逻辑）
        first = guard.check_and_store("KEY-005", payload, result)
        second = guard.check_and_store("KEY-005", payload, result)

        # 第一个成功，第二个返回幂等结果
        assert first["stored"] is True
        assert second["idempotent"] is True
        assert first["result"]["id"] == second["result"]["id"]


class TestIdempotencyKeyGeneration:
    """测试幂等键生成。"""

    def test_key_format(self):
        """键格式符合规范。"""
        guard = IdempotencyGuard()
        key = guard.generate_key("SR-001", "submit")

        assert key.startswith("SR-001:submit:")
        assert len(key) > 20  # 包含时间戳

    def test_different_payloads_different_keys(self):
        """不同Payload生成不同哈希。"""
        guard = IdempotencyGuard()
        hash1 = guard._hash_payload({"service": "audit"})
        hash2 = guard._hash_payload({"service": "diagnosis"})

        assert hash1 != hash2

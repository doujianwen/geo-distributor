"""Idempotency Guard（Sprint 0 — P0 必须）。

防止 Distributor 因网络问题重复点击导致重复创建。

规则：
- 同 Key + 同 Payload → 返回原结果
- 同 Key + 不同 Payload → 409 IDEMPOTENCY_CONFLICT
- Key 过期（默认 24h）→ 允许新请求
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class IdempotencyRecord:
    """幂等性记录。"""
    key: str
    payload_hash: str
    result: Dict[str, Any]
    created_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


class IdempotencyGuard:
    """幂等性守卫。

    MVP 使用内存存储，生产环境应替换为 Redis。
    """

    def __init__(self, ttl_hours: int = 24):
        self._store: Dict[str, IdempotencyRecord] = {}
        self._ttl = timedelta(hours=ttl_hours)

    def check_and_store(
        self,
        key: str,
        payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """检查幂等键，如果已存在则返回原结果，否则存储新结果。

        返回：
        - {"idempotent": True, "result": ...} 如果 key 已存在
        - {"idempotent": False, "stored": True, "result": ...} 如果新存储
        """
        payload_hash = self._hash_payload(payload)

        if key in self._store:
            record = self._store[key]
            if record.is_expired():
                # 过期，允许新请求
                del self._store[key]
            elif record.payload_hash == payload_hash:
                # 相同请求，返回原结果
                logger.info("Idempotent hit: key=%s", key[:8])
                return {"idempotent": True, "result": record.result}
            else:
                # 不同请求，冲突
                logger.warning("Idempotency conflict: key=%s", key[:8])
                return {
                    "idempotent": False,
                    "error": "IDEMPOTENCY_CONFLICT",
                    "message": f"Key {key} has different payload",
                }

        # 新请求，存储结果
        now = datetime.now()
        self._store[key] = IdempotencyRecord(
            key=key,
            payload_hash=payload_hash,
            result=result,
            created_at=now,
            expires_at=now + self._ttl,
        )
        logger.info("Idempotency stored: key=%s", key[:8])
        return {"idempotent": False, "stored": True, "result": result}

    def get_result(self, key: str) -> Optional[Dict[str, Any]]:
        """获取已存储的结果（用于重试）。"""
        if key in self._store:
            record = self._store[key]
            if not record.is_expired():
                return record.result
        return None

    def invalidate(self, key: str) -> bool:
        """使记录失效（用于失败后重试）。"""
        if key in self._store:
            del self._store[key]
            logger.info("Idempotency invalidated: key=%s", key[:8])
            return True
        return False

    def cleanup_expired(self):
        """清理过期记录。"""
        now = datetime.now()
        expired = [k for k, v in self._store.items() if v.is_expired()]
        for k in expired:
            del self._store[k]
        return len(expired)

    @staticmethod
    def _hash_payload(payload: Dict[str, Any]) -> str:
        """计算 payload 的哈希。"""
        import json
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]

    def generate_key(self, request_id: str, action: str) -> str:
        """生成幂等键。"""
        return f"{request_id}:{action}:{datetime.now().strftime('%Y%m%d%H%M%S')}"

"""请求限流：按 API Key 的令牌桶。

## 为什么需要

B-2 认证解决了「你是谁」，但没解决「你能打多少次」。
远程商业部署后，密钥泄露或客户端 bug 都可能瞬间打满 API。
`secrets.compare_digest` 只防时序侧信道，不防暴力请求。

## 为什么用令牌桶而不是固定窗口

- 固定窗口在窗口边界允许 2倍突发
- 令牌桶允许可控的突发（桶容量）同时限制长期速率
- 无外部依赖，纯标准库实现

## 与反向代理的分工

限流是**应用层最后一道防线**，不是第一道。建议部署时：

- 反向代理层：按 IP 粗粒度限流（挡扫描器）
- 本模块：按 API Key 细粒度限流（挡单租户失控）

两层都要有：反代层看不到 API Key，本模块看不到 IP。

运行：
    from api.ratelimit import limiter
    limiter.check("sk-xxx", cost=1)   # 抛 429 或返回剩余配额
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------

RATE_LIMIT_ENV = "GEO_DISTRIBUTOR_RATE_LIMIT"       # "60" 每分钟请求数
BURST_ENV = "GEO_DISTRIBUTOR_RATE_BURST"            # 桶容量（突发上限）

DEFAULT_RATE_PER_MIN = 60
DEFAULT_BURST = 20

# 令牌桶内部时钟：可用环境变量加速测试（不改变语义，只改变时间流速）
CLOCK_SCALE_ENV = "GEO_DISTRIBUTOR_CLOCK_SCALE"


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def _clock_scale() -> float:
    """测试可加速时钟。生产恒为 1.0。"""
    raw = (os.environ.get(CLOCK_SCALE_ENV, "") or "").strip()
    if not raw:
        return 1.0
    try:
        scale = float(raw)
        return scale if scale > 0 else 1.0
    except ValueError:
        return 1.0


def _now() -> float:
    return time.monotonic() * _clock_scale()


# ------------------------------------------------------------
# 令牌桶
# ------------------------------------------------------------


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    """按 key（通常是 API Key）的令牌桶限流器。"""

    def __init__(
        self,
        rate_per_min: Optional[int] = None,
        burst: Optional[int] = None,
    ) -> None:
        self.rate_per_min = rate_per_min or _env_int(RATE_LIMIT_ENV, DEFAULT_RATE_PER_MIN)
        self.burst = burst or _env_int(BURST_ENV, DEFAULT_BURST)
        # 每秒补充的令牌数
        self.rate_per_sec = self.rate_per_min / 60.0
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str, cost: float = 1.0) -> tuple[bool, int, int]:
        """尝试消费令牌。

        返回 `(allowed, remaining, retry_after_seconds)`：
        - allowed=False 时 retry_after 为建议等待秒数（向上取整，最小 1）
        """
        if not key:
            # 没有 key（未认证请求已在认证层被拒）→ 不在此处限流
            return True, self.burst, 0

        with self._lock:
            now = _now()
            bucket = self._buckets.get(key)

            if bucket is None:
                bucket = _Bucket(tokens=float(self.burst), last_refill=now)
                self._buckets[key] = bucket
            else:
                elapsed = now - bucket.last_refill
                if elapsed > 0:
                    bucket.tokens = min(
                        float(self.burst),
                        bucket.tokens + elapsed * self.rate_per_sec,
                    )
                    bucket.last_refill = now

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True, int(bucket.tokens), 0

            # 不足：算出还需多久才能补够
            deficit = cost - bucket.tokens
            retry_after = max(1, int(deficit / self.rate_per_sec) + 1) if self.rate_per_sec > 0 else 60
            return False, 0, retry_after

    def reset(self, key: Optional[str] = None) -> None:
        """清空桶（测试用，或密钥吊销时调用）。"""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)

    def snapshot(self) -> Dict[str, float]:
        """当前各 key 的剩余令牌（诊断用）。"""
        with self._lock:
            return {k: round(v.tokens, 2) for k, v in self._buckets.items()}


# 全局单例
limiter = RateLimiter()

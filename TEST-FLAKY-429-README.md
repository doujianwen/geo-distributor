# 全量跑 geo-distributor 测试前必读

## 现象
全量 `pytest` 出现 6failed / 18 failed **数量随机波动**，但单跑每个测试都通过。

## 根因：API 令牌桶限流（不是代码回归）

`api/ratelimit.py`：

```
RATE_LIMIT_ENV   = "GEO_DISTRIBUTOR_RATE_LIMIT"    # 默认 60 次/分钟
BURST_ENV        = "GEO_DISTRIBUTOR_RATE_BURST"# 桶容量，默认 20
```

全量 380+ 用例**共享同一个 API Key**，必然触顶→ 429。

## 判定方法（不要靠猜）

```bash
# 1. 看报错里有没有 429
pytest 2>&1 | grep -oE "429|Rate limit exceeded" | sort | uniq -c

# 2. 决定性证据：单跑同一个测试
pytest tests/test_p1_remaining.py::test_distribution_routes_available   # → passed
pytest tests/test_p1_remaining.py                                        # → 21 passed
```

**单跑通过 + 全量失败 = 限流干扰，不是回归。**

## 抬额度无效

```bash
GEO_DISTRIBUTOR_RATE_LIMIT=100000 pytest   # ❌ 无效
```

原因：`limiter = RateLimiter()` 是**模块导入期创建的全局单例**，
此时环境变量已读入；`tests/conftest.py` 在更早阶段就导入了 api 模块，
后设的环境变量不会再触发 `_env_int` 读取。

## 正确做法

- **验证单个改动的影响** → 只跑相关文件，别跑全量
- **必须跑全量时** → 间隔足够时间（令牌桶 60/分钟 ⇒至少等 2 分钟）再跑，且只看**趋势**不看单次数字
- **关键指标**：`test_prompt_integrity.py`（L4 真实配置守卫）必须 9/9，
  这个文件不依赖 API，不受限流影响

## 2026-10-06 实例

清理 Hydroviv 数据后连续 3 次全量：6 failed → 18 failed → 18 failed，
但 `test_prompt_integrity.py` 始终 9 passed、单跑 `test_p1_remaining.py` 21 passed。
**同一份代码**，波动完全来自限流。若当时只看"18 failed"就回滚清理工作，会误伤。

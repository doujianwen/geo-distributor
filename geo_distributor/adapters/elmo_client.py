"""Elmo REST API 客户端。

所有与 Elmo 的 HTTP 交互封装在此文件。
- Bearer token 认证
- 版本锁定（self.version 存储在 raw_metadata 中追溯）
- 保留原始响应（raw_metadata 中存储完整 Elmo 数据）
- Async context manager
- 重试策略：5xx 最多 2 次指数退避；401/403/404 不重试
- 超时：30s（可配置）

设计约束：
- 绝不直接访问 Elmo PostgreSQL
- 只通过 /api/v1/* REST 端点交互
- 上层业务不感知此文件，仅通过 ElmoAdapter 间接使用
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class ElmoClientError(Exception):
    """Elmo API 调用失败时抛出。"""
    pass


class ElmoClient:
    """Elmo REST API 客户端。

    Args:
        base_url: Elmo 服务地址，如 "http://localhost:3000"
        api_key: Bearer token
        version: 锁定的 Elmo 版本，如 "v0.3.0"
        timeout_seconds: 请求超时（秒）
        max_retries: 5xx 重试次数
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        version: str = "v0.3.0",
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ):
        if not base_url:
            raise ElmoClientError("base_url is required")
        if not api_key:
            raise ElmoClientError("api_key is required")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.version = version
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """发送请求，带重试和认证。"""
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        kwargs.setdefault("timeout", self.timeout_seconds)
        kwargs.setdefault("headers", headers)

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.request(method, url, **kwargs)

                if resp.status_code >= 500 and attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "Elmo %s %s → %d (attempt %d/%d), retrying in %ds",
                        method, path, resp.status_code,
                        attempt + 1, self.max_retries + 1, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                return resp

            except (httpx.TimeoutException, httpx.ConnectError, OSError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "Elmo %s %s network error (attempt %d/%d): %s",
                        method, path, attempt + 1, self.max_retries + 1, exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error("Elmo %s %s failed after %d attempts: %s",
                                 method, path, self.max_retries + 1, exc)

        raise ElmoClientError(
            f"Elmo {method} {path} failed after {self.max_retries + 1} attempts: {last_exc}"
        ) from last_exc

    async def _get(self, path: str) -> Dict[str, Any]:
        resp = await self._request("GET", path)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: Optional[dict] = None) -> Dict[str, Any]:
        resp = await self._request("POST", path, json=body)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """GET /api/v1/me — 验证 API 可访问性和认证。"""
        try:
            data = await self._get("/api/v1/me")
            logger.info("Elmo health check OK: %s", data.get("user", {}).get("name", "unknown"))
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                logger.error("Elmo health check: auth failed (%d)", exc.response.status_code)
            else:
                logger.error("Elmo health check: %d", exc.response.status_code)
            return False
        except Exception as exc:
            logger.error("Elmo health check error: %s", exc)
            return False

    async def get_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """GET /api/v1/prompts/{id} — 获取 prompt 详情。"""
        return await self._get(f"/api/v1/prompts/{prompt_id}")

    async def list_runs(
        self,
        prompt_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> list:
        """GET /api/v1/prompts/{id}/runs — 获取 prompt 的 runs 列表。"""
        data = await self._get(
            f"/api/v1/prompts/{prompt_id}/runs?limit={limit}&offset={offset}"
        )
        return data.get("runs", [])

    async def get_run(self, prompt_id: str, run_id: str) -> Dict[str, Any]:
        """GET /api/v1/prompts/{id}/runs/{runId} — 获取单次运行详情。"""
        return await self._get(f"/api/v1/prompts/{prompt_id}/runs/{run_id}")

    async def list_models(self) -> list:
        """GET /api/v1/models — 列出可用的 AI 模型。"""
        data = await self._get("/api/v1/models")
        return data.get("models", [])

    async def get_brand(self, brand_id: str) -> Dict[str, Any]:
        """GET /api/v1/brands/{brandId} — 获取品牌信息（名称、域名等）。"""
        return await self._get(f"/api/v1/brands/{brand_id}")

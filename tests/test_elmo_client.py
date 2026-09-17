"""测试：ElmoClient REST API 客户端（零网络依赖，MockTransport）。"""

import sys
import os
import asyncio
import pytest
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.adapters.elmo_client import ElmoClient, ElmoClientError


def _make_client(base_url="http://localhost:3000", api_key="test-key"):
    return ElmoClient(base_url=base_url, api_key=api_key, version="v0.3.0")


def test_elmo_client_requires_api_key():
    """空 api_key 时初始化应抛出 ElmoClientError。"""
    with pytest.raises(ElmoClientError, match="api_key"):
        ElmoClient(base_url="http://localhost:3000", api_key="", version="v0.3.0")


def test_elmo_client_requires_base_url():
    """空 base_url 时初始化应抛出 ElmoClientError。"""
    with pytest.raises(ElmoClientError, match="base_url"):
        ElmoClient(base_url="", api_key="test-key")


async def _test_health_with_status(status_code, expected_result):
    """通用 health_check 测试：mock 指定状态码。"""
    async def handler(request):
        return httpx.Response(status_code, json={"error": "test"})

    client = _make_client()
    # 注入 mock transport
    original_request = client._request

    async def mock_request(method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            resp = await http_client.request(method, f"http://localhost:3000{path}", **kwargs)
        return resp

    client._request = mock_request
    result = await client.health_check()
    assert result == expected_result


def test_elmo_client_health_success():
    asyncio.run(_test_health_with_status(200, True))


def test_elmo_client_health_failure():
    asyncio.run(_test_health_with_status(500, False))


def test_elmo_client_401_returns_false():
    asyncio.run(_test_health_with_status(401, False))


async def _test_get_run():
    run_data = {"id": "run-001", "model": "gpt-4o", "brandMentioned": True}

    async def handler(request):
        return httpx.Response(200, json=run_data)

    client = _make_client()

    async def mock_request(method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            resp = await http_client.request(method, f"http://localhost:3000{path}", **kwargs)
        return resp

    client._request = mock_request
    data = await client._get("/api/v1/prompts/123/runs/run-001")
    assert data == run_data


def test_elmo_client_get_run_returns_dict():
    asyncio.run(_test_get_run())


def test_elmo_client_timeout_returns_false():
    """网络超时 → health_check 返回 False。"""
    async def handler(request):
        raise httpx.ConnectError("Connection refused")

    async def run_test():
        client = _make_client()

        async def mock_request(method, path, **kwargs):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
                try:
                    return await http_client.request(method, f"http://localhost:3000{path}", **kwargs)
                except Exception:
                    raise

        client._request = mock_request
        return await client.health_check()

    result = asyncio.run(run_test())
    assert result is False


async def _test_list_runs():
    runs_data = {"runs": [{"id": "r1"}, {"id": "r2"}]}

    async def handler(request):
        return httpx.Response(200, json=runs_data)

    client = _make_client()

    async def mock_request(method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            resp = await http_client.request(method, f"http://localhost:3000{path}", **kwargs)
        return resp

    client._request = mock_request
    runs = await client.list_runs("123", limit=10)
    assert len(runs) == 2
    assert runs[0]["id"] == "r1"


def test_elmo_client_list_runs_returns_list():
    asyncio.run(_test_list_runs())

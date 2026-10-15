"""integration 目录专属夹具。

## 为什么需要这个文件（2026-10-13 定位的 4 项失败根因）

本目录的测试用**真实 uvicorn 子进程 + 真实 httpx 客户端**验证网络行为。
httpx 默认 `trust_env=True`，会读取 HTTP_PROXY/HTTPS_PROXY 等环境变量。

当开发机存在系统级代理（如沙箱/企业代理 127.0.0.1:<port>）时：

- 对 `127.0.0.1:<port>` 的请求被转发给代理，代理行为不可控
  （GET 可能被代答 404 → 造成「create 201 后读回 404」的伪报）；
- 对非回环地址的「必须连不上」断言更严重：代理会对**不可达目标**
  返回 HTTP 502 **响应**而非抛出连接异常 →
  `test_RT_WP_08_backend_binds_loopback_only` 误判"后端暴露在非回环地址"
  （实际服务只绑定 127.0.0.1，netstat 实证）。

修复方式：本目录所有用例自动清除代理环境变量（等价 NO_PROXY=*），
让 httpx 直连真实目标——这正是"走真实网络"的本意，且不削弱任何
安全断言（非回环不可达的检查变为真实直连探测，反而更严格）。
"""

from __future__ import annotations

import pytest

_PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@pytest.fixture(autouse=True)
def _no_ambient_proxy(monkeypatch):
    """隔离环境代理：本目录测试必须直连，不经过任何系统代理。"""
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    yield

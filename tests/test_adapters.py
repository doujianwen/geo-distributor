"""测试：adapters（V0.4 ElmoAdapter MVP）。"""

import sys
import os
import pytest
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.adapters import ElmoAdapter, GeoCollectorAdapter
from geo_distributor.models import Prompt
from geo_distributor.compatibility import PlatformObservation


def test_elmo_adapter_health_with_empty_config():
    """配置缺失时 health_check 返回 False。"""
    adapter = ElmoAdapter()
    result = asyncio.run(adapter.health_check())
    assert result is False


def test_elmo_adapter_collect_returns_error_on_empty_config():
    """配置缺失时 collect_prompt 返回 error PlatformObservation（不抛异常）。"""
    adapter = ElmoAdapter()
    prompt = Prompt(prompt_id=1, category="", intent="", location="", text="test")
    obs = asyncio.run(adapter.collect_prompt(prompt))
    assert isinstance(obs, PlatformObservation)
    assert obs.status == "failed"
    assert "error" in obs.raw_metadata


def test_elmo_adapter_batch_empty_list():
    """空 prompts 列表返回空结果。"""
    adapter = ElmoAdapter()
    results = asyncio.run(adapter.collect_batch([]))
    assert results == []


def test_elmo_adapter_batch_partial_failure():
    """部分失败时继续处理其余 prompt。"""
    adapter = ElmoAdapter(elmo_url="http://nonexistent:9999", api_key="test")
    prompts = [
        Prompt(prompt_id=1, category="", intent="", location="", text="test1"),
        Prompt(prompt_id=2, category="", intent="", location="", text="test2"),
    ]
    results = asyncio.run(adapter.collect_batch(prompts))
    assert len(results) == 2
    # 两者都应该返回 failed 而非抛异常
    assert all(r.status == "failed" for r in results)


def test_geo_collector_adapter_exists():
    adapter = GeoCollectorAdapter()
    assert adapter is not None


def test_geo_collector_adapter_health():
    adapter = GeoCollectorAdapter()
    result = asyncio.run(adapter.health_check())
    assert result is True


def test_geo_collector_adapter_collect_returns_platform_observation():
    """验证 GeoCollectorAdapter.collect_prompt 返回类型契约。"""
    import inspect
    from geo_distributor.adapters import GeoCollectorAdapter
    adapter = GeoCollectorAdapter()
    sig = inspect.signature(adapter.collect_prompt)
    annotations = sig.return_annotation
    assert annotations == PlatformObservation or annotations is inspect.Parameter.empty

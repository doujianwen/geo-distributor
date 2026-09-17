"""测试：配置加载。"""

import os
import sys
import pytest

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geo_distributor.config import (
    load_settings, load_engines,
    get_project_root, get_geo_collector_root,
    get_elmo_config,
)


def test_get_project_root():
    root = get_project_root()
    assert os.path.isdir(root)
    assert os.path.basename(root) == "geo-distributor"


def test_get_geo_collector_root():
    root = get_geo_collector_root()
    assert os.path.isdir(root)
    assert os.path.basename(root) == "geo-collector"


def test_load_settings():
    settings = load_settings()
    assert isinstance(settings, dict)
    assert "brand" in settings
    assert settings["brand"] == "Hydroviv"


def test_load_engines():
    engines = load_engines()
    assert isinstance(engines, dict)
    assert "engines" in engines
    engine_keys = list(engines["engines"].keys())
    assert "chatgpt" in engine_keys
    assert "perplexity" in engine_keys


def test_load_settings_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom.yaml"
    custom.write_text("brand: TestBrand\nproxy: http://test:8080\n", encoding="utf-8")
    monkeypatch.setenv("GEO_DISTRIBUTOR_CONFIG", str(custom))
    load_settings.cache_clear()
    result = load_settings()
    assert result["brand"] == "TestBrand"
    load_settings.cache_clear()
    assert result["proxy"] == "http://test:8080"


def test_ensure_sys_path():
    from geo_distributor.config import ensure_sys_path
    ensure_sys_path()
    collector_root = get_geo_collector_root()
    assert collector_root in sys.path


def test_get_elmo_config():
    """Elmo 配置可从 settings 中获取。"""
    cfg = get_elmo_config()
    assert isinstance(cfg, dict)
    assert cfg.get("version") == "v0.3.0"
    # base_url 来自配置文件，可能因环境而异
    assert "base_url" in cfg
    assert cfg.get("enabled") in [True, False]


def test_get_elmo_config_missing_section(tmp_path, monkeypatch):
    """缺少 elmo section 时返回空 dict。"""
    custom = tmp_path / "no_elmo.yaml"
    custom.write_text("brand: TestBrand\n", encoding="utf-8")
    monkeypatch.setenv("GEO_DISTRIBUTOR_CONFIG", str(custom))
    load_settings.cache_clear()
    cfg = get_elmo_config()
    assert cfg == {}
    load_settings.cache_clear()

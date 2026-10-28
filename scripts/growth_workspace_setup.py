"""Explicit schema-only setup: never copies canonical historical rows or touches its schema."""
import os
from pathlib import Path
import sqlite3
from api.growth_core import contract, DEFAULT_ROOT


def _core_root() -> Path:
    """增长核心根目录：优先 GEO_GROWTH_CORE_ROOT。

    原先直接引用 DEFAULT_ROOT（硬编码的 Windows 开发路径），在 Linux 部署上
    会因为该路径是相对路径而让 Path.as_uri() 抛 ValueError，无法建库。
    """
    return Path(os.environ.get('GEO_GROWTH_CORE_ROOT', str(DEFAULT_ROOT))).resolve()


def create_core(path):
    path=Path(path)
    if path.exists():
        raise RuntimeError('Refusing to overwrite an existing Growth database')
    path.parent.mkdir(parents=True,exist_ok=True)
    original=sqlite3.connect((_core_root()/'geo_intent.db').as_uri()+'?mode=ro',uri=True)
    try:
        # A new empty workspace must not inherit the live database's deployment
        # fence. Its own write cutover is installed explicitly when it is adopted.
        schema=original.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'portal_fence_%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END").fetchall()
    finally: original.close()
    c=sqlite3.connect(path)
    try:
        for _,_,sql in schema: c.execute(sql)
        contract().initialize(c)
    finally:c.close()
    return path

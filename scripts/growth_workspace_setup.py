"""Explicit schema-only setup: never copies canonical historical rows or touches its schema."""
from pathlib import Path
import sqlite3
from api.growth_core import contract, DEFAULT_ROOT


def create_core(path):
    path=Path(path)
    if path.exists():
        raise RuntimeError('Refusing to overwrite an existing Growth database')
    path.parent.mkdir(parents=True,exist_ok=True)
    original=sqlite3.connect((DEFAULT_ROOT/'geo_intent.db').as_uri()+'?mode=ro',uri=True)
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

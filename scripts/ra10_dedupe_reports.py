#!/usr/bin/env python3
"""RA-10 加固 · 一次性数据修复：reports_projection 按 (project_id, tenant_id, scope_version) 去重。

背景（2026-10-17 实测）：唯一约束落地前，并发/重试交付在实时库产生重复报告
（PRJ-B03106CA/T-E2E-SMOKE/scope1 共 5 条）。本脚本保留每组最早 created_at 一条，
删除其余重复行。幂等：无重复时为 no-op。

用法：
    python scripts/ra10_dedupe_reports.py [--db PATH] [--dry-run]

退出码：0 = 成功（含 no-op）；1 = 失败（异常或删除后仍存在重复）。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "geo_distributor.db"


def find_duplicates(conn: sqlite3.Connection) -> dict:
    """返回 {(project_id, tenant_id, scope_version): [row dicts]}，仅含 >1 的组。"""
    rows = conn.execute(
        "SELECT id, tenant_id, project_id, payload, updated_at FROM reports_projection"
    ).fetchall()
    groups: dict = defaultdict(list)
    for rid, tenant, project, payload, updated in rows:
        sv = json.loads(payload).get("scope_version")
        groups[(project, tenant, sv)].append(
            {"id": rid, "created_at": json.loads(payload).get("created_at"), "updated_at": updated}
        )
    return {k: v for k, v in groups.items() if len(v) > 1}


def dedupe(conn: sqlite3.Connection, dry_run: bool) -> list:
    dups = find_duplicates(conn)
    removed = []
    for (project, tenant, sv), rows in sorted(dups.items()):
        # 保留最早 created_at（缺失时回退 updated_at）；平局取 id 字典序最小，保证可复现
        rows_sorted = sorted(rows, key=lambda r: (r["created_at"] or r["updated_at"], r["id"]))
        keep, drop = rows_sorted[0], rows_sorted[1:]
        print(f"[dup] project={project} tenant={tenant} scope={sv}: "
              f"keep={keep['id']} ({keep['created_at']}), remove={[r['id'] for r in drop]}")
        for r in drop:
            removed.append({"project": project, "tenant": tenant, "scope": sv, "removed_id": r["id"]})
            if not dry_run:
                conn.execute("DELETE FROM reports_projection WHERE id = ?", (r["id"],))
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=os.environ.get("GEO_DISTRIBUTOR_DB", str(DEFAULT_DB)))
    ap.add_argument("--dry-run", action="store_true", help="只报告，不删除")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[error] db not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        removed = dedupe(conn, dry_run=args.dry_run)
        if not removed:
            print("[ok] no duplicate (project, tenant, scope_version) groups — nothing to do")
            return 0
        if args.dry_run:
            print(f"[dry-run] would remove {len(removed)} duplicate row(s); no changes made")
            return 0
        conn.commit()
        # 删除后自检：必须清零，否则判失败（不伪造成功）
        remaining = find_duplicates(conn)
        if remaining:
            print(f"[error] duplicates remain after dedupe: {remaining}", file=sys.stderr)
            return 1
        print(f"[ok] removed {len(removed)} duplicate row(s); post-check clean")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
# ============================================================
# RA-11 可观测性 · 本地健康检查（告警钩子）
# ------------------------------------------------------------
# 用途: 对 geo-distributor 本地演示环境做一轮完整健康探测，
#       任一判据失败即退出码 1（可被计划任务/CI 捕获后触发告警，
#       如飞书 Webhook——参照 bookconv FEISHU_WEBHOOK_URL 模式）。
#
# 判据:
#   C1  /health HTTP 200 且 body 为 {"status":"ok"}
#   C2  持久化: data/geo_distributor.db 存在且 reports_projection 可读
#   C3  数据完整性: PRAGMA quick_check == ok
#   C4  幂等约束: ux_reports_projection_ptv 唯一索引存在
#   C5  审计日志: data/audit_log.db 存在且 audit_log 行数 > 0
#   C6  (可选, 传 --with-apache) 经 Apache 反代 /geo-api/health 可达
#
# 用法:  bash scripts/health_check.sh [--with-apache] [--base-url URL]
# 退出:  0 = 全部通过;  1 = 任一失败（失败项逐条打印 [FAIL]）
#
# ⚠️ 环境说明（2026-10-17 V2 终裁）:
#   本脚本为 MSYS/Git Bash 环境兼容版本——依赖 curl 与 bash heredoc，
#   仅保证在 Git Bash / MSYS 下行为正确。Windows 原生环境（PowerShell、
#   Windows 计划任务）请使用 scripts/health_check.ps1（判据完全一致），
#   详见 scripts/README_HEALTH_CHECK.md。
# ============================================================
set -uo pipefail
cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://127.0.0.1:8765}"
WITH_APACHE=0
[ "${1:-}" = "--with-apache" ] && WITH_APACHE=1

FAILS=0
fail() { echo "[FAIL] $1"; FAILS=$((FAILS+1)); }
pass() { echo "[PASS] $1"; }

# C1 /health
HTTP=$(curl -s -o /tmp/health_body.$$ -w "%{http_code}" --max-time 5 "$BASE_URL/health" 2>/dev/null)
BODY=$(cat /tmp/health_body.$$ 2>/dev/null); rm -f /tmp/health_body.$$
if [ "$HTTP" = "200" ] && [ "$BODY" = '{"status":"ok"}' ]; then
    pass "C1 /health 200 + status ok"
else
    fail "C1 /health -> HTTP=$HTTP body=$BODY"
fi

# C2/C3/C4/C5 持久化与完整性
DB="data/geo_distributor.db"
PY=.venv/Scripts/python.exe
[ -x "$PY" ] || PY=python

if [ -f "$DB" ]; then
    pass "C2 db file exists: $DB"
    "$PY" - "$DB" <<'PYEOF' || FAILS=$((FAILS+1))
import sqlite3, sys
db = sys.argv[1]
c = sqlite3.connect(db)
try:
    n = c.execute("SELECT COUNT(*) FROM reports_projection").fetchone()[0]
    print(f"[PASS] C2 reports_projection readable, rows={n}")
except Exception as e:
    print(f"[FAIL] C2 reports_projection unreadable: {e}"); sys.exit(1)
qc = c.execute("PRAGMA quick_check").fetchone()[0]
print(f"[{'PASS' if qc=='ok' else 'FAIL'}] C3 quick_check = {qc}")
if qc != "ok": sys.exit(1)
idx = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='ux_reports_projection_ptv'").fetchone()[0]
print(f"[{'PASS' if idx else 'FAIL'}] C4 unique index ux_reports_projection_ptv present = {bool(idx)}")
if not idx: sys.exit(1)
sys.exit(0)
PYEOF
else
    fail "C2 db file missing: $DB"
    FAILS=$((FAILS+1))
fi

AUDIT="data/audit_log.db"
if [ -f "$AUDIT" ]; then
    ROWS=$("$PY" -c "import sqlite3;print(sqlite3.connect('$AUDIT').execute('SELECT COUNT(*) FROM audit_log').fetchone()[0])" 2>/dev/null || echo 0)
    if [ "${ROWS:-0}" -gt 0 ] 2>/dev/null; then
        pass "C5 audit_log.db rows=$ROWS"
    else
        fail "C5 audit_log.db empty/unreadable rows=$ROWS"
    fi
else
    fail "C5 audit_log.db missing"
fi

# C6 可选 Apache 反代探针
if [ "$WITH_APACHE" = "1" ]; then
    AHTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://geo-growth.local/geo-api/health" 2>/dev/null)
    if [ "$AHTTP" = "200" ]; then
        pass "C6 apache /geo-api/health 200"
    else
        fail "C6 apache /geo-api/health -> $AHTTP"
    fi
fi

echo "----------------------------------------"
if [ "$FAILS" -gt 0 ]; then
    echo "HEALTH_CHECK: FAIL ($FAILS failure(s))"
    exit 1
fi
echo "HEALTH_CHECK: PASS (all criteria green)"
exit 0

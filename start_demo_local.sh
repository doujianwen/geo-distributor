#!/bin/bash
# ============================================================
# GEO 渠道商演示环境 · 本地规范启动入口（RA-01 持久化整改产物）
# 任务: GGS-FULL-RELEASE-CLOSURE-20261017-V1
# ------------------------------------------------------------
# 作用:
#   - 以 SQLite 持久化模式启动 geo-distributor（RA-01 修复）
#   - 数据库路径唯一且固定: <repo>/data/geo_distributor.db
#   - 审计库: <repo>/data/audit_log.db（audit.py 默认，未显式覆盖）
#   - 绑定 127.0.0.1:8765（对外由 Apache 反代 /geo-api/ 暴露）
#
# 优先级说明（与 geo_distributor/persistence/sqlite_repository.py 一致）:
#   显式参数 > 环境变量 GEO_DISTRIBUTOR_DB > 默认(内存)
#   本脚本显式 export GEO_DISTRIBUTOR_DB，杜绝内存回退。
#
# 用法:  bash start_demo_local.sh [PORT]   # 默认 8765
# 停止:  通过 PID 文件 kill（见 data/distributor.pid）
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8765}"
export GEO_DISTRIBUTOR_DB="$(pwd)/data/geo_distributor.db"
export GEO_DISTRIBUTOR_AUDIT_DB="$(pwd)/data/audit_log.db"

echo "[demo] GEO_DISTRIBUTOR_DB=${GEO_DISTRIBUTOR_DB}"
echo "[demo] starting uvicorn on 127.0.0.1:${PORT} (sqlite persist mode)"

# RA-01/V2 修正（2026-10-17）：
#   ① 原 `echo $$` 记录外层 shell PID，与真实 uvicorn PID 不符；
#   ② 改用 `$!` 后实测仍不符（Git-Bash/MSYS PID 映射：$!=10355 ≠ Windows 监听进程 27332）。
# 最终方案：后台启动后按端口反查 Windows 真实监听 PID 写入 pid 文件；
# 停机流程同样按端口反查（见 stop_demo_local.sh），不信任任何静态 PID。
.venv/Scripts/python.exe -m uvicorn api.app:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --no-server-header &
UVICORN_JOB=$!

REAL_PID=""
for _ in $(seq 1 20); do
    sleep 0.5
    REAL_PID=$(netstat -ano | grep "127.0.0.1:$PORT " | grep LISTENING | awk '{print $NF}' | head -1 || true)
    if [ -n "$REAL_PID" ]; then break; fi
done
if [ -n "$REAL_PID" ]; then
    echo "$REAL_PID" > data/distributor.pid
    echo "[demo] uvicorn windows pid=${REAL_PID} (recorded in data/distributor.pid)"
else
    echo "[demo] WARN: could not resolve listener pid for port ${PORT}" >&2
fi
wait "$UVICORN_JOB"

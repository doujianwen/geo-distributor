#!/bin/bash
# ============================================================
# GEO 渠道商演示环境 · 本地规范停止入口（RA-01 持久化整改配套）
# 任务: GGS-REMAINING-RELEASE-BLOCKERS-CLOSURE-20261017-V2
# ------------------------------------------------------------
# 作用: 按端口反查真实监听 PID 并停止 geo-distributor。
# 为何不读 data/distributor.pid:
#   Git-Bash/MSYS 环境下 $! 与 Windows 进程 PID 存在映射偏差
#   （实测 $!=10355 而真实监听进程=27332），静态 PID 文件不可信。
#   端口反查是唯一可靠的停机判据。
# 用法:  bash stop_demo_local.sh [PORT]   # 默认 8765
# ============================================================
set -euo pipefail

PORT="${1:-8765}"

PID=$(netstat -ano | grep "127.0.0.1:$PORT " | grep LISTENING | awk '{print $NF}' | head -1 || true)

if [ -z "$PID" ]; then
    echo "[demo] nothing listening on 127.0.0.1:${PORT}; already stopped."
    exit 0
fi

echo "[demo] stopping geo-distributor pid=${PID} (port ${PORT})"
MSYS_NO_PATHCONV=1 taskkill /PID "$PID" /F

# 等待端口释放（最多 10s）
for _ in $(seq 1 20); do
    sleep 0.5
    if ! netstat -ano | grep "127.0.0.1:$PORT " | grep -q LISTENING; then
        echo "[demo] port ${PORT} released."
        exit 0
    fi
done

echo "[demo] WARN: port ${PORT} still in use after kill" >&2
exit 1

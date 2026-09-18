#!/bin/bash
# Start GEO Distributor V2 Web API
#
# Usage:
#   ./start_api.sh [PORT]           # 内存模式（默认，重启即失）
#   ./start_api.sh [PORT] persist   # SQLite 持久化模式（跨重启保留）
#
# 也可直接设置环境变量（优先级高于第二个参数）：
#   GEO_DISTRIBUTOR_DB=data/geo_distributor.db ./start_api.sh
#   GEO_DISTRIBUTOR_DB=1 ./start_api.sh        # 开关值 → 落到默认路径

cd "$(dirname "$0")"
PORT="${1:-8765}"
MODE="${2:-}"

DEFAULT_DB="$(pwd)/data/geo_distributor.db"

if [ -z "$GEO_DISTRIBUTOR_DB" ] && [ "$MODE" = "persist" ]; then
    export GEO_DISTRIBUTOR_DB="$DEFAULT_DB"
fi

echo "Starting GEO Distributor V2 Web API on port $PORT..."
if [ -n "$GEO_DISTRIBUTOR_DB" ]; then
    echo "Persistence:  SQLite ($GEO_DISTRIBUTOR_DB)"
else
    echo "Persistence:  In-Memory (data lost on restart; use './start_api.sh $PORT persist')"
fi
echo "API Docs:     http://127.0.0.1:${PORT}/docs"
echo "ReDoc:        http://127.0.0.1:${PORT}/redoc"
echo "OpenAPI JSON: http://127.0.0.1:${PORT}/openapi.json"
echo ""

.venv/Scripts/python.exe -m uvicorn api.app:app --host 127.0.0.1 --port "$PORT" --reload

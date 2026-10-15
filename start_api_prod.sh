#!/bin/bash
# Start GEO Distributor V2 Web API — 生产模式
#
# 与 start_api.sh（开发模式）的区别：
#   - 不带 --reload（生产必须关闭热重载：会监视文件系统、占用额外进程）
#   - 强制 GEO_DISTRIBUTOR_ENV=production（禁用内置开发密钥）
#   - 强制绑定 127.0.0.1（对外暴露由反向代理负责，TLS 在代理层终止）
#
# 部署检查清单：
#   1. 反向代理已配置 TLS，且**不得**把 8765 直接暴露公网
#   2. GEO_DISTRIBUTOR_API_KEYS 已设置（生产密钥，不要用 dev/test）
#   3. GEO_DISTRIBUTOR_CORS_ORIGINS 已设置为 WordPress 域名
#   4. GEO_DISTRIBUTOR_DB 指向持久化路径
#   5. GEO_DISTRIBUTOR_AUDIT_DB 指向审计库路径（可审计文件）
#
# 用法：
#   ./start_api_prod.sh [PORT]
#
# 持久化（强烈建议生产使用）：
#   GEO_DISTRIBUTOR_DB=/var/lib/geo-distributor/geo.db ./start_api_prod.sh

set -euo pipefail

cd "$(dirname "$0")"
PORT="${1:-8765}"

# ---- 生产环境强制项 ----
export GEO_DISTRIBUTOR_ENV=production

# 未配置密钥时直接拒绝启动 —— 宁可起不来，也不要裸奔
if [ -z "${GEO_DISTRIBUTOR_API_KEYS:-}" ]; then
    echo "ERROR: GEO_DISTRIBUTOR_API_KEYS 未设置，拒绝以无认证状态启动。"
    echo ""
    echo "  生成密钥："
    echo "    python -c \"import secrets;print('sk-'+secrets.token_urlsafe(32))\""
    echo ""
    echo "  配置示例（写入 .env 或由进程管理器注入）："
    echo "    export GEO_DISTRIBUTOR_API_KEYS='DST-001:sk-xxx:DISTRIBUTOR_ADMIN'"
    echo ""
    echo "  如仅做本地验证，请用 ./start_api.sh（开发模式）。"
    exit 1
fi

DEFAULT_DB="$(pwd)/data/geo_distributor.db"
if [ -z "${GEO_DISTRIBUTOR_DB:-}" ]; then
    export GEO_DISTRIBUTOR_DB="$DEFAULT_DB"
fi

# 审计库：默认与业务库同目录的独立文件
if [ -z "${GEO_DISTRIBUTOR_AUDIT_DB:-}" ]; then
    export GEO_DISTRIBUTOR_AUDIT_DB="$(pwd)/data/audit_log.db"
fi

# 限流默认值（可被环境变量覆盖）
export GEO_DISTRIBUTOR_RATE_LIMIT="${GEO_DISTRIBUTOR_RATE_LIMIT:-120}"
export GEO_DISTRIBUTOR_RATE_BURST="${GEO_DISTRIBUTOR_RATE_BURST:-40}"

echo "=========================================="
echo " GEO Distributor API — PRODUCTION MODE"
echo "=========================================="
echo "绑定:          127.0.0.1:${PORT}（仅本机，对外需反向代理）"
echo "Persistence:SQLite ($GEO_DISTRIBUTOR_DB)"
echo "Audit:        SQLite ($GEO_DISTRIBUTOR_AUDIT_DB)"
echo "Rate limit:   ${GEO_DISTRIBUTOR_RATE_LIMIT}/min, burst ${GEO_DISTRIBUTOR_RATE_BURST}"
echo "API Docs:     已关闭（如需开启设 GEO_DISTRIBUTOR_EXPOSE_DOCS=1）"
echo "Health:       http://127.0.0.1:${PORT}/health"
echo ""
echo "已注册租户:   $(echo "$GEO_DISTRIBUTOR_API_KEYS" | tr ',' '\n' | grep -c ':' || echo 0) 个"
echo "=========================================="
echo ""

# 注意：此处刻意**不加** --reload
# --no-server-header：抑制 `Server: uvicorn`。
# 该响应头由 uvicorn 在 ASGI 层之外注入，应用层中间件**删不掉**，
# 只能由服务器层关闭。反代侧另有 server_tokens off 作为第二层。
exec .venv/Scripts/python.exe -m uvicorn api.app:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --no-access-log \
    --no-server-header

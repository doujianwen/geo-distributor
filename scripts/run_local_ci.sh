#!/usr/bin/env bash
# run_local_ci.sh — GEO 渠道商演示环境本地可复现测试流水线（RA-03 整改产物）
#
# 任务: GGS-REMAINING-RELEASE-BLOCKERS-CLOSURE-20261017-V2
# 用途: 在无外部 CI 平台时，提供与 CI 等价的本地构建+测试入口。
#       严格使用 requirements.lock（钉死版本），保证可复现。
#
# 用法:
#   bash scripts/run_local_ci.sh            # 使用仓库内 .venv（已存在则复用）
#   bash scripts/run_local_ci.sh --fresh    # 删除并重建 .venv，从 lock 全新安装
#
# 不变量:
#   - 永不触碰 data/geo_distributor.db（测试环境 GEO_DISTRIBUTOR_ENV=test 走内存仓储）
#   - 依赖一律来自 requirements.lock，不浮动升级
#   - 测试失败以非零退出码返回，供自动化判定

set -euo pipefail

PY="${PYTHON:-python3}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FRESH=0
[[ "${1:-}" == "--fresh" ]] && FRESH=1

echo "[ci] repo root: $REPO_ROOT"
echo "[ci] python: $($PY --version 2>&1)"

if [[ $FRESH -eq 1 ]]; then
  echo "[ci] --fresh: rebuilding .venv from requirements.lock"
  rm -rf .venv
fi

if [[ ! -x .venv/Scripts/python.exe && ! -x .venv/bin/python ]]; then
  echo "[ci] creating venv..."
  "$PY" -m venv .venv
fi

VENV_PY=".venv/Scripts/python.exe"
[[ -x "$VENV_PY" ]] || VENV_PY=".venv/bin/python"

echo "[ci] installing dependencies from requirements.lock (pinned)..."
"$VENV_PY" -m pip install -q -r requirements.lock

echo "[ci] lock vs installed diff (empty = reproducible):"
if diff <("$VENV_PY" -m pip freeze 2>/dev/null | grep '==') <(grep '==' requirements.lock); then
  echo "[ci]   LOCK_REPRODUCIBLE: identical pinned set"
else
  echo "[ci]   WARNING: installed set differs from lock"
fi

echo "[ci] running test suite (GEO_DISTRIBUTOR_ENV=test -> in-memory repos)..."
export GEO_DISTRIBUTOR_ENV=test
"$VENV_PY" -m pytest -q -rf -p no:cacheprovider tests/ "$@"
RC=$?
echo "[ci] pytest exit code: $RC"
exit $RC

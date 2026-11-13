#!/usr/bin/env bash
# 云搜浏览器 一键启动（macOS / Linux 开发机）。参数同 run.py，例如 ./start.sh --dev
set -euo pipefail
cd "$(dirname "$0")"
for p in python3.13 python3.12 python3 python; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    exec "$p" run.py "$@"
  fi
done
echo "[错误] 需要 Python 3.12 或 3.13" >&2
exit 1

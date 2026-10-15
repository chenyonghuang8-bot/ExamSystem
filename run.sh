#!/usr/bin/env bash
# 本机常驻运行（无 Docker 时）：自动重启
cd "$(dirname "$0")"
PY=${PY:-/workspace/venv/bin/python}
while true; do
  $PY -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 >> data/server.log 2>&1
  sleep 2
done

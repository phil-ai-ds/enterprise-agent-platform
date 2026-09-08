#!/usr/bin/env bash
# 本地启动 Enterprise Agent Platform
set -e
cd "$(dirname "$0")"
cd backend
if [ ! -d "../.venv" ]; then
  echo "创建虚拟环境…"
  /Users/eaglezpf/.hermes/hermes-agent/venv/bin/python3 -m venv ../.venv
  ../.venv/bin/pip install -q -r requirements.txt
fi
echo "启动 http://localhost:8000  (admin/alice/bob · demo123)"
exec ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

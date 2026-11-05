#!/usr/bin/env bash
# folio-local launcher for Linux/macOS: venv + deps + server.
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

if [ ! -x ".venv/bin/uvicorn" ]; then
    echo "Installing dependencies..."
    .venv/bin/pip install -r requirements.txt
fi

PORT="${FOLIO_PORT:-8000}"
echo "Starting folio-local on http://127.0.0.1:${PORT} ..."
exec .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port "${PORT}"

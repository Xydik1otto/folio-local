#!/usr/bin/env bash
# Deploy folio-local on a plain host — no containers needed: venv + uvicorn
# (systemd-friendly).
# Usage:
#   ./scripts/deploy-local.sh              # install deps, then serve on 127.0.0.1:8000
#   FOLIO_HOST=0.0.0.0 FOLIO_PORT=8080 ./scripts/deploy-local.sh
#   ./scripts/deploy-local.sh --install-only   # prepare venv, do not start the server
# Auth (optional, expose only behind HTTPS reverse proxy):
#   FOLIO_AUTH_USER / FOLIO_AUTH_PASSWORD  (see README)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

HOST="${FOLIO_HOST:-127.0.0.1}"
PORT="${FOLIO_PORT:-8000}"
INSTALL_ONLY=0
case "${1:-}" in
  --install-only) INSTALL_ONLY=1 ;;
  ""|--help|-h)
    if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
      sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# //'
      exit 0
    fi
    ;;
  *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-python3}"
if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON} not found (Python 3.10+ required)" >&2
  exit 1
fi

# 1. Virtual environment (idempotent)
if [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/Scripts/python.exe" ]; then
  echo "==> creating virtualenv .venv"
  "${PYTHON}" -m venv .venv
fi
if [ -x ".venv/bin/python" ]; then VENV_PY=".venv/bin/python"; else VENV_PY=".venv/Scripts/python.exe"; fi

# 2. Dependencies
echo "==> installing requirements"
"${VENV_PY}" -m pip install --upgrade pip >/dev/null
"${VENV_PY}" -m pip install -r requirements.txt

# 3. Database (creates folio.db with the current schema if absent; the
#    default path is the repo root, overridable via FOLIO_DB)
echo "==> initializing database"
"${VENV_PY}" -c "from backend.db import init_db; init_db(); print('db ok')"

if [ "${INSTALL_ONLY}" = "1" ]; then
  echo "==> install complete; start later with: ${VENV_PY} -m uvicorn backend.main:app --host ${HOST} --port ${PORT}"
  exit 0
fi

# 4. Serve (foreground; systemd/supervisor handle restarts)
echo "==> starting http://${HOST}:${PORT}"
exec "${VENV_PY}" -m uvicorn backend.main:app --host "${HOST}" --port "${PORT}"

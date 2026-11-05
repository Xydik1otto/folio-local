#!/usr/bin/env bash
# Smoke test folio-local: uvicorn on a random port -> curl checks -> PASS/FAIL.
# Usage: bash scripts/smoke.sh   (no Docker, no API keys needed)
set -u
cd "$(dirname "$0")/.."

PORT=$(( (RANDOM % 5000) + 40000 ))
DB_FILE="${TMPDIR:-/tmp}/folio-smoke-$$-$RANDOM.db"
export FOLIO_DB="$DB_FILE"

cleanup() {
  [ -n "${SRV:-}" ] && kill "$SRV" 2>/dev/null
  rm -f "$DB_FILE"
}
trap cleanup EXIT

python -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" \
  --log-level warning &
SRV=$!

# wait for readiness (max ~15s)
ready=0
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  echo "SMOKE: FAIL (server did not start on port $PORT)"
  exit 1
fi

BASE="http://127.0.0.1:$PORT"
fail=0
check() { # label, url, expected substring
  if curl -sf "$2" | grep -q "$3"; then
    echo "  ok   $1"
  else
    echo "  FAIL $1"
    fail=1
  fi
}

check "GET /api/health"        "$BASE/api/health" '"status":"ok"'

acc=$(curl -sf -X POST "$BASE/api/accounts" \
  -H 'content-type: application/json' -d '{"name":"Smoke","currency":"EUR"}')
if echo "$acc" | grep -q '"id"'; then echo "  ok   POST /api/accounts"; else echo "  FAIL POST /api/accounts"; fail=1; fi

curl -sf -X POST "$BASE/api/transactions" -H 'content-type: application/json' \
  -d '{"account_id":1,"type":"deposit","date":"2024-01-01","amount":1000,"currency":"EUR"}' \
  | grep -q '"id"' && echo "  ok   POST /api/transactions" || { echo "  FAIL POST /api/transactions"; fail=1; }

check "GET /api/accounts"      "$BASE/api/accounts"            '"currency"'
check "GET /api/portfolio"     "$BASE/api/portfolio?account_id=1"     '"total"'
check "GET /api/holdings"      "$BASE/api/holdings?account_id=1"      '"holdings"'
check "GET /api/portfolio/allocation" "$BASE/api/portfolio/allocation?account_id=1" '"groups"'
check "GET /api/warnings"      "$BASE/api/warnings?account_id=1"      '"warnings"'
check "GET /api/tax/preview"   "$BASE/api/tax/preview?account_id=1&year=2024" '"sales"'
check "GET /api/tax/export csv" "$BASE/api/tax/export?account_id=1&year=2024&format=csv" 'date,ticker'
check "GET / (UI)"             "$BASE/" 'folio-local'

if [ "$fail" -eq 0 ]; then
  echo "SMOKE: PASS"
else
  echo "SMOKE: FAIL"
fi
exit "$fail"

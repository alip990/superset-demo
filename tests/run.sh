#!/bin/sh
# Every test in this repo. No third-party Python package is needed.
#
#   tests/run.sh                      calendar core, ranges, grains (SQLite), plugin
#   JALALI_TEST_PG_DSN=... tests/run.sh   ... and the same grains in PostgreSQL,
#                                         plus db/jalali.sql
#   SUPERSET_URL=... tests/run.sh         ... and the Jalali date filter against a
#                                         running Superset (tests/test_filter_binding.py)
#
# Against the demo stack (psycopg2 and the SQL library are already there):
#   docker compose cp . superset:/tmp/repo 2>/dev/null || true
#   docker compose exec -T db psql -U postgres -d demo < db/jalali.sql
#   docker compose exec superset bash -lc '
#     cd /tmp/repo && JALALI_TEST_PG_DSN=postgresql://postgres:postgres@db:5432/demo \
#     PYTHONPATH=superset /app/.venv/bin/python -m unittest discover -s tests -v'
set -e
cd "$(dirname "$0")/.."

echo "== python =="
"${PYTHON:-python3}" -m unittest discover -s tests -v

echo
echo "== plugins/superset-jalali =="
if [ -d plugins/superset-jalali/node_modules ]; then
  (cd plugins/superset-jalali && npm run --silent check)
else
  echo "ERROR: missing frontend test dependencies; run npm ci in plugins/superset-jalali" >&2
  exit 1
fi

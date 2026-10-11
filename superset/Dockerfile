ARG SUPERSET_JALALI_REF=14a7a6a6af81a538afa53c69dced44f687ace8ac

# Once superset-jalali is on PyPI, replace the two build stages with
# uv pip install superset-jalali==<version> in Superset's Python environment.
FROM node:22-bookworm-slim AS jalali-js
ARG SUPERSET_JALALI_REF
RUN apt-get update && apt-get install -y --no-install-recommends git python3 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/alip990/superset-jalali /src && git -C /src checkout "$SUPERSET_JALALI_REF"
WORKDIR /src/frontend
RUN npm ci && npm run build

FROM python:3.11-slim AS jalali-wheel
COPY --from=jalali-js /src /src
RUN pip wheel --no-deps -w /wheels /src
RUN python - <<'PY'
import json
from pathlib import Path
from zipfile import ZipFile

with ZipFile(next(Path('/wheels').glob('superset_jalali-*.whl'))) as wheel:
    manifest = 'superset_jalali/static/manifest.json'
    assert manifest in wheel.namelist(), 'Jalali manifest missing from wheel'
    bundle = json.loads(wheel.read(manifest))['bundle']
    assert 'superset_jalali/static/' + bundle in wheel.namelist(), 'Jalali bundle missing from wheel'
PY

FROM apache/superset:6.1.0
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary==2.9.13
COPY --from=jalali-wheel /wheels /tmp/wheels
RUN uv pip install --python /app/.venv/bin/python --no-cache /tmp/wheels/superset_jalali-*.whl && rm -rf /tmp/wheels
USER superset

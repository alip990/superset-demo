# Superset 6.1.0 + psycopg2 + the Jalali calendar frontend (plugins/superset-jalali).
# Build context is the repo root (see docker-compose.yml and .dockerignore):
#   docker compose build superset
#
# Only the *frontend* half of the Jalali feature needs this image: Superset has no
# runtime hook for time formatters or for the date picker, so the 6.1.0 frontend is
# rebuilt from the same tag as the backend and its static assets replace the ones in
# the published image as a whole (chunk names and manifest.json must match). The
# backend half (time grains, the Jalali time-range vocabulary, the dataset macros)
# is pure config and works on the stock image - see superset/jalali_calendar/.
# Needs ~8 GB RAM and ~20-40 min the first time.
ARG SUPERSET_VERSION=6.1.0

FROM node:22-trixie-slim AS node-base
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates build-essential python3 zstd perl \
    && rm -rf /var/lib/apt/lists/*

# Superset source at the backend's tag. Cloned by default; to use a local checkout of
# the same tag instead (e.g. slow/flaky network):
#   docker build --build-context superset-src=/path/to/superset -f superset/Dockerfile .
FROM node-base AS superset-clone
ARG SUPERSET_VERSION
RUN git clone --depth 1 --branch ${SUPERSET_VERSION} https://github.com/apache/superset /src
FROM scratch AS superset-src
COPY --from=superset-clone /src /

FROM node-base AS frontend
COPY --from=superset-src /superset-frontend /app/superset-frontend
WORKDIR /app/superset-frontend
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
RUN --mount=type=cache,target=/root/.npm npm ci
# the plugin's sources, then the three patches that hook them into upstream's own
# setup, date-filter popover and time-range label (patches/apply.sh is idempotent
# and fails the build if a Superset upgrade moved the code it edits)
COPY plugins/superset-jalali/src/ src/jalali/
COPY plugins/superset-jalali/patches/ /tmp/jalali-patches/
RUN sh /tmp/jalali-patches/apply.sh && npm run build

FROM apache/superset:${SUPERSET_VERSION}
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache psycopg2-binary==2.9.13
RUN rm -rf /app/superset/static/assets
COPY --from=frontend --chown=superset:superset /app/superset/static/assets /app/superset/static/assets
USER superset

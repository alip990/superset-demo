# Jalali package migration: 6.1.0 compatibility gate

## Outcome

The extension API in Apache Superset 6.1.0 discovers and loads a `.supx` in the main authenticated application. The real-host browser test observes its `remoteEntry` request and the documented `window.superset.extensions` API after startup; it does not prove that a contributed SQL Lab view renders. The public extension API cannot replace native time-filter controls in this release. Therefore this repository deliberately does not package its calendar picker as an independently installable `.supx`. The existing patched frontend remains the only route that displays that picker in `CustomFrame`; `superset/Dockerfile` still rebuilds and replaces Superset assets for that route. The independent host-install requirement is blocked pending an upstream API or a supported alternative in a released Superset version.

The `.supx` under `dist/active` during local acceptance is only a diagnostic, labelled as such in its manifest. Remove it before any shared deployment. The backend wheel is independent of Superset's frontend build, but it is not a public-API-only backend extension: it has a 6.1.0 guard and an isolated `FLASK_APP_MUTATOR` compatibility adapter which wraps `get_since_until`, changes frontend configuration, and registers time-grain settings. Treat this hook as version-pinned integration code.

## Proven host contract

The target release and prebuilt image are pinned in `deployment/independent/compose.yaml`: `apache/superset:6.1.0`, manifest version `6.1.0`, SHA-256 image digest `16b50bbef6648912a79e3293d418fefa743ce555d36c5af6b85d859119ed7f88`. This is a verified official image used by the isolated lab, not a claim about any remote deployment. The repository's `superset-demo:6.1.0-pg` image is only a donor for the already installed Postgres 2.9.13 client libraries in a local sidecar; the running Superset service uses the official digest above. It is never started as the host.

The release-tag source check can be rerun with:

```sh
python3 tools/check_extension_host.py --tag 6.1.0
```

Its report records fetched file hashes and tests the public contract: `@apache-superset/core` exposes no `getExtensionsRegistry`, the native `TimeFilterPlugin` imports and reads that singleton from `@superset-ui/core`, and the host webpack shares React, React DOM and Ant Design without sharing `@superset-ui/core`. An extension's registry instance cannot replace the host singleton. The 6.1.0 host reads the date-control key when its native time-filter plugin renders; registration is not a public contribution point, and a later registration alone does not rerender that filter. The React peer contract in 6.1.0 is React/React DOM 17.0.2. The embedded entrypoint also skips the main app's extension startup path.

The diagnostic package is discovered from `EXTENSIONS_PATH` with `ENABLE_EXTENSIONS` set. Its entrypoint reports the public `extensions` API surface and registers a diagnostic component, including under the arbitrary string `filter.dateFilterControl`; the host date-filter consumer does not render that component. Dashboard baseline tests separately prove an unmodified chart query/result. The strict Dashboard test is expected to fail when it requires a replacement control, which is the negative integration result gating the migration. Explore and embedded dashboards also have distinct initialization paths and are not proven integrations.

## Local build and isolated host

Requires Docker, Node.js 22, Python 3.10+, `uv`, `npm`, the official Superset 6.1.0 image above, and this repository's pre-existing `superset-demo:6.1.0-pg` image for the test-only Postgres client sidecar.

```sh
python3 tools/lab_prepare.py
npm ci --prefix extensions/registry-probe/frontend
(cd extensions/registry-probe && uv run --no-project \
  --with apache-superset-extensions-cli==0.1.0rc3 \
  superset-extensions bundle \
  --output ../../dist/active/jalali-lab.registry-probe-0.1.0.supx)
docker compose -f deployment/independent/compose.yaml up -d web
npm ci --prefix tests/browser
npm --prefix tests/browser test
```

The CI job builds only the backend wheel and calendar source tests. The browser suite uses the real prebuilt host and PostgreSQL fixtures. It proves bundle retrieval/evaluation and extension API presence, plus stock Dashboard rendering and the baseline query result. It does not demonstrate a SQL Lab view, a replacement date control, or a filtered chart result. To enforce the migration acceptance condition and observe the blocker as a failing assertion, run:

```sh
REQUIRE_NATIVE_JALALI=1 npm --prefix tests/browser test -- --grep 'native Dashboard consumer'
```

This required-calendar gate must remain red on 6.1.0. Do not reinterpret the negative test as a successful Jalali installation. Stop the isolated stack with `docker compose -f deployment/independent/compose.yaml down`; the isolated volumes are disposable test data and are not production volumes.

To compare host assets, the official image SHA-256 for `/app/superset/static/assets/manifest.json` is `e070b91a30d10adffca3ded602ff0d714d62f33817974a63900507fdf1237ac2`. The test web container's image ID is the same official image ID; no build of Superset or writes under its asset path are part of this Compose configuration. Check `docker diff jalali-independent-lab-web-1 | grep /app/superset/static/assets` (no output is expected).

## Backend wheel build, compatibility and private release

`pyproject.toml` builds a versioned pure-Python wheel (`superset_jalali_backend-1.1.0-py3-none-any.whl`). It contains only this repository's backend package. It does not include the PostgreSQL SQL library at `db/jalali.sql`; choosing grain `function` requires installing that SQL library into the target PostgreSQL database separately. Inline grains need no database objects. Backend parsing and grains do not install the React picker, change chart colors, or convert arbitrary chart labels. UTC-to-Tehran grain conversion currently advertises PostgreSQL only.

```sh
uv build --wheel --no-sources --out-dir dist
(cd dist && sha256sum superset_jalali_backend-*.whl > SHASUMS256.txt)
```

Source tag `jalali-backend-vX.Y.Z` must exactly match `[project].version`; the workflow tests before building and attaches the pure Python wheel plus SHA-256 file to a private GitHub Release. Source history remains in Git; the release asset is the immutable distribution. There is no direct install-from-Git behavior. The repository uses GitHub (`origin` points to `github.com/alip990/superset-demo`), so GitLab's Generic Package Registry is not assumed. The workflow has not been triggered and no release has been created.

Authenticated install from an existing private release:

```sh
GITHUB_REPOSITORY=alip990/superset-demo GH_TOKEN="$GH_TOKEN" \
  tools/backend-artifact.sh install 1.1.0
```

The token must be read-only for private releases and supplied by the operator's environment. The script checks the downloaded SHA-256, validates wheel name/version, keeps rollback copies outside the `/calendar` mount, enforces one active version, and restarts only the isolated lab's web service. Install a locally built wheel with `tools/backend-artifact.sh local dist/superset_jalali_backend-1.1.0-py3-none-any.whl`; test an upgrade with a second version, then use `tools/backend-artifact.sh rollback VERSION` to select the prior artifact explicitly when multiple versions are archived. `tools/backend-artifact.sh remove` moves the wheel out of the scanned mount, disables the backend hook in the isolated lab env file, and restarts. This local test contract is not a production installer; copy its versioned mount/restart mechanics into the target deployment and supply its actual Superset version, configuration ownership and process manager.

The wheel is loaded from a read-only mount as Python's zipimport source. `deployment/independent/superset_config.py` activates it only when `JALALI_BACKEND_ENABLED=1`, calls its guarded install hook, and expects exactly one wheel. Copy the release artifact into the active mount as described above, set the option, and restart web processes and workers that parse ranges. Rollback uses the archived wheel, restores the previous setting, and restarts the same processes. `EXTENSIONS_PATH` scans only the diagnostic `.supx` path in this lab; archived artifacts are deliberately outside it.

## Calendar contract and remaining correctness limits

Serialized filter endpoints remain Gregorian naive timestamps in the selected storage clock; dashboard/Explore filters use `[start, end)`. `storage_timezone='wall'` preserves local-wall timestamp columns. `storage_timezone='UTC'` converts boundaries using `business_timezone='Asia/Tehran'` and IANA historical offsets. Typed ambiguous/nonexistent times fail instead of silently normalizing; a calendar-day boundary in a midnight timezone gap advances to the first valid instant. A nonzero `shift_minutes` keeps the legacy fixed-offset mode, subtracts the offset on filtering, and cannot be combined with IANA UTC storage. It is not a historical timezone. Browser timezone does not define the business date. New UTC-storage grain SQL is PostgreSQL only and expects naive UTC timestamps.

Calendar arithmetic follows the shared Borkowski implementation. It agrees with ICU 77 across 1900–2200 except the explicit ICU non-leap correction for AP 1502, 2124-03-20 through 2125-03-20 (366 days). The test records this exact exception and rejects any other mismatch; conversions after the modern Iranian civil calendar's well-defined astronomical range are proleptic arithmetic, not a prediction of future official calendars. `Current`/`Previous` resolve whole Jalali calendar periods; `Last` is a rolling period ending at today's start; `to date` includes today and ends at tomorrow's midnight. A calendar picker alone does not cause chart-axis/tooltip formatting or database aggregation to become Jalali.

## Current gate

On Superset 6.1.0, the strict native Dashboard date-control Playwright gate is expected to fail because that release does not bridge the date-control registry into public extensions. Do not publish a `.supx` represented as the Jalali picker until an exact released host version passes a browser test proving it renders in the real filter, emits a Gregorian range, and changes the database-backed chart result. Do not promote the previous frontend patch image as an independent extension; it violates the no-rebuild requirement.

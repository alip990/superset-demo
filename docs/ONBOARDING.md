# Onboarding Guide

Read this after the [README](../README.md) got the stack running. It explains *how the demo is built*, where to change things, and how to extend it.

## 1. Mental model (5 minutes)

```
 Browser ──► embed-app (Flask, :8090) ──guest token──► Superset (:8088) ──SQL──► Postgres "demo"
                                                          │  └─ metadata ───► Postgres "superset"
                                                          └─ map tiles ◄──── tileserver (:8081) ◄── tiles/iran.mbtiles
```

Three ideas to hold on to:

1. **Everything is configuration-as-code.** No manual clicking in Superset. `superset/bootstrap.py` calls Superset's REST API to create the connection, datasets, charts, dashboard, roles, users and RLS rule. Re-running it is safe (it looks things up first and updates).
2. **Two kinds of row-level security**, one per access path:
   - *Direct Superset login* → an RLS rule with Jinja: `region IN (SELECT region FROM user_access WHERE username = '{{ current_username() }}')`.
   - *Embedded (guest token)* → the host app sends an RLS clause inside the token: `region IN ('north')`.
3. **The map is self-hosted.** No Mapbox key; base tiles come from our own tileserver.

## 2. Where each thing is implemented

| Concern | File | What to look at |
|---|---|---|
| Postgres DBs, sample data | `db/01-init.sql` | Creates `superset` (metadata) and `demo` (business) DBs; `provinces` → `branches` → `sales` (random data, ~540 days) and `user_access` |
| Jalali calendar | `db/01-init.sql` | `to_jalali(date)` SQL function fills `jalali_date/month/year` columns; charts group on `jalali_month` |
| Superset image | `superset/Dockerfile` | Stock `apache/superset:6.1.0` + `psycopg2-binary` |
| Superset settings | `superset/superset_config.py` | Persian locale, feature flags, embedding/CORS, guest-token settings, deck.gl base map |
| Provisioning | `superset/bootstrap.py` | REST API calls (connection, datasets, charts, dashboard layout, embedding) then ORM code for roles/users/RLS |
| Host app | `embed-app/app.py`, `embed-app/index.html` | Fake users, guest-token endpoint, iframe via `@superset-ui/embedded-sdk` |
| Startup ordering | `docker-compose.yml` | `db` healthy → `superset-init` → `superset` healthy → `superset-bootstrap` |

### 2.1 Persian + Jalali

- UI language: `BABEL_DEFAULT_LOCALE = "fa"` (English kept in `LANGUAGES`).
- Superset has no native Jalali axis, so dates are pre-computed in SQL and used as plain text dimensions (`x_axis: "jalali_month"`). Trade-off: sorting works because `YYYY-MM` sorts lexically; there is no real date arithmetic.

### 2.2 Bootstrap flow (`superset/bootstrap.py`)

1. Log in as `admin`, fetch CSRF token.
2. Create DB connection `Demo DB (mock)` using the read-only user `demo_reader`.
3. Create datasets: `sales` (physical, with metric `total_amount`) and `sales_by_branch` (virtual, SQL aggregate for the map).
4. Create 5 charts (`deck_scatter` map, big number, ECharts bar, pie, table) via `chart()` helper, which upserts by name.
5. Build `position_json` (grid rows/widths) and create dashboard slug `sales-fa`.
6. Enable embedding → prints `EMBEDDED_DASHBOARD_UUID`.
7. Use the Flask app context + ORM to create roles `DemoViewer`, `EmbedGuest`, `RegionalUser`, users, and the RLS filter.

Idempotency: helper `find(resource, col, value)` looks up by name/slug. Renaming a chart in the script therefore creates a *new* one.

### 2.3 Embedding and guest tokens (`embed-app/app.py`)

1. Page load: app logs in to Superset as admin and reads the dashboard's embedded UUID.
2. The SDK calls `fetchGuestToken()` → `GET /guest-token`.
3. The app maps the current app user to regions and posts to `/api/v1/security/guest_token/` with `resources` (the dashboard) and `rls` clauses.
4. Superset returns a signed JWT (`GUEST_TOKEN_JWT_SECRET`, 10 min expiry, role `EmbedGuest`); the iframe uses it.
5. Switching the user in the dropdown re-mounts the iframe with a new token.

Important: the RLS clause is applied to **every dataset** in the dashboard, so all datasets need a `region` column.

### 2.4 Map server

- Tiles: Planetiler converts the OSM Iran extract to `tiles/iran.mbtiles`; `tileserver-gl` serves it.
- Superset's deck.gl `mapbox_style` only accepts `mapbox://styles/...` or `tile://http(s)://...` raster URLs. We use `tile://http://localhost:8081/styles/basic-preview/{z}/{x}/{y}.png`. This URL must be reachable **from the user's browser**, hence `localhost:8081`, not the Docker hostname.

## 3. Plugins

**Current status: no custom plugin is implemented.** `plugins/` is an empty placeholder. All charts, including the map, are built-in Superset viz types (the map is `deck_scatter`). Anything below is a guide for adding one, not a description of existing code.

There are two things people call "plugin" here; pick the right one:

| You want | Approach |
|---|---|
| A new chart type (custom visualization) | Superset **viz plugin** (React/TypeScript), below |
| Different base map / styling | No plugin: edit `DECKGL_BASE_MAP` in `superset_config.py` |
| Custom auth, security rules, Jinja macros | Python config hooks in `superset_config.py` (`CUSTOM_SECURITY_MANAGER`, `JINJA_CONTEXT_ADDONS`), no frontend build |

### 3.1 Building a custom viz plugin

Prerequisites: Node.js (match the version in the Superset repo's `superset-frontend/.nvmrc`), npm, and a checkout of the Superset repo at the tag matching our version (`6.1.0`).

1. **Scaffold** inside `plugins/`:
   ```bash
   npm install -g yo @superset-ui/generator-superset
   cd plugins && yo @superset-ui/superset
   ```
   This creates `plugins/plugin-chart-<name>/` with `src/plugin/{index,controlPanel,buildQuery,transformProps}.ts` and `src/<Name>.tsx`.
2. **Understand the four pieces**
   - `controlPanel.ts`: the form the user fills in (metrics, group-by, options).
   - `buildQuery.ts`: turns form data into the query sent to the backend.
   - `transformProps.ts`: converts the query result into props for your component.
   - `<Name>.tsx`: the React component that renders.
3. **Register it in Superset**: in `superset-frontend`, `npm i -S ../path/to/plugins/plugin-chart-<name>`, then add it to `superset-frontend/src/visualizations/presets/MainPreset.js`:
   ```js
   import MyChartPlugin from 'plugin-chart-<name>';
   new MyChartPlugin().configure({ key: 'my_chart' }),
   ```
4. **Build the image.** The stock image ships a pre-built frontend, so a plugin means building the frontend from source. Typical approach: a multi-stage Dockerfile in `superset/` that clones Superset 6.1.0, copies `plugins/`, applies steps 3, runs `npm ci && npm run build`, then packages it. Point `image:` in `docker-compose.yml` at the result (or add a `build:` block).
5. **Use it in bootstrap**: add a `chart("...", "my_chart", ds, {...})` entry in `superset/bootstrap.py`.

Notes:
- Superset also has an experimental `DYNAMIC_PLUGINS` feature flag that loads plugin bundles at runtime without a rebuild; it is not enabled here and not tested for this stack.
- Verify all of the above against the Superset 6.1 docs ("Creating Visualization Plugins") before committing to it. These steps were written from general knowledge of the plugin system and were **not executed in this repo**.

## 4. Common tasks

| Task | How |
|---|---|
| Add a chart | New `chart(...)` call in `bootstrap.py`, add its key to `charts`, `rows`, `widths`, `heights`; re-run bootstrap |
| Re-run bootstrap | `docker compose run --rm superset-bootstrap` |
| Add an app user (embedded) | Add to `APP_USERS` in `embed-app/app.py` (regions list, `None` = unrestricted) |
| Add a Superset user | Add to the user list in `bootstrap.py`, plus rows in `user_access` in `db/01-init.sql` |
| Change sample data | Edit `db/01-init.sql`, then `docker compose down -v && docker compose up -d` (init scripts run only on an empty volume) |
| Change config | Edit `superset/superset_config.py`, then `docker compose restart superset` |
| Open a SQL shell | `docker compose exec db psql -U postgres -d demo` |
| Tail logs | `docker compose logs -f superset` |
| Get dashboard UUID | `docker compose logs superset-bootstrap \| grep EMBEDDED` |

## 5. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pull access denied for superset-demo` | Custom image not built: `docker build -t superset-demo:6.1.0-pg ./superset` |
| Map shows points but no base map | Tiles missing (`tiles/iran.mbtiles`), tileserver style name differs, or `localhost:8081` unreachable from the browser. Test `http://localhost:8081` |
| Tileserver exits immediately | `iran.mbtiles` not found in `./tiles` |
| Embedded dashboard blank / refused | CORS origin or iframe headers; check `CORS_OPTIONS` and the `embed-app` URL is exactly `http://localhost:8090` |
| Guest token 401/403 | `GUEST_ROLE_NAME` role missing (bootstrap didn't finish) or JWT secret mismatch |
| Bootstrap `-> 4xx` error | The error prints method, path and body; usually a stale/renamed object. Try a clean reset with `down -v` |
| Users see no data | Missing rows in `user_access` (direct login) or empty `regions` (embed) |
| Postgres changes ignored | `01-init.sql` only runs on first init; wipe volume with `down -v` |

## 6. Known limitations (be upfront with reviewers)

- Demo credentials and static secrets everywhere; Talisman/CSP disabled; `X-Frame-Options: ALLOWALL`.
- `embed-app` logs in as `admin` to mint guest tokens. Production should use a dedicated service account with only guest-token permission.
- Sample data is random; regenerated only on a fresh DB volume.
- Jalali support is a SQL workaround, not native.
- No automated tests and no CI.
- No custom plugin exists yet (see section 3).

## 7. Suggested first-day path

1. Bring the stack up (README) and open Superset as `admin`, look at the `sales-fa` dashboard.
2. Open http://localhost:8090 and switch between the three users; watch the RLS clause change in the header and the numbers change.
3. Log in to Superset directly as `ali_north` / `ali_north` and compare (RLS via Jinja).
4. Read `bootstrap.py` top to bottom, then `embed-app/app.py`.
5. Try a task from section 4 (add a chart or a user).

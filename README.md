# Superset Demo: Persian Sales Dashboard with Embedding, RLS and a Self-Hosted Map

> **فارسی:** راهنمای ساده به زبان فارسی در انتهای همین فایل است: [راهنمای فارسی](#راهنمای-فارسی)

A fully containerised demo of **Apache Superset 6.1** that shows:

- 🇮🇷 **Persian (fa) localisation** and **Jalali (Shamsi) calendar** aggregation
- 🗺️ **Self-hosted map server** (vector tiles built from OpenStreetMap Iran via Planetiler, served by TileServer GL) used as the deck.gl base map, with no Mapbox key
- 🔐 **Row-level security (RLS)** driven by the logged-in user (`{{ current_username() }}`)
- 🧩 **Embedding** a dashboard in a host app through an iframe with **guest tokens** and per-user dynamic RLS
- 🤖 A **bootstrap script** that creates the DB connection, datasets, charts, dashboard, roles, users and embedding automatically
- 🚓 **Traffic-police dashboards on real (beta) data**: a restored `pg_dumpall` backup, a BI schema on top of it, and
  **company-tree tenancy** for embedded dashboards (a company sees itself and every company below it). See
  [How this was built](#how-this-was-built) and [SUPERSET_RLS_GUIDE.md](SUPERSET_RLS_GUIDE.md).

## Architecture

| Service | Image | Port | Purpose |
|---|---|---|---|
| `db` | `postgres:16` | 5440 | Superset metadata DB (`superset`) and mock business DB (`demo`) |
| `backup-db` | `postgres:14` | 5441 | Restored beta backup (`pg_dumpall`) plus the `bi` schema in `CrimeManagementDb` |
| `redis` | `redis:7-alpine` | n/a | Cache (the chart-data cache is deliberately off, see below) |
| `superset-init` | `superset-demo:6.1.0-pg` | n/a | One-shot: `db upgrade`, create admin, `superset init` |
| `superset` | `superset-demo:6.1.0-pg` | 8088 | Superset web app |
| `superset-bootstrap` | `superset-demo:6.1.0-pg` | n/a | One-shot: runs `bootstrap.py` (sales demo) then `bootstrap_traffic.py` (traffic dashboards) |
| `embed-app` | `superset-demo:6.1.0-pg` | 8090 | Flask host app that embeds `traffic-fa-embedded` via guest tokens |

> **Map tiles:** the current `docker-compose.yml` has **no `tileserver` service**. `MAP_TILE_URL` points at
> OpenStreetMap's public raster tiles (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`). The self-hosted
> tileserver described under *Map server* below is still supported by `superset_config.py`, but you have to run it
> yourself and point `MAP_TILE_URL` at it.

## Sequence Diagram

### 1. Startup

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant DC as docker compose
    participant PG as Postgres (db)
    participant INIT as superset-init
    participant SS as Superset
    participant BS as superset-bootstrap
    participant BK as backup-db
    participant EA as embed-app

    Dev->>DC: docker compose up -d
    DC->>PG: start (runs db/01-init.sql: superset + demo DBs, sales data)
    PG-->>DC: healthy (pg_isready)
    DC->>BK: start (first run: restore.sh restores the dump, then 02-bi.sql builds schema bi)
    BK-->>DC: healthy (TCP pg_isready, only after restore + BI build)
    DC->>INIT: run
    INIT->>PG: superset db upgrade, create-admin, superset init
    INIT-->>DC: completed successfully
    DC->>SS: start (port 8088)
    SS-->>DC: healthy (/health)
    DC->>BS: run bootstrap.py, then bootstrap_traffic.py
    BS->>SS: login, create DB connections, datasets, charts, dashboards
    BS->>SS: enable embedding (dashboard UUIDs)
    BS->>SS: create roles, users, RLS rules
    DC->>EA: start (port 8090)
```

### 2. Embedded dashboard with guest token and RLS

```mermaid
sequenceDiagram
    autonumber
    actor U as End user (browser)
    participant EA as embed-app (:8090)
    participant SS as Superset (:8088)
    participant PG as Postgres (backup-db)
    participant TS as tile server (OSM by default)

    U->>EA: GET / (pick user, e.g. navidahmadian, and a company in their subtree)
    EA->>SS: login as admin, GET dashboard/traffic-fa-embedded/embedded
    SS-->>EA: embedded dashboard UUID
    EA-->>U: HTML page with iframe SDK

    U->>EA: GET /guest-token
    EA->>PG: recursive CTE: user's company + all descendants
    EA->>SS: POST /security/guest_token/ (username "navidahmadian|<ids>", rls: [])
    SS-->>EA: signed JWT guest token
    EA-->>U: token

    U->>SS: load embedded dashboard (iframe, guest token)
    SS->>PG: virtual-dataset SQL: company_id IN (get_guest_user_attribute(...))
    PG-->>SS: only rows the user may see
    SS-->>U: charts render
    U->>TS: GET /{z}/{x}/{y}.png
    TS-->>U: map tiles (MAP_TILE_URL)
```

## Prerequisites

- Docker and Docker Compose v2
- ~2 GB free disk, plus room for the restored backup (the dump alone is ~263 MB)
- The beta dump `backups/1may-backup.sql` (not in git, see below)
- Free ports: `5440`, `5441`, `8088`, `8090` (and `8081` only if you run your own tileserver)

## How to Bring It Up

### 1. Clone

```bash
git clone https://github.com/alip990/superset-demo.git
cd superset-demo
```

### 2. Build the Superset image

The stock image lacks the Postgres driver, so build the small custom image referenced by `docker-compose.yml`:

```bash
docker build -t superset-demo:6.1.0-pg ./superset
```

### 3. Provide the backup dump

Copy the beta backup to `backups/1may-backup.sql`. It is git-ignored (`backups/*.sql`, except `02-bi.sql`)
because it is large and contains real data and credential hashes. Without it the `backup-db` restore fails and
the traffic dashboards and the embed app can't start.

### 3b. (Optional) Provide the map tiles

Only needed if you want the self-hosted tileserver instead of the public OSM tiles.
`tiles/iran.mbtiles` (~580 MB) is **not** stored in git. Generate it once with Planetiler from an OSM extract:

```bash
mkdir -p tiles
curl -L -o tiles/iran-latest.osm.pbf https://download.geofabrik.de/asia/iran-latest.osm.pbf
docker run --rm -v "$(pwd)/tiles:/data" onthegomap/planetiler:latest \
  --osm-path=/data/iran-latest.osm.pbf --output=/data/iran.mbtiles
```

> The tileserver serves the `basic-preview` style. If your tileserver has no `styles/` config for it, adjust the tile URL in `superset/superset_config.py` and `superset/bootstrap.py`.

### 4. Start everything

```bash
docker compose up -d
docker compose logs -f superset-bootstrap   # wait for BOOTSTRAP_DONE
```

The first start takes a few minutes (DB migrations, the backup restore, and bootstrap). `backup-db` reports
healthy only after the restore and the BI build finish, and `superset-bootstrap` waits for it.
Wait for `TRAFFIC_BOOTSTRAP_DONE` in the bootstrap log.

### 5. Open the apps

| App | URL | Login |
|---|---|---|
| Superset | http://localhost:8088 | `admin` / `admin` |
| Embedded host app | http://localhost:8090 | pick a demo user in the page |
| Postgres (metadata + demo) | `localhost:5440` | `postgres` / `postgres` |
| Postgres (restored backup) | `localhost:5441` | `postgres` / `postgres`, or read-only `bi_reader` / `bi_reader` |

Dashboard slugs: `sales-fa`, `traffic-fa` and `traffic-fa-embedded`
(e.g. `http://localhost:8088/superset/dashboard/traffic-fa/`).

### Demo users (Superset, password = username)

| User | Regions (RLS via `user_access` table) |
|---|---|
| `ali_north` | north |
| `sara_south` | south, center |
| `manager` | north, south, center, east, west |

The embedded app (http://localhost:8090) shows the traffic dashboard `traffic-fa-embedded` on the restored
backup data, scoped by the **company tree**. Pick one of the backup's real users (e.g. `fkreza` = national,
`navidahmadian` = Qom, `rezailka` = Tehran), then optionally a company inside that user's subtree. See [SUPERSET_RLS_GUIDE.md](SUPERSET_RLS_GUIDE.md).

Direct logins `traffic_national`, `traffic_qom` and `traffic_tehran` see the same split on the
`traffic-fa` dashboard through a regular RLS rule.

### Stop and reset

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and wipe the Postgres volumes (pgdata and backupdata; the restore runs again next start)
```

## How this was built

This section records, step by step, how the traffic part of the demo was put together on top of the original sales
demo, and the commands to reproduce each step.

### Step 1: Restore the beta backup into its own Postgres (`backup-db`)

- The source is a `pg_dumpall` of a **PostgreSQL 14** cluster (`backups/1may-backup.sql`, ~263 MB, git-ignored).
  It contains several databases; the ones used here are `CrimeManagementDb`, `DeviceManagement` and
  `UserManagementDb`.
- It gets its own service, `backup-db` (`postgres:14`, host port **5441**, volume `backupdata`), so it never mixes
  with Superset's metadata DB.
- `backups/restore.sh` is mounted as `/docker-entrypoint-initdb.d/01-restore.sh`, so it runs **once**, on an empty
  volume. It pipes the dump into `psql`, dropping the `CREATE ROLE postgres` / `ALTER ROLE postgres` lines: the role
  already exists, and the dump's `ALTER ROLE` would reset its password to an unknown one.
- `backups/02-bi.sql` is mounted as `/docker-entrypoint-initdb.d/02-bi.sql`, so it runs right after the restore.
- The healthcheck uses TCP (`pg_isready -h 127.0.0.1`). During the first-start restore Postgres only listens on the
  unix socket, so the service stays unhealthy until restore and BI build are done, and everything that depends on it
  waits.

```bash
# first start (or after wiping the volume) restores automatically:
docker compose up -d backup-db
docker compose logs -f backup-db        # wait until it is healthy

# start the restore again from scratch (deletes the restored data):
docker compose rm -sf backup-db && docker volume rm superset-demo_backupdata && docker compose up -d backup-db
```

### Step 2: Build the BI layer (`backups/02-bi.sql`, schema `bi` in `CrimeManagementDb`)

The raw tables are spread over three databases and are not chart-friendly, so a flat BI schema is built once:

| Object | What it is |
|---|---|
| `dm_src.*`, `um_src.*` | `postgres_fdw` foreign tables: `DM.Company`, `Vehicle`, `VehicleModel`, `VehicleUsage`, `Plate` from `DeviceManagement`; `um.User`, `UserAttribute` from `UserManagementDb` |
| `bi.to_jalali(date)` | SQL function that converts a Gregorian date to Jalali text `YYYY-MM-DD` |
| `bi.company` | The company tree (`company_id`, `parent_id`, `title`, `depth`): national → Qom, Tehran. `province_name` links a provincial company to crime records |
| `bi.company_closure` | Recursive view of every (ancestor, descendant) pair, including self |
| `bi.app_user` | Real application users and their company (from `um.UserAttribute.CompanyId`). Used by the embed app |
| `bi.company_user` | Demo Superset logins → company: `traffic_national`, `traffic_qom`, `traffic_tehran` |
| `bi.vehicle` | One vehicle per device. **Off-by-one in the source data:** `CR.DeviceCrime.DeviceId` = `DM.Device.Id + 1`, so the key is `DeviceId + 1` |
| `bi.violation` | Fact table, one row per speed check (non-deleted `CR.DeviceCrime`), local Tehran time, Jalali date, hour, weekday, status, `is_violation`, company, location, lat/lon plus a 3-decimal `lat_grid`/`lon_grid`, driver, plate, vehicle model/usage |
| `bi_reader` | Read-only login role (`SELECT` on schema `bi`) that Superset and the embed app use |

In the restored data `bi.violation` has **931,335** speed checks over 5 days: Qom **511,392**, Tehran **419,943**.

The script drops and recreates `bi` (and the FDW servers), so it can be re-run at any time without a new restore:

```bash
docker compose exec -T backup-db psql -U postgres -q < backups/02-bi.sql

# quick check
docker compose exec -T backup-db psql -U postgres -d CrimeManagementDb \
  -c "SELECT company, count(*) FROM bi.violation GROUP BY 1"
```

### Step 3: Build the dashboards (`superset/bootstrap_traffic.py`)

Run by the `superset-bootstrap` job after `bootstrap.py`. Like the sales bootstrap it uses the REST API and
upserts by name, so it is safe to re-run.

1. Creates the database connection `Traffic BI (backup)` →
   `postgresql+psycopg2://bi_reader:bi_reader@backup-db:5432/CrimeManagementDb`.
2. Creates datasets: `violation` (physical `bi.violation`), `violation_scoped` (virtual, tenant-filtered, see
   Step 4) and `vehicle` (physical `bi.vehicle`, no `company_id`).
3. Builds the same tabbed dashboard twice:
   - header, intro text and a KPI row (checks, violations, violation rate, vehicles, drivers, gauge);
   - tab **Overview** (نمای کلی و سازمان): sunburst of the company tree, status donut, company bar, daily Jalali
     bars, hourly area, day × hour heatmap;
   - tab **Maps** (نقشه‌ها): deck.gl 3D hex, heatmap and scatter, all aggregated on the ~100 m
     `lat_grid`/`lon_grid` so the browser does not receive 900k points;
   - tab **Fleet** (محورها، خودروها و رانندگان): top roads, treemap, vehicle models, top vehicles and drivers;
   - native filters: company, Jalali date, status, road, vehicle model.
4. `traffic-fa` uses the physical `violation` dataset and is for **direct Superset login**. A regular RLS rule
   `company-tree-by-current-user` on role `TrafficCompanyUser` limits it:
   ```sql
   company_id IN (SELECT cc.descendant_id FROM bi.company_closure cc
                  JOIN bi.company_user cu ON cu.company_id = cc.ancestor_id
                  WHERE cu.username = '{{ current_username() }}')
   ```
   Demo users `traffic_national`, `traffic_qom`, `traffic_tehran` (password = username).
5. `traffic-fa-embedded` uses `violation_scoped` (plus a `vehicle` table chart) and gets embedding enabled.
   The `EmbedGuest` role is granted only `violation_scoped` and `vehicle`.

```bash
docker compose run --rm superset-bootstrap   # re-run both bootstrap scripts
docker compose logs superset-bootstrap | grep -E 'TRAFFIC_(EMBEDDED|BOOTSTRAP)'
```

### Step 4: Company-tree tenancy for the embedded dashboard

Goal: an embedded user sees their own company and every company below it, and nothing else.

1. **Embed app** (`embed-app/app.py`, port 8090). A **user** dropdown lists the activated users from
   `bi.app_user` (plus a demo-only "مدیر سامانه" entry that can pick any company). A **company** dropdown offers only
   the user's company and its descendants. The backend re-checks the chosen company against the user's subtree, so
   editing the request can't reach another company.
2. On `GET /guest-token` the app walks down the tree from the selected company with a recursive CTE over
   `bi.company` and joins the ids. Superset 6.1 drops `user.attributes` from guest-token requests, so the ids are
   **packed into the username**: `"<user>|<id1>, <id2>"`. The token's `"rls"` is `[]`.
3. `superset/superset_config.py` adds the Jinja macro `get_guest_user_attribute('allowed_companies')`
   (via `JINJA_CONTEXT_ADDONS`). It reads native attributes if present, otherwise it returns the part of the
   username after `|`.
4. The virtual dataset `violation_scoped` filters with it and **fails closed**:
   ```sql
   SELECT * FROM bi.violation
   WHERE 1=1
   {% set allowed_companies = get_guest_user_attribute('allowed_companies') %}
   {% if allowed_companies %}
     AND company_id IN ({{ allowed_companies }})
   {% else %}
     AND 1=0 -- Failsafe: if the attribute is missing, return nothing to prevent data leaks
   {% endif %}
   ```
5. **The data cache is off** (`DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}`). Superset's cache key does not
   include the value of a custom macro, so with a cache Qom and Tehran could be served each other's cached results.
6. The token-level `rls` is not used because Superset applies it to every dataset on the dashboard, and a dataset
   without `company_id` (like `vehicle`) would then fail.

Rules for analysts who add datasets to embedded dashboards are in [SUPERSET_RLS_GUIDE.md](SUPERSET_RLS_GUIDE.md).

### Step 5: Check it

Open http://localhost:8090 and compare the "کل پایش‌های سرعت" KPI. The header shows the `allowed_companies` value
that went into the token.

| Selection | allowed_companies | Total speed checks |
|---|---|---|
| `fkreza` (national) | all three | 931,335 |
| `fkreza` → company Tehran | Tehran | 419,943 |
| `navidahmadian` (Qom) | Qom only | 511,392 |
| `superadmin` (no company) | none | 0 (failsafe) |

Then log in to http://localhost:8088 as `traffic_qom` / `traffic_qom` and open `traffic-fa`: it shows the same
Qom numbers through the regular RLS rule. `traffic_national` sees both provinces.

### Jalali (Persian) dates: one possible approach

Superset has no Jalali calendar, so this demo converts dates **in SQL, at load time** and gives Superset ready-made
Jalali text columns. This is one possible approach, not the only one (see the alternative below).

**The function.** `bi.to_jalali(date)` in `backups/02-bi.sql` is a plain plpgsql arithmetic conversion. It needs no
extension and no Superset plugin. Example: `bi.to_jalali('2025-03-10')` → `'1403-12-20'`.

```sql
CREATE FUNCTION bi.to_jalali(d date) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  gy int := extract(year from d); gm int := extract(month from d); gd int := extract(day from d);
  g_d_m int[] := ARRAY[0,31,59,90,120,151,181,212,243,273,304,334];
  gy2 int; days int; jy int; jm int; jd int;
BEGIN
  gy2 := CASE WHEN gm > 2 THEN gy + 1 ELSE gy END;
  days := 355666 + (365 * gy) + ((gy2 + 3) / 4) - ((gy2 + 99) / 100) + ((gy2 + 399) / 400) + gd + g_d_m[gm];
  jy := -1595 + (33 * (days / 12053));
  days := days % 12053;
  jy := jy + 4 * (days / 1461);
  days := days % 1461;
  IF days > 365 THEN jy := jy + ((days - 1) / 365); days := (days - 1) % 365; END IF;
  IF days < 186 THEN jm := 1 + (days / 31); jd := 1 + (days % 31);
  ELSE jm := 7 + ((days - 186) / 30); jd := 1 + ((days - 186) % 30); END IF;
  RETURN lpad(jy::text,4,'0') || '-' || lpad(jm::text,2,'0') || '-' || lpad(jd::text,2,'0');
END $$;
```

**How it is used.** It runs once, when `bi.violation` is built, and fills extra columns next to the real timestamp:

```sql
WITH base AS (
  SELECT d.*, (d."OccouredDate" AT TIME ZONE 'Asia/Tehran') AS local_ts FROM "CR"."DeviceCrime" d
  WHERE NOT d."Deleted"
)
SELECT b."Id" AS id,
       b.local_ts AS occurred_at,
       b.local_ts::date AS occurred_date,
       bi.to_jalali(b.local_ts::date) AS jalali_date,
       substr(bi.to_jalali(b.local_ts::date), 1, 7) AS jalali_month,
       extract(hour FROM b.local_ts)::int AS hour_of_day,
       -- isodow 1 = Monday; the number prefix sorts the week Saturday-first
       (ARRAY['۲ دوشنبه','۳ سه‌شنبه','۴ چهارشنبه','۵ پنجشنبه','۶ جمعه','۰ شنبه','۱ یکشنبه'])
         [extract(isodow FROM b.local_ts)::int] AS weekday,
```

- `occurred_at`: the real timestamp in `Asia/Tehran` local time, kept for anything that needs real date arithmetic.
- `jalali_date`: text `YYYY-MM-DD`; `jalali_month`: text `YYYY-MM`.
- `weekday`: Persian day names with a number prefix (`۰ شنبه` … `۶ جمعه`) so the week sorts Saturday-first.
- `hour_of_day`: 0–23 in local time.

**How Superset uses them.** As plain text categories. Charts group by `jalali_date` (the daily bars and the
day × hour heatmap in the traffic dashboards) or `jalali_month` (the sales demo, built the same way by `to_jalali()` in
`db/01-init.sql`). The native date filter "تاریخ (شمسی)" is a dropdown of `jalali_date` values. Because the text is
zero-padded `YYYY-MM-DD`, sorting it alphabetically also sorts it by date.

**Pros**
- No Superset plugin and no custom frontend build.
- Fast: the conversion runs once at load time, not on every query.
- The real timestamp is kept, so nothing is lost.

**Cons**
- Superset's time grain, date-range picker and relative ranges ("last 7 days") stay Gregorian.
- Every new table needs the same Jalali columns.
- A text axis is categorical: days with no data simply disappear instead of showing as gaps.

**Alternative (not implemented; suggested as a spike)**
- Keep only real timestamps in the database.
- Add Jalali month and year time grains through `TIME_GRAIN_ADDON_EXPRESSIONS` in `superset_config.py`, so grouping
  still happens in the database.
- Add a custom Superset frontend time formatter that uses `Intl.DateTimeFormat('fa-IR-u-ca-persian')` to label
  the axis in Jalali.
- The date-range picker would still be Gregorian unless the frontend is changed further.

### Reproduce from scratch (summary)

```bash
docker build -t superset-demo:6.1.0-pg ./superset
cp /path/to/1may-backup.sql backups/1may-backup.sql
docker compose up -d                                        # restore + 02-bi.sql + bootstrap run automatically
docker compose logs -f superset-bootstrap                   # wait for TRAFFIC_BOOTSTRAP_DONE

# after editing backups/02-bi.sql:
docker compose exec -T backup-db psql -U postgres -q < backups/02-bi.sql
# after editing superset/bootstrap_traffic.py:
docker compose run --rm superset-bootstrap
# after editing superset/superset_config.py or embed-app/app.py:
docker compose restart superset embed-app
```

## Developer Guide (Onboarding)

Read this after the stack is running. It explains how the demo is built, where to change things, and how to extend it.

### Mental model (5 minutes)

```
 Browser ──► embed-app (Flask, :8090) ──guest token──► Superset (:8088) ──SQL──► Postgres "demo"
                                                          │  └─ metadata ───► Postgres "superset"
                                                          └─ map tiles ◄──── tileserver (:8081) ◄── tiles/iran.mbtiles
```

Three ideas to hold on to:

1. **Everything is configuration-as-code.** No manual clicking in Superset. `superset/bootstrap.py` calls Superset's REST API to create the connection, datasets, charts, dashboard, roles, users and RLS rule. Re-running it is safe (it looks things up first and updates).
2. **Two kinds of row-level security**, one per access path:
   - *Direct Superset login* → an RLS rule with Jinja: `region IN (SELECT region FROM user_access WHERE username = '{{ current_username() }}')`.
   - *Embedded (guest token)* → the host app packs the user's allowed company ids (their company and all
     companies below it) into the token's username; virtual datasets filter on
     `get_guest_user_attribute('allowed_companies')`. The token's `rls` is empty. See
     [SUPERSET_RLS_GUIDE.md](SUPERSET_RLS_GUIDE.md).
3. **The map is self-hosted.** No Mapbox key; base tiles come from our own tileserver.

### Where each thing is implemented

| Concern | File | What to look at |
|---|---|---|
| Postgres DBs, sample data | `db/01-init.sql` | Creates `superset` (metadata) and `demo` (business) DBs; `provinces` → `branches` → `sales` (random data, ~540 days) and `user_access` |
| Jalali calendar | `db/01-init.sql` | `to_jalali(date)` SQL function fills `jalali_date/month/year` columns; charts group on `jalali_month` |
| Superset image | `superset/Dockerfile` | Stock `apache/superset:6.1.0` + `psycopg2-binary` |
| Superset settings | `superset/superset_config.py` | Persian locale, feature flags, embedding/CORS, guest-token settings, deck.gl base map |
| Provisioning | `superset/bootstrap.py` | REST API calls (connection, datasets, charts, dashboard layout, embedding) then ORM code for roles/users/RLS |
| Host app | `embed-app/app.py`, `embed-app/index.html` | Fake users, company-tree CTE, guest-token endpoint, iframe via `@superset-ui/embedded-sdk` |
| Backup data + BI layer | `backups/restore.sh`, `backups/02-bi.sql` | Restores the beta backup into `backup-db` (:5441) and builds schema `bi` (company tree, `violation` fact table) |
| Traffic dashboards | `superset/bootstrap_traffic.py` | `traffic-fa` (direct login, RLS) and `traffic-fa-embedded` (scoped virtual datasets) |
| Startup ordering | `docker-compose.yml` | `db` healthy → `superset-init` → `superset` healthy → `superset-bootstrap` |

#### Persian + Jalali

- UI language: `BABEL_DEFAULT_LOCALE = "fa"` (English kept in `LANGUAGES`).
- Superset has no native Jalali axis, so dates are pre-computed in SQL and used as plain text dimensions (`x_axis: "jalali_month"`). Trade-off: sorting works because `YYYY-MM` sorts lexically; there is no real date arithmetic.

#### Bootstrap flow (`superset/bootstrap.py`)

1. Log in as `admin`, fetch CSRF token.
2. Create DB connection `Demo DB (mock)` using the read-only user `demo_reader`.
3. Create datasets: `sales` (physical, with metric `total_amount`) and `sales_by_branch` (virtual, SQL aggregate for the map).
4. Create 5 charts (`deck_scatter` map, big number, ECharts bar, pie, table) via `chart()` helper, which upserts by name.
5. Build `position_json` (grid rows/widths) and create dashboard slug `sales-fa`.
6. Enable embedding → prints `EMBEDDED_DASHBOARD_UUID`.
7. Use the Flask app context + ORM to create roles `DemoViewer`, `EmbedGuest`, `RegionalUser`, users, and the RLS filter.

Idempotency: helper `find(resource, col, value)` looks up by name/slug. Renaming a chart in the script therefore creates a *new* one.

#### Embedding and guest tokens (`embed-app/app.py`)

1. Page load: app logs in to Superset as admin and reads the dashboard's embedded UUID.
2. The SDK calls `fetchGuestToken()` → `GET /guest-token`.
3. The app looks up the user's company, flattens the company tree below it with a recursive CTE
   (`bi.company` in `backup-db`), and posts to `/api/v1/security/guest_token/` with username
   `"<user>|<id>, <id>, ..."`, `resources` (the dashboard) and `"rls": []`.
4. Superset returns a signed JWT (`GUEST_TOKEN_JWT_SECRET`, 10 min expiry, role `EmbedGuest`); the iframe uses it.
5. Switching the user in the dropdown re-mounts the iframe with a new token.

Important: this is why the token's `rls` is empty. A token-level RLS clause is applied to **every dataset** in the
dashboard, so every dataset would need the filtered column. Filtering inside the virtual datasets avoids that.

#### Map server (no plugin needed)

The map is **not** a custom plugin. It is Superset's built-in deck.gl *Scatterplot* chart (`deck_scatter`) plus a **self-hosted base map**. Superset only needs a tile URL, so the whole integration is a config value, one chart parameter and one extra container.

**Pipeline**

```
OSM Iran extract (.osm.pbf, Geofabrik)
        │  Planetiler (one-off, offline)
        ▼
tiles/iran.mbtiles ──mounted──► tileserver-gl (:8081) ──HTTP──► browser ──► Superset deck.gl map
                                   serves /styles/basic-preview/{z}/{x}/{y}.png
```

1. **Build the tiles (offline, once).** Planetiler turns the OSM extract into an MBTiles file (`tiles/iran.mbtiles`, ~580 MB). It is git-ignored; see the README for the command. Rebuild only if you want fresher OSM data.
2. **Serve them.** `docker-compose.yml` runs `maptiler/tileserver-gl` with `--file /data/iran.mbtiles -p 8080 -u http://localhost:8081`. `-u` is the *public* URL the server embeds in its responses, so it must be what the browser can reach (host port 8081), not the Docker-internal name. The server renders the vector tiles into raster PNGs through its built-in `basic-preview` style.
3. **Point Superset at it.** In `superset/superset_config.py`:
   ```python
   TILE_SERVER = os.environ.get("TILE_SERVER_PUBLIC_URL", "http://localhost:8081")
   DECKGL_BASE_MAP = [[f"tile://{TILE_SERVER}/styles/basic-preview/{{z}}/{{x}}/{{y}}.png", "Own map server (Iran, basic)"]]
   MAPBOX_API_KEY = ""
   ```
   `DECKGL_BASE_MAP` adds our server to the base-map dropdown in deck.gl charts. Emptying `MAPBOX_API_KEY` means no request ever goes to Mapbox.
4. **Use it in the chart.** `superset/bootstrap.py` sets `mapbox_style` on the `deck_scatter` chart to the same `tile://...` URL, with the viewport centred on Iran (lon 53.7, lat 32.4, zoom 4.4). Points come from the `sales_by_branch` dataset (`lat`, `lon`, `SUM(amount)`).
5. **Browser fetches tiles directly.** Tile requests go from the user's browser to `localhost:8081`, not through Superset. That is why the tileserver publishes a port and why it also works inside the embedded iframe.

**Why raster `tile://` and not a MapLibre style.json?** Superset's `mapbox_style` field validates its input and only accepts `mapbox://styles/...` or `tile://http(s)://...` (raster XYZ). A bare `style.json` URL is silently rejected and no base map is drawn. So we let tileserver-gl do the vector-to-raster rendering and give Superset plain XYZ PNG tiles.

**Trade-offs of this approach**
- Raster tiles: no client-side restyling, no rotating/pitching a crisp vector map, and less sharp on high-DPI screens.
- Only Iran is covered; outside the extract the map is blank.
- Styling is limited to what tileserver-gl's styles offer. A different look means supplying your own style (mount it into the tileserver and change the `/styles/<name>/` part of the URL in **both** `superset_config.py` and `bootstrap.py`).
- The map data must stay in sync between those two files, since the chart stores its own copy of the URL.

**When would a plugin be needed?** Only if you want true vector rendering (MapLibre GL), custom layers or interactions the built-in deck.gl charts do not offer. See *Plugins* below. For this demo the built-in chart plus config was enough, and it avoids building Superset's frontend from source.

**Checking it works**
- `http://localhost:8081` lists the available styles/data.
- `http://localhost:8081/styles/basic-preview/5/20/12.png` should return a PNG tile.
- If points appear on a blank/grey background, the chart works but the tile URL is unreachable or the style name is wrong.

### Plugins

**Current status: no custom plugin is implemented.** `plugins/` is an empty placeholder. All charts, including the map, are built-in Superset viz types (the map is `deck_scatter`). Anything below is a guide for adding one, not a description of existing code.

There are two things people call "plugin" here; pick the right one:

| You want | Approach |
|---|---|
| A new chart type (custom visualization) | Superset **viz plugin** (React/TypeScript), below |
| Different base map / styling | No plugin: edit `DECKGL_BASE_MAP` in `superset_config.py` (see *Map server* above) |
| Custom auth, security rules, Jinja macros | Python config hooks in `superset_config.py` (`CUSTOM_SECURITY_MANAGER`, `JINJA_CONTEXT_ADDONS`), no frontend build |

#### Building a custom viz plugin

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

### Common tasks

| Task | How |
|---|---|
| Add a chart | New `chart(...)` call in `bootstrap.py`, add its key to `charts`, `rows`, `widths`, `heights`; re-run bootstrap |
| Re-run bootstrap | `docker compose run --rm superset-bootstrap` |
| Add an app user (embedded) | Users come from `bi.app_user` (copied from `um.User` by `backups/02-bi.sql`); change the source data or that script and re-run it |
| Add a Superset user | Add to the user list in `bootstrap.py`, plus rows in `user_access` in `db/01-init.sql` |
| Change sample data | Edit `db/01-init.sql`, then `docker compose down -v && docker compose up -d` (init scripts run only on an empty volume) |
| Change config | Edit `superset/superset_config.py`, then `docker compose restart superset` |
| Open a SQL shell | `docker compose exec db psql -U postgres -d demo` |
| Tail logs | `docker compose logs -f superset` |
| Get dashboard UUID | `docker compose logs superset-bootstrap \| grep EMBEDDED` |

### Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pull access denied for superset-demo` | Custom image not built: `docker build -t superset-demo:6.1.0-pg ./superset` |
| Map shows points but no base map | Tiles missing (`tiles/iran.mbtiles`), tileserver style name differs, or `localhost:8081` unreachable from the browser. Test `http://localhost:8081` |
| Tileserver exits immediately | `iran.mbtiles` not found in `./tiles` |
| Embedded dashboard blank / refused | CORS origin or iframe headers; check `CORS_OPTIONS` and the `embed-app` URL is exactly `http://localhost:8090` |
| Guest token 401/403 | `GUEST_ROLE_NAME` role missing (bootstrap didn't finish) or JWT secret mismatch |
| Bootstrap `-> 4xx` error | The error prints method, path and body; usually a stale/renamed object. Try a clean reset with `down -v` |
| Users see no data | Missing rows in `user_access` / `bi.company_user` (direct login), or the user has no company so `allowed_companies` is empty (embed failsafe) |
| `backup-db` stays unhealthy | Restore still running (can take minutes), or `backups/1may-backup.sql` missing: check `docker compose logs backup-db` |
| Postgres changes ignored | `01-init.sql` only runs on first init; wipe volume with `down -v` |

### Known limitations (be upfront with reviewers)

- Demo credentials and static secrets everywhere; Talisman/CSP disabled; `X-Frame-Options: ALLOWALL`.
- `embed-app` logs in as `admin` to mint guest tokens. Production should use a dedicated service account with only guest-token permission.
- Sample data is random; regenerated only on a fresh DB volume.
- Chart-data caching is off for the tenant filter to be safe; every chart query hits Postgres.
- Company ids are inserted into SQL as-is; they come from our backend in a signed token and must stay a list of integers.
- Jalali support is a SQL workaround, not native.
- No automated tests and no CI.
- No custom plugin exists yet (see *Plugins* above).

### Suggested first-day path

1. Bring the stack up (README) and open Superset as `admin`, look at the `sales-fa` dashboard.
2. Open http://localhost:8090 and switch between users and companies; watch `allowed_companies` change in the header and the numbers change.
3. Log in to Superset directly as `ali_north` / `ali_north` (sales) or `traffic_qom` / `traffic_qom` (traffic) and compare (RLS via Jinja).
4. Read `bootstrap.py` top to bottom, then `embed-app/app.py`.
5. Try a task from *Common tasks* (add a chart or a user).

## Project Layout

```
.
├── docker-compose.yml        # all services
├── db/01-init.sql            # creates DBs, Jalali function, mock sales data, user_access
├── backups/
│   ├── 1may-backup.sql       # beta pg_dumpall (git-ignored, supply it yourself)
│   ├── restore.sh            # first-start restore into backup-db
│   └── 02-bi.sql             # schema bi: company tree, users, vehicles, violation fact table
├── superset/
│   ├── Dockerfile            # Superset 6.1.0 + psycopg2
│   ├── superset_config.py    # fa locale, feature flags, embedding, base map, get_guest_user_attribute, NullCache
│   ├── bootstrap.py          # provisions the sales charts, dashboard, roles, users, RLS
│   └── bootstrap_traffic.py  # traffic-fa and traffic-fa-embedded dashboards, RLS, EmbedGuest grants
├── embed-app/                # Flask host app (user/company pickers, guest tokens + iframe)
├── SUPERSET_RLS_GUIDE.md     # rules for datasets on embedded dashboards
├── tiles/                    # iran.mbtiles goes here (git-ignored)
└── plugins/                  # reserved for custom viz plugins (empty today)
```

## Security Note

This is a **demo**. It uses default credentials, a static JWT secret, CORS/iframe restrictions relaxed and Talisman disabled. Change `SUPERSET_SECRET_KEY`, `GUEST_TOKEN_JWT_SECRET`, all passwords, and set a real CSP before any real deployment.

---

## راهنمای فارسی

<div dir="rtl">

این بخش همان مطالب فنی بالا را به زبان ساده توضیح می‌دهد. دستورها، نام فایل‌ها و نام جدول‌ها عمداً انگلیسی مانده‌اند تا بتوانید مستقیم کپی کنید.

### این پروژه چیست؟

یک نمونهٔ آزمایشی (دمو) از **Apache Superset 6.1** است که همه چیزش داخل Docker اجرا می‌شود. Superset ابزاری برای ساختن نمودار و داشبورد است. در این پروژه:

- رابط کاربری فارسی است و تاریخ‌ها **شمسی** نمایش داده می‌شوند.
- یک داشبورد فروش نمونه با دادهٔ ساختگی داریم (`sales-fa`).
- دو داشبورد **پایش سرعت پلیس راهور** روی دادهٔ واقعی نسخهٔ بتا داریم (`traffic-fa` و `traffic-fa-embedded`).
- یک برنامهٔ نمونه (embed-app) داریم که داشبورد را داخل صفحهٔ خودش نشان می‌دهد و هر کاربر فقط دادهٔ **شرکت خودش و شرکت‌های زیرمجموعه‌اش** را می‌بیند.

### اجزای سیستم (سرویس‌ها)

هر سرویس یک کانتینر Docker است:

| سرویس | پورت | کارش چیست |
|---|---|---|
| `db` | 5440 | پایگاه دادهٔ خود Superset و دادهٔ نمونهٔ فروش |
| `backup-db` | 5441 | بک‌آپ بازگردانی‌شدهٔ نسخهٔ بتا و لایهٔ `bi` |
| `redis` | – | حافظهٔ کش Superset |
| `superset` | 8088 | خود Superset (نام کاربری و رمز: `admin` / `admin`) |
| `superset-init` | – | یک بار اجرا می‌شود: ساخت جدول‌های Superset و کاربر admin |
| `superset-bootstrap` | – | یک بار اجرا می‌شود: همهٔ نمودارها، داشبوردها، نقش‌ها و کاربرها را خودکار می‌سازد |
| `embed-app` | 8090 | برنامهٔ نمونه که داشبورد را داخل خودش نشان می‌دهد |

همه با یک دستور بالا می‌آیند:

```bash
docker compose up -d
```

### مرحلهٔ ۱: بازگردانی بک‌آپ

- فایل بک‌آپ `backups/1may-backup.sql` (حدود ۲۶۳ مگابایت) خروجی `pg_dumpall` از یک PostgreSQL نسخهٔ ۱۴ است. این فایل **داخل git نیست** (چون حجیم است و دادهٔ واقعی دارد)؛ باید خودتان آن را در پوشهٔ `backups` بگذارید.
- برای آن یک پایگاه دادهٔ جدا به نام `backup-db` (پورت 5441) ساختیم تا با پایگاه دادهٔ Superset قاطی نشود.
- اولین باری که `backup-db` روشن می‌شود، اسکریپت `backups/restore.sh` بک‌آپ را بازمی‌گرداند. خط‌های مربوط به کاربر `postgres` را حذف می‌کند تا رمز این کاربر عوض نشود.
- بلافاصله بعد از آن، `backups/02-bi.sql` اجرا می‌شود و لایهٔ `bi` را می‌سازد (مرحلهٔ ۲).
- تا این دو کار تمام نشود، `backup-db` «سالم» (healthy) اعلام نمی‌شود و بقیهٔ سرویس‌ها منتظر می‌مانند. پس اولین اجرا چند دقیقه طول می‌کشد.

### مرحلهٔ ۲: لایهٔ BI

دادهٔ خام در سه پایگاه دادهٔ جدا پخش است (`CrimeManagementDb`، `DeviceManagement` و `UserManagementDb`) و برای نمودار مناسب نیست. پس در `CrimeManagementDb` یک schema به نام `bi` ساختیم که داده را مرتب و یک‌جا نگه می‌دارد:

- با `postgres_fdw` جدول‌های دو پایگاه دادهٔ دیگر را طوری وصل کردیم که انگار داخل همین پایگاه داده‌اند.
- تابع `bi.to_jalali()` تاریخ میلادی را به شمسی تبدیل می‌کند.
- `bi.company` **درخت شرکت‌ها** است: «راهنمایی و رانندگی کل کشور» در بالا، و «پلیس استان قم» و «پلیس استان تهران» زیر آن. `bi.company_closure` برای هر شرکت، همهٔ شرکت‌های زیرمجموعه‌اش را فهرست می‌کند.
- `bi.app_user` کاربران واقعی سامانه و شرکت هر کدام است. `bi.company_user` سه کاربر آزمایشی Superset را به شرکت‌ها وصل می‌کند.
- `bi.vehicle` فهرست خودروهاست. نکته: در دادهٔ اصلی، شناسهٔ دستگاه در جدول تخلفات **یکی بیشتر** از شناسهٔ دستگاه در جدول دستگاه‌هاست؛ این اختلاف همین‌جا درست شده است.
- `bi.violation` جدول اصلی است: هر سطر یک بار ثبت سرعت. جمعاً **۹۳۱٬۳۳۵** سطر در ۵ روز: قم **۵۱۱٬۳۹۲** و تهران **۴۱۹٬۹۴۳**.
- نقش فقط‌خواندنی `bi_reader` ساخته می‌شود و Superset فقط با همین نقش به داده وصل می‌شود.

اگر `02-bi.sql` را تغییر دادید، لازم نیست بک‌آپ را دوباره بازگردانید؛ فقط این را اجرا کنید:

```bash
docker compose exec -T backup-db psql -U postgres -q < backups/02-bi.sql
```

### مرحلهٔ ۳: داشبوردها

اسکریپت `superset/bootstrap_traffic.py` همه چیز را خودکار می‌سازد (نیازی به کلیک دستی در Superset نیست و اجرای دوباره‌اش بی‌خطر است). یک داشبورد با دو نسخه ساخته می‌شود:

- بالای داشبورد: شاخص‌های کلیدی (تعداد پایش، تعداد تخلف، نرخ تخلف، تعداد خودرو، تعداد راننده).
- زبانهٔ **نمای کلی و سازمان**: نمودارهای مقایسهٔ استان‌ها، روزانه، ساعتی و نقشهٔ حرارتی روز × ساعت.
- زبانهٔ **نقشه‌ها**: نقشهٔ سه‌بعدی، نقشهٔ تراکم و نقشهٔ نقطه‌ای. نقطه‌ها روی یک شبکهٔ حدوداً ۱۰۰ متری جمع می‌شوند تا ۹۰۰ هزار نقطه به مرورگر فرستاده نشود.
- زبانهٔ **محورها، خودروها و رانندگان**: پرتخلف‌ترین محورها، خودروها و رانندگان.

دو نسخه:

1. `traffic-fa` برای **ورود مستقیم** به Superset است. یک قانون RLS (محدودیت در سطح سطر) بر اساس نام کاربر واردشده، داده را محدود می‌کند. کاربران آزمایشی `traffic_national`، `traffic_qom` و `traffic_tehran` هستند و رمز هر کدام همان نام کاربری است.
2. `traffic-fa-embedded` برای **نمایش داخل برنامهٔ دیگر** (embed) است و از dataset مجازی `violation_scoped` استفاده می‌کند (مرحلهٔ ۴).

### مرحلهٔ ۴: هر شرکت فقط دادهٔ خودش را ببیند

قاعده ساده است: **هر کاربر دادهٔ شرکت خودش و همهٔ شرکت‌های زیرمجموعه‌اش را می‌بیند.** کاربر کل کشور همه چیز را می‌بیند و کاربر قم فقط قم را. روال کار:

1. در برنامهٔ نمونه (`embed-app/app.py`، پورت 8090) اول کاربر را انتخاب می‌کنید، بعد شرکت را. فهرست شرکت‌ها فقط شرکت خود کاربر و زیرمجموعه‌هایش را نشان می‌دهد. سرور هم انتخاب را دوباره بررسی می‌کند تا کسی با دست‌کاری درخواست نتواند شرکت دیگری را ببیند.
2. برنامه با یک پرس‌وجوی بازگشتی (recursive CTE)، شناسهٔ شرکت انتخاب‌شده و همهٔ زیرمجموعه‌هایش را پیدا می‌کند.
3. برنامه از Superset یک «توکن مهمان» (guest token) می‌گیرد. Superset 6.1 اجازه نمی‌دهد اطلاعات اضافه در توکن بفرستیم، پس شناسه‌ها را **داخل نام کاربری** می‌گذاریم، به این شکل: `"user|id1, id2"`. قسمت `rls` توکن خالی می‌ماند.
4. در `superset/superset_config.py` تابعی به نام `get_guest_user_attribute('allowed_companies')` تعریف کرده‌ایم که شناسه‌ها را از نام کاربری بیرون می‌کشد.
5. dataset مجازی `violation_scoped` با همین تابع فیلتر می‌کند. **اگر شناسه‌ای نباشد، هیچ سطری برنمی‌گرداند** (با `AND 1=0`). یعنی در صورت خطا، به‌جای نشت داده، داشبورد خالی می‌شود.

جزئیات بیشتر و قوانین ساخت dataset برای داشبوردهای embed در [SUPERSET_RLS_GUIDE.md](SUPERSET_RLS_GUIDE.md) است.

### تاریخ شمسی: یک راه‌حل ممکن

Superset تقویم شمسی ندارد. ما تاریخ را **موقع ساختن داده، داخل خود پایگاه داده** به شمسی تبدیل می‌کنیم و ستون‌های آماده به Superset می‌دهیم. این فقط یکی از راه‌هاست.

**تابع تبدیل.** تابع `bi.to_jalali(date)` در `backups/02-bi.sql` فقط با چند محاسبهٔ ساده تاریخ میلادی را شمسی می‌کند و به هیچ افزونه یا پلاگینی نیاز ندارد. مثلاً `2025-03-10` می‌شود `1403-12-20`. متن کامل تابع در بخش انگلیسی بالا ([Jalali (Persian) dates](#jalali-persian-dates-one-possible-approach)) آمده است.

**چطور استفاده می‌شود.** این تابع فقط یک بار، هنگام ساختن جدول `bi.violation`، اجرا می‌شود و این ستون‌ها را پر می‌کند:

- `occurred_at`: زمان واقعی به وقت تهران (برای محاسبه‌های دقیق نگه داشته شده).
- `jalali_date`: تاریخ شمسی به شکل `1403-12-20`، و `jalali_month`: ماه شمسی به شکل `1403-12`.
- `weekday`: نام روز هفته به فارسی با یک عدد در ابتدا (`۰ شنبه` تا `۶ جمعه`) تا هفته از شنبه مرتب شود.
- `hour_of_day`: ساعت روز (۰ تا ۲۳).

**Superset چطور از آن‌ها استفاده می‌کند.** مثل یک متن معمولی. نمودارها بر اساس `jalali_date` یا `jalali_month` گروه‌بندی می‌شوند و فیلتر «تاریخ (شمسی)» یک فهرست کشویی از مقدارهای `jalali_date` است. چون تاریخ به شکل `YYYY-MM-DD` نوشته شده، مرتب کردن الفبایی همان مرتب کردن بر اساس تاریخ است.

**مزیت‌ها**
- نیازی به پلاگین یا ساختن دوبارهٔ ظاهر Superset نیست.
- سریع است، چون تبدیل فقط یک بار هنگام بارگذاری داده انجام می‌شود.
- زمان واقعی هم حفظ می‌شود.

**محدودیت‌ها**
- بازه‌های زمانی Superset (روز/ماه/سال)، انتخاب‌گر بازهٔ تاریخ و گزینه‌هایی مثل «۷ روز گذشته» همچنان میلادی هستند.
- هر جدول جدید باید همین ستون‌های شمسی را داشته باشد.
- چون محور متنی است، روزهایی که داده ندارند اصلاً نمایش داده نمی‌شوند (جای خالی نمی‌ماند).

**راه دیگر (پیاده‌سازی نشده، پیشنهاد برای بررسی)**
- در پایگاه داده فقط زمان واقعی نگه داشته شود.
- با `TIME_GRAIN_ADDON_EXPRESSIONS` در `superset_config.py` بازهٔ ماه و سال شمسی اضافه شود تا گروه‌بندی همچنان در پایگاه داده انجام شود.
- یک قالب‌بند زمان (time formatter) اختصاصی در ظاهر Superset با `Intl.DateTimeFormat('fa-IR-u-ca-persian')` اضافه شود تا برچسب‌ها شمسی نمایش داده شوند.
- انتخاب‌گر بازهٔ تاریخ همچنان میلادی می‌ماند، مگر اینکه ظاهر Superset بیشتر تغییر کند.

### چرا کش خاموش است؟

Superset معمولاً نتیجهٔ نمودارها را کش می‌کند تا دفعهٔ بعد سریع‌تر باشد. اما کلید کش شامل مقدار تابع اختصاصی ما (فهرست شرکت‌ها) نیست. اگر کش روشن باشد، ممکن است نتیجه‌ای که برای قم ساخته شده به کاربر تهران نشان داده شود. برای همین در `superset_config.py` کش داده خاموش است:

```python
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
```

**این را روشن نکنید**، مگر اینکه آن تابع طوری تغییر کند که فهرست شرکت‌ها وارد کلید کش شود.

### اجرا و بررسی

```bash
docker build -t superset-demo:6.1.0-pg ./superset       # فقط بار اول
docker compose up -d
docker compose logs -f superset-bootstrap               # صبر کنید تا TRAFFIC_BOOTSTRAP_DONE چاپ شود
```

بعد:

1. http://localhost:8090 را باز کنید و کاربرها و شرکت‌ها را عوض کنید. عدد «کل پایش‌های سرعت» باید این‌طور باشد:

| انتخاب | تعداد کل پایش |
|---|---|
| `fkreza` (کل کشور) | 931,335 |
| `fkreza` ← شرکت تهران | 419,943 |
| `navidahmadian` (قم) | 511,392 |
| `superadmin` (بدون شرکت) | 0 (حالت ایمن) |

2. در http://localhost:8088 با `traffic_qom` / `traffic_qom` وارد شوید و داشبورد `traffic-fa` را باز کنید؛ باید همان اعداد قم را ببینید.

دستورهای کاربردی دیگر:

```bash
docker compose run --rm superset-bootstrap               # ساخت دوبارهٔ داشبوردها
docker compose restart superset embed-app                # بعد از تغییر تنظیمات یا embed-app
docker compose down                                      # خاموش کردن (داده می‌ماند)
docker compose down -v                                   # خاموش کردن و پاک کردن همهٔ داده‌ها
```

</div>

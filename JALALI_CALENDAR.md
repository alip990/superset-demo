# Jalali (Persian) calendar in Superset: every option

Superset only knows the Gregorian calendar. To show Persian dates we have to solve
**three separate problems**, and each one is solved in a different place:

| Problem | Example | Where it can be solved |
|---|---|---|
| **1. Show** a date in Jalali | axis label `20 اسفند`, tooltip `دوشنبه 20 اسفند 1403` | Superset frontend, or a text column from the database |
| **2. Group** by a Jalali period | one bar per Jalali month (Esfand = 20 Feb – 20 Mar) | where the SQL runs: database or Trino |
| **3. Filter** by Jalali dates | "Esfand 1403", "from 1 Farvardin" | native filter on a Jalali column, or the date picker (Gregorian only) |

A formatter alone can't group: the Esfand bucket must be built by the database. A
database column alone can't make Superset's own time axis and tooltips Jalali. So in
practice we combine options.

## What is implemented in this repo

| # | Approach | Status | Files |
|---|---|---|---|
| A | Postgres function `bi.to_jalali()` + stored Jalali text columns | ✅ in use since the first dashboard, kept as is | `backups/02-bi.sql` |
| B | **Superset frontend plugin**: Jalali time formatters | ✅ implemented | `plugins/superset-jalali/`, `superset/Dockerfile` |
| C | **Jalali time grains** (`Jalali month`, `Jalali year`) for Postgres | ✅ implemented | `superset/superset_config.py` |
| D | Trino: Jalali functions (plugin / SQL routine) + grains | 📝 planned, next step | – |
| E | Calendar table `dim_date` | 💡 option | – |
| F | Change the date-range picker to a Jalali picker | 💡 option, most work | – |

---

## A. Postgres function + Jalali columns (existing)

`bi.to_jalali(date) → text` in `backups/02-bi.sql` is plain arithmetic (no extension).
It runs **once**, when `bi.violation` is built, and fills `jalali_date` (`1403-12-20`),
`jalali_month` (`1403-12`) and `weekday` (`۰ شنبه`...). Charts use them as **text
categories**, and the native filter "تاریخ (شمسی)" is a dropdown of `jalali_date`.
The real timestamp `occurred_at` stays in the table. Full code and pros/cons: README,
section "Jalali (Persian) dates".

- ➕ no Superset change; fast; filters show Jalali values.
- ➖ Superset treats them as text, not time: no real time axis, no gaps for missing
  days, no time grains; every new table needs the same columns.

## B. Superset frontend plugin: Jalali formatters (implemented)

Superset formats every date in the browser through a **time formatter registry**
(`getTimeFormatterRegistry()` in `@superset-ui/core`). Built-in entries are d3 formats
and `smart_date` ("Adaptive formatting", the default for time axes). We add our own
entries. The conversion uses the browser's built-in Persian calendar,
`Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {timeZone: 'UTC'})`, so it needs no
library and works for **any database**.

**Why UTC:** Superset renders naive timestamps as UTC. Our `occurred_at` is Tehran local
time without a zone. Formatting in the browser's zone could move a date to the wrong
Jalali day, so every formatter uses `timeZone: 'UTC'`, like Superset's own.

Registered formats (pick them in a chart's *Time format* / *X axis time format*, they are
added to the dropdown):

| id | Output |
|---|---|
| `jalali_smart` | axis labels: `14:30`, `20 اسفند`, `فروردین` (1st of a month), `1404` (1 Farvardin) |
| `jalali_date` | `1403-12-20` |
| `jalali_datetime` | `1403-12-20 14:32:05` |
| `jalali_month` | `اسفند 1403` |
| `jalali_year` | `1403` |
| `jalali_verbose` | `دوشنبه 20 اسفند 1403` |

**Global switch:** with `FEATURE_FLAGS["JALALI_CALENDAR"] = True` in
`superset/superset_config.py`, the plugin also replaces `smart_date`,
`smart_date_verbose` (tooltips) and `smart_date_detailed`. Every existing chart that uses
the default time format becomes Jalali without editing it. The flag is ours; the stock
Superset image ignores it.

**How it gets into Superset:** Superset has no runtime hook for formatters, so the
frontend is rebuilt. `superset/Dockerfile`:

1. clones Superset at the **same tag** as the backend image (`6.1.0`);
2. copies `plugins/superset-jalali/src/` to `superset-frontend/src/jalali/`;
3. runs `setupFormatters.patch.sh`, which adds one call, `registerJalaliFormatters()`, at
   the end of `src/setup/setupFormatters.ts` (the embedded dashboard runs the same setup);
4. `npm ci && npm run build`, then replaces `/app/superset/static/assets` in the
   `apache/superset:6.1.0` image with the new build.

```bash
docker compose build superset       # ~8 GB RAM; the first build is slow (npm ci + webpack)
docker compose up -d
```

Rollback: set the image back to `superset-demo:6.1.0-pg` (stock frontend) in
`docker-compose.yml`. The old image is kept.

- ➕ real time axis in Jalali; tooltips, tables, any database; one switch.
- ➖ custom frontend build to maintain on each Superset upgrade (the patch is one line);
  axis tick positions are still chosen by ECharts on Gregorian boundaries (each tick is
  labelled with its correct Jalali date, e.g. `11 اسفند` for 1 March); grouping by Jalali
  month needs C; the date-range picker stays Gregorian.

## C. Jalali time grains (implemented, Postgres)

`TIME_GRAIN_ADDONS` adds **Jalali month** and **Jalali year** to every chart's *Time grain*
menu. `TIME_GRAIN_ADDON_EXPRESSIONS["postgresql"]` tells Superset how to compute them. Each
bucket is the Gregorian timestamp of the 1st of the Jalali month/year, computed with
`bi.to_jalali`:

```sql
-- JALALI_MONTH: date minus (day of the Jalali month - 1)
((col)::date - (split_part(bi.to_jalali((col)::date), '-', 3)::int - 1))::timestamp
-- JALALI_YEAR: date minus (day of the Jalali year - 1); months 1-6 have 31 days, 7-11 have 30
```

The B formatter then labels the bucket `اسفند 1403`. Checked for every day from
2023-03-19 to 2026-03-22 (1,100 days, including leap year 1403 whose Esfand has 30 days):
all buckets start on the 1st of the right Jalali month and year.

- ➕ grouping happens in the database; works with the real timestamp column.
- ➖ only on databases that have `bi.to_jalali` (our `CrimeManagementDb`), other Postgres
  databases get an error if someone picks the grain; it evaluates the function per row
  (~4 s on 931k rows here; E is faster).

**Demo:** the dashboard's Overview tab, last row:
- *روند روزانه روی محور زمان (فرمت‌کننده شمسی)*: `occurred_at` by day, default format →
  Jalali labels and tooltips from the plugin (B).
- *تخلفات به تفکیک ماه شمسی*: `occurred_at` with the *Jalali month* grain (C), format
  `jalali_month`.

Note: the demo data only has 5 days (1403-12-20..25 and 1404-01-30), so it has two Jalali
months (Esfand 1403, Farvardin 1404). Gregorian months give the same two groups here
(March/April 2025), so the demo can't show the difference; the SQL check above does.

## D. Trino (planned)

When ScyllaDB (or other sources) is queried through Trino, the Jalali logic has to exist in
Trino too; the Postgres function isn't available there.

1. **Trino plugin (Java)**: a `Plugin` exposing scalar functions via Trino's SPI
   (`@ScalarFunction`), e.g. `to_jalali(date) → varchar`, `jalali_month_start(timestamp)`,
   `jalali_year_start(timestamp)`. Packaged as a jar in `plugin/jalali/` of the Trino
   server. Fast (compiled), works on every catalog, but it's Java code to build and deploy.
2. **Trino SQL routines**: newer Trino versions support functions written in SQL (inline
   `WITH FUNCTION`, or stored `CREATE FUNCTION` in a catalog that supports it). Same
   arithmetic as `bi.to_jalali`, no Java, but slower and version-dependent.
3. Then add `TIME_GRAIN_ADDON_EXPRESSIONS["trino"]` with the same two grains, calling the
   Trino function. The frontend plugin (B) needs no change: it formats whatever timestamp
   Trino returns.

## E. Calendar table `dim_date` (option)

One row per day (e.g. 1390–1420, ~11,000 rows): `gregorian_date`, `jalali_date`,
`jalali_year`, `jalali_month`, `jalali_month_name`, `jalali_month_start`, `weekday_fa`,
`is_holiday`... Filled once (with `bi.to_jalali` or Python `jdatetime`). Datasets join it
on the date.

- ➕ works with every engine (Postgres, ClickHouse, Scylla through Trino) with no
  functions; much faster than calling a function per row; can hold **Iranian holidays**,
  which no formula can compute; month names and fiscal periods are just columns.
- ➖ every dataset needs the join; Superset's time grain menu doesn't use it (you group by
  its columns instead).

## F. Jalali date-range picker (option)

Superset's time-range filter ("Last week", custom start/end) is Gregorian. Making it Jalali
means replacing the date picker component in the frontend (e.g. with a Jalali antd/dayjs
picker) and converting to Gregorian before sending: a larger, riskier frontend change.
Workaround in use: a native select filter on `jalali_date` / `jalali_month` (A).

## Recommendation

- Keep A for filters and simple categories (already works).
- Use B + C for real time charts (implemented now).
- For Trino / ScyllaDB: D (start with a SQL routine, move to a Java plugin if it's slow or
  used widely), and E if we need holidays or many engines.
- F only if users really need to type Jalali ranges.

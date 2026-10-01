# Jalali (Persian) calendar in Superset 6.1.0

Superset only knows the Gregorian calendar. Making it Persian means solving
**four** separate problems, in four different places:

| | Problem | Example | Where it is solved |
|---|---|---|---|
| 1 | **Show** a date in Jalali | axis label `20 اسفند`, tooltip `دوشنبه 20 اسفند 1403` | the browser: time-format registry |
| 2 | **Group** by a Jalali period | one bar per Jalali month (Esfand = 19 Feb – 20 Mar) | the database: SQL the time grain emits |
| 3 | **Filter** by Jalali dates | "ماه جاری (شمسی)", "از ابتدای سال", 1403-12-01 … 1404-01-01 | the server resolves the range, the browser offers and shows it |
| 4 | **Know** the calendar | Esfand 1403 has 30 days, Friday is the weekend, 13 Farvardin is a holiday | one algorithm, shared by all of the above |

A formatter alone cannot group: the Esfand bucket has to be built by the
database. A database column alone cannot make Superset's own axis, tooltips and
date picker Persian. So all four are implemented, and they share one calendar.

Everything here works on **stock Superset 6.1.0** except the browser half, which
needs the frontend rebuilt (one image, one documented command).

---

## What is implemented

| Where | What | Needs |
|---|---|---|
| `superset/jalali_calendar/` | 5 Jalali **time grains** as inline SQL for 21 engines; the Jalali **time-range vocabulary**, resolved server-side; 8 **dataset macros**; the options the browser reads | config only (`FLASK_APP_MUTATOR`) |
| `plugins/superset-jalali/` | Jalali **time formats** in every chart (and as Superset's default); Jalali **shortcuts** in the date-filter popover; a Jalali **date picker**; the resolved range shown in Jalali | custom frontend build |
| `db/jalali.sql` | Jalali functions in PostgreSQL (`jalali.format`, `jalali.month_start`, …), `jalali.dim_date` with Iranian **weekends and holidays** | `psql -f` once, optional |
| `tests/`, `plugins/superset-jalali/tests/` | the calendar, the grains in two SQL engines, the vocabulary, the SQL library and both implementations against each other | nothing |

Superseded: `bi.to_jalali()` / `jalali_date` text columns (`backups/02-bi.sql`,
`db/01-init.sql`) still exist and still work - the existing charts use them - but
new work does not need them. Nothing in this feature calls them any more.

---

## 4. The calendar, first

Everything else is built on `superset/jalali_calendar/core.py` and its literal
port `plugins/superset-jalali/src/core/jalali.ts`.

* The conversion is **Borkowski's algorithm** (what `jalaali-js`,
  `moment-jalaali` and `jdf` use), which reproduces the *official* Iranian
  calendar - the one on Iranian wall calendars - for Jalali years 1178–1633
  (1799–2256 CE).
* No dependency and no `Intl`. The first version of the plugin asked the browser
  (`Intl.DateTimeFormat('fa-IR-u-ca-persian')`); arithmetic replaced it because
  `Intl` depends on the ICU build behind the runtime (a `small-icu` Node build has
  no Persian calendar at all), it cannot be asked about an arbitrary offset, and
  `formatToParts()` per cell is slow in a big table.
* Verified for **every day from 1900-01-01 to 2200-12-31** (109,938 days) against
  three independent oracles: the browser's own ICU Persian calendar, the Python
  implementation, and the existing `bi.to_jalali()` in this repo. All agree.
  1403 is a leap year, 30 Esfand 1403 = 2025-03-20, Nowruz 1404 = 2025-03-21.
* The Iranian week starts on **Saturday**, quarters are the four **seasons**
  (`بهار` = months 1–3 … `زمستان` = 10–12), and month lengths are
  31×6, 30×5, then 29 or 30.

```python
>>> from jalali_calendar import core
>>> core.to_jalali(date(2025, 3, 20))         # JalaliDate(year=1403, month=12, day=30)
>>> core.format_jalali(dt, 'dddd D MMMM YYYY')   # 'دوشنبه 20 اسفند 1403'
>>> core.month_start(date(2025, 3, 10))       # date(2025, 2, 19)  -> 1 Esfand
>>> core.parse_literal('۱۴۰۳/۱۲/۲۰').date     # date(2025, 3, 10)
```

### Time zones

Superset renders naive timestamps as UTC, and this repo's `occurred_at` is
already Tehran local time, so the default shift is **0**. If your data is stored
in **UTC** and the business day is Tehran's, set

```python
JALALI_CALENDAR_OPTIONS = {"shift_minutes": 210}   # Asia/Tehran = UTC+3:30
```

and both the grains and the labels move the instant before deciding which Jalali
day it belongs to. Without it, every day would break at 03:30 local time. For
`timestamptz` columns with the installed SQL functions, set the session or
database `TimeZone` to `Asia/Tehran` instead - those functions follow it, exactly
as PostgreSQL's own `date_trunc(text, timestamptz)` does.

---

## 2. Time grains: grouping by a Jalali period

Every chart's **Time grain** menu gains five entries:

| Grain | Label | Bucket |
|---|---|---|
| `JALALI_WEEK` | هفته شمسی (شنبه) | the Saturday that starts the week |
| `JALALI_MONTH` | ماه شمسی | the 1st of the Jalali month |
| `JALALI_QUARTER` | فصل شمسی | 1 Farvardin / 1 Tir / 1 Mehr / 1 Dey |
| `JALALI_HALF_YEAR` | نیم‌سال شمسی | 1 Farvardin / 1 Mehr |
| `JALALI_YEAR` | سال شمسی | Nowruz |

Superset asks the engine spec for `TIME_GRAIN_ADDON_EXPRESSIONS[engine][grain]`
and substitutes `{col}`. The expressions are **pure integer arithmetic**, so they
need nothing installed in the database:

```sql
-- JALALI_MONTH on PostgreSQL, folded for readability
((col)::date - (CASE WHEN doy0 < 186 THEN mod(doy0, 31) ELSE mod(doy0 - 186, 30) END))::timestamp
--  where doy0, the 0-based day of the Jalali year, is
--  mod(mod((col::date - DATE '2000-01-01') + 965622, 12053), 1461), minus one
--  day inside the leap year that opens each 4-year sub-cycle
```

33 Jalali years are exactly 12053 days and 4 are 1461, so two divisions put any
date in its place inside the cycle; the rest is subtraction. 2000-01-01 was a
Saturday, which is why the week grain is just `col - mod(x, 7)`.

**Engines.** postgresql, redshift, cockroachdb, crate, duckdb, trino, presto,
athena, mysql, mariadb, clickhouse (3 dialect names), bigquery, sqlite,
databricks, hive, spark, sparksql, snowflake, mssql - 21 keys, generated from one
table of SQL primitives in `grains.py`, so adding an engine is five lines.

**Cost.** A handful of integer operations per row and no function call - the
predecessor of this module called a PL/pgSQL `bi.to_jalali()` per row (~4 s on
931k rows). For large tables either index the expression

```sql
CREATE INDEX ON bi.violation ((mod((occurred_at::date - DATE '2000-01-01') + 965622, 12053)));
```

or, with `db/jalali.sql` installed, switch to the short indexable functions:

```python
JALALI_CALENDAR_OPTIONS = {"grain_mode": "function"}   # jalali.month_start({col})
```

or join `jalali.dim_date` (below), which is the fastest of the three.

---

## 3. Filtering: the Jalali date picker

Superset resolves time ranges **on the server** -
`superset/utils/date_parser.py: get_since_until()`. The explore UI only displays
what the API returned, and alerts, reports, CSV exports and embedded dashboards
never run the UI at all. So the Jalali vocabulary lives in
`jalali_calendar/ranges.py`, wrapped around that function: a Jalali expression is
rewritten to the plain ISO `since : until` string Superset already understands,
everything else is passed through untouched. Time shifts, time comparison and
validation stay exactly as upstream wrote them, and **a saved chart keeps working
when nobody is looking at it**.

### The vocabulary

Anything in the first column can be typed into the *Advanced* frame, stored in a
saved chart, set as a dashboard's default time range, or used by an alert.
"jalali" may also be spelled "shamsi"; Persian and Arabic-Indic digits are
accepted everywhere; matching is case-insensitive.

| Expression | Means | Shown in the popover as |
|---|---|---|
| `Current jalali day` | today | امروز |
| `Current jalali week` | Saturday → next Saturday | هفته جاری (شمسی) |
| `Current jalali month` | 1st of this Jalali month → 1st of the next | ماه جاری (شمسی) |
| `Current jalali quarter` | this season | فصل جاری (شمسی) |
| `Current jalali year` | Nowruz → next Nowruz | سال جاری (شمسی) |
| `Current jalali half` | this half-year | – (type it) |
| `previous jalali week/month/quarter/year` | the whole previous period | هفته/ماه/فصل/سال تقویمی قبل |
| `Last jalali week/month/quarter/year` | rolling: one Jalali period back → today | هفته/ماه/فصل/سال گذشته |
| `Last 3 jalali months` | rolling, any count and unit | – (type it) |
| `Next 2 jalali weeks` | forward-looking | – (type it) |
| `jalali month/quarter/year to date` | 1st of the period → end of today | از ابتدای ماه/فصل/سال تا امروز |
| `jalali:1403` | all of 1403 | – (type it) |
| `jalali:1403-12` | all of Esfand | – |
| `jalali:1403-q4` | winter 1403 | – |
| `jalali:1403-12-20` | that one day | – |
| `1403-12-01 : 1404-01-01` | an explicit range (`bare_literals`) | – |
| `jalali:1403-12-20 : now` | mixed with Superset's own grammar | – |

Rolling units are real Jalali arithmetic, not 30 days: "Last jalali month" from
20 Esfand is 20 Bahman. All boundaries are midnight-aligned, `since` inclusive
and `until` exclusive - like Superset's own calendar ranges. "to date" ends at
midnight *tomorrow*, so today's rows are in.

### In the UI

The *Last*, *Previous* and *Current* frames of the date-filter popover gain the
Persian options above - in every chart, every native dashboard filter and every
adhoc temporal filter, because they all use the same control. The *Custom* frame
gets a **Jalali month grid**: Saturday first, Persian month names, Friday in red,
today outlined, year and month dropdowns, arrow-key navigation, an optional
time-of-day field, and a text box that accepts `1403/12/20`, `۱۴۰۳/۱۲/۲۰` or
`1403-12-20 14:30`. What it stores is still the ISO Gregorian string stock
Superset stores, so a chart saved with it opens in a stock Superset unchanged.

The control's pill, its tooltip and the popover's *Actual time range* line show
the resolved range in Jalali (`1404-01-01 ≤ col < 1404-02-01`).

---

## 1. Showing dates in Jalali

`plugins/superset-jalali/src/formatters.ts` registers these in Superset's
time-format registry; they appear in every chart's *Time format* /
*X axis time format* dropdown:

| id | Output |
|---|---|
| `jalali_smart` | adaptive, like Superset's own: `14:30`, `20 اسفند`, `اسفند` on the 1st, `1404` on Nowruz |
| `jalali_date` | `1403-12-20` |
| `jalali_datetime` | `1403-12-20 14:32:05` |
| `jalali_minute` | `1403-12-20 14:32` |
| `jalali_month` | `اسفند 1403` |
| `jalali_month_short` | `1403-12` |
| `jalali_quarter` | `زمستان 1403` |
| `jalali_year` | `1403` |
| `jalali_week` | `هفته 51 - 1403` |
| `jalali_verbose` | `دوشنبه 20 اسفند 1403` |
| `jalali_day_month` | `20 اسفند` |
| `…_fa` | the five most used, always with Persian digits (`۱۴۰۳-۱۲-۲۰`) |

With `override_smart_date` (the default) the plugin also replaces Superset's own
`smart_date`, `smart_date_verbose` and `smart_date_detailed`, so **every chart
that never picked a time format becomes Jalali** - axes, tooltips, table cells -
without being edited. Set `digits: "persian"` to switch every label to
`۱۴۰۳-۱۲-۲۰` at once.

---

## Dataset macros

With `ENABLE_TEMPLATE_PROCESSING` on, datasets and SQL Lab can use:

| Macro | Returns |
|---|---|
| `{{ jalali_today() }}` | `1405-07-09` (any format string: `jalali_today('D MMMM YYYY')`) |
| `{{ jalali_now() }}` | `1405-07-09 22:15:04` |
| `{{ to_jalali('2025-03-20') }}` | `1403-12-30` |
| `{{ from_jalali('1403-12-20') }}` | `2025-03-10` - hard-code Jalali dates in SQL |
| `{{ jalali_start('month', -1) }}` | first instant of last Jalali month |
| `{{ jalali_end('month') }}` | exclusive end of this Jalali month |
| `{{ jalali_filter('occurred_at', 'jalali year to date') }}` | `occurred_at >= '…' AND occurred_at < '…'` for any expression of the vocabulary |
| `{{ jalali_grain('occurred_at', 'month') }}` | the grain SQL, as a column |

They are installed as `ExtraCache` methods and added to `ExtraCache.regex` - the
same mechanism `superset/guest_user_attributes.py` uses - so the ones whose value
depends on the date **reach the query cache key**. Without that, a chart filtered
on "this Jalali month" would keep serving last month's rows from Redis after
midnight on the 1st. The three macros that depend only on their arguments
deliberately add nothing to the cache key.

---

## `db/jalali.sql`: the calendar in PostgreSQL

Optional; install it into the database your datasets live in:

```bash
docker compose exec -T db psql -U postgres -d demo < db/jalali.sql          # done automatically
docker compose exec -T backup-db psql -U postgres -d CrimeManagementDb < db/jalali.sql
```

* `jalali.year/month/day/quarter/doy0/day_of_week/is_weekend/is_leap/days_in_month`
* `jalali.day_start/week_start/month_start/quarter_start/half_year_start/year_start`
  - `IMMUTABLE`, so they can back an index, and `grain_mode: "function"` uses them
* `jalali.format(ts, 'dddd D MMMM YYYY')`, `jalali.month_name/weekday_name/season_name`,
  `jalali.to_persian_digits`
* `jalali.to_gregorian(1403, 12, 30)`, `jalali.year_start_of(1404)`
* every function in `date`, `timestamp` and `timestamptz` flavours, because
  PostgreSQL will not implicitly narrow a timestamp to a date when it resolves a
  call

### `jalali.dim_date`: weekends, holidays, working days

```sql
SELECT jalali.build_dim_date(1390, 1420);   -- 11,000 rows, runs in seconds
```

One row per day with `jalali_date`, `jalali_month`, `jmonth_label`, `jquarter`,
`jquarter_name`, `jhalf`, `jweek_of_year`, `jday_of_year`, `jdow`, `jdow_name`,
`is_weekend`, `is_holiday`, `holiday_title`, `is_working_day` and the four period
starts. Join it on the date for the fastest possible Jalali grouping, for Persian
month names as a dimension, and for the one thing no formula can produce:

* **`jalali.holiday_rule`** holds the holidays that fall on a fixed Jalali date
  and are therefore computable: Nowruz 1–4, 12 and 13 Farvardin, 14 and 15
  Khordad, 22 Bahman, 29 Esfand. Seeded by the script.
* **`jalali.holiday_override`** is where the *lunar* holidays go. They follow the
  Islamic calendar and are announced each year, so nothing can compute them -
  load them from the official calendar and they win over the rules:

  ```sql
  INSERT INTO jalali.holiday_override VALUES ('2025-01-14', 'شهادت حضرت فاطمه', true);
  ```

  Until they are loaded, `is_holiday` only reflects the fixed ones, and
  `is_working_day` is correspondingly optimistic. That is a data problem, not a
  code one; the table is the honest place for it.

---

## Configuration

Everything is in one dict in `superset/superset_config.py`; every key is
optional.

```python
JALALI_CALENDAR_OPTIONS = {
    "enabled": True,              # master switch for the browser half
    "digits": "latin",            # or "persian": ۱۴۰۳-۱۲-۲۰ everywhere
    "override_smart_date": True,  # replace Superset's own adaptive formatters
    "shift_minutes": 0,           # 210 for UTC-stored data of an Asia/Tehran business
    "bare_literals": True,        # accept 1403-12-20 without the "jalali:" prefix
    "grain_mode": "inline",       # or "function" (needs db/jalali.sql)
    "grains": ["JALALI_WEEK", "JALALI_MONTH", "JALALI_QUARTER",
               "JALALI_HALF_YEAR", "JALALI_YEAR"],
    "grain_labels": {"JALALI_MONTH": "ماه شمسی"},   # rename what the menu shows
    "thursday_is_weekend": False, # Thursday greyed out in the picker as well
}

def FLASK_APP_MUTATOR(app):
    import jalali_calendar
    jalali_calendar.install(app)
```

`install()` is idempotent, logs one line with what it patched, and never raises
on a Superset it does not recognise - it logs and leaves that part Gregorian.
Also available: `DEFAULT_TIME_FILTER = "Current jalali month"` makes every new
chart open on the current Jalali month (left commented out in this repo, because
the demo data only covers a few days).

## Build and run

The backend half needs nothing: `docker compose up -d` and the grains, the
vocabulary and the macros are there. For the browser half:

```bash
docker compose --profile build build superset-frontend-build   # ~8 GB RAM, 20-40 min
SUPERSET_IMAGE=superset-demo:6.1.0-jalali docker compose up -d
```

`superset/Dockerfile` clones Superset at the **same tag as the backend** (6.1.0),
copies `plugins/superset-jalali/src/` to `superset-frontend/src/jalali/`, runs the
three patches in `plugins/superset-jalali/patches/`, builds, and replaces
`/app/superset/static/assets` as a whole (chunk names and `manifest.json` must
match). Rollback is `unset SUPERSET_IMAGE`.

## Tests

```bash
tests/run.sh                                     # 61 Python tests + 17 plugin tests
JALALI_TEST_PG_DSN=postgresql://… tests/run.sh    # + the same grains in PostgreSQL
```

| Suite | Checks |
|---|---|
| `tests/test_jalali_core.py` | round trip for 109,938 days; the official leap years; month lengths; formatting; parsing; **every day against the ICU Persian calendar** |
| `tests/test_jalali_grains.py` | the magic constants recomputed from the calendar; every generated expression executed in **SQLite** for 109,938 days; the same in **PostgreSQL** when a DSN is given |
| `tests/test_jalali_ranges.py` | every shortcut against a frozen "today", hand-checked against an Iranian calendar; that each one resolves (or the Apply button would be dead); that Gregorian ranges are untouched |
| `tests/test_jalali_sql.py` | `db/jalali.sql` against the Python core for 44,000 days, `grain_mode: function` vs `inline` for 18,000 days, `dim_date` row by row, the holidays |
| `plugins/superset-jalali/tests/` | the TypeScript calendar against `tests/fixtures/jalali_cases.json` (generated from Python) and against ICU; the range vocabulary against the backend's |
| `npm run typecheck` | the plugin against hand-written declarations of the Superset modules **and against upstream's own call sites** |

Regenerate the shared fixtures after changing the calendar or the vocabulary:

```bash
python3 tests/test_jalali_core.py --write-fixtures
```

## Limits, and what was deliberately left out

* **The frontend half needs a custom image.** Superset has no runtime hook for
  time formatters or for the picker component. The patches are three small edits
  that fail loudly if upstream moves, but they are still edits to maintain across
  upgrades.
* **Axis tick *positions* are still chosen by ECharts** on Gregorian boundaries.
  Each tick is labelled with its correct Jalali date, so a tick on 1 March reads
  `11 اسفند`; it is the tick spacing, not the label, that is Gregorian. Group by
  a Jalali grain when the buckets themselves have to be Jalali.
* **Lunar holidays cannot be computed** - see `jalali.holiday_override`.
* **No new npm dependency.** The picker is built on Superset's own components
  rather than `antd-jalali`/`dayjs-jalali`, so `package-lock.json` is untouched
  and `npm ci` keeps working in the image build.
* **Dates outside 1178–1633 AP** (1799–2256 CE) are refused rather than guessed:
  the official calendar is not arithmetically predictable outside that window.
* **Not done:** a Jalali *year* picker mode (quarter/year pickers exist in antd
  but no Superset control asks for one), Jalali fiscal years that do not start on
  Nowruz, and Trino/Spark *installed* functions (the inline grains cover those
  engines already).

### When upgrading Superset

1. Bump `ARG SUPERSET_VERSION` in `superset/Dockerfile` and rebuild; the patches
   fail the build if the files they edit moved.
2. Re-run `tests/run.sh` inside the new image: it checks the grain machinery, the
   time-range parser and the Jinja hooks against the real Superset.
3. Check the two upstream internals the backend leans on -
   `ExtraCache.regex` and `get_since_until()`'s signature. `install()` warns in
   the log if it could not patch either.

---

## خلاصه (فارسی)

ساپرست تقویم شمسی ندارد. این مخزن چهار بخش را اضافه می‌کند:

1. **نمایش** - قالب‌های زمانی شمسی در همه نمودارها، و با `override_smart_date`
   جایگزین قالب پیش‌فرض خود ساپرست، پس همه نمودارهای قبلی هم شمسی می‌شوند
   (`plugins/superset-jalali`، نیازمند ساخت ایمیج فرانت‌اند).
2. **گروه‌بندی** - دانه‌بندی‌های زمانی «ماه شمسی»، «فصل شمسی»، «هفته شمسی (شنبه)»،
   «نیم‌سال شمسی» و «سال شمسی» برای ۲۱ موتور پایگاه‌داده، به شکل محاسبات صحیح درون
   SQL؛ هیچ تابعی لازم نیست در پایگاه‌داده نصب شود.
3. **فیلتر** - واژگان بازه زمانی شمسی («ماه جاری (شمسی)»، «از ابتدای سال تا امروز»،
   `jalali:1403-12`) که **در سمت سرور** تفسیر می‌شود، بنابراین نمودارهای ذخیره‌شده،
   هشدارها، گزارش‌ها و داشبوردهای جاسازی‌شده هم درست کار می‌کنند؛ به‌علاوه یک
   **تقویم شمسی** در قسمت Custom انتخابگر تاریخ (شنبه اول هفته، نام ماه‌های فارسی،
   امکان تایپ `۱۴۰۳/۱۲/۲۰`).
4. **تقویم** - یک الگوریتم (بورکوفسکی) در پایتون، تایپ‌اسکریپت و SQL، آزمون‌شده
   روی تمام روزهای ۱۹۰۰ تا ۲۲۰۰ در برابر تقویم فارسی مرورگر؛ ۱۴۰۳ کبیسه است و
   ۳۰ اسفند ۱۴۰۳ برابر ۲۰۲۵-۰۳-۲۰ است.

تنظیمات در `JALALI_CALENDAR_OPTIONS` داخل `superset/superset_config.py` است.
برای داده‌هایی که به وقت UTC ذخیره شده‌اند `shift_minutes: 210` را تنظیم کنید.
جدول `jalali.dim_date` (از `db/jalali.sql`) تعطیلات رسمی با تاریخ ثابت شمسی و
روزهای کاری را دارد؛ تعطیلات قمری را باید در `jalali.holiday_override` وارد کرد.

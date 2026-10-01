-- Jalali (Persian) calendar library for PostgreSQL: schema "jalali".
--
-- Install it into the database your datasets live in (it does not pick one):
--     psql -d demo           -f db/jalali.sql
--     docker compose exec -T db       psql -U postgres -d demo < db/jalali.sql
--     docker compose exec -T backup-db psql -U postgres -d CrimeManagementDb < db/jalali.sql
-- Re-runnable: every object is CREATE OR REPLACE / IF NOT EXISTS, and the data
-- in jalali.dim_date survives unless you rebuild it.
--
-- Nothing in Superset *needs* this file - the time grains in
-- superset/jalali_calendar/grains.py are self-contained arithmetic. Install it
-- when you want:
--   * short, readable grain SQL (JALALI_CALENDAR_OPTIONS = {"grain_mode": "function"}),
--     and an index that can serve it:
--       CREATE INDEX ON bi.violation (jalali.month_start(occurred_at));
--   * Jalali text columns and names in datasets: jalali.format(), month_name() ...
--   * jalali.dim_date: one row per day with Iranian weekends and holidays, which
--     no formula can compute - join it for "working days only" dashboards.
--
-- The arithmetic is the same 33-year-cycle algorithm as the Python core
-- (superset/jalali_calendar/core.py) and the inline grain SQL, verified day by
-- day against both in tests/test_jalali_sql.py, so a dashboard that mixes a
-- time grain with a dim_date join can never disagree with itself.

CREATE SCHEMA IF NOT EXISTS jalali;
COMMENT ON SCHEMA jalali IS
  'Jalali (Persian) calendar: conversion, period starts, names, dim_date. See db/jalali.sql.';

-- ---------------------------------------------------------------- constants --
-- Day count of 2000-01-01 in the 33-year-cycle numbering plus 80 whole cycles,
-- so the value stays positive for any realistic date. Must match
-- superset/jalali_calendar/grains.py (ANCHOR).
CREATE OR REPLACE FUNCTION jalali._x(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (d - DATE '2000-01-01') + 965622 $$;

COMMENT ON FUNCTION jalali._x(date) IS
  'Internal: day number aligned with the 33-year Jalali cycle.';

-- 0-based day of the Jalali year.
CREATE OR REPLACE FUNCTION jalali.doy0(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$
  SELECT CASE WHEN sub > 365 THEN (sub - 1) % 365 ELSE sub END
  FROM (SELECT jalali._x(d) % 12053 % 1461 AS sub) s
$$;

-- ARRAY[year, month, day] of the Jalali date.
CREATE OR REPLACE FUNCTION jalali.parts(d date) RETURNS int[]
  LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS
$$
DECLARE
  -- absolute day count of the algorithm; 1086152 is its value for 2000-01-01
  days int := (d - DATE '2000-01-01') + 1086152;
  jy int; doy int;
BEGIN
  jy := -1595 + 33 * (days / 12053);
  days := days % 12053;
  jy := jy + 4 * (days / 1461);
  days := days % 1461;
  IF days > 365 THEN
    jy := jy + (days - 1) / 365;
    days := (days - 1) % 365;
  END IF;
  doy := days;
  IF doy < 186 THEN
    RETURN ARRAY[jy, 1 + doy / 31, 1 + doy % 31];
  END IF;
  RETURN ARRAY[jy, 7 + (doy - 186) / 30, 1 + (doy - 186) % 30];
END
$$;

CREATE OR REPLACE FUNCTION jalali.year(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (jalali.parts(d))[1] $$;

CREATE OR REPLACE FUNCTION jalali.month(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (jalali.parts(d))[2] $$;

CREATE OR REPLACE FUNCTION jalali.day(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (jalali.parts(d))[3] $$;

-- Does Esfand of this Jalali year have 30 days? Inside the 1210..1629 window
-- the official leap years are exactly those where (jy - 1209) mod 33 is one of
-- 1, 5, 9, 13, 17, 21, 25, 29.
CREATE OR REPLACE FUNCTION jalali.is_leap(jy int) RETURNS boolean
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT ((jy - 1209) % 33) IN (1, 5, 9, 13, 17, 21, 25, 29) $$;

CREATE OR REPLACE FUNCTION jalali.days_in_month(jy int, jm int) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT CASE WHEN jm <= 6 THEN 31
               WHEN jm <= 11 THEN 30
               WHEN jalali.is_leap(jy) THEN 30
               ELSE 29 END $$;

CREATE OR REPLACE FUNCTION jalali.days_in_year(jy int) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT CASE WHEN jalali.is_leap(jy) THEN 366 ELSE 365 END $$;

-- Gregorian date of 1 Farvardin of a Jalali year. Lands near the year with the
-- mean year length, then steps whole Jalali years until it is exact (at most a
-- couple of steps), so there is only one conversion algorithm in this file.
CREATE OR REPLACE FUNCTION jalali.year_start_of(jy int) RETURNS date
  LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS
$$
DECLARE
  probe date := DATE '2024-03-20' + round(365.2422 * (jy - 1403))::int;
  start date := probe - jalali.doy0(probe);
BEGIN
  WHILE jalali.year(start) < jy LOOP
    start := start + jalali.days_in_year(jalali.year(start));
  END LOOP;
  WHILE jalali.year(start) > jy LOOP
    start := (start - 1) - jalali.doy0(start - 1);
  END LOOP;
  RETURN start;
END
$$;

-- Jalali date -> Gregorian date. NULL when the day does not exist.
CREATE OR REPLACE FUNCTION jalali.to_gregorian(jy int, jm int, jd int) RETURNS date
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$
  SELECT CASE
    WHEN jm BETWEEN 1 AND 12 AND jd BETWEEN 1 AND jalali.days_in_month(jy, jm)
    THEN jalali.year_start_of(jy) + ((jm - 1) * 31 - (jm / 7) * (jm - 7) + jd - 1)
  END
$$;

-- 0 = Saturday .. 6 = Friday, the Iranian week.
CREATE OR REPLACE FUNCTION jalali.day_of_week(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (extract(dow from d)::int + 1) % 7 $$;

-- 1..4: the four seasons (months 1-3, 4-6, 7-9, 10-12).
CREATE OR REPLACE FUNCTION jalali.quarter(d date) RETURNS int
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (jalali.month(d) - 1) / 3 + 1 $$;

CREATE OR REPLACE FUNCTION jalali.is_weekend(d date, thursday boolean DEFAULT false)
  RETURNS boolean LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT jalali.day_of_week(d) = 6 OR (thursday AND jalali.day_of_week(d) = 5) $$;

-- ------------------------------------------------------------ period starts --
-- The timestamp of the first instant of the period containing the argument -
-- exactly what the "ماه شمسی" time grain groups by.
CREATE OR REPLACE FUNCTION jalali.day_start(ts timestamp) RETURNS timestamp
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT ts::date::timestamp $$;

CREATE OR REPLACE FUNCTION jalali.week_start(ts timestamp) RETURNS timestamp
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (ts::date - jalali.day_of_week(ts::date))::timestamp $$;

CREATE OR REPLACE FUNCTION jalali.month_start(ts timestamp) RETURNS timestamp
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (ts::date - (jalali.day(ts::date) - 1))::timestamp $$;

CREATE OR REPLACE FUNCTION jalali.quarter_start(ts timestamp) RETURNS timestamp
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$
  SELECT (ts::date - (doy - CASE WHEN doy < 186 THEN 93 * (doy / 93)
                                ELSE 186 + 90 * ((doy - 186) / 90) END))::timestamp
  FROM (SELECT jalali.doy0(ts::date) AS doy) s
$$;

CREATE OR REPLACE FUNCTION jalali.half_year_start(ts timestamp) RETURNS timestamp
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$
  SELECT (ts::date - (doy - CASE WHEN doy < 186 THEN 0 ELSE 186 END))::timestamp
  FROM (SELECT jalali.doy0(ts::date) AS doy) s
$$;

CREATE OR REPLACE FUNCTION jalali.year_start(ts timestamp) RETURNS timestamp
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (ts::date - jalali.doy0(ts::date))::timestamp $$;

-- ------------------------------------------------------------------- names ---
CREATE OR REPLACE FUNCTION jalali.month_name(d date) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (ARRAY['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور',
                 'مهر','آبان','آذر','دی','بهمن','اسفند'])[jalali.month(d)] $$;

CREATE OR REPLACE FUNCTION jalali.weekday_name(d date) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (ARRAY['شنبه','یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه'])
          [jalali.day_of_week(d) + 1] $$;

CREATE OR REPLACE FUNCTION jalali.season_name(d date) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT (ARRAY['بهار','تابستان','پاییز','زمستان'])[jalali.quarter(d)] $$;

CREATE OR REPLACE FUNCTION jalali.to_persian_digits(t text) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS
$$ SELECT translate(t, '0123456789', '۰۱۲۳۴۵۶۷۸۹') $$;

-- Format with the same dayjs-style tokens as the Python core and the frontend
-- plugin: YYYY YY MMMM MM M DDDD DD D dddd QQQQ Q HH mm ss. Replacement is
-- ordered longest token first; no substituted value contains a token letter.
CREATE OR REPLACE FUNCTION jalali.format(ts timestamp, pattern text DEFAULT 'YYYY-MM-DD')
  RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS
$$
DECLARE
  d date := ts::date;
  p int[] := jalali.parts(d);
  out text := pattern;
BEGIN
  out := replace(out, 'YYYY', lpad(p[1]::text, 4, '0'));
  out := replace(out, 'YY', lpad((p[1] % 100)::text, 2, '0'));
  out := replace(out, 'MMMM', jalali.month_name(d));
  out := replace(out, 'MM', lpad(p[2]::text, 2, '0'));
  out := replace(out, 'DDDD', lpad((jalali.doy0(d) + 1)::text, 3, '0'));
  out := replace(out, 'DDD', (jalali.doy0(d) + 1)::text);
  out := replace(out, 'DD', lpad(p[3]::text, 2, '0'));
  out := replace(out, 'dddd', jalali.weekday_name(d));
  out := replace(out, 'QQQQ', jalali.season_name(d));
  out := replace(out, 'HH', lpad(extract(hour from ts)::int::text, 2, '0'));
  out := replace(out, 'mm', lpad(extract(minute from ts)::int::text, 2, '0'));
  out := replace(out, 'ss', lpad(floor(extract(second from ts))::int::text, 2, '0'));
  out := replace(out, 'Q', jalali.quarter(d)::text);
  out := replace(out, 'M', p[2]::text);
  out := replace(out, 'D', p[3]::text);
  RETURN out;
END
$$;

COMMENT ON FUNCTION jalali.format(timestamp, text) IS
  'Jalali text, dayjs tokens: jalali.format(occurred_at, ''dddd D MMMM YYYY'').';

-- ----------------------------------------------------------- column types ----
-- Datasets have date, timestamp and timestamptz columns, and PostgreSQL will
-- not implicitly cast a timestamp down to a date when it resolves a function
-- call, so every public function above gets both overloads. The timestamptz
-- ones are STABLE rather than IMMUTABLE because which Jalali day an instant
-- belongs to depends on the session time zone - exactly like PostgreSQL's own
-- date_trunc(text, timestamptz). For UTC-stored data of an Asia/Tehran
-- business, either set the session/database TimeZone to Asia/Tehran or use
-- JALALI_CALENDAR_OPTIONS = {"shift_minutes": 210} with the inline grains.
DO $overloads$
DECLARE
  spec text[];
  named text;
  returns text;
BEGIN
  FOREACH spec SLICE 1 IN ARRAY ARRAY[
    ARRAY['parts', 'int[]'], ARRAY['year', 'int'], ARRAY['month', 'int'],
    ARRAY['day', 'int'], ARRAY['doy0', 'int'], ARRAY['quarter', 'int'],
    ARRAY['day_of_week', 'int'], ARRAY['is_weekend', 'boolean'],
    ARRAY['month_name', 'text'], ARRAY['weekday_name', 'text'],
    ARRAY['season_name', 'text']
  ] LOOP
    named := spec[1];
    returns := spec[2];
    EXECUTE format(
      'CREATE OR REPLACE FUNCTION jalali.%I(ts timestamp) RETURNS %s'
      ' LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $body$'
      ' SELECT jalali.%I(ts::date) $body$', named, returns, named);
    EXECUTE format(
      'CREATE OR REPLACE FUNCTION jalali.%I(ts timestamptz) RETURNS %s'
      ' LANGUAGE sql STABLE STRICT PARALLEL SAFE AS $body$'
      ' SELECT jalali.%I((ts AT TIME ZONE current_setting(''TimeZone''))::date)'
      ' $body$', named, returns, named);
  END LOOP;

  -- the period starts already take a timestamp; they only need the tz variant
  FOREACH named IN ARRAY ARRAY['day_start', 'week_start', 'month_start',
                               'quarter_start', 'half_year_start', 'year_start'] LOOP
    EXECUTE format(
      'CREATE OR REPLACE FUNCTION jalali.%I(ts timestamptz) RETURNS timestamp'
      ' LANGUAGE sql STABLE STRICT PARALLEL SAFE AS $body$'
      ' SELECT jalali.%I(ts AT TIME ZONE current_setting(''TimeZone''))'
      ' $body$', named, named);
  END LOOP;
END
$overloads$;

CREATE OR REPLACE FUNCTION jalali.format(ts timestamptz,
                                         pattern text DEFAULT 'YYYY-MM-DD')
  RETURNS text LANGUAGE sql STABLE STRICT PARALLEL SAFE AS
$$ SELECT jalali.format(ts AT TIME ZONE current_setting('TimeZone'), pattern) $$;

-- --------------------------------------------------------------- holidays ----
-- Holidays that fall on a fixed Jalali date are law and can be computed.
CREATE TABLE IF NOT EXISTS jalali.holiday_rule (
  jmonth smallint NOT NULL CHECK (jmonth BETWEEN 1 AND 12),
  jday smallint NOT NULL CHECK (jday BETWEEN 1 AND 31),
  title text NOT NULL,
  PRIMARY KEY (jmonth, jday)
);
COMMENT ON TABLE jalali.holiday_rule IS
  'Official Iranian holidays on a fixed Jalali date.';

INSERT INTO jalali.holiday_rule (jmonth, jday, title) VALUES
  (1, 1, 'عید نوروز'),
  (1, 2, 'عید نوروز'),
  (1, 3, 'عید نوروز'),
  (1, 4, 'عید نوروز'),
  (1, 12, 'روز جمهوری اسلامی'),
  (1, 13, 'سیزده بدر'),
  (3, 14, 'رحلت امام خمینی'),
  (3, 15, 'قیام ۱۵ خرداد'),
  (11, 22, 'پیروزی انقلاب اسلامی'),
  (12, 29, 'روز ملی شدن صنعت نفت')
ON CONFLICT (jmonth, jday) DO NOTHING;

-- Religious holidays follow the lunar calendar and are announced each year, so
-- no formula gets them right: load them from the official calendar (time.ir and
-- the yearly decree) and they win over the rules above.
--     INSERT INTO jalali.holiday_override VALUES ('2025-01-14', 'شهادت حضرت فاطمه', true);
CREATE TABLE IF NOT EXISTS jalali.holiday_override (
  gregorian_date date PRIMARY KEY,
  title text,
  is_holiday boolean NOT NULL DEFAULT true
);
COMMENT ON TABLE jalali.holiday_override IS
  'Announced (lunar) holidays and corrections; overrides jalali.holiday_rule.';

-- --------------------------------------------------------------- dim_date ----
-- One row per day: everything a dashboard might group, filter or label by,
-- precomputed. A join against this beats calling functions per row on large
-- tables, and it is the only place holidays and working days can live.
CREATE TABLE IF NOT EXISTS jalali.dim_date (
  gregorian_date date PRIMARY KEY,
  jyear smallint NOT NULL,
  jmonth smallint NOT NULL,
  jday smallint NOT NULL,
  jalali_date text NOT NULL,          -- 1403-12-20
  jalali_month text NOT NULL,          -- 1403-12
  jmonth_name text NOT NULL,           -- اسفند
  jmonth_label text NOT NULL,          -- اسفند 1403
  jquarter smallint NOT NULL,
  jquarter_name text NOT NULL,         -- زمستان
  jhalf smallint NOT NULL,
  jweek_of_year smallint NOT NULL,
  jday_of_year smallint NOT NULL,
  jdow smallint NOT NULL,              -- 0 = Saturday
  jdow_name text NOT NULL,             -- شنبه
  is_weekend boolean NOT NULL,
  is_holiday boolean NOT NULL,
  holiday_title text,
  is_working_day boolean NOT NULL,
  week_start date NOT NULL,
  month_start date NOT NULL,
  quarter_start date NOT NULL,
  year_start date NOT NULL
);
COMMENT ON TABLE jalali.dim_date IS
  'Jalali calendar, one row per day. Fill with jalali.build_dim_date(1390, 1420).';

CREATE INDEX IF NOT EXISTS dim_date_jyear_jmonth_idx
  ON jalali.dim_date (jyear, jmonth);
CREATE INDEX IF NOT EXISTS dim_date_jalali_date_idx
  ON jalali.dim_date (jalali_date);

-- Rebuild the calendar for whole Jalali years. Returns the number of days.
CREATE OR REPLACE FUNCTION jalali.build_dim_date(from_jy int DEFAULT 1390,
                                                 to_jy int DEFAULT 1420)
  RETURNS bigint LANGUAGE plpgsql AS
$$
DECLARE
  first_day date := jalali.to_gregorian(from_jy, 1, 1);
  last_day date := jalali.to_gregorian(to_jy, 12, jalali.days_in_month(to_jy, 12));
  inserted bigint;
BEGIN
  IF first_day IS NULL OR last_day IS NULL THEN
    RAISE EXCEPTION 'Jalali years % .. % are outside the supported window', from_jy, to_jy;
  END IF;
  DELETE FROM jalali.dim_date WHERE gregorian_date BETWEEN first_day AND last_day;
  INSERT INTO jalali.dim_date
  SELECT d,
         p[1], p[2], p[3],
         lpad(p[1]::text, 4, '0') || '-' || lpad(p[2]::text, 2, '0') || '-'
           || lpad(p[3]::text, 2, '0'),
         lpad(p[1]::text, 4, '0') || '-' || lpad(p[2]::text, 2, '0'),
         jalali.month_name(d),
         jalali.month_name(d) || ' ' || p[1],
         jalali.quarter(d),
         jalali.season_name(d),
         CASE WHEN p[2] <= 6 THEN 1 ELSE 2 END,
         (jalali.doy0(d) / 7) + 1,
         jalali.doy0(d) + 1,
         jalali.day_of_week(d),
         jalali.weekday_name(d),
         jalali.is_weekend(d),
         holiday.is_holiday,
         holiday.title,
         NOT (jalali.is_weekend(d) OR holiday.is_holiday),
         jalali.week_start(d)::date,
         jalali.month_start(d)::date,
         jalali.quarter_start(d)::date,
         jalali.year_start(d)::date
  FROM generate_series(first_day, last_day, interval '1 day') AS g(ts)
  CROSS JOIN LATERAL (SELECT g.ts::date AS d) AS day
  CROSS JOIN LATERAL (SELECT jalali.parts(day.d) AS p) AS parts
  CROSS JOIN LATERAL (
    SELECT coalesce(o.is_holiday, r.title IS NOT NULL) AS is_holiday,
           coalesce(o.title, r.title) AS title
    FROM (SELECT 1) one
    LEFT JOIN jalali.holiday_override o ON o.gregorian_date = day.d
    LEFT JOIN jalali.holiday_rule r ON (r.jmonth, r.jday) = (parts.p[2], parts.p[3])
  ) AS holiday;
  SELECT count(*) INTO inserted FROM jalali.dim_date
   WHERE gregorian_date BETWEEN first_day AND last_day;
  RETURN inserted;
END
$$;

COMMENT ON FUNCTION jalali.build_dim_date(int, int) IS
  'Rebuild jalali.dim_date for whole Jalali years: SELECT jalali.build_dim_date(1390, 1420);';

-- Read-only access for the Superset database user of this demo; harmless if the
-- role does not exist in another installation.
DO $$
BEGIN
  EXECUTE 'GRANT USAGE ON SCHEMA jalali TO PUBLIC';
  EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA jalali TO PUBLIC';
  EXECUTE 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA jalali TO PUBLIC';
END $$;

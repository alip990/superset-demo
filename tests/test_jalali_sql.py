"""db/jalali.sql against the Python core: the installed SQL functions, the
"function" time-grain mode and jalali.dim_date must all agree with core.py, or a
dashboard that mixes a time grain with a dim_date join would disagree with
itself.

Needs a Postgres with db/jalali.sql installed:

    docker compose exec -T db psql -U postgres -d demo < db/jalali.sql
    docker compose exec superset bash -lc \
      "JALALI_TEST_PG_DSN=postgresql://postgres:postgres@db:5432/demo \
       /app/.venv/bin/python -m unittest tests.test_jalali_sql -v"
"""

import datetime as dt
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "superset"))

from jalali_calendar import core, grains  # noqa: E402

START, END = dt.date(1960, 1, 1), dt.date(2080, 12, 31)
DIM_DATE_YEARS = (1398, 1410)


@unittest.skipUnless(os.environ.get("JALALI_TEST_PG_DSN"),
                     "set JALALI_TEST_PG_DSN to check db/jalali.sql")
class TestSqlLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import psycopg2  # pylint: disable=import-outside-toplevel
        except ImportError as ex:  # pragma: no cover
            raise unittest.SkipTest(f"psycopg2 not installed: {ex}")
        cls.conn = psycopg2.connect(os.environ["JALALI_TEST_PG_DSN"])
        cls.conn.autocommit = True  # one failing query must not abort the rest
        with cls.conn.cursor() as cursor:
            cursor.execute("SELECT to_regnamespace('jalali') IS NOT NULL")
            if not cursor.fetchone()[0]:
                raise unittest.SkipTest("db/jalali.sql is not installed")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def query(self, sql: str) -> list[tuple]:
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()

    def sweep(self, select: str) -> list[tuple]:
        """``select`` is an expression list over the column ``d``."""
        return self.query(
            f"SELECT d::date::text, {select} FROM generate_series("
            f"DATE '{START.isoformat()}', DATE '{END.isoformat()}',"
            " interval '1 day') AS g(d)"
        )

    def test_conversion_every_day(self):
        rows = self.sweep("jalali.year(d::date), jalali.month(d::date), "
                          "jalali.day(d::date)")
        self.assertGreater(len(rows), 44000)
        for iso, jy, jm, jd in rows:
            self.assertEqual((jy, jm, jd),
                             tuple(core.to_jalali(dt.date.fromisoformat(iso))), iso)

    def test_period_starts_every_day(self):
        rows = self.sweep(
            "jalali.day_start(d)::date::text, jalali.week_start(d)::date::text, "
            "jalali.month_start(d)::date::text, jalali.quarter_start(d)::date::text, "
            "jalali.half_year_start(d)::date::text, jalali.year_start(d)::date::text")
        units = ("day", "week", "month", "quarter", "half", "year")
        for iso, *starts in rows:
            day = dt.date.fromisoformat(iso)
            for unit, actual in zip(units, starts):
                self.assertEqual(actual, core.PERIOD_STARTS[unit](day).isoformat(),
                                 (iso, unit))

    def test_derived_values_every_day(self):
        rows = self.sweep("jalali.day_of_week(d::date), jalali.quarter(d::date), "
                          "jalali.is_weekend(d::date), jalali.doy0(d::date)")
        for iso, dow, quarter, weekend, doy0 in rows:
            day = dt.date.fromisoformat(iso)
            self.assertEqual(dow, core.day_of_week(day), iso)
            self.assertEqual(quarter, core.quarter(day), iso)
            self.assertEqual(weekend, core.is_weekend(day), iso)
            self.assertEqual(doy0, core.day_of_year(day) - 1, iso)

    def test_leap_years_and_month_lengths(self):
        rows = self.query(
            "SELECT jy, jalali.is_leap(jy), jalali.days_in_year(jy),"
            " jalali.days_in_month(jy, 12), jalali.year_start_of(jy)::text"
            " FROM generate_series(1300, 1500) AS g(jy)")
        for jy, leap, year_days, esfand, year_start in rows:
            self.assertEqual(leap, core.is_leap_year(jy), jy)
            self.assertEqual(year_days, core.days_in_year(jy), jy)
            self.assertEqual(esfand, core.days_in_month(jy, 12), jy)
            self.assertEqual(year_start, core.from_jalali(jy, 1, 1).isoformat(), jy)

    def test_to_gregorian_round_trip(self):
        rows = self.query(
            "SELECT jy, jm, jd, jalali.to_gregorian(jy, jm, jd)::text"
            " FROM generate_series(1395, 1410) AS y(jy),"
            " generate_series(1, 12) AS m(jm), generate_series(1, 31) AS d(jd)")
        for jy, jm, jd, gregorian in rows:
            if jd > core.days_in_month(jy, jm):
                self.assertIsNone(gregorian, (jy, jm, jd))
            else:
                self.assertEqual(gregorian, core.from_jalali(jy, jm, jd).isoformat(),
                                 (jy, jm, jd))

    def test_format_matches_the_python_formatter(self):
        patterns = ["YYYY-MM-DD", "dddd D MMMM YYYY", "QQQQ YYYY", "YYYY/M/D",
                    "MMMM", "YYYY-MM-DD HH:mm:ss", "DDD"]
        samples = ["2025-03-10 14:32:05", "2025-03-21 00:00:00",
                   "2024-03-20 09:05:00", "2025-09-22 23:59:59", "1979-02-11 00:00:00"]
        selects = ", ".join(
            f"jalali.format(TIMESTAMP '{sample}', '{pattern}')"
            for sample in samples for pattern in patterns)
        row = self.query(f"SELECT {selects}")[0]
        expected = [core.format_jalali(dt.datetime.fromisoformat(sample), pattern)
                    for sample in samples for pattern in patterns]
        self.assertEqual(list(row), expected)

    def test_persian_digits(self):
        self.assertEqual(
            self.query("SELECT jalali.to_persian_digits("
                       "jalali.format(TIMESTAMP '2025-03-10'))")[0][0],
            core.format_jalali(dt.date(2025, 3, 10), "YYYY-MM-DD", True))

    def test_function_grain_mode_matches_inline(self):
        for grain in grains.GRAIN_LABELS:
            inline = grains.grain_expression("postgresql", grain).format(col="d")
            installed = grains.grain_expression("postgresql", grain,
                                                mode="function").format(col="d")
            rows = self.query(
                f"SELECT count(*) FROM generate_series(DATE '2000-01-01',"
                f" DATE '2050-12-31', interval '1 day') AS g(d)"
                f" WHERE ({inline})::date <> ({installed})::date")
            self.assertEqual(rows[0][0], 0, grain)

    def test_dim_date(self):
        first, last = DIM_DATE_YEARS
        rows = self.query(
            "SELECT gregorian_date::text, jalali_date, jalali_month, jmonth_label,"
            " jquarter, jquarter_name, jhalf, jday_of_year, jdow, jdow_name,"
            " is_weekend, is_holiday, is_working_day, week_start::text,"
            " month_start::text, quarter_start::text, year_start::text"
            " FROM jalali.dim_date ORDER BY gregorian_date")
        if not rows:
            self.skipTest("jalali.dim_date is empty: SELECT jalali.build_dim_date()")
        expected_days = sum(core.days_in_year(jy) for jy in range(first, last + 1))
        self.assertEqual(len(rows), expected_days)
        for (iso, jalali_date, jalali_month, label, quarter, season, half, doy,
             dow, dow_name, weekend, holiday, working, week_start, month_start,
             quarter_start, year_start) in rows:
            day = dt.date.fromisoformat(iso)
            parts = core.to_jalali(day)
            self.assertEqual(jalali_date, str(parts), iso)
            self.assertEqual(jalali_month, f"{parts.year:04d}-{parts.month:02d}", iso)
            self.assertEqual(label, f"{core.MONTH_NAMES[parts.month - 1]} {parts.year}",
                             iso)
            self.assertEqual(quarter, core.quarter(day), iso)
            self.assertEqual(season, core.SEASON_NAMES[core.quarter(day) - 1], iso)
            self.assertEqual(half, 1 if parts.month <= 6 else 2, iso)
            self.assertEqual(doy, core.day_of_year(day), iso)
            self.assertEqual(dow, core.day_of_week(day), iso)
            self.assertEqual(dow_name, core.WEEKDAY_NAMES[dow], iso)
            self.assertEqual(weekend, core.is_weekend(day), iso)
            self.assertEqual(working, not (weekend or holiday), iso)
            self.assertEqual(week_start, core.week_start(day).isoformat(), iso)
            self.assertEqual(month_start, core.month_start(day).isoformat(), iso)
            self.assertEqual(quarter_start, core.quarter_start(day).isoformat(), iso)
            self.assertEqual(year_start, core.year_start(day).isoformat(), iso)

    def test_dim_date_holidays(self):
        rows = dict(self.query(
            "SELECT gregorian_date::text, holiday_title FROM jalali.dim_date"
            " WHERE is_holiday ORDER BY gregorian_date"))
        # fixed-date official holidays of 1404
        self.assertEqual(rows.get("2025-03-21"), "عید نوروز")
        self.assertEqual(rows.get("2025-04-01"), "روز جمهوری اسلامی")
        self.assertEqual(rows.get("2025-04-02"), "سیزده بدر")
        self.assertEqual(rows.get("2026-02-11"), "پیروزی انقلاب اسلامی")
        # ... and 10 of them every year, before any announced lunar holiday
        per_year = {}
        for iso in rows:
            per_year.setdefault(core.to_jalali(dt.date.fromisoformat(iso)).year, 0)
            per_year[core.to_jalali(dt.date.fromisoformat(iso)).year] += 1
        for jy, count in per_year.items():
            if DIM_DATE_YEARS[0] < jy < DIM_DATE_YEARS[1]:
                self.assertGreaterEqual(count, 10, jy)

"""The time-grain SQL: the generated expressions must bucket exactly like the
Python core, in a real SQL engine.

SQLite runs in-process (no setup, always exercised). Postgres is exercised too
when a DSN is given, which is how the demo stack is checked:

    docker compose exec superset bash -lc \
      "JALALI_TEST_PG_DSN=postgresql://postgres:postgres@db:5432/demo \
       /app/.venv/bin/python -m unittest tests.test_jalali_grains -v"
"""

import datetime as dt
import os
import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "superset"))

from jalali_calendar import core, grains  # noqa: E402

# A long sweep for the in-process engine, a shorter one for a remote database.
SWEEP_START, SWEEP_END = dt.date(1900, 1, 1), dt.date(2200, 12, 31)
PG_SWEEP_START, PG_SWEEP_END = dt.date(1990, 1, 1), dt.date(2060, 12, 31)

GRAIN_TO_UNIT = {
    "JALALI_WEEK": "week",
    "JALALI_MONTH": "month",
    "JALALI_QUARTER": "quarter",
    "JALALI_HALF_YEAR": "half",
    "JALALI_YEAR": "year",
}


def expected_buckets(start: dt.date, end: dt.date) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {grain: {} for grain in GRAIN_TO_UNIT}
    for day in core.iter_dates(start, end):
        iso = day.isoformat()
        for grain, unit in GRAIN_TO_UNIT.items():
            out[grain][iso] = core.PERIOD_STARTS[unit](day).isoformat()
    return out


class TestConstants(unittest.TestCase):
    """The magic numbers in grains.py are derived, not guessed - recompute them."""

    def test_anchor_matches_the_cycle_arithmetic(self):
        anchor = dt.date.fromisoformat(grains.ANCHOR_DATE)
        # the anchor constant must put the 33-year cycle in the right phase for
        # every day of the sweep, which is what day_of_year proves
        for day in (anchor, dt.date(2025, 3, 20), dt.date(2025, 3, 21),
                    dt.date(1900, 1, 1), dt.date(2200, 12, 31)):
            x = (day - anchor).days + grains.ANCHOR
            doy0 = x % grains.CYCLE % grains.SUBCYCLE
            if doy0 > 365:
                doy0 = (doy0 - 1) % 365
            self.assertEqual(doy0, core.day_of_year(day) - 1, day.isoformat())

    def test_anchor_stays_positive_over_the_sweep(self):
        anchor = dt.date.fromisoformat(grains.ANCHOR_DATE)
        self.assertGreater((SWEEP_START - anchor).days + grains.ANCHOR, 0)

    def test_week_phase_lands_on_saturday(self):
        anchor = dt.date.fromisoformat(grains.ANCHOR_DATE)
        for day in core.iter_dates(dt.date(2025, 1, 1), dt.date(2025, 2, 28)):
            x = (day - anchor).days + grains.ANCHOR + grains.WEEK_PHASE
            self.assertEqual(x % 7 == 0, core.day_of_week(day) == 0,
                             day.isoformat())

    def test_quarter_and_half_starts(self):
        self.assertEqual(grains.QUARTER_STARTS,
                         tuple(core.day_of_year(core.from_jalali(1403, m, 1)) - 1
                               for m in (1, 4, 7, 10)))
        self.assertEqual(grains.HALF_STARTS,
                         tuple(core.day_of_year(core.from_jalali(1403, m, 1)) - 1
                               for m in (1, 7)))


class TestGeneratedSql(unittest.TestCase):
    def test_every_engine_gets_every_grain(self):
        expressions = grains.time_grain_addon_expressions()
        self.assertEqual(set(expressions), set(grains.DIALECTS_BY_ENGINE))
        self.assertGreaterEqual(len(expressions), 20)
        for engine, by_grain in expressions.items():
            self.assertEqual(set(by_grain), set(grains.GRAIN_LABELS), engine)
            for grain, sql in by_grain.items():
                self.assertIn("{col}", sql, (engine, grain))
                self.assertEqual(sql.count("{"), sql.count("}"), (engine, grain))
                self.assertEqual(sql.count("("), sql.count(")"), (engine, grain))

    def test_labels_cover_the_grains(self):
        self.assertEqual(set(grains.time_grain_addons()), set(grains.GRAIN_LABELS))

    def test_function_mode_is_short_and_postgres_only(self):
        pg = grains.grain_expression("postgresql", "JALALI_MONTH", mode="function")
        self.assertEqual(pg, "jalali.month_start({col})")
        inline = grains.grain_expression("trino", "JALALI_MONTH", mode="function")
        self.assertNotIn("jalali.", inline)  # no functions off Postgres

    def test_shift_minutes_moves_the_boundary(self):
        plain = grains.grain_expression("sqlite", "JALALI_MONTH")
        shifted = grains.grain_expression("sqlite", "JALALI_MONTH", shift_minutes=210)
        self.assertNotEqual(plain, shifted)
        self.assertIn("210 minutes", shifted)


class SqlEngineChecks:
    """Shared body: run every grain over a sweep of dates and compare."""

    engine_name = ""
    start = SWEEP_START
    end = SWEEP_END

    def run_grain(self, grain: str) -> dict[str, str]:
        raise NotImplementedError

    def test_grains_match_the_python_core(self):
        expected = expected_buckets(self.start, self.end)
        for grain in GRAIN_TO_UNIT:
            with self.subTest(grain=grain):  # type: ignore[attr-defined]
                actual = self.run_grain(grain)
                self.assertEqual(len(actual), len(expected[grain]))  # type: ignore[attr-defined]
                mismatches = [(iso, actual[iso], expected[grain][iso])
                              for iso in expected[grain]
                              if actual[iso] != expected[grain][iso]]
                self.assertEqual(mismatches[:5], [],  # type: ignore[attr-defined]
                                 f"{len(mismatches)} mismatching buckets in "
                                 f"{self.engine_name} {grain}")


class TestSqlite(SqlEngineChecks, unittest.TestCase):
    engine_name = "sqlite"

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.execute("CREATE TABLE t (d TEXT)")
        cls.conn.executemany("INSERT INTO t VALUES (?)",
                             [(day.isoformat(),) for day in
                              core.iter_dates(cls.start, cls.end)])

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def run_grain(self, grain: str) -> dict[str, str]:
        expr = grains.grain_expression("sqlite", grain).format(col="d")
        rows = self.conn.execute(f"SELECT d, date({expr}) FROM t")
        return dict(rows)


@unittest.skipUnless(os.environ.get("JALALI_TEST_PG_DSN"),
                     "set JALALI_TEST_PG_DSN to check the Postgres expressions")
class TestPostgres(SqlEngineChecks, unittest.TestCase):
    engine_name = "postgresql"
    start, end = PG_SWEEP_START, PG_SWEEP_END

    @classmethod
    def setUpClass(cls):
        try:
            import psycopg2  # pylint: disable=import-outside-toplevel
        except ImportError as ex:  # pragma: no cover
            raise unittest.SkipTest(f"psycopg2 not installed: {ex}")
        cls.conn = psycopg2.connect(os.environ["JALALI_TEST_PG_DSN"])

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def run_grain(self, grain: str) -> dict[str, str]:
        expr = grains.grain_expression("postgresql", grain).format(col="d")
        with self.conn.cursor() as cursor:
            # no bound parameters: psycopg2 would read a % in the expression as
            # a parameter marker, and the sweep bounds are generated here
            cursor.execute(
                # generate_series with an interval yields timestamps, which is
                # also the realistic column type for a grain
                f"SELECT d::date::text, ({expr})::date::text FROM generate_series("
                f"DATE '{self.start.isoformat()}', DATE '{self.end.isoformat()}',"
                " interval '1 day') AS g(d)"
            )
            return dict(cursor.fetchall())

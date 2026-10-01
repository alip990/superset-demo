"""Jalali time grains for Superset's "Time grain" menu, as inline SQL.

Grouping by a Jalali period has to happen in the database - a frontend date
formatter can only relabel buckets the database already produced, so "one bar
per Jalali month" is impossible without this. Superset asks the engine spec for
``TIME_GRAIN_ADDON_EXPRESSIONS[engine][grain]`` and substitutes ``{col}``
(superset/db_engine_specs/base.py: get_time_grain_expressions).

The expressions are **pure integer arithmetic**, so they need nothing installed
in the database - no PL/pgSQL function, no extension, no calendar table - and
the same generator emits them for every supported engine. The predecessor of
this module called ``bi.to_jalali()``, which only existed in one database and
ran a PL/pgSQL function per row.

How the arithmetic works (verified day by day against core.py for 1900..2200 in
tests/test_jalali_grains.py):

    X     = days since 2000-01-01 + ANCHOR  (ANCHOR aligns X with the 33-year
            Jalali cycle and keeps X positive for any realistic date)
    X % 12053            position inside the 33-year cycle (12053 days)
    ... % 1461           position inside the 4-year sub-cycle (1461 days)
    DOY0                 0-based day of the Jalali year, after the one-day
                         correction for the leap year that opens each sub-cycle

Every grain is then "the date minus the number of days since the start of the
period", which only needs DOY0 - and for weeks not even that, because the
Iranian week starts on Saturday and 2000-01-01 was a Saturday, so X % 7 is the
offset back to Saturday.

Cost: a handful of integer operations per row, no function call. For very large
tables prefer joining the calendar table (db/02-jalali.sql, jalali.dim_date) or
index the expression:

    CREATE INDEX ON bi.violation (((occurred_at::date - DATE '2000-01-01' + 965622) % 12053));
"""

from __future__ import annotations

# Day count of 2000-01-01 in the 33-year-cycle numbering, plus 80 whole cycles
# so X stays positive back to ~360 CE. tests/test_jalali_grains.py recomputes
# both constants from core.py, so they cannot silently drift.
ANCHOR_DATE = "2000-01-01"
ANCHOR = 965622
CYCLE = 12053  # days in 33 Jalali years
SUBCYCLE = 1461  # days in 4 Jalali years
WEEK_PHASE = 0  # (X + WEEK_PHASE) % 7 == 0 on Saturdays

# 0-based day of the Jalali year each season / half starts on. Months 1-6 have
# 31 days, 7-11 have 30: spring 0, summer 93, autumn 186, winter 276.
QUARTER_STARTS = (0, 93, 186, 276)
HALF_STARTS = (0, 186)

GRAIN_LABELS = {
    "JALALI_WEEK": "هفته شمسی (شنبه)",
    "JALALI_MONTH": "ماه شمسی",
    "JALALI_QUARTER": "فصل شمسی",
    "JALALI_HALF_YEAR": "نیم‌سال شمسی",
    "JALALI_YEAR": "سال شمسی",
}


class Dialect:
    """SQL primitives of one engine family, used to build the grain expressions.

    Every template takes already-parenthesised fragments, so the generated SQL
    needs no precedence rules of its own.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        engines: tuple[str, ...],
        to_date: str,
        days_between: str,
        int_div: str,
        modulo: str,
        minus_days: str,
        to_timestamp: str,
        shift_minutes: str | None = None,
    ) -> None:
        self.engines = engines
        self._to_date = to_date
        self._days_between = days_between
        self._int_div = int_div
        self._modulo = modulo
        self._minus_days = minus_days
        self._to_timestamp = to_timestamp
        self._shift_minutes = shift_minutes

    def to_date(self, col: str) -> str:
        return self._to_date.format(col=col)

    def days_between(self, date_expr: str) -> str:
        return self._days_between.format(anchor=ANCHOR_DATE, date=date_expr)

    def int_div(self, a: str, b: int) -> str:
        return self._int_div.format(a=a, b=b)

    def modulo(self, a: str, b: int) -> str:
        return self._modulo.format(a=a, b=b)

    def minus_days(self, date_expr: str, days: str) -> str:
        return self._minus_days.format(date=date_expr, days=days)

    def to_timestamp(self, date_expr: str) -> str:
        return self._to_timestamp.format(date=date_expr)

    def shift(self, col: str, minutes: int) -> str:
        if not minutes:
            return col
        if self._shift_minutes is None:
            raise NotImplementedError(
                f"shift_minutes is not implemented for {self.engines[0]}"
            )
        return self._shift_minutes.format(col=col, minutes=minutes)

    # ---------------------------------------------------------- expressions ---
    def case(self, branches: list[tuple[str, str]], default: str) -> str:
        when = " ".join(f"WHEN {cond} THEN {then}" for cond, then in branches)
        return f"CASE {when} ELSE {default} END"

    def day_offsets(self, col: str, shift_minutes: int = 0) -> tuple[str, str]:
        """(date expression, DOY0 expression) for the column."""
        date_expr = self.to_date(self.shift(col, shift_minutes))
        x = f"({self.days_between(date_expr)} + {ANCHOR})"
        sub = self.modulo(self.modulo(x, CYCLE), SUBCYCLE)
        doy0 = self.case(
            [(f"{sub} > 365", self.modulo(f"({sub} - 1)", 365))], sub
        )
        return date_expr, doy0

    def grain(self, grain: str, col: str, shift_minutes: int = 0) -> str:
        date_expr, doy0 = self.day_offsets(col, shift_minutes)
        if grain == "JALALI_WEEK":
            x = f"({self.days_between(date_expr)} + {ANCHOR + WEEK_PHASE})"
            back = self.modulo(x, 7)
        elif grain == "JALALI_MONTH":
            # day-of-month - 1: months 1-6 are 31 days long, 7-12 are 30
            back = self.case(
                [(f"{doy0} < 186", self.modulo(doy0, 31))],
                self.modulo(f"({doy0} - 186)", 30),
            )
        elif grain == "JALALI_QUARTER":
            # Seasons start on days 0, 93, 186 and 276 of the Jalali year: the
            # first three are 93 days (3 x 31), winter 90 (3 x 30). Written as
            # two divisions instead of four CASE branches to keep the SQL short.
            spring_summer = self.int_div(doy0, 93)
            autumn_winter = self.int_div(f"({doy0} - 186)", 90)
            back = self.case(
                [(f"{doy0} < 186", f"({doy0} - 93 * {spring_summer})")],
                f"({doy0} - 186 - 90 * {autumn_winter})",
            )
        elif grain == "JALALI_HALF_YEAR":
            back = self.case(
                [(f"{doy0} < 186", doy0)], f"({doy0} - 186)"
            )
        elif grain == "JALALI_YEAR":
            back = doy0
        else:
            raise KeyError(grain)
        return self.to_timestamp(self.minus_days(date_expr, back))


DIALECTS = (
    Dialect(
        engines=("postgresql", "redshift", "cockroachdb", "crate"),
        to_date="({col})::date",
        days_between="({date} - DATE '{anchor}')",
        int_div="(({a}) / {b})",
        # mod(), not %: psycopg2 reads a % as a parameter marker when the
        # statement is executed with bound parameters
        modulo="mod({a}, {b})",
        minus_days="({date} - ({days}))",
        to_timestamp="({date})::timestamp",
        shift_minutes="(({col}) + INTERVAL '{minutes} minutes')",
    ),
    Dialect(
        engines=("duckdb",),
        to_date="({col})::date",
        days_between="date_diff('day', DATE '{anchor}', {date})",
        int_div="(({a}) // {b})",
        modulo="mod({a}, {b})",
        minus_days="({date} - ({days}))",
        to_timestamp="({date})::timestamp",
        shift_minutes="(({col}) + INTERVAL '{minutes} minutes')",
    ),
    Dialect(
        engines=("trino", "presto", "athena"),
        to_date="CAST(({col}) AS DATE)",
        days_between="date_diff('day', DATE '{anchor}', {date})",
        int_div="(({a}) / {b})",
        modulo="mod({a}, {b})",
        minus_days="date_add('day', -({days}), {date})",
        to_timestamp="CAST({date} AS TIMESTAMP)",
        shift_minutes="date_add('minute', {minutes}, {col})",
    ),
    Dialect(
        engines=("mysql", "mariadb"),
        to_date="DATE({col})",
        days_between="DATEDIFF({date}, '{anchor}')",
        int_div="(({a}) DIV {b})",
        modulo="MOD({a}, {b})",
        minus_days="DATE_SUB({date}, INTERVAL ({days}) DAY)",
        to_timestamp="CAST({date} AS DATETIME)",
        shift_minutes="DATE_ADD({col}, INTERVAL {minutes} MINUTE)",
    ),
    Dialect(
        engines=("clickhouse", "clickhousedb", "clickhouseconnect"),
        to_date="toDate({col})",
        days_between="dateDiff('day', toDate('{anchor}'), {date})",
        int_div="intDiv({a}, {b})",
        modulo="modulo({a}, {b})",
        minus_days="subtractDays({date}, {days})",
        to_timestamp="toDateTime({date})",
        shift_minutes="addMinutes({col}, {minutes})",
    ),
    Dialect(
        engines=("bigquery",),
        to_date="DATE({col})",
        days_between="DATE_DIFF({date}, DATE '{anchor}', DAY)",
        int_div="DIV({a}, {b})",
        modulo="MOD({a}, {b})",
        minus_days="DATE_SUB({date}, INTERVAL ({days}) DAY)",
        to_timestamp="DATETIME({date})",
        shift_minutes="DATETIME_ADD({col}, INTERVAL {minutes} MINUTE)",
    ),
    Dialect(
        engines=("sqlite",),
        to_date="date({col})",
        days_between="CAST(julianday({date}) - julianday('{anchor}') AS INTEGER)",
        int_div="CAST(({a}) / {b} AS INTEGER)",
        modulo="(({a}) % {b})",
        minus_days="date({date}, '-' || CAST(({days}) AS TEXT) || ' days')",
        to_timestamp="datetime({date})",
        shift_minutes="datetime({col}, '{minutes} minutes')",
    ),
    Dialect(
        engines=("databricks", "hive", "spark", "sparksql"),
        to_date="to_date({col})",
        days_between="datediff({date}, DATE '{anchor}')",
        int_div="(({a}) div {b})",
        modulo="mod({a}, {b})",
        minus_days="date_sub({date}, CAST(({days}) AS INT))",
        to_timestamp="CAST({date} AS TIMESTAMP)",
        shift_minutes="({col} + INTERVAL '{minutes}' MINUTE)",
    ),
    Dialect(
        engines=("snowflake",),
        to_date="CAST({col} AS DATE)",
        days_between="DATEDIFF('day', DATE '{anchor}', {date})",
        int_div="FLOOR(({a}) / {b})",
        modulo="MOD({a}, {b})",
        minus_days="DATEADD('day', -({days}), {date})",
        to_timestamp="CAST({date} AS TIMESTAMP)",
        shift_minutes="DATEADD('minute', {minutes}, {col})",
    ),
    Dialect(
        engines=("mssql",),
        to_date="CAST({col} AS DATE)",
        days_between="DATEDIFF(day, CAST('{anchor}' AS DATE), {date})",
        int_div="(({a}) / {b})",
        modulo="(({a}) % {b})",
        minus_days="DATEADD(day, -({days}), {date})",
        to_timestamp="CAST({date} AS DATETIME)",
        shift_minutes="DATEADD(minute, {minutes}, {col})",
    ),
)

DIALECTS_BY_ENGINE = {
    engine: dialect for dialect in DIALECTS for engine in dialect.engines
}


# Grain expressions for installations that applied db/02-jalali.sql: short,
# readable SQL, and because the functions are IMMUTABLE they can back an index
# (CREATE INDEX ON t (jalali.month_start(occurred_at))). Only Postgres-family
# engines can host the functions; every other engine keeps the inline math.
FUNCTION_SCHEMA = "jalali"
FUNCTION_NAMES = {
    "JALALI_WEEK": "week_start",
    "JALALI_MONTH": "month_start",
    "JALALI_QUARTER": "quarter_start",
    "JALALI_HALF_YEAR": "half_year_start",
    "JALALI_YEAR": "year_start",
}
FUNCTION_ENGINES = ("postgresql", "redshift", "cockroachdb")


def function_grain_expression(grain: str, col: str = "{col}",
                              shift_minutes: int = 0,
                              schema: str = FUNCTION_SCHEMA) -> str:
    shifted = (
        col if not shift_minutes
        else f"(({col}) + INTERVAL '{shift_minutes} minutes')"
    )
    return f"{schema}.{FUNCTION_NAMES[grain]}({shifted})"


def grain_expression(engine: str, grain: str, col: str = "{col}",
                     shift_minutes: int = 0, mode: str = "inline") -> str:
    """One grain expression for one engine, with ``{col}`` left in place for
    Superset to substitute. ``mode`` is "inline" (self-contained arithmetic) or
    "function" (needs db/02-jalali.sql; falls back to inline off Postgres)."""
    if mode == "function" and engine in FUNCTION_ENGINES:
        return function_grain_expression(grain, col, shift_minutes)
    return DIALECTS_BY_ENGINE[engine].grain(grain, col, shift_minutes)


def time_grain_addons(labels: dict[str, str] | None = None) -> dict[str, str]:
    """Value for the TIME_GRAIN_ADDONS config key."""
    return dict(labels or GRAIN_LABELS)


def time_grain_addon_expressions(
    grains: tuple[str, ...] | None = None, shift_minutes: int = 0,
    mode: str = "inline",
) -> dict[str, dict[str, str]]:
    """Value for the TIME_GRAIN_ADDON_EXPRESSIONS config key: every grain for
    every supported engine."""
    wanted = grains or tuple(GRAIN_LABELS)
    return {
        engine: {
            grain: grain_expression(engine, grain, "{col}", shift_minutes, mode)
            for grain in wanted
        }
        for dialect in DIALECTS
        for engine in dialect.engines
    }

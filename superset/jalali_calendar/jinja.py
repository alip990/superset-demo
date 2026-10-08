"""Jinja macros for dataset and SQL Lab queries: ``{{ jalali_today() }}``,
``{{ jalali_filter('occurred_at', 'Current jalali month') }}`` and friends.

They are installed as :class:`superset.jinja_context.ExtraCache` methods rather
than through ``JINJA_CONTEXT_ADDONS``, for the same reason the guest-token
attribute macro is (see superset/guest_user_attributes.py): a macro whose value
changes over time has to reach the **query cache key**. Superset decides whether
to re-render a dataset's SQL for cache-key collection with
``ExtraCache.regex``; a macro the regex does not mention is invisible to the
cache, so a chart filtered on "this Jalali month" would keep serving last
month's rows from Redis. ``install.py`` extends that regex and these methods
call ``cache_key_wrapper()`` with the value they resolved to.

Macros that depend only on their arguments (``to_jalali``, ``from_jalali``,
``jalali_grain``) are pure and deliberately add nothing to the cache key.
"""

from __future__ import annotations

import datetime as dt
import re

from . import core, grains, ranges, timezone

ISO_DATE = "%Y-%m-%d"
ISO_DATETIME = "%Y-%m-%d %H:%M:%S"
# Dataset SQL is written by trusted authors, but a macro argument can come from a
# URL parameter, so anything that lands in SQL unquoted is checked first.
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)*$")


def _identifier(name: str) -> str:
    if not IDENTIFIER_RE.match(str(name)):
        raise ValueError(f"not a column name: {name!r}")
    return str(name)


def _parse_value(value: object) -> dt.date | dt.datetime:
    """Accept what a dataset can hand a macro: a date, a datetime, an ISO string
    or a Jalali literal."""
    if isinstance(value, (dt.datetime, dt.date)):
        return value
    text = str(value).strip()
    literal = core.parse_literal(text)
    if literal is not None:
        return literal.datetime
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError as ex:
        raise ValueError(f"not a date: {value!r}") from ex


# ------------------------------------------------- time-dependent macros -----
def jalali_today(self, fmt: str = "YYYY-MM-DD", persian_digits: bool = False) -> str:
    """Today's Jalali date as text, e.g. ``1404-07-09``."""
    out = core.format_jalali(timezone.current().now().date(), fmt, persian_digits)
    self.cache_key_wrapper(f"jalali_today:{out}")
    return out


def jalali_now(self, fmt: str = "YYYY-MM-DD HH:mm:ss",
               persian_digits: bool = False) -> str:
    """Current Jalali date and time as text. Changes every second, so a query
    using it is effectively uncacheable - that is intentional."""
    out = core.format_jalali(timezone.current().now(), fmt, persian_digits)
    self.cache_key_wrapper(f"jalali_now:{out}")
    return out


def jalali_start(self, unit: str = "month", offset: int = 0,
                 fmt: str = ISO_DATETIME) -> str:
    """Start of the current Jalali period, shifted by ``offset`` periods:
    ``{{ jalali_start('month', -1) }}`` is the 1st of last Jalali month."""
    clock = timezone.current()
    start = core.PERIOD_STARTS[unit](clock.now().date())
    if offset:
        start = core.add_period(start, offset, unit)
    out = clock.to_storage(dt.datetime.combine(start, dt.time()), boundary=True).strftime(fmt)
    self.cache_key_wrapper(f"jalali_start:{unit}:{offset}:{out}")
    return out


def jalali_end(self, unit: str = "month", offset: int = 0,
               fmt: str = ISO_DATETIME) -> str:
    """Exclusive end of the current Jalali period, shifted by ``offset``."""
    clock = timezone.current()
    start = core.PERIOD_STARTS[unit](clock.now().date())
    end = core.add_period(start, offset + 1, unit)
    out = clock.to_storage(dt.datetime.combine(end, dt.time()), boundary=True).strftime(fmt)
    self.cache_key_wrapper(f"jalali_end:{unit}:{offset}:{out}")
    return out


def jalali_filter(self, column: str, expression: str = "Current jalali month") -> str:
    """A half-open range predicate for any expression of the Jalali range
    vocabulary (ranges.py), ready to drop into a WHERE clause::

        WHERE {{ jalali_filter('occurred_at', 'jalali year to date') }}
    """
    col = _identifier(column)
    clock = timezone.current()
    resolved = ranges.resolve(expression, clock.now())
    if resolved is None:
        raise ValueError(f"not a Jalali time range: {expression!r}")
    since, until = (clock.to_storage(part, boundary=True) for part in resolved)
    out = (f"{col} >= '{since.strftime(ISO_DATETIME)}'"
           f" AND {col} < '{until.strftime(ISO_DATETIME)}'")
    self.cache_key_wrapper(f"jalali_filter:{col}:{expression}:{out}")
    return out


# ------------------------------------------------------------ pure macros ----
def to_jalali(self, value: object, fmt: str = "YYYY-MM-DD",  # noqa: ARG001
              persian_digits: bool = False) -> str:
    """Format a Gregorian date/datetime (or an ISO string) in Jalali."""
    parsed = _parse_value(value)
    if isinstance(parsed, dt.datetime):
        parsed = timezone.current().from_storage(parsed)
    return core.format_jalali(parsed, fmt, persian_digits)


def from_jalali(self, literal: str) -> str:  # noqa: ARG001
    """Gregorian ISO date of a Jalali literal: ``{{ from_jalali('1403-12-20') }}``
    renders ``2025-03-10``, so dataset SQL can hard-code Jalali dates."""
    parsed = core.parse_literal(str(literal))
    if parsed is None:
        raise ValueError(f"not a Jalali literal: {literal!r}")
    return parsed.date.strftime(ISO_DATE)


def jalali_grain(self, column: str, unit: str = "month",  # noqa: ARG001
                 engine: str | None = None) -> str:
    """The SQL that buckets ``column`` to the start of its Jalali period - the
    same expression the "ماه شمسی" time grain uses, for datasets that want it as
    a column. ``engine`` defaults to the database of the query when it can be
    determined, else to Postgres."""
    col = _identifier(column)
    grain = f"JALALI_{unit.upper().replace('-', '_')}"
    if grain == "JALALI_HALF":
        grain = "JALALI_HALF_YEAR"
    engine_name = engine or _engine_of(self) or "postgresql"
    if engine_name not in grains.DIALECTS_BY_ENGINE:
        raise ValueError(f"no Jalali grain SQL for engine {engine_name!r}")
    clock = timezone.current()
    return grains.grain_expression(engine_name, grain, col, clock.shift_minutes,
        business_timezone=(clock.business_timezone if clock.storage_timezone == 'UTC' else None))


def _engine_of(extra_cache: object) -> str | None:
    """Backend name of the database the query runs against, if the ExtraCache
    instance Superset built for this request knows it."""
    database = getattr(extra_cache, "database", None)
    try:
        return database.db_engine_spec.engine if database is not None else None
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001
        return None


# The macros, in the order the docs list them. ``install.py`` binds every entry
# to ExtraCache and publishes it in the Jinja context.
MACROS = {
    "jalali_today": jalali_today,
    "jalali_now": jalali_now,
    "jalali_start": jalali_start,
    "jalali_end": jalali_end,
    "jalali_filter": jalali_filter,
    "to_jalali": to_jalali,
    "from_jalali": from_jalali,
    "jalali_grain": jalali_grain,
}
# Only these change over time, so only these have to be in ExtraCache.regex.
CACHE_KEY_MACROS = ("jalali_today", "jalali_now", "jalali_start", "jalali_end",
                    "jalali_filter")

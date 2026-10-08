"""The Jalali time-range vocabulary: the strings a chart can store as its
``time_range``, and how they resolve to a Gregorian half-open interval.

Superset resolves time ranges **on the server** (superset/utils/date_parser.py,
``get_since_until``) - the explore UI only shows what the API returned, and
alerts, reports, CSV exports and embedded dashboards never run the UI at all.
So a Jalali range has to be understood here, not in the browser, or a saved
chart would break the moment nobody is looking at it.

``install.py`` wraps ``get_since_until`` with :func:`rewrite`, which turns a
Jalali expression into the plain ISO ``since : until`` string Superset already
knows, and leaves everything else untouched. That keeps time shifts, time
comparison and validation exactly as upstream wrote them.

Grammar (case-insensitive; "jalali" may also be spelled "shamsi"):

    whole string, no " : " separator
        Current jalali day|week|month|quarter|half|year
        previous jalali day|week|month|quarter|half|year
        Last jalali day|week|month|quarter|half|year
        Last <n> jalali days|weeks|months|quarters|halves|years
        Next <n> jalali days|weeks|months|quarters|halves|years
        jalali day|week|month|quarter|half|year to date
        jalali:<literal>            the whole period the literal names
        <literal>                   same, when bare literals are allowed

    one side of "<since> : <until>"
        jalali:<literal> | <literal>      -> that instant (midnight by default)
        anything else                     -> left to Superset

    <literal> is 1403, 1403-12, 1403-q4, 1403-12-20, 1403/12/20 14:30[:00],
    with Persian or Arabic-Indic digits allowed everywhere.

All boundaries are midnight-aligned, ``since`` inclusive and ``until``
exclusive, like Superset's own calendar ranges. "to date" ends at midnight
*tomorrow*, so today's rows are included.
"""

from __future__ import annotations

import datetime as dt
import re

from . import core
from .timezone import CalendarClock
from zoneinfo import ZoneInfo

SEPARATOR = " : "
ISO = "%Y-%m-%dT%H:%M:%S"
PREFIX_RE = re.compile(r"^(?:jalali|shamsi|jalaali|j)\s*[:_-]\s*", re.IGNORECASE)
_WORD = r"(?:jalali|shamsi|jalaali)"
_UNITS = {
    "day": "day", "days": "day",
    "week": "week", "weeks": "week",
    "month": "month", "months": "month",
    "quarter": "quarter", "quarters": "quarter", "season": "quarter",
    "seasons": "quarter",
    "half": "half", "halves": "half", "half-year": "half",
    "year": "year", "years": "year",
}
_UNIT_RE = "|".join(sorted(_UNITS, key=len, reverse=True))

CURRENT_RE = re.compile(rf"^current\s+{_WORD}\s+({_UNIT_RE})$", re.IGNORECASE)
PREVIOUS_RE = re.compile(rf"^previous\s+{_WORD}\s+({_UNIT_RE})$", re.IGNORECASE)
LAST_RE = re.compile(rf"^last\s+(?:(\d+)\s+)?{_WORD}\s+({_UNIT_RE})$", re.IGNORECASE)
NEXT_RE = re.compile(rf"^next\s+(?:(\d+)\s+)?{_WORD}\s+({_UNIT_RE})$", re.IGNORECASE)
TO_DATE_RE = re.compile(rf"^{_WORD}\s+({_UNIT_RE})\s+to\s+date$", re.IGNORECASE)

# Persian labels for everything the picker offers, grouped by the frame of
# Superset's date-filter popover that shows them. The frontend builds its radio
# options from this list (it is published in JALALI_CALENDAR_OPTIONS), so the
# two sides cannot drift apart.
COMMON_RANGES = (
    ("Last jalali week", "هفته گذشته (شمسی)"),
    ("Last jalali month", "ماه گذشته (شمسی)"),
    ("Last jalali quarter", "فصل گذشته (شمسی)"),
    ("Last jalali year", "سال گذشته (شمسی)"),
)
CALENDAR_RANGES = (
    ("previous jalali week", "هفته تقویمی قبل (شمسی)"),
    ("previous jalali month", "ماه تقویمی قبل (شمسی)"),
    ("previous jalali quarter", "فصل تقویمی قبل (شمسی)"),
    ("previous jalali year", "سال تقویمی قبل (شمسی)"),
)
CURRENT_RANGES = (
    ("Current jalali day", "امروز"),
    ("Current jalali week", "هفته جاری (شمسی)"),
    ("Current jalali month", "ماه جاری (شمسی)"),
    ("Current jalali quarter", "فصل جاری (شمسی)"),
    ("Current jalali year", "سال جاری (شمسی)"),
    ("jalali month to date", "از ابتدای ماه تا امروز"),
    ("jalali quarter to date", "از ابتدای فصل تا امروز"),
    ("jalali year to date", "از ابتدای سال تا امروز"),
)
ALL_RANGES = COMMON_RANGES + CALENDAR_RANGES + CURRENT_RANGES
LABELS = dict(ALL_RANGES)


def _midnight(value: dt.date | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.datetime(value.year, value.month, value.day)


def _period_start(day: dt.date, unit: str) -> dt.date:
    return core.PERIOD_STARTS[unit](day)


def _anchor(now: dt.datetime | str | None) -> dt.datetime:
    """"today" for relative ranges: a datetime, an ISO string (Superset's
    ``relative_start``) or the server clock."""
    if isinstance(now, str):
        try:
            now = dt.datetime.fromisoformat(now)
        except ValueError:
            now = None
    return _midnight(now if now is not None else
                     dt.datetime.now(ZoneInfo('Asia/Tehran')))


def resolve(time_range: str, now: dt.datetime | str | None = None,
            bare_literals: bool = True
            ) -> tuple[dt.datetime, dt.datetime] | None:
    """Resolve a whole-string Jalali expression, or return None if the string is
    not one."""
    text = core.to_latin_digits(time_range.strip())
    today = _anchor(now)
    day = today.date()

    if match := CURRENT_RE.match(text):
        unit = _UNITS[match.group(1).lower()]
        start = _period_start(day, unit)
        return _midnight(start), _midnight(core.add_period(start, 1, unit))

    if match := PREVIOUS_RE.match(text):
        unit = _UNITS[match.group(1).lower()]
        start = _period_start(day, unit)
        return _midnight(core.add_period(start, -1, unit)), _midnight(start)

    if match := TO_DATE_RE.match(text):
        unit = _UNITS[match.group(1).lower()]
        return (_midnight(_period_start(day, unit)),
                _midnight(day + dt.timedelta(days=1)))

    if match := LAST_RE.match(text):
        count = int(match.group(1) or 1)
        unit = _UNITS[match.group(2).lower()]
        return _midnight(core.add_period(day, -count, unit)), today

    if match := NEXT_RE.match(text):
        count = int(match.group(1) or 1)
        unit = _UNITS[match.group(2).lower()]
        return today, _midnight(core.add_period(day, count, unit))

    # a single literal names a whole period: "jalali:1403-12" is all of Esfand
    literal = parse_endpoint(text, require_prefix=not bare_literals, whole_period=True)
    if literal is not None:
        return literal
    return None


def parse_endpoint(text: str, require_prefix: bool = False,
                   whole_period: bool = False
                   ) -> tuple[dt.datetime, dt.datetime] | dt.datetime | None:
    """Parse one Jalali literal. With ``whole_period`` the result is the
    half-open interval the literal denotes, otherwise its start instant.
    ``require_prefix`` refuses bare literals such as "1403-12-20"."""
    stripped = text.strip()
    prefixed = PREFIX_RE.match(stripped)
    if prefixed:
        stripped = stripped[prefixed.end():]
    elif require_prefix:
        return None
    parsed = core.parse_literal(stripped)
    if parsed is None:
        if prefixed:
            raise ValueError(f'Invalid Jalali literal: {text!r}')
        return None
    if whole_period:
        return parsed.datetime, parsed.period_end()
    return parsed.datetime


def rewrite(time_range: str | None, relative_start: str | None = None,
            relative_end: str | None = None, bare_literals: bool = True,
            now: dt.datetime | None = None,
            clock: CalendarClock | None = None) -> str | None:
    """Rewrite a Jalali time range into the ISO ``since : until`` form Superset
    understands, or return None when there is nothing Jalali about it."""
    if not time_range or not isinstance(time_range, str):
        return None
    text = time_range.strip()
    clock = clock or CalendarClock()
    if SEPARATOR not in text:
        resolved = resolve(text, clock.now(now or relative_start), bare_literals)
        if resolved is None:
            return None
        since, until = (clock.to_storage(part, boundary=True) for part in resolved)
        return f"{since.strftime(ISO)}{SEPARATOR}{until.strftime(ISO)}"

    # "<since> : <until>": rewrite only the sides that are Jalali literals and
    # hand the rest back to Superset unchanged, so "jalali:1403-12-20 : now" works.
    out: list[str] = []
    touched = False
    for part in (side.strip() for side in text.split(SEPARATOR, 1)):
        endpoint = parse_endpoint(part, require_prefix=not bare_literals)
        if endpoint is None:
            out.append(part)
            continue
        touched = True
        out.append(clock.to_storage(endpoint).strftime(ISO))
    if touched:
        try:
            start, end = (dt.datetime.fromisoformat(part) for part in out)
        except ValueError:
            pass  # mixed Superset expressions are validated by get_since_until
        else:
            if start > end:
                raise ValueError('Range start must not be after its exclusive end')
    return SEPARATOR.join(out) if touched else None


def describe(time_range: str, now: dt.datetime | None = None) -> str:
    """A Persian label for a Jalali range, for tooltips and documentation."""
    if time_range in LABELS:
        return LABELS[time_range]
    resolved = resolve(time_range, now)
    if resolved is None:
        return time_range
    since, until = resolved
    # the interval is half-open, so name the last day it actually contains
    last = until - dt.timedelta(seconds=1)
    first_fa = core.format_named(since, "jalali_date")
    last_fa = core.format_named(last, "jalali_date")
    return first_fa if first_fa == last_fa else f"{first_fa} تا {last_fa}"

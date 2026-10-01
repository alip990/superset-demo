"""Jalali (Solar Hijri / Persian) calendar arithmetic, formatting and parsing.

No third-party dependency: the conversion is Borkowski's algorithm (the one
jalaali-js / moment-jalaali / jdf use), which reproduces the *official* Iranian
calendar - the one printed on Iranian wall calendars - for Jalali years
1178..1633 (1799..2256 CE).

Why not a library or the browser's calendar:

* ``jdatetime`` / ``khayyam`` are extra dependencies in the Superset image.
* ``Intl``/ICU (what plugins/superset-jalali used to use) depends on the ICU
  version shipped with the browser or Node build; builds with ``small-icu`` have
  no Persian calendar at all, and ``formatToParts`` per cell is slow in big
  tables. Arithmetic is deterministic, fast and identical on every runtime.

The frontend plugin (plugins/superset-jalali/src/core/jalali.ts) is a literal
port of this module, and tests/fixtures/jalali_cases.json is generated from here
and asserted by both test suites, so the two sides can never drift apart.

Verified against the ICU Persian calendar (Node ``Intl``, fa-IR-u-ca-persian)
and against ``bi.to_jalali()`` from backups/02-bi.sql for every day between
1900-01-01 and 2200-12-31: all three agree, 1403 is a leap year and
1403-12-30 = 2025-03-20, as the official calendar has it.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Iterable, NamedTuple

# ---------------------------------------------------------------- names ------
# Month and weekday names are data, not formatting: charts group by them.
MONTH_NAMES = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
MONTH_NAMES_EN = (
    "Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar",
    "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand",
)
# The Iranian week starts on Saturday; index 0 is Saturday, like day_of_week().
WEEKDAY_NAMES = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
WEEKDAY_NAMES_EN = (
    "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
)
# Jalali quarters are the four seasons: months 1-3, 4-6, 7-9, 10-12.
SEASON_NAMES = ("بهار", "تابستان", "پاییز", "زمستان")
SEASON_NAMES_EN = ("Spring", "Summer", "Autumn", "Winter")
HALF_NAMES = ("نیمه اول", "نیمه دوم")

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_PERSIAN = str.maketrans("0123456789", PERSIAN_DIGITS)
_TO_LATIN = str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS, "0123456789" * 2)

# Borkowski's breaks table spans these Jalali years; outside them a conversion
# raises instead of returning a wrong date.
DOMAIN_MIN_YEAR, DOMAIN_MAX_YEAR = -61, 3177
# Inside this narrower window the result is the *official* Iranian calendar.
# Literal parsing is restricted to it, which is also what keeps a Gregorian date
# from ever being read as a Jalali one: no real data is from the 15th century.
MIN_YEAR, MAX_YEAR = 1178, 1633

# Jalali months 1..6 have 31 days, 7..11 have 30, Esfand has 29 or 30.
_LONG_MONTHS = 6
_DAYS_BEFORE_MONTH = (0, 31, 62, 93, 124, 155, 186, 216, 246, 276, 306, 336)
_QUARTER_START_DOY0 = (0, 93, 186, 276)  # 0-based day of year each season starts
_HALF_START_DOY0 = (0, 186)


class JalaliDate(NamedTuple):
    """A Jalali calendar date. ``month`` is 1..12, ``day`` 1..31."""

    year: int
    month: int
    day: int

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


# ------------------------------------------------------- Borkowski core ------
# Integer division/modulo truncating toward zero, as in the reference C/JS
# implementation. Python's // and % floor instead, which differs for negatives.
def _div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _mod(a: int, b: int) -> int:
    return a - b * _div(a, b)


# Jalali years where the 33-year cycle shifts; see Borkowski, "The Persian
# calendar for 3000 years" (1996).
_BREAKS = (-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060,
           2097, 2192, 2262, 2324, 2394, 2456, 3178)


def _jal_cal(jy: int) -> tuple[int, int, int]:
    """(leap, gregorian_year, march_day): ``leap`` is 0 on a leap year, and
    1 Farvardin of ``jy`` falls on ``march_day`` March of ``gregorian_year``."""
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    if jy < jp or jy >= _BREAKS[-1]:
        raise ValueError(f"Jalali year out of range: {jy}")
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap, gy, march


def _g2d(gy: int, gm: int, gd: int) -> int:
    """Gregorian date -> Julian Day Number."""
    d = (_div((gy + _div(gm - 8, 6) + 100100) * 1461, 4)
         + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408)
    return d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752


def _d2g(jdn: int) -> tuple[int, int, int]:
    """Julian Day Number -> Gregorian date."""
    j = 4 * jdn + 139361631
    j += _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd


def is_leap_year(jy: int) -> bool:
    """Does Esfand of ``jy`` have 30 days?"""
    return _jal_cal(jy)[0] == 0


def days_in_month(jy: int, jm: int) -> int:
    if not 1 <= jm <= 12:
        raise ValueError(f"Jalali month out of range: {jm}")
    if jm <= _LONG_MONTHS:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap_year(jy) else 29


def days_in_year(jy: int) -> int:
    return 366 if is_leap_year(jy) else 365


def to_jalali(value: dt.date | dt.datetime) -> JalaliDate:
    """Gregorian date (or the date part of a datetime) -> Jalali date."""
    if isinstance(value, dt.datetime):
        value = value.date()
    jdn = _g2d(value.year, value.month, value.day)
    gy = _d2g(jdn)[0]
    jy = gy - 621
    leap, _, march = _jal_cal(jy)
    k = jdn - _g2d(gy, 3, march)
    if k >= 0:
        if k <= 185:
            return JalaliDate(jy, 1 + _div(k, 31), _mod(k, 31) + 1)
        k -= 186
    else:
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return JalaliDate(jy, 7 + _div(k, 30), _mod(k, 30) + 1)


def from_jalali(jy: int, jm: int, jd: int) -> dt.date:
    """Jalali date -> Gregorian date. Rejects days the Jalali month lacks."""
    if not 1 <= jm <= 12:
        raise ValueError(f"Jalali month out of range: {jm}")
    if not 1 <= jd <= days_in_month(jy, jm):
        raise ValueError(f"no day {jd} in {jy}-{jm:02d}")
    _, gy, march = _jal_cal(jy)
    jdn = (_g2d(gy, 3, march) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1)
    return dt.date(*_d2g(jdn))


def to_datetime(jy: int, jm: int, jd: int, hour: int = 0, minute: int = 0,
                second: int = 0) -> dt.datetime:
    d = from_jalali(jy, jm, jd)
    return dt.datetime(d.year, d.month, d.day, hour, minute, second)


# ------------------------------------------------------ derived values -------
def day_of_year(value: dt.date | dt.datetime) -> int:
    """1-based day of the Jalali year."""
    j = to_jalali(value)
    return _DAYS_BEFORE_MONTH[j.month - 1] + j.day


def day_of_week(value: dt.date | dt.datetime) -> int:
    """0 = Saturday .. 6 = Friday, the Iranian week."""
    if isinstance(value, dt.datetime):
        value = value.date()
    # date.weekday(): 0 = Monday .. 6 = Sunday
    return (value.weekday() + 2) % 7


def quarter(value: dt.date | dt.datetime) -> int:
    """1..4 - the Jalali quarter, i.e. the season."""
    return (to_jalali(value).month - 1) // 3 + 1


def is_weekend(value: dt.date | dt.datetime, thursday: bool = False) -> bool:
    """Friday is the Iranian weekend; some employers add Thursday."""
    dow = day_of_week(value)
    return dow == 6 or (thursday and dow == 5)


def _as_date(value: dt.date | dt.datetime) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


def day_start(value: dt.date | dt.datetime) -> dt.date:
    return _as_date(value)


def week_start(value: dt.date | dt.datetime) -> dt.date:
    """Saturday of the week containing ``value``."""
    d = _as_date(value)
    return d - dt.timedelta(days=day_of_week(d))


def month_start(value: dt.date | dt.datetime) -> dt.date:
    j = to_jalali(value)
    return _as_date(value) - dt.timedelta(days=j.day - 1)


def quarter_start(value: dt.date | dt.datetime) -> dt.date:
    doy0 = day_of_year(value) - 1
    season = next(s for s in reversed(_QUARTER_START_DOY0) if doy0 >= s)
    return _as_date(value) - dt.timedelta(days=doy0 - season)


def half_year_start(value: dt.date | dt.datetime) -> dt.date:
    doy0 = day_of_year(value) - 1
    half = _HALF_START_DOY0[1] if doy0 >= _HALF_START_DOY0[1] else 0
    return _as_date(value) - dt.timedelta(days=doy0 - half)


def year_start(value: dt.date | dt.datetime) -> dt.date:
    return _as_date(value) - dt.timedelta(days=day_of_year(value) - 1)


PERIOD_STARTS = {
    "day": day_start,
    "week": week_start,
    "month": month_start,
    "quarter": quarter_start,
    "half": half_year_start,
    "year": year_start,
}


def add_months(value: dt.date | dt.datetime, months: int) -> dt.date:
    """Shift by whole Jalali months, clamping the day (31 Farvardin - 1 month
    is 30 Esfand in a leap year, 29 Esfand otherwise)."""
    j = to_jalali(value)
    total = (j.year * 12 + j.month - 1) + months
    jy, jm = divmod(total, 12)
    jm += 1
    return from_jalali(jy, jm, min(j.day, days_in_month(jy, jm)))


def add_years(value: dt.date | dt.datetime, years: int) -> dt.date:
    j = to_jalali(value)
    return from_jalali(j.year + years, j.month,
                       min(j.day, days_in_month(j.year + years, j.month)))


def add_period(value: dt.date | dt.datetime, periods: int, unit: str) -> dt.date:
    """``unit`` is one of PERIOD_STARTS' keys (plus 'day'/'week' in days)."""
    if unit == "day":
        return _as_date(value) + dt.timedelta(days=periods)
    if unit == "week":
        return _as_date(value) + dt.timedelta(days=7 * periods)
    if unit == "month":
        return add_months(value, periods)
    if unit == "quarter":
        return add_months(value, 3 * periods)
    if unit == "half":
        return add_months(value, 6 * periods)
    if unit == "year":
        return add_years(value, periods)
    raise ValueError(f"unknown Jalali period: {unit}")


# ---------------------------------------------------------- formatting -------
def to_persian_digits(text: str) -> str:
    return text.translate(_TO_PERSIAN)


def to_latin_digits(text: str) -> str:
    return text.translate(_TO_LATIN)


# dayjs-style tokens, so the format strings are the same ones the frontend
# plugin accepts. Longest token first: the formatter scans greedily.
_TOKEN_RE = re.compile(
    r"\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|DDDD|DDD|DD|D|dddd|ddd|HH|H|hh|h|mm|m|"
    r"ss|s|QQQQ|QQ|Q|WW|W|A|a"
)


def format_jalali(value: dt.date | dt.datetime, pattern: str,
                  persian_digits: bool = False, english_names: bool = False) -> str:
    """Format a date/datetime with dayjs-like tokens in the Jalali calendar."""
    j = to_jalali(value)
    time = value if isinstance(value, dt.datetime) else None
    hour = time.hour if time else 0
    minute = time.minute if time else 0
    second = time.second if time else 0
    months = MONTH_NAMES_EN if english_names else MONTH_NAMES
    weekdays = WEEKDAY_NAMES_EN if english_names else WEEKDAY_NAMES
    seasons = SEASON_NAMES_EN if english_names else SEASON_NAMES
    doy = _DAYS_BEFORE_MONTH[j.month - 1] + j.day
    dow = day_of_week(value)
    qtr = (j.month - 1) // 3 + 1
    week = (doy - 1) // 7 + 1

    def token(match: re.Match[str]) -> str:
        if match.group(1) is not None:  # [literal]
            return match.group(1)
        tok = match.group(0)
        return {
            "YYYY": f"{j.year:04d}", "YY": f"{j.year % 100:02d}",
            "MMMM": months[j.month - 1], "MMM": months[j.month - 1][:3],
            "MM": f"{j.month:02d}", "M": str(j.month),
            "DD": f"{j.day:02d}", "D": str(j.day),
            "DDDD": f"{doy:03d}", "DDD": str(doy),
            "dddd": weekdays[dow], "ddd": weekdays[dow][:3],
            "HH": f"{hour:02d}", "H": str(hour),
            "hh": f"{(hour % 12) or 12:02d}", "h": str((hour % 12) or 12),
            "mm": f"{minute:02d}", "m": str(minute),
            "ss": f"{second:02d}", "s": str(second),
            "QQQQ": seasons[qtr - 1], "QQ": f"{qtr:02d}", "Q": str(qtr),
            "WW": f"{week:02d}", "W": str(week),
            "A": "ق.ظ" if hour < 12 else "ب.ظ",
            "a": "ق.ظ" if hour < 12 else "ب.ظ",
        }[tok]

    out = _TOKEN_RE.sub(token, pattern)
    return to_persian_digits(out) if persian_digits else out


# The named formats the frontend registers in Superset's time-format registry.
# Kept here as well so SQL macros and reports can produce the same strings.
NAMED_FORMATS = {
    "jalali_date": "YYYY-MM-DD",
    "jalali_datetime": "YYYY-MM-DD HH:mm:ss",
    "jalali_minute": "YYYY-MM-DD HH:mm",
    "jalali_month": "MMMM YYYY",
    "jalali_month_short": "YYYY-MM",
    "jalali_quarter": "QQQQ YYYY",
    "jalali_year": "YYYY",
    "jalali_week": "[هفته] W [-] YYYY",
    "jalali_verbose": "dddd D MMMM YYYY",
    "jalali_day_month": "D MMMM",
}


def format_named(value: dt.date | dt.datetime, name: str,
                 persian_digits: bool = False) -> str:
    return format_jalali(value, NAMED_FORMATS[name], persian_digits)


def format_smart(value: dt.date | dt.datetime, persian_digits: bool = False) -> str:
    """Adaptive labels, like Superset's smart_date but on Jalali boundaries:
    a time of day if there is one, else the year on 1 Farvardin, the month name
    on the 1st of a month, otherwise "20 اسفند"."""
    time = value if isinstance(value, dt.datetime) else None
    j = to_jalali(value)
    if time and (time.second or time.microsecond):
        out = f"{time.hour:02d}:{time.minute:02d}:{time.second:02d}"
    elif time and (time.hour or time.minute):
        out = f"{time.hour:02d}:{time.minute:02d}"
    elif j.day == 1 and j.month == 1:
        out = f"{j.year:04d}"
    elif j.day == 1:
        out = MONTH_NAMES[j.month - 1]
    else:
        out = f"{j.day} {MONTH_NAMES[j.month - 1]}"
    return to_persian_digits(out) if persian_digits else out


# ------------------------------------------------------------- parsing -------
# 1403-12-20, 1403/12/20, ۱۴۰۳/۱۲/۲۰, 1403-12 (whole month), 1403 (whole year),
# any of them with a time of day.
_LITERAL_RE = re.compile(
    r"^(?P<y>\d{3,4})(?:[-/](?P<m>\d{1,2})(?:[-/](?P<d>\d{1,2}))?)?"
    r"(?:[ T](?P<H>\d{1,2}):(?P<M>\d{1,2})(?::(?P<S>\d{1,2}))?)?$"
)
_QUARTER_RE = re.compile(r"^(?P<y>\d{3,4})[-/]?[qQ](?P<q>[1-4])$")


class JalaliLiteral(NamedTuple):
    """A parsed Jalali literal. ``precision`` says how much of it was given,
    which is what makes "1403-12" mean the whole month of Esfand."""

    date: dt.date
    precision: str  # year | quarter | month | day | minute | second
    hour: int = 0
    minute: int = 0
    second: int = 0

    @property
    def datetime(self) -> dt.datetime:
        return dt.datetime(self.date.year, self.date.month, self.date.day,
                           self.hour, self.minute, self.second)

    def period_end(self) -> dt.datetime:
        """Exclusive end of the period the literal denotes."""
        if self.precision == "year":
            return dt.datetime.combine(add_years(self.date, 1), dt.time())
        if self.precision == "quarter":
            return dt.datetime.combine(add_months(self.date, 3), dt.time())
        if self.precision == "month":
            return dt.datetime.combine(add_months(self.date, 1), dt.time())
        if self.precision == "day":
            return dt.datetime.combine(self.date + dt.timedelta(days=1), dt.time())
        if self.precision == "minute":
            return self.datetime + dt.timedelta(minutes=1)
        return self.datetime + dt.timedelta(seconds=1)


def parse_literal(text: str) -> JalaliLiteral | None:
    """Parse a Jalali literal, or return None if it is not one. Persian and
    Arabic-Indic digits are accepted; the year must be inside the supported
    window, so a Gregorian date can never be mistaken for a Jalali one."""
    normalised = to_latin_digits(text.strip()).replace("‏", "")
    if not normalised:
        return None
    match = _QUARTER_RE.match(normalised)
    if match:
        jy, q = int(match.group("y")), int(match.group("q"))
        if not MIN_YEAR <= jy <= MAX_YEAR:
            return None
        return JalaliLiteral(from_jalali(jy, 3 * (q - 1) + 1, 1), "quarter")
    match = _LITERAL_RE.match(normalised)
    if not match:
        return None
    jy = int(match.group("y"))
    if not MIN_YEAR <= jy <= MAX_YEAR:
        return None
    jm = int(match.group("m") or 1)
    jd = int(match.group("d") or 1)
    if not 1 <= jm <= 12 or not 1 <= jd <= days_in_month(jy, jm):
        return None
    hour = int(match.group("H") or 0)
    minute = int(match.group("M") or 0)
    second = int(match.group("S") or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    if match.group("H") is not None:
        precision = "second" if match.group("S") is not None else "minute"
    elif match.group("d") is not None:
        precision = "day"
    elif match.group("m") is not None:
        precision = "month"
    else:
        precision = "year"
    return JalaliLiteral(from_jalali(jy, jm, jd), precision, hour, minute, second)


def iter_dates(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    """Every date in [start, end], inclusive - used by the calendar table."""
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)

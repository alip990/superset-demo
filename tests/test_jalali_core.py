"""Calendar arithmetic, formatting and parsing.

Run every test:  python3 -m unittest discover -s tests -v
No third-party package is needed. Where Node is installed the suite also
cross-checks every day of 300 years against the ICU Persian calendar, which is
an implementation nobody here wrote.
"""

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "superset"))

from jalali_calendar import core, ranges  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "jalali_cases.json"

# Leap years of the official Iranian calendar, as printed on Iranian calendars.
KNOWN_LEAP_YEARS = {1362, 1366, 1370, 1375, 1379, 1383, 1387, 1391, 1395, 1399,
                    1403, 1408, 1412, 1416, 1420, 1424, 1428, 1432, 1436, 1441}
# Dates everybody in Iran knows, as an anchor against algorithm drift.
KNOWN_DATES = [
    ("2025-03-20", 1403, 12, 30),   # last day of a leap year
    ("2025-03-21", 1404, 1, 1),     # Nowruz 1404
    ("2024-03-20", 1403, 1, 1),     # Nowruz 1403
    ("2021-03-20", 1399, 12, 30),   # leap year 1399
    ("2026-03-21", 1405, 1, 1),
    ("1979-02-11", 1357, 11, 22),   # 22 Bahman 1357
    ("2016-03-20", 1395, 1, 1),
    ("2000-01-01", 1378, 10, 11),
]


class TestConversion(unittest.TestCase):
    def test_known_dates(self):
        for iso, jy, jm, jd in KNOWN_DATES:
            with self.subTest(iso):
                self.assertEqual(core.to_jalali(dt.date.fromisoformat(iso)),
                                 (jy, jm, jd))
                self.assertEqual(core.from_jalali(jy, jm, jd),
                                 dt.date.fromisoformat(iso))

    def test_round_trip_every_day_1900_2200(self):
        day, end, count = dt.date(1900, 1, 1), dt.date(2200, 12, 31), 0
        while day <= end:
            jy, jm, jd = core.to_jalali(day)
            self.assertEqual(core.from_jalali(jy, jm, jd), day, day.isoformat())
            count += 1
            day += dt.timedelta(days=1)
        self.assertEqual(count, 109938)

    def test_leap_years(self):
        found = {jy for jy in range(1360, 1445) if core.is_leap_year(jy)}
        self.assertEqual(found & KNOWN_LEAP_YEARS, KNOWN_LEAP_YEARS & found)
        self.assertEqual(found, {jy for jy in KNOWN_LEAP_YEARS if jy < 1445})

    def test_leap_year_has_366_days(self):
        for jy in range(1360, 1445):
            length = (core.from_jalali(jy + 1, 1, 1) - core.from_jalali(jy, 1, 1)).days
            self.assertEqual(length, core.days_in_year(jy), jy)
            self.assertEqual(length, 366 if jy in KNOWN_LEAP_YEARS else 365, jy)

    def test_month_lengths(self):
        for jy in (1402, 1403, 1404):
            for jm in range(1, 13):
                expected = (core.from_jalali(jy + (jm == 12), (jm % 12) + 1, 1)
                            - core.from_jalali(jy, jm, 1)).days
                self.assertEqual(core.days_in_month(jy, jm), expected, (jy, jm))
        self.assertEqual(core.days_in_month(1403, 12), 30)
        self.assertEqual(core.days_in_month(1404, 12), 29)

    def test_out_of_domain_year_is_refused(self):
        # the conversion domain is wider than the window the official calendar
        # is guaranteed in, but it is not unbounded
        with self.assertRaises(ValueError):
            core.from_jalali(core.DOMAIN_MIN_YEAR - 1, 1, 1)
        with self.assertRaises(ValueError):
            core.to_jalali(dt.date(400, 1, 1))
        # ... while literals are only accepted inside the accurate window, so a
        # Gregorian date can never be read as a Jalali one
        self.assertIsNone(core.parse_literal(f"{core.MIN_YEAR - 1}-01-01"))
        self.assertIsNone(core.parse_literal(f"{core.MAX_YEAR + 1}-01-01"))
        self.assertIsNotNone(core.parse_literal(f"{core.MIN_YEAR}-01-01"))

    def test_invalid_day_is_refused(self):
        with self.assertRaises(ValueError):
            core.from_jalali(1404, 12, 30)  # 1404 is not a leap year
        with self.assertRaises(ValueError):
            core.from_jalali(1403, 7, 31)   # Mehr has 30 days


class TestDerivedValues(unittest.TestCase):
    def test_day_of_week_is_saturday_first(self):
        # 2025-03-08 was a Saturday
        self.assertEqual(core.day_of_week(dt.date(2025, 3, 8)), 0)
        self.assertEqual(core.day_of_week(dt.date(2025, 3, 14)), 6)  # Friday
        self.assertEqual(core.WEEKDAY_NAMES[core.day_of_week(dt.date(2025, 3, 10))],
                         "دوشنبه")

    def test_day_of_year(self):
        self.assertEqual(core.day_of_year(dt.date(2025, 3, 21)), 1)      # 1 Farvardin
        self.assertEqual(core.day_of_year(dt.date(2025, 3, 20)), 366)    # 30 Esfand 1403
        self.assertEqual(core.day_of_year(dt.date(2026, 3, 20)), 365)    # 29 Esfand 1404

    def test_period_starts(self):
        day = dt.date(2025, 3, 10)  # 20 Esfand 1403, a Monday
        self.assertEqual(core.day_start(day), day)
        self.assertEqual(core.week_start(day), dt.date(2025, 3, 8))
        self.assertEqual(core.month_start(day), dt.date(2025, 2, 19))
        self.assertEqual(core.quarter_start(day), dt.date(2024, 12, 21))
        self.assertEqual(core.half_year_start(day), dt.date(2024, 9, 22))
        self.assertEqual(core.year_start(day), dt.date(2024, 3, 20))

    def test_period_start_is_idempotent_and_in_period(self):
        day, end = dt.date(2020, 1, 1), dt.date(2030, 12, 31)
        while day <= end:
            for unit, func in core.PERIOD_STARTS.items():
                start = func(day)
                self.assertLessEqual(start, day, (unit, day))
                self.assertEqual(func(start), start, (unit, day))
            self.assertEqual(core.to_jalali(core.month_start(day)).day, 1)
            self.assertEqual(core.to_jalali(core.year_start(day))[1:], (1, 1))
            self.assertIn(core.to_jalali(core.quarter_start(day)).month, (1, 4, 7, 10))
            self.assertEqual(core.day_of_week(core.week_start(day)), 0)
            day += dt.timedelta(days=1)

    def test_quarter_and_weekend(self):
        self.assertEqual(core.quarter(dt.date(2025, 3, 10)), 4)   # Esfand -> winter
        self.assertEqual(core.quarter(dt.date(2025, 4, 10)), 1)   # Farvardin -> spring
        self.assertTrue(core.is_weekend(dt.date(2025, 3, 14)))    # Friday
        self.assertFalse(core.is_weekend(dt.date(2025, 3, 13)))   # Thursday
        self.assertTrue(core.is_weekend(dt.date(2025, 3, 13), thursday=True))

    def test_add_months_clamps_the_day(self):
        # 31 Farvardin minus one month: Esfand has 29 or 30 days
        self.assertEqual(core.add_months(dt.date(2025, 4, 20), -1),  # 31/1/1404
                         dt.date(2025, 3, 20))                      # 30/12/1403
        self.assertEqual(core.add_months(dt.date(2024, 4, 19), -1),  # 31/1/1403
                         dt.date(2024, 3, 19))                      # 30/12/1402?
        self.assertEqual(core.to_jalali(core.add_months(dt.date(2024, 4, 19), -1)),
                         (1402, 12, 29))
        self.assertEqual(core.add_months(dt.date(2025, 3, 10), 1),
                         dt.date(2025, 4, 9))  # 20 Esfand -> 20 Farvardin

    def test_add_period(self):
        day = dt.date(2025, 3, 10)
        self.assertEqual(core.add_period(day, 1, "day"), dt.date(2025, 3, 11))
        self.assertEqual(core.add_period(day, 1, "week"), dt.date(2025, 3, 17))
        self.assertEqual(core.add_period(day, -1, "quarter"),
                         core.add_months(day, -3))
        self.assertEqual(core.add_period(day, 1, "half"), core.add_months(day, 6))
        self.assertEqual(core.to_jalali(core.add_period(day, 1, "year")),
                         (1404, 12, 20))


class TestFormatting(unittest.TestCase):
    def test_tokens(self):
        value = dt.datetime(2025, 3, 10, 14, 32, 5)  # دوشنبه 20 اسفند 1403
        self.assertEqual(core.format_jalali(value, "YYYY-MM-DD"), "1403-12-20")
        self.assertEqual(core.format_jalali(value, "YYYY/M/D HH:mm:ss"),
                         "1403/12/20 14:32:05")
        self.assertEqual(core.format_jalali(value, "dddd D MMMM YYYY"),
                         "دوشنبه 20 اسفند 1403")
        self.assertEqual(core.format_jalali(value, "QQQQ YYYY"), "زمستان 1403")
        self.assertEqual(core.format_jalali(value, "Q"), "4")
        self.assertEqual(core.format_jalali(value, "YY A"), "03 ب.ظ")
        self.assertEqual(core.format_jalali(value, "[ساعت] HH"), "ساعت 14")
        self.assertEqual(core.format_jalali(value, "DDD"), "356")

    def test_persian_digits(self):
        value = dt.date(2025, 3, 10)
        self.assertEqual(core.format_jalali(value, "YYYY-MM-DD", True), "۱۴۰۳-۱۲-۲۰")
        self.assertEqual(core.to_latin_digits("۱۴۰۳/۱۲/۲۰"), "1403/12/20")
        self.assertEqual(core.to_latin_digits("١٤٠٣"), "1403")  # Arabic-Indic

    def test_named_formats(self):
        value = dt.datetime(2025, 3, 10, 14, 32, 5)
        self.assertEqual(core.format_named(value, "jalali_month"), "اسفند 1403")
        self.assertEqual(core.format_named(value, "jalali_datetime"),
                         "1403-12-20 14:32:05")
        self.assertEqual(core.format_named(value, "jalali_quarter"), "زمستان 1403")

    def test_smart_format(self):
        self.assertEqual(core.format_smart(dt.date(2025, 3, 21)), "1404")
        self.assertEqual(core.format_smart(dt.date(2025, 2, 19)), "اسفند")
        self.assertEqual(core.format_smart(dt.date(2025, 3, 10)), "20 اسفند")
        self.assertEqual(core.format_smart(dt.datetime(2025, 3, 10, 14, 30)), "14:30")
        self.assertEqual(core.format_smart(dt.datetime(2025, 3, 10, 14, 30, 9)),
                         "14:30:09")


class TestParsing(unittest.TestCase):
    def test_precision(self):
        for text, expected, precision in [
            ("1403", "2024-03-20", "year"),
            ("1403-12", "2025-02-19", "month"),
            ("1403-q4", "2024-12-21", "quarter"),
            ("1403-12-20", "2025-03-10", "day"),
            ("1403/12/20", "2025-03-10", "day"),
            ("۱۴۰۳/۱۲/۲۰", "2025-03-10", "day"),
            ("1403-12-20 14:30", "2025-03-10", "minute"),
            ("1403-12-20T14:30:05", "2025-03-10", "second"),
        ]:
            with self.subTest(text):
                parsed = core.parse_literal(text)
                self.assertIsNotNone(parsed, text)
                self.assertEqual(parsed.date, dt.date.fromisoformat(expected))
                self.assertEqual(parsed.precision, precision)

    def test_period_end(self):
        self.assertEqual(core.parse_literal("1403-12").period_end(),
                         dt.datetime(2025, 3, 21))
        self.assertEqual(core.parse_literal("1403").period_end(),
                         dt.datetime(2025, 3, 21))
        self.assertEqual(core.parse_literal("1403-q4").period_end(),
                         dt.datetime(2025, 3, 21))
        self.assertEqual(core.parse_literal("1403-12-20").period_end(),
                         dt.datetime(2025, 3, 11))

    def test_gregorian_dates_are_not_mistaken_for_jalali(self):
        for text in ["2025-03-10", "1999-01-01", "2020", "", "hello",
                     "1403-13-01", "1404-12-30", "1403-12-20 25:00"]:
            self.assertIsNone(core.parse_literal(text), text)


class TestIcuCrossCheck(unittest.TestCase):
    """The browser's own Persian calendar as an independent oracle."""

    @classmethod
    def setUpClass(cls):
        script = (
            "const f=new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn',"
            "{timeZone:'UTC',year:'numeric',month:'numeric',day:'numeric'});"
            "let d=Date.UTC(1900,0,1), out=[];"
            "const end=Date.UTC(2200,11,31);"
            "for(;d<=end;d+=86400000){const o={};"
            "f.formatToParts(new Date(d)).forEach(p=>o[p.type]=p.value);"
            "out.push(`${o.year}-${o.month}-${o.day}`);}"
            "console.log(out.join(' '));"
        )
        try:
            result = subprocess.run(["node", "-e", script], capture_output=True,
                                    text=True, timeout=600, check=True)
        except (OSError, subprocess.SubprocessError) as ex:
            raise unittest.SkipTest(f"node with full ICU not available: {ex}")
        cls.icu = result.stdout.split()

    def test_every_day_matches_icu_with_documented_1502_correction(self):
        day = dt.date(1900, 1, 1)
        self.assertGreater(len(self.icu), 100000)
        mismatches = []
        for value in self.icu:
            jy, jm, jd = (int(part) for part in value.split("-"))
            if core.to_jalali(day) != (jy, jm, jd):
                mismatches.append(day)
            day += dt.timedelta(days=1)
        # ICU release-77-1/persncal.cpp explicitly moves the leap day from
        # AP 1502 to 1503. Borkowski and our SQL retain the original arithmetic.
        # Older ICU has no correction. Fail on ANY other divergence.
        corrected = self.icu[(dt.date(2124, 3, 20) - dt.date(1900, 1, 1)).days] == '1503-1-1'
        expected = [dt.date(2124, 3, 20) + dt.timedelta(days=i) for i in range(366)] if corrected else []
        self.assertEqual(mismatches, expected)
        self.assertEqual(core.to_jalali(dt.date(2124, 3, 20)), (1502, 12, 30))
        self.assertEqual(core.to_jalali(dt.date(2125, 3, 20)), (1503, 12, 29))


class TestSharedFixtures(unittest.TestCase):
    """tests/fixtures/jalali_cases.json is asserted by this suite and by the
    TypeScript suite in plugins/superset-jalali, so the two implementations of
    the calendar cannot drift apart. Regenerate with
    ``python3 tests/test_jalali_core.py --write-fixtures``."""

    def test_fixtures_match(self):
        self.assertTrue(FIXTURES.exists(), "run with --write-fixtures first")
        cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
        for case in cases["conversions"]:
            value = dt.date.fromisoformat(case["gregorian"])
            self.assertEqual(list(core.to_jalali(value)), case["jalali"],
                             case["gregorian"])
        for case in cases["formats"]:
            value = dt.datetime.fromisoformat(case["gregorian"])
            digits = case.get("persianDigits", False)
            actual = (core.format_smart(value, digits)
                      if case["pattern"] == "@smart"
                      else core.format_jalali(value, case["pattern"], digits))
            self.assertEqual(actual, case["expected"], case)
        for case in cases["periodStarts"]:
            value = dt.date.fromisoformat(case["gregorian"])
            for unit, expected in case["starts"].items():
                self.assertEqual(core.PERIOD_STARTS[unit](value).isoformat(),
                                 expected, (case["gregorian"], unit))
        self.assertEqual(
            cases["ranges"],
            {group: [list(item) for item in items] for group, items in
             (("common", ranges.COMMON_RANGES),
              ("calendar", ranges.CALENDAR_RANGES),
              ("current", ranges.CURRENT_RANGES))},
            "regenerate the fixtures: the range vocabulary changed")
        for case in cases["literals"]:
            parsed = core.parse_literal(case["text"])
            if case["date"] is None:
                self.assertIsNone(parsed, case["text"])
            else:
                self.assertIsNotNone(parsed, case["text"])
                self.assertEqual(parsed.date.isoformat(), case["date"], case["text"])
                self.assertEqual(parsed.precision, case["precision"], case["text"])


def write_fixtures() -> None:
    """Generate the fixture file both test suites read."""
    conversions = []
    day = dt.date(1920, 1, 1)
    while day <= dt.date(2120, 1, 1):  # every 37th day: ~2000 spread-out cases
        conversions.append({"gregorian": day.isoformat(),
                            "jalali": list(core.to_jalali(day))})
        day += dt.timedelta(days=37)
    for iso, jy, jm, jd in KNOWN_DATES:
        conversions.append({"gregorian": iso, "jalali": [jy, jm, jd]})
    # every Nowruz and the day before it, where off-by-one errors live
    for jy in range(1340, 1460):
        nowruz = core.from_jalali(jy, 1, 1)
        for value in (nowruz - dt.timedelta(days=1), nowruz):
            conversions.append({"gregorian": value.isoformat(),
                                "jalali": list(core.to_jalali(value))})

    patterns = ["YYYY-MM-DD", "YYYY/M/D HH:mm:ss", "dddd D MMMM YYYY",
                "QQQQ YYYY", "YY A", "DDD", "[ساعت] HH:mm", "MMMM", "W"]
    samples = [dt.datetime(2025, 3, 10, 14, 32, 5), dt.datetime(2025, 3, 21),
               dt.datetime(2024, 3, 20, 9, 5), dt.datetime(2025, 9, 22, 23, 59, 59),
               dt.datetime(1979, 2, 11)]
    formats = [{"gregorian": value.isoformat(), "pattern": pattern,
                "expected": core.format_jalali(value, pattern)}
               for value in samples for pattern in patterns]
    formats += [{"gregorian": value.isoformat(), "pattern": "YYYY-MM-DD",
                 "persianDigits": True,
                 "expected": core.format_jalali(value, "YYYY-MM-DD", True)}
                for value in samples]
    formats += [{"gregorian": value.isoformat(), "pattern": "@smart",
                 "expected": core.format_smart(value)} for value in samples]

    period_starts = []
    day = dt.date(2023, 1, 1)
    while day <= dt.date(2027, 12, 31):
        period_starts.append({
            "gregorian": day.isoformat(),
            "starts": {unit: func(day).isoformat()
                       for unit, func in core.PERIOD_STARTS.items()},
        })
        day += dt.timedelta(days=11)

    literal_texts = ["1403", "1403-12", "1403-q4", "1403-Q2", "1403-12-20",
                     "1403/12/20", "۱۴۰۳/۱۲/۲۰", "1403-12-20 14:30",
                     "1403-12-20T14:30:05", "2025-03-10", "1999-01-01", "hello",
                     "1403-13-01", "1404-12-30", ""]
    literals = []
    for text in literal_texts:
        parsed = core.parse_literal(text)
        literals.append({"text": text,
                         "date": parsed.date.isoformat() if parsed else None,
                         "precision": parsed.precision if parsed else None})

    vocabulary = {group: [list(item) for item in items] for group, items in
                  (("common", ranges.COMMON_RANGES),
                   ("calendar", ranges.CALENDAR_RANGES),
                   ("current", ranges.CURRENT_RANGES))}

    FIXTURES.parent.mkdir(parents=True, exist_ok=True)
    FIXTURES.write_text(json.dumps({
        "generatedBy": "tests/test_jalali_core.py --write-fixtures",
        "conversions": conversions, "formats": formats,
        "periodStarts": period_starts, "literals": literals,
        "ranges": vocabulary,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {FIXTURES} "
          f"({len(conversions)} conversions, {len(formats)} formats, "
          f"{len(period_starts)} period starts, {len(literals)} literals, "
          f"{sum(len(items) for items in vocabulary.values())} range shortcuts)")


if __name__ == "__main__":
    if "--write-fixtures" in sys.argv:
        write_fixtures()
    else:
        unittest.main()

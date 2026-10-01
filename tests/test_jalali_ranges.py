"""The Jalali time-range vocabulary: every shortcut the date picker can store,
resolved against a frozen "today".

The expected values are hand-checked against an Iranian calendar:
1403 is a leap year (30 Esfand = 2025-03-20), Nowruz 1404 is 2025-03-21,
1 Esfand 1403 is 2025-02-19 and 2025-03-08 is a Saturday.
"""

import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "superset"))

from jalali_calendar import core, ranges  # noqa: E402

NOW = dt.datetime(2025, 3, 10, 15, 4, 32)  # دوشنبه 20 اسفند 1403


def resolved(expression):
    out = ranges.resolve(expression, NOW)
    return None if out is None else (out[0].isoformat(), out[1].isoformat())


class TestShortcuts(unittest.TestCase):
    def test_current(self):
        self.assertEqual(resolved("Current jalali day"),
                         ("2025-03-10T00:00:00", "2025-03-11T00:00:00"))
        self.assertEqual(resolved("Current jalali week"),
                         ("2025-03-08T00:00:00", "2025-03-15T00:00:00"))
        self.assertEqual(resolved("Current jalali month"),
                         ("2025-02-19T00:00:00", "2025-03-21T00:00:00"))
        self.assertEqual(resolved("Current jalali quarter"),
                         ("2024-12-21T00:00:00", "2025-03-21T00:00:00"))
        self.assertEqual(resolved("Current jalali half"),
                         ("2024-09-22T00:00:00", "2025-03-21T00:00:00"))
        self.assertEqual(resolved("Current jalali year"),
                         ("2024-03-20T00:00:00", "2025-03-21T00:00:00"))

    def test_previous(self):
        self.assertEqual(resolved("previous jalali week"),
                         ("2025-03-01T00:00:00", "2025-03-08T00:00:00"))
        self.assertEqual(resolved("previous jalali month"),
                         ("2025-01-20T00:00:00", "2025-02-19T00:00:00"))
        self.assertEqual(resolved("previous jalali quarter"),
                         ("2024-09-22T00:00:00", "2024-12-21T00:00:00"))
        self.assertEqual(resolved("previous jalali year"),
                         ("2023-03-21T00:00:00", "2024-03-20T00:00:00"))

    def test_last_rolling(self):
        self.assertEqual(resolved("Last jalali day"),
                         ("2025-03-09T00:00:00", "2025-03-10T00:00:00"))
        self.assertEqual(resolved("Last jalali week"),
                         ("2025-03-03T00:00:00", "2025-03-10T00:00:00"))
        # 20 Esfand minus one Jalali month is 20 Bahman
        self.assertEqual(resolved("Last jalali month"),
                         ("2025-02-08T00:00:00", "2025-03-10T00:00:00"))
        self.assertEqual(resolved("Last 3 jalali months"),
                         ("2024-12-10T00:00:00", "2025-03-10T00:00:00"))
        self.assertEqual(resolved("Last jalali year"),
                         ("2024-03-10T00:00:00", "2025-03-10T00:00:00"))
        self.assertEqual(resolved("Last 2 jalali years"),
                         ("2023-03-11T00:00:00", "2025-03-10T00:00:00"))

    def test_next(self):
        self.assertEqual(resolved("Next jalali month"),
                         ("2025-03-10T00:00:00", "2025-04-09T00:00:00"))
        self.assertEqual(resolved("Next 2 jalali weeks"),
                         ("2025-03-10T00:00:00", "2025-03-24T00:00:00"))

    def test_to_date(self):
        # "to date" includes today, so it ends at midnight tomorrow
        self.assertEqual(resolved("jalali month to date"),
                         ("2025-02-19T00:00:00", "2025-03-11T00:00:00"))
        self.assertEqual(resolved("jalali year to date"),
                         ("2024-03-20T00:00:00", "2025-03-11T00:00:00"))
        self.assertEqual(resolved("jalali quarter to date"),
                         ("2024-12-21T00:00:00", "2025-03-11T00:00:00"))

    def test_spelling_variants(self):
        for expression in ["current jalali month", "CURRENT JALALI MONTH",
                           "Current shamsi month", "Current jalaali month"]:
            self.assertEqual(resolved(expression), resolved("Current jalali month"),
                             expression)

    def test_literals_name_a_whole_period(self):
        self.assertEqual(resolved("jalali:1403"),
                         ("2024-03-20T00:00:00", "2025-03-21T00:00:00"))
        self.assertEqual(resolved("jalali:1403-12"),
                         ("2025-02-19T00:00:00", "2025-03-21T00:00:00"))
        self.assertEqual(resolved("jalali:1403-q4"),
                         ("2024-12-21T00:00:00", "2025-03-21T00:00:00"))
        self.assertEqual(resolved("jalali:1403-12-20"),
                         ("2025-03-10T00:00:00", "2025-03-11T00:00:00"))
        self.assertEqual(resolved("۱۴۰۳/۱۲/۲۰"), resolved("jalali:1403-12-20"))

    def test_published_vocabulary_resolves(self):
        """Everything the picker offers must be resolvable, or the Apply button
        would be disabled in the UI."""
        for value, label in ranges.ALL_RANGES:
            self.assertIsNotNone(resolved(value), value)
            self.assertTrue(label.strip(), value)
            since, until = ranges.resolve(value, NOW)
            self.assertLess(since, until, value)

    def test_not_jalali(self):
        for expression in ["Last week", "Current month", "No filter", "",
                           "previous calendar month", "2025-01-01", "DATEADD(x)"]:
            self.assertIsNone(resolved(expression), expression)


class TestRewrite(unittest.TestCase):
    def test_whole_string(self):
        self.assertEqual(ranges.rewrite("Current jalali month", now=NOW),
                         "2025-02-19T00:00:00 : 2025-03-21T00:00:00")

    def test_endpoints(self):
        self.assertEqual(
            ranges.rewrite("jalali:1403-01-01 : jalali:1403-07-01", now=NOW),
            "2024-03-20T00:00:00 : 2024-09-22T00:00:00")
        # a Jalali endpoint next to something only Superset understands
        self.assertEqual(ranges.rewrite("jalali:1403-12-20 : now", now=NOW),
                         "2025-03-10T00:00:00 : now")
        self.assertEqual(ranges.rewrite("today : jalali:1404-01-01", now=NOW),
                         "today : 2025-03-21T00:00:00")

    def test_bare_literals_can_be_turned_off(self):
        self.assertEqual(ranges.rewrite("1403-12-01 : 1404-01-01", now=NOW),
                         "2025-02-19T00:00:00 : 2025-03-21T00:00:00")
        self.assertIsNone(ranges.rewrite("1403-12-01 : 1404-01-01", now=NOW,
                                         bare_literals=False))

    def test_gregorian_is_untouched(self):
        for expression in ["2025-01-01 : 2025-02-01", "Last week", "No filter",
                           "DATEADD(DATETIME('today'), -7, day) : today", None, ""]:
            self.assertIsNone(ranges.rewrite(expression, now=NOW), expression)

    def test_relative_start_anchors_the_vocabulary(self):
        # Superset passes relative_start for time comparison; "this month" has
        # to follow it instead of the server clock
        self.assertEqual(
            ranges.rewrite("Current jalali month", relative_start="2024-05-05T00:00:00"),
            "2024-04-20T00:00:00 : 2024-05-21T00:00:00")

    def test_output_is_what_superset_parses(self):
        """The rewrite has to produce the exact shape get_since_until expects:
        two ISO datetimes separated by ' : '."""
        for value, _label in ranges.ALL_RANGES:
            out = ranges.rewrite(value, now=NOW)
            self.assertIsNotNone(out, value)
            since, until = out.split(ranges.SEPARATOR)
            for part in (since, until):
                dt.datetime.strptime(part, ranges.ISO)


class TestDescribe(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(ranges.describe("Current jalali month", NOW), "ماه جاری (شمسی)")
        self.assertEqual(ranges.describe("jalali:1403-12-20", NOW), "1403-12-20")
        self.assertEqual(ranges.describe("jalali:1403-12", NOW),
                         "1403-12-01 تا 1403-12-30")
        self.assertEqual(ranges.describe("Last week", NOW), "Last week")

    def test_every_shortcut_has_a_persian_label(self):
        for value, label in ranges.ALL_RANGES:
            self.assertEqual(ranges.describe(value, NOW), label, value)
            self.assertFalse(label.isascii(), f"{value} has no Persian label")


class TestCoverage(unittest.TestCase):
    """The vocabulary should cover every period the grains do, so that a chart
    grouped by Jalali quarter can also be filtered by one."""

    def test_units(self):
        for unit in ("week", "month", "quarter", "year"):
            self.assertIsNotNone(resolved(f"Current jalali {unit}"), unit)
            self.assertIsNotNone(resolved(f"previous jalali {unit}"), unit)
            self.assertIsNotNone(resolved(f"Last jalali {unit}"), unit)
        self.assertEqual(set(core.PERIOD_STARTS),
                         {"day", "week", "month", "quarter", "half", "year"})

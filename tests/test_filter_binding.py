"""Does a Jalali time range actually filter a chart, and to the right dates?

This is an integration check against a *running* Superset, because what it
verifies is Superset's own contract, not our code: the time filter is applied
only to a query that has a temporal column (superset/models/helpers.py passes
`granularity` to get_sqla_query, and "if None, time_filters not applied"). A
chart that plots the jalali_date text column has no temporal column of its own,
so without `granularity_sqla` the dashboard's Jalali date filter would silently
do nothing to it - which is exactly why superset/bootstrap.py and
bootstrap_traffic.py put it on every chart.

    docker compose exec superset bash -lc \
      'SUPERSET_URL=http://localhost:8088 /app/.venv/bin/python -m unittest \
       tests.test_filter_binding -v'

Skipped unless SUPERSET_URL is set, so the offline suite is unaffected.
"""

import datetime as dt
import json
import os
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "superset"))

from jalali_calendar import core, ranges  # noqa: E402

URL = os.environ.get("SUPERSET_URL")
USERNAME = os.environ.get("SUPERSET_USERNAME", "admin")
PASSWORD = os.environ.get("SUPERSET_PASSWORD", "admin")
# a dataset with a date column; the demo's mock sales table by default
DATASET = os.environ.get("JALALI_TEST_DATASET", "sales")
TIME_COL = os.environ.get("JALALI_TEST_TIME_COL", "sale_date")


@unittest.skipUnless(URL, "set SUPERSET_URL to check the filter against a live Superset")
class TestFilterBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import requests  # pylint: disable=import-outside-toplevel
        except ImportError as ex:  # pragma: no cover
            raise unittest.SkipTest(f"requests not installed: {ex}")
        cls.session = requests.Session()
        login = cls.session.post(f"{URL}/api/v1/security/login", json={
            "username": USERNAME, "password": PASSWORD, "provider": "db",
            "refresh": True})
        if login.status_code != 200:
            raise unittest.SkipTest(f"cannot log in to {URL}: {login.status_code}")
        cls.session.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        cls.session.headers["X-CSRFToken"] = cls.session.get(
            f"{URL}/api/v1/security/csrf_token/").json()["result"]
        cls.session.headers["Referer"] = URL
        # the FAB views (/api/v1/time_range/) authenticate with the session
        # cookie the browser gets, not the JWT, so log in both ways
        cls.browser = requests.Session()
        page = cls.browser.get(f"{URL}/login/")
        csrf = re.search(r'csrf_token"[^>]*value="([^"]+)"', page.text)
        if csrf:
            cls.browser.post(f"{URL}/login/", data={
                "username": USERNAME, "password": PASSWORD,
                "csrf_token": csrf.group(1)})
        query = json.dumps({"filters": [
            {"col": "table_name", "opr": "eq", "value": DATASET}]})
        found = cls.session.get(f"{URL}/api/v1/dataset/?q={query}").json()["result"]
        if not found:
            raise unittest.SkipTest(f"dataset {DATASET!r} not found on {URL}")
        cls.dataset_id = found[0]["id"]

    COUNT = {"expressionType": "SIMPLE", "label": "rows", "aggregate": "COUNT",
             "column": {"column_name": "id", "type": "BIGINT"}}

    def chart_data(self, **query):
        """Run one query the way a dashboard would and return (rows, WHERE clause)."""
        payload = {"datasource": {"id": self.dataset_id, "type": "table"},
                   "result_format": "json", "result_type": "full",
                   "queries": [{"metrics": [self.COUNT], "orderby": [],
                                "row_limit": 1000, **query}]}
        response = self.session.post(f"{URL}/api/v1/chart/data", json=payload)
        self.assertEqual(response.status_code, 200, response.text[:400])
        result = response.json()["result"][0]
        sql = " ".join(result["query"].split())
        where = re.search(r"WHERE (.*?)(?:GROUP BY|ORDER BY|LIMIT|$)", sql)
        return len(result["data"]), (where.group(1).strip() if where else "")

    def test_a_time_range_without_a_temporal_column_is_ignored(self):
        """The trap this test exists for."""
        _, where = self.chart_data(columns=[TIME_COL and "jalali_month"],
                                   time_range="jalali:1404-05")
        self.assertNotIn(TIME_COL, where,
                         "a time range was applied without a temporal column; "
                         "Superset changed behaviour and the granularity_sqla "
                         "workaround in bootstrap.py may be unnecessary")

    def test_a_jalali_range_filters_a_text_axis_chart(self):
        rows_all, where_all = self.chart_data(columns=["jalali_month"],
                                              granularity=TIME_COL)
        rows_month, where_month = self.chart_data(
            columns=["jalali_month"], granularity=TIME_COL,
            time_range="jalali:1404-05")
        self.assertEqual(where_all, "")
        self.assertIn(TIME_COL, where_month)
        self.assertLess(rows_month, rows_all)
        self.assertEqual(rows_month, 1, "Mordad 1404 is one Jalali month")

    def test_the_dates_are_the_converted_Jalali_ones(self):
        """The filter has to be the Gregorian translation of the Jalali range,
        to the day."""
        for expression in ["jalali:1404-05", "jalali:1403", "jalali:1403-q4",
                           "previous jalali year", "Current jalali month",
                           "jalali year to date"]:
            with self.subTest(expression):
                since, until = ranges.resolve(expression)
                _, where = self.chart_data(columns=["jalali_month"],
                                           granularity=TIME_COL,
                                           time_range=expression)
                self.assertIn(since.strftime("%Y-%m-%d"), where)
                self.assertIn(until.strftime("%Y-%m-%d"), where)

    def test_a_jalali_range_equals_its_gregorian_twin(self):
        """Same range, written both ways: identical SQL and identical rows."""
        expression = "previous jalali year"
        since, until = ranges.resolve(expression)
        gregorian = (f"{since.strftime('%Y-%m-%dT%H:%M:%S')} : "
                     f"{until.strftime('%Y-%m-%dT%H:%M:%S')}")
        self.assertEqual(self.chart_data(columns=["category"], granularity=TIME_COL,
                                         time_range=expression),
                         self.chart_data(columns=["category"], granularity=TIME_COL,
                                         time_range=gregorian))

    def test_a_chart_with_no_dimension_at_all_is_filtered(self):
        """A big-number chart has no x axis; the filter still has to reach it."""
        _, where = self.chart_data(columns=[], granularity=TIME_COL,
                                   time_range="jalali:1404-05")
        self.assertIn(TIME_COL, where)

    def test_the_demo_dashboard_is_wired_for_it(self):
        """Every chart the Jalali filter is scoped to must carry a temporal
        column, or the filter would be a no-op on it."""
        dashboard = self.session.get(f"{URL}/api/v1/dashboard/sales-fa")
        if dashboard.status_code != 200:
            self.skipTest("the sales-fa dashboard is not provisioned here")
        metadata = json.loads(dashboard.json()["result"]["json_metadata"])
        time_filters = [flt for flt in metadata.get("native_filter_configuration", [])
                        if flt["filterType"] == "filter_time"]
        self.assertTrue(time_filters, "no native time filter on the dashboard")
        scoped = set(time_filters[0]["chartsInScope"])
        self.assertTrue(scoped)
        default = time_filters[0]["defaultDataMask"]["filterState"]["value"]
        self.assertIsNotNone(ranges.resolve(default),
                             f"the filter's default {default!r} is not a Jalali range")
        charts = self.session.get(f"{URL}/api/v1/dashboard/sales-fa/charts").json()
        for chart in charts["result"]:
            form_data = chart.get("form_data") or {}
            if isinstance(form_data, str):
                form_data = json.loads(form_data)
            if chart.get("slice_id") in scoped or chart.get("id") in scoped:
                self.assertTrue(form_data.get("granularity_sqla"),
                                f"{chart.get('slice_name')} is in the filter's scope "
                                "but has no time column")

    def test_the_resolved_range_is_what_the_calendar_says(self):
        """Belt and braces: the API's own answer for a Jalali range must match
        the calendar in this repo."""
        for expression in ["jalali:1403-12", "Current jalali year",
                           "previous jalali quarter"]:
            with self.subTest(expression):
                response = self.browser.get(f"{URL}/api/v1/time_range/",
                                            params={"q": f"'{expression}'"})
                if response.status_code != 200:
                    self.skipTest(f"/api/v1/time_range/ -> {response.status_code}")
                item = response.json()["result"][0]
                since, until = ranges.resolve(expression)
                self.assertEqual(item["since"], since.isoformat())
                self.assertEqual(item["until"], until.isoformat())
                # and the Jalali rendering of those dates round-trips
                self.assertEqual(
                    core.to_jalali(dt.datetime.fromisoformat(item["since"])),
                    core.to_jalali(since))

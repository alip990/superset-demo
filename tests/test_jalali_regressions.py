"""Independent expected boundaries and regression tests for the backend adapter."""
import datetime as dt
import importlib
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'superset'))
from jalali_calendar import ranges, jinja, grains
from jalali_calendar.timezone import CalendarClock

adapter = importlib.import_module('jalali_calendar.install')
UTC = dt.timezone.utc

class TestRangeRegressions(unittest.TestCase):
    def test_bare_literals_false_applies_to_whole_range_and_endpoints(self):
        for value in ('1403', '1403-12', '۱۴۰۳/۱۲/۲۰', '1403-12-20 : 1404-01-01'):
            self.assertIsNone(ranges.rewrite(value, bare_literals=False))
        self.assertEqual(ranges.rewrite('jalali:1404-01-01', bare_literals=False),
                         '2025-03-21T00:00:00 : 2025-03-22T00:00:00')

    def test_explicit_invalid_and_reversed_inputs_fail(self):
        for value in ('jalali:1404-12-30', 'jalali:1404-01-01 25:00',
                      'jalali:1404-01-01 12:99', 'jalali:1404-01-02 : jalali:1404-01-01'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ranges.rewrite(value)

    def test_tehran_nowruz_serializes_utc_half_open(self):
        clock = CalendarClock('UTC', 'Asia/Tehran')
        self.assertEqual(ranges.rewrite('jalali:1404-01-01', clock=clock),
                         '2025-03-20T20:30:00 : 2025-03-21T20:30:00')

    def test_legacy_fixed_offset_is_subtracted_from_filter(self):
        self.assertEqual(ranges.rewrite('jalali:1404-01-01', clock=CalendarClock(shift_minutes=210)),
                         '2025-03-20T20:30:00 : 2025-03-21T20:30:00')

    def test_historical_tehran_dst_is_not_fixed_0330(self):
        self.assertEqual(ranges.rewrite('jalali:1400-04-10', clock=CalendarClock('UTC')),
                         '2021-06-30T19:30:00 : 2021-07-01T19:30:00')

    def test_business_date_rolls_before_utc_midnight(self):
        clock = CalendarClock('UTC')
        before = ranges.rewrite('Current jalali day', now=dt.datetime(2025, 3, 20, 20, 29, 59, tzinfo=UTC), clock=clock)
        after = ranges.rewrite('Current jalali day', now=dt.datetime(2025, 3, 20, 20, 30, tzinfo=UTC), clock=clock)
        self.assertEqual(before, '2025-03-19T20:30:00 : 2025-03-20T20:30:00')
        self.assertEqual(after, '2025-03-20T20:30:00 : 2025-03-21T20:30:00')

    def test_timezone_gap_and_fold_do_not_silently_normalize_typed_time(self):
        clock = CalendarClock('UTC', 'America/New_York')
        for value in (dt.datetime(2025, 3, 9, 2, 30), dt.datetime(2025, 11, 2, 1, 30)):
            with self.assertRaises(ValueError):
                clock.to_storage(value)

    def test_midnight_dst_calendar_boundary_uses_first_valid_instant(self):
        clock = CalendarClock('UTC')
        self.assertEqual(clock.to_storage(dt.datetime(2021, 3, 22), boundary=True),
                         dt.datetime(2021, 3, 21, 20, 30))

    def test_jinja_cache_key_changes_at_business_midnight(self):
        class Cache:
            def __init__(self): self.keys = []
            def cache_key_wrapper(self, key): self.keys.append(key)
        cache = Cache()
        for now in (dt.datetime(2025, 3, 20, 23, 59), dt.datetime(2025, 3, 21)):
            clock = CalendarClock('UTC')
            with patch('jalali_calendar.jinja.timezone.current', return_value=clock), \
                 patch.object(CalendarClock, 'now', return_value=now):
                jinja.jalali_filter(cache, 'occurred_at', 'Current jalali day')
        self.assertNotEqual(cache.keys[0], cache.keys[1])
        self.assertIn('2025-03-20 20:30:00', cache.keys[1])

    def test_utc_storage_grains_only_advertise_verified_postgres(self):
        expressions = grains.time_grain_addon_expressions(business_timezone='Asia/Tehran')
        self.assertEqual(set(expressions), {'postgresql'})
        self.assertEqual(set(expressions['postgresql']), set(grains.GRAIN_LABELS))
        with self.assertRaises(ValueError):
            grains.grain_expression('sqlite', 'JALALI_MONTH', business_timezone='Asia/Tehran')

class TestInitialization(unittest.TestCase):
    def test_publishing_does_not_destroy_config(self):
        original = {'shift_minutes': 210, 'override_smart_date': False,
                    'grain_mode': 'function', 'bare_literals': False}
        app = types.SimpleNamespace(config={adapter.OPTIONS_KEY: dict(original)})
        for _ in range(2):
            with patch.dict(sys.modules, {'superset.views': types.SimpleNamespace(
                    base=types.SimpleNamespace(FRONTEND_CONF_KEYS=()))}):
                adapter._expose_options(app, adapter.options(app))
        self.assertEqual(app.config[adapter.OPTIONS_KEY], original)
        self.assertEqual(adapter.options(app)['shift_minutes'], 210)
        self.assertFalse(adapter.options(app)['bare_literals'])

    def test_incompatible_host_fails_clearly(self):
        app = types.SimpleNamespace(config={})
        with patch.object(adapter, 'version', return_value='7.0.0'), self.assertRaisesRegex(RuntimeError, '7.0.0'):
            adapter.install(app)

    def test_disabled_does_not_install_adapters(self):
        app = types.SimpleNamespace(config={adapter.OPTIONS_KEY: {'enabled': False}})
        with patch.object(adapter, 'version', return_value='6.1.0'), patch.object(adapter, '_patch_date_parser') as parser:
            self.assertFalse(adapter.install(app)['enabled'])
            parser.assert_not_called()

    def test_conflicting_clock_config_is_rejected(self):
        with self.assertRaises(ValueError):
            CalendarClock('UTC', 'Asia/Tehran', 210)

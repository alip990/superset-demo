"""Wire Jalali support into a running Superset 6.1.0, from superset_config.py::

    def FLASK_APP_MUTATOR(app):
        import jalali_calendar
        jalali_calendar.install(app)

Nothing here forks Superset: the four integration points are the two config keys
Superset already reads for extra time grains, one wrapper around the time-range
parser, and the Jinja context. The frontend half of the feature (formatters and
the date picker) lives in plugins/superset-jalali and reads the options this
module publishes to the browser.

    TIME_GRAIN_ADDONS / TIME_GRAIN_ADDON_EXPRESSIONS
        "ماه شمسی" and friends in every chart's Time grain menu, as inline SQL
        for 21 engines (grains.py).

    get_since_until()
        teaches the whole product - explore, dashboards, alerts, reports, CSV
        export, embedded guest sessions - the Jalali time-range vocabulary
        (ranges.py). Wrapped, not replaced: a Jalali expression is rewritten to
        the ISO "since : until" string Superset already understands, everything
        else is passed through untouched.

    ExtraCache + JinjaTemplateProcessor.set_context
        the dataset macros (jinja.py), registered the way
        superset/guest_user_attributes.py registers its own, so that a macro
        whose value changes with the date also changes the query cache key.

    FRONTEND_CONF_KEYS
        publishes JALALI_CALENDAR_OPTIONS in the bootstrap payload, so the
        picker's shortcut list, digits and timezone shift come from this config
        instead of being hard-coded in the frontend bundle.

install() is idempotent for the pinned host process. It raises on an unsupported
Superset release or contradictory calendar configuration instead of silently
installing a partial adapter.
"""

from __future__ import annotations

import functools
import logging
import re
import sys
from importlib.metadata import version
from typing import Any

from . import core, grains, jinja, ranges, timezone

logger = logging.getLogger(__name__)

OPTIONS_KEY = "JALALI_CALENDAR_OPTIONS"
FRONTEND_OPTIONS_KEY = "JALALI_CALENDAR_FRONTEND_OPTIONS"
SUPPORTED_SUPERSET = ('6.1.0',)

DEFAULT_OPTIONS: dict[str, Any] = {
    # master switch read by the frontend plugin; False leaves Superset Gregorian
    "enabled": True,
    # "latin" (1403-12-20) or "persian" (۱۴۰۳-۱۲-۲۰) digits in every label
    "digits": "latin",
    # replace Superset's own adaptive/verbose formatters, so existing charts
    # become Jalali without being edited
    "override_smart_date": True,
    # minutes to add to a timestamp before deciding which Jalali day it is: 0
    # when the database stores local time (this repo's occurred_at does), 210
    # for UTC data read by an Asia/Tehran business
    "shift_minutes": 0,
    "storage_timezone": "wall",
    "business_timezone": "Asia/Tehran",
    # accept "1403-12-20" as a Jalali date without the "jalali:" prefix
    "bare_literals": True,
    # "inline" needs nothing installed in the database; "function" uses the
    # IMMUTABLE functions from db/02-jalali.sql (shorter SQL, indexable)
    "grain_mode": "inline",
    "grains": tuple(grains.GRAIN_LABELS),
    "grain_labels": dict(grains.GRAIN_LABELS),
    # Friday is the Iranian weekend; set True where Thursday is too
    "thursday_is_weekend": False,
}


def options(app: Any = None) -> dict[str, Any]:
    """Defaults merged with the JALALI_CALENDAR_OPTIONS dict from the config.

    Publishing browser options must never overwrite this configuration."""
    merged = dict(DEFAULT_OPTIONS)
    config = (app.config.get(OPTIONS_KEY) or {}) if app is not None else {}
    unknown = [key for key in config if key not in DEFAULT_OPTIONS]
    known = {key: value for key, value in config.items() if key in DEFAULT_OPTIONS}
    if unknown and not all(key in _PUBLISHED_KEYS for key in unknown):
        logger.warning("jalali: ignoring unknown %s keys: %s", OPTIONS_KEY,
                       ", ".join(sorted(set(unknown) - _PUBLISHED_KEYS)))
    merged.update(known)
    timezone.from_options(merged)  # fail early on contradictory timezone settings
    return merged


# the camelCase keys the browser gets; recognised here only so that a second
# install() in the same process does not warn about its own payload
_PUBLISHED_KEYS = frozenset({
    "enabled", "digits", "overrideSmartDate", "shiftMinutes", "thursdayIsWeekend",
    "monthNames", "weekdayNames", "seasonNames", "formats", "ranges",
})


def _published_options(opts: dict[str, Any]) -> dict[str, Any]:
    """What the browser needs: the knobs plus the vocabulary, so the picker's
    option lists and the server-side parser can never disagree."""
    return {
        "enabled": opts["enabled"],
        "digits": opts["digits"],
        "overrideSmartDate": opts["override_smart_date"],
        "shiftMinutes": opts["shift_minutes"],
        "storageTimezone": opts["storage_timezone"],
        "businessTimezone": opts["business_timezone"],
        "thursdayIsWeekend": opts["thursday_is_weekend"],
        "monthNames": list(core.MONTH_NAMES),
        "weekdayNames": list(core.WEEKDAY_NAMES),
        "seasonNames": list(core.SEASON_NAMES),
        "formats": dict(core.NAMED_FORMATS),
        "ranges": {
            "common": [list(item) for item in ranges.COMMON_RANGES],
            "calendar": [list(item) for item in ranges.CALENDAR_RANGES],
            "current": [list(item) for item in ranges.CURRENT_RANGES],
        },
    }


# ------------------------------------------------------------- time grains ---
def _configure_grains(app: Any, opts: dict[str, Any]) -> int:
    labels = {
        grain: opts["grain_labels"].get(grain, grains.GRAIN_LABELS[grain])
        for grain in opts["grains"]
    }
    expressions = grains.time_grain_addon_expressions(
        tuple(opts["grains"]), opts["shift_minutes"], opts["grain_mode"],
        business_timezone=(opts['business_timezone'] if opts['storage_timezone'] == 'UTC' else None),
    )
    addons = dict(app.config.get("TIME_GRAIN_ADDONS") or {})
    addons.update(labels)
    app.config["TIME_GRAIN_ADDONS"] = addons
    merged = {
        engine: {**(app.config.get("TIME_GRAIN_ADDON_EXPRESSIONS") or {}).get(engine, {}),
                 **grain_sql}
        for engine, grain_sql in expressions.items()
    }
    for engine, grain_sql in (app.config.get("TIME_GRAIN_ADDON_EXPRESSIONS") or {}).items():
        merged.setdefault(engine, grain_sql)
    app.config["TIME_GRAIN_ADDON_EXPRESSIONS"] = merged
    return len(labels)


# -------------------------------------------------------- time-range parser --
def _patch_date_parser(opts: dict[str, Any]) -> bool:
    """Wrap get_since_until() and rebind it in every module that already
    imported it by name (``from ... import get_since_until`` copies the
    reference, so patching only the defining module would miss the query path)."""
    from superset.utils import date_parser  # pylint: disable=import-outside-toplevel

    original = date_parser.get_since_until
    if getattr(original, "_jalali_patched", False):
        return True

    @functools.wraps(original)
    def get_since_until(  # pylint: disable=too-many-arguments
        time_range: str | None = None,
        since: str | None = None,
        until: str | None = None,
        time_shift: str | None = None,
        relative_start: str | None = None,
        relative_end: str | None = None,
        **kwargs: Any,
    ) -> Any:
        from flask import current_app
        active = options(current_app)
        if active['enabled']:
            rewritten = ranges.rewrite(
                time_range, relative_start, relative_end, active['bare_literals'],
                clock=timezone.from_options(active),
            )
        else:
            rewritten = None
        if rewritten is not None:
            logger.debug("jalali: %r -> %r", time_range, rewritten)
            time_range = rewritten
        return original(
            time_range=time_range,
            since=since,
            until=until,
            time_shift=time_shift,
            relative_start=relative_start,
            relative_end=relative_end,
            **kwargs,
        )

    get_since_until._jalali_patched = True  # type: ignore[attr-defined]
    get_since_until._jalali_original = original  # type: ignore[attr-defined]

    patched_modules = 0
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, "get_since_until", None) is original:
                setattr(module, "get_since_until", get_since_until)
                patched_modules += 1
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001, S112
            continue
    logger.debug("jalali: get_since_until rebound in %d modules", patched_modules)
    return patched_modules > 0


# ----------------------------------------------------------- Jinja macros ----
def _patch_extra_cache() -> int:
    """Add the macros to ExtraCache and make the cache-key regex see the ones
    whose value depends on the date."""
    from superset.jinja_context import ExtraCache  # pylint: disable=import-outside-toplevel

    added = 0
    for name, func in jinja.MACROS.items():
        if not hasattr(ExtraCache, name):
            setattr(ExtraCache, name, func)
            added += 1

    pattern = ExtraCache.regex.pattern
    missing = [name for name in jinja.CACHE_KEY_MACROS
               if f"{name}\\(" not in pattern]
    if missing:
        anchor = r"url_param\([^)]*\)"
        if anchor not in pattern:
            logger.warning(
                "jalali: ExtraCache.regex has an unexpected shape; the date "
                "macros will not reach the query cache key. Set "
                "DATA_CACHE_CONFIG to NullCache or pin Superset 6.1.0."
            )
        else:
            addition = "|".join(f"{name}\\([^)]*\\)" for name in missing)
            ExtraCache.regex = re.compile(
                pattern.replace(anchor, f"{anchor}|{addition}", 1)
            )
    return added


def _patch_template_processor() -> bool:
    """Expose the macros in the Jinja context, bound to the ExtraCache instance
    Superset built for this request - the one whose cache_key_wrapper() feeds
    the query's cache key."""
    from superset import jinja_context  # pylint: disable=import-outside-toplevel

    processor = jinja_context.JinjaTemplateProcessor
    if getattr(processor.set_context, "_jalali_patched", False):
        return True
    original_set_context = processor.set_context

    def set_context(self: Any, **kwargs: Any) -> None:
        original_set_context(self, **kwargs)
        wrapper = self._context.get("cache_key_wrapper")  # noqa: SLF001
        bound = (getattr(wrapper, "args", None) or (None,))[0]
        extra_cache = getattr(bound, "__self__", None)
        if extra_cache is None:
            logger.warning("jalali: no ExtraCache in the Jinja context; the "
                           "date macros are not available in SQL")
            return
        for name in jinja.MACROS:
            method = getattr(extra_cache, name, None)
            if method is not None:
                self._context[name] = functools.partial(  # noqa: SLF001
                    jinja_context.safe_proxy, method
                )

    set_context._jalali_patched = True  # type: ignore[attr-defined]
    processor.set_context = set_context  # type: ignore[method-assign]
    return True


def _expose_options(app: Any, opts: dict[str, Any]) -> bool:
    """Publish the options in the bootstrap payload the browser receives."""
    app.config[FRONTEND_OPTIONS_KEY] = _published_options(opts)
    try:
        from superset.views import base  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001
        return False
    if FRONTEND_OPTIONS_KEY not in base.FRONTEND_CONF_KEYS:
        base.FRONTEND_CONF_KEYS = (*base.FRONTEND_CONF_KEYS, FRONTEND_OPTIONS_KEY)
    return True


def install(app: Any = None) -> dict[str, Any]:
    """Install everything and return what was done, for logs and tests."""
    if app is None:  # pragma: no cover - convenience for shells and tests
        from flask import current_app  # pylint: disable=import-outside-toplevel

        app = current_app
    opts = options(app)
    actual = version('apache-superset')
    if actual not in SUPPORTED_SUPERSET:
        raise RuntimeError(f'Jalali backend supports Superset {SUPPORTED_SUPERSET}; found {actual}')
    if not opts['enabled']:
        return {'enabled': False, 'options': opts}
    report = {
        "grains": _configure_grains(app, opts),
        "time_range_parser": _patch_date_parser(opts),
        "jinja_macros": _patch_extra_cache(),
        "jinja_context": _patch_template_processor(),
        "frontend_options": _expose_options(app, opts),
        "options": opts,
    }
    logger.info(
        "jalali_calendar: %d time grains, %d Jinja macros, time-range "
        "vocabulary %s, frontend options %s (digits=%s, shift=%smin, grains=%s)",
        report["grains"], report["jinja_macros"],
        "installed" if report["time_range_parser"] else "NOT installed",
        "published" if report["frontend_options"] else "NOT published",
        opts["digits"], opts["shift_minutes"], opts["grain_mode"],
    )
    return report

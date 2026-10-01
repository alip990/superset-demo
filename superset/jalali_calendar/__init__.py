"""Jalali (Persian) calendar support for Superset 6.1.0.

* ``core``    - calendar arithmetic, formatting and parsing (no dependencies)
* ``grains``  - "ماه شمسی" / "فصل شمسی" ... time grains as inline SQL per engine
* ``ranges``  - the Jalali time-range vocabulary used by the date picker
* ``jinja``   - dataset macros ({{ jalali_filter('occurred_at', ...) }})
* ``install`` - the four integration points, called from FLASK_APP_MUTATOR

See JALALI_CALENDAR.md for the whole picture, including the frontend half in
plugins/superset-jalali.
"""

from . import core, grains, jinja, ranges  # noqa: F401
from .install import DEFAULT_OPTIONS, install, options  # noqa: F401

__all__ = ["core", "grains", "jinja", "ranges", "install", "options",
           "DEFAULT_OPTIONS"]

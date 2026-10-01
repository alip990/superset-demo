import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-demo-secret-key-please-rotate")
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:postgres@db:5432/superset"

# ---- Cache / async (redis) ----
REDIS_URL = "redis://redis:6379"
CACHE_CONFIG = {"CACHE_TYPE": "RedisCache", "CACHE_DEFAULT_TIMEOUT": 300,
                "CACHE_KEY_PREFIX": "superset_", "CACHE_REDIS_URL": f"{REDIS_URL}/0"}
# Chart-data caching is back ON: guest_user_attributes.install() (see FLASK_APP_MUTATOR
# below) adds get_guest_user_attribute() to ExtraCache.regex, so the resolved attribute
# goes through cache_key_wrapper() and into the query's cache key. Without that patch
# this has to be NullCache - the tenant filter would be invisible to the cache key and
# one company would be served another company's cached results.
DATA_CACHE_CONFIG = {**CACHE_CONFIG, "CACHE_KEY_PREFIX": "superset_data_"}

# ---- Persian localisation ----
BABEL_DEFAULT_LOCALE = "fa"
LANGUAGES = {
    "fa": {"flag": "ir", "name": "فارسی"},
    "en": {"flag": "us", "name": "English"},
}

FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,          # iframe embedding with guest tokens
    "ENABLE_TEMPLATE_PROCESSING": True, # Jinja in SQL / RLS: {{ current_username() }}
    "DASHBOARD_RBAC": True,             # per-dashboard role access
    "ALERT_REPORTS": False,
    # read by plugins/superset-jalali when JALALI_CALENDAR_OPTIONS is absent;
    # see the Jalali section below. Only the frontend bundle looks at it.
    "JALALI_CALENDAR": True,
}

# ---- Our own map server (tileserver-gl, serving raster tiles rendered from
#      the OSM Iran extract via planetiler) as the deck.gl base map ----
# NOTE: Superset's deck.gl "mapbox_style" field only accepts
#   "mapbox://styles/..." (needs MAPBOX_API_KEY) or "tile://http(s)://..." (raster XYZ).
#   A bare MapLibre style.json URL fails Superset's own validation and silently
#   renders no basemap - use the tileserver's raster tile endpoint instead.
# MAP_TILE_URL may point at our own tileserver (default) or, when that isn't
# available (e.g. no network access to build tiles/iran.mbtiles), a public
# XYZ tile provider such as OpenStreetMap.
TILE_SERVER = os.environ.get("TILE_SERVER_PUBLIC_URL", "http://localhost:8081")
MAP_TILE_URL = os.environ.get(
    "MAP_TILE_URL", f"{TILE_SERVER}/styles/basic-preview/{{z}}/{{x}}/{{y}}.png"
)
DECKGL_BASE_MAP = [
    [f"tile://{MAP_TILE_URL}", "Map basemap"],
]
MAPBOX_API_KEY = ""

# ---- Embedding / guest tokens ----
GUEST_ROLE_NAME = "EmbedGuest"
GUEST_TOKEN_JWT_SECRET = os.environ.get("GUEST_TOKEN_JWT_SECRET", "demo-guest-token-secret")
GUEST_TOKEN_JWT_EXP_SECONDS = 600
ENABLE_CORS = True
CORS_OPTIONS = {"supports_credentials": True, "allow_headers": ["*"], "resources": ["*"],
                "origins": ["http://localhost:8090"]}
# demo only: no CSP so iframe + external tile server work; set a real CSP in production
TALISMAN_ENABLED = False
HTTP_HEADERS = {"X-Frame-Options": "ALLOWALL"}
SESSION_COOKIE_SAMESITE = "Lax"
WTF_CSRF_ENABLED = True

FAB_ADD_SECURITY_API = True  # /api/v1/security/roles, users ... for automation


# ---- Jalali (Persian) calendar (see JALALI_CALENDAR.md) ----
# superset/jalali_calendar/ adds, from this one hook:
#   * the time grains "ماه شمسی", "فصل شمسی", "هفته شمسی (شنبه)", "نیم‌سال شمسی"
#     and "سال شمسی" to every chart, as inline SQL for 21 engines - nothing has to
#     be installed in the database;
#   * the Jalali time-range vocabulary the date picker stores and the server
#     resolves ("ماه جاری (شمسی)", "از ابتدای سال تا امروز", "jalali:1403-12"),
#     which is what makes saved charts, alerts, reports and embedded dashboards
#     agree with the browser;
#   * dataset macros: {{ jalali_filter('occurred_at', 'Current jalali month') }},
#     {{ jalali_today() }}, {{ from_jalali('1403-12-20') }} ...
#   * these options in the bootstrap payload, for plugins/superset-jalali.
# Every key is optional; the defaults are in jalali_calendar/install.py.
JALALI_CALENDAR_OPTIONS = {
    "enabled": True,
    # "persian" shows ۱۴۰۳-۱۲-۲۰ everywhere instead of 1403-12-20
    "digits": "latin",
    # replace Superset's own "Adaptive formatting", so charts that never chose a
    # time format become Jalali without being edited
    "override_smart_date": True,
    # minutes added to a timestamp before deciding which Jalali day it is. 0 here:
    # bi.violation.occurred_at is already Tehran local time. Use 210 for data
    # stored in UTC (Asia/Tehran is UTC+3:30), or the day would break at 03:30.
    "shift_minutes": 0,
    # accept "1403-12-20" in the Advanced frame without the "jalali:" prefix; no
    # real data is from the 15th century, so this cannot swallow a Gregorian date
    "bare_literals": True,
    # "inline" = self-contained arithmetic (default, works everywhere);
    # "function" = the shorter, indexable jalali.*_start() functions from
    # db/jalali.sql, which the db container installs into the demo database
    "grain_mode": "inline",
}
# Makes every *new* chart open on the current Jalali month. Left off because the
# demo data only covers a few days of 1403-12 and 1404-01, so new charts would
# look empty:
# DEFAULT_TIME_FILTER = "Current jalali month"


# ---- Guest-token user attributes (see SUPERSET_RLS_GUIDE.md) ----
# apache/superset master lets a guest token carry `user.attributes` and reads them
# back in SQL templates via get_guest_user_attribute(); 6.1.0 ships neither, so
# guest_user_attributes.py backports both. Company scoping therefore travels as a
# real attribute - {"attributes": {"allowed_companies": [3, 4]}} - instead of being
# packed into the username, and it reaches the query cache key.
def FLASK_APP_MUTATOR(app):  # noqa: N802
    import jalali_calendar
    from guest_user_attributes import install

    install()
    jalali_calendar.install(app)

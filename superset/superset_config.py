import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-demo-secret-key-please-rotate")
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:postgres@db:5432/superset"

# ---- Cache / async (redis) ----
REDIS_URL = "redis://redis:6379"
CACHE_CONFIG = {"CACHE_TYPE": "RedisCache", "CACHE_DEFAULT_TIMEOUT": 300,
                "CACHE_KEY_PREFIX": "superset_", "CACHE_REDIS_URL": f"{REDIS_URL}/0"}
# Chart-data caching is OFF: the tenant filter comes from get_guest_user_attribute()
# (see below), which Superset does not include in its cache key - with a data cache,
# one company could be served another company's cached results.
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}

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
    # custom flag read by plugins/superset-jalali: Superset's default ("Adaptive")
    # time formatting shows Jalali dates in every chart. Needs the image built from
    # superset/Dockerfile; the stock image ignores it.
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


# ---- Company-tree tenancy for embedded dashboards (see SUPERSET_RLS_GUIDE.md) ----
# Superset 6.1 drops user.attributes from guest-token requests, so the host app
# packs the allowed company ids into the username: "<app user>|<id>, <id>, ...".
def get_guest_user_attribute(attribute_name, default=None):
    """Polyfill for SIP-174's get_guest_user_attribute Jinja macro."""
    from flask import g

    if hasattr(g, "user") and hasattr(g.user, "guest_token"):
        user_payload = g.user.guest_token.get("user", {})

        # 1. native attributes, for Superset versions that keep them
        attributes = user_payload.get("attributes") or {}
        if attribute_name in attributes:
            return attributes[attribute_name]

        # 2. fallback: unpack the ids packed into the username
        username = user_payload.get("username", "")
        if "|" in username and attribute_name == "allowed_companies":
            return username.split("|", 1)[1].strip()

    return default


JINJA_CONTEXT_ADDONS = {"get_guest_user_attribute": get_guest_user_attribute}


# ---- Jalali time grains: "Jalali month" / "Jalali year" in every chart's Time grain ----
# Grouping has to happen in the database, so the frontend formatter alone can't do it.
# Each bucket starts on the Gregorian timestamp of the 1st of the Jalali month/year,
# which the Jalali formatter then shows as e.g. "اسفند" / "1404".
# Uses bi.to_jalali() from backups/02-bi.sql, so it only works on databases that have
# that function (our CrimeManagementDb). Other engines (Trino, ClickHouse...) need their
# own expressions - see JALALI_CALENDAR.md.
_JALALI = "bi.to_jalali(({col})::date)"
_JALALI_MONTH = f"split_part({_JALALI}, '-', 2)::int"
_JALALI_DAY = f"split_part({_JALALI}, '-', 3)::int"
TIME_GRAIN_ADDONS = {"JALALI_MONTH": "Jalali month", "JALALI_YEAR": "Jalali year"}
TIME_GRAIN_ADDON_EXPRESSIONS = {
    "postgresql": {
        # date minus (day of the Jalali month - 1)
        "JALALI_MONTH": f"(({{col}})::date - ({_JALALI_DAY} - 1))::timestamp",
        # date minus (day of the Jalali year - 1): months 1-6 have 31 days, 7-11 have 30
        "JALALI_YEAR": f"(({{col}})::date - (CASE WHEN {_JALALI_MONTH} <= 6"
                       f" THEN ({_JALALI_MONTH} - 1) * 31 ELSE 186 + ({_JALALI_MONTH} - 7) * 30 END"
                       f" + {_JALALI_DAY} - 1))::timestamp",
    }
}

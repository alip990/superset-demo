import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-demo-secret-key-please-rotate")
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:postgres@db:5432/superset"

# ---- Cache / async (redis) ----
REDIS_URL = "redis://redis:6379"
CACHE_CONFIG = {"CACHE_TYPE": "RedisCache", "CACHE_DEFAULT_TIMEOUT": 300,
                "CACHE_KEY_PREFIX": "superset_", "CACHE_REDIS_URL": f"{REDIS_URL}/0"}
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
}

# ---- Our own map server (tileserver-gl, serving raster tiles rendered from
#      the OSM Iran extract via planetiler) as the deck.gl base map ----
# NOTE: Superset's deck.gl "mapbox_style" field only accepts
#   "mapbox://styles/..." (needs MAPBOX_API_KEY) or "tile://http(s)://..." (raster XYZ).
#   A bare MapLibre style.json URL fails Superset's own validation and silently
#   renders no basemap - use the tileserver's raster tile endpoint instead.
TILE_SERVER = os.environ.get("TILE_SERVER_PUBLIC_URL", "http://localhost:8081")
DECKGL_BASE_MAP = [
    [f"tile://{TILE_SERVER}/styles/basic-preview/{{z}}/{{x}}/{{y}}.png", "Own map server (Iran, basic)"],
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

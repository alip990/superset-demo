import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-demo-secret-key-please-rotate")
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://postgres:postgres@db:5432/superset"

REDIS_URL = "redis://redis:6379"
CACHE_CONFIG = {"CACHE_TYPE": "RedisCache", "CACHE_DEFAULT_TIMEOUT": 300,
                "CACHE_KEY_PREFIX": "superset_", "CACHE_REDIS_URL": f"{REDIS_URL}/0"}
# Guest company scope is not part of Superset's data-cache key.
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}

BABEL_DEFAULT_LOCALE = "fa"
LANGUAGES = {
    "fa": {"flag": "ir", "name": "فارسی"},
    "en": {"flag": "us", "name": "English"},
}

FEATURE_FLAGS = {
    "EMBEDDED_SUPERSET": True,
    "ENABLE_TEMPLATE_PROCESSING": True,
}

GUEST_ROLE_NAME = "EmbedGuest"
GUEST_TOKEN_JWT_SECRET = os.environ.get("GUEST_TOKEN_JWT_SECRET", "demo-guest-token-secret")
GUEST_TOKEN_JWT_EXP_SECONDS = 600
ENABLE_CORS = True
CORS_OPTIONS = {"supports_credentials": True, "allow_headers": ["*"], "resources": ["*"],
                "origins": ["http://localhost:8090"]}
TALISMAN_ENABLED = False
HTTP_HEADERS = {"X-Frame-Options": "ALLOWALL"}
FAB_ADD_SECURITY_API = True

# Superset 6.1 drops guest user.attributes, so the host packs company ids into the username.
def get_guest_user_attribute(attribute_name, default=None):
    from flask import g

    if hasattr(g, "user") and hasattr(g.user, "guest_token"):
        user_payload = g.user.guest_token.get("user", {})
        attributes = user_payload.get("attributes") or {}
        if attribute_name in attributes:
            return attributes[attribute_name]
        username = user_payload.get("username", "")
        if "|" in username and attribute_name == "allowed_companies":
            return username.split("|", 1)[1].strip()
    return default


from superset_jalali_sql import JINJA_ADDONS

JINJA_CONTEXT_ADDONS = {**JINJA_ADDONS, "get_guest_user_attribute": get_guest_user_attribute}
JALALI_SQL = {"dialect": "postgresql", "digits": "latin", "min_year": 1390, "max_year": 1420}

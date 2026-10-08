"""Local acceptance lab ONLY. All listeners are bound to host loopback."""
import os
from pathlib import Path
import sys

SECRET_KEY = os.environ['LAB_SECRET_KEY']
SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://lab:lab-only@db:5432/lab'
FEATURE_FLAGS = {'ENABLE_EXTENSIONS': True, 'EMBEDDED_SUPERSET': True,
                 'ENABLE_TEMPLATE_PROCESSING': True}
EXTENSIONS_PATH = '/extensions'
WTF_CSRF_ENABLED = True
TALISMAN_ENABLED = True
TALISMAN_CONFIG = {'force_https': False, 'content_security_policy': {
    'default-src': ["'self'"], 'img-src': ["'self'", 'blob:', 'data:'],
    'style-src': ["'self'", "'unsafe-inline'"], 'script-src': ["'self'", "'strict-dynamic'"],
    'worker-src': ["'self'", 'blob:'], 'connect-src': ["'self'"],
}, 'content_security_policy_nonce_in': ['script-src']}
SESSION_COOKIE_SECURE = False  # isolated HTTP localhost only
GUEST_TOKEN_JWT_SECRET = os.environ['LAB_SECRET_KEY']
GUEST_ROLE_NAME = 'Gamma'
JALALI_CALENDAR_OPTIONS = {
    'enabled': True, 'storage_timezone': 'UTC', 'business_timezone': 'Asia/Tehran',
    'digits': 'persian', 'bare_literals': False,
}

def FLASK_APP_MUTATOR(app):
    if os.environ.get('JALALI_BACKEND_ENABLED') == '1':
        wheels = list(Path('/calendar').glob('superset_jalali_backend-*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('Expected exactly one active Jalali backend wheel')
        sys.path.insert(0, str(wheels[0]))
        from jalali_calendar import install
        install(app)

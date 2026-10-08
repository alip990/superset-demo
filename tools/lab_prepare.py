#!/usr/bin/env python3
"""Create isolated lab state. Secrets stay in ignored files with mode 0600."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
state = root / 'deployment/independent/.state'
state.mkdir(parents=True, exist_ok=True)
env = state / 'lab.env'
if not env.exists():
    env.touch(mode=0o600)
    env.write_text(f'LAB_SECRET_KEY={secrets.token_urlsafe(48)}\n'
                   f'LAB_ADMIN_PASSWORD={secrets.token_urlsafe(24)}\n'
                   'JALALI_BACKEND_ENABLED=0\n')
for name in ('active', 'backend-active', 'archive'):
    (root / 'dist' / name).mkdir(parents=True, exist_ok=True)
print('Local lab prepared; existing secrets preserved.')

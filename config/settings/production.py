"""Pengaturan untuk environment production.

Strategi:
- Security headers selalu aktif (XSS filter, content-type, X-Frame-Options).
- Cookie & SSL redirect HANYA aktif saat USE_HTTPS=True di .env, supaya
  initial deploy via HTTP (sebelum certbot) tetap bisa login.
- Setelah Let's Encrypt aktif, set USE_HTTPS=True dan restart Gunicorn.
"""
import os

from .base import *  # noqa: F401, F403

DEBUG = False

# Header keamanan yang tidak bergantung HTTPS (selalu aktif)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Toggle HTTPS dari .env. Default False supaya HTTP-only deploy tidak break.
USE_HTTPS = os.environ.get('USE_HTTPS', 'False').lower() == 'true'

SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE = USE_HTTPS

if USE_HTTPS:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 tahun
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF trusted origins — wajib untuk POST form di production.
# Format: http://IP atau https://domain (pisahkan koma di .env).
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost,http://127.0.0.1',
    ).split(',') if o.strip()
]

# --- Database connection pooling -----------------------------------------
# Setiap request HTTP normalnya membuka & menutup koneksi DB baru. Saat
# load tinggi (200 user serentak) overhead handshake PostgreSQL jadi
# bottleneck. CONN_MAX_AGE mempersist koneksi selama 60 detik antar request
# di worker yang sama → handshake hanya sekali per menit.
# CONN_HEALTH_CHECKS memastikan koneksi yang di-reuse masih hidup
# (PostgreSQL kadang tutup koneksi idle dari sisi server).
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

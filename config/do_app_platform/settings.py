from django.core.management.utils import get_random_secret_key
from pathlib import Path
import os
import sys
import dj_database_url

from config.dev.settings import *

# Production overrides for AWS credentials (use environment variables instead of .env file)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

# All other AWS/storage settings inherited from dev settings

WSGI_APPLICATION = "config.do_app_platform.app.application"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", None)

DEBUG = True

ALLOWED_HOSTS = [
    "overslotbaseball.com",
    "www.overslotbaseball.com", 
    "overslot-prod-wxrbl.ondigitalocean.app",
]

DEVELOPMENT_MODE = True

DATABASE_URL = os.environ.get("DATABASE_URL", None)

DATABASES = {
    "default": dj_database_url.parse(DATABASE_URL),
}

# Session settings for multi-pod deployment
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400 * 30  # 30 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True  # HTTPS only
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_DOMAIN = '.overslotbaseball.com'  # Works for www.overslotbaseball.com and overslotbaseball.com
SESSION_SAVE_EVERY_REQUEST = False  # Only save when session is modified
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Security settings for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Static and media files settings inherited from dev 
# (Both use DigitalOcean Spaces)

# Production-specific CORS settings
CORS_ALLOWED_ORIGINS = [
    "https://the-over-slot.nyc3.cdn.digitaloceanspaces.com",
    "https://overslot-prod-wxrbl.ondigitalocean.app",
    "https://overslotbaseball.com",
    "https://www.overslotbaseball.com",
]

CORS_ALLOW_ALL_ORIGINS = False

# Allow specific headers for CORS
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Update CSRF trusted origins for production
CSRF_TRUSTED_ORIGINS = [
    "https://overslot-prod-wxrbl.ondigitalocean.app",
    "https://overslotbaseball.com",
    "https://www.overslotbaseball.com",
    "https://the-over-slot.nyc3.cdn.digitaloceanspaces.com",
]

# Cache configuration - use database for simplicity in multi-pod setup
# For better performance, consider Redis or Memcached in the future
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'cache_table',
    }
}

# CSRF settings for multi-pod deployment
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_DOMAIN = '.overslotbaseball.com'  # Match session cookie domain

# Production-specific settings
DEBUG = False  # Turn off debug in production
DEVELOPMENT_MODE = False

# Email settings for production
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY', None)
MAILGUN_DOMAIN = os.environ.get('MAILGUN_DOMAIN', 'overslotbaseball.com')

# Email blocklist to reduce spam signups/logins (override/extend dev defaults if needed)
BLOCKED_EMAIL_TLDS = [
    "ru",
    "su",
    "cn",
]
BLOCKED_EMAIL_DOMAINS = [
    # Common disposable providers
    "mailinator.com",
    "10minutemail.com",
    "guerrillamail.com",
    "guerrillamail.de",
    "guerrillamail.biz",
    "guerrillamail.info",
    "sharklasers.com",
    "trashmail.com",
    "trash-mail.com",
    "temp-mail.org",
    "tempmail.plus",
    "tempmail.email",
    "tempmailo.com",
    "yopmail.com",
    "dispostable.com",
    "getnada.com",
    "nada.ltd",
    "dropmail.me",
    "1secmail.com",
    "mytemp.email",
    "mintemail.com",
    "maildrop.cc",
    "fakeinbox.com",
    "mailcatch.com",
    "mailnesia.com",
    "moakt.com",
    "emailondeck.com",
    "throwawaymail.com",
    "mailpoof.com",
    "getairmail.com",
    "disposablemail.com",
    "mail7.io",
    "mailsac.com",
    "linshi-email.com",
    "mail-temp.com",
    "mail.tm",
    "inboxbear.com",
    "mvrht.com",
    "kurzepost.de",
    "spamgourmet.com",
    "generator.email",
]

# Email backend configuration for production
if MAILGUN_API_KEY and MAILGUN_DOMAIN:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # Use actual email in production
    DEFAULT_FROM_EMAIL = f'Over Slot <noreply@{MAILGUN_DOMAIN}>'
    SERVER_EMAIL = DEFAULT_FROM_EMAIL
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Fallback

# Site configuration for django.contrib.sites
SITE_ID = 1

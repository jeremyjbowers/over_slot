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

# DigitalOcean injects DATABASE_URL for both Postgres and Redis components.
# Redis uses rediss:// which dj_database_url doesn't support. When you have both
# Postgres and Redis, bind Postgres to POSTGRES_DATABASE_URL and Redis to VALKEY_URL.
DATABASE_URL = os.environ.get("DATABASE_URL", None)
POSTGRES_DATABASE_URL = os.environ.get("POSTGRES_DATABASE_URL", None)

def _get_database_url():
    url = DATABASE_URL or POSTGRES_DATABASE_URL
    if not url:
        return None
    scheme = url.split(":", 1)[0].lower()
    if scheme in ("rediss", "redis", "valkey", "valkeys"):
        # DATABASE_URL is Redis/Valkey; use POSTGRES_DATABASE_URL for the app DB
        if not POSTGRES_DATABASE_URL:
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(
                "DATABASE_URL is a Redis/Valkey URL (rediss://). Set POSTGRES_DATABASE_URL to your "
                "PostgreSQL connection string. In App Platform, bind your Postgres DB to "
                "POSTGRES_DATABASE_URL and Redis/Valkey to VALKEY_URL."
            )
        return POSTGRES_DATABASE_URL
    return url

_db_url = _get_database_url()
DATABASES = {
    "default": dj_database_url.parse(_db_url),
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

# Static and media files settings
# Serve static from DigitalOcean Spaces CDN in production
STORAGES['staticfiles'] = {
    'BACKEND': 'storages.backends.s3boto3.S3StaticStorage',
    'OPTIONS': {
        'location': 'static',
    },
}

# Point STATIC_URL at the CDN domain
STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"

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

# Cache configuration - Valkey (Redis-compatible) when VALKEY_URL is set, else database
# Env var: VALKEY_URL - e.g. valkey://localhost:6379/0 or valkeys://host:6379/0 (TLS)
VALKEY_URL = os.environ.get('VALKEY_URL', '')
if VALKEY_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_valkey.cache.ValkeyCache',
            'LOCATION': VALKEY_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_valkey.client.DefaultClient',
                # Fail fast (5s) if Valkey unreachable; avoids gunicorn timeout killing worker
                'CONNECTION_POOL_KWARGS': {'socket_connect_timeout': 5},
            },
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'cache_table',
        }
    }

# CSRF settings for multi-pod deployment
CSRF_COOKIE_SECURE = True
# Must be False so client JS can read csrftoken for X-CSRFToken (mock draft share POST, etc.).
# Session cookies stay HttpOnly; CSRF token is not session-equivalent. See Django CSRF docs.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_DOMAIN = '.overslotbaseball.com'  # Match session cookie domain

# Production-specific settings
DEBUG = False  # Turn off debug in production
DEVELOPMENT_MODE = False

# Email settings for production
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY', None)
MAILGUN_DOMAIN = os.environ.get('MAILGUN_DOMAIN', 'overslotbaseball.com')
MAILGUN_VALIDATION_API_KEY = os.environ.get('MAILGUN_VALIDATION_API_KEY', None)

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

# Logging configuration for production (DigitalOcean App Platform captures stdout/stderr)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
        },
        'django.server': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '%(server_time)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'verbose',
        },
        'django.server': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'django.server',
        },
    },
    'loggers': {
        # Core Django logs
        'django': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['django.server'],
            'level': 'INFO',
            'propagate': False,
        },
        # Project app logs
        'overslot': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        # Gunicorn (common in App Platform) logs
        'gunicorn.error': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'gunicorn.access': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

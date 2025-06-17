from django.core.management.utils import get_random_secret_key
from pathlib import Path
import os
import sys
import dj_database_url

from config.dev.settings import *

WSGI_APPLICATION = "config.do_app_platform.app.application"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", None)

DEBUG = True

ALLOWED_HOSTS = ["*"]

DEVELOPMENT_MODE = True

DATABASE_URL = os.environ.get("DATABASE_URL", None)

DATABASES = {
    "default": dj_database_url.parse(DATABASE_URL),
}

STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/"
STATICFILES_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# Media files (uploads) configuration
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

INSTALLED_APPS = INSTALLED_APPS + ["storages"]

# Production-specific CORS settings
CORS_ALLOWED_ORIGINS = [
    "https://the-over-slot.nyc3.cdn.digitaloceanspaces.com",
    "https://overslot-prod-wxrbl.ondigitalocean.app",
    "https://overslotbaseball.com",
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
    "https://the-over-slot.nyc3.cdn.digitaloceanspaces.com",
]

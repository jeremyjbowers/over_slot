import os
import environ

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ["*"]),
    MAILGUN_API_KEY=(str, ''),
    MAILGUN_DOMAIN=(str, ''),
    STRIPE_SECRET_KEY=(str, ''),
    STRIPE_PUBLISHABLE_KEY=(str, ''),
    STRIPE_WEBHOOK_SECRET=(str, ''),
    USE_TLS=(bool, True),
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Take environment variables from .env file
environ.Env.read_env(os.path.join(os.path.dirname(BASE_DIR), '.env'))

SECRET_KEY = env('DJANGO_SECRET_KEY', default=")(hv#e)wqd-9pwuvd94wq5-snmz+@m(&-g5e74&zg)+geh-xqe+++++sadjklfhlk9999999h7")

DEBUG = True

ALLOWED_HOSTS = env('ALLOWED_HOSTS')

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "django.contrib.sites",  # Required for django-allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "sesame",
    "overslot",
    "django_prose_editor"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # Move allauth before sesame
    "sesame.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"

ROOT_URLCONF = "overslot.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["overslot/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",  # Required for django-allauth
                "overslot.context_processors.settings_context",  # Make settings available in templates
            ],
            "libraries": {
                "overslot_tags": "overslot.templatetags.overslot_tags",
            },
        },
    },
]

WSGI_APPLICATION = "config.dev.app.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("DB_NAME", "overslot"),
        "USER": os.environ.get("DB_USER", "overslot"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "overslot"),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Authentication settings
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# django-allauth settings
SITE_ID = 1

# Authentication backends - now including sesame for magic links
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'sesame.backends.ModelBackend',  # Add sesame backend for magic links
    'allauth.account.auth_backends.AuthenticationBackend',  # Re-enable allauth
]

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'first_name*', 'last_name*']
ACCOUNT_EMAIL_VERIFICATION = 'none'  # Disable allauth email verification since we handle it via magic links
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_PASSWORD_MIN_LENGTH = 8  # Keep for admin users, but not used in signup
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True  # Auto-login users when they verify email
ACCOUNT_LOGOUT_ON_GET = False  # Require POST for logout
ACCOUNT_SESSION_REMEMBER = None  # Don't auto-remember sessions

# Enable login by code (magic link alternative through allauth)
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 300  # 5 minutes
ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS = 3

# Django Sesame settings for magic link authentication
SESAME_MAX_AGE = 24 * 60 * 60  # 24 hours - restore production value
SESAME_ONE_TIME = False  # Allow multiple uses for testing
SESAME_INVALIDATE_ON_PASSWORD_CHANGE = False  # Prevent password changes from affecting tokens
# Let sesame use its default packer

# STATICFILES
STATIC_URL = "/static/"
STATIC_ROOT = "static/"

AWS_S3_REGION_NAME = "nyc3"
AWS_S3_ENDPOINT_URL = f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID', default=None)
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY', default=None)
AWS_DEFAULT_ACL = "public-read"
AWS_STORAGE_BUCKET_NAME = "the-over-slot"
AWS_S3_CUSTOM_DOMAIN = "the-over-slot.nyc3.cdn.digitaloceanspaces.com"
AWS_LOCATION = "static"

CORS_ALLOWED_ORIGINS = [
    "https://the-over-slot.nyc3.cdn.digitaloceanspaces.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://overslot-prod-wxrbl.ondigitalocean.app",
    "https://the-over-slot.nyc3.cdn.digitaloceanspaces.com",
    "https://ruling-badger-really.ngrok-free.app",
]

# Email settings
MAILGUN_API_KEY = env('MAILGUN_API_KEY', default=None)
MAILGUN_DOMAIN = env('MAILGUN_DOMAIN', default=None)

# Email backend configuration
if MAILGUN_API_KEY and MAILGUN_DOMAIN:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # For development
    DEFAULT_FROM_EMAIL = f'Over Slot <noreply@{MAILGUN_DOMAIN}>'
    SERVER_EMAIL = DEFAULT_FROM_EMAIL
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Stripe settings
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default=None)
STRIPE_PUBLISHABLE_KEY = env('STRIPE_PUBLISHABLE_KEY', default=None)
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default=None)

# Subscription pricing
SUBSCRIPTION_PRICE_MONTHLY = 9.99  # Monthly price in USD

DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# HTTPS and proxy settings for development
USE_TLS = env('USE_TLS', default=True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False  # Don't force redirect in development
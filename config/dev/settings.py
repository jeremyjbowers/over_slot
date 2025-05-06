import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    ")(hv#e)wqd-9pwuvd94wq5-snmz+@m(&-g5e74&zg)+geh-xqe+++++sadjklfhlk9999999h7",
)

DEBUG = os.environ.get("DEBUG", True)

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["https://ruling-badger-really.ngrok-free.app"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "overslot",
    "django_prose_editor"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
                "django.template.context_processors.request",
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

# LOGIN STUFF
LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "/"

# STATICFILES
STATIC_URL = "/static/"
STATIC_ROOT = "static/"

AWS_S3_REGION_NAME = "nyc3"
AWS_S3_ENDPOINT_URL = f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", None)
AWS_DEFAULT_ACL = "public-read"
AWS_STORAGE_BUCKET_NAME = "static-theoverslot"
AWS_S3_CUSTOM_DOMAIN = "static-theoverslot.nyc3.cdn.digitaloceanspaces.com"
AWS_LOCATION = "static"

## MAIL
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", None)

DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
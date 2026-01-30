"""
Django settings for qrservice project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-&8o-2-@pgxvg69xo0ax5*qh)5_9#t2lu81@guaf1z6q%--@904'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Required for allauth

    # OAuth authentication
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.yandex',

    # Наши приложения
    'apps.accounts',
    'apps.companies',
    'apps.qr',
    'apps.reviews',
    'apps.dashboard',
    'apps.integrations',

    # Старое приложение (для совместимости, потом удалим)
    'qrcode_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',  # OAuth support
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.RateLimitMiddleware',  # Bot protection
]

ROOT_URLCONF = 'qrservice.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'qrservice.wsgi.application'


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Site ID for django.contrib.sites
SITE_ID = 1

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',  # Default Django auth
    'allauth.account.auth_backends.AuthenticationBackend',  # OAuth auth
]


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Login settings
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'


# Cache Configuration
# Production: установить REDIS_URL=redis://localhost:6379/1
REDIS_URL = os.environ.get('REDIS_URL')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    # Development: локальный кэш в памяти
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'review-analysis-cache',
        }
    }


# Celery Configuration (SQLite broker for development)
CELERY_BROKER_URL = 'sqla+sqlite:///' + str(BASE_DIR / 'celery-broker.db')
CELERY_RESULT_BACKEND = 'db+sqlite:///' + str(BASE_DIR / 'celery-results.db')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes


# Google Business Profile API
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:8000/integrations/google/callback/')
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/business.manage',
]

# Telegram Bot for notifications
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOT_USERNAME = 'TopNaKarte_notifications_bot'

# Site URL для генерации QR-кодов
# Development: http://localhost:8000
# Production: https://replyq.ru
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000')


# Django-allauth OAuth settings
SOCIALACCOUNT_AUTO_SIGNUP = True  # Автосоздание аккаунта при OAuth
ACCOUNT_EMAIL_VERIFICATION = 'none'  # OAuth провайдер уже проверил email
ACCOUNT_EMAIL_REQUIRED = True  # Email обязателен
SOCIALACCOUNT_QUERY_EMAIL = True  # Запрашивать email у провайдера
ACCOUNT_AUTHENTICATION_METHOD = 'email'  # Вход по email
ACCOUNT_USERNAME_REQUIRED = False  # Username не нужен
ACCOUNT_USER_MODEL_USERNAME_FIELD = None  # У User нет поля username
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.SocialAccountAdapter'

# OAuth providers configuration
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
    },
    'yandex': {
        # Настройки для Яндекс OAuth
    }
}


# Rate Limiting (bot protection)
RATE_LIMIT_REQUESTS = 5  # Max requests per window
RATE_LIMIT_WINDOW = 60   # Window in seconds
RATE_LIMIT_PATHS = [     # Protected endpoints
    '/accounts/register/',
    '/accounts/login/',
]


# Logging Configuration (для отладки OAuth)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'allauth': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'apps.accounts': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'ih2201fopweuhOHB@@DOQ}IUWGBDIOWdwq@#@#id!843109)'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['storage.eventshock.ru', '127.0.0.1', 'localhost', 's.eventshock.ru', '95.163.87.65']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storage.apps.StorageConfig',
    'eventshock_auth.apps.EventshockAuthConfig',
    'crispy_forms',
    'crispy_bootstrap5',
    'oauth2_provider',
    'corsheaders',
    'rest_framework',
]

# В DEBUG режиме можно временно отключить SecurityMiddleware для отладки
# Раскомментируйте следующую строку, если редирект все еще происходит:
# DEBUG_DISABLE_SECURITY_MIDDLEWARE = True

DEBUG_DISABLE_SECURITY_MIDDLEWARE = False  # Установите True для полного отключения SecurityMiddleware в DEBUG

if DEBUG and DEBUG_DISABLE_SECURITY_MIDDLEWARE:
    # В DEBUG режиме полностью отключаем SecurityMiddleware
    MIDDLEWARE = [
        # 'django.middleware.security.SecurityMiddleware',  # Отключено в DEBUG
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.locale.LocaleMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'utils.middleware.SessionValidationMiddleware',  # Проверка валидности сессии
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'utils.middleware.LanguageMiddleware',
    ]
else:
    MIDDLEWARE = [
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.locale.LocaleMiddleware',
        'corsheaders.middleware.CorsMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'utils.middleware.SessionValidationMiddleware',  # Проверка валидности сессии
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'utils.middleware.LanguageMiddleware',
    ]

ROOT_URLCONF = 'estorage.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'utils.context_processors.language_processor',
                'utils.context_processors.system_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'estorage.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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
LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', 'Русский'),
    ('en', 'English'),
    ('ja', '日本語'),
]
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'staticfiles'),
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# OAuth2 settings
OAUTH2_PROVIDER = {
    'SCOPES': {'read': 'Read scope', 'write': 'Write scope'},
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 86400,
}

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
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
CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRFToken']

# Video quality requirements
VIDEO_QUALITY_REQUIREMENTS = {
    'min_fps': 30,
    'min_resolution': '720p',
    'preferred_codec': 'h264'
}

# File upload settings
# Максимальный размер файла в памяти перед сохранением на диск (100MB)
# Файлы больше этого размера автоматически сохраняются во временный файл
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100MB
FILE_UPLOAD_TEMP_DIR = os.path.join(BASE_DIR, 'tmp')
# Максимальный размер всех данных POST-запроса (1GB)
# Это критически важно для загрузки больших файлов
DATA_UPLOAD_MAX_MEMORY_SIZE = 4294967296  # 4GB
CHUNKED_UPLOAD_MAX_BYTES = 2147483648  # 2GB
CHUNKED_UPLOAD_CHUNK_SIZE = 10485760  # 10MB

# Avatar upload settings
MAX_AVATAR_SIZE = 10 * 1024 * 1024  # 10MB

# Create temp directory if it doesn't exist
if not os.path.exists(FILE_UPLOAD_TEMP_DIR):
    os.makedirs(FILE_UPLOAD_TEMP_DIR)

# Large file settings
LARGE_FILE_SIZE_THRESHOLD = 52428800  # 10MB (10485760 bytes = 10 * 1024 * 1024)
MAX_FILE_SIZE = 4294967296  # 4GB (было 2GB, уменьшено до 1GB согласно требованиям)
MAX_UPLOAD_SIZE = 4294967296  # 4GB

# Настройки для больших файлов
CHUNK_SIZE = 10485760  # 10MB

# Login URL
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'

# Настройки безопасности (только для production)
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    # Явно отключаем все редиректы на HTTPS в режиме разработки
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_PROXY_SSL_HEADER = None  # Отключаем проверку заголовков прокси в DEBUG
    # Дополнительно отключаем HSTS (HTTP Strict Transport Security)
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# Настройки сессий
# Время жизни сессии в секундах (по умолчанию 2 недели)
SESSION_COOKIE_AGE = 1209600  # 14 дней (60 * 60 * 24 * 14)
# Обновлять время жизни сессии при каждом запросе
SESSION_SAVE_EVERY_REQUEST = True
# Истекает ли сессия при закрытии браузера (False = использует SESSION_COOKIE_AGE)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# Хранить сессии в базе данных (надежнее, чем cookies)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
# Имя cookie для сессии
SESSION_COOKIE_NAME = 'sessionid'
# SameSite настройка для сессионных cookie
SESSION_COOKIE_SAMESITE = 'Lax'
# HTTPOnly для безопасности (предотвращает доступ JavaScript к cookie сессии)
SESSION_COOKIE_HTTPONLY = True
# Настройки CSRF для работы с большими файлами и обычными формами
# Разрешаем JavaScript читать CSRF токен из cookie для AJAX запросов
CSRF_COOKIE_HTTPONLY = False
# Используем cookie вместо сессии для CSRF
CSRF_USE_SESSIONS = False
# SameSite настройка: 'Lax' работает для обычных форм и AJAX
# При необходимости можно изменить на 'None' если есть проблемы с cross-site запросами
CSRF_COOKIE_SAMESITE = 'Lax'
# Доверенные источники
CSRF_TRUSTED_ORIGINS = [
    'https://storage.eventshock.ru',
    'https://s.eventshock.ru',
    'http://127.0.0.1',
    'http://localhost',
    'https://127.0.0.1',
    'https://localhost',
]
# Дополнительные настройки безопасности (только для production)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
else:
    SECURE_BROWSER_XSS_FILTER = False
    SECURE_CONTENT_TYPE_NOSNIFF = False
    X_FRAME_OPTIONS = 'SAMEORIGIN'  # Разрешаем iframe для разработки

# Настройки кэширования
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}

# Добавьте эти настройки
# Создаем директорию для логов, если её нет
LOG_DIR = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'error.log'),
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'ERROR',
            'propagate': True,
        },
        'storage': {
            'handlers': ['file', 'console'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}

# Добавьте эти настройки
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser'
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication'
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}

"""
Django settings for directorio_turistico project.

Detecta automáticamente el entorno:
- Local: DJANGO_DEBUG no existe → DEBUG=True
- Producción: DJANGO_DEBUG=False → DEBUG=False

Variables de entorno requeridas en producción:
- DJANGO_DEBUG=False
- DJANGO_SECRET_KEY=<clave-generada-con-get_random_secret_key>
"""
import os
from pathlib import Path
from decouple import config, Csv

# =============================================================
#  BASE
# =============================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================
#  ENTORNO (local vs producción)
# =============================================================
# En local, la variable no está definida → DEBUG=True
# En producción, DJANGO_DEBUG=False → DEBUG=False
DEBUG = config('DJANGO_DEBUG', default=True, cast=bool)

# =============================================================
#  SEGURIDAD
# =============================================================
SECRET_KEY = config(
    'DJANGO_SECRET_KEY',
    default='django-insecure-default-solo-para-desarrollo'
)

ALLOWED_HOSTS = [
    'chatbot-sigef.tabasco.gob.mx',
    'www.chatbot-sigef.tabasco.gob.mx',
    '127.0.0.1',
    'localhost',
]

CSRF_TRUSTED_ORIGINS = [
    'http://chatbot-sigef.tabasco.gob.mx',
    'https://chatbot-sigef.tabasco.gob.mx',
]

# =============================================================
#  SUBRUTA (para que funcione bajo /directorio/)
# =============================================================
# En desarrollo: sin prefijo (http://127.0.0.1:8000/)
# En producción: con prefijo (https://dominio/directorio/)
if DEBUG:
    FORCE_SCRIPT_NAME = None
else:
    FORCE_SCRIPT_NAME = '/directorio'

# =============================================================
#  APLICACIONES
# =============================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'directorio',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # ⬇️ Middleware de login global (al final)
    'directorio.middleware.LoginRequiredMiddleware',
]

ROOT_URLCONF = 'directorio_turistico.urls'

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

WSGI_APPLICATION = 'directorio_turistico.wsgi.application'

# =============================================================
#  BASE DE DATOS
# =============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# =============================================================
#  CONTRASEÑAS
# =============================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================
#  INTERNACIONALIZACIÓN
# =============================================================
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

# =============================================================
#  ARCHIVOS ESTÁTICOS Y MEDIA
# =============================================================
if DEBUG:
    STATIC_URL = '/static/'
    MEDIA_URL = '/media/'
else:
    STATIC_URL = '/directorio/static/'
    MEDIA_URL = '/directorio/media/'

STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'

# =============================================================
#  LOGIN
# =============================================================
if DEBUG:
    LOGIN_URL = '/login/'
    LOGOUT_REDIRECT_URL = '/login/'
    LOGIN_REDIRECT_URL = '/'
else:
    LOGIN_URL = '/directorio/login/'
    LOGOUT_REDIRECT_URL = '/directorio/login/'
    LOGIN_REDIRECT_URL = '/directorio/'

# URLs que NO requieren login
LOGIN_EXEMPT_URLS = [
    r'^/login/$',
    r'^/directorio/login/$',
    r'^/admin/',
    r'^/static/',
    r'^/media/',
    r'^/favicon\.ico$',
]

# Sesión: 12 horas
SESSION_COOKIE_AGE = 12 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True

# =============================================================
#  SEGURIDAD EN PRODUCCIÓN (solo si DEBUG=False)
# =============================================================
if not DEBUG:
    # Cookies solo por HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Detectar HTTPS detrás de nginx
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # Redirigir todo a HTTPS
    SECURE_SSL_REDIRECT = True

    # HSTS: forzar HTTPS por 1 año
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Prevenir clickjacking
    X_FRAME_OPTIONS = 'DENY'

    # Evitar sniffing de tipo MIME
    SECURE_CONTENT_TYPE_NOSNIFF = True

    # Cookies con SameSite Lax
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'

# =============================================================
#  FOTOS
# =============================================================
FOTOS_ACTIVAS = 'negocios'

# =============================================================
#  OTROS
# =============================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
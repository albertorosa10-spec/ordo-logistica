"""
Django settings for setup project.
Zakaz — Plataforma de Agendamento
Versão: 1.0.0 — Configuração híbrida dev/prod via DJANGO_ENV
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ==========================================
# AMBIENTE
# ==========================================

DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development')
IS_PRODUCTION = DJANGO_ENV == 'production'

# ==========================================
# SEGURANÇA
# ==========================================

if IS_PRODUCTION:
    SECRET_KEY = os.environ['SECRET_KEY']
    DEBUG = False
    ALLOWED_HOSTS = ['10.253.12.13', 'localhost', '127.0.0.1']
else:
    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'django-insecure-tc83e6zypdz1mzm49=sh(r^_qnav6vo7bj8!+=4ietsg(&7ey#'
    )
    DEBUG = True
    ALLOWED_HOSTS = ['*']

if IS_PRODUCTION:
    CSRF_TRUSTED_ORIGINS = [
        'http://10.253.12.13:443',
        'http://10.253.12.13',
        'https://10.253.12.13',
        'http://localhost',
    ]
else:
    CSRF_TRUSTED_ORIGINS = [
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        'http://10.253.12.13',
        'http://10.253.12.13:8000',
    ]

# ==========================================
# SEGURANÇA HTTP (produção)
# ==========================================

if IS_PRODUCTION:
    SECURE_BROWSER_XSS_FILTER     = True
    SECURE_CONTENT_TYPE_NOSNIFF   = True
    SESSION_COOKIE_SECURE         = False  # sem HTTPS por ora
    CSRF_COOKIE_SECURE            = False  # sem HTTPS por ora

# ==========================================
# APLICAÇÕES
# ==========================================

INSTALLED_APPS = [
    'core',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'setup.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.perfis_usuario',
            ],
        },
    },
]

WSGI_APPLICATION = 'setup.wsgi.application'

# ==========================================
# DATABASE
# ==========================================

if IS_PRODUCTION:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'),
            conn_max_age=600,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ==========================================
# VALIDAÇÃO DE SENHAS
# ==========================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ==========================================
# INTERNACIONALIZAÇÃO
# ==========================================

LANGUAGE_CODE = 'pt-br'
TIME_ZONE     = 'America/Sao_Paulo'
USE_I18N      = True
USE_TZ        = True

# ==========================================
# ARQUIVOS ESTÁTICOS E MÍDIA
# ==========================================

STATIC_URL  = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ==========================================
# CELERY / REDIS
# ==========================================

CELERY_BROKER_URL     = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_TIMEZONE       = 'America/Sao_Paulo'

# ==========================================
# AUTENTICAÇÃO
# ==========================================

LOGIN_URL           = '/portal/login/'
LOGIN_REDIRECT_URL  = '/portal/dashboard/'
LOGOUT_REDIRECT_URL = '/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==========================================
# E-MAIL — DESABILITADO
# ==========================================

# _email_host = os.environ.get('EMAIL_HOST_USER')
# if _email_host:
#     EMAIL_BACKEND         = 'django.core.mail.backends.smtp.EmailBackend'
#     EMAIL_HOST            = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
#     EMAIL_PORT            = int(os.environ.get('EMAIL_PORT', 587))
#     EMAIL_USE_TLS         = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
#     EMAIL_HOST_USER       = _email_host
#     EMAIL_HOST_PASSWORD   = os.environ.get('EMAIL_HOST_PASSWORD', '')
#     DEFAULT_FROM_EMAIL    = os.environ.get('DEFAULT_FROM_EMAIL', _email_host)
# else:
#     EMAIL_BACKEND      = 'django.core.mail.backends.console.EmailBackend'
#     DEFAULT_FROM_EMAIL = 'zakaz@localhost'

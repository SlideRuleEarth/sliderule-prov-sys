"""
Django settings for ps_web project.

Generated by 'django-admin startproject' using Django 3.2.9.

For more information on this file, see
https://docs.djangoproject.com/en/dev/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/dev/ref/settings/
"""

from datetime import timedelta, datetime, timezone
from pathlib import Path
import os
import environ
import requests
from django.contrib.messages import constants as messages

MESSAGE_TAGS = {
        messages.DEBUG: 'alert-secondary',
        messages.INFO: 'alert-info',
        messages.SUCCESS: 'alert-success',
        messages.WARNING: 'alert-warning',
        messages.ERROR: 'alert-danger',
}

# # Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(env_file=os.path.join(BASE_DIR, '.versions'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/dev/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY","INVALID")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = (os.environ.get("DEBUG", default="False")=="True")
DJANGO_DEBUG_TOOLBAR = (os.environ.get("DJANGO_DEBUG_TOOLBAR", default="False")=="True")
PS_VERSION = (os.environ.get("PS_VERSION"))
PS_SITE_TITLE = (os.environ.get("PS_SITE_TITLE"))
PS_BLD_ENVVER = (os.environ.get("PS_BLD_ENVVER"))
DOCKER_TAG = (os.environ.get("DOCKER_TAG"))
GIT_VERSION = (os.environ.get("GIT_VERSION"))
#DEBUG = False
if DEBUG and DJANGO_DEBUG_TOOLBAR:
    import socket  
    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS = [ip[: ip.rfind(".")] + ".1" for ip in ips] + ["127.0.0.1", "10.0.2.2"]
else:
    INTERNAL_IPS = ['127.0.0.1', ]
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split()
if DEBUG and DJANGO_DEBUG_TOOLBAR:
    ALLOWED_HOSTS += INTERNAL_IPS
# These are non routable local ip address so not neccessary to add to invalid hosts
# METADATA_URI = os.environ.get("ECS_CONTAINER_METADATA_URI")
# if (METADATA_URI is not None) and (METADATA_URI != ''):
#     container_metadata = requests.get(METADATA_URI).json()
#     ALLOWED_HOSTS.append(container_metadata['Networks'][0]['IPv4Addresses'][0])
# new for Django 4.0
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', '').split()
# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'phonenumber_field',
    'users.apps.UsersConfig',
    'api.apps.ApiConfig',
    'captcha',
    'django_celery_results',
    'crispy_forms',
#    'django_celery_beat',
    'django.contrib.sites',
    'oauth2_provider',
    'corsheaders',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.github',
#    'allauth.socialaccount.providers.google',
    'django_rq',
]
if DEBUG and DJANGO_DEBUG_TOOLBAR:
    INSTALLED_APPS.append('debug_toolbar')

CRISPY_TEMPLATE_PACK = 'bootstrap'

# allauth
SITE_ID = int(os.environ.get("SITE_ID",default=1))
ACCOUNT_FORMS = {
    "login": "users.forms.CustomLoginForm",
    'signup': 'users.forms.CustomSignupForm'
}
SOCIALACCOUNT_FORMS = {
    'signup': 'users.forms.MyCustomSocialSignupForm'
}

ACCOUNT_MAX_EMAIL_ADDRESSES=10
ACCOUNT_PRESERVE_USERNAME_CASING=False
ACCOUNT_EMAIL_REQUIRED=True
ACCOUNT_EMAIL_VERIFICATION="mandatory"
ACCOUNT_PASSWORD_INPUT_RENDER_VALUE=True
ACCOUNT_SIGNUP_EMAIL_ENTER_TWICE=True
SOCIALACCOUNT_AUTO_SIGNUP=True
ACCOUNT_DEFAULT_HTTP_PROTOCOL=(os.environ.get("ACCOUNT_DEFAULT_HTTP_PROTOCOL", default="https"))
LOGIN_REDIRECT_URL="/"
SOCIALACCOUNT_PROVIDERS = {
  'github': {
      'EMAIL_AUTHENTICATION': True
  }
}
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT=True


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
#    'DEFAULT_PARSER_CLASSES': ('rest_framework.parsers.JSONParser',),
}
DOMAIN =  os.environ.get("DOMAIN", default="localhost")
URL = DOMAIN
if DOMAIN != 'localhost':
    URL = 'ps.' + str(DOMAIN)
LONG_DESCRIPTION="""
User interface for SlideRule Provisioning API.\nNOTE: This interface is encapsulated by the SlideRule Library and is not typically used directly by users.

The provisioning system allows different organizations to share a given amazon web services account and to maintain independent clusters of sliderule nodes. This provides the owners of organizations the ability to control access to their organization’s cluster via a privilaged ‘owner’ account.

Regular users of sliderule can create a regular account and request membership to organizations. The owner of the organization can accept the membership and make the user an active member or ignore the request. Owners can make members inactive to temporarily deny access to the cluster. Active members can obtain an access token that provides access to the system for 24 hours. Active members can request node capacity for the duration of the token lifetime or with a provided “time to live”.

Owner accounts:

* deploy or shutdown the organization cluster

* accept users’ membership requests

* activate/deactivate memberships

* specify the minimum and maximum number of nodes that can be deployed on the organization cluster

* can view organization’s cluster account and budget forecast

Regular accounts:

* can request membership to organizations

* can view cluster account balance and status

Endpoints:

The provisioning system provides endpoints that allow regular users to request server resources to be allocated for their python client to use throughout a given session. Users share sliderule nodes. All requests for node capacity have an expiration. Requests from all users are combined so that each and every users’ requests for the minimum number of nodes required are honored. When all the node capacity requests have expired the provisioning system will automatically reduce the number of nodes in the cluster to the minimum it is configured for. Organization cluster have two nodes (a load balancer and a monitor) that are always active even if the worker nodes is set to zero. The load balancer node can take several minutes to start. However, the organization cluster can be configured to destroy the overhead nodes if the minimum number of nodes is zero or to keep them active for faster deployment. The organization cluster can also be configured to deploy automatically (if the overhead nodes were configured to be destroyed) upon the first node capacity request. When the load balancer has to be started it will take longer to make the cluster completely available to the users’ client. However this tradeoff can save money if the organization cluster is expected to be idle for long periods of time.

All endpoints require some kind of authentication.


"""


SPECTACULAR_SETTINGS = {
    'TITLE': 'SlideRule Provisioning API',
    'DESCRIPTION': LONG_DESCRIPTION,
    'VERSION': os.environ.get('PS_VERSION', '0.0.0'),
    'SERVE_INCLUDE_SCHEMA': True,
    'LICENSE': {"name": "BSD-3-Clause", "url": "https://github.com/ICESat2-SlideRule/sliderule-ps-web/blob/main/LICENSE"},
    'CONTACT':{'name':'developer', 'email': 'support@mail.slideruleearth.io'},
    'EXTERNAL_DOCS':{'description':'SlideRule User Documentation','url':'https://slideruleearth.io/web/rtd/'}
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,

    'ALGORITHM': 'HS256',
    # SECURITY WARNING: keep the singing key used in production secret!
    'SIGNING_KEY': os.environ.get("JWT_SECRET_KEY",""),
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('api.tokens.JWTAccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(hours=12),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

MIDDLEWARE = [
#    'ps_web.middleware.EarlyLoggingMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'ps_web.middleware.HealthCheckMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'ps_web.middleware.OAuthToolkitGroupProtectionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'oauth2_provider.middleware.OAuth2TokenMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware'
]

if DEBUG and DJANGO_DEBUG_TOOLBAR:
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')


ROOT_URLCONF = 'ps_web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'users.views.get_user_orgs',
            ],
        },
    },
]

WSGI_APPLICATION = 'ps_web.wsgi.application'


# Database
# NOTE sqllite3 is just the fallback!
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("SQL_ENGINE"),
        "NAME": os.environ.get("POSTGRES_DB"),
        "USER": os.environ.get("POSTGRES_USER"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("SQL_HOST"),
        "PORT": os.environ.get("SQL_PORT"),
        # migrating to and/or connecting to an aws db
        #     "ENGINE": "django.db.backends.postgresql",
        #     "NAME": "provsys",
        #     "USER": "ps_admin",
        #     "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "password"),
        #     "HOST": "prov-sys.[hostname id here].[region].rds.amazonaws.com", ## this can change
        #     "PORT": "[port number here]",
    }
}


# Password validation
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators

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

AUTH_USER_MODEL = 'users.User'
LOGIN_URL = '/accounts/login/'
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Internationalization
# https://docs.djangoproject.com/en/dev/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/dev/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
# The following creates an incompatiblity with django rest framework for django 4.1 release
#STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

# Default primary key field type
# https://docs.djangoproject.com/en/dev/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = 'django_amazon_ses.EmailBackend'

AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
DEFAULT_FROM_EMAIL = 'support@mail.slideruleearth.io'
EMAIL_HOST = 'icesat2sliderule.org' ##   os.environ.get("DOMAIN")
EMAIL_HOST_USER = '#'
AUTHENTICATION_BACKENDS = [
    'oauth2_provider.backends.OAuth2Backend',
    "django.contrib.auth.backends.ModelBackend",
    'allauth.account.auth_backends.AuthenticationBackend',
]
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{filename}:{lineno:d}:{funcName}] [{message}]',
            'style': '{',
        },
        "rq_console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    'handlers': {
        'console': {
            'level': os.environ.get("PS_WEB_LOG_LEVEL", "INFO"),
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'test_console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'test_console_info': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        "rq_console": {
            "level": "DEBUG",
            "class": "rq.logutils.ColorizingStreamHandler",
            "formatter": "rq_console",
            "exclude": ["%(asctime)s"],
        },
        # 'file': {
        #     'level': 'INFO',
        #     'class': 'logging.FileHandler',
        #     'filename': '/home/logs/ps-web.log',
        #     'formatter': 'verbose'
        # },
    },
    'loggers': {
        'django': {
            # 'handlers': ['console', 'file'],
            'handlers': ['console'],
            'propagate': True,
        },
        "rq.worker": {
            "handlers": ["rq_console"],
            "level": "DEBUG"
        },
    }
}

# using django-redis cache backend
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{os.environ.get('REDIS_HOST', 'redis')}:{os.environ.get('REDIS_PORT', '6379')}/{os.environ.get('REDIS_DB', '0')}", #<-- redis://redis:6379/0
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.lz4.Lz4Compressor",
        }
    }
}

#PHONENUMBER_DEFAULT_REGION = 'E164'
PHONENUMBER_DEFAULT_FORMAT = 'NATIONAL'
PHONENUMBER_DEFAULT_REGION = "US"


RQ_QUEUES = {
    'default': {
        'HOST': os.environ.get("REDIS_HOST", "redis"),
        'PORT': os.environ.get("REDIS_PORT", "6379"),
        'DB': os.environ.get("REDIS_DB", "0"),
        'USE_REDIS_CACHE': 'default',
        'DEFAULT_TIMEOUT': 3600,
    },
    'cmd':{
        'HOST': os.environ.get("REDIS_HOST", "redis"),
        'PORT': os.environ.get("REDIS_PORT", "6379"),
        'DB': os.environ.get("REDIS_DB", "0"),
        'USE_REDIS_CACHE': 'default',
        'DEFAULT_TIMEOUT': 3600,
    },
    'scheduled':{
        'HOST': os.environ.get("REDIS_HOST", "redis"),
        'PORT': os.environ.get("REDIS_PORT", "6379"),
        'DB': os.environ.get("REDIS_DB", "0"),
        'USE_REDIS_CACHE': 'default',
        'DEFAULT_TIMEOUT': 172800,
    }
}
RQ_SHOW_ADMIN_LINK = True

OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    "OIDC_RSA_PRIVATE_KEY": os.environ.get("DJANGO_OIDC_RSA_PRIVATE_KEY", '').replace('\\n', '\n'),
    "OIDC_RSA_PRIVATE_KEYS_INACTIVE": [
        # to rotate keys see https://django-oauth-toolkit.readthedocs.io/en/latest/oidc.html#configuration
        # os.environ.get("OIDC_RSA_PRIVATE_KEY_2"),
        # os.environ.get("OIDC_RSA_PRIVATE_KEY_3")
    ],
    'SCOPES': {
        "openid": " Use OpenID Connect to create ID token",
        'memberships': ' Get list of active memberships'
    },
    'CLIENT_ID_GENERATOR_CLASS': 'oauth2_provider.generators.ClientIdGenerator',
    'CLIENT_SECRET_GENERATOR_CLASS': 'oauth2_provider.generators.ClientSecretGenerator',
    'OAUTH2_VALIDATOR_CLASS': 'api.oauth_validators.CustomOAuth2Validator',
}
# Only allow specific origins
# CORS_ORIGIN_REGEX_WHITELIST = [
#     r'^https://(\w+\.)?slideruleearth\.io$',
#     r'^https://(\w+\.)?testsliderule\.org$',
# ]
# OR
# CORS_ORIGIN_ALLOW_ALL = True
# OR
CORS_ALLOWED_ORIGINS = [
    "https://sliderule.slideruleearth.io",
    "https://developers.slideruleearth.io",
    "https://uw.slideruleearth.io",
    "https://utexas.slideruleearth.io",
    "https://uofmdtest.testsliderule.org",
    "https://esr.slideruleearth.io",
    "https://brown.slideruleearth.io",
]
if DEBUG:
    CORS_ALLOWED_ORIGINS.append("http://localhost")
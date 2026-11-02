"""
PostgreSQL Dedicated Test Settings for SriLekh.
Guarantees tests run strictly against PostgreSQL with zero silent fallback to SQLite.
Supports environment-configurable connection credentials for disposable test databases.
"""
import os
import sys

# Pre-set environment indicator so settings.py does not override DATABASES with SQLite
os.environ['USE_POSTGRES_TEST'] = '1'

from .settings import *

# Verify database engine is strictly PostgreSQL
db_conf = DATABASES.get('default', {})
engine = db_conf.get('ENGINE', '')
if 'sqlite' in engine or not engine:
    # Build PostgreSQL configuration from DATABASE_URL or explicit parameters
    test_db_url = os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if test_db_url and 'postgres' in test_db_url:
        DATABASES['default'] = env.db_url_config(test_db_url)
    else:
        DATABASES['default'] = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('TEST_DB_NAME', 'test_srilekh'),
            'USER': os.environ.get('TEST_DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('TEST_DB_PASSWORD', 'postgres'),
            'HOST': os.environ.get('TEST_DB_HOST', 'localhost'),
            'PORT': os.environ.get('TEST_DB_PORT', '5432'),
        }

# Strict Assertion: NEVER allow silent fallback to SQLite
assert 'postgresql' in DATABASES['default']['ENGINE'], (
    f"FATAL: PostgreSQL test configuration requires PostgreSQL engine, but got '{DATABASES['default']['ENGINE']}'."
)

# Test database settings for disposable isolation
DATABASES['default']['TEST'] = {
    'CHARSET': 'utf8',
}
DATABASES['default']['CONN_MAX_AGE'] = 0

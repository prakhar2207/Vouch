"""
Tests for Stage 4.2 Staging Database Isolation Safety Guard & Environment Identity Verification.
Verifies fail-closed behavior to protect production accounting databases from accidental staging connection.
"""

from django.test import TestCase, override_settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIClient
from django.conf import settings

from config.environment_guard import (
    validate_environment_database_isolation,
    get_environment_identity_metadata,
    PROD_HOST_DEFAULT,
    PROD_DB_DEFAULT,
)


class StagingDatabaseIsolationSafetyTests(TestCase):
    """
    Validates that the backend strictly refuses to boot in staging mode
    when configured against the production database, satisfying Phase 2.3 requirements.
    """

    def setUp(self):
        self.client = APIClient()

    def test_01_staging_fails_closed_when_pointing_to_neondb(self):
        """Staging backend MUST refuse to start if database name is 'neondb'."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={"ENGINE": "django.db.backends.postgresql", "NAME": "neondb", "HOST": "staging-pooler.neon.tech"},
                prod_db_name="neondb",
                is_testing=False
            )
        self.assertIn("FATAL ISOLATION DEFECT", str(ctx.exception))
        self.assertIn("production target", str(ctx.exception))

    def test_02_staging_fails_closed_when_pointing_to_prod_neon_host(self):
        """Staging backend MUST refuse to start if database host matches production endpoint without staging namespace."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={"ENGINE": "django.db.backends.postgresql", "NAME": "finance_db", "HOST": PROD_HOST_DEFAULT},
                prod_host=PROD_HOST_DEFAULT,
                prod_db_name=PROD_DB_DEFAULT,
                is_testing=False
            )
        self.assertIn("FATAL ISOLATION DEFECT", str(ctx.exception))
        self.assertIn("lacks explicit staging namespace", str(ctx.exception))

    def test_03_staging_fails_closed_when_database_url_targets_production(self):
        """Staging backend MUST inspect raw DATABASE_URL and fail closed if pointing to production."""
        prod_url = f"postgres://user:pass@{PROD_HOST_DEFAULT}/neondb?sslmode=require"
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={},
                database_url=prod_url,
                prod_host=PROD_HOST_DEFAULT,
                prod_db_name=PROD_DB_DEFAULT,
                is_testing=False
            )
        self.assertIn("FATAL ISOLATION DEFECT", str(ctx.exception))

    def test_04_staging_fails_closed_on_live_sqlite(self):
        """Staging backend cannot run on SQLite in non-testing live mode."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={"ENGINE": "django.db.backends.sqlite3", "NAME": "staging.sqlite3", "HOST": ""},
                prod_host=PROD_HOST_DEFAULT,
                prod_db_name=PROD_DB_DEFAULT,
                is_testing=False
            )
        self.assertIn("FATAL ISOLATION DEFECT", str(ctx.exception))
        self.assertIn("cannot run on SQLite in live mode", str(ctx.exception))

    def test_05_staging_succeeds_when_pointing_to_dedicated_staging_database(self):
        """Staging backend boots successfully when connected to dedicated isolated staging database."""
        result = validate_environment_database_isolation(
            environment="staging",
            db_config={
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "neondb_staging",
                "HOST": "ep-staging-branch-pooler.c-4.ap-southeast-1.aws.neon.tech"
            },
            prod_host=PROD_HOST_DEFAULT,
            prod_db_name=PROD_DB_DEFAULT,
            is_testing=False
        )
        self.assertTrue(result)

    def test_06_production_and_development_environments_unaffected(self):
        """Production and development environments remain unblocked by the staging isolation guard."""
        prod_result = validate_environment_database_isolation(
            environment="production",
            db_config={"ENGINE": "django.db.backends.postgresql", "NAME": "neondb", "HOST": PROD_HOST_DEFAULT},
            prod_host=PROD_HOST_DEFAULT,
            prod_db_name=PROD_DB_DEFAULT,
            is_testing=False
        )
        self.assertTrue(prod_result)

        dev_result = validate_environment_database_isolation(
            environment="development",
            db_config={"ENGINE": "django.db.backends.sqlite3", "NAME": "dev.sqlite3", "HOST": ""},
            prod_host=PROD_HOST_DEFAULT,
            prod_db_name=PROD_DB_DEFAULT,
            is_testing=False
        )
        self.assertTrue(dev_result)

    def test_07_environment_identity_endpoint_contract(self):
        """Verify GET /api/v1/health/environment/ returns non-sensitive metadata without secret leakage."""
        res = self.client.get("/api/v1/health/environment/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Contract verification
        self.assertEqual(data.get("status"), "healthy")
        self.assertIn("environment", data)
        self.assertIn("version", data)
        self.assertIn("commit", data)
        self.assertIn("database", data)
        self.assertIn("redis", data)
        self.assertIn("celery", data)
        self.assertIn("migrations", data)

        # Security invariant: zero secret leakage
        raw_text = str(data).lower()
        self.assertNotIn("password", raw_text)
        self.assertNotIn("secret", raw_text)
        self.assertNotIn("token", raw_text)
        self.assertNotIn("postgres://", raw_text)
        self.assertNotIn("redis://", raw_text)

    def test_08_environment_identity_alias_endpoint(self):
        """Verify compatibility alias GET /api/health/environment/."""
        res = self.client.get("/api/health/environment/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "healthy")

"""
Tests for Stage 4.3 Staging Database Isolation Safety Guard & Negative Isolation Scenarios.
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
    PROD_HOST_IPS,
)


class StagingDatabaseIsolationSafetyTests(TestCase):
    """
    Validates that the backend strictly refuses to boot in staging mode
    under all possible bypass techniques, satisfying Phase 1, Phase 2, and Phase 6 requirements.
    """

    def setUp(self):
        self.client = APIClient()

    def test_01_staging_fails_closed_when_pointing_to_neondb(self):
        """Negative Test 1: Staging backend MUST refuse to start if database name is 'neondb'."""
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
        """Negative Test 2: Staging backend MUST refuse to start if database host matches production endpoint."""
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

    def test_03_staging_fails_closed_when_pointing_to_prod_ip_address(self):
        """Negative Test 3: Staging backend MUST refuse to boot if configured with production Neon IP addresses."""
        for ip in PROD_HOST_IPS:
            with self.assertRaises(ImproperlyConfigured) as ctx:
                validate_environment_database_isolation(
                    environment="staging",
                    db_config={"ENGINE": "django.db.backends.postgresql", "NAME": "custom_db", "HOST": ip},
                    prod_host=PROD_HOST_DEFAULT,
                    prod_db_name=PROD_DB_DEFAULT,
                    is_testing=False
                )
            self.assertIn("FATAL ISOLATION DEFECT", str(ctx.exception))

    def test_04_staging_fails_closed_when_database_url_targets_production(self):
        """Negative Test 4: Staging backend MUST parse raw DATABASE_URL and fail closed if pointing to production."""
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

    def test_05_staging_fails_closed_when_database_name_passed_in_querystring(self):
        """Negative Test 5: Connection string passing ?database=neondb in querystring must fail closed."""
        tricky_url = f"postgres://user:pass@some-random-host.com/other?database=neondb"
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={},
                database_url=tricky_url,
                prod_host=PROD_HOST_DEFAULT,
                prod_db_name=PROD_DB_DEFAULT,
                is_testing=False
            )
        self.assertIn("FATAL ISOLATION DEFECT", str(ctx.exception))

    def test_06_staging_fails_closed_when_database_name_missing_in_live_mode(self):
        """Negative Test 6: Missing database name in live staging must fail closed."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={"ENGINE": "django.db.backends.postgresql", "NAME": "", "HOST": "other-host.com"},
                prod_host=PROD_HOST_DEFAULT,
                prod_db_name=PROD_DB_DEFAULT,
                is_testing=False
            )
        self.assertIn("missing in staging environment", str(ctx.exception))

    def test_07_staging_fails_closed_on_live_sqlite(self):
        """Negative Test 7: Staging backend cannot run on SQLite in non-testing live mode."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_environment_database_isolation(
                environment="staging",
                db_config={"ENGINE": "django.db.backends.sqlite3", "NAME": "staging.sqlite3", "HOST": ""},
                prod_host=PROD_HOST_DEFAULT,
                prod_db_name=PROD_DB_DEFAULT,
                is_testing=False
            )
        self.assertIn("cannot run on SQLite in live mode", str(ctx.exception))

    def test_08_staging_aliases_trigger_guard(self):
        """Negative Test 8: Aliases 'stage', 'stg', 'staging_canary' must trigger isolation guard."""
        for alias in ("stage", "stg", "staging_canary"):
            with self.assertRaises(ImproperlyConfigured):
                validate_environment_database_isolation(
                    environment=alias,
                    db_config={"ENGINE": "django.db.backends.postgresql", "NAME": "neondb", "HOST": "host.com"},
                    prod_host=PROD_HOST_DEFAULT,
                    prod_db_name=PROD_DB_DEFAULT,
                    is_testing=False
                )

    def test_09_staging_succeeds_when_pointing_to_dedicated_staging_database(self):
        """Positive Test 9: Staging backend boots successfully when connected to dedicated isolated staging database."""
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

    def test_10_production_and_development_environments_unaffected(self):
        """Positive Test 10: Production and development environments remain unblocked by the staging isolation guard."""
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

    def test_11_environment_identity_endpoint_contract(self):
        """Verify GET /api/v1/health/environment/ returns non-sensitive metadata without secret leakage."""
        res = self.client.get("/api/v1/health/environment/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data.get("status"), "healthy")
        self.assertIn("environment", data)
        self.assertIn("version", data)
        self.assertIn("commit", data)
        self.assertIn("database", data)
        self.assertIn("redis", data)
        self.assertIn("celery", data)
        self.assertIn("migrations", data)

        # Strict security invariant: zero secret leakage
        raw_text = str(data).lower()
        self.assertNotIn("password", raw_text)
        self.assertNotIn("secret", raw_text)
        self.assertNotIn("token", raw_text)
        self.assertNotIn("postgres://", raw_text)
        self.assertNotIn("redis://", raw_text)

    def test_12_environment_identity_alias_endpoint(self):
        """Verify compatibility alias GET /api/health/environment/."""
        res = self.client.get("/api/health/environment/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "healthy")

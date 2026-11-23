import json
import uuid
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.companies.models import Company, UserCompany
from apps.gst.models import CompanyGSTConfig
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gst_error_normalizer import normalize_gst_error
from apps.gst.services.gst_sandbox_service import GSTPortalService
from apps.gst.views import CompanyGSTConfigAPIView

User = get_user_model()

# Dedicated Sandbox Company Invariant
SANDBOX_COMPANY_ID = "4e62863a-08f9-4e99-b0bd-64873acfdd33"
PROTECTED_PROD_TENANT_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"


class GSTPortalAbstractionAndSecurityTests(TestCase):
    """
    Test suite verifying:
    1. Mandatory Test Isolation (No real tenant accounts touched).
    2. Quicko provider contract compliance (x-source: primary header).
    3. Error normalization (Zero leak of raw parameters, headers, or infrastructure).
    4. API view abstraction (Stripping credentials and environment flags from responses).
    5. Cooldown & brute-force rate-limiting on OTP endpoints.
    6. Multi-tenant session boundary isolation.
    """

    def setUp(self):
        cache.clear()

        # Invariant check: Assert we never touch production tenant
        self.assertNotEqual(SANDBOX_COMPANY_ID, PROTECTED_PROD_TENANT_ID)

        # Create or fetch sandbox company
        self.company, _ = Company.objects.get_or_create(
            id=uuid.UUID(SANDBOX_COMPANY_ID),
            defaults={
                "name": "Apex Belting & Industrial Store (Demo)",
                "legal_name": "Apex Belting & Industrial Supplies Pvt Ltd",
                "gstin": "27AAACA1234A1Z5",
                "state_code": "27",
            }
        )
        assert str(self.company.id) == SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"

        # Create secondary tenant for cross-tenant isolation tests
        self.other_company = Company.objects.create(
            name="Competitor Tenant Ltd",
            legal_name="Competitor Tenant Pvt Ltd",
            gstin="29AAACP9999P1Z8",
            state_code="29",
        )

        # Users
        self.user = User.objects.create_user(
            email="accountant@apexbelting.demo",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        self.other_user = User.objects.create_user(
            email="other@competitor.demo",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.other_user, company=self.other_company, role='ADMIN')

        self.factory = APIRequestFactory()

    def tearDown(self):
        cache.clear()

    def test_01_mandatory_test_isolation_invariant(self):
        """Verify the test runner operates exclusively in sandbox context and protects real tenants."""
        self.assertEqual(str(self.company.id), SANDBOX_COMPANY_ID)
        self.assertNotEqual(str(self.company.id), PROTECTED_PROD_TENANT_ID)
        self.assertFalse(Company.objects.filter(id=uuid.UUID(PROTECTED_PROD_TENANT_ID)).exists())

    def test_02_sandbox_client_x_source_header_injection(self):
        """Verify SandboxGSTClient always injects 'x-source: primary' in authorized headers."""
        client = SandboxGSTClient(company=self.company)
        with patch.object(client, "get_api_credentials", return_value=("test_api_key", "test_secret", "https://api.sandbox.co.in", False)):
            with patch.object(client, "get_access_token", return_value="dummy_bearer_token"):
                headers, corr_id = client._get_authorized_headers()

                self.assertIn("x-source", headers)
                self.assertEqual(headers["x-source"], "primary")
                self.assertEqual(headers["x-api-version"], "1.0.0")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["authorization"], "dummy_bearer_token")

    def test_03_error_normalizer_masks_x_source_and_technical_details(self):
        """Verify normalize_gst_error intercepts raw provider errors and converts to friendly copy."""
        # 1. The exact error from user screenshot: Missing required request parameters: [x-source]
        raw_x_source_err = "Missing required request parameters: [x-source]"
        friendly_x_source = normalize_gst_error(raw_x_source_err)
        self.assertNotIn("x-source", friendly_x_source)
        self.assertNotIn("[x-source]", friendly_x_source)
        self.assertIn("connect", friendly_x_source.lower())

        # 2. Rate limit HTTP 429
        raw_429 = "Client error: 429 Too Many Requests: Rate limit exceeded"
        friendly_429 = normalize_gst_error(raw_429)
        self.assertNotIn("429", friendly_429)
        self.assertIn("wait", friendly_429.lower())

        # 3. Invalid OTP
        raw_invalid_otp = "Invalid OTP provided by taxpayer for transaction TXN123"
        friendly_otp = normalize_gst_error(raw_invalid_otp)
        self.assertIn("OTP", friendly_otp)
        self.assertIn("incorrect", friendly_otp.lower())

        # 4. Sensitive credentials leak prevention
        raw_leaked_secret = "Failed auth with key key_live_abc123 and secret sec_xyz999"
        friendly_leak = normalize_gst_error(raw_leaked_secret)
        self.assertNotIn("key_live", friendly_leak)
        self.assertNotIn("sec_xyz", friendly_leak)

    def test_04_company_gst_config_api_strips_infrastructure_details(self):
        """Verify GET /api/v1/gst/config/<company_id>/ returns NO infrastructure flags."""
        config, _ = CompanyGSTConfig.objects.get_or_create(
            company=self.company,
            defaults={
                "eway_username": "27AAACA1234A1Z5",
                "auth_token": "dummy_token_123",
                "token_expires_at": timezone.now() + timedelta(days=30),
            }
        )

        request = self.factory.get(f"/api/v1/gst/config/{self.company.id}/")
        force_authenticate(request, user=self.user)
        view = CompanyGSTConfigAPIView.as_view()
        response = view(request, company_id=str(self.company.id))

        self.assertEqual(response.status_code, 200)
        data = response.data.get("config", {})

        # Invariants: Infrastructure & provider secrets must NEVER appear in client response
        self.assertNotIn("has_env_credentials", data)
        self.assertNotIn("api_key", data)
        self.assertNotIn("sandbox_api_key", data)
        self.assertNotIn("sandbox_api_secret", data)
        self.assertNotIn("sandbox_base_url", data)
        self.assertNotIn("has_sandbox_api_key", data)
        self.assertNotIn("has_sandbox_api_secret", data)

        # Essential business attributes must be present
        self.assertIn("is_portal_connected", data)
        self.assertIn("portal_username", data)

    def test_05_otp_cooldown_enforcement(self):
        """Verify backend strictly enforces 30s cooldown per company on requesting OTP."""
        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "request_portal_otp", return_value={"success": True, "correlation_id": "CORR_1"}):
                # First attempt: succeeds and returns cooldown_seconds
                res1 = GSTPortalService.request_portal_otp(self.company, "27AAACA1234A1Z5", "27AAACA1234A1Z5")
                self.assertTrue(res1["success"])
                self.assertEqual(res1.get("cooldown_seconds"), 30)

                # Second attempt immediately: must be blocked by server-side cooldown
                res2 = GSTPortalService.request_portal_otp(self.company, "27AAACA1234A1Z5", "27AAACA1234A1Z5")
                self.assertFalse(res2["success"])
                self.assertIn("wait", res2["error"].lower())
                self.assertIn("seconds", res2["error"].lower())

    def test_06_otp_verify_brute_force_protection(self):
        """Verify backend blocks OTP verification after 5 consecutive failed attempts."""
        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "verify_portal_otp", return_value={"success": False, "error": "Invalid OTP", "status_code": 400}):
                for i in range(5):
                    res = GSTPortalService.verify_portal_otp(self.company, "000000", "TXN_1", "27AAACA1234A1Z5", "27AAACA1234A1Z5")
                    self.assertFalse(res["success"])

                # 6th attempt should be rejected immediately due to brute-force lockout
                res_locked = GSTPortalService.verify_portal_otp(self.company, "000000", "TXN_1", "27AAACA1234A1Z5", "27AAACA1234A1Z5")
                self.assertFalse(res_locked["success"])
                self.assertIn("too many incorrect otp attempts", res_locked["error"].lower())

    def test_07_cross_tenant_isolation(self):
        """Verify user of Company B cannot request or view GST configuration for Company A."""
        request = self.factory.get(f"/api/v1/gst/config/{self.company.id}/")
        force_authenticate(request, user=self.other_user)
        view = CompanyGSTConfigAPIView.as_view()
        response = view(request, company_id=str(self.company.id))

        # Permission check: must be forbidden or denied
        self.assertIn(response.status_code, [403, 404])

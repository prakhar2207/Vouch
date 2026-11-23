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
from apps.gst.views import (
    CompanyGSTConfigAPIView,
    GSTRDirectPortalOTPRequestAPIView,
    GSTRDirectPortalVerifyOTPAPIView,
    GSTRDirectPortalDisconnectAPIView,
    GSTRDirectPortalRefreshSessionAPIView,
)

User = get_user_model()

# Dedicated Sandbox Company Invariant
SANDBOX_COMPANY_ID = "4e62863a-08f9-4e99-b0bd-64873acfdd33"
PROTECTED_PROD_TENANT_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"


class GSTPortalSandboxIntegrationCorrectionTests(TestCase):
    """
    Authoritative test suite for Sandbox.co.in GST Taxpayer API integration:
    1. Mandatory Test Isolation (No real user/client accounts modified).
    2. API access disabled error handling on GST Portal.
    3. API access enabled flow.
    4. Missing x-source header failure and masking.
    5. Valid x-source header injection and contract compliance.
    6. Invalid GST Portal username handling.
    7. Invalid OTP handling.
    8. Expired OTP handling.
    9. Successful OTP verification and 6-hour taxpayer session creation.
    10. Expired taxpayer session detection.
    11. Company switching state isolation.
    12. Cross-company token access prevention (RBAC).
    13. Token refresh and remote logout.
    """

    def setUp(self):
        cache.clear()

        # Invariant check: Assert we never touch production tenant
        self.assertNotEqual(SANDBOX_COMPANY_ID, PROTECTED_PROD_TENANT_ID)

        # Create dedicated sandbox company
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

        # Create isolated competitor tenant for multi-company tests
        self.other_company = Company.objects.create(
            name="Precision Tools Ltd",
            legal_name="Precision Tools India Pvt Ltd",
            gstin="29AAACP9999P1Z8",
            state_code="29",
        )

        # Create users
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

    # -------------------------------------------------------------
    # 1. Mandatory Test Isolation Invariant
    # -------------------------------------------------------------
    def test_01_mandatory_test_isolation_invariant(self):
        """Verify the test suite runs exclusively against Apex Belting demo and protects production tenants."""
        self.assertEqual(str(self.company.id), SANDBOX_COMPANY_ID)
        self.assertNotEqual(str(self.company.id), PROTECTED_PROD_TENANT_ID)
        self.assertFalse(Company.objects.filter(id=uuid.UUID(PROTECTED_PROD_TENANT_ID)).exists())

    # -------------------------------------------------------------
    # 2. API Access Disabled on Government Portal
    # -------------------------------------------------------------
    def test_02_api_access_disabled(self):
        """Verify clear customer-facing message when GST Portal API access is disabled."""
        disabled_error_response = {
            "success": False,
            "status_code": 400,
            "error": "API access is disabled for the taxpayer. Please enable API access from GST Portal.",
            "correlation_id": "CORR_API_DISABLED"
        }

        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "request_portal_otp", return_value=disabled_error_response):
                res = GSTPortalService.request_portal_otp(
                    company=self.company,
                    gstin="27AAACA1234A1Z5",
                    username="apex_user"
                )
                self.assertFalse(res["success"])
                expected_msg = "GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."
                self.assertEqual(res["error"], expected_msg)

    # -------------------------------------------------------------
    # 3. API Access Enabled Flow
    # -------------------------------------------------------------
    def test_03_api_access_enabled(self):
        """Verify successful OTP dispatch when API access is enabled."""
        success_response = {
            "success": True,
            "status_code": 200,
            "data": {"status_cd": "1"},
            "correlation_id": "CORR_SUCCESS_OTP"
        }

        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "request_portal_otp", return_value=success_response):
                res = GSTPortalService.request_portal_otp(
                    company=self.company,
                    gstin="27AAACA1234A1Z5",
                    username="apex_user"
                )
                self.assertTrue(res["success"])
                self.assertEqual(res.get("cooldown_seconds"), 30)
                self.assertIn("verification otp has been sent", res.get("message", "").lower())

    # -------------------------------------------------------------
    # 4. Missing x-source Header
    # -------------------------------------------------------------
    def test_04_missing_x_source_header(self):
        """Verify that omitting x-source triggers provider error and is normalized safely without leaking x-source."""
        client = SandboxGSTClient(company=self.company)
        with patch.object(client, "get_api_credentials", return_value=("key_123", "sec_456", "https://api.sandbox.co.in", False)):
            with patch.object(client, "get_access_token", return_value="jwt_sandbox_token"):
                headers, _ = client._get_authorized_headers(omit_source=True)
                self.assertNotIn("x-source", headers)

                raw_provider_error = "Missing required request parameters: [x-source]"
                normalized = normalize_gst_error(raw_provider_error)
                self.assertNotIn("x-source", normalized)
                self.assertNotIn("[x-source]", normalized)
                self.assertIn("connect", normalized.lower())

    # -------------------------------------------------------------
    # 5. Valid x-source Header & Contract Headers
    # -------------------------------------------------------------
    def test_05_valid_x_source_header(self):
        """Verify SandboxGSTClient injects x-source: primary, x-api-version, authorization, and json headers."""
        client = SandboxGSTClient(company=self.company)
        with patch.object(client, "get_api_credentials", return_value=("key_123", "sec_456", "https://api.sandbox.co.in", False)):
            with patch.object(client, "get_access_token", return_value="jwt_sandbox_token"):
                headers, corr_id = client._get_authorized_headers(source="primary")
                self.assertEqual(headers["x-source"], "primary")
                self.assertEqual(headers["x-api-version"], "1.0.0")
                self.assertEqual(headers["authorization"], "jwt_sandbox_token")
                self.assertEqual(headers["x-api-key"], "key_123")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["Accept"], "application/json")

    # -------------------------------------------------------------
    # 6. Invalid GST Portal Username
    # -------------------------------------------------------------
    def test_06_invalid_gst_portal_username(self):
        """Verify normalized user-friendly error when username is invalid or not registered."""
        invalid_user_response = {
            "success": False,
            "status_code": 400,
            "error": "Taxpayer username not found or invalid taxpayer credentials.",
            "correlation_id": "CORR_INV_USER"
        }

        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "request_portal_otp", return_value=invalid_user_response):
                res = GSTPortalService.request_portal_otp(
                    company=self.company,
                    gstin="27AAACA1234A1Z5",
                    username="wrong_username"
                )
                self.assertFalse(res["success"])
                self.assertIn("username", res["error"].lower())

    # -------------------------------------------------------------
    # 7. Invalid OTP
    # -------------------------------------------------------------
    def test_07_invalid_otp(self):
        """Verify normalized error when user enters an incorrect OTP."""
        invalid_otp_response = {
            "success": False,
            "status_code": 400,
            "error": "Invalid OTP entered by taxpayer.",
            "correlation_id": "CORR_INV_OTP"
        }

        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=invalid_otp_response):
                res = GSTPortalService.verify_portal_otp(
                    company=self.company,
                    otp="123456",
                    gstin="27AAACA1234A1Z5",
                    username="apex_user"
                )
                self.assertFalse(res["success"])
                self.assertEqual(res["error"], "The OTP entered is incorrect or has expired. Please check and try again.")

    # -------------------------------------------------------------
    # 8. Expired OTP
    # -------------------------------------------------------------
    def test_08_expired_otp(self):
        """Verify normalized error when OTP has expired."""
        expired_otp_response = {
            "success": False,
            "status_code": 400,
            "error": "The OTP has expired. Please request a new OTP.",
            "correlation_id": "CORR_EXP_OTP"
        }

        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=expired_otp_response):
                res = GSTPortalService.verify_portal_otp(
                    company=self.company,
                    otp="999999",
                    gstin="27AAACA1234A1Z5",
                    username="apex_user"
                )
                self.assertFalse(res["success"])
                self.assertEqual(res["error"], "The OTP entered is incorrect or has expired. Please check and try again.")

    # -------------------------------------------------------------
    # 9. Successful OTP Verification
    # -------------------------------------------------------------
    def test_09_successful_otp_verification(self):
        """Verify OTP verification persists token and activates connected status."""
        future_expiry_ms = int((time.time() + 21600) * 1000)  # 6 hours ahead
        verify_success = {
            "success": True,
            "status_code": 200,
            "data": {
                "auth_token": "gsp_live_taxpayer_token_xyz",
                "session_expiry": future_expiry_ms,
                "token_expiry": future_expiry_ms,
                "status_cd": "1",
                "gstin": "27AAACA1234A1Z5"
            },
            "correlation_id": "CORR_VERIFY_OK"
        }

        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=verify_success):
                res = GSTPortalService.verify_portal_otp(
                    company=self.company,
                    otp="582109",
                    gstin="27AAACA1234A1Z5",
                    username="apex_user"
                )
                self.assertTrue(res["success"])

                # Verify database state
                config = CompanyGSTConfig.objects.get(company=self.company)
                self.assertEqual(config.auth_token, "gsp_live_taxpayer_token_xyz")
                self.assertIsNotNone(config.token_expires_at)
                self.assertTrue(config.token_expires_at > timezone.now())
                self.assertEqual(config.eway_username, "apex_user")

                # Verify API View reports connected
                request = self.factory.get(f"/api/v1/gst/config/{self.company.id}/")
                force_authenticate(request, user=self.user)
                view = CompanyGSTConfigAPIView.as_view()
                api_res = view(request, company_id=str(self.company.id))
                self.assertTrue(api_res.data["config"]["is_portal_connected"])

    # -------------------------------------------------------------
    # 10. Expired Taxpayer Session
    # -------------------------------------------------------------
    def test_10_expired_taxpayer_session(self):
        """Verify that an expired session token is recognized as NOT connected."""
        config, _ = CompanyGSTConfig.objects.get_or_create(company=self.company)
        config.auth_token = "stale_token_from_yesterday"
        config.token_expires_at = timezone.now() - timedelta(hours=2)
        config.save()

        request = self.factory.get(f"/api/v1/gst/config/{self.company.id}/")
        force_authenticate(request, user=self.user)
        view = CompanyGSTConfigAPIView.as_view()
        api_res = view(request, company_id=str(self.company.id))

        self.assertFalse(api_res.data["config"]["is_portal_connected"])

    # -------------------------------------------------------------
    # 11. Company Switching & Configuration Isolation
    # -------------------------------------------------------------
    def test_11_company_switching(self):
        """Verify switching between companies loads isolated credentials and does not cross-contaminate."""
        # Setup Company A as connected
        config_a, _ = CompanyGSTConfig.objects.get_or_create(company=self.company)
        config_a.auth_token = "token_company_a"
        config_a.token_expires_at = timezone.now() + timedelta(hours=5)
        config_a.eway_username = "username_a"
        config_a.save()

        # Setup Company B as disconnected
        config_b, _ = CompanyGSTConfig.objects.get_or_create(company=self.other_company)
        config_b.auth_token = ""
        config_b.token_expires_at = None
        config_b.eway_username = ""
        config_b.save()

        # Fetch Company A config
        req_a = self.factory.get(f"/api/v1/gst/config/{self.company.id}/")
        force_authenticate(req_a, user=self.user)
        view = CompanyGSTConfigAPIView.as_view()
        res_a = view(req_a, company_id=str(self.company.id))

        self.assertTrue(res_a.data["config"]["is_portal_connected"])
        self.assertEqual(res_a.data["config"]["portal_username"], "username_a")

        # Fetch Company B config
        req_b = self.factory.get(f"/api/v1/gst/config/{self.other_company.id}/")
        force_authenticate(req_b, user=self.other_user)
        res_b = view(req_b, company_id=str(self.other_company.id))

        self.assertFalse(res_b.data["config"]["is_portal_connected"])
        self.assertEqual(res_b.data["config"]["portal_username"], "")

    # -------------------------------------------------------------
    # 12. Cross-Company Token Access Prevention (RBAC)
    # -------------------------------------------------------------
    def test_12_cross_company_token_access(self):
        """Verify user of Company B cannot read or modify Company A's GST configuration or session."""
        request = self.factory.get(f"/api/v1/gst/config/{self.company.id}/")
        force_authenticate(request, user=self.other_user)
        view = CompanyGSTConfigAPIView.as_view()
        response = view(request, company_id=str(self.company.id))

        self.assertIn(response.status_code, [403, 404])

    # -------------------------------------------------------------
    # 13. Token Refresh and Logout Flow
    # -------------------------------------------------------------
    def test_13_token_refresh_and_logout(self):
        """Verify session token extension and remote logout invalidate session."""
        config, _ = CompanyGSTConfig.objects.get_or_create(company=self.company)
        config.auth_token = "initial_session_token"
        config.token_expires_at = timezone.now() + timedelta(hours=1)
        config.save()

        # 1. Test Refresh
        new_expiry_ms = int((time.time() + 21600) * 1000)
        refresh_success = {
            "success": True,
            "status_code": 200,
            "data": {
                "access_token": "refreshed_session_token_abc",
                "session_expiry": new_expiry_ms,
                "token_expiry": new_expiry_ms,
                "status_cd": "1"
            }
        }
        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "refresh_portal_session", return_value=refresh_success):
                res_refresh = GSTPortalService.refresh_portal_session(self.company)
                self.assertTrue(res_refresh["success"])

                config.refresh_from_db()
                self.assertEqual(config.auth_token, "refreshed_session_token_abc")

        # 2. Test Logout / Disconnect
        logout_success = {
            "success": True,
            "status_code": 200,
            "data": {"status_cd": "1"}
        }
        with patch.object(SandboxGSTClient, "is_configured", return_value=True):
            with patch.object(SandboxGSTClient, "logout_portal_session", return_value=logout_success):
                res_logout = GSTPortalService.disconnect_portal_session(self.company)
                self.assertTrue(res_logout["success"])

                config.refresh_from_db()
                self.assertEqual(config.auth_token, "")
                self.assertIsNone(config.token_expires_at)

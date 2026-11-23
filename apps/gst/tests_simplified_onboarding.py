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
from apps.gst.services.gst_error_normalizer import (
    normalize_gst_error,
    get_structured_gst_error,
    PORTAL_HELP_GUIDE,
)
from apps.gst.services.gst_sandbox_service import GSTPortalService
from apps.gst.views import (
    GSTRDirectPortalPreflightAPIView,
    GSTRDirectPortalOTPRequestAPIView,
    GSTRDirectPortalVerifyOTPAPIView,
    GSTRDirectPortalDisconnectAPIView,
    GSTRDirectPortalRefreshSessionAPIView,
)

User = get_user_model()

# Dedicated Sandbox Company Invariant
SANDBOX_COMPANY_ID = "4e62863a-08f9-4e99-b0bd-64873acfdd33"
PROTECTED_PROD_TENANT_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"


class GSTSimplifiedOnboardingRegressionTests(TestCase):
    """
    Authoritative test suite for SriLekh GST Portal Simplified Taxpayer Onboarding:
    - Phase 1: GSP/ASP authorization mapping (Quicko Infosoft Private Limited)
    - Phase 2: Automatic preflight checks (GSTIN presence, format, session state)
    - Phase 3: Simplified onboarding UX contract & portal help guidance
    - Phase 4: Intelligent error classification (API_ACCESS_DISABLED, GSP_AUTH_MISSING, etc.)
    - Phase 5: Authentication lifecycle (session refresh, logout, isolation)
    - Phase 6: Production abstraction & zero credential leaks
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
                "gstin": "09AAACA1234A1Z5",
                "state_code": "09",
            }
        )
        assert str(self.company.id) == SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"

        # Create isolated second tenant
        self.other_company = Company.objects.create(
            name="Apex Tooling Store (Secondary)",
            legal_name="Apex Tooling Store Pvt Ltd",
            gstin="27BBBCB5678B1Z9",
            state_code="27",
        )

        # Create test user with permissions
        self.user = User.objects.create_user(
            email="testowner@example.com",
            password="securePassword123!",
            first_name="Sandbox",
            last_name="Tester",
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="ADMIN")
        UserCompany.objects.create(user=self.user, company=self.other_company, role="ADMIN")

        self.factory = APIRequestFactory()

        # Initialize CompanyGSTConfig
        self.config, _ = CompanyGSTConfig.objects.get_or_create(
            company=self.company,
            defaults={
                "provider": "SANDBOX_CO_IN",
                "is_sandbox": False,
            }
        )
        self.other_config, _ = CompanyGSTConfig.objects.get_or_create(
            company=self.other_company,
            defaults={
                "provider": "SANDBOX_CO_IN",
                "is_sandbox": False,
            }
        )

    # -------------------------------------------------------------------------
    # TEST 1: MANDATORY TEST ISOLATION INVARIANT
    # -------------------------------------------------------------------------
    def test_01_mandatory_test_isolation_invariant(self):
        """Verify strict isolation from protected production accounts."""
        self.assertEqual(str(self.company.id), SANDBOX_COMPANY_ID)
        self.assertNotEqual(str(self.company.id), PROTECTED_PROD_TENANT_ID)

        prod_exists = Company.objects.filter(id=PROTECTED_PROD_TENANT_ID).exists()
        self.assertFalse(
            prod_exists,
            "Protected production tenant Maa Annapurna Belting Store must NEVER exist in test DB!"
        )

    # -------------------------------------------------------------------------
    # TEST 2: PREFLIGHT CHECK — GSTIN MISSING
    # -------------------------------------------------------------------------
    def test_02_preflight_gstin_missing(self):
        """When company has no GSTIN, preflight returns GSTIN_MISSING with actionable guide."""
        no_gstin_company = Company.objects.create(
            name="Unregistered Enterprise",
            gstin="",
            state_code="09",
        )
        UserCompany.objects.create(user=self.user, company=no_gstin_company, role="ADMIN")

        view = GSTRDirectPortalPreflightAPIView.as_view()
        request = self.factory.get(f"/api/v1/gst/portal/preflight/{no_gstin_company.id}/")
        force_authenticate(request, user=self.user)
        response = view(request, company_id=no_gstin_company.id)

        self.assertEqual(response.status_code, 200)
        data = response.data.get("preflight", {})
        self.assertFalse(data.get("eligible"))
        self.assertEqual(data.get("code"), "GSTIN_MISSING")
        self.assertEqual(data.get("action"), "CONFIGURE_GSTIN")
        self.assertIn("15-character GSTIN", data.get("message"))

    # -------------------------------------------------------------------------
    # TEST 3: PREFLIGHT CHECK — GSTIN INVALID FORMAT
    # -------------------------------------------------------------------------
    def test_03_preflight_gstin_invalid_format(self):
        """When company has invalid GSTIN format, preflight returns GSTIN_INVALID_FORMAT."""
        bad_gstin_company = Company.objects.create(
            name="Malformed GSTIN Corp",
            gstin="INVALID_GSTIN_123",
            state_code="09",
        )
        UserCompany.objects.create(user=self.user, company=bad_gstin_company, role="ADMIN")

        view = GSTRDirectPortalPreflightAPIView.as_view()
        request = self.factory.get(f"/api/v1/gst/portal/preflight/{bad_gstin_company.id}/")
        force_authenticate(request, user=self.user)
        response = view(request, company_id=bad_gstin_company.id)

        self.assertEqual(response.status_code, 200)
        data = response.data.get("preflight", {})
        self.assertFalse(data.get("eligible"))
        self.assertEqual(data.get("code"), "GSTIN_INVALID_FORMAT")
        self.assertEqual(data.get("action"), "CONFIGURE_GSTIN")

    # -------------------------------------------------------------------------
    # TEST 4: PREFLIGHT CHECK — SUCCESS & OFFICIAL GSP MAPPING
    # -------------------------------------------------------------------------
    def test_04_preflight_success_and_portal_help_guide(self):
        """When company has valid GSTIN, preflight returns eligible=True with confirmed GSP guide."""
        view = GSTRDirectPortalPreflightAPIView.as_view()
        request = self.factory.get(f"/api/v1/gst/portal/preflight/{self.company.id}/")
        force_authenticate(request, user=self.user)
        response = view(request, company_id=self.company.id)

        self.assertEqual(response.status_code, 200)
        data = response.data.get("preflight", {})
        self.assertTrue(data.get("eligible"))
        self.assertFalse(data.get("is_connected"))
        self.assertEqual(data.get("gstin"), "09AAACA1234A1Z5")

        # Verify exact confirmed GSP legal name and portal URL
        help_guide = data.get("portal_help", {})
        self.assertEqual(help_guide.get("gsp_name"), "Quicko Infosoft Private Limited")
        self.assertEqual(help_guide.get("url"), "https://services.gst.gov.in")
        self.assertIn("Quicko Infosoft Private Limited", help_guide.get("steps", [])[4])

    # -------------------------------------------------------------------------
    # TEST 5: INTELLIGENT ERROR DETECTION — API ACCESS DISABLED
    # -------------------------------------------------------------------------
    @patch.object(SandboxGSTClient, 'is_configured', return_value=True)
    @patch.object(SandboxGSTClient, 'request_portal_otp')
    def test_05_intelligent_detection_api_access_disabled(self, mock_request_otp, mock_configured):
        """When taxpayer has not enabled API access on portal, return mandated error copy."""
        mock_request_otp.return_value = {
            "success": False,
            "status_code": 400,
            "error": "API access is disabled for this GSTIN. Please enable API access from the GST Common Portal.",
            "correlation_id": "CORR-API-DISABLED-001"
        }

        view = GSTRDirectPortalOTPRequestAPIView.as_view()
        request = self.factory.post(
            "/api/v1/gst/portal/request-otp/",
            data={
                "company_id": str(self.company.id),
                "gstin": "09AAACA1234A1Z5",
                "username": "09AAACA1234A1Z5",
            },
            format="json"
        )
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data.get("success"))
        self.assertEqual(response.data.get("code"), "API_ACCESS_DISABLED")
        self.assertEqual(response.data.get("action"), "ENABLE_PORTAL_API_ACCESS")

        # Verify mandated customer-facing message
        expected_msg = (
            "GST API access is currently disabled for this GST registration. "
            "Please enable API access in your GST Portal account and try again."
        )
        self.assertEqual(response.data.get("error"), expected_msg)

        # Verify portal guide is provided
        portal_help = response.data.get("portal_help")
        self.assertIsNotNone(portal_help)
        self.assertEqual(portal_help.get("gsp_name"), "Quicko Infosoft Private Limited")

    # -------------------------------------------------------------------------
    # TEST 6: INTELLIGENT ERROR DETECTION — GSP/ASP AUTHORIZATION MISSING
    # -------------------------------------------------------------------------
    @patch.object(SandboxGSTClient, 'is_configured', return_value=True)
    @patch.object(SandboxGSTClient, 'request_portal_otp')
    def test_06_intelligent_detection_gsp_auth_missing(self, mock_request_otp, mock_configured):
        """When GSP authorization mapping is missing on portal, identify GSP_AUTH_MISSING."""
        mock_request_otp.return_value = {
            "success": False,
            "status_code": 400,
            "error": "GSP authorization missing or not mapped for this taxpayer.",
            "correlation_id": "CORR-GSP-MISSING-002"
        }

        view = GSTRDirectPortalOTPRequestAPIView.as_view()
        request = self.factory.post(
            "/api/v1/gst/portal/request-otp/",
            data={
                "company_id": str(self.company.id),
                "gstin": "09AAACA1234A1Z5",
                "username": "09AAACA1234A1Z5",
            },
            format="json"
        )
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "GSP_AUTH_MISSING")
        self.assertEqual(response.data.get("action"), "ENABLE_PORTAL_API_ACCESS")
        self.assertIn("Quicko Infosoft Private Limited", response.data.get("message", response.data.get("error", "")))

    # -------------------------------------------------------------------------
    # TEST 7: INTELLIGENT ERROR DETECTION — INVALID USERNAME
    # -------------------------------------------------------------------------
    @patch.object(SandboxGSTClient, 'is_configured', return_value=True)
    @patch.object(SandboxGSTClient, 'request_portal_otp')
    def test_07_intelligent_detection_invalid_username(self, mock_request_otp, mock_configured):
        """When taxpayer username is invalid or not found on portal, return INVALID_USERNAME."""
        mock_request_otp.return_value = {
            "success": False,
            "status_code": 400,
            "error": "Taxpayer not found with given username in GSTN records.",
            "correlation_id": "CORR-BAD-USER-003"
        }

        view = GSTRDirectPortalOTPRequestAPIView.as_view()
        request = self.factory.post(
            "/api/v1/gst/portal/request-otp/",
            data={
                "company_id": str(self.company.id),
                "gstin": "09AAACA1234A1Z5",
                "username": "WRONG_PORTAL_USER",
            },
            format="json"
        )
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "INVALID_USERNAME")
        self.assertEqual(response.data.get("action"), "RECHECK_USERNAME")
        self.assertIn("username", response.data.get("error", "").lower())

    # -------------------------------------------------------------------------
    # TEST 8: INTELLIGENT ERROR DETECTION — INCORRECT AND EXPIRED OTP
    # -------------------------------------------------------------------------
    @patch.object(SandboxGSTClient, 'is_configured', return_value=True)
    @patch.object(SandboxGSTClient, 'verify_portal_otp')
    def test_08_intelligent_detection_incorrect_and_expired_otp(self, mock_verify, mock_configured):
        """Distinguish between incorrect OTP vs expired OTP with correct error codes."""
        # Case A: Incorrect OTP
        mock_verify.return_value = {
            "success": False,
            "status_code": 400,
            "error": "Invalid OTP entered by user.",
            "correlation_id": "CORR-BAD-OTP-004"
        }

        view = GSTRDirectPortalVerifyOTPAPIView.as_view()
        request = self.factory.post(
            "/api/v1/gst/portal/verify-otp/",
            data={
                "company_id": str(self.company.id),
                "otp": "123456",
                "gstin": "09AAACA1234A1Z5",
            },
            format="json"
        )
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "INCORRECT_OTP")
        self.assertEqual(response.data.get("action"), "REENTER_OTP")

        # Case B: Expired OTP
        cache.clear()
        mock_verify.return_value = {
            "success": False,
            "status_code": 400,
            "error": "OTP has expired. Please request a new OTP.",
            "correlation_id": "CORR-EXP-OTP-005"
        }
        request_exp = self.factory.post(
            "/api/v1/gst/portal/verify-otp/",
            data={
                "company_id": str(self.company.id),
                "otp": "654321",
                "gstin": "09AAACA1234A1Z5",
            },
            format="json"
        )
        force_authenticate(request_exp, user=self.user)
        response_exp = view(request_exp)

        self.assertEqual(response_exp.status_code, 400)
        self.assertEqual(response_exp.data.get("code"), "EXPIRED_OTP")
        self.assertEqual(response_exp.data.get("action"), "REQUEST_NEW_OTP")

    # -------------------------------------------------------------------------
    # TEST 9: AUTHENTICATION LIFECYCLE — REFRESH & REMOTE LOGOUT
    # -------------------------------------------------------------------------
    @patch.object(SandboxGSTClient, 'is_configured', return_value=True)
    @patch.object(SandboxGSTClient, 'refresh_portal_session')
    @patch.object(SandboxGSTClient, 'logout_portal_session')
    def test_09_session_refresh_and_logout(self, mock_logout, mock_refresh, mock_configured):
        """Test session refresh extends expiry and logout invalidates and clears session token."""
        # 1. Establish initial active session
        self.config.auth_token = "EXISTING-SESSION-TOKEN-999"
        self.config.token_expires_at = timezone.now() + timedelta(hours=2)
        self.config.save(update_fields=['auth_token', 'token_expires_at'])

        # 2. Refresh session
        new_expiry_ms = int((time.time() + 21600) * 1000)
        mock_refresh.return_value = {
            "success": True,
            "data": {
                "access_token": "REFRESHED-SESSION-TOKEN-888",
                "session_expiry": new_expiry_ms
            }
        }

        refresh_view = GSTRDirectPortalRefreshSessionAPIView.as_view()
        req_refresh = self.factory.post(
            "/api/v1/gst/portal/refresh/",
            data={"company_id": str(self.company.id)},
            format="json"
        )
        force_authenticate(req_refresh, user=self.user)
        res_refresh = refresh_view(req_refresh)

        self.assertEqual(res_refresh.status_code, 200)
        self.assertTrue(res_refresh.data.get("success"))

        self.config.refresh_from_db()
        self.assertEqual(self.config.auth_token, "REFRESHED-SESSION-TOKEN-888")

        # 3. Disconnect (Remote Logout)
        mock_logout.return_value = {"success": True}
        disconnect_view = GSTRDirectPortalDisconnectAPIView.as_view()
        req_disc = self.factory.post(
            "/api/v1/gst/portal/disconnect/",
            data={"company_id": str(self.company.id)},
            format="json"
        )
        force_authenticate(req_disc, user=self.user)
        res_disc = disconnect_view(req_disc)

        self.assertEqual(res_disc.status_code, 200)
        self.assertTrue(res_disc.data.get("success"))

        self.config.refresh_from_db()
        self.assertEqual(self.config.auth_token, "")
        self.assertIsNone(self.config.token_expires_at)
        mock_logout.assert_called_once_with(session_token="REFRESHED-SESSION-TOKEN-888")

    # -------------------------------------------------------------------------
    # TEST 10: MULTI-COMPANY ISOLATION — CROSS-COMPANY BOUNDARY INTEGRITY
    # -------------------------------------------------------------------------
    def test_10_multi_company_token_isolation(self):
        """Ensure Company A's active session is never shared or leaked to Company B."""
        # Company A is connected
        self.config.auth_token = "COMPANY-A-SECRET-SESSION-TOKEN"
        self.config.token_expires_at = timezone.now() + timedelta(hours=6)
        self.config.save(update_fields=['auth_token', 'token_expires_at'])

        # Company B is not connected
        self.other_config.auth_token = ""
        self.other_config.token_expires_at = None
        self.other_config.save(update_fields=['auth_token', 'token_expires_at'])

        view = GSTRDirectPortalPreflightAPIView.as_view()

        # Query Company A
        req_a = self.factory.get(f"/api/v1/gst/portal/preflight/{self.company.id}/")
        force_authenticate(req_a, user=self.user)
        res_a = view(req_a, company_id=self.company.id)
        self.assertTrue(res_a.data["preflight"]["is_connected"])

        # Query Company B
        req_b = self.factory.get(f"/api/v1/gst/portal/preflight/{self.other_company.id}/")
        force_authenticate(req_b, user=self.user)
        res_b = view(req_b, company_id=self.other_company.id)
        self.assertFalse(res_b.data["preflight"]["is_connected"])
        self.assertIsNone(res_b.data["preflight"]["token_expires_at"])

import json
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.companies.models import Company, UserCompany
from apps.gst.models import (
    CompanyGSTConfig,
    GSTRegistration,
    GSTFilingRecord,
    GSTAuditLog,
)
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gst_error_normalizer import (
    normalize_gst_error,
    sanitize_audit_payload,
    redact_sensitive_str,
)
from apps.gst.services.gst_sandbox_service import GSTPortalService
from apps.gst.views import (
    CompanyGSTConfigTestConnectionAPIView,
    GSTRDirectPortalPreflightAPIView,
    GSTRDirectPortalOTPRequestAPIView,
    GSTRDirectPortalVerifyOTPAPIView,
    GSTRDirectPortalUploadGSTR1APIView,
    GSTRDirectPortalStatusAPIView,
    GSTRDirectPortalDisconnectAPIView,
    GSTRDirectPortalRefreshSessionAPIView,
)

User = get_user_model()

# STRICT MANDATE: Dedicated Sandbox Company Invariant
SANDBOX_COMPANY_ID = "4e62863a-08f9-4e99-b0bd-64873acfdd33"
PROTECTED_PROD_TENANT_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"


class GSTRound2517IntegrityTests(TestCase):
    """
    SriLekh GST Round 2.5.17: Independent Production Certification Test Suite.
    Enforces:
    - Phase A: Authentication Token Integrity & strict schema validation
    - Phase B: Multi-GSTIN session and token isolation
    - Phase C: GSTR-1 direct filing safety, state machine, zero fabricated ARNs, zero hardcoded OTPs
    - Phase D: Gateway configuration & preflight status separation
    - Phase E: Safe error normalization & audit log credential redaction
    - Phase F: Atomic rate limiting & cryptographically bound challenge validation
    - Phase G: Disconnect and session refresh semantics
    """

    def setUp(self):
        cache.clear()

        # Invariant check: Assert we never touch production tenant
        self.assertNotEqual(SANDBOX_COMPANY_ID, PROTECTED_PROD_TENANT_ID)

        # Create or fetch dedicated sandbox company
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

        self.user = User.objects.create_user(
            email="auditor@apexbelting.demo",
            password="SecureAuditPassword123!",
            first_name="Apex",
            last_name="Auditor",
            is_staff=False,
            is_superuser=False,
        )
        self.staff_user = User.objects.create_user(
            email="admin@apexbelting.demo",
            password="SecureAdminPassword123!",
            first_name="Apex",
            last_name="Admin",
            is_staff=True,
            is_superuser=True,
        )
        UserCompany.objects.create(
            user=self.user,
            company=self.company,
            role="OWNER",
        )

        self.config, _ = CompanyGSTConfig.objects.get_or_create(
            company=self.company,
            defaults={
                "provider": "SANDBOX_CO_IN",
                "is_sandbox": True,
                "sandbox_api_key": "key_live_apex_test_credentials_12345",
                "sandbox_api_secret": "sec_live_apex_test_secret_67890",
                "sandbox_base_url": "https://api.sandbox.co.in",
            }
        )
        self.factory = APIRequestFactory()

    # =========================================================================
    # PHASE A: AUTHENTICATION TOKEN INTEGRITY (P0)
    # =========================================================================

    def test_auth_rejects_missing_access_token(self):
        """Reject authentication when provider returns no session token."""
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
            },
            "correlation_id": "corr-test-001"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "INVALID_SESSION_TOKEN")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_correlation_id_as_token(self):
        """CRITICAL: Reject correlation_id from being used as auth_token."""
        cid = "corr-uuid-12345678-abcd"
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": cid,  # Provider returned correlation_id inside auth_token field
                "expiry": (timezone.now() + timedelta(hours=6)).isoformat(),
            },
            "correlation_id": cid
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "INVALID_SESSION_TOKEN")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_status_cd_zero(self):
        """Reject authentication when provider returns HTTP 200 with status_cd=0 or failed status."""
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "0",
                "status": "failed",
                "error": {"message": "Invalid OTP", "error_cd": "AUTH404"},
                "auth_token": "valid_looking_token_that_should_be_ignored"
            },
            "correlation_id": "corr-test-003"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="000000",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_missing_expiry(self):
        """Reject authentication when token is present but expiry is missing."""
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "valid_session_token_xyz_1234567890",
                # Missing expiry / expires_at
            },
            "correlation_id": "corr-test-004"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "INVALID_EXPIRY")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_malformed_expiry(self):
        """Reject authentication when expiry cannot be parsed into a valid timestamp."""
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "valid_session_token_xyz_1234567890",
                "expiry": "not-a-valid-timestamp-format"
            },
            "correlation_id": "corr-test-005"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "INVALID_EXPIRY")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_past_expiry(self):
        """Reject authentication when expiry is already in the past."""
        past_time = (timezone.now() - timedelta(minutes=5)).isoformat()
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "valid_session_token_xyz_1234567890",
                "expiry": past_time
            },
            "correlation_id": "corr-test-006"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "INVALID_EXPIRY")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_gstin_mismatch(self):
        """Reject authentication when returned taxpayer GSTIN does not match requested GSTIN."""
        future_time = (timezone.now() + timedelta(hours=6)).isoformat()
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "valid_session_token_xyz_1234567890",
                "expiry": future_time,
                "gstin": "27OTHERGSTIN1234"  # Mismatched GSTIN
            },
            "correlation_id": "corr-test-007"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "GSTIN_MISMATCH")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_auth_rejects_short_token(self):
        """Reject authentication when token length is < 10 characters."""
        future_time = (timezone.now() + timedelta(hours=6)).isoformat()
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "short",
                "expiry": future_time,
            },
            "correlation_id": "corr-test-008"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "INVALID_SESSION_TOKEN")

    def test_auth_success_stores_valid_session(self):
        """Genuine token and valid expiry successfully creates an active session."""
        future_time = (timezone.now() + timedelta(hours=6)).isoformat()
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "genuine_taxpayer_session_token_abc123456789",
                "expiry": future_time,
                "gstin": "09AAACA1234A1Z5",
            },
            "correlation_id": "corr-test-009"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="09AAACA1234A1Z5",
            )
            self.assertTrue(res["success"])
            self.assertTrue(res["is_connected"])
            self.assertTrue(GSTPortalService.has_active_portal_session(self.company))

    # =========================================================================
    # PHASE B: MULTI-GSTIN SESSION ISOLATION (P0)
    # =========================================================================

    def test_multi_gstin_session_isolation(self):
        """Authentication for GSTIN A cannot authorize filing or session for GSTIN B under same company."""
        reg_a = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            state_code="09",
            legal_name="Apex Belting UP",
            taxpayer_type="REGULAR",
            is_primary=True,
        )
        reg_b = GSTRegistration.objects.create(
            company=self.company,
            gstin="27AAACA1234A1Z6",
            state_code="27",
            legal_name="Apex Belting MH",
            taxpayer_type="REGULAR",
            is_primary=False,
        )

        future_time = (timezone.now() + timedelta(hours=6)).isoformat()
        mock_response = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "token_for_reg_a_only_1234567890",
                "expiry": future_time,
                "gstin": reg_a.gstin,
            },
            "correlation_id": "corr-multi-a"
        }
        with patch.object(SandboxGSTClient, "verify_portal_otp", return_value=mock_response):
            res_a = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin=reg_a.gstin,
            )
            self.assertTrue(res_a["success"])

        # Refresh from DB
        reg_a.refresh_from_db()
        reg_b.refresh_from_db()

        self.assertTrue(reg_a.has_active_portal_session())
        self.assertFalse(reg_b.has_active_portal_session())

        # Preflight for Reg B must show NO active session
        pf_b = GSTPortalService.get_preflight_status(self.company, gstin=reg_b.gstin)
        self.assertFalse(pf_b["has_active_session"])
        self.assertFalse(pf_b["is_connected"])

        # Attempt to upload GSTR-1 for Reg B must fail with AUTHENTICATION_REQUIRED
        upload_b = GSTPortalService.upload_gstr1_direct(
            company=self.company,
            start_date="2026-04-01",
            end_date="2026-04-30",
            gstin=reg_b.gstin,
        )
        self.assertFalse(upload_b["success"])
        self.assertEqual(upload_b["code"], "AUTHENTICATION_REQUIRED")

    # =========================================================================
    # PHASE C: GSTR-1 FILING SAFETY (P0)
    # =========================================================================

    def test_filing_rejects_without_session(self):
        """Uploading GSTR-1 without an active session returns structured AUTHENTICATION_REQUIRED error."""
        self.config.auth_token = ""
        self.config.token_expires_at = None
        self.config.save()

        res = GSTPortalService.upload_gstr1_direct(
            company=self.company,
            start_date="2026-04-01",
            end_date="2026-04-30",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "AUTHENTICATION_REQUIRED")

    def test_filing_rejects_expired_session(self):
        """Uploading GSTR-1 with an expired token returns AUTHENTICATION_REQUIRED."""
        self.config.auth_token = "valid_looking_token_1234567890"
        self.config.token_expires_at = timezone.now() - timedelta(hours=1)
        self.config.save()

        res = GSTPortalService.upload_gstr1_direct(
            company=self.company,
            start_date="2026-04-01",
            end_date="2026-04-30",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "AUTHENTICATION_REQUIRED")

    def test_filing_never_uses_hardcoded_otp(self):
        """Verify that verify_portal_otp is NEVER automatically called with 575757."""
        with patch.object(GSTPortalService, "verify_portal_otp") as mock_verify:
            res = GSTPortalService.upload_gstr1_direct(
                company=self.company,
                start_date="2026-04-01",
                end_date="2026-04-30",
            )
            self.assertFalse(res["success"])
            mock_verify.assert_not_called()

    def test_filing_rejects_synthetic_arn_and_requires_genuine_arn(self):
        """CRITICAL: Ensure REF-G1-... or synthetic UUID is NEVER persisted as government ARN."""
        self.config.auth_token = "active_session_token_1234567890"
        self.config.token_expires_at = timezone.now() + timedelta(hours=4)
        self.config.save()

        # Provider returns submission acknowledgement with reference_id, but NO government ARN yet
        mock_provider_res = {
            "success": True,
            "status_code": 200,
            "data": {
                "reference_id": "REF-G1-9988776655",
                # Note: No government ARN
            }
        }
        with patch.object(SandboxGSTClient, "save_gstr1", return_value=mock_provider_res):
            res = GSTPortalService.upload_gstr1_direct(
                company=self.company,
                start_date="2026-04-01",
                end_date="2026-04-30",
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "SUBMITTED")
            # ARN must NOT be synthetic REF-G1-...
            self.assertEqual(res.get("arn"), "")
            self.assertEqual(res.get("ref_id"), "REF-G1-9988776655")

            record = GSTFilingRecord.objects.filter(
                company=self.company,
                return_period="202604",
                return_type="GSTR1"
            ).first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "SUBMITTED")
            self.assertEqual(record.arn, "")  # Zero synthetic ARN

    def test_filing_status_failed_on_provider_rejection(self):
        """Provider 400 error records status FAILED, not SUBMITTED or FILED."""
        self.config.auth_token = "active_session_token_1234567890"
        self.config.token_expires_at = timezone.now() + timedelta(hours=4)
        self.config.save()

        mock_err_res = {
            "success": False,
            "status_code": 400,
            "error": "Invalid invoice HSN format in B2B table"
        }
        with patch.object(SandboxGSTClient, "save_gstr1", return_value=mock_err_res):
            res = GSTPortalService.upload_gstr1_direct(
                company=self.company,
                start_date="2026-05-01",
                end_date="2026-05-31",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "FAILED")

            record = GSTFilingRecord.objects.filter(
                company=self.company,
                return_period="202605",
                return_type="GSTR1"
            ).first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "FAILED")
            self.assertEqual(res["code"], "SUBMISSION_REJECTED")
            self.assertEqual(record.error_message, "Invalid invoice HSN format in B2B table")

    def test_filing_status_reconciliation_required_on_timeout(self):
        """Gateway timeout or unverified response records RECONCILIATION_REQUIRED, not FILED."""
        self.config.auth_token = "active_session_token_1234567890"
        self.config.token_expires_at = timezone.now() + timedelta(hours=4)
        self.config.save()

        mock_timeout_res = {
            "success": False,
            "status_code": 504,
            "error": "Connection to Sandbox failed: Timeout"
        }
        with patch.object(SandboxGSTClient, "save_gstr1", return_value=mock_timeout_res):
            res = GSTPortalService.upload_gstr1_direct(
                company=self.company,
                start_date="2026-06-01",
                end_date="2026-06-30",
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "RECONCILIATION_REQUIRED")

            record = GSTFilingRecord.objects.filter(
                company=self.company,
                return_period="202606",
                return_type="GSTR1"
            ).first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "RECONCILIATION_REQUIRED")

    def test_filing_success_persists_genuine_government_arn(self):
        """When official government ARN is returned, record becomes FILED with official ARN."""
        self.config.auth_token = "active_session_token_1234567890"
        self.config.token_expires_at = timezone.now() + timedelta(hours=4)
        self.config.save()

        genuine_arn = "AA090726000001Y"
        mock_success_res = {
            "success": True,
            "status_code": 200,
            "data": {
                "reference_id": "REF-G1-SUCCESS-1234",
                "arn": genuine_arn,
                "status": "FILED"
            }
        }
        with patch.object(SandboxGSTClient, "save_gstr1", return_value=mock_success_res):
            res = GSTPortalService.upload_gstr1_direct(
                company=self.company,
                start_date="2026-07-01",
                end_date="2026-07-31",
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "FILED")
            self.assertEqual(res["arn"], genuine_arn)

            record = GSTFilingRecord.objects.filter(
                company=self.company,
                return_period="202607",
                return_type="GSTR1"
            ).first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "FILED")
            self.assertEqual(record.arn, genuine_arn)

    def test_filing_prevents_duplicate_filing_when_already_filed(self):
        """Attempting to file for an already FILED period rejects with ALREADY_FILED."""
        self.config.auth_token = "active_session_token_1234567890"
        self.config.token_expires_at = timezone.now() + timedelta(hours=4)
        self.config.save()

        # Seed an already filed record
        GSTFilingRecord.objects.create(
            company=self.company,
            return_period="202608",
            return_type="GSTR1",
            status="FILED",
            arn="AA090826000002Z",
            filing_mode="PORTAL_DIRECT",
            submitted_at=timezone.now(),
        )

        res = GSTPortalService.upload_gstr1_direct(
            company=self.company,
            start_date="2026-08-01",
            end_date="2026-08-31",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "ALREADY_FILED")

    def test_filing_reconciliation_endpoint_updates_record_idempotently(self):
        """Reconciliation endpoint queries status and transitions SUBMITTED to FILED with official ARN."""
        self.config.auth_token = "active_session_token_1234567890"
        self.config.token_expires_at = timezone.now() + timedelta(hours=4)
        self.config.save()

        record = GSTFilingRecord.objects.create(
            company=self.company,
            return_period="202609",
            return_type="GSTR1",
            status="SUBMITTED",
            arn="",
            filing_mode="PORTAL_DIRECT",
            provider_reference="REF-G1-RECON-123",
            response_snapshot={"ref_id": "REF-G1-RECON-123"},
            submitted_at=timezone.now(),
        )

        genuine_arn = "AA090926000003X"
        mock_recon_res = {
            "success": True,
            "status_code": 200,
            "data": {
                "status": "PROCESSED",
                "arn": genuine_arn,
            }
        }
        with patch.object(SandboxGSTClient, "get_gstr_status", return_value=mock_recon_res):
            res = GSTPortalService.get_portal_status(
                company=self.company,
                ref_id="REF-G1-RECON-123",
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "FILED")
            self.assertEqual(res["arn"], genuine_arn)

            record.refresh_from_db()
            self.assertEqual(record.status, "FILED")
            self.assertEqual(record.arn, genuine_arn)

    # =========================================================================
    # PHASE D: CONFIGURATION & PREFLIGHT SEPARATION (P1)
    # =========================================================================

    def test_preflight_gateway_configured_false_when_missing_keys(self):
        """gateway_configured is False when API keys are absent."""
        self.config.sandbox_api_key = ""
        self.config.sandbox_api_secret = ""
        self.config.save()

        with patch.dict("os.environ", {}, clear=True):
            pf = GSTPortalService.get_preflight_status(self.company)
            self.assertFalse(pf["gateway_configured"])
            self.assertFalse(pf["is_connected"])
            self.assertFalse(pf["has_active_session"])

    def test_preflight_gateway_configured_false_when_invalid_url(self):
        """gateway_configured is False when base URL is not https or valid domain."""
        self.config.sandbox_base_url = "ftp://invalid-url.com"
        self.config.save()

        pf = GSTPortalService.get_preflight_status(self.company)
        self.assertFalse(pf["gateway_configured"])

    def test_preflight_separates_gateway_ready_from_session_active(self):
        """gateway_configured=True does NOT imply is_connected=True or has_active_session=True."""
        self.config.sandbox_api_key = "key_live_apex_test_12345"
        self.config.sandbox_api_secret = "sec_live_apex_test_67890"
        self.config.sandbox_base_url = "https://api.sandbox.co.in"
        self.config.auth_token = ""
        self.config.token_expires_at = None
        self.config.save()

        pf = GSTPortalService.get_preflight_status(self.company)
        self.assertTrue(pf["gateway_configured"])
        self.assertFalse(pf["is_connected"])
        self.assertFalse(pf["has_active_session"])

    # =========================================================================
    # PHASE E: AUDIT LOG SANITIZATION & ERROR NORMALIZATION (P1)
    # =========================================================================

    def test_audit_log_redacts_credentials(self):
        """Audit payload sanitizer replaces all secrets with ***REDACTED***."""
        payload = {
            "username": "09AAACA1234A1Z5",
            "password": "MySuperSecretPassword",
            "otp": "987654",
            "auth_token": "bearer_secret_token_12345",
            "access_token": "oauth_access_secret_67890",
            "nested": {
                "api_secret": "raw_secret_key",
                "client_secret": "oauth_client_secret"
            }
        }
        sanitized = sanitize_audit_payload(payload)
        self.assertEqual(sanitized["password"], "***REDACTED***")
        self.assertEqual(sanitized["otp"], "***REDACTED***")
        self.assertEqual(sanitized["auth_token"], "***REDACTED***")
        self.assertEqual(sanitized["access_token"], "***REDACTED***")
        self.assertEqual(sanitized["nested"]["api_secret"], "***REDACTED***")
        self.assertEqual(sanitized["nested"]["client_secret"], "***REDACTED***")

    def test_error_messages_contain_no_internal_urls_or_headers(self):
        """Error messages presented to end users contain zero internal infrastructure details."""
        raw_error = "Missing required request parameters: [x-source] at https://api.sandbox.co.in/gst/otp"
        normalized = normalize_gst_error(raw_error)
        self.assertNotIn("api.sandbox.co.in", normalized)
        self.assertNotIn("x-source", normalized)
        self.assertIn("GST Portal", normalized)

    # =========================================================================
    # PHASE F: ATOMIC RATE LIMITING & CHALLENGE BINDING (P1)
    # =========================================================================

    def test_otp_rate_limiting_enforces_cooldown(self):
        """Requesting OTP twice within 30s cooldown triggers COOLDOWN_ACTIVE."""
        mock_res = {
            "success": True,
            "status_code": 200,
            "data": {"txn_id": "TXN-RATE-001"}
        }
        with patch.object(SandboxGSTClient, "request_portal_otp", return_value=mock_res):
            res1 = GSTPortalService.request_portal_otp(self.company)
            self.assertTrue(res1["success"])

            # Immediate second request
            res2 = GSTPortalService.request_portal_otp(self.company)
            self.assertFalse(res2["success"])
            self.assertEqual(res2["code"], "COOLDOWN_ACTIVE")
            self.assertIn("Please wait", res2["error"])

    def test_challenge_binding_and_rejection(self):
        """Challenge token cannot be verified with wrong company or ownership mismatch."""
        cache.set(
            "gst_chal_WRONG_COMPANY",
            {
                "txn_id": "WRONG_COMPANY",
                "company_id": str(uuid.uuid4()),  # different company ID
                "gstin": "09AAACA1234A1Z5",
                "username": "09AAACA1234A1Z5",
                "attempts": 0,
            },
            timeout=600
        )
        res = GSTPortalService.verify_portal_otp(
            company=self.company,
            otp="123456",
            txn_id="WRONG_COMPANY",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "INVALID_CHALLENGE")

    def test_challenge_expired(self):
        """Expired or nonexistent challenge returns CHALLENGE_EXPIRED."""
        res = GSTPortalService.verify_portal_otp(
            company=self.company,
            otp="123456",
            txn_id="NON_EXISTENT_CHALLENGE",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "CHALLENGE_EXPIRED")

    # =========================================================================
    # PHASE G: DISCONNECT & REFRESH SEMANTICS (P1)
    # =========================================================================

    def test_disconnect_local_and_remote(self):
        """Disconnect revokes token locally and returns remote_status."""
        self.config.auth_token = "token_to_disconnect_12345"
        self.config.token_expires_at = timezone.now() + timedelta(hours=2)
        self.config.save()

        mock_logout_res = {"success": True, "status_code": 200, "data": {"status": "success"}}
        with patch.object(SandboxGSTClient, "logout_portal_session", return_value=mock_logout_res):
            res = GSTPortalService.disconnect_portal_session(self.company)
            self.assertTrue(res["success"])
            self.assertFalse(res["is_connected"])
            self.assertEqual(res["remote_status"], "CONFIRMED")
            self.assertFalse(GSTPortalService.has_active_portal_session(self.company))

    def test_refresh_session_extends_active_session(self):
        """Refresh session updates token and expiry."""
        self.config.auth_token = "token_to_refresh_12345"
        self.config.token_expires_at = timezone.now() + timedelta(minutes=30)
        self.config.save()

        future_time = (timezone.now() + timedelta(hours=6)).isoformat()
        mock_refresh_res = {
            "success": True,
            "status_code": 200,
            "data": {
                "status_cd": "1",
                "status": "success",
                "auth_token": "refreshed_session_token_67890",
                "expiry": future_time
            }
        }
        with patch.object(SandboxGSTClient, "refresh_portal_session", return_value=mock_refresh_res):
            res = GSTPortalService.refresh_portal_session(self.company)
            self.assertTrue(res["success"])
            self.assertEqual(res["token"], "refreshed_session_token_67890")

    # =========================================================================
    # PRODUCTION ABSTRACTION: DEVELOPER DIAGNOSTICS ACCESS CONTROL
    # =========================================================================

    def test_test_connection_restricted_from_ordinary_users(self):
        """Ordinary users cannot execute developer test connection diagnostic."""
        request = self.factory.post(f"/api/v1/gst/config/{self.company.id}/test-connection/")
        force_authenticate(request, user=self.user)
        view = CompanyGSTConfigTestConnectionAPIView.as_view()
        response = view(request, company_id=self.company.id)
        self.assertEqual(response.status_code, 403)
        self.assertIn("internal diagnostic tool", response.data["error"])

    def test_test_connection_accessible_to_staff_admins(self):
        """Staff administrators can execute developer test connection diagnostic."""
        request = self.factory.post(f"/api/v1/gst/config/{self.company.id}/test-connection/")
        force_authenticate(request, user=self.staff_user)
        view = CompanyGSTConfigTestConnectionAPIView.as_view()

        with patch("apps.gst.services.authentication_service.SandboxAuthenticationService.test_connection", return_value={"healthy": True, "message": "OK"}):
            response = view(request, company_id=self.company.id)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["healthy"])

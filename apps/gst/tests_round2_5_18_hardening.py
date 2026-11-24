import json
import uuid
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
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
from apps.gst.services.audit_service import (
    GSTAuditService,
    redact_sensitive_payload,
    sanitize_error_message,
)
from apps.gst.services.gst_sandbox_service import GSTPortalService
from apps.gst.views import (
    GSTRDirectPortalPreflightAPIView,
    GSTRDirectPortalOTPRequestAPIView,
    GSTRDirectPortalVerifyOTPAPIView,
    GSTRDirectPortalUploadGSTR1APIView,
    GSTRDirectPortalStatusAPIView,
    GSTRDirectPortalDisconnectAPIView,
    GSTRDirectPortalRefreshSessionAPIView,
    GSTRMarkPeriodFiledAPIView,
)

User = get_user_model()

# STRICT SYSTEM MANDATE: Dedicated Sandbox Company Invariant
SANDBOX_COMPANY_ID = "4e62863a-08f9-4e99-b0bd-64873acfdd33"
PROTECTED_PROD_TENANT_ID = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"


class GSTRound2518HardeningTests(TestCase):
    """
    SriLekh GST Round 2.5.18: Multi-GSTIN Isolation, Concurrency & State Machine Re-Certification.
    Adversarial verification suite covering:
    - Phase A: Multi-GSTIN Registration Resolution & Fail-Closed Token Isolation
    - Phase B: Multi-GSTIN Filing Scoping, Identity Constraints & Deletion Protection
    - Phase C: OTP Challenge Concurrency, Rate Limiting & User/Tenant Challenge Binding
    - Phase D: GSTR-1 Statutory State Machine & Reconciliation Idempotency
    - Phase E: Caller-Supplied Token Injection Elimination & Cross-Tenant Validation
    - Phase F: Sensitive Credential Redaction & Log Sanitization
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

        # Secondary test company for tenant isolation assertions
        self.other_company = Company.objects.create(
            name="Other Sandbox Company (Demo)",
            legal_name="Other Sandbox Industrial Pvt Ltd",
            gstin="27AAACA9999Z1Z1",
            state_code="27",
        )

        self.user = User.objects.create_user(
            email="auditor@apexbelting.demo",
            password="SecureAuditPassword123!",
            first_name="Apex",
            last_name="Auditor",
            is_staff=False,
        )
        self.other_user = User.objects.create_user(
            email="intruder@external.demo",
            password="SecureIntruderPassword123!",
            first_name="Intruder",
            last_name="User",
            is_staff=False,
        )

        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')
        UserCompany.objects.create(user=self.other_user, company=self.other_company, role='ADMIN')

        self.factory = APIRequestFactory()

    # =========================================================================
    # PHASE A: MULTI-GSTIN REGISTRATION ISOLATION & FAIL-CLOSED TOKEN RESOLUTION
    # =========================================================================

    def test_token_resolution_active_primary_reg(self):
        """Active primary registration returns its own token."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP Primary",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_primary_active_12345",
            token_expires_at=timezone.now() + timedelta(hours=6),
            taxpayer_username="apex_up_user",
        )
        sess = GSTPortalService.get_session_info(self.company)
        self.assertTrue(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "token_primary_active_12345")
        self.assertEqual(sess["gstin"], "09AAACA1234A1Z5")
        self.assertIsNone(sess["error_code"])

    def test_token_resolution_active_secondary_reg_explicit(self):
        """Resolving an explicit secondary registration returns that registration's isolated token."""
        GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP Primary",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_primary_12345",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        reg_dl = GSTRegistration.objects.create(
            company=self.company,
            gstin="07AAACA1234B1Z2",
            legal_name="Apex Delhi Branch",
            state_code="07",
            state_name="Delhi",
            status="ACTIVE",
            is_primary=False,
            auth_token="token_delhi_branch_67890",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )

        sess_dl = GSTPortalService.get_session_info(self.company, gstin="07AAACA1234B1Z2")
        self.assertTrue(sess_dl["is_connected"])
        self.assertEqual(sess_dl["auth_token"], "token_delhi_branch_67890")
        self.assertEqual(sess_dl["gstin"], "07AAACA1234B1Z2")
        self.assertNotEqual(sess_dl["auth_token"], "token_primary_12345")

    def test_token_resolution_unknown_gstin_fails_closed(self):
        """Explicit GSTIN not registered under the company fails closed with GSTIN_NOT_REGISTERED."""
        config = GSTPortalService.get_or_create_config(self.company)
        config.auth_token = "token_company_legacy_999"
        config.token_expires_at = timezone.now() + timedelta(hours=6)
        config.save()

        sess = GSTPortalService.get_session_info(self.company, gstin="24AAACA9999C1Z9")
        self.assertFalse(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "")
        self.assertEqual(sess["error_code"], "GSTIN_NOT_REGISTERED")

    def test_token_resolution_cross_company_gstin_fails_closed(self):
        """GSTIN registered under Company 2 queried under Company 1 fails closed."""
        GSTRegistration.objects.create(
            company=self.other_company,
            gstin="27AAACA9999Z1Z1",
            legal_name="Other Company Maharashtra",
            state_code="27",
            state_name="Maharashtra",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_other_company_secret",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )

        sess = GSTPortalService.get_session_info(self.company, gstin="27AAACA9999Z1Z1")
        self.assertFalse(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "")
        self.assertEqual(sess["error_code"], "GSTIN_NOT_REGISTERED")

    def test_token_resolution_inactive_reg_fails_closed(self):
        """Registration with status != ACTIVE fails closed with REGISTRATION_INACTIVE."""
        GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex Suspended Store",
            state_code="09",
            state_name="Uttar Pradesh",
            status="SUSPENDED",
            is_primary=True,
            auth_token="token_suspended_reg_xyz",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )

        sess = GSTPortalService.get_session_info(self.company, gstin="09AAACA1234A1Z5")
        self.assertFalse(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "")
        self.assertEqual(sess["error_code"], "REGISTRATION_INACTIVE")

    def test_token_resolution_multi_reg_no_primary_fails_closed(self):
        """Multi-registration company without an unambiguous primary registration returns AMBIGUOUS_GSTIN."""
        GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex Branch A",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=False,
            auth_token="token_a_12345",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        GSTRegistration.objects.create(
            company=self.company,
            gstin="07AAACA1234B1Z2",
            legal_name="Apex Branch B",
            state_code="07",
            state_name="Delhi",
            status="ACTIVE",
            is_primary=False,
            auth_token="token_b_67890",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )

        sess = GSTPortalService.get_session_info(self.company)
        self.assertFalse(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "")
        self.assertEqual(sess["error_code"], "AMBIGUOUS_GSTIN")

    def test_token_resolution_legacy_single_reg_fallback(self):
        """Company with 0 registrations falls back to config.auth_token for backward compatibility."""
        config = GSTPortalService.get_or_create_config(self.company)
        config.auth_token = "token_legacy_compat_123"
        config.token_expires_at = timezone.now() + timedelta(hours=4)
        config.save()

        sess = GSTPortalService.get_session_info(self.company)
        self.assertTrue(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "token_legacy_compat_123")
        self.assertEqual(sess["gstin"], "09AAACA1234A1Z5")

    def test_token_resolution_multi_reg_never_borrows_config_token(self):
        """Multi-registration company never bleeds or borrows config.auth_token."""
        config = GSTPortalService.get_or_create_config(self.company)
        config.auth_token = "token_config_leak_trap"
        config.token_expires_at = timezone.now() + timedelta(hours=4)
        config.save()

        # Registration without token
        GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex Branch A",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="",
        )
        GSTRegistration.objects.create(
            company=self.company,
            gstin="07AAACA1234B1Z2",
            legal_name="Apex Branch B",
            state_code="07",
            state_name="Delhi",
            status="ACTIVE",
            is_primary=False,
            auth_token="",
        )

        sess = GSTPortalService.get_session_info(self.company, gstin="09AAACA1234A1Z5")
        self.assertFalse(sess["is_connected"])
        self.assertEqual(sess["auth_token"], "")
        self.assertNotEqual(sess["auth_token"], "token_config_leak_trap")

    def test_token_expiry_in_past_marks_disconnected(self):
        """Token with expiry in the past is treated as expired and disconnected."""
        GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex Expired",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_expired_123",
            token_expires_at=timezone.now() - timedelta(minutes=5),
        )

        sess = GSTPortalService.get_session_info(self.company, gstin="09AAACA1234A1Z5")
        self.assertFalse(sess["is_connected"])
        self.assertTrue(sess["is_expired"])
        self.assertEqual(sess["auth_token"], "")

    def test_clear_session_token_scoped_to_registration(self):
        """Clearing token for GSTIN A does not affect GSTIN B."""
        reg_a = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex Branch A",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_a_keep",
            token_expires_at=timezone.now() + timedelta(hours=2),
        )
        reg_b = GSTRegistration.objects.create(
            company=self.company,
            gstin="07AAACA1234B1Z2",
            legal_name="Apex Branch B",
            state_code="07",
            state_name="Delhi",
            status="ACTIVE",
            is_primary=False,
            auth_token="token_b_clear",
            token_expires_at=timezone.now() + timedelta(hours=2),
        )

        GSTPortalService.clear_session_token(self.company, gstin="07AAACA1234B1Z2")

        reg_a.refresh_from_db()
        reg_b.refresh_from_db()
        self.assertEqual(reg_a.auth_token, "token_a_keep")
        self.assertEqual(reg_b.auth_token, "")

    def test_persist_session_token_scoped_to_registration(self):
        """Persisting session token writes strictly to target registration."""
        reg_a = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex Branch A",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_a_orig",
            token_expires_at=timezone.now() + timedelta(hours=2),
        )
        reg_b = GSTRegistration.objects.create(
            company=self.company,
            gstin="07AAACA1234B1Z2",
            legal_name="Apex Branch B",
            state_code="07",
            state_name="Delhi",
            status="ACTIVE",
            is_primary=False,
            auth_token="",
        )

        new_expiry = timezone.now() + timedelta(hours=6)
        GSTPortalService.persist_session_token(self.company, "07AAACA1234B1Z2", "token_b_new", new_expiry, "apex_b_user")

        reg_a.refresh_from_db()
        reg_b.refresh_from_db()
        self.assertEqual(reg_a.auth_token, "token_a_orig")
        self.assertEqual(reg_b.auth_token, "token_b_new")

    # =========================================================================
    # PHASE B: MULTI-GSTIN FILING SCOPING, IDENTITY CONSTRAINTS & DELETION PROTECTION
    # =========================================================================

    def test_separate_filing_records_for_different_gstins_same_period(self):
        """Separate registrations filing for the same period create distinct filing records."""
        reg_a = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_reg_a",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        reg_b = GSTRegistration.objects.create(
            company=self.company,
            gstin="07AAACA1234B1Z2",
            legal_name="Apex Delhi",
            state_code="07",
            state_name="Delhi",
            status="ACTIVE",
            is_primary=False,
            auth_token="token_reg_b",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )

        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_apex_mock"
        config.sandbox_api_secret = "sec_live_apex_mock"
        config.save()

        with patch.object(SandboxGSTClient, 'save_gstr1') as mock_save:
            mock_save.return_value = {"success": True, "data": {"reference_id": "REF-UP-082026"}}
            res_a = GSTPortalService.upload_gstr1_direct(self.company, "2026-08-01", "2026-08-31", gstin="09AAACA1234A1Z5")
            self.assertTrue(res_a["success"])

            mock_save.return_value = {"success": True, "data": {"reference_id": "REF-DL-082026"}}
            res_b = GSTPortalService.upload_gstr1_direct(self.company, "2026-08-01", "2026-08-31", gstin="07AAACA1234B1Z2")
            self.assertTrue(res_b["success"])

        # Both records must coexist under the same company for the same period
        filings = GSTFilingRecord.objects.filter(company=self.company, return_type="GSTR1")
        self.assertEqual(filings.count(), 2)
        rec_a = filings.get(gst_registration=reg_a)
        rec_b = filings.get(gst_registration=reg_b)
        self.assertEqual(rec_a.provider_reference, "REF-UP-082026")
        self.assertEqual(rec_b.provider_reference, "REF-DL-082026")

    def test_database_unique_constraint_enforces_company_reg_period(self):
        """Database constraint enforces uniqueness of (company, gst_registration, return_type, return_period)."""
        reg_a = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
        )

        GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg_a,
            return_type="GSTR1",
            return_period="082026",
            status="SUBMITTED",
        )

        with self.assertRaises(IntegrityError):
            GSTFilingRecord.objects.create(
                company=self.company,
                gst_registration=reg_a,
                return_type="GSTR1",
                return_period="082026",
                status="SUBMITTED",
            )

    def test_duplicate_submission_blocked_when_already_filed(self):
        """Submitting GSTR-1 when already confirmed FILED with an ARN is blocked."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_reg_valid",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg,
            return_type="GSTR1",
            return_period="082026",
            status="FILED",
            arn="092608123456789",
        )

        with patch('apps.gst.services.gstr_report_service.GSTRReportService.generate_gstr1') as mock_gen:
            mock_gen.return_value = {"fp": "082026", "b2b": []}
            res = GSTPortalService.upload_gstr1_direct(self.company, "2026-08-01", "2026-08-31", gstin="09AAACA1234A1Z5")
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "ALREADY_FILED")
            self.assertEqual(res["arn"], "092608123456789")

    def test_duplicate_submission_blocked_when_pending(self):
        """Submitting GSTR-1 when a previous submission is SUBMITTED or SUBMITTING is blocked."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_reg_valid",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg,
            return_type="GSTR1",
            return_period="082026",
            status="SUBMITTED",
            provider_reference="REF-PENDING-001",
        )

        with patch('apps.gst.services.gstr_report_service.GSTRReportService.generate_gstr1') as mock_gen:
            mock_gen.return_value = {"fp": "082026", "b2b": []}
            res = GSTPortalService.upload_gstr1_direct(self.company, "2026-08-01", "2026-08-31", gstin="09AAACA1234A1Z5")
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "SUBMISSION_PENDING")
            self.assertEqual(res["provider_reference"], "REF-PENDING-001")

    def test_filing_record_protected_from_deletion_when_filed(self):
        """Statutory filing records in FILED status cannot be deleted (preserves statutory audit)."""
        rec = GSTFilingRecord.objects.create(
            company=self.company,
            return_type="GSTR1",
            return_period="082026",
            status="FILED",
            arn="092608123456789",
        )
        with self.assertRaises(ValidationError):
            rec.delete()

    # =========================================================================
    # PHASE C: OTP CHALLENGE CONCURRENCY, RATE LIMITING & ATOMIC SHIELDS
    # =========================================================================

    def test_invalid_or_expired_txn_id_on_otp_verification(self):
        """verify_portal_otp strictly rejects calls with non-existent or expired txn_id."""
        res = GSTPortalService.verify_portal_otp(
            company=self.company,
            otp="123456",
            txn_id="CHAL-NON-EXISTENT-999",
            gstin="09AAACA1234A1Z5",
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "CHALLENGE_EXPIRED")

    def test_atomic_cooldown_acquisition_race_condition(self):
        """Rapid concurrent OTP requests enforce atomic cooldown lock (only 1 succeeds, others receive COOLDOWN_ACTIVE)."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        with patch.object(SandboxGSTClient, 'request_portal_otp') as mock_req:
            mock_req.return_value = {"success": True, "correlation_id": "CORR-001"}

            # First request acquires lock
            res1 = GSTPortalService.request_portal_otp(self.company, gstin="09AAACA1234A1Z5")
            self.assertTrue(res1["success"])

            # Immediate second request hits atomic cooldown lock
            res2 = GSTPortalService.request_portal_otp(self.company, gstin="09AAACA1234A1Z5")
            self.assertFalse(res2["success"])
            self.assertEqual(res2["code"], "COOLDOWN_ACTIVE")
            self.assertGreater(res2["cooldown_remaining"], 0)

    def test_hourly_rate_limit_enforced(self):
        """More than 5 OTP requests within an hour are blocked by rate limit."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        rate_key = f"gst_otp_hr_{self.company.id}_09AAACA1234A1Z5"
        # Simulate 5 previous requests in current hour
        cache.set(rate_key, 5, timeout=3600)

        res = GSTPortalService.request_portal_otp(self.company, gstin="09AAACA1234A1Z5")
        self.assertFalse(res["success"])
        self.assertEqual(res["code"], "RATE_LIMIT_EXCEEDED")

    def test_cross_user_challenge_ownership_rejection(self):
        """OTP challenge requested by User A cannot be verified by User B."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        with patch.object(SandboxGSTClient, 'request_portal_otp') as mock_req:
            mock_req.return_value = {"success": True, "correlation_id": "CORR-USER-A"}
            req_res = GSTPortalService.request_portal_otp(self.company, gstin="09AAACA1234A1Z5", user=self.user)
            self.assertTrue(req_res["success"])
            txn_id = req_res["txn_id"]

        # User B attempts to verify User A's challenge
        ver_res = GSTPortalService.verify_portal_otp(
            self.company,
            otp="123456",
            txn_id=txn_id,
            gstin="09AAACA1234A1Z5",
            user=self.other_user
        )
        self.assertFalse(ver_res["success"])
        self.assertEqual(ver_res["code"], "CHALLENGE_OWNERSHIP_MISMATCH")

    def test_cross_company_challenge_rejection(self):
        """OTP challenge issued for Company 1 cannot be verified under Company 2."""
        txn_id = "CHAL-CROSS-COMPANY-01"
        cache.set(
            f"gst_chal_{txn_id}",
            {
                "txn_id": txn_id,
                "company_id": str(self.company.id),
                "gstin": "09AAACA1234A1Z5",
                "username": "apex_user",
                "created_at": time.time(),
                "expires_at": time.time() + 600,
            },
            timeout=600
        )

        ver_res = GSTPortalService.verify_portal_otp(
            company=self.other_company,
            otp="123456",
            txn_id=txn_id,
            gstin="27AAACA9999Z1Z1",
        )
        self.assertFalse(ver_res["success"])
        self.assertEqual(ver_res["code"], "INVALID_CHALLENGE")

    def test_atomic_attempt_counter_and_lockout(self):
        """More than 5 invalid OTP attempts lockout and invalidate the challenge."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        txn_id = "CHAL-LOCKOUT-TEST-99"
        cache.set(
            f"gst_chal_{txn_id}",
            {
                "txn_id": txn_id,
                "company_id": str(self.company.id),
                "gstin": "09AAACA1234A1Z5",
                "username": "apex_user",
                "created_at": time.time(),
                "expires_at": time.time() + 600,
            },
            timeout=600
        )

        with patch.object(SandboxGSTClient, 'verify_portal_otp') as mock_ver:
            mock_ver.return_value = {"success": False, "error": "Invalid OTP entered."}
            # 5 failed attempts
            for _ in range(5):
                res = GSTPortalService.verify_portal_otp(self.company, otp="111111", txn_id=txn_id, gstin="09AAACA1234A1Z5")
                self.assertFalse(res["success"])

            # 6th attempt locks out
            res_locked = GSTPortalService.verify_portal_otp(self.company, otp="111111", txn_id=txn_id, gstin="09AAACA1234A1Z5")
            self.assertFalse(res_locked["success"])
            self.assertEqual(res_locked["code"], "MAX_ATTEMPTS_EXCEEDED")

            # Challenge must be deleted from cache
            self.assertIsNone(cache.get(f"gst_chal_{txn_id}"))

    def test_challenge_replay_prevention(self):
        """Challenge is invalidated immediately on success to prevent replay attacks."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        txn_id = "CHAL-REPLAY-PREVENT-01"
        cache.set(
            f"gst_chal_{txn_id}",
            {
                "txn_id": txn_id,
                "company_id": str(self.company.id),
                "gstin": "09AAACA1234A1Z5",
                "username": "apex_user",
                "created_at": time.time(),
                "expires_at": time.time() + 600,
            },
            timeout=600
        )

        future_exp = int((time.time() + 21600) * 1000)
        with patch.object(SandboxGSTClient, 'verify_portal_otp') as mock_ver:
            mock_ver.return_value = {
                "success": True,
                "data": {
                    "auth_token": "token_authentic_session_12345",
                    "session_expiry": future_exp,
                    "gstin": "09AAACA1234A1Z5",
                }
            }
            res1 = GSTPortalService.verify_portal_otp(self.company, otp="654321", txn_id=txn_id, gstin="09AAACA1234A1Z5")
            self.assertTrue(res1["success"])

            # Replaying the same challenge fails with CHALLENGE_EXPIRED
            res2 = GSTPortalService.verify_portal_otp(self.company, otp="654321", txn_id=txn_id, gstin="09AAACA1234A1Z5")
            self.assertFalse(res2["success"])
            self.assertEqual(res2["code"], "CHALLENGE_EXPIRED")

    # =========================================================================
    # PHASE D: GSTR-1 STATUTORY STATE MACHINE & RECONCILIATION IDEMPOTENCY
    # =========================================================================

    def test_processed_response_without_arn_remains_submitted(self):
        """When provider reports PROCESSED but no ARN is provided, status remains SUBMITTED, never FILED."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_active_reg",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        filing = GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg,
            return_type="GSTR1",
            return_period="082026",
            status="SUBMITTED",
            provider_reference="REF-PROC-NO-ARN",
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        with patch.object(SandboxGSTClient, 'get_gstr_status') as mock_stat:
            mock_stat.return_value = {
                "success": True,
                "data": {
                    "status": "PROCESSED",
                    "arn": "",  # Blank ARN!
                }
            }
            res = GSTPortalService.get_portal_status(self.company, ref_id="REF-PROC-NO-ARN", gstin="09AAACA1234A1Z5")
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "SUBMITTED")
            self.assertIsNone(res["arn"])

        filing.refresh_from_db()
        self.assertEqual(filing.status, "SUBMITTED")
        self.assertEqual(filing.arn, "")

    def test_genuine_arn_transitions_to_filed(self):
        """When provider returns authentic government ARN, status transitions to FILED."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_active_reg",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        filing = GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg,
            return_type="GSTR1",
            return_period="082026",
            status="SUBMITTED",
            provider_reference="REF-CONFIRMED-01",
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        with patch.object(SandboxGSTClient, 'get_gstr_status') as mock_stat:
            mock_stat.return_value = {
                "success": True,
                "data": {
                    "status": "PROCESSED",
                    "arn": "092608123456789",
                }
            }
            res = GSTPortalService.get_portal_status(self.company, ref_id="REF-CONFIRMED-01", gstin="09AAACA1234A1Z5")
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "FILED")
            self.assertEqual(res["arn"], "092608123456789")

        filing.refresh_from_db()
        self.assertEqual(filing.status, "FILED")
        self.assertEqual(filing.arn, "092608123456789")

    def test_idempotent_reconciliation(self):
        """Querying status on an already FILED return returns immediately without contacting provider."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_active_reg",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg,
            return_type="GSTR1",
            return_period="082026",
            status="FILED",
            arn="092608123456789",
            provider_reference="REF-IDEMPOTENT-01",
        )

        with patch.object(SandboxGSTClient, 'get_gstr_status') as mock_stat:
            res = GSTPortalService.get_portal_status(self.company, ref_id="REF-IDEMPOTENT-01", gstin="09AAACA1234A1Z5")
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "FILED")
            self.assertEqual(res["arn"], "092608123456789")
            mock_stat.assert_not_called()

    def test_filed_status_never_downgraded_on_provider_error(self):
        """A filing already confirmed FILED is never downgraded or overwritten if network or provider fails."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_active_reg",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        filing = GSTFilingRecord.objects.create(
            company=self.company,
            gst_registration=reg,
            return_type="GSTR1",
            return_period="082026",
            status="FILED",
            arn="092608123456789",
            provider_reference="REF-NO-DOWNGRADE",
        )

        res = GSTPortalService.get_portal_status(self.company, ref_id="REF-NO-DOWNGRADE", gstin="09AAACA1234A1Z5")
        self.assertEqual(res["status"], "FILED")
        self.assertEqual(res["arn"], "092608123456789")

        filing.refresh_from_db()
        self.assertEqual(filing.status, "FILED")
        self.assertEqual(filing.arn, "092608123456789")

    # =========================================================================
    # PHASE E: CALLER-SUPPLIED TOKEN ELIMINATION & CROSS-TENANT ACCESS CONTROL
    # =========================================================================

    def test_upload_gstr1_ignores_caller_supplied_auth_token(self):
        """upload_gstr1_direct resolves token exclusively from verified session store and ignores caller token."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="verified_store_token_999",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        with patch.object(SandboxGSTClient, 'save_gstr1') as mock_save:
            mock_save.return_value = {"success": True, "data": {"reference_id": "REF-TOKEN-TEST"}}
            GSTPortalService.upload_gstr1_direct(
                self.company,
                "2026-08-01",
                "2026-08-31",
                gstin="09AAACA1234A1Z5",
                auth_token="spoofed_malicious_token_attempt"
            )
            # Must be called with verified_store_token_999, NOT spoofed_malicious_token_attempt
            args, kwargs = mock_save.call_args
            self.assertEqual(kwargs.get("session_token"), "verified_store_token_999")

    def test_upload_gstr1_api_validates_gstin_belongs_to_company(self):
        """POST /upload-gstr1/ rejects requests for a GSTIN not registered under the company."""
        url = "/api/v1/gst/portal/upload-gstr1/"
        req = self.factory.post(
            url,
            {
                "company_id": str(self.company.id),
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
                "gstin": "24AAACA9999C1Z9",  # Not registered
            },
            format='json'
        )
        force_authenticate(req, user=self.user)
        view = GSTRDirectPortalUploadGSTR1APIView.as_view()
        response = view(req)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "GSTIN_NOT_REGISTERED")

    # =========================================================================
    # PHASE F: SENSITIVE CREDENTIAL REDACTION & LOG SANITIZATION
    # =========================================================================

    def test_no_bearer_tokens_or_passwords_in_audit_logs(self):
        """Audit logging redacts bearer tokens, passwords, and API keys."""
        dirty_payload = {
            "auth_token": "Bearer secret_bearer_token_12345",
            "password": "SuperSecretPassword!",
            "x-api-key": "key_live_private_secret",
            "taxpayer_name": "Apex Belting Store",
        }
        cleaned = redact_sensitive_payload(dirty_payload)
        self.assertEqual(cleaned["auth_token"], "REDACTED")
        self.assertEqual(cleaned["password"], "REDACTED")
        self.assertEqual(cleaned["x-api-key"], "REDACTED")
        self.assertEqual(cleaned["taxpayer_name"], "Apex Belting Store")

    def test_no_raw_network_exception_leaked_in_filing_error(self):
        """Network timeout during upload stores sanitized diagnostic message without leaking raw socket strings."""
        reg = GSTRegistration.objects.create(
            company=self.company,
            gstin="09AAACA1234A1Z5",
            legal_name="Apex UP",
            state_code="09",
            state_name="Uttar Pradesh",
            status="ACTIVE",
            is_primary=True,
            auth_token="token_active_reg",
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        config = GSTPortalService.get_or_create_config(self.company)
        config.sandbox_api_key = "key_live_mock"
        config.sandbox_api_secret = "sec_live_mock"
        config.save()

        import requests
        with patch.object(SandboxGSTClient, 'save_gstr1') as mock_save:
            mock_save.side_effect = requests.exceptions.ConnectTimeout("HTTPSConnectionPool(host='api.sandbox.co.in', port=443): Max retries exceeded")
            res = GSTPortalService.upload_gstr1_direct(self.company, "2026-08-01", "2026-08-31", gstin="09AAACA1234A1Z5")
            self.assertFalse(res["success"])
            self.assertEqual(res["code"], "RECONCILIATION_REQUIRED")

        filing = GSTFilingRecord.objects.get(company=self.company, gst_registration=reg, return_type="GSTR1")
        self.assertEqual(filing.status, "RECONCILIATION_REQUIRED")
        self.assertNotIn("HTTPSConnectionPool", filing.error_message)
        self.assertNotIn("443", filing.error_message)
        self.assertIn("Network timeout during submission", filing.error_message)

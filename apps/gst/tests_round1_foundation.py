import json
import uuid
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import (
    CompanyGSTConfig,
    GSTRegistration,
    GSTTaxpayerCache,
    GSTAuditLog
)
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gstin_service import GSTINService, calculate_gstin_checksum
from apps.gst.services.registration_service import GSTRegistrationService
from apps.gst.services.authentication_service import SandboxAuthenticationService
from apps.gst.exceptions import (
    GSTConfigurationMissingError,
    GSTAuthenticationError,
    GSTRateLimitExceededError,
    GSTIntegrationError,
    GSTINValidationError,
    DuplicateSubmissionError,
    GSTRegistrationAccessDenied,
)

User = get_user_model()


class GSTRound1FoundationTests(TestCase):
    """
    Round 1 Test Suite:
    - Provider Connectivity & Sandbox Client Resiliency
    - Multi-GSTIN Registration Management & Lifecycle
    - GSTIN Verification (Luhn MOD-36 Checksum & Sandbox Public Search)
    - Party Master Integration & Non-Intrusive Enrichment
    - Tenant Isolation & RBAC Security
    - Double-Entry Accounting Regression & Non-Interference
    """

    def setUp(self):
        # 1. Company A (Primary Sandbox Test Tenant)
        self.company_a = Company.objects.create(
            name="Apex Belting Store",
            legal_name="Apex Belting & Industrial Supplies Pvt Ltd",
            gstin="27AAACA1234A1Z5",
            state_code="27",
            state_name="Maharashtra",
            city="Mumbai",
            address="101 Industrial Estate, Andheri East",
            pincode="400069",
            email="accounts@apexbelting.com",
            phone="9876543210"
        )

        # 2. Company B (Isolated Cross-Tenant)
        self.company_b = Company.objects.create(
            name="North Agro Equipment",
            legal_name="North Agro Equipment Ltd",
            gstin="07BBBCB5678B1Z2",
            state_code="07",
            state_name="Delhi",
            city="New Delhi",
            address="45 Connaught Place",
            pincode="110001",
            email="finance@northagro.com"
        )

        # Users
        self.user_a = User.objects.create_user(
            email="accountant_a@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(
            user=self.user_a,
            company=self.company_a,
            role="ACCOUNTANT"
        )

        self.user_b = User.objects.create_user(
            email="accountant_b@northagro.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(
            user=self.user_b,
            company=self.company_b,
            role="ACCOUNTANT"
        )

        # Config A with Sandbox Credentials
        self.config_a = CompanyGSTConfig.objects.create(
            company=self.company_a,
            provider='SANDBOX_CO_IN',
            is_sandbox=True,
            sandbox_api_key='key_test_apex_belting_12345',
            sandbox_api_secret='sec_test_apex_secret_99999',
            sandbox_base_url='https://test-api.sandbox.co.in'
        )

        # Standard Ledgers
        self.group_debtors = LedgerGroup.objects.create(
            company=self.company_a,
            name="Sundry Debtors",
            nature="ASSET"
        )
        self.group_creditors = LedgerGroup.objects.create(
            company=self.company_a,
            name="Sundry Creditors",
            nature="LIABILITY"
        )

        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

    # =========================================================================
    # SECTION A: PROVIDER CLIENT TESTS
    # =========================================================================
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_client_authentication_success_and_caching(self, mock_req):
        """Verifies JWT token exchange and caching in CompanyGSTConfig."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "mock_jwt_apex_token_xyz",
            "expires_in": 86400
        }
        mock_req.return_value = mock_resp

        client = SandboxGSTClient(company=self.company_a)
        token = client.get_access_token()

        self.assertEqual(token, "mock_jwt_apex_token_xyz")
        self.config_a.refresh_from_db()
        self.assertEqual(self.config_a.sandbox_access_token, "mock_jwt_apex_token_xyz")
        self.assertIsNotNone(self.config_a.sandbox_token_expires_at)

        # Second call should reuse cached token without network dispatch
        token_cached = client.get_access_token()
        self.assertEqual(token_cached, "mock_jwt_apex_token_xyz")
        self.assertEqual(mock_req.call_count, 1)

    def test_client_missing_credentials_raises_error(self):
        """Verifies that missing API keys raise GSTConfigurationMissingError gracefully."""
        self.config_a.sandbox_api_key = ''
        self.config_a.sandbox_api_secret = ''
        self.config_a.save()

        client = SandboxGSTClient(company=self.company_a)
        with self.assertRaises(GSTConfigurationMissingError):
            client.get_access_token()

    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_client_authentication_failure_handling(self, mock_req):
        """Verifies HTTP 401 raises GSTAuthenticationError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"message": "Invalid API Key"}'
        mock_req.return_value = mock_resp

        client = SandboxGSTClient(company=self.company_a)
        with self.assertRaises(GSTAuthenticationError):
            client.get_access_token(force_refresh=True)

    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_client_rate_limiting_429(self, mock_req):
        """Verifies HTTP 429 raises GSTRateLimitExceededError during auth."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"message": "Rate limit exceeded"}'
        mock_req.return_value = mock_resp

        client = SandboxGSTClient(company=self.company_a)
        with self.assertRaises(GSTRateLimitExceededError):
            client.get_access_token(force_refresh=True)

    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_client_timeout_and_server_error_handling(self, mock_req):
        """Verifies network timeouts return normalized 504 responses."""
        import requests
        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {"access_token": "valid_token"}
        mock_req.side_effect = [
            mock_auth,
            requests.exceptions.Timeout("Read timeout attempt 1"),
            requests.exceptions.Timeout("Read timeout attempt 2"),
            requests.exceptions.Timeout("Read timeout attempt 3")
        ]

        client = SandboxGSTClient(company=self.company_a)
        res = client.search_taxpayer("27AADCB2230M1ZT")
        self.assertFalse(res["success"])
        self.assertEqual(res["status_code"], 504)
        self.assertIn("Connection to Sandbox failed", res["error"])

    # =========================================================================
    # SECTION B: GSTIN VERIFICATION TESTS
    # =========================================================================
    def test_luhn_mod36_checksum_calculation(self):
        """Verifies correct calculation and validation of 15th checksum character."""
        # Valid Maharashtra GSTIN: 27AADCB2230M1ZT
        self.assertEqual(calculate_gstin_checksum("27AADCB2230M1Z"), "T")
        # Valid Delhi GSTIN: 07AAAAA0000A1Z4
        self.assertEqual(calculate_gstin_checksum("07AAAAA0000A1Z"), "4")

    def test_gstin_format_validation(self):
        """Tests local format check against invalid lengths, bad PAN, and invalid state codes."""
        # Valid format
        val_valid = GSTINService.validate_format("27AADCB2230M1ZT")
        self.assertTrue(val_valid["valid"])

        # Checksum mismatch
        val_bad_chk = GSTINService.validate_format("27AADCB2230M1ZA")
        self.assertFalse(val_bad_chk["checksum_valid"])
        self.assertIn("Checksum mismatch", val_bad_chk["error"])

        # Bad length
        val_short = GSTINService.validate_format("27AADCB2230")
        self.assertFalse(val_short["valid"])

        # Bad state code (00 is invalid)
        val_bad_state = GSTINService.validate_format("00AADCB2230M1ZT")
        self.assertFalse(val_bad_state["valid"])

    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_verify_gstin_sandbox_call_and_cache_persistence(self, mock_req):
        """Verifies public search queries Sandbox and caches profile in GSTTaxpayerCache."""
        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {"access_token": "token123"}

        mock_search = MagicMock(status_code=200)
        mock_search.json.return_value = {
            "status_code": 200,
            "data": {
                "gstin": "27AADCB2230M1ZT",
                "lgnm": "TATA CONSULTANCY SERVICES LIMITED",
                "tradeNam": "TCS",
                "sts": "Active",
                "ctb": "Regular",
                "rgdt": "01/07/2017",
                "pradr": {
                  "addr": {
                    "bno": "TCS House",
                    "st": "Raveline Street",
                    "loc": "Mumbai",
                    "pncd": "400001",
                    "stcd": "27"
                  }
                }
            }
        }
        mock_req.side_effect = [mock_auth, mock_search]

        res = GSTINService.verify_gstin("27AADCB2230M1ZT", company=self.company_a)
        self.assertTrue(res["success"])
        self.assertEqual(res["legal_name"], "TATA CONSULTANCY SERVICES LIMITED")
        self.assertEqual(res["status"], "Active")

        # Verify cached
        cached = GSTTaxpayerCache.objects.filter(gstin="27AADCB2230M1ZT").first()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.legal_name, "TATA CONSULTANCY SERVICES LIMITED")

        # Second call should be served from cache
        res2 = GSTINService.verify_gstin("27AADCB2230M1ZT", company=self.company_a)
        self.assertTrue(res2["is_cached"])
        self.assertEqual(mock_req.call_count, 2)  # No extra calls

    # =========================================================================
    # SECTION C: MULTI-GSTIN REGISTRATION TESTS
    # =========================================================================
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_multi_gstin_registration_lifecycle(self, mock_req):
        """Tests adding multi-state GST registrations, primary switching, and deactivation."""
        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {"access_token": "token123"}
        mock_search_mh = MagicMock(status_code=200)
        mock_search_mh.json.return_value = {
            "data": {"gstin": "27AAACA1234A1Z5", "lgnm": "Apex Belting MH", "sts": "Active", "ctb": "Regular"}
        }
        mock_search_dl = MagicMock(status_code=200)
        mock_search_dl.json.return_value = {
            "data": {"gstin": "07AAACA1234A1Z7", "lgnm": "Apex Belting DL", "sts": "Active", "ctb": "Regular"}
        }
        mock_req.side_effect = [mock_auth, mock_search_mh, mock_auth, mock_search_dl]

        # 1. Create first registration (MH) - auto-primary
        reg_mh = GSTRegistrationService.create_registration(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            state_code="27",
            user=self.user_a
        )
        self.assertEqual(reg_mh.state_code, "27")
        self.assertTrue(reg_mh.is_primary)
        self.assertEqual(reg_mh.verification_status, "VERIFIED")

        # 2. Create second registration (DL) - set as primary
        reg_dl = GSTRegistrationService.create_registration(
            company=self.company_a,
            gstin="07AAACA1234A1Z7",
            state_code="07",
            is_primary=True,
            user=self.user_a
        )
        self.assertEqual(reg_dl.state_code, "07")
        self.assertTrue(reg_dl.is_primary)

        # MH should have had primary cleared
        reg_mh.refresh_from_db()
        self.assertFalse(reg_mh.is_primary)

        # 3. Duplicate GSTIN prevention within company
        with self.assertRaises(DuplicateSubmissionError):
            GSTRegistrationService.create_registration(
                company=self.company_a,
                gstin="27AAACA1234A1Z5",
                state_code="27",
                user=self.user_a
            )

        # 4. Deactivate DL registration
        GSTRegistrationService.deactivate_registration(self.company_a, str(reg_dl.id), user=self.user_a)
        reg_dl.refresh_from_db()
        self.assertEqual(reg_dl.status, "INACTIVE")

        # List should include it when include_inactive=True
        all_regs = GSTRegistrationService.list_registrations(self.company_a, include_inactive=True)
        self.assertEqual(len(all_regs), 2)

        # Active-only list should return only MH
        active_regs = GSTRegistrationService.list_registrations(self.company_a, include_inactive=False)
        self.assertEqual(len(active_regs), 1)
        self.assertEqual(active_regs[0].gstin, "27AAACA1234A1Z5")

    # =========================================================================
    # SECTION D: PARTY MASTER INTEGRATION TESTS
    # =========================================================================
    def test_party_enrichment_preview_and_non_intrusive_apply(self):
        """Verifies party enrichment produces a diff preview and never silently overwrites."""
        party = Ledger.objects.create(
            company=self.company_a,
            group=self.group_debtors,
            name="Tata Corp",
            state_code="27",
            address="Old Address"
        )

        verified_data = {
            "gstin": "27AADCB2230M1ZT",
            "legal_name": "TATA CONSULTANCY SERVICES LIMITED",
            "trade_name": "TCS",
            "state_code": "27",
            "address": "TCS House, Mumbai, 400001",
            "status": "Active"
        }

        # 1. Preview Diff
        diff = GSTINService.preview_party_enrichment(party, verified_data)
        self.assertTrue(diff["has_changes"])
        self.assertEqual(diff["diffs"]["legal_name"]["current"], "Tata Corp")
        self.assertEqual(diff["diffs"]["legal_name"]["verified"], "TATA CONSULTANCY SERVICES LIMITED")

        # 2. Selective Apply (only trade_name and address, keep name)
        updated_party = GSTINService.apply_party_enrichment(
            ledger_id=party.id,
            verified_data=verified_data,
            apply_legal_name=False,
            apply_state=True,
            apply_address=True,
            user=self.user_a
        )
        self.assertEqual(updated_party.name, "Tata Corp")  # Preserved
        self.assertEqual(updated_party.address, "TCS House, Mumbai, 400001")
        self.assertEqual(updated_party.gstin, "27AADCB2230M1ZT")

        # Check Audit Log created
        audit = GSTAuditLog.objects.filter(company=self.company_a, action="PARTY_ENRICH").first()
        self.assertIsNotNone(audit)

    # =========================================================================
    # SECTION E: TENANT ISOLATION TESTS
    # =========================================================================
    def test_tenant_isolation_on_gst_registrations(self):
        """Verifies that Company B cannot access, verify, or modify Company A's registrations."""
        reg_a = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            legal_name="Apex MH",
            state_code="27",
            state_name="Maharashtra"
        )

        # 1. Company B tries to fetch Company A's registration via service
        with self.assertRaises(GSTRegistrationAccessDenied):
            GSTRegistrationService.get_registration(self.company_b, str(reg_a.id))

        # 2. Company B tries to access via API endpoint
        url = f"/api/v1/gst/registrations/{self.company_a.id}/{reg_a.id}/"
        res = self.client_b.get(url)
        self.assertEqual(res.status_code, 403)

        # 3. Company B tries to deactivate Company A's registration via API
        deactivate_url = f"/api/v1/gst/registrations/{self.company_a.id}/{reg_a.id}/deactivate/"
        res_deact = self.client_b.post(deactivate_url)
        self.assertEqual(res_deact.status_code, 403)
        reg_a.refresh_from_db()
        self.assertEqual(reg_a.status, "ACTIVE")

    # =========================================================================
    # SECTION F: ACCOUNTING REGRESSION & INVARIANCE
    # =========================================================================
    def test_accounting_engine_invariance(self):
        """
        Verifies that registering GSTINs, verifying taxpayers, and modifying registrations
        causes ZERO mutations to accounting vouchers, balances, or stock ledgers.
        """
        # Baseline Accounting Voucher
        party = Ledger.objects.create(
            company=self.company_a,
            group=self.group_debtors,
            name="Client A",
            current_balance=Decimal("1180.00")
        )
        voucher = Voucher.objects.create(
            company=self.company_a,
            created_by=self.user_a,
            voucher_type='SALES',
            voucher_number='INV/R1/001',
            voucher_date=date(2026, 8, 20),
            party_ledger=party,
            status='POSTED',
            total_amount=Decimal('1180.00')
        )

        voucher_count_before = Voucher.objects.filter(company=self.company_a).count()
        party_bal_before = party.current_balance

        # Perform multiple GST operations
        GSTRegistrationService.create_registration(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            state_code="27",
            auto_verify=False,
            user=self.user_a
        )
        GSTINService.validate_format("27AADCB2230M1ZT")

        # Assert zero accounting mutations
        voucher_count_after = Voucher.objects.filter(company=self.company_a).count()
        party.refresh_from_db()
        voucher.refresh_from_db()

        self.assertEqual(voucher_count_before, voucher_count_after)
        self.assertEqual(party_bal_before, party.current_balance)
        self.assertEqual(voucher.total_amount, Decimal('1180.00'))
        self.assertEqual(voucher.status, 'POSTED')

    # =========================================================================
    # SECTION G: ROUND 1.2 ENCRYPTION HARDENING & CACHE BEHAVIOR
    # =========================================================================
    def test_dedicated_encryption_key_enforcement_in_staging(self):
        """
        Verifies that staging and production strictly require GST_ENCRYPTION_KEY
        and refuse to silently fall back to Django SECRET_KEY.
        """
        from apps.gst.encryption import get_gst_credential_fernet, CredentialEncryptionError
        from unittest.mock import patch

        with patch('django.conf.settings.ENVIRONMENT', 'staging'):
            with patch('django.conf.settings.TESTING', False):
                with patch('sys.argv', ['manage.py', 'runserver']):
                    with patch.dict('os.environ', {'GST_ENCRYPTION_KEY': '', 'GST_CREDENTIAL_KEY': ''}, clear=False):
                        with patch('django.conf.settings.GST_ENCRYPTION_KEY', ''):
                            with patch('django.conf.settings.GST_CREDENTIAL_KEY', ''):
                                with self.assertRaises(CredentialEncryptionError) as ctx:
                                    get_gst_credential_fernet()
                                self.assertIn("Dedicated GST encryption key", str(ctx.exception))

    def test_encryption_roundtrip_with_direct_and_derived_keys(self):
        """
        Verifies backward-compatible encryption and decryption supporting both
        direct 44-character Fernet keys and SHA-256 derived passphrases.
        """
        from apps.gst.encryption import encrypt_gst_credential, decrypt_gst_credential
        from cryptography.fernet import Fernet
        from unittest.mock import patch

        # 1. Test with direct 44-char Fernet key
        direct_key = Fernet.generate_key().decode('utf-8')
        with patch('django.conf.settings.GST_ENCRYPTION_KEY', direct_key):
            secret_text = "test_sandbox_secret_key_direct_98765"
            ciphertext = encrypt_gst_credential(secret_text)
            self.assertTrue(ciphertext.startswith("enc:v1:"))
            decrypted = decrypt_gst_credential(ciphertext)
            self.assertEqual(decrypted, secret_text)

        # 2. Test with passphrase derived key
        passphrase_key = "secure_passphrase_for_derived_key"
        with patch('django.conf.settings.GST_ENCRYPTION_KEY', passphrase_key):
            secret_text2 = "test_sandbox_secret_key_derived_12345"
            ciphertext2 = encrypt_gst_credential(secret_text2)
            self.assertTrue(ciphertext2.startswith("enc:v1:"))
            decrypted2 = decrypt_gst_credential(ciphertext2)
            self.assertEqual(decrypted2, secret_text2)

    def test_taxpayer_cache_24h_expiry_and_force_refresh(self):
        """
        Verifies that the taxpayer cache respects the 24-hour TTL:
        - Within 24 hours: served from cache
        - Force refresh: bypasses cache
        - Older than 24 hours: cache considered stale and provider is called
        """
        from datetime import timedelta
        from django.utils import timezone
        from apps.gst.models import GSTTaxpayerCache
        from unittest.mock import patch

        gstin = "27AAACA1234A1Z5"
        # Seed cache created 25 hours ago
        stale_time = timezone.now() - timedelta(hours=25)
        cache_entry = GSTTaxpayerCache.objects.create(
            gstin=gstin,
            legal_name="Old Stale Apex Name",
            state_code="27",
            status="Active"
        )
        GSTTaxpayerCache.objects.filter(id=cache_entry.id).update(updated_at=stale_time)

        # Mock client to return fresh name
        mock_provider_res = {
            "success": True,
            "legal_name": "Fresh Apex Belting Ltd",
            "trade_name": "Apex Belting",
            "status": "Active",
            "state_code": "27"
        }

        with patch.object(SandboxGSTClient, 'is_configured', return_value=True):
            with patch.object(SandboxGSTClient, 'search_taxpayer', return_value=mock_provider_res):
                # 1. Lookup with stale cache should query provider
                res = GSTINService.verify_gstin(gstin, company=self.company_a)
                self.assertTrue(res.get("success"))
                self.assertEqual(res.get("legal_name"), "Fresh Apex Belting Ltd")

                # 2. Lookup within 24 hours should hit cache
                res_cached = GSTINService.verify_gstin(gstin, company=self.company_a)
                self.assertTrue(res_cached.get("is_cached"))
                self.assertEqual(res_cached.get("source"), "local_cache")

                # 3. Force refresh should bypass cache
                with patch.object(SandboxGSTClient, 'search_taxpayer', return_value={
                    "success": True,
                    "legal_name": "Forced Refresh Apex Ltd",
                    "status": "Active",
                    "state_code": "27"
                }):
                    res_forced = GSTINService.verify_gstin(gstin, company=self.company_a, force_refresh=True)
                    self.assertFalse(res_forced.get("is_cached", False))
                    self.assertEqual(res_forced.get("legal_name"), "Forced Refresh Apex Ltd")

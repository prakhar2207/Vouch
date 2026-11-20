import json
import uuid
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.utils import IntegrityError
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

        # Additional roles on Company A for RBAC & Tenant Isolation verification
        self.user_owner = User.objects.create_user(
            email="owner_a@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user_owner, company=self.company_a, role="OWNER")

        self.user_admin = User.objects.create_user(
            email="admin_a@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user_admin, company=self.company_a, role="ADMIN")

        self.user_employee = User.objects.create_user(
            email="employee_a@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user_employee, company=self.company_a, role="EMPLOYEE")

        self.user_viewer = User.objects.create_user(
            email="viewer_a@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user_viewer, company=self.company_a, role="VIEWER")

        self.user_ca = User.objects.create_user(
            email="ca_a@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user_ca, company=self.company_a, role="CA")

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

        self.client_owner = APIClient()
        self.client_owner.force_authenticate(user=self.user_owner)

        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.user_admin)

        self.client_employee = APIClient()
        self.client_employee.force_authenticate(user=self.user_employee)

        self.client_viewer = APIClient()
        self.client_viewer.force_authenticate(user=self.user_viewer)

        self.client_ca = APIClient()
        self.client_ca.force_authenticate(user=self.user_ca)

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
        # Baseline Accounting Voucher & Entries
        from apps.accounting.models import LedgerEntry
        party = Ledger.objects.create(
            company=self.company_a,
            group=self.group_debtors,
            name="Client A",
            opening_balance=Decimal("500.00"),
            current_balance=Decimal("1680.00")
        )
        sales_ledger = Ledger.objects.create(
            company=self.company_a,
            group=self.group_creditors,
            name="Domestic Sales",
            opening_balance=Decimal("0.00"),
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
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=party,
            debit_amount=Decimal('1180.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=sales_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('1180.00')
        )

        voucher_count_before = Voucher.objects.filter(company=self.company_a).count()
        entry_count_before = LedgerEntry.objects.filter(voucher__company=self.company_a).count()
        party_bal_before = party.current_balance
        party_op_before = party.opening_balance
        sales_bal_before = sales_ledger.current_balance

        # Perform multiple GST operations
        reg = GSTRegistrationService.create_registration(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            state_code="27",
            auto_verify=False,
            user=self.user_a
        )
        GSTINService.validate_format("27AADCB2230M1ZT")

        # Perform party enrichment (metadata update only)
        GSTINService.apply_party_enrichment(
            ledger_id=party.id,
            verified_data={
                "gstin": "27AAACA1234A1Z5",
                "legal_name": "Client A Legal Entity",
                "address": "Verified Billing Address",
                "state_code": "27"
            },
            apply_legal_name=True,
            apply_address=True,
            apply_state=True,
            user=self.user_a
        )

        # Assert zero accounting mutations
        voucher_count_after = Voucher.objects.filter(company=self.company_a).count()
        entry_count_after = LedgerEntry.objects.filter(voucher__company=self.company_a).count()
        party.refresh_from_db()
        sales_ledger.refresh_from_db()
        voucher.refresh_from_db()

        self.assertEqual(voucher_count_before, voucher_count_after)
        self.assertEqual(entry_count_before, entry_count_after)
        self.assertEqual(party_bal_before, party.current_balance)
        self.assertEqual(party_op_before, party.opening_balance)
        self.assertEqual(sales_bal_before, sales_ledger.current_balance)
        self.assertEqual(voucher.total_amount, Decimal('1180.00'))
        self.assertEqual(voucher.status, 'POSTED')
        # Only party metadata was enriched
        self.assertEqual(party.name, "Client A Legal Entity")
        self.assertEqual(party.address, "Verified Billing Address")

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

    # =========================================================================
    # SECTION H: ROUND 1.3 PRODUCTION-READINESS REMEDIATION & HARNESS TESTS
    # =========================================================================
    def test_raw_database_contains_ciphertext_not_plaintext(self):
        """
        Verifies that raw database columns store encrypted Fernet envelope 'enc:v1:...'
        and never expose plaintext secrets at rest.
        """
        from apps.gst.encryption import ENCRYPTION_PREFIX
        config = CompanyGSTConfig.objects.create(
            company=self.company_b,
            sandbox_api_key="super_secret_sandbox_key_999",
            sandbox_api_secret="super_secret_sandbox_secret_888"
        )
        # Fetch raw values directly from database bypassing field converters (from_db_value)
        from django.db import connection
        clean_id = config.id.hex if hasattr(config.id, 'hex') else str(config.id).replace('-', '')
        with connection.cursor() as cursor:
            cursor.execute("SELECT sandbox_api_key, sandbox_api_secret FROM gst_companygstconfig WHERE id = %s OR id = %s", [str(config.id), clean_id])
            raw_key, raw_secret = cursor.fetchone()

        self.assertTrue(raw_key.startswith(ENCRYPTION_PREFIX))
        self.assertTrue(raw_secret.startswith(ENCRYPTION_PREFIX))
        self.assertNotIn("super_secret_sandbox_key_999", raw_key)
        self.assertNotIn("super_secret_sandbox_secret_888", raw_secret)

        # Transparent model property retrieval decrypts correctly
        config.refresh_from_db()
        self.assertEqual(config.sandbox_api_key, "super_secret_sandbox_key_999")
        self.assertEqual(config.sandbox_api_secret, "super_secret_sandbox_secret_888")

    def test_corrupted_ciphertext_raises_credential_decryption_error(self):
        """Verifies that corrupted or tampered ciphertext raises CredentialDecryptionError."""
        from apps.gst.encryption import CredentialDecryptionError
        config = CompanyGSTConfig.objects.create(
            company=self.company_b,
            sandbox_api_key="valid_secret_key"
        )
        # Inject corrupted ciphertext
        CompanyGSTConfig.objects.filter(id=config.id).update(sandbox_api_key="enc:v1:this_is_corrupted_ciphertext_tampered")

        with self.assertRaises(CredentialDecryptionError):
            config.refresh_from_db()

    def test_key_rotation_management_command_dry_run_and_execution(self):
        """
        Verifies the rotate_gst_credentials management command:
        1. Decrypts records encrypted with GST_ENCRYPTION_KEY_OLD
        2. Re-encrypts with current primary GST_ENCRYPTION_KEY
        3. Supports idempotent execution and dry-run mode
        """
        from cryptography.fernet import Fernet
        from apps.gst.encryption import is_encrypted_with_primary_key, encrypt_gst_credential
        from io import StringIO

        primary_key = Fernet.generate_key().decode('utf-8')
        old_key = Fernet.generate_key().decode('utf-8')

        # Encrypt record using old key
        old_fernet = Fernet(old_key.encode('utf-8'))
        old_cipher = f"enc:v1:{old_fernet.encrypt(b'secret_key_under_old_key').decode('utf-8')}"

        with self.settings(GST_ENCRYPTION_KEY=primary_key, GST_ENCRYPTION_KEY_OLD=old_key):
            config = CompanyGSTConfig.objects.create(
                company=self.company_b,
                sandbox_api_key=""
            )
            CompanyGSTConfig.objects.filter(id=config.id).update(sandbox_api_key=old_cipher)

            # Prior to rotation: readable via old key, but not encrypted with primary key
            self.assertFalse(is_encrypted_with_primary_key(old_cipher))

            # 1. Dry run execution
            out_dry = StringIO()
            call_command('rotate_gst_credentials', '--dry-run', f'--company-id={self.company_b.id}', stdout=out_dry)
            output_dry = out_dry.getvalue()
            self.assertIn("Dry Run: True", output_dry)
            self.assertIn("Total Fields Rotated:             1", output_dry)

            # Verify database unchanged after dry-run
            from django.db import connection
            clean_id = config.id.hex if hasattr(config.id, 'hex') else str(config.id).replace('-', '')
            with connection.cursor() as cursor:
                cursor.execute("SELECT sandbox_api_key FROM gst_companygstconfig WHERE id = %s OR id = %s", [str(config.id), clean_id])
                row = cursor.fetchone()
                self.assertIsNotNone(row)
                raw_key_dry = row[0]
            self.assertEqual(raw_key_dry, old_cipher)

            # 2. Live rotation execution
            out_live = StringIO()
            call_command('rotate_gst_credentials', f'--company-id={self.company_b.id}', stdout=out_live)
            output_live = out_live.getvalue()
            self.assertIn("Dry Run: False", output_live)
            self.assertIn("Total Fields Rotated:             1", output_live)

            # Verify database is now encrypted with primary key
            with connection.cursor() as cursor:
                cursor.execute("SELECT sandbox_api_key FROM gst_companygstconfig WHERE id = %s OR id = %s", [str(config.id), clean_id])
                row = cursor.fetchone()
                self.assertIsNotNone(row)
                raw_key_live = row[0]
            self.assertNotEqual(raw_key_live, old_cipher)
            self.assertTrue(is_encrypted_with_primary_key(raw_key_live))

            # Verify transparent decryption yields original plaintext
            config.refresh_from_db()
            self.assertEqual(config.sandbox_api_key, "secret_key_under_old_key")

            # 3. Subsequent run should skip already rotated records (idempotent)
            out_idempotent = StringIO()
            call_command('rotate_gst_credentials', f'--company-id={self.company_b.id}', stdout=out_idempotent)
            self.assertIn("Total Fields Rotated:             0", out_idempotent.getvalue())

            # 4. Removing the old key entirely does not break credential retrieval
            with self.settings(GST_ENCRYPTION_KEY=primary_key, GST_ENCRYPTION_KEY_OLD=None):
                config.refresh_from_db()
                self.assertEqual(config.sandbox_api_key, "secret_key_under_old_key")

    def test_rbac_registration_mutations_restricted_to_admin_owner(self):
        """
        Verifies that only OWNER and ADMIN can create, update, or deactivate registrations.
        EMPLOYEE and VIEWER are strictly forbidden (HTTP 403).
        """
        url = f"/api/v1/gst/registrations/{self.company_a.id}/"
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "state_code": "27",
            "legal_name": "Apex Maharashtra",
            "auto_verify": False
        }

        # 1. VIEWER cannot create
        res_viewer = self.client_viewer.post(url, payload)
        self.assertEqual(res_viewer.status_code, 403)

        # 2. EMPLOYEE cannot create
        res_emp = self.client_employee.post(url, payload)
        self.assertEqual(res_emp.status_code, 403)

        # 3. ADMIN can create
        res_admin = self.client_admin.post(url, payload)
        self.assertEqual(res_admin.status_code, 201)
        reg_id = res_admin.data['registration']['id']

        # 4. VIEWER cannot deactivate
        deact_url = f"/api/v1/gst/registrations/{self.company_a.id}/{reg_id}/deactivate/"
        res_deact_viewer = self.client_viewer.post(deact_url)
        self.assertEqual(res_deact_viewer.status_code, 403)

        # 5. ADMIN can deactivate
        res_deact_admin = self.client_admin.post(deact_url)
        self.assertEqual(res_deact_admin.status_code, 200)

    def test_registration_authorized_users_object_permission(self):
        """
        Verifies registration-level authorized_users enforcement:
        Non-admin members must be explicitly present in authorized_users.
        ADMIN and OWNER bypass the restriction.
        """
        reg = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            legal_name="Apex MH",
            state_code="27",
            state_name="Maharashtra"
        )
        reg.authorized_users.add(self.user_employee)

        detail_url = f"/api/v1/gst/registrations/{self.company_a.id}/{reg.id}/"

        # Authorized employee can access
        res_emp = self.client_employee.get(detail_url)
        self.assertEqual(res_emp.status_code, 200)

        # Unauthorized viewer cannot access (not in authorized_users, not admin)
        res_viewer = self.client_viewer.get(detail_url)
        self.assertEqual(res_viewer.status_code, 403)

        # Admin can access even if not explicitly in authorized_users
        res_admin = self.client_admin.get(detail_url)
        self.assertEqual(res_admin.status_code, 200)

    def test_party_enrichment_rbac_and_cross_tenant_isolation(self):
        """
        Verifies party enrichment RBAC (OWNER, ADMIN, ACCOUNTANT only)
        and strict tenant isolation (cross-tenant party rejected with 404/403).
        """
        party = Ledger.objects.create(
            company=self.company_a,
            group=self.group_debtors,
            name="Original Client Name",
            state_code="27",
            gstin="27AADCB2230M1ZT"
        )
        # Pre-seed cache so verify_gstin succeeds offline
        GSTTaxpayerCache.objects.create(
            gstin="27AADCB2230M1ZT",
            legal_name="Verified TCS Legal Name",
            state_code="27",
            address="Verified Address"
        )

        enrich_url = "/api/v1/gst/party/enrich/"
        payload = {
            "company_id": str(self.company_a.id),
            "party_id": str(party.id),
            "fields_to_update": ["legal_name", "address"]
        }

        # 1. VIEWER and EMPLOYEE cannot enrich
        res_viewer = self.client_viewer.post(enrich_url, payload, format='json')
        self.assertEqual(res_viewer.status_code, 403)
        res_emp = self.client_employee.post(enrich_url, payload, format='json')
        self.assertEqual(res_emp.status_code, 403)

        # 2. Cross-tenant attempt (Company B tries to enrich Company A's party)
        cross_payload = {
            "company_id": str(self.company_b.id),
            "party_id": str(party.id),
            "fields_to_update": ["legal_name"]
        }
        res_cross = self.client_b.post(enrich_url, cross_payload, format='json')
        self.assertEqual(res_cross.status_code, 404)

        # 3. CA can enrich
        res_ca = self.client_ca.post(enrich_url, payload, format='json')
        self.assertEqual(res_ca.status_code, 200)

        # 4. ACCOUNTANT can enrich
        res_acc = self.client_a.post(enrich_url, payload, format='json')
        self.assertEqual(res_acc.status_code, 200)
        party.refresh_from_db()
        self.assertEqual(party.name, "Verified TCS Legal Name")
        self.assertEqual(party.address, "Verified Address")

    def test_pan_stem_mismatch_raises_validation_error(self):
        """
        Verifies PAN stem invariant: All registrations for an enterprise entity
        must share the exact same 10-character PAN stem.
        """
        # First registration: PAN is AAACA1234A
        GSTRegistrationService.create_registration(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            state_code="27",
            auto_verify=False,
            user=self.user_admin
        )

        # Second registration with DIFFERENT PAN: BBBCB5678B
        with self.assertRaises(GSTINValidationError) as ctx:
            GSTRegistrationService.create_registration(
                company=self.company_a,
                gstin="07BBBCB5678B1Z2",
                state_code="07",
                auto_verify=False,
                user=self.user_admin
            )
        self.assertIn("PAN stem mismatch", str(ctx.exception))

    def test_concurrent_primary_registration_unique_constraint(self):
        """
        Verifies that the database-level UniqueConstraint strictly prevents
        two primary registrations from existing for the same company.
        """
        # Create primary registration
        GSTRegistration.objects.create(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            legal_name="Apex MH",
            state_code="27",
            is_primary=True
        )

        # Direct attempt to insert a second primary registration must raise IntegrityError
        with self.assertRaises(IntegrityError):
            GSTRegistration.objects.create(
                company=self.company_a,
                gstin="07AAACA1234A1Z7",
                legal_name="Apex DL",
                state_code="07",
                is_primary=True
            )

    def test_deactivate_primary_promotes_next_active_registration(self):
        """
        Verifies that deactivating the primary registration atomically promotes
        the next active registration to primary, preserving primary invariant.
        """
        reg_mh = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            legal_name="Apex MH",
            state_code="27",
            status="ACTIVE",
            is_primary=True
        )
        reg_dl = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="07AAACA1234A1Z7",
            legal_name="Apex DL",
            state_code="07",
            status="ACTIVE",
            is_primary=False
        )

        GSTRegistrationService.deactivate_registration(self.company_a, str(reg_mh.id), user=self.user_admin)

        reg_mh.refresh_from_db()
        reg_dl.refresh_from_db()
        self.assertEqual(reg_mh.status, "INACTIVE")
        self.assertFalse(reg_mh.is_primary)
        self.assertTrue(reg_dl.is_primary)
        self.assertEqual(self.company_a.gstin, reg_dl.gstin)

    def test_deactivate_sole_primary_registration_leaves_zero_primary_registrations(self):
        """
        Verifies that deactivating the only registration leaves the company with
        zero primary registrations and zero active registrations without database errors,
        explicitly confirming the 'at most one primary' invariant (0 <= 1).
        """
        reg = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            legal_name="Apex MH",
            state_code="27",
            status="ACTIVE",
            is_primary=True
        )
        GSTRegistrationService.deactivate_registration(self.company_a, str(reg.id), user=self.user_admin)
        reg.refresh_from_db()
        self.assertEqual(reg.status, "INACTIVE")
        self.assertFalse(reg.is_primary)
        self.assertEqual(self.company_a.gst_registrations.filter(is_primary=True).count(), 0)
        self.assertEqual(self.company_a.gst_registrations.filter(status='ACTIVE').count(), 0)

    def test_concurrent_primary_switching_atomic(self):
        """
        Verifies that updating a non-primary registration to primary atomically
        demotes the existing primary, maintaining exactly one primary active.
        """
        reg1 = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="27AAACA1234A1Z5",
            legal_name="Apex MH",
            state_code="27",
            status="ACTIVE",
            is_primary=True
        )
        reg2 = GSTRegistration.objects.create(
            company=self.company_a,
            gstin="07AAACA1234A1Z7",
            legal_name="Apex DL",
            state_code="07",
            status="ACTIVE",
            is_primary=False
        )
        GSTRegistrationService.update_registration(
            company=self.company_a,
            registration_id=str(reg2.id),
            data={"is_primary": True},
            user=self.user_admin
        )
        reg1.refresh_from_db()
        reg2.refresh_from_db()
        self.assertFalse(reg1.is_primary)
        self.assertTrue(reg2.is_primary)
        self.assertEqual(self.company_a.gstin, reg2.gstin)
        self.assertEqual(self.company_a.gst_registrations.filter(is_primary=True).count(), 1)

    def test_force_refresh_failure_does_not_return_stale_cache_as_success(self):
        """
        Verifies that if an error occurs during force_refresh=True, the service
        strictly returns success=False and does NOT misrepresent stale cache as fresh verification.
        """
        import requests
        gstin = "27AAACA1234A1Z5"
        # Seed stale cache
        GSTTaxpayerCache.objects.create(
            gstin=gstin,
            legal_name="Cached Stale Name",
            state_code="27",
            status="Active"
        )

        with patch.object(SandboxGSTClient, 'is_configured', return_value=True):
            with patch.object(SandboxGSTClient, 'search_taxpayer', return_value={
                "success": False,
                "error": "504 Gateway Timeout contacting GST Portal"
            }):
                res = GSTINService.verify_gstin(gstin, company=self.company_a, force_refresh=True)
                self.assertFalse(res["success"])
                self.assertEqual(res["source"], "provider_error")
                self.assertIn("504 Gateway Timeout", res["error"])
                self.assertIsNotNone(res.get("last_known_data"))

    def test_iso_8601_registration_date_parsing(self):
        """Verifies robust parsing of ISO-8601 timestamps returned by Sandbox."""
        mock_res = {
            "success": True,
            "data": {
                "gstin": "27AADCB2230M1ZT",
                "lgnm": "TATA CONSULTANCY SERVICES LIMITED",
                "sts": "Active",
                "rgdt": "2017-07-01T00:00:00.000Z",
                "stcd": "27"
            }
        }
        with patch.object(SandboxGSTClient, 'is_configured', return_value=True):
            with patch.object(SandboxGSTClient, 'execute_request', return_value=mock_res):
                client = SandboxGSTClient(company=self.company_a)
                parsed = client.search_taxpayer("27AADCB2230M1ZT")
                self.assertTrue(parsed["success"])
                self.assertEqual(parsed["legal_name"], "TATA CONSULTANCY SERVICES LIMITED")

    def test_sandbox_client_ssrf_host_allowlist_enforced(self):
        """
        Verifies that user-supplied malicious or unallowlisted base URLs
        are rejected and safely reset to the default allowlisted host.
        """
        self.config_a.sandbox_base_url = 'http://169.254.169.254/latest/meta-data'
        self.config_a.save()
        client = SandboxGSTClient(company=self.company_a)
        _, _, base_url, _ = client.get_api_credentials()
        self.assertNotIn('169.254', base_url)
        self.assertIn(base_url, ['https://api.sandbox.co.in', 'https://test-api.sandbox.co.in'])

    def test_sandbox_client_token_caching_without_config_row(self):
        """
        Verifies that when CompanyGSTConfig is absent, JWT tokens are cached
        in Django cache to prevent token stampedes on /authenticate.
        """
        from django.core.cache import cache
        cache.clear()

        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {"access_token": "global_jwt_token_123", "expires_in": 3600}

        with patch('apps.gst.services.sandbox_client.requests.request', return_value=mock_auth) as mock_req:
            with patch('django.conf.settings.SANDBOX_API_KEY', 'platform_key'):
                with patch('django.conf.settings.SANDBOX_API_SECRET', 'platform_secret'):
                    # Company B has no CompanyGSTConfig record
                    client = SandboxGSTClient(company=self.company_b)
                    token1 = client.get_access_token()
                    self.assertEqual(token1, "global_jwt_token_123")
                    self.assertEqual(mock_req.call_count, 1)

                    # Second call must hit Django cache without executing requests.request
                    token2 = client.get_access_token()
                    self.assertEqual(token2, "global_jwt_token_123")
                    self.assertEqual(mock_req.call_count, 1)

    def test_sandbox_client_nested_expires_in(self):
        """Verifies that nested 'expires_in' inside data payload is correctly parsed."""
        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {
            "status_code": 200,
            "data": {
                "access_token": "nested_jwt_token",
                "expires_in": 7200
            }
        }
        with patch('apps.gst.services.sandbox_client.requests.request', return_value=mock_auth):
            client = SandboxGSTClient(company=self.company_a)
            token = client.get_access_token(force_refresh=True)
            self.assertEqual(token, "nested_jwt_token")
            self.config_a.refresh_from_db()
            self.assertIsNotNone(self.config_a.sandbox_token_expires_at)
            # Should expire ~2 hours (7200s) from now, not 24 hours
            diff = self.config_a.sandbox_token_expires_at - timezone.now()
            self.assertTrue(7100 <= diff.total_seconds() <= 7210)

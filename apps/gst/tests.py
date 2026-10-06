from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem, FinancialYear
from apps.accounting.services.voucher_service import VoucherService
from apps.gst.models import CompanyGSTConfig, EWayBillRecord, GSTTaxpayerCache
from apps.gst.services.gstin_validator import GSTINValidator
from apps.gst.services.gstin_lookup_service import GSTINLookupService
from apps.gst.services.eway_bill_service import EWayBillService
from apps.gst.services.gstr_report_service import GSTRReportService

User = get_user_model()

class GSTIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='gst_test@example.com',
            password='testpassword123'
        )
        self.company = Company.objects.create(
            name="Maa Annapurna Belting Store",
            gstin="09AAACB1234C1Z1",
            state_code="09",
            state_name="Uttar Pradesh",
            address="Plot 10, Industrial Estate",
            city="Kanpur",
            pincode="208001"
        )
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31)
        )
        # Groups
        self.debtors_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.sales_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")
        self.tax_grp = LedgerGroup.objects.create(company=self.company, name="Duties & Taxes", nature="LIABILITY")

        # Ledgers
        self.customer = Ledger.objects.create(
            company=self.company,
            name="Classic Pipe Enterprises",
            group=self.debtors_grp,
            ledger_type="CUSTOMER",
            gstin="24AABCC1234D1Z8",
            state_code="24"
        )
        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            name="Sales Account",
            group=self.sales_grp,
            ledger_type="SALES"
        )
        self.cgst = Ledger.objects.create(company=self.company, name="Output CGST", group=self.tax_grp, ledger_type="TAX")
        self.sgst = Ledger.objects.create(company=self.company, name="Output SGST", group=self.tax_grp, ledger_type="TAX")
        self.igst = Ledger.objects.create(company=self.company, name="Output IGST", group=self.tax_grp, ledger_type="TAX")

        # Product
        self.product = Product.objects.create(
            company=self.company,
            name="V-Belt B-65",
            sku="VB-B65",
            hsn_code="8483",
            unit="PCS",
            selling_price=Decimal("500.00"),
            purchase_price=Decimal("400.00"),
            gst_rate=Decimal("18.00")
        )

    def test_01_gstin_validator(self):
        """Test checksum verification and state code extraction"""
        valid = GSTINValidator.validate("09AAACB1234C1Z1")
        self.assertTrue(valid['is_valid'])
        self.assertEqual(valid['state_code'], "09")
        self.assertEqual(valid['state_name'], "Uttar Pradesh")
        self.assertEqual(valid['pan'], "AAACB1234C")

        invalid = GSTINValidator.validate("INVALID_GSTIN")
        self.assertFalse(invalid['is_valid'])

    def test_02_gstin_lookup_service(self):
        """Test party detail auto-fetch with mock provider and persistent caching"""
        res = GSTINLookupService.lookup_gstin("24AABCC1234D1Z8", company=self.company)
        self.assertTrue(res['success'])
        self.assertEqual(res['trade_name'], "Classic Pipe Enterprises")
        self.assertEqual(res['state_code'], "24")
        self.assertEqual(res['status'], "Active")

        # Verify cached in database
        cached = GSTTaxpayerCache.objects.filter(gstin="24AABCC1234D1Z8").first()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.trade_name, "Classic Pipe Enterprises")

        # Repeated call should hit cache
        res2 = GSTINLookupService.lookup_gstin("24AABCC1234D1Z8", company=self.company)
        self.assertTrue(res2.get('is_cached'))

    def test_03_eway_bill_generation_and_lifecycle(self):
        """Test E-Way bill generation, vehicle update, and cancellation"""
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV/26-27/0050",
            voucher_date=date(2026, 8, 15),
            party_ledger=self.customer,
            total_amount=Decimal("59000.00"),
            status="POSTED",
            created_by=self.user
        )
        VoucherItem.objects.create(
            voucher=voucher,
            product=self.product,
            quantity=Decimal("100.00"),
            rate=Decimal("500.00"),
            total_amount=Decimal("59000.00"),
            taxable_amount=Decimal("50000.00"),
            gst_rate=Decimal("18.00"),
            igst_amount=Decimal("9000.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00")
        )

        transport_details = {
            "transport_mode": "1",
            "distance_km": 350,
            "vehicle_number": "UP78BT4521",
            "transporter_id": "09AAACB1234C1Z1",
            "transporter_name": "FastTrack Logistics"
        }

        gen_res = EWayBillService.generate_for_voucher(voucher, transport_details, self.user)
        self.assertTrue(gen_res['success'])
        self.assertIn('ewb_number', gen_res)
        self.assertEqual(gen_res['status'], 'ACTIVE')

        ewb = EWayBillRecord.objects.get(ewb_number=gen_res['ewb_number'])
        self.assertEqual(ewb.vehicle_number, "UP78BT4521")
        self.assertEqual(ewb.distance_km, 350)

        # Update vehicle
        upd_res = EWayBillService.update_vehicle(ewb, "UP78BT9999", reason="Breakdown")
        self.assertTrue(upd_res['success'])
        ewb.refresh_from_db()
        self.assertEqual(ewb.vehicle_number, "UP78BT9999")

        # Cancel E-Way Bill
        can_res = EWayBillService.cancel_eway_bill(ewb, reason="1", remarks="Order cancelled by customer")
        self.assertTrue(can_res['success'])
        ewb.refresh_from_db()
        self.assertEqual(ewb.status, "CANCELLED")

    def test_04_gstr1_json_generation(self):
        """Test GSTR-1 JSON structure matches GSTN Offline format"""
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV/26-27/0051",
            voucher_date=date(2026, 8, 20),
            party_ledger=self.customer,
            total_amount=Decimal("11800.00"),
            status="POSTED",
            created_by=self.user
        )
        VoucherItem.objects.create(
            voucher=voucher,
            product=self.product,
            quantity=Decimal("20.00"),
            rate=Decimal("500.00"),
            total_amount=Decimal("11800.00"),
            taxable_amount=Decimal("10000.00"),
            gst_rate=Decimal("18.00"),
            igst_amount=Decimal("1800.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00")
        )

        gstr1 = GSTRReportService.generate_gstr1(self.company, "2026-08-01", "2026-08-31")
        self.assertIn("b2b", gstr1)
        self.assertIn("hsn", gstr1)
        self.assertIn("doc_issue", gstr1)
        self.assertEqual(len(gstr1["b2b"]), 1)
        self.assertEqual(gstr1["b2b"][0]["ctin"], "24AABCC1234D1Z8")
        self.assertEqual(gstr1["b2b"][0]["inv"][0]["inum"], "INV/26-27/0051")

    def test_05_gst_credential_envelope_encryption(self):
        """Test Fernet AES-256 envelope encryption at rest for GST credentials."""
        from apps.gst.encryption import ENCRYPTION_PREFIX, encrypt_gst_credential, decrypt_gst_credential
        from django.db import connection

        raw_secret = "super_secret_portal_key_xyz_9988"
        raw_password = "nic_portal_password_secure!@#"

        config, _ = CompanyGSTConfig.objects.get_or_create(company=self.company)
        config.api_secret = raw_secret
        config.eway_password = raw_password
        config.save()

        # 1. Verify that raw database column contains ciphertext starting with enc:v1:
        with connection.cursor() as cursor:
            cursor.execute("SELECT api_secret, eway_password FROM gst_companygstconfig WHERE id = %s OR id = %s", [str(config.id), config.id.hex])
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            db_secret, db_password = row[0], row[1]

        self.assertTrue(db_secret.startswith(ENCRYPTION_PREFIX))
        self.assertTrue(db_password.startswith(ENCRYPTION_PREFIX))
        self.assertNotIn(raw_secret, db_secret)
        self.assertNotIn(raw_password, db_password)

        # 2. Verify that Python ORM transparently decrypts the ciphertext
        config.refresh_from_db()
        self.assertEqual(config.api_secret, raw_secret)
        self.assertEqual(config.eway_password, raw_password)

        # 3. Verify backward compatibility: legacy unencrypted values are returned as-is
        self.assertEqual(decrypt_gst_credential("legacy_plaintext"), "legacy_plaintext")

    def test_06_cross_tenant_itc_authorization_barrier(self):
        """Test strict cross-tenant isolation on ITC endpoints: unauthorized user cannot access Company B."""
        from apps.companies.models import UserCompany
        from rest_framework.test import APIClient

        # Setup Company A membership for self.user
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        # Create separate victim Company B with separate user
        attacker_user = User.objects.create_user(email='attacker@example.com', password='attackerpass123')
        victim_company = Company.objects.create(
            name="Victim Enterprises Pvt Ltd",
            gstin="27AAACV9999Z1Z5",
            state_code="27",
            state_name="Maharashtra"
        )
        # Attacker is ONLY a member of Company A
        UserCompany.objects.create(user=attacker_user, company=self.company, role='ADMIN')

        client = APIClient()
        client.force_authenticate(user=attacker_user)

        # Attacker attempts to upload GSTR-2B for Victim Company B
        res_upload = client.post(
            '/api/v1/gst/itc/upload-2b/',
            data={'json_data': '{"b2b": []}', 'return_period': '082026'},
            HTTP_X_COMPANY_ID=str(victim_company.id),
            format='json'
        )
        self.assertEqual(res_upload.status_code, 403)

        # Attacker attempts to read ITC list of Victim Company B
        res_list = client.get(
            '/api/v1/gst/itc/reconciliation/',
            HTTP_X_COMPANY_ID=str(victim_company.id)
        )
        self.assertEqual(res_list.status_code, 403)

        # Attacker attempts to apply Smart Payment Hold on Victim Company B
        res_hold = client.post(
            '/api/v1/gst/itc/hold-gst/',
            data={'voucher_id': '00000000-0000-0000-0000-000000000000', 'held_amount': 5000},
            HTTP_X_COMPANY_ID=str(victim_company.id),
            format='json'
        )
        self.assertEqual(res_hold.status_code, 403)

    def test_07_gst_filing_record_durable_persistence(self):
        """Test that marking a GST return as filed authoritatively creates a durable GSTFilingRecord."""
        from apps.companies.models import UserCompany
        from apps.gst.models import GSTFilingRecord
        from rest_framework.test import APIClient

        UserCompany.objects.create(user=self.user, company=self.company, role='CA')
        client = APIClient()
        client.force_authenticate(user=self.user)

        post_res = client.post(
            f'/api/v1/gst/returns/mark-filed/{self.company.id}/',
            data={
                'period': '082026',
                'return_type': 'GSTR1',
                'total_taxable_value': '150000.00',
                'total_tax_amount': '27000.00'
            },
            format='json'
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertTrue(post_res.data['success'])
        self.assertEqual(post_res.data['status'], 'FILED')
        # P0-08: When user does not supply government ARN, arn is None and internal reference is in provider_reference
        self.assertIsNone(post_res.data['arn'])
        self.assertTrue(post_res.data['provider_reference'].startswith('VOUCH-INTERNAL-REF-'))

        # Check database persistence
        filing = GSTFilingRecord.objects.filter(
            company=self.company,
            return_period='082026',
            return_type='GSTR1'
        ).first()
        self.assertIsNotNone(filing)
        self.assertEqual(filing.status, 'FILED')
        self.assertEqual(filing.total_taxable_value, Decimal('150000.00'))
        self.assertEqual(filing.submitted_by, self.user)
        self.assertTrue(filing.provider_reference.startswith('VOUCH-INTERNAL-REF-'))

        # Check GET history
        get_res = client.get(f'/api/v1/gst/returns/mark-filed/{self.company.id}/')
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(len(get_res.data['filings']), 1)
        self.assertEqual(get_res.data['filings'][0]['return_period'], '082026')

        # Test unmarking / toggling filing back to DRAFT
        unmark_res = client.post(
            f'/api/v1/gst/returns/mark-filed/{self.company.id}/',
            data={'period': '082026', 'return_type': 'GSTR1', 'unmark': True},
            format='json'
        )
        self.assertEqual(unmark_res.status_code, 200)
        self.assertEqual(unmark_res.data['status'], 'DRAFT')
        filing.refresh_from_db()
        self.assertEqual(filing.status, 'DRAFT')

    def test_08_gst_credential_rbac_protection(self):
        """Test that VIEWER role is strictly blocked from modifying company GST credentials."""
        from apps.companies.models import UserCompany
        from rest_framework.test import APIClient

        viewer_user = User.objects.create_user(email='viewer@example.com', password='viewerpassword123')
        UserCompany.objects.create(user=viewer_user, company=self.company, role='VIEWER')

        client = APIClient()
        client.force_authenticate(user=viewer_user)

        res = client.post(
            f'/api/v1/gst/config/{self.company.id}/',
            data={'api_secret': 'malicious_override_attempt'},
            format='json'
        )
        self.assertEqual(res.status_code, 403)

    def test_09_fail_closed_encryption_on_corrupted_ciphertext(self):
        """P0-01: Corrupted ciphertext MUST fail closed with CredentialDecryptionError, never returning ciphertext."""
        from apps.gst.encryption import decrypt_gst_credential, CredentialDecryptionError

        corrupted_token = "enc:v1:corrupted_garbage_token_invalid_base64_or_bad_hmac"
        with self.assertRaises(CredentialDecryptionError):
            decrypt_gst_credential(corrupted_token)

    def test_10_gst_filing_with_official_government_arn(self):
        """P0-08: When official government ARN is provided, it is stored in arn directly."""
        from apps.companies.models import UserCompany
        from apps.gst.models import GSTFilingRecord
        from rest_framework.test import APIClient

        UserCompany.objects.create(user=self.user, company=self.company, role='CA')
        client = APIClient()
        client.force_authenticate(user=self.user)

        official_arn = "AA0908260123456"
        post_res = client.post(
            f'/api/v1/gst/returns/mark-filed/{self.company.id}/',
            data={
                'period': '092026',
                'return_type': 'GSTR1',
                'arn': official_arn,
                'total_taxable_value': '200000.00',
                'total_tax_amount': '36000.00'
            },
            format='json'
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.data['arn'], official_arn)

        filing = GSTFilingRecord.objects.filter(
            company=self.company,
            return_period='092026'
        ).first()
        self.assertIsNotNone(filing)
        self.assertEqual(filing.arn, official_arn)

    def test_11_statutory_gst_rbac_separation_of_duties(self):
        """P0-03: EMPLOYEE can view reports but CANNOT file GST returns or modify portal credentials."""
        from apps.companies.models import UserCompany
        from rest_framework.test import APIClient

        employee = User.objects.create_user(email='emp_statutory@example.com', password='empstatutorypass123')
        UserCompany.objects.create(user=employee, company=self.company, role='EMPLOYEE')

        client = APIClient()
        client.force_authenticate(user=employee)

        # 1. EMPLOYEE can view GSTR-3B summary (CanViewGST)
        get_res = client.get(f'/api/v1/gst/reports/gstr3b/{self.company.id}/')
        self.assertEqual(get_res.status_code, 200)

        # 2. EMPLOYEE cannot mark return as filed (CanFileGST requires ADMIN, OWNER, CA)
        file_res = client.post(
            f'/api/v1/gst/returns/mark-filed/{self.company.id}/',
            data={'period': '102026', 'return_type': 'GSTR1'},
            format='json'
        )
        self.assertEqual(file_res.status_code, 403)

        # 3. EMPLOYEE cannot modify GST credentials (CanManageGSTCredentials requires ADMIN, OWNER)
        cred_res = client.post(
            f'/api/v1/gst/config/{self.company.id}/',
            data={'api_key': 'new_key'},
            format='json'
        )
        self.assertEqual(cred_res.status_code, 403)


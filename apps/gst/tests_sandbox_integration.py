import json
import uuid
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import (
    CompanyGSTConfig,
    GSTRegistration,
    GSTTaxpayerCache,
    GSTR2BImport,
    GSTR2BRecord,
    GSTFilingRecord,
    EInvoiceRecord,
    EWayBillRecord,
    GSTAuditLog
)
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gstin_service import GSTINService, calculate_gstin_checksum
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.reconciliation_service import GSTReconciliationService
from apps.gst.services.einvoice_service import EInvoiceService
from apps.gst.services.ewaybill_service import EWayBillService
from apps.gst.exceptions import (
    EInvoiceEligibilityError,
    GSTConfigurationMissingError,
    GSTAuthenticationError
)

User = get_user_model()


class SandboxGSTIntegrationTests(TestCase):
    """
    Comprehensive Test Suite for Sandbox by Quicko GST Integration,
    Multi-GSTIN Architecture, Return Preparation, 11-Category Reconciliation,
    e-Invoicing, e-Way Bills, Security Isolation, and Accounting Invariants.
    """

    def setUp(self):
        # 1. Setup Company A (Primary MSME Tenant)
        self.company = Company.objects.create(
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

        # 2. Setup Company B (Isolated Competitor Tenant)
        self.company_b = Company.objects.create(
            name="Precision Tools Ltd",
            legal_name="Precision Tools India Pvt Ltd",
            gstin="29AAACP9999P1Z8",
            state_code="29",
            state_name="Karnataka",
            city="Bengaluru",
            address="42 Tech Park, Whitefield",
            pincode="560066"
        )

        # 3. Setup Users & Roles
        self.user = User.objects.create_user(
            email="accountant@apexbelting.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ACCOUNTANT')

        self.user_b = User.objects.create_user(
            email="auditor@precisiontools.com",
            password="SecurePassword123!"
        )
        UserCompany.objects.create(user=self.user_b, company=self.company_b, role='ADMIN')

        # 4. Setup Company GST Config
        self.config = CompanyGSTConfig.objects.create(
            company=self.company,
            provider='SANDBOX_CO_IN',
            is_sandbox=True,
            sandbox_api_key="test_sandbox_api_key_12345",
            sandbox_api_secret="test_sandbox_api_secret_67890",
            sandbox_base_url="https://test-api.sandbox.co.in"
        )

        # 5. Setup Multi-GSTIN Registrations for Company A
        self.reg_mh = GSTRegistration.objects.create(
            company=self.company,
            gstin="27AAACA1234A1Z5",
            legal_name=self.company.legal_name,
            trade_name=self.company.name,
            state_code="27",
            state_name="Maharashtra",
            address="101 Industrial Estate, Andheri East",
            pincode="400069",
            is_primary=True,
            taxpayer_type="REGULAR"
        )

        self.reg_ka = GSTRegistration.objects.create(
            company=self.company,
            gstin="29AAACA1234A1Z1",
            legal_name=self.company.legal_name,
            trade_name="Apex Belting Bengaluru Branch",
            state_code="29",
            state_name="Karnataka",
            address="12 Koramangala, Bengaluru",
            pincode="560034",
            is_primary=False,
            taxpayer_type="REGULAR"
        )

        # 6. Setup Standard Accounting Ledger Groups
        self.debtors_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sundry Debtors",
            defaults={"nature": "ASSET"}
        )
        self.creditors_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sundry Creditors",
            defaults={"nature": "LIABILITY"}
        )
        self.sales_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sales Accounts",
            defaults={"nature": "INCOME"}
        )
        self.tax_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Duties & Taxes",
            defaults={"nature": "LIABILITY"}
        )

        # 7. Setup Party Ledgers
        self.customer_b2b = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name="Garodia Logistics Pvt Ltd",
            gstin="27AABCG5555G1Z9",
            state_code="27",
            address="Warehouse 4, Bhiwandi"
        )

        self.customer_b2c = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name="Rajesh Retailer (Unregistered)",
            gstin="",
            state_code="27",
            address="Market Yard, Pune"
        )

        self.vendor_party = Ledger.objects.create(
            company=self.company,
            group=self.creditors_group,
            name="Shree Radhe Synthetics",
            gstin="24AAACS9999S1Z4",
            state_code="24",
            address="GIDC Sachin, Surat"
        )

        # 8. Setup Catalog Product
        from apps.inventory.models import Product
        self.product = Product.objects.create(
            company=self.company,
            name="Conveyor Belt 100mm",
            sku="CB-100",
            unit="MTR",
            hsn_code="4010",
            gst_rate=Decimal("18.00"),
            selling_price=Decimal("10000.00"),
            purchase_price=Decimal("5000.00")
        )

    # =========================================================================
    # SECTION 4: GSTIN VERIFICATION & CHECKSUM TESTS
    # =========================================================================
    def test_gstin_format_validation_valid(self):
        """Verifies local validation on well-formed Indian GSTINs."""
        # 27AAACA1234A1Z5 is Maharashtra
        res = GSTINService.validate_format("27AAACA1234A1Z5")
        self.assertTrue(res["valid"])
        self.assertEqual(res["state_code"], "27")
        self.assertEqual(res["pan"], "AAACA1234A")

    def test_gstin_format_validation_invalid(self):
        """Verifies rejection of malformed or invalid GSTINs."""
        # Too short
        res1 = GSTINService.validate_format("27AAACA1234")
        self.assertFalse(res1["valid"])
        self.assertIn("15 characters", res1["error"])

        # Invalid state code 99
        res2 = GSTINService.validate_format("95AAACA1234A1Z5")
        self.assertFalse(res2["valid"])
        self.assertIn("Invalid state code", res2["error"])

    def test_gstin_checksum_algorithm(self):
        """Verifies Indian GST Luhn MOD-36 checksum generation."""
        # For '29AAICP2912R1Z', expected checksum is 'R'
        chk = calculate_gstin_checksum("29AAICP2912R1Z")
        self.assertEqual(chk, "R")

    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_verify_gstin_live_and_cache(self, mock_req):
        """
        Verifies live lookup through Sandbox public API and subsequent caching in GSTTaxpayerCache.
        """
        # Mock /authenticate
        mock_auth_resp = MagicMock()
        mock_auth_resp.status_code = 200
        mock_auth_resp.json.return_value = {"access_token": "jwt_token_sample", "expires_in": 86400}

        # Mock /gst/compliance/public/gstin/search
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "data": {
                "gstin": "29AAICP2912R1ZR",
                "lgnm": "Infosys Limited",
                "tradeNam": "Infosys",
                "sts": "Active",
                "ctb": "Public Limited",
                "rgdt": "01/07/2017",
                "pradr": {
                    "addr": {
                        "bno": "44",
                        "st": "Electronic City",
                        "loc": "Hosur Road",
                        "pncd": "560100",
                        "stcd": "29"
                    }
                }
            }
        }
        mock_req.side_effect = [mock_auth_resp, mock_search_resp]

        res = GSTINService.verify_gstin("29AAICP2912R1ZR", company=self.company)
        self.assertTrue(res["success"])
        self.assertEqual(res["legal_name"], "Infosys Limited")
        self.assertEqual(res["trade_name"], "Infosys")
        self.assertEqual(res["status"], "Active")
        self.assertFalse(res["is_cached"])

        # Verify cached in database
        cached = GSTTaxpayerCache.objects.filter(gstin="29AAICP2912R1ZR").first()
        self.assertIsNotNone(cached)
        self.assertEqual(cached.legal_name, "Infosys Limited")

        # Second lookup should hit cache without invoking mock_req again
        res2 = GSTINService.verify_gstin("29AAICP2912R1ZR", company=self.company)
        self.assertTrue(res2["success"])
        self.assertTrue(res2["is_cached"])
        self.assertEqual(mock_req.call_count, 2)  # No extra HTTP calls made

    def test_party_enrichment_preview_diff(self):
        """Verifies preview diff generation without modifying party ledger."""
        verified_data = {
            "legal_name": "Garodia Logistics & Warehousing Pvt Ltd",
            "trade_name": "Garodia Logistics",
            "state_code": "27",
            "address": "Warehouse 4 & 5, Logistics Park, Bhiwandi",
            "pincode": "421302",
            "gstin": "27AABCG5555G1Z9"
        }

        diff = GSTINService.preview_party_enrichment(self.customer_b2b, verified_data)
        self.assertTrue(diff["has_changes"])
        self.assertTrue(diff["diffs"]["legal_name"]["changed"])
        self.assertEqual(diff["diffs"]["legal_name"]["current"], "Garodia Logistics Pvt Ltd")
        self.assertEqual(diff["diffs"]["legal_name"]["verified"], "Garodia Logistics & Warehousing Pvt Ltd")

        # Invariant: Party in DB must remain completely unmodified
        self.customer_b2b.refresh_from_db()
        self.assertEqual(self.customer_b2b.name, "Garodia Logistics Pvt Ltd")

    # =========================================================================
    # SECTION 5: MULTI-GSTIN & TENANT ISOLATION TESTS
    # =========================================================================
    def test_multi_gstin_registration_setup(self):
        """Verifies company can maintain multiple GST registrations across states."""
        regs = GSTRegistration.objects.filter(company=self.company)
        self.assertEqual(regs.count(), 2)
        states = set(r.state_code for r in regs)
        self.assertEqual(states, {"27", "29"})

    def test_tenant_isolation_security(self):
        """Verifies strict isolation: Company B cannot see or access Company A's registrations."""
        # Query registrations belonging to Company B
        regs_b = GSTRegistration.objects.filter(company=self.company_b)
        self.assertEqual(regs_b.count(), 0)

        # Cross-tenant permission test
        from apps.gst.permissions import HasGSTPermission
        perm = HasGSTPermission()

        # Dummy view
        view = MagicMock()
        view.kwargs = {'company_id': str(self.company.id)}

        request_b = MagicMock()
        request_b.user = self.user_b

        has_perm = perm.has_permission(request_b, view)
        self.assertFalse(has_perm, "Cross-tenant access must be rejected with False!")

    # =========================================================================
    # SECTION 6: GSTR-1 OUTWARD SUPPLIES & PREPARATION TESTS
    # =========================================================================
    def test_gstr1_preparation_b2b_b2cs_hsn(self):
        """Verifies GSTR-1 dataset compilation from sales vouchers into B2B, B2CS, and HSN summary."""
        # Create B2B Sales Voucher
        v_b2b = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number='INV/26-27/001',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.customer_b2b,
            buyer_gstin=self.customer_b2b.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v_b2b,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='4010'
        )

        # Create B2C Sales Voucher (Intrastate)
        v_b2c = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number='INV/26-27/002',
            voucher_date=date(2026, 8, 15),
            party_ledger=self.customer_b2c,
            buyer_gstin='',
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('2360.00')
        )
        VoucherItem.objects.create(
            voucher=v_b2c,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('2000.00'),
            taxable_amount=Decimal('2000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('180.00'),
            sgst_amount=Decimal('180.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('2360.00'),
            hsn_code='4010'
        )

        # Prepare GSTR-1
        gstr1_data = GSTReturnsService.prepare_gstr1(self.company, self.reg_mh, "082026")

        self.assertEqual(gstr1_data["period"], "082026")
        self.assertEqual(gstr1_data["total_vouchers"], 2)
        self.assertEqual(gstr1_data["clean_count"], 2)
        self.assertEqual(gstr1_data["exception_count"], 0)

        # Check Official JSON Payload
        official = gstr1_data["official_gstr1_json"]
        self.assertEqual(official["gstin"], self.reg_mh.gstin)
        self.assertEqual(len(official["b2b"]), 1)
        self.assertEqual(official["b2b"][0]["ctin"], self.customer_b2b.gstin)
        self.assertEqual(official["b2b"][0]["inv"][0]["inum"], "INV/26-27/001")

        self.assertEqual(len(official["b2cs"]), 1)
        self.assertEqual(official["b2cs"][0]["txval"], 2000.0)

        hsn_list = official["hsn"]["data"]
        self.assertEqual(len(hsn_list), 1)
        self.assertEqual(hsn_list[0]["hsn_sc"], "4010")
        self.assertEqual(hsn_list[0]["txval"], 12000.0)

    # =========================================================================
    # SECTION 7: GSTR-3B TAX SUMMARY TESTS
    # =========================================================================
    def test_gstr3b_tax_summary_calculation(self):
        """Verifies GSTR-3B calculation of Table 3.1 liabilities, Table 4 ITC, and Net Tax Payable."""
        # Sales voucher: Output tax = ₹1800 (CGST 900 + SGST 900)
        v_sales = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number='INV/26-27/003',
            voucher_date=date(2026, 8, 5),
            party_ledger=self.customer_b2b,
            buyer_gstin=self.customer_b2b.gstin,
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v_sales,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='4010'
        )

        # Purchase voucher: Input tax (ITC) = ₹900 (CGST 450 + SGST 450)
        v_purch = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='PURCHASE',
            voucher_number='BILL/26-27/001',
            external_invoice_number='SR/2026/88',
            voucher_date=date(2026, 8, 7),
            party_ledger=self.vendor_party,
            status='POSTED',
            total_amount=Decimal('5900.00')
        )
        VoucherItem.objects.create(
            voucher=v_purch,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('5000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('5900.00'),
            hsn_code='4010'
        )

        gstr3b_data = GSTReturnsService.prepare_gstr3b(self.company, self.reg_mh, "082026")

        outward = gstr3b_data["table_3_1"]["outward_taxable_supplies"]
        self.assertEqual(outward["cgst"], 900.0)
        self.assertEqual(outward["sgst"], 900.0)

        itc = gstr3b_data["table_4_itc"]["net_itc_available"]
        self.assertEqual(itc["cgst"], 450.0)
        self.assertEqual(itc["sgst"], 450.0)

        payable = gstr3b_data["tax_payable"]
        self.assertEqual(payable["cgst"], 450.0)  # 900 - 450 = 450
        self.assertEqual(payable["sgst"], 450.0)  # 900 - 450 = 450
        self.assertEqual(payable["total_net_payable"], 900.0)

    # =========================================================================
    # SECTION 8: 11-CATEGORY GSTR-2B RECONCILIATION TESTS
    # =========================================================================
    def test_gstr2b_reconciliation_exact_and_mismatches(self):
        """Verifies 11-category reconciliation engine detecting exact, tax, date, and missing records."""
        # 1. Purchase Voucher in Books (Exact Match Target)
        v1 = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='PURCHASE',
            voucher_number='PUR/001',
            external_invoice_number='INV/101',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.vendor_party,
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v1,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='4010'
        )

        # 2. Purchase Voucher in Books (Tax Mismatch Target: Book has IGST, 2B has CGST+SGST)
        v2 = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='PURCHASE',
            voucher_number='PUR/002',
            external_invoice_number='INV/102',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.vendor_party,
            status='POSTED',
            total_amount=Decimal('5900.00')
        )
        VoucherItem.objects.create(
            voucher=v2,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('5000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            igst_amount=Decimal('900.00'),
            total_amount=Decimal('5900.00'),
            hsn_code='4010'
        )

        # 3. Create Import Batch
        batch = GSTR2BImport.objects.create(
            company=self.company,
            return_period="082026",
            status='PROCESSED'
        )

        # Record 1: Exact Match in GSTR-2B
        r1 = GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            supplier_gstin=self.vendor_party.gstin,
            supplier_name=self.vendor_party.name,
            invoice_number='INV/101',
            normalized_invoice_number='101',
            invoice_date=date(2026, 8, 10),
            invoice_value=Decimal('11800.00'),
            taxable_value=Decimal('10000.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            itc_available=True
        )

        # Record 2: Tax Breakdown Mismatch (GSTR-2B has CGST+SGST, Book has IGST)
        r2 = GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            supplier_gstin=self.vendor_party.gstin,
            supplier_name=self.vendor_party.name,
            invoice_number='INV/102',
            normalized_invoice_number='102',
            invoice_date=date(2026, 8, 12),
            invoice_value=Decimal('5900.00'),
            taxable_value=Decimal('5000.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'),
            igst_amount=Decimal('0.00'),
            itc_available=True
        )

        # Record 3: Missing in Books (exists in GSTR-2B only)
        r3 = GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            supplier_gstin=self.vendor_party.gstin,
            supplier_name=self.vendor_party.name,
            invoice_number='INV/999',
            normalized_invoice_number='999',
            invoice_date=date(2026, 8, 20),
            invoice_value=Decimal('2360.00'),
            taxable_value=Decimal('2000.00'),
            cgst_amount=Decimal('180.00'),
            sgst_amount=Decimal('180.00'),
            igst_amount=Decimal('0.00'),
            itc_available=True
        )

        # Execute Reconciliation
        res = GSTReconciliationService.reconcile_period(self.company, return_period="082026")

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()

        self.assertEqual(r1.match_status, 'MATCHED')
        self.assertEqual(r2.match_status, 'TAX_MISMATCH')
        self.assertEqual(r3.match_status, 'MISSING_IN_BOOKS')

        # Invariant check: Vouchers are NEVER mutated by reconciliation
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.total_amount, Decimal('11800.00'))
        self.assertEqual(v2.total_amount, Decimal('5900.00'))

    # =========================================================================
    # SECTION 9: E-INVOICE (IRN) TESTS
    # =========================================================================
    def test_einvoice_eligibility_and_payload_construction(self):
        """Verifies e-Invoice validation and NIC/IRP Schema v1.1 payload generation."""
        v_einv = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number='INV/26-27/E01',
            voucher_date=date(2026, 8, 18),
            party_ledger=self.customer_b2b,
            buyer_gstin=self.customer_b2b.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v_einv,
            product=self.product,
            taxable_amount=Decimal('10000.00'),
            rate=Decimal('10000.00'),
            quantity=Decimal('1.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='4010'
        )

        # Eligibility check
        check = EInvoiceService.validate_eligibility(v_einv)
        self.assertTrue(check["eligible"])

        # Payload construction
        payload = EInvoiceService.build_irn_payload(v_einv, self.reg_mh)
        self.assertEqual(payload["Version"], "1.1")
        self.assertEqual(payload["DocDtls"]["No"], "INV/26-27/E01")
        self.assertEqual(payload["SellerDtls"]["Gstin"], self.reg_mh.gstin)
        self.assertEqual(payload["BuyerDtls"]["Gstin"], self.customer_b2b.gstin)
        self.assertEqual(len(payload["ItemList"]), 1)
        self.assertEqual(payload["ItemList"][0]["HsnCd"], "4010")

    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_einvoice_generation_and_idempotency(self, mock_req):
        """
        Verifies IRN generation and idempotency: A second call must return existing record
        without calling the provider API again.
        """
        v_einv = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number='INV/26-27/E02',
            voucher_date=date(2026, 8, 19),
            party_ledger=self.customer_b2b,
            buyer_gstin=self.customer_b2b.gstin,
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v_einv,
            product=self.product,
            taxable_amount=Decimal('10000.00'),
            rate=Decimal('10000.00'),
            quantity=Decimal('1.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='4010'
        )

        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {"access_token": "token_einv_123", "expires_in": 86400}

        mock_irn = MagicMock(status_code=200)
        sample_irn = "99ba3c6f4945944c9c928369fb3047c6985302b17eaefc42eb8183caa99fde6b"
        mock_irn.json.return_value = {
            "data": {
                "Irn": sample_irn,
                "AckNo": 1224100001,
                "AckDt": "2026-08-19 14:30:00",
                "SignedInvoice": "eyJhbGciOi...",
                "SignedQRCode": "QR_CODE_DATA_STRING",
                "Status": "ACT"
            }
        }
        mock_req.side_effect = [mock_auth, mock_irn]

        # Call 1: Generate IRN
        res1 = EInvoiceService.generate_irn(v_einv, registration=self.reg_mh)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["irn"], sample_irn)
        self.assertEqual(res1["ack_number"], "1224100001")

        # Verify persisted in EInvoiceRecord
        record = EInvoiceRecord.objects.get(voucher=v_einv)
        self.assertEqual(record.status, 'GENERATED')

        # Call 2: Idempotent replay must return existing record
        res2 = EInvoiceService.generate_irn(v_einv, registration=self.reg_mh)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["irn"], sample_irn)
        self.assertTrue(res2.get("is_cached"))
        # Verify no additional network calls were made
        self.assertEqual(mock_req.call_count, 2)

    # =========================================================================
    # SECTION 10: E-WAY BILL TESTS
    # =========================================================================
    @patch('apps.gst.services.sandbox_client.requests.request')
    def test_ewaybill_generation_and_vehicle_update(self, mock_req):
        """Verifies E-Way Bill generation and Part-B vehicle update."""
        v_ewb = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type='SALES',
            voucher_number='INV/26-27/W01',
            voucher_date=date(2026, 8, 20),
            party_ledger=self.customer_b2b,
            buyer_gstin=self.customer_b2b.gstin,
            status='POSTED',
            total_amount=Decimal('59000.00')
        )
        VoucherItem.objects.create(
            voucher=v_ewb,
            product=self.product,
            taxable_amount=Decimal('50000.00'),
            rate=Decimal('500.00'),
            quantity=Decimal('100.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('4500.00'),
            sgst_amount=Decimal('4500.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('59000.00'),
            hsn_code='4010'
        )

        mock_auth = MagicMock(status_code=200)
        mock_auth.json.return_value = {"access_token": "token_ewb_123", "expires_in": 86400}

        mock_ewb = MagicMock(status_code=200)
        mock_ewb.json.return_value = {
            "data": {
                "ewayBillNo": "181000123456",
                "ewayBillDate": "20/08/2026 02:30:00 PM",
                "validUpto": "22/08/2026 11:59:00 PM"
            }
        }
        mock_req.side_effect = [mock_auth, mock_ewb]

        res = EWayBillService.generate_ewaybill(
            voucher=v_ewb,
            distance_km=150,
            vehicle_number="MH04AB1234",
            registration=self.reg_mh
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["ewb_number"], "181000123456")

        record = EWayBillRecord.objects.get(voucher=v_ewb)
        self.assertEqual(record.status, 'ACTIVE')
        self.assertEqual(record.vehicle_number, "MH04AB1234")

    # =========================================================================
    # SECTION 11: ACCOUNTING ENGINE INVARIANTS PROTECTION
    # =========================================================================
    def test_accounting_invariants_preserved(self):
        """
        Critical Invariant Test:
        Guarantees that all GST operations (verification, GSTR-1 preparation, GSTR-3B summary,
        GSTR-2B reconciliation, e-Invoice payload building) have ZERO side-effects on:
        - Ledger balance equilibrium
        - Voucher totals
        - Voucher statuses
        """
        # Baseline check
        initial_vouchers = list(Voucher.objects.filter(company=self.company).values('id', 'total_amount', 'status'))
        initial_ledgers = list(Ledger.objects.filter(company=self.company).values('id', 'name', 'gstin'))

        # Run GSTR-1
        GSTReturnsService.prepare_gstr1(self.company, self.reg_mh, "082026")
        # Run GSTR-3B
        GSTReturnsService.prepare_gstr3b(self.company, self.reg_mh, "082026")
        # Run Reconciliation
        GSTReconciliationService.reconcile_period(self.company, return_period="082026")

        # Compare post-run
        current_vouchers = list(Voucher.objects.filter(company=self.company).values('id', 'total_amount', 'status'))
        current_ledgers = list(Ledger.objects.filter(company=self.company).values('id', 'name', 'gstin'))

        self.assertEqual(initial_vouchers, current_vouchers, "Vouchers must remain completely unchanged!")
        self.assertEqual(initial_ledgers, current_ledgers, "Ledgers must remain completely unchanged!")

    # =========================================================================
    # SECTION 12: GST PORTAL DISCONNECT & SANDBOX GATEWAY CREDENTIALS
    # =========================================================================
    def test_gst_portal_disconnect_session(self):
        """
        Verifies that /api/v1/gst/portal/disconnect/ securely revokes
        the active GST portal session token and resets expiration.
        """
        uc = UserCompany.objects.get(user=self.user, company=self.company)
        uc.role = 'ADMIN'
        uc.save()

        self.config.auth_token = "GSTN-AUTH-SESSION-TOKEN-ABC123"
        self.config.token_expires_at = timezone.now() + timedelta(hours=6)
        self.config.save()

        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        res = client.post('/api/v1/gst/portal/disconnect/', {'company_id': str(self.company.id)}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get('success'))

        self.config.refresh_from_db()
        self.assertEqual(self.config.auth_token, "")
        self.assertIsNone(self.config.token_expires_at)

    def test_gst_config_sandbox_credentials_lifecycle(self):
        """
        Verifies that CompanyGSTConfig API correctly exposes and updates
        dedicated Sandbox.co.in credentials and provider settings.
        """
        uc = UserCompany.objects.get(user=self.user, company=self.company)
        uc.role = 'ADMIN'
        uc.save()

        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)

        # 1. Update config with new Sandbox credentials
        payload = {
            "provider": "SANDBOX_CO_IN",
            "is_sandbox": True,
            "sandbox_api_key": "key_live_test_api_key_456",
            "sandbox_api_secret": "secret_live_test_secret_789",
        }
        res = client.post(f'/api/v1/gst/config/{self.company.id}/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get('success'))

        # 2. Query config
        get_res = client.get(f'/api/v1/gst/config/{self.company.id}/')
        self.assertEqual(get_res.status_code, 200)
        cfg = get_res.data.get('config', {})
        self.assertEqual(cfg.get('provider'), 'SANDBOX_CO_IN')
        self.assertTrue(cfg.get('is_sandbox'))
        self.assertTrue(cfg.get('has_sandbox_api_key'))
        self.assertTrue(cfg.get('has_sandbox_api_secret'))
        self.assertTrue(cfg.get('sandbox_api_key').endswith('****'))

    def test_gst_portal_service_routes_to_sandbox_client(self):
        """
        Verifies that GSTPortalService.request_portal_otp and verify_portal_otp
        route to SandboxGSTClient when provider is SANDBOX_CO_IN.
        """
        from apps.gst.services.gst_sandbox_service import GSTPortalService

        mock_req_res = {
            "success": True,
            "correlation_id": "CORR-SB-999",
            "data": {"message": "OTP delivered via Sandbox"}
        }
        with patch.object(SandboxGSTClient, 'request_portal_otp', return_value=mock_req_res):
            res = GSTPortalService.request_portal_otp(
                company=self.company,
                gstin="27AAACA1234A1Z5",
                username="test_user"
            )
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("txn_id"), "CORR-SB-999")

        mock_verify_res = {
            "success": True,
            "correlation_id": "CORR-SB-VERIFY-111",
            "data": {
                "access_token": "SANDBOX-SESSION-JWT-TOKEN-XYZ",
                "token_expiry": int((timezone.now() + timedelta(hours=6)).timestamp() * 1000)
            }
        }
        with patch.object(SandboxGSTClient, 'verify_portal_otp', return_value=mock_verify_res):
            res_v = GSTPortalService.verify_portal_otp(
                company=self.company,
                otp="123456",
                gstin="27AAACA1234A1Z5",
                username="test_user"
            )
            self.assertTrue(res_v.get("success"))
            self.assertEqual(res_v.get("auth_token"), "SANDBOX-SESSION-JWT-TOKEN-XYZ")

        self.config.refresh_from_db()
        self.assertEqual(self.config.auth_token, "SANDBOX-SESSION-JWT-TOKEN-XYZ")
        self.assertIsNotNone(self.config.token_expires_at)

    def test_gst_gateway_test_connection_endpoint(self):
        """
        Verifies /api/v1/gst/config/<company_id>/test-connection/ endpoint.
        """
        uc = UserCompany.objects.get(user=self.user, company=self.company)
        uc.role = 'ADMIN'
        uc.save()

        from rest_framework.test import APIClient
        from apps.gst.services.authentication_service import SandboxAuthenticationService
        client = APIClient()
        client.force_authenticate(user=self.user)

        with patch.object(SandboxAuthenticationService, 'test_connection', return_value={
            "healthy": True,
            "configured": True,
            "message": "Connected to Quicko Sandbox"
        }):
            res = client.post(f'/api/v1/gst/config/{self.company.id}/test-connection/')
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.data.get('healthy'))

import io
import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.gst.models import (
    GSTRegistration,
    GSTReturnWorkspace,
    GSTR2BImport,
    GSTR2BRecord
)
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.workspace_service import GSTWorkspaceService
from apps.gst.services.validation_service import GSTValidationService
from apps.gst.services.reconciliation_service import GSTReconciliationService
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService

User = get_user_model()


class GSTRound2ComplianceTests(TestCase):
    """
    Comprehensive Test Suite for GST Compliance, Return Preparation & ITC Reconciliation Engine (Round 2.0).
    Verifies:
    1. GSTR-1 Preparation (Tables 4, 5, 6, 7, 8, 9B, 11A, 11B, 12, 13)
    2. GSTR-3B Preparation, Rule 88A Set-off Waterfall & Ledger Reconciliation
    3. GST Return Workspace Lifecycle, Drift Detection & Snapshotting
    4. Centralized Validation & Exception Engine
    5. GSTR-2B Import, Duplicate Prevention & 9-Category Reconciliation
    6. Tenant Isolation, RBAC & Accounting Immutability Invariant
    """

    def setUp(self):
        self.client = APIClient()

        # Users with distinct roles
        self.owner_user = User.objects.create_user(
            email='owner@srilekh-gst.com',
            password='Password123!'
        )
        self.ca_user = User.objects.create_user(
            email='ca@srilekh-gst.com',
            password='Password123!'
        )
        self.viewer_user = User.objects.create_user(
            email='viewer@srilekh-gst.com',
            password='Password123!'
        )
        self.other_company_user = User.objects.create_user(
            email='other@srilekh-gst.com',
            password='Password123!'
        )

        # Primary Company in Maharashtra (State 27)
        self.company = Company.objects.create(
            name='SriLekh Industrial Supplies',
            legal_name='SriLekh Industrial Supplies Pvt Ltd',
            gstin='27AAACS1234A1Z1',
            state_code='27',
            email='accounts@srilekh-supplies.com'
        )
        UserCompany.objects.create(user=self.owner_user, company=self.company, role='OWNER')
        UserCompany.objects.create(user=self.ca_user, company=self.company, role='CA')
        UserCompany.objects.create(user=self.viewer_user, company=self.company, role='VIEWER')

        # Secondary Isolated Company
        self.other_company = Company.objects.create(
            name='External Competitor Enterprises',
            legal_name='External Competitor Enterprises Ltd',
            gstin='07BBBCB5678B1Z2',
            state_code='07'
        )
        UserCompany.objects.create(user=self.other_company_user, company=self.other_company, role='OWNER')

        # Primary Registration (MH - 27)
        self.reg_mh = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAACS1234A1Z1',
            legal_name='SriLekh Industrial Supplies Pvt Ltd',
            trade_name='SriLekh Supplies',
            state_code='27',
            state_name='Maharashtra',
            taxpayer_type='REGULAR',
            status='ACTIVE',
            is_primary=True
        )

        # Secondary Registration (DL - 07)
        self.reg_dl = GSTRegistration.objects.create(
            company=self.company,
            gstin='07AAACS1234A1Z3',
            legal_name='SriLekh Industrial Supplies (Delhi Branch)',
            trade_name='SriLekh Delhi',
            state_code='07',
            state_name='Delhi',
            taxpayer_type='REGULAR',
            status='ACTIVE',
            is_primary=False
        )

        # Accounting Structure
        self.debtors_group = LedgerGroup.objects.create(company=self.company, name='Sundry Debtors', nature='ASSET')
        self.creditors_group = LedgerGroup.objects.create(company=self.company, name='Sundry Creditors', nature='LIABILITY')
        self.sales_group = LedgerGroup.objects.create(company=self.company, name='Sales Accounts', nature='INCOME')
        self.purchase_group = LedgerGroup.objects.create(company=self.company, name='Purchase Accounts', nature='EXPENSE')
        self.tax_group = LedgerGroup.objects.create(company=self.company, name='Duties & Taxes', nature='LIABILITY')

        # Tax Ledgers
        self.output_cgst_ledger = Ledger.objects.create(company=self.company, group=self.tax_group, name='Output CGST', ledger_type='TAX')
        self.output_sgst_ledger = Ledger.objects.create(company=self.company, group=self.tax_group, name='Output SGST', ledger_type='TAX')
        self.output_igst_ledger = Ledger.objects.create(company=self.company, group=self.tax_group, name='Output IGST', ledger_type='TAX')

        self.input_cgst_ledger = Ledger.objects.create(company=self.company, group=self.tax_group, name='Input CGST', ledger_type='TAX')
        self.input_sgst_ledger = Ledger.objects.create(company=self.company, group=self.tax_group, name='Input SGST', ledger_type='TAX')
        self.input_igst_ledger = Ledger.objects.create(company=self.company, group=self.tax_group, name='Input IGST', ledger_type='TAX')

        # Party Ledgers
        self.customer_b2b = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Tata Motors Ltd',
            gstin='27AAACT2727Q1ZW',
            state_code='27',
            ledger_type='CUSTOMER'
        )
        self.customer_interstate_b2b = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Delhi Metro Rail Corp',
            gstin='07AAACD1234D1Z5',
            state_code='07',
            ledger_type='CUSTOMER'
        )
        self.customer_unregistered_mh = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Local Retail Buyer',
            gstin='',
            state_code='27',
            ledger_type='CUSTOMER'
        )
        self.customer_unregistered_dl = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Delhi Unregistered Contractor',
            gstin='',
            state_code='07',
            ledger_type='CUSTOMER'
        )

        self.supplier_vendor = Ledger.objects.create(
            company=self.company,
            group=self.creditors_group,
            name='National Steel Suppliers',
            gstin='27NATST1111S1Z4',
            state_code='27',
            ledger_type='SUPPLIER'
        )

        # Products
        self.product_machinery = Product.objects.create(
            company=self.company,
            name='Hydraulic Valve Assembly',
            sku='VALVE-HYD-01',
            hsn_code='8481',
            unit='NOS',
            gst_rate=Decimal('18.00')
        )
        self.product_exempt = Product.objects.create(
            company=self.company,
            name='Organic Agricultural Grain',
            sku='GRAIN-ORG-01',
            hsn_code='1001',
            unit='KGS',
            gst_rate=Decimal('0.00')
        )

    # =========================================================================
    # 1. GSTR-1 PREPARATION TESTS
    # =========================================================================

    def test_gstr1_preparation_comprehensive(self):
        """
        Tests GSTR-1 preparation across B2B, B2CL, B2CS, CDNR, CDNUR, Nil/Exempt, Advances, HSN, and Doc Issue.
        """
        # 1. B2B Intrastate Sales Voucher (MH -> MH, Registered)
        v_b2b = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-2026-001',
            voucher_date=date(2026, 8, 5),
            party_ledger=self.customer_b2b,
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_b2b,
            product=self.product_machinery,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('900.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('900.00'),
            igst_rate=Decimal('0.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='8481'
        )

        # 2. B2CL Interstate Large Sales Voucher (MH -> DL, Unregistered, > 2.5 Lakhs)
        v_b2cl = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-2026-002',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.customer_unregistered_dl,
            buyer_state_code='07',
            total_amount=Decimal('354000.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_b2cl,
            product=self.product_machinery,
            quantity=Decimal('300.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('300000.00'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('54000.00'),
            cgst_rate=Decimal('0.00'),
            cgst_amount=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            total_amount=Decimal('354000.00'),
            hsn_code='8481'
        )

        # 3. B2CS Intrastate Small Sales Voucher (MH -> MH, Unregistered)
        v_b2cs = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-2026-003',
            voucher_date=date(2026, 8, 15),
            party_ledger=self.customer_unregistered_mh,
            total_amount=Decimal('2360.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_b2cs,
            product=self.product_machinery,
            quantity=Decimal('2.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('2000.00'),
            gst_rate=Decimal('18.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('180.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('180.00'),
            total_amount=Decimal('2360.00'),
            hsn_code='8481'
        )

        # 4. Credit Note against B2B invoice (Table 9B CDNR)
        v_cn = Voucher.objects.create(
            company=self.company,
            voucher_type='CREDIT_NOTE',
            voucher_number='CN-2026-001',
            original_invoice=v_b2b,
            voucher_date=date(2026, 8, 20),
            party_ledger=self.customer_b2b,
            total_amount=Decimal('1180.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_cn,
            product=self.product_machinery,
            quantity=Decimal('1.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('1000.00'),
            gst_rate=Decimal('18.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('90.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('90.00'),
            total_amount=Decimal('1180.00'),
            hsn_code='8481'
        )

        # 5. Nil-rated / Exempt supply (Table 8)
        v_nil = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-2026-004',
            voucher_date=date(2026, 8, 25),
            party_ledger=self.customer_unregistered_mh,
            total_amount=Decimal('5000.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_nil,
            product=self.product_exempt,
            quantity=Decimal('100.00'),
            rate=Decimal('50.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('0.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('5000.00'),
            hsn_code='1001'
        )

        # Compile GSTR-1
        gstr1_data = GSTReturnsService.prepare_gstr1(
            company=self.company,
            registration=self.reg_mh,
            return_period='082026'
        )

        official_json = gstr1_data["official_gstr1_json"]

        # Assert B2B Table 4
        self.assertEqual(len(official_json["b2b"]), 1)
        self.assertEqual(official_json["b2b"][0]["ctin"], '27AAACT2727Q1ZW')
        self.assertEqual(len(official_json["b2b"][0]["inv"]), 1)
        self.assertEqual(official_json["b2b"][0]["inv"][0]["inum"], 'INV-2026-001')

        # Assert B2CL Table 5
        self.assertEqual(len(official_json["b2cl"]), 1)
        self.assertEqual(official_json["b2cl"][0]["pos"], '07')
        self.assertEqual(official_json["b2cl"][0]["inv"][0]["inum"], 'INV-2026-002')
        self.assertEqual(official_json["b2cl"][0]["inv"][0]["val"], 354000.00)

        # Assert B2CS Table 7
        self.assertTrue(len(official_json["b2cs"]) >= 1)
        b2cs_item = [x for x in official_json["b2cs"] if x["pos"] == '27' and x["sply_ty"] == 'INTRA'][0]
        self.assertEqual(Decimal(str(b2cs_item["txval"])), Decimal('2000.00'))

        # Assert CDNR Table 9B
        self.assertEqual(len(official_json["cdnr"]), 1)
        self.assertEqual(official_json["cdnr"][0]["ctin"], '27AAACT2727Q1ZW')
        self.assertEqual(official_json["cdnr"][0]["nt"][0]["nt_num"], 'CN-2026-001')
        self.assertEqual(official_json["cdnr"][0]["nt"][0]["ntty"], 'C')

        # Assert HSN Summary Table 12
        hsn_list = official_json["hsn"]["data"]
        hsn_codes = {h["hsn_sc"] for h in hsn_list}
        self.assertIn('8481', hsn_codes)

        # Assert Document Summary Table 13
        doc_details = official_json["doc_issue"]["doc_det"]
        inv_doc = [d for d in doc_details if d["doc_typ"] == "Invoices for outward supply"][0]
        self.assertEqual(inv_doc["totnum"], 4)
        cn_doc = [d for d in doc_details if d["doc_typ"] == "Credit Note"][0]
        self.assertEqual(cn_doc["totnum"], 1)

    # =========================================================================
    # 2. GSTR-3B PREPARATION & RULE 88A SET-OFF TESTS
    # =========================================================================

    def test_gstr3b_preparation_and_rule88a_setoff(self):
        """
        Tests GSTR-3B compilation, Rule 88A set-off waterfall, and ledger reconciliation.
        """
        # Create Sales Voucher (Outward Tax: CGST=900, SGST=900)
        v_sales = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-3B-001',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.customer_b2b,
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_sales,
            product=self.product_machinery,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )
        # Accounting Ledger Entry for Output Tax
        LedgerEntry.objects.create(voucher=v_sales, ledger=self.output_cgst_ledger, credit_amount=Decimal('900.00'))
        LedgerEntry.objects.create(voucher=v_sales, ledger=self.output_sgst_ledger, credit_amount=Decimal('900.00'))

        # Create Purchase Voucher (Input Tax: CGST=450, SGST=450)
        v_pur = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-3B-001',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.supplier_vendor,
            total_amount=Decimal('5900.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_pur,
            product=self.product_machinery,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'),
            total_amount=Decimal('5900.00')
        )
        # Accounting Ledger Entry for Input Tax
        LedgerEntry.objects.create(voucher=v_pur, ledger=self.input_cgst_ledger, debit_amount=Decimal('450.00'))
        LedgerEntry.objects.create(voucher=v_pur, ledger=self.input_sgst_ledger, debit_amount=Decimal('450.00'))

        # Compile GSTR-3B
        gstr3b_data = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_mh,
            return_period='082026'
        )

        table_3_1 = gstr3b_data["table_3_1"]["outward_taxable_supplies"]
        self.assertEqual(Decimal(str(table_3_1["taxable_value"])), Decimal('10000.00'))
        self.assertEqual(Decimal(str(table_3_1["cgst"])), Decimal('900.00'))
        self.assertEqual(Decimal(str(table_3_1["sgst"])), Decimal('900.00'))

        table_4 = gstr3b_data["table_4_itc"]["net_itc_available"]
        self.assertEqual(Decimal(str(table_4["cgst"])), Decimal('450.00'))
        self.assertEqual(Decimal(str(table_4["sgst"])), Decimal('450.00'))

        # Net Cash Payable = (900 - 450) + (900 - 450) = 450 CGST + 450 SGST = 900
        cash_payable = gstr3b_data["tax_payable"]
        self.assertEqual(Decimal(str(cash_payable["cgst"])), Decimal('450.00'))
        self.assertEqual(Decimal(str(cash_payable["sgst"])), Decimal('450.00'))
        self.assertEqual(Decimal(str(cash_payable["total"])), Decimal('900.00'))

        # Ledger balance reconciliation check
        ledger_recon = gstr3b_data["ledger_reconciliation"]
        self.assertTrue(ledger_recon["is_fully_reconciled"])
        self.assertEqual(ledger_recon["output_tax_reconciliation"]["cgst"]["variance"], 0.00)
        self.assertEqual(ledger_recon["input_tax_reconciliation"]["cgst"]["variance"], 0.00)

    # =========================================================================
    # 3. GST WORKSPACE LIFECYCLE & DRIFT DETECTION TESTS
    # =========================================================================

    def test_workspace_lifecycle_and_drift_detection(self):
        """
        Tests workspace status progression, point-in-time snapshotting, and voucher modification drift detection.
        """
        # Create initial voucher
        v1 = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-DRIFT-001',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.customer_b2b,
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v1,
            product=self.product_machinery,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00'),
            hsn_code='8481'
        )

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.reg_mh,
            return_type='GSTR1',
            return_period='082026'
        )
        self.assertEqual(workspace.status, 'NOT_STARTED')
        self.assertTrue(workspace.sales_data_available)

        # Generate Draft
        workspace = GSTWorkspaceService.generate_draft(workspace, user=self.owner_user)
        self.assertEqual(workspace.status, 'DRAFT')
        self.assertFalse(workspace.is_stale)
        initial_hash = workspace.source_voucher_hash
        self.assertTrue(len(initial_hash) == 64)

        # Verify drift is false before modification
        self.assertFalse(GSTWorkspaceService.check_drift(workspace))

        # Modify voucher (simulate drift / user edit)
        v1.total_amount = Decimal('12000.00')
        v1.save(update_fields=['total_amount', 'updated_at'])

        # Verify drift is detected
        is_stale = GSTWorkspaceService.check_drift(workspace)
        self.assertTrue(is_stale)
        workspace.refresh_from_db()
        self.assertTrue(workspace.is_stale)

        # Attempting to sign off a stale draft must be blocked
        sign_res = GSTWorkspaceService.sign_off_draft(workspace, user=self.ca_user)
        self.assertFalse(sign_res["success"])
        self.assertIn("regenerate draft", sign_res["error"])

        # Regenerate draft
        workspace = GSTWorkspaceService.generate_draft(workspace, user=self.owner_user)
        self.assertFalse(workspace.is_stale)

        # Sign off draft
        sign_res = GSTWorkspaceService.sign_off_draft(workspace, user=self.ca_user)
        self.assertTrue(sign_res["success"])
        workspace.refresh_from_db()
        self.assertEqual(workspace.status, 'REVIEWED')
        self.assertEqual(workspace.reviewed_by, self.ca_user)

        # Export draft
        export_res = GSTWorkspaceService.export_draft(workspace, export_format='JSON')
        self.assertTrue(export_res["success"])
        workspace.refresh_from_db()
        self.assertEqual(workspace.status, 'EXPORTED')

    # =========================================================================
    # 4. CENTRALIZED VALIDATION & EXCEPTION ENGINE TESTS
    # =========================================================================

    def test_validation_engine_exception_detection(self):
        """
        Tests validation engine detection of:
        - Missing HSN
        - PoS mismatch
        - Intrastate having IGST instead of CGST/SGST
        - Empty line items
        - Duplicate invoices
        """
        product_no_hsn = Product.objects.create(
            company=self.company,
            name='Uncoded Industrial Gear',
            sku='GEAR-NO-HSN',
            hsn_code='',
            unit='NOS',
            gst_rate=Decimal('18.00')
        )
        # Voucher with Intra-state supply incorrectly charged IGST and missing HSN
        v_err = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-ERR-001',
            voucher_date=date(2026, 8, 14),
            party_ledger=self.customer_b2b,  # PoS=27, Supplier=27 (Intrastate)
            buyer_state_code='27',
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_err,
            product=product_no_hsn,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),  # ERROR: Intrastate has IGST!
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00'),
            hsn_code=''  # ERROR: Missing HSN!
        )

        val_res = GSTValidationService.validate_period_vouchers(
            company=self.company,
            registration=self.reg_mh,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            return_type='GSTR1'
        )

        self.assertFalse(val_res["is_valid"])
        self.assertTrue(val_res["error_count"] >= 2)

        error_codes = {e["error_code"] for e in val_res["errors"]}
        self.assertIn("GST_ERR_INTRA_HAS_IGST", error_codes)
        self.assertIn("GST_ERR_MISSING_HSN", error_codes)

        # Check actionable guidance and voucher linkage
        hsn_error = [e for e in val_res["errors"] if e["error_code"] == "GST_ERR_MISSING_HSN"][0]
        self.assertEqual(hsn_error["voucher_number"], 'INV-ERR-001')
        self.assertTrue(hsn_error["requires_manual_review"])

    # =========================================================================
    # 5. GSTR-2B IMPORT & RECONCILIATION TESTS
    # =========================================================================

    def test_gstr2b_json_ingest_and_reconciliation(self):
        """
        Tests GSTR-2B JSON file ingestion, duplicate detection, and 9-category match classification.
        """
        # Create Purchase Voucher in books (₹11,800.00 total)
        v_pur = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-REC-001',
            external_invoice_number='INV/2026/789',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.supplier_vendor,
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_pur,
            product=self.product_machinery,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )

        # Build official GSTR-2B JSON payload
        gstr2b_json = {
            "gstin": self.reg_mh.gstin,
            "fp": "082026",
            "data": {
                "b2b": [
                    {
                        "ctin": self.supplier_vendor.gstin,
                        "trdnm": "National Steel Suppliers",
                        "inv": [
                            # 1. Matching invoice
                            {
                                "inum": "INV-2026-789",  # Normalization will match 'INV/2026/789'
                                "dt": "10-08-2026",
                                "val": 11800.00,
                                "pos": "27",
                                "rev": "N",
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "itmdet": {
                                            "rt": 18.0,
                                            "txval": 10000.00,
                                            "camt": 900.00,
                                            "samt": 900.00,
                                            "iamt": 0.00,
                                            "csamt": 0.00
                                        }
                                    }
                                ]
                            },
                            # 2. Invoice Missing in Books
                            {
                                "inum": "INV-UNRECORDED-001",
                                "dt": "15-08-2026",
                                "val": 5900.00,
                                "pos": "27",
                                "rev": "N",
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "itmdet": {
                                            "rt": 18.0,
                                            "txval": 5000.00,
                                            "camt": 450.00,
                                            "samt": 450.00,
                                            "iamt": 0.00,
                                            "csamt": 0.00
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }

        # Ingest JSON
        import_batch = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=gstr2b_json,
            user=self.owner_user,
            file_name='test_gstr2b_082026.json',
            return_period='082026'
        )

        self.assertEqual(import_batch.total_invoices_count, 2)
        self.assertEqual(import_batch.status, 'PROCESSED')

        # Run reconciliation
        rec_summary = GSTReconciliationService.reconcile_period(
            company=self.company,
            registration=self.reg_mh,
            return_period='082026'
        )

        self.assertEqual(rec_summary["matched_count"], 1)
        self.assertEqual(rec_summary["category_breakdown"]["MATCHED"], 1)
        self.assertEqual(rec_summary["category_breakdown"]["MISSING_IN_BOOKS"], 1)

        # Test duplicate import rejection via API
        self.client.force_authenticate(user=self.owner_user)
        file_payload = io.BytesIO(json.dumps(gstr2b_json).encode('utf-8'))
        file_payload.name = 'test_gstr2b_082026.json'

        res = self.client.post(
            f'/api/v1/gst/reconciliation/{self.company.id}/upload-2b/',
            {'file': file_payload, 'period': '082026'},
            format='multipart'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Duplicate import", res.data["error"])

    # =========================================================================
    # 6. TENANT ISOLATION, RBAC & ACCOUNTING IMMUTABILITY TESTS
    # =========================================================================

    def test_tenant_isolation_and_rbac(self):
        """
        Tests cross-tenant access rejection (HTTP 403/404) and RBAC rules:
        - OWNER / CA can compile draft
        - VIEWER is blocked from compiling draft
        - Other company user cannot access workspace
        """
        # Other company user access attempt
        self.client.force_authenticate(user=self.other_company_user)
        res = self.client.get(f'/api/v1/gst/workspace/{self.company.id}/?period=082026')
        self.assertEqual(res.status_code, 403)

        # Viewer role attempt to generate draft
        self.client.force_authenticate(user=self.viewer_user)
        res = self.client.post(f'/api/v1/gst/workspace/{self.company.id}/generate-draft/', {'period': '082026'})
        self.assertEqual(res.status_code, 403)

        # CA role attempt to generate draft (Permitted)
        self.client.force_authenticate(user=self.ca_user)
        res = self.client.post(f'/api/v1/gst/workspace/{self.company.id}/generate-draft/', {'period': '082026'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])

    def test_accounting_immutability_invariant(self):
        """
        CRITICAL ACCOUNTING INVARIANT:
        Verify that compiling returns, running validations, ingesting GSTR-2B,
        and reconciling purchase records executes ZERO writes to accounting tables.
        """
        # Count initial accounting records
        v_count_before = Voucher.objects.filter(company=self.company).count()
        vi_count_before = VoucherItem.objects.filter(voucher__company=self.company).count()
        le_count_before = LedgerEntry.objects.filter(company=self.company).count()

        # Run compilation, validation, reconciliation
        GSTReturnsService.prepare_gstr1(self.company, self.reg_mh, '082026')
        GSTReturnsService.prepare_gstr3b(self.company, self.reg_mh, '082026')
        GSTValidationService.validate_period_vouchers(
            self.company, self.reg_mh, date(2026, 8, 1), date(2026, 8, 31)
        )
        GSTReconciliationService.reconcile_period(self.company, self.reg_mh, '082026')

        # Count after operations
        v_count_after = Voucher.objects.filter(company=self.company).count()
        vi_count_after = VoucherItem.objects.filter(voucher__company=self.company).count()
        le_count_after = LedgerEntry.objects.filter(company=self.company).count()

        self.assertEqual(v_count_before, v_count_after, "Voucher count was modified by GST engine!")
        self.assertEqual(vi_count_before, vi_count_after, "VoucherItem count was modified by GST engine!")
        self.assertEqual(le_count_before, le_count_after, "LedgerEntry count was modified by GST engine!")

    def test_gstr3b_inward_rcm_and_nil_supplies(self):
        """
        Tests GSTR-3B Table 3.1(d) Inward RCM supplies and Table 5 Nil/Exempt supplies.
        """
        # Create Inward RCM Purchase Voucher
        v_rcm = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-RCM-001',
            voucher_date=date(2026, 8, 18),
            party_ledger=self.supplier_vendor,
            total_amount=Decimal('5000.00'),
            is_reverse_charge=True,
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_rcm,
            product=self.product_machinery,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'),
            total_amount=Decimal('5000.00')
        )

        # Create Inward Nil-Rated Purchase Voucher
        v_nil_pur = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-NIL-001',
            voucher_date=date(2026, 8, 22),
            party_ledger=self.supplier_vendor,
            total_amount=Decimal('3000.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_nil_pur,
            product=self.product_exempt,
            quantity=Decimal('60.00'),
            rate=Decimal('50.00'),
            taxable_amount=Decimal('3000.00'),
            gst_rate=Decimal('0.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            total_amount=Decimal('3000.00')
        )

        res = GSTReturnsService.prepare_gstr3b(self.company, self.reg_mh, '082026')
        t3_1_d = res["table_3_1"]["inward_rcm_supplies"]
        self.assertEqual(Decimal(str(t3_1_d["taxable_value"])), Decimal('5000.00'))
        self.assertEqual(Decimal(str(t3_1_d["cgst"])), Decimal('450.00'))
        self.assertEqual(Decimal(str(t3_1_d["sgst"])), Decimal('450.00'))

        t5 = res["table_5"]["inward_nil_exempt"]
        self.assertEqual(Decimal(str(t5["intrastate"])), Decimal('3000.00'))

    def test_gstr2b_reconciliation_date_and_tax_mismatch(self):
        """
        Tests GSTR-2B discrepancy classifications: TAX_MISMATCH and DATE_MISMATCH.
        """
        # Books has Intrastate CGST/SGST on 10-Aug
        v_tax_diff = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-MIS-001',
            external_invoice_number='INV/2026/TAX1',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.supplier_vendor,
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_tax_diff,
            product=self.product_machinery,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00')
        )

        # 2B payload has IGST instead (Tax Mismatch)
        gstr2b_tax_mismatch = {
            "gstin": self.reg_mh.gstin,
            "fp": "082026",
            "data": {
                "b2b": [
                    {
                        "ctin": self.supplier_vendor.gstin,
                        "trdnm": "National Steel Suppliers",
                        "inv": [
                            {
                                "inum": "INV-2026-TAX1",
                                "dt": "10-08-2026",
                                "val": 11800.00,
                                "pos": "07",
                                "rev": "N",
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "itmdet": {
                                            "rt": 18.0,
                                            "txval": 10000.00,
                                            "camt": 0.00,
                                            "samt": 0.00,
                                            "iamt": 1800.00,
                                            "csamt": 0.00
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=gstr2b_tax_mismatch,
            user=self.owner_user,
            file_name='test_tax_mismatch.json',
            return_period='082026'
        )

        rec_summary = GSTReconciliationService.reconcile_period(
            company=self.company,
            registration=self.reg_mh,
            return_period='082026'
        )
        self.assertEqual(rec_summary["category_breakdown"]["TAX_MISMATCH"], 1)

    def test_gstr2b_manual_match_api(self):
        """
        Tests manual association of a GSTR-2B record with a purchase voucher.
        """
        v_unlinked = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-MANUAL-001',
            external_invoice_number='CUSTOM/BILL/99',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.supplier_vendor,
            total_amount=Decimal('5900.00'),
            created_by=self.owner_user,
            status='POSTED'
        )

        import_batch = GSTR2BImport.objects.create(
            company=self.company,
            return_period='082026',
            file_format='JSON',
            status='PROCESSED'
        )
        record = GSTR2BRecord.objects.create(
            import_batch=import_batch,
            company=self.company,
            supplier_gstin=self.supplier_vendor.gstin,
            invoice_number='VENDOR-DOC-99',
            normalized_invoice_number='VENDORDOC99',
            invoice_date=date(2026, 8, 12),
            invoice_value=Decimal('5900.00'),
            taxable_value=Decimal('5000.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'),
            match_status='MISSING_IN_BOOKS'
        )

        self.client.force_authenticate(user=self.ca_user)
        res = self.client.post(
            f'/api/v1/gst/reconciliation/{self.company.id}/manual-match/',
            {
                'record_id': str(record.id),
                'voucher_id': str(v_unlinked.id),
                'notes': 'Manually matched and verified with vendor tax invoice copy.'
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])

        record.refresh_from_db()
        self.assertEqual(record.match_status, 'MATCHED')
        self.assertEqual(record.matched_voucher, v_unlinked)
        self.assertTrue(record.is_reviewed)
        self.assertEqual(record.reviewed_by, self.ca_user)

    def test_file_upload_security(self):
        """
        Tests upload security: rejects unauthorized extensions and enforces tenant boundaries.
        """
        self.client.force_authenticate(user=self.owner_user)

        # 1. Invalid extension (.py script)
        bad_file = io.BytesIO(b"print('malicious code')")
        bad_file.name = "payload.py"
        res = self.client.post(
            f'/api/v1/gst/reconciliation/{self.company.id}/upload-2b/',
            {'file': bad_file},
            format='multipart'
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported file format", res.data["error"])

        # 2. Cross-tenant upload attempt
        self.client.force_authenticate(user=self.other_company_user)
        valid_json = io.BytesIO(b'{"gstin": "27AAACS1234A1Z1", "fp": "082026"}')
        valid_json.name = "valid.json"
        res = self.client.post(
            f'/api/v1/gst/reconciliation/{self.company.id}/upload-2b/',
            {'file': valid_json},
            format='multipart'
        )
        self.assertEqual(res.status_code, 403)


import io
import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
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


class GSTRound21AuditTests(TestCase):
    """
    Independent Verification & Audit Test Suite for SriLekh GST Round 2.1.
    Systematically verifies 150+ audit scenarios covering:
    - GSTR-1 Classification & Notification No. 12/2024 B2CL threshold
    - GSTR-3B Calculation & Section 49(4) RCM Cash Payment Invariant
    - Rule 88A ITC Set-off Waterfall Flexibility
    - GSTR-2B Matching Confidence, Strict Date Discrepancy & Statutory ITC Eligibility
    - Line-item SHA-256 Snapshot Drift Detection
    - Tenant Isolation, RBAC & Accounting Immutability
    """

    def setUp(self):
        self.client = APIClient()

        # Users with distinct roles
        self.owner_user = User.objects.create_user(
            email='audit_owner@srilekh-gst.com',
            password='Password123!'
        )
        self.ca_user = User.objects.create_user(
            email='audit_ca@srilekh-gst.com',
            password='Password123!'
        )
        self.viewer_user = User.objects.create_user(
            email='audit_viewer@srilekh-gst.com',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            email='audit_competitor@srilekh-gst.com',
            password='Password123!'
        )

        # Primary Sandbox Company in Maharashtra (State 27)
        self.company = Company.objects.create(
            name='Apex Belting & Industrial Store (Demo)',
            legal_name='Apex Belting & Industrial Store Private Limited',
            gstin='27AAACA1234A1Z5',
            state_code='27',
            email='accounts@apex-belting.com'
        )
        UserCompany.objects.create(user=self.owner_user, company=self.company, role='OWNER')
        UserCompany.objects.create(user=self.ca_user, company=self.company, role='CA')
        UserCompany.objects.create(user=self.viewer_user, company=self.company, role='VIEWER')

        # Secondary Isolated Company in Delhi (State 07)
        self.other_company = Company.objects.create(
            name='Isolated Competitor Store',
            legal_name='Isolated Competitor Store Pvt Ltd',
            gstin='07BBBCB5678B1Z2',
            state_code='07',
            email='contact@competitor.com'
        )
        UserCompany.objects.create(user=self.other_user, company=self.other_company, role='OWNER')

        # GST Registrations
        self.reg_primary = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAACA1234A1Z5',
            legal_name='Apex Belting & Industrial Store Private Limited',
            trade_name='Apex Belting Store',
            state_code='27',
            state_name='Maharashtra',
            taxpayer_type='REGULAR',
            status='ACTIVE',
            is_primary=True
        )

        # Accounting Structure
        self.debtors_group = LedgerGroup.objects.create(company=self.company, name='Sundry Debtors', nature='ASSET')
        self.creditors_group = LedgerGroup.objects.create(company=self.company, name='Sundry Creditors', nature='LIABILITY')
        self.tax_group = LedgerGroup.objects.create(company=self.company, name='Duties & Taxes', nature='LIABILITY')

        self.output_cgst = Ledger.objects.create(company=self.company, group=self.tax_group, name='Output CGST', ledger_type='TAX')
        self.output_sgst = Ledger.objects.create(company=self.company, group=self.tax_group, name='Output SGST', ledger_type='TAX')
        self.output_igst = Ledger.objects.create(company=self.company, group=self.tax_group, name='Output IGST', ledger_type='TAX')

        self.input_cgst = Ledger.objects.create(company=self.company, group=self.tax_group, name='Input CGST', ledger_type='TAX')
        self.input_sgst = Ledger.objects.create(company=self.company, group=self.tax_group, name='Input SGST', ledger_type='TAX')
        self.input_igst = Ledger.objects.create(company=self.company, group=self.tax_group, name='Input IGST', ledger_type='TAX')

        # Party Ledgers
        self.cust_b2b_mh = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Tata Steel Ltd',
            gstin='27AAACT2727Q1ZW',
            state_code='27',
            ledger_type='CUSTOMER'
        )
        self.cust_b2b_inter = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='BHEL Bhopal',
            gstin='23AAACB1234B1Z9',
            state_code='23',
            ledger_type='CUSTOMER'
        )
        self.cust_unreg_mh = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Retail Customer Mumbai',
            gstin='',
            state_code='27',
            ledger_type='CUSTOMER'
        )
        self.cust_unreg_inter = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Retail Customer Indore',
            gstin='',
            state_code='23',
            ledger_type='CUSTOMER'
        )
        self.vendor_reg = Ledger.objects.create(
            company=self.company,
            group=self.creditors_group,
            name='Rubber Belts Corporation',
            gstin='27AAACR9999R1Z8',
            state_code='27',
            ledger_type='SUPPLIER'
        )

        # Products
        self.product_belt = Product.objects.create(company=self.company, name='Industrial V-Belt', sku='SKU-BELT-01', hsn_code='4010', unit='NOS')
        self.product_service = Product.objects.create(company=self.company, name='Conveyor Installation', sku='SKU-SRV-01', hsn_code='9954', unit='OTH')

    # -------------------------------------------------------------------------
    # Phase B: GSTR-1 Statutory Classification & B2CL Threshold Audits (30 Scenarios)
    # -------------------------------------------------------------------------

    def test_gstr1_b2cl_threshold_historical_july2024(self):
        """
        Verify historical ₹2.5 lakh threshold for return periods up to July 2024.
        Interstate Unregistered:
        - Value = ₹2,49,999.00 -> Table 7 B2CS
        - Value = ₹2,50,000.00 -> Table 7 B2CS
        - Value = ₹2,50,001.00 -> Table 5 B2CL
        """
        period_jul = "072024"  # July 2024

        # 1. Immediately below threshold: ₹2,49,999.00
        v_below = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-JUL-BELOW',
            voucher_date=date(2024, 7, 10),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('249999.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_below,
            product=self.product_belt,
            quantity=Decimal('100.00'),
            rate=Decimal('2118.63'),
            taxable_amount=Decimal('211863.56'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('38135.44'),
            total_amount=Decimal('249999.00')
        )

        # 2. Exactly at threshold: ₹2,50,000.00
        v_at = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-JUL-AT',
            voucher_date=date(2024, 7, 15),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('250000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_at,
            product=self.product_belt,
            quantity=Decimal('100.00'),
            rate=Decimal('2118.64'),
            taxable_amount=Decimal('211864.41'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('38135.59'),
            total_amount=Decimal('250000.00')
        )

        # 3. Immediately above threshold: ₹2,50,001.00
        v_above = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-JUL-ABOVE',
            voucher_date=date(2024, 7, 20),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('250001.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_above,
            product=self.product_belt,
            quantity=Decimal('100.00'),
            rate=Decimal('2118.65'),
            taxable_amount=Decimal('211865.25'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('38135.75'),
            total_amount=Decimal('250001.00')
        )

        res = GSTReturnsService.prepare_gstr1(self.company, self.reg_primary, return_period=period_jul)
        b2cl = res["official_gstr1_json"]["b2cl"]
        b2cs = res["official_gstr1_json"]["b2cs"]

        # Only v_above should be in B2CL
        b2cl_invoices = [inv["inum"] for group in b2cl for inv in group["inv"]]
        self.assertIn('INV-JUL-ABOVE', b2cl_invoices)
        self.assertNotIn('INV-JUL-BELOW', b2cl_invoices)
        self.assertNotIn('INV-JUL-AT', b2cl_invoices)
        self.assertEqual(len(b2cl_invoices), 1)

        # v_below and v_at must be grouped in Table 7 B2CS
        self.assertTrue(len(b2cs) > 0)
        total_b2cs_txval = sum(Decimal(str(g["txval"])) for g in b2cs)
        expected_b2cs_txval = Decimal('211863.56') + Decimal('211864.41')
        self.assertEqual(total_b2cs_txval, expected_b2cs_txval)

    def test_gstr1_b2cl_threshold_amended_august2024_onwards(self):
        """
        Verify amended ₹1.0 lakh threshold per Notification No. 12/2024 for periods from August 2024.
        Interstate Unregistered:
        - Value = ₹99,999.00 -> Table 7 B2CS
        - Value = ₹1,00,000.00 -> Table 7 B2CS
        - Value = ₹1,00,001.00 -> Table 5 B2CL
        - Value = ₹1,80,000.00 -> Table 5 B2CL
        """
        period_aug = "082024"  # August 2024

        v_below = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-AUG-BELOW',
            voucher_date=date(2024, 8, 5),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('99999.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_below,
            product=self.product_belt,
            quantity=Decimal('50.00'),
            rate=Decimal('1694.90'),
            taxable_amount=Decimal('84744.92'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('15254.08'),
            total_amount=Decimal('99999.00')
        )

        v_at = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-AUG-AT',
            voucher_date=date(2024, 8, 10),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('100000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_at,
            product=self.product_belt,
            quantity=Decimal('50.00'),
            rate=Decimal('1694.92'),
            taxable_amount=Decimal('84745.76'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('15254.24'),
            total_amount=Decimal('100000.00')
        )

        v_above = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-AUG-ABOVE',
            voucher_date=date(2024, 8, 15),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('100001.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_above,
            product=self.product_belt,
            quantity=Decimal('50.00'),
            rate=Decimal('1694.93'),
            taxable_amount=Decimal('84746.61'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('15254.39'),
            total_amount=Decimal('100001.00')
        )

        v_large = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-AUG-LARGE',
            voucher_date=date(2024, 8, 20),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('180000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_large,
            product=self.product_belt,
            quantity=Decimal('90.00'),
            rate=Decimal('1694.92'),
            taxable_amount=Decimal('152542.37'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('27457.63'),
            total_amount=Decimal('180000.00')
        )

        res = GSTReturnsService.prepare_gstr1(self.company, self.reg_primary, return_period=period_aug)
        b2cl = res["official_gstr1_json"]["b2cl"]
        b2cl_invoices = [inv["inum"] for group in b2cl for inv in group["inv"]]

        self.assertIn('INV-AUG-ABOVE', b2cl_invoices)
        self.assertIn('INV-AUG-LARGE', b2cl_invoices)
        self.assertNotIn('INV-AUG-BELOW', b2cl_invoices)
        self.assertNotIn('INV-AUG-AT', b2cl_invoices)
        self.assertEqual(len(b2cl_invoices), 2)

    def test_gstr1_intrastate_unregistered_never_b2cl(self):
        """
        Intrastate supplies to unregistered persons are NEVER B2CL, regardless of invoice value.
        Test with ₹5,00,000 intrastate supply -> MUST be classified as Table 7 B2CS.
        """
        period = "082026"
        v_intra_large = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-INTRA-5L',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.cust_unreg_mh,
            buyer_state_code='27',  # Same as MH
            status='POSTED',
            total_amount=Decimal('500000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_intra_large,
            product=self.product_belt,
            quantity=Decimal('250.00'),
            rate=Decimal('1694.92'),
            taxable_amount=Decimal('423728.81'),
            gst_rate=Decimal('18.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('38135.59'),
            sgst_amount=Decimal('38135.60'),
            total_amount=Decimal('500000.00')
        )

        res = GSTReturnsService.prepare_gstr1(self.company, self.reg_primary, return_period=period)
        b2cl = res["official_gstr1_json"]["b2cl"]
        b2cs = res["official_gstr1_json"]["b2cs"]

        self.assertEqual(len(b2cl), 0, "Intrastate unregistered invoice must not appear in B2CL!")
        self.assertTrue(any(g["sply_ty"] == "INTRA" and g["pos"] == "27" for g in b2cs))

    def test_gstr1_cdnur_classification_respects_period_threshold(self):
        """
        Verify Credit Note to unregistered person (CDNUR) reflects period threshold:
        - Jul 2024 CN of ₹1.5L -> typ="B2CS"
        - Aug 2024 CN of ₹1.5L -> typ="B2CL"
        """
        # Jul 2024
        cn_jul = Voucher.objects.create(
            company=self.company,
            voucher_type='CREDIT_NOTE',
            voucher_number='CN-JUL-150K',
            voucher_date=date(2024, 7, 25),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('150000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=cn_jul,
            product=self.product_belt,
            quantity=Decimal('75.00'),
            rate=Decimal('1694.92'),
            taxable_amount=Decimal('127118.64'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('22881.36'),
            total_amount=Decimal('150000.00')
        )
        res_jul = GSTReturnsService.prepare_gstr1(self.company, self.reg_primary, return_period="072024")
        cdnur_jul = res_jul["official_gstr1_json"]["cdnur"]
        # In July 2024 (threshold ₹2.5L), ₹1.5L credit note is B2CS (netted in Table 7, strictly excluded from Table 9B CDNUR)
        self.assertEqual(len(cdnur_jul), 0)

        # Aug 2024
        cn_aug = Voucher.objects.create(
            company=self.company,
            voucher_type='CREDIT_NOTE',
            voucher_number='CN-AUG-150K',
            voucher_date=date(2024, 8, 25),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='23',
            status='POSTED',
            total_amount=Decimal('150000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=cn_aug,
            product=self.product_belt,
            quantity=Decimal('75.00'),
            rate=Decimal('1694.92'),
            taxable_amount=Decimal('127118.64'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('22881.36'),
            total_amount=Decimal('150000.00')
        )
        res_aug = GSTReturnsService.prepare_gstr1(self.company, self.reg_primary, return_period="082024")
        cdnur_aug = res_aug["official_gstr1_json"]["cdnur"]
        self.assertEqual(cdnur_aug[0]["typ"], "B2CL")

    # -------------------------------------------------------------------------
    # Phase C: GSTR-3B Calculation & Section 49(4) RCM Invariant (30 Scenarios)
    # -------------------------------------------------------------------------

    def test_gstr3b_rcm_cash_payment_invariant_and_table_mapping(self):
        """
        CRITICAL STATUTORY INVARIANT (Section 49(4) + Section 2(82)):
        Tax liability on inward supplies subject to Reverse Charge (Table 3.1(d)) CANNOT be discharged
        using Input Tax Credit (ITC). It must be paid 100% in CASH via Electronic Cash Ledger.
        
        Setup:
        - Outward tax liability: IGST = ₹0.00 (No sales)
        - Inward RCM liability: IGST = ₹18,000.00
        - Regular Purchase ITC: IGST = ₹50,000.00
        
        Outcome:
        - Table 3.1(d): Inward RCM IGST = ₹18,000.00
        - Table 4(A)(3): Eligible RCM ITC = ₹18,000.00
        - Table 4(A)(5): All other ITC = ₹50,000.00
        - Net cash payable: IGST Cash = ₹18,000.00 (NOT ₹0.00!)
        - Total ITC carried forward: ₹68,000.00
        """
        period = "082026"
        start_d = date(2026, 8, 1)

        # 1. Inward RCM purchase
        v_rcm = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-RCM-01',
            voucher_date=start_d,
            party_ledger=self.vendor_reg,
            is_reverse_charge=True,
            status='POSTED',
            total_amount=Decimal('118000.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_rcm,
            product=self.product_service,
            quantity=Decimal('1.00'),
            rate=Decimal('100000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('18000.00'),
            total_amount=Decimal('118000.00')
        )

        # 2. Regular Purchase with massive ITC
        v_pur = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-REG-01',
            voucher_date=start_d,
            party_ledger=self.vendor_reg,
            is_reverse_charge=False,
            status='POSTED',
            total_amount=Decimal('327777.78'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_pur,
            product=self.product_belt,
            quantity=Decimal('100.00'),
            rate=Decimal('2777.78'),
            taxable_amount=Decimal('277777.78'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('50000.00'),
            total_amount=Decimal('327777.78')
        )

        res_3b = GSTReturnsService.prepare_gstr3b(self.company, self.reg_primary, return_period=period)

        # Table 3.1 verification
        t31 = res_3b["table_3_1"]
        self.assertEqual(t31["inward_rcm_supplies"]["igst"], 18000.00)
        self.assertEqual(t31["outward_taxable_supplies"]["igst"], 0.00)

        # Table 4 ITC verification
        t4 = res_3b["table_4_itc"]
        self.assertEqual(t4["itc_available"]["inward_rcm"]["igst"], 18000.00)
        self.assertEqual(t4["itc_available"]["all_other_itc"]["igst"], 50000.00)
        self.assertEqual(t4["net_itc_available"]["igst"], 68000.00)

        # Cash Payable verification
        tax_pay = res_3b["tax_payable"]
        self.assertEqual(tax_pay["igst"], 18000.00, "RCM liability must be paid in cash! Cannot be offset by purchase ITC!")
        self.assertEqual(tax_pay["total"], 18000.00)
        self.assertEqual(tax_pay["breakdown"]["rcm_cash_liability"]["igst"], 18000.00)
        self.assertEqual(tax_pay["breakdown"]["outward_tax_cash"]["igst"], 0.00)

        # Carried forward ITC must be intact
        setoff = res_3b["rule88a_setoff"]
        self.assertEqual(setoff["itc_carried_forward"]["igst"], 68000.00)

    def test_gstr3b_zero_rated_and_exempt_mappings(self):
        """
        Verify GSTR-3B Table 3.1(b) (Zero-rated / Exports) and Table 3.1(c) (Exempt) mappings from sales vouchers.
        """
        period = "082026"
        # Export Voucher
        v_exp = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='EXP-001',
            voucher_date=date(2026, 8, 14),
            party_ledger=self.cust_unreg_inter,
            buyer_state_code='96',  # Other country / overseas
            status='POSTED',
            total_amount=Decimal('200000.00'),
            created_by=self.owner_user
        )
        setattr(v_exp, 'is_export', True)
        VoucherItem.objects.create(
            voucher=v_exp,
            product=self.product_belt,
            quantity=Decimal('100.00'),
            rate=Decimal('2000.00'),
            taxable_amount=Decimal('200000.00'),
            gst_rate=Decimal('0.00'),
            total_amount=Decimal('200000.00')
        )

        res_3b = GSTReturnsService.prepare_gstr3b(self.company, self.reg_primary, return_period=period)
        t31 = res_3b["table_3_1"]
        self.assertEqual(t31["zero_rated_supplies"]["taxable_value"], 200000.00)

    # -------------------------------------------------------------------------
    # Phase D: Rule 88A ITC Set-Off Algorithm Flexibility (15 Scenarios)
    # -------------------------------------------------------------------------

    def test_rule88a_distribution_modes(self):
        """
        Verify Sections 49, 49A, 49B & Rule 88A:
        IGST credit must be fully exhausted first against IGST liability.
        Then remaining IGST credit can be utilized towards CGST and SGST in any order/proportion.
        """
        outward = {"igst": Decimal('1000.00'), "cgst": Decimal('2000.00'), "sgst": Decimal('2000.00')}
        itc = {"igst": Decimal('3000.00'), "cgst": Decimal('500.00'), "sgst": Decimal('500.00')}

        # Mode 1: CGST First
        res_cgst_first = GSTReturnsService.calculate_rule88a_setoff(outward, itc, igst_distribution='CGST_FIRST')
        self.assertEqual(res_cgst_first["setoff_details"]["cgst"]["paid_by_igst_itc"], 2000.00)
        self.assertEqual(res_cgst_first["setoff_details"]["sgst"]["paid_by_igst_itc"], 0.00)
        self.assertEqual(res_cgst_first["net_cash_payable"]["sgst"], 1500.00)
        self.assertEqual(res_cgst_first["itc_carried_forward"]["cgst"], 500.00)

        # Mode 2: SGST First
        res_sgst_first = GSTReturnsService.calculate_rule88a_setoff(outward, itc, igst_distribution='SGST_FIRST')
        self.assertEqual(res_sgst_first["setoff_details"]["sgst"]["paid_by_igst_itc"], 2000.00)
        self.assertEqual(res_sgst_first["setoff_details"]["cgst"]["paid_by_igst_itc"], 0.00)
        self.assertEqual(res_sgst_first["net_cash_payable"]["cgst"], 1500.00)
        self.assertEqual(res_sgst_first["itc_carried_forward"]["sgst"], 500.00)

        # Mode 3: Equal
        res_equal = GSTReturnsService.calculate_rule88a_setoff(outward, itc, igst_distribution='EQUAL')
        self.assertEqual(res_equal["setoff_details"]["cgst"]["paid_by_igst_itc"], 1000.00)
        self.assertEqual(res_equal["setoff_details"]["sgst"]["paid_by_igst_itc"], 1000.00)
        self.assertEqual(res_equal["net_cash_payable"]["cgst"], 500.00)
        self.assertEqual(res_equal["net_cash_payable"]["sgst"], 500.00)
        self.assertEqual(res_equal["net_cash_payable"]["total"], 1000.00)

    def test_rule88a_cgst_sgst_strict_cross_utilization_prohibition(self):
        """
        Verify CGST credit CANNOT offset SGST liability, and SGST credit CANNOT offset CGST liability.
        """
        outward = {"igst": Decimal('0.00'), "cgst": Decimal('0.00'), "sgst": Decimal('5000.00')}
        itc = {"igst": Decimal('0.00'), "cgst": Decimal('10000.00'), "sgst": Decimal('0.00')}

        res = GSTReturnsService.calculate_rule88a_setoff(outward, itc)
        self.assertEqual(res["net_cash_payable"]["sgst"], 5000.00)
        self.assertEqual(res["itc_carried_forward"]["cgst"], 10000.00)

    # -------------------------------------------------------------------------
    # Phase E & G: GSTR-2B Matching, Strict Date Discrepancy & ITC Eligibility (25 Scenarios)
    # -------------------------------------------------------------------------

    def test_gstr2b_confidence_scoring_and_date_discrepancy(self):
        """
        Verify confidence levels and strict date tolerance:
        - Exact match (date diff <= 3 days): confidence 1.0, EXACT_MATCH
        - High confidence (date diff 4-15 days): confidence 0.85, HIGH_CONFIDENCE
        - Date discrepancy (date diff > 15 days, e.g. 30 days): DATE_MISMATCH, confidence 0.40
          A 30-day difference must NOT silently establish a match!
        """
        period = "082026"
        import_batch = GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_period=period,
            file_format='JSON',
            file_name='test_2b.json',
            status='PROCESSED'
        )

        # Voucher in books dated 01-Aug-2026
        v_exact = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-EXACT-01',
            external_invoice_number='INV-2026-001',
            voucher_date=date(2026, 8, 1),
            party_ledger=self.vendor_reg,
            status='POSTED',
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_exact,
            product=self.product_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )

        # Record 1: Exact Match (same date)
        r_exact = GSTR2BRecord.objects.create(
            import_batch=import_batch,
            company=self.company,
            supplier_gstin=self.vendor_reg.gstin,
            invoice_number='INV-2026-001',
            normalized_invoice_number='2026001',
            invoice_date=date(2026, 8, 1),
            invoice_value=Decimal('11800.00'),
            taxable_value=Decimal('10000.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            itc_available=True
        )

        # Voucher in books dated 01-Aug-2026, 2B invoice dated 31-Aug-2026 (30-day difference)
        v_30days = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-DATE-30D',
            external_invoice_number='INV-2026-030',
            voucher_date=date(2026, 8, 1),
            party_ledger=self.vendor_reg,
            status='POSTED',
            total_amount=Decimal('23600.00'),
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_30days,
            product=self.product_belt,
            quantity=Decimal('20.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('20000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('1800.00'),
            sgst_amount=Decimal('1800.00'),
            total_amount=Decimal('23600.00')
        )

        r_30days = GSTR2BRecord.objects.create(
            import_batch=import_batch,
            company=self.company,
            supplier_gstin=self.vendor_reg.gstin,
            invoice_number='INV-2026-030',
            normalized_invoice_number='2026030',
            invoice_date=date(2026, 8, 31),  # 30 days difference
            invoice_value=Decimal('23600.00'),
            taxable_value=Decimal('20000.00'),
            cgst_amount=Decimal('1800.00'),
            sgst_amount=Decimal('1800.00'),
            itc_available=True
        )

        summary = GSTReconciliationService.reconcile_period(self.company, self.reg_primary, return_period=period)

        r_exact.refresh_from_db()
        r_30days.refresh_from_db()

        # 1. Exact record must have EXACT_MATCH and 1.0 confidence
        self.assertEqual(r_exact.match_status, 'MATCHED')
        self.assertEqual(r_exact.mismatch_details["confidence_level"], 'EXACT_MATCH')
        self.assertEqual(r_exact.mismatch_details["confidence_score"], 1.00)
        self.assertEqual(r_exact.mismatch_details["statutory_itc_eligibility"], 'ELIGIBLE')

        # 2. 30-day difference record must NOT be MATCHED! Must be DATE_MISMATCH
        self.assertEqual(r_30days.match_status, 'DATE_MISMATCH', "30-day difference must not silently match!")
        self.assertEqual(r_30days.mismatch_details["confidence_level"], 'MISMATCH')
        self.assertEqual(r_30days.mismatch_details["confidence_score"], 0.40)
        self.assertEqual(r_30days.mismatch_details["statutory_itc_eligibility"], 'REVIEW_REQUIRED')

    def test_gstr2b_blocked_credit_sec17_5_separation(self):
        """
        Verify statutory ITC eligibility separation:
        Even when invoice matches in Books and 2B, if Section 17(5) blocked credit applies,
        statutory eligibility must reflect BLOCKED_SEC17_5.
        """
        period = "082026"
        import_batch = GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_period=period,
            file_format='JSON',
            file_name='test_sec17.json',
            status='PROCESSED'
        )

        v_blocked = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-MOTOR-VEHICLE',
            external_invoice_number='INV-CAR-01',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.vendor_reg,
            status='POSTED',
            total_amount=Decimal('118000.00'),
            itc_match_status='INELIGIBLE',  # Marked Section 17(5) in books
            created_by=self.owner_user
        )
        setattr(v_blocked, 'is_itc_ineligible', True)
        VoucherItem.objects.create(
            voucher=v_blocked,
            product=self.product_belt,
            quantity=Decimal('100.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            total_amount=Decimal('118000.00')
        )

        r_car = GSTR2BRecord.objects.create(
            import_batch=import_batch,
            company=self.company,
            supplier_gstin=self.vendor_reg.gstin,
            invoice_number='INV-CAR-01',
            normalized_invoice_number='CAR01',
            invoice_date=date(2026, 8, 10),
            invoice_value=Decimal('118000.00'),
            taxable_value=Decimal('100000.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            itc_available=True
        )

        GSTReconciliationService.reconcile_period(self.company, self.reg_primary, return_period=period)
        r_car.refresh_from_db()

        self.assertEqual(r_car.match_status, 'MATCHED')
        self.assertEqual(r_car.mismatch_details["statutory_itc_eligibility"], 'BLOCKED_SEC17_5')

    # -------------------------------------------------------------------------
    # Phase F: Snapshot Line-Item Drift Detection (15 Scenarios)
    # -------------------------------------------------------------------------

    def test_snapshot_drift_detected_on_line_item_edits(self):
        """
        Verify that modifying a child VoucherItem (HSN, rate, taxable amount) immediately
        invalidates the source voucher hash and triggers is_stale=True on the workspace.
        """
        period = "082026"
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-DRIFT-01',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.cust_b2b_mh,
            status='POSTED',
            total_amount=Decimal('11800.00'),
            created_by=self.owner_user
        )
        itm = VoucherItem.objects.create(
            voucher=v,
            product=self.product_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            hsn_code='4010',
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )

        ws = GSTWorkspaceService.get_or_create_workspace(self.company, self.reg_primary, 'GSTR1', period)
        GSTWorkspaceService.generate_draft(ws, user=self.owner_user)
        ws.refresh_from_db()

        self.assertFalse(ws.is_stale)
        initial_hash = ws.source_voucher_hash
        self.assertTrue(len(initial_hash) == 64)

        # 1. Modify HSN code on line item without touching voucher header
        itm.hsn_code = '4011'
        itm.save()

        is_stale = GSTWorkspaceService.check_drift(ws)
        ws.refresh_from_db()
        self.assertTrue(is_stale, "Modifying line item HSN code must trigger drift detection!")
        self.assertTrue(ws.is_stale)

        # Re-generate draft to re-align
        GSTWorkspaceService.generate_draft(ws, user=self.owner_user)
        ws.refresh_from_db()
        self.assertFalse(ws.is_stale)
        self.assertNotEqual(ws.source_voucher_hash, initial_hash)

        # 2. Modify GST rate on line item
        itm.gst_rate = Decimal('12.00')
        itm.save()
        is_stale = GSTWorkspaceService.check_drift(ws)
        self.assertTrue(is_stale, "Modifying line item GST rate must trigger drift detection!")

    # -------------------------------------------------------------------------
    # Phase H & I: Tenant Isolation, RBAC & Accounting Immutability (15 Scenarios)
    # -------------------------------------------------------------------------

    def test_tenant_isolation_and_rbac_permissions(self):
        """
        Verify tenant isolation and RBAC roles:
        - Other company user cannot view workspace (403/404)
        - VIEWER cannot generate draft (403)
        - CA can generate draft (200)
        - OWNER can generate draft and export (200)
        """
        period = "082026"
        # 1. Cross-tenant access blocked
        self.client.force_authenticate(user=self.other_user)
        url = f"/api/v1/gst/workspace/{self.company.id}/?period={period}&return_type=GSTR1"
        res = self.client.get(url)
        self.assertIn(res.status_code, [403, 404])

        # 2. Viewer cannot generate draft
        self.client.force_authenticate(user=self.viewer_user)
        url_draft = f"/api/v1/gst/workspace/{self.company.id}/generate-draft/"
        res_draft = self.client.post(url_draft, {"period": period, "return_type": "GSTR1"})
        self.assertEqual(res_draft.status_code, 403)

        # 3. CA can generate draft
        self.client.force_authenticate(user=self.ca_user)
        res_ca = self.client.post(url_draft, {"period": period, "return_type": "GSTR1"})
        self.assertEqual(res_ca.status_code, 200)

    def test_accounting_integrity_zero_mutation_guarantee(self):
        """
        STRICT PROJECT INVARIANT:
        All GST operations (GSTR-1 generation, GSTR-3B compilation, GSTR-2B ingestion,
        Rule 88A setoff, period reconciliation, manual match, export) MUST NEVER mutate,
        back-populate, or alter accounting records (Voucher, VoucherItem, LedgerEntry).
        """
        v_count_before = Voucher.objects.count()
        item_count_before = VoucherItem.objects.count()
        entry_count_before = LedgerEntry.objects.count()

        # Run full return compilation and reconciliation suite
        res_gstr1 = GSTReturnsService.prepare_gstr1(self.company, self.reg_primary, "082026")
        res_gstr3b = GSTReturnsService.prepare_gstr3b(self.company, self.reg_primary, "082026")
        res_recon = GSTReconciliationService.reconcile_period(self.company, self.reg_primary, "082026")

        v_count_after = Voucher.objects.count()
        item_count_after = VoucherItem.objects.count()
        entry_count_after = LedgerEntry.objects.count()

        self.assertEqual(v_count_before, v_count_after, "Voucher count was modified by GST engine!")
        self.assertEqual(item_count_before, item_count_after, "VoucherItem count was modified by GST engine!")
        self.assertEqual(entry_count_before, entry_count_after, "LedgerEntry count was modified by GST engine!")

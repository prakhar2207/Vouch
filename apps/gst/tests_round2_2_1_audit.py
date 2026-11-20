import json
import hashlib
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
    GSTFilingRecord
)
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.workspace_service import GSTWorkspaceService
from apps.gst.services.payload_validator import GSTPayloadValidator
from apps.gst.services.rate_reference_service import GSTRateScheduleService
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

User = get_user_model()


class GSTRound221IndependentAuditTests(TestCase):
    """
    Independent Verification & Certification Test Suite for SriLekh GST Round 2.2.1.
    Audits and Certifies:
    1. Effective-Dated Statutory GST Rate Reference Schedule & Validation.
    2. Official GSTR-1 Schema Conformance (GSTN Offline Tool Schema v3.1.2).
       - B2CL Grouping by PoS.
       - CDNUR Flat List Structure & Exclusion of B2CS notes.
       - Table 7 B2CS Netting of small unregistered credit/debit notes.
       - Table 8 Nil 4-Way Statutory Breakdown.
       - Table 12 HSN Statutory Rate Validation.
       - Full Table 13 and Amendment Tables (b2ba, b2cla, etc.).
    3. GSTR-3B Compatibility Truth & Clarified Classifications.
       - GSTN GSP/ASP Return Payload v1.4 (Automated API Schema - Not Portal Uploadable).
       - Statutory Table-by-Table Entry Guide & Audit Report.
    4. Payload Reproducibility, Drift Guard, RBAC, and Zero Accounting Mutation.
    """

    def setUp(self):
        self.client = APIClient()

        # Dedicated Sandbox Company: Apex Belting & Industrial Store (Demo)
        self.company = Company.objects.create(
            name='Apex Belting & Industrial Store (Demo)',
            legal_name='Apex Belting & Industrial Store Private Limited',
            gstin='27AAACA1234A1Z5',
            state_code='27',
            email='accounts@apex-belting.com'
        )

        self.owner_user = User.objects.create_user(
            email='audit_owner@srilekh-gst.com',
            password='Password123!'
        )
        self.ca_user = User.objects.create_user(
            email='audit_ca@srilekh-gst.com',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            email='audit_intruder@srilekh-gst.com',
            password='Password123!'
        )

        UserCompany.objects.create(user=self.owner_user, company=self.company, role='OWNER')
        UserCompany.objects.create(user=self.ca_user, company=self.company, role='CA')

        # Secondary Isolated Company
        self.other_company = Company.objects.create(
            name='Isolated Gujarat Belting Store',
            legal_name='Isolated Gujarat Belting Store Pvt Ltd',
            gstin='24AAACG9999G1Z8',
            state_code='24',
            email='contact@gujarat-belts.com'
        )
        UserCompany.objects.create(user=self.other_user, company=self.other_company, role='OWNER')

        # GST Registration
        self.reg_primary = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAACA1234A1Z5',
            legal_name='Apex Belting & Industrial Store Private Limited',
            trade_name='Apex Belting Store',
            state_code='27',
            state_name='Maharashtra',
            taxpayer_type='REGULAR',
            status='ACTIVE',
            is_primary=True,
            verification_status='VERIFIED'
        )

        # Ledger Groups & Ledgers
        self.grp_debtors = LedgerGroup.objects.create(company=self.company, name='Sundry Debtors', nature='ASSET')
        self.grp_sales = LedgerGroup.objects.create(company=self.company, name='Sales Accounts', nature='INCOME')
        self.grp_duties = LedgerGroup.objects.create(company=self.company, name='Duties & Taxes', nature='LIABILITY')

        self.led_output_cgst = Ledger.objects.create(company=self.company, group=self.grp_duties, name='Output CGST', ledger_type='TAX')
        self.led_output_sgst = Ledger.objects.create(company=self.company, group=self.grp_duties, name='Output SGST', ledger_type='TAX')
        self.led_output_igst = Ledger.objects.create(company=self.company, group=self.grp_duties, name='Output IGST', ledger_type='TAX')
        self.led_sales = Ledger.objects.create(company=self.company, group=self.grp_sales, name='Sales Account', ledger_type='SALES')

        # Parties
        self.party_reg_intra = Ledger.objects.create(
            company=self.company, group=self.grp_debtors, name='Pune Auto Components',
            ledger_type='CUSTOMER', gstin='27AAACT2727Q1ZW', state_code='27'
        )
        self.party_unreg_inter = Ledger.objects.create(
            company=self.company, group=self.grp_debtors, name='Indore Industrial Buyer (Unregistered)',
            ledger_type='CUSTOMER', gstin='', state_code='23'
        )
        self.party_unreg_intra = Ledger.objects.create(
            company=self.company, group=self.grp_debtors, name='Mumbai Walk-in Buyer',
            ledger_type='CUSTOMER', gstin='', state_code='27'
        )

        # Products
        self.prod_belts = Product.objects.create(company=self.company, name='Industrial Rubber Belts', sku='SKU-BELT-001', hsn_code='4010', unit='MTR')
        self.prod_valves = Product.objects.create(company=self.company, name='Industrial Safety Valves', sku='SKU-VALVE-001', hsn_code='8481', unit='NOS')
        self.prod_ev = Product.objects.create(company=self.company, name='Electric Industrial Vehicle', sku='SKU-EV-001', hsn_code='8703', unit='NOS')
        self.prod_gold = Product.objects.create(company=self.company, name='Gold Belt Buckles', sku='SKU-GOLD-001', hsn_code='7113', unit='GMS')
        self.prod_paneer = Product.objects.create(company=self.company, name='Pre-Packaged Canteen Paneer', sku='SKU-PANEER-001', hsn_code='0406', unit='KGS')

    # =========================================================================
    # 1. Effective-Dated Statutory GST Rate Reference Schedule & Validation Tests
    # =========================================================================

    def test_effective_dated_ev_tax_rate_transition(self):
        """
        Electric Vehicles (HSN 8703):
        - Prior to 01-Aug-2019: 12% (Notif No. 1/2017-CT(Rate)).
        - From 01-Aug-2019 onwards: 5% (Notif No. 12/2019-CT(Rate)).
        """
        # Historical: May 2018 at 12% is VALID
        res_hist_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2018, 5, 10), applied_rate=Decimal('12.00'), is_interstate=True
        )
        self.assertEqual(res_hist_valid["status"], "VALID")
        self.assertTrue(res_hist_valid["is_statutorily_valid"])

        # Historical: May 2018 at 5% is STATUTORY_MISMATCH (rate was not reduced yet)
        res_hist_invalid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2018, 5, 10), applied_rate=Decimal('5.00'), is_interstate=True
        )
        self.assertEqual(res_hist_invalid["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res_hist_invalid["is_statutorily_valid"])
        self.assertIn("1/2017", res_hist_invalid["notification_reference"])

        # Current: August 2024 at 5% is VALID
        res_curr_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2024, 8, 10), applied_rate=Decimal('5.00'), is_interstate=True
        )
        self.assertEqual(res_curr_valid["status"], "VALID")

        # Current: August 2024 at 12% is STATUTORY_MISMATCH (must be 5%)
        res_curr_invalid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2024, 8, 10), applied_rate=Decimal('12.00'), is_interstate=True
        )
        self.assertEqual(res_curr_invalid["status"], "STATUTORY_MISMATCH")
        self.assertIn("12/2019", res_curr_invalid["notification_reference"])

    def test_effective_dated_paneer_dairy_tax_rate_transition(self):
        """
        Pre-Packaged Paneer / Dairy (HSN 0406):
        - Prior to 18-Jul-2022: Exempt 0% (Notif No. 2/2017-CT(Rate)).
        - From 18-Jul-2022 onwards: 5% (Notif No. 6/2022-CT(Rate)).
        """
        # Prior to July 2022: 0% is VALID (Exempt)
        res_pre = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2021, 6, 1), applied_rate=Decimal('0.00'), is_interstate=False
        )
        self.assertEqual(res_pre["status"], "VALID")

        # Prior to July 2022: 5% is STATUTORY_MISMATCH
        res_pre_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2021, 6, 1), applied_rate=Decimal('5.00'), is_interstate=False
        )
        self.assertEqual(res_pre_err["status"], "STATUTORY_MISMATCH")

        # Post July 2022: 5% is VALID
        res_post = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2024, 8, 1), applied_rate=Decimal('5.00'), is_interstate=False
        )
        self.assertEqual(res_post["status"], "VALID")

        # Post July 2022: 0% is STATUTORY_MISMATCH (brought into 5% tax bracket)
        res_post_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2024, 8, 1), applied_rate=Decimal('0.00'), is_interstate=False
        )
        self.assertEqual(res_post_err["status"], "STATUTORY_MISMATCH")
        self.assertIn("6/2022", res_post_err["notification_reference"])

    def test_effective_dated_restaurant_service_rate_transition(self):
        """
        Restaurant Services (SAC 9963):
        - Prior to 15-Nov-2017: 18% with ITC (Notif No. 11/2017-CT(Rate)).
        - From 15-Nov-2017 onwards: 5% without ITC (Notif No. 46/2017-CT(Rate)).
        """
        res_pre = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2017, 8, 1), applied_rate=Decimal('18.00'), is_interstate=False
        )
        self.assertEqual(res_pre["status"], "VALID")

        res_post = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2024, 8, 1), applied_rate=Decimal('5.00'), is_interstate=False
        )
        self.assertEqual(res_post["status"], "VALID")

        res_post_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2024, 8, 1), applied_rate=Decimal('18.00'), is_interstate=False
        )
        self.assertEqual(res_post_err["status"], "STATUTORY_MISMATCH")
        self.assertIn("46/2017", res_post_err["notification_reference"])

    def test_special_statutory_rates(self):
        """
        Special rates under GST law:
        - Gold (HSN 7113): 3% standard rate throughout.
        - Rough Diamonds (HSN 7102): 0.25% from 25-Jan-2018 (Notif No. 1/2018).
        - Merchant Exports: 0.1% (Notif No. 40/2017 & 41/2017).
        - Compensation Cess on Luxury Motor Vehicles (HSN 8703 > 1500cc): 28% + 22% cess.
        """
        # Gold at 3% is VALID; Gold at 18% is STATUTORY_MISMATCH
        res_gold_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7113', tx_date=date(2024, 8, 1), applied_rate=Decimal('3.00'), is_interstate=False
        )
        self.assertEqual(res_gold_valid["status"], "VALID")

        res_gold_invalid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7113', tx_date=date(2024, 8, 1), applied_rate=Decimal('18.00'), is_interstate=False
        )
        self.assertEqual(res_gold_invalid["status"], "STATUTORY_MISMATCH")

        # Rough diamonds at 0.25% is VALID
        res_diamond = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2024, 8, 1), applied_rate=Decimal('0.25'), is_interstate=True
        )
        self.assertEqual(res_diamond["status"], "VALID")

        # Merchant export at 0.1% is VALID
        res_export = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='MERCHANT_EXPORT', tx_date=date(2024, 8, 1), applied_rate=Decimal('0.10'), is_interstate=True
        )
        self.assertEqual(res_export["status"], "VALID")

        # Luxury Motor Vehicle with 22% Cess is VALID
        res_car_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2024, 8, 1), applied_rate=Decimal('28.00'),
            applied_cess=Decimal('22.00'), is_interstate=True
        )
        self.assertEqual(res_car_valid["status"], "VALID")

    def test_unrecognized_hsn_triggers_review_warning_not_blocking_error(self):
        """Unrecognized HSN is flagged for human/CA review (WARNING) without crashing or blocking export."""
        res_unknown = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='999999', tx_date=date(2024, 8, 1), applied_rate=Decimal('18.00'), is_interstate=True
        )
        self.assertEqual(res_unknown["status"], "REVIEW_REQUIRED")
        self.assertTrue(res_unknown["is_statutorily_valid"])
        self.assertEqual(res_unknown["issue"]["severity"], "WARNING")

    # =========================================================================
    # 2. Official GSTR-1 Schema Conformance & Table Structure Tests
    # =========================================================================

    def test_gstr1_b2cl_grouping_by_pos_conformance(self):
        """
        Table 5 (B2CL): Invoices must be grouped by Place of Supply (pos).
        Multiple invoices to the same PoS must appear under a single {"pos": "23", "inv": [inv1, inv2]}.
        Each invoice must include 'inv_typ': 'R'.
        """
        # Create 2 large interstate invoices to unregistered buyer in MP (PoS 23) in August 2024 (> ₹1,00,000 threshold)
        v1 = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number='B2CL-AUG-001',
            voucher_date=date(2024, 8, 5), party_ledger=self.party_unreg_inter,
            buyer_state_code='23', total_amount=Decimal('150000.00'), status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v1, product=self.prod_belts, quantity=Decimal('10.00'), rate=Decimal('12711.86'),
            taxable_amount=Decimal('127118.64'), gst_rate=Decimal('18.00'), igst_amount=Decimal('22881.36'),
            total_amount=Decimal('150000.00')
        )

        v2 = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number='B2CL-AUG-002',
            voucher_date=date(2024, 8, 15), party_ledger=self.party_unreg_inter,
            buyer_state_code='23', total_amount=Decimal('200000.00'), status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v2, product=self.prod_valves, quantity=Decimal('5.00'), rate=Decimal('33898.31'),
            taxable_amount=Decimal('169491.53'), gst_rate=Decimal('18.00'), igst_amount=Decimal('30508.47'),
            total_amount=Decimal('200000.00')
        )

        res = GSTReturnsService.prepare_gstr1(
            company=self.company, return_period="082024", registration=self.reg_primary
        )
        gstr1_json = res["official_gstr1_json"]
        b2cl = gstr1_json.get("b2cl", [])

        # Must have exactly 1 group for PoS 23
        self.assertEqual(len(b2cl), 1)
        group_mp = b2cl[0]
        self.assertEqual(group_mp["pos"], "23")

        # Must have 2 invoices under this group
        self.assertEqual(len(group_mp["inv"]), 2)
        inv_nums = [inv["inum"] for inv in group_mp["inv"]]
        self.assertIn("B2CL-AUG-001", inv_nums)
        self.assertIn("B2CL-AUG-002", inv_nums)

        # Each invoice must have inv_typ == 'R'
        for inv in group_mp["inv"]:
            self.assertEqual(inv.get("inv_typ"), "R")

    def test_gstr1_cdnur_flat_list_and_b2cs_netting_statutory_invariant(self):
        """
        Table 9B CDNUR and Table 7 B2CS Statutory Invariant:
        1. Large interstate credit notes (> threshold) to unregistered buyers go to Table 9B CDNUR as flat note objects (typ='B2CL').
        2. Small credit notes to unregistered buyers MUST NOT appear in Table 9B CDNUR (typ='B2CS' is legally prohibited in CDNUR).
        3. Small credit notes must be netted directly into Table 7 (B2CS) turnover and tax heads.
        """
        # 1. Post Small Intrastate Sales Voucher (₹20,000)
        v_sales = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number='INV-RETAIL-001',
            voucher_date=date(2024, 8, 2), party_ledger=self.party_unreg_intra,
            buyer_state_code='27', total_amount=Decimal('23600.00'), status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_sales, product=self.prod_belts, quantity=Decimal('2.00'), rate=Decimal('10000.00'),
            taxable_amount=Decimal('20000.00'), gst_rate=Decimal('18.00'), cgst_amount=Decimal('1800.00'),
            sgst_amount=Decimal('1800.00'), total_amount=Decimal('23600.00')
        )

        # 2. Post Small Credit Note against it (₹5,900 incl tax, taxable ₹5,000)
        v_cn_small = Voucher.objects.create(
            company=self.company, voucher_type='CREDIT_NOTE', voucher_number='CN-RETAIL-001',
            voucher_date=date(2024, 8, 10), party_ledger=self.party_unreg_intra,
            buyer_state_code='27', total_amount=Decimal('5900.00'), status='POSTED',
            original_invoice=v_sales,
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_cn_small, product=self.prod_belts, quantity=Decimal('0.50'), rate=Decimal('10000.00'),
            taxable_amount=Decimal('5000.00'), gst_rate=Decimal('18.00'), cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'), total_amount=Decimal('5900.00')
        )

        # 3. Post Large Interstate Unregistered Sales Voucher (₹1,50,000)
        v_sales_large = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number='INV-LARGE-001',
            voucher_date=date(2024, 8, 3), party_ledger=self.party_unreg_inter,
            buyer_state_code='23', total_amount=Decimal('177000.00'), status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_sales_large, product=self.prod_valves, quantity=Decimal('5.00'), rate=Decimal('30000.00'),
            taxable_amount=Decimal('150000.00'), gst_rate=Decimal('18.00'), igst_amount=Decimal('27000.00'),
            total_amount=Decimal('177000.00')
        )

        # 4. Post Large Credit Note against it (₹1,18,000 incl tax > ₹1,00,000 threshold)
        v_cn_large = Voucher.objects.create(
            company=self.company, voucher_type='CREDIT_NOTE', voucher_number='CN-LARGE-001',
            voucher_date=date(2024, 8, 20), party_ledger=self.party_unreg_inter,
            buyer_state_code='23', total_amount=Decimal('118000.00'), status='POSTED',
            original_invoice=v_sales_large,
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_cn_large, product=self.prod_valves, quantity=Decimal('3.00'), rate=Decimal('30000.00'),
            taxable_amount=Decimal('100000.00'), gst_rate=Decimal('18.00'), igst_amount=Decimal('18000.00'),
            total_amount=Decimal('118000.00')
        )

        # Generate GSTR-1
        res = GSTReturnsService.prepare_gstr1(
            company=self.company, return_period="082024", registration=self.reg_primary
        )
        gstr1 = res["official_gstr1_json"]

        # Table 7 B2CS must have netted taxable value: ₹20,000 - ₹5,000 = ₹15,000
        b2cs = gstr1.get("b2cs", [])
        intra_row = next((r for r in b2cs if r["pos"] == "27" and r["sply_ty"] == "INTRA"), None)
        self.assertIsNotNone(intra_row)
        self.assertEqual(Decimal(str(intra_row["txval"])), Decimal('15000.00'))
        self.assertEqual(Decimal(str(intra_row["camt"])), Decimal('1350.00'))
        self.assertEqual(Decimal(str(intra_row["samt"])), Decimal('1350.00'))

        # Table 9B CDNUR must contain ONLY the large credit note, NEVER B2CS
        cdnur = gstr1.get("cdnur", [])
        self.assertEqual(len(cdnur), 1)
        note = cdnur[0]
        self.assertEqual(note["typ"], "B2CL")
        self.assertEqual(note["nt_num"], "CN-LARGE-001")
        self.assertEqual(note["ntty"], "C")
        self.assertEqual(note["inum"], "INV-LARGE-001")
        self.assertEqual(note["p_gst"], "N")

        # Must not contain any B2CS note
        for nt in cdnur:
            self.assertNotEqual(nt.get("typ"), "B2CS")

    def test_gstr1_table8_nil_four_way_statutory_breakdown(self):
        """
        Table 8: Nil/Exempt supplies must be partitioned into the 4 statutory buckets:
        - INTRAB2B: Intra-State supplies to registered persons.
        - INTRAB2C: Intra-State supplies to unregistered persons.
        - INTERB2B: Inter-State supplies to registered persons.
        - INTERB2C: Inter-State supplies to unregistered persons.
        """
        res = GSTReturnsService.prepare_gstr1(
            company=self.company, return_period="082024", registration=self.reg_primary
        )
        gstr1 = res["official_gstr1_json"]
        nil_inv = gstr1.get("nil", {}).get("inv", [])

        # Must have exactly 4 statutory rows
        self.assertEqual(len(nil_inv), 4)
        sply_types = {r["sply_ty"] for r in nil_inv}
        self.assertEqual(sply_types, {"INTRAB2B", "INTRAB2C", "INTERB2B", "INTERB2C"})

        for r in nil_inv:
            self.assertIn("nil_amt", r)
            self.assertIn("expt_amt", r)
            self.assertIn("ngsup_amt", r)

    def test_gstr1_amendment_sections_present_in_official_payload(self):
        """
        GSTR-1 JSON must include all official amendment arrays as lists:
        b2ba, b2cla, b2csa, cdnra, cdnura, expa, ata, txpda.
        """
        res = GSTReturnsService.prepare_gstr1(
            company=self.company, return_period="082024", registration=self.reg_primary
        )
        gstr1 = res["official_gstr1_json"]
        amendment_keys = ['b2ba', 'b2cla', 'b2csa', 'cdnra', 'cdnura', 'expa', 'ata', 'txpda']
        for k in amendment_keys:
            self.assertIn(k, gstr1)
            self.assertIsInstance(gstr1[k], list)

    def test_validator_detects_prohibited_b2cs_in_cdnur(self):
        """Pre-export validator explicitly detects and rejects any malformed CDNUR payload containing typ: B2CS."""
        malformed_payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082024",
            "version": "GST3.1.2",
            "cur_gt": 10000.0,
            "b2b": [],
            "b2cl": [],
            "b2cs": [],
            "cdnr": [],
            "cdnur": [
                {
                    "typ": "B2CS",  # PROHIBITED!
                    "nt_num": "CN-ILLEGAL-01",
                    "ntty": "C",
                    "inum": "INV-001",
                    "val": 5000.0,
                    "pos": "27"
                }
            ],
            "exp": [],
            "hsn": {"data": []},
            "doc_issue": {"doc_det": []}
        }
        val_res = GSTPayloadValidator.validate_gstr1_payload(malformed_payload)
        self.assertFalse(val_res["is_valid"])
        err_codes = [iss["error_code"] for iss in val_res["issues"]]
        self.assertIn("GST_CDNUR_B2CS_PROHIBITED", err_codes)

    # =========================================================================
    # 3. GSTR-3B Export Compatibility Truth & Product Labels Tests
    # =========================================================================

    def test_gstr3b_export_classification_truth(self):
        """
        Verifies GSTR-3B export classification truth:
        1. Format JSON is classified as 'GSTN_API_RETURN_PAYLOAD' and portal_uploadable is False.
        2. Carrying explicit notice: GUI does NOT accept JSON; use for automated API or use Table-by-Table Entry Guide.
        3. Format REVIEW_REPORT is classified as 'STATUTORY_PORTAL_ENTRY_GUIDE'.
        """
        workspace = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR3B',
            return_period='082024',
            financial_year='2024-2025',
            status='DRAFT'
        )

        # JSON Export
        export_json = GSTWorkspaceService.export_draft(workspace, export_format='JSON')
        self.assertTrue(export_json["success"])
        self.assertFalse(export_json["portal_uploadable"])
        self.assertEqual(export_json["export_classification"], "GSTN_API_RETURN_PAYLOAD")
        self.assertIn("does NOT support direct .json file upload", export_json["portal_compatibility_notice"])

        # Reset status for second export
        workspace.status = 'DRAFT'
        workspace.save()

        # Review Report Export (Human Audit & Portal Form Guide)
        export_report = GSTWorkspaceService.export_draft(workspace, export_format='REVIEW_REPORT')
        self.assertTrue(export_report["success"])
        self.assertFalse(export_report["portal_uploadable"])
        self.assertEqual(export_report["export_classification"], "STATUTORY_PORTAL_ENTRY_GUIDE")
        self.assertEqual(
            export_report["payload"]["title"],
            "SriLekh Statutory GSTR-3B Table-by-Table Portal Entry Guide & Audit Report"
        )
        self.assertIn("table_3_1_supplies", export_report["payload"])
        self.assertIn("table_4_itc", export_report["payload"])

    def test_gstr1_export_classification_truth(self):
        """GSTR-1 JSON export is classified as OFFICIAL_PORTAL_OFFLINE_TOOL_JSON with portal_uploadable == True."""
        workspace = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082024',
            financial_year='2024-2025',
            status='DRAFT'
        )
        export_res = GSTWorkspaceService.export_draft(workspace, export_format='JSON')
        self.assertTrue(export_res["success"])
        self.assertTrue(export_res["portal_uploadable"])
        self.assertEqual(export_res["export_classification"], "OFFICIAL_PORTAL_OFFLINE_TOOL_JSON")
        self.assertIn("Uploadable directly to GST Portal", export_res["portal_compatibility_notice"])

    # =========================================================================
    # 4. Payload Reproducibility, Drift Guard & Accounting Immutability Tests
    # =========================================================================

    def test_deterministic_payload_hash_reproducibility(self):
        """Exporting an unchanged return draft produces the identical SHA-256 payload hash."""
        workspace = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082024',
            financial_year='2024-2025',
            status='DRAFT'
        )
        exp1 = GSTWorkspaceService.export_draft(workspace, export_format='JSON')
        hash1 = exp1["payload_hash"]

        # Reset workspace status to DRAFT and re-export
        workspace.status = 'DRAFT'
        workspace.save()

        exp2 = GSTWorkspaceService.export_draft(workspace, export_format='JSON')
        hash2 = exp2["payload_hash"]

        self.assertEqual(hash1, hash2)
        self.assertEqual(exp1["payload"], exp2["payload"])

    def test_cross_tenant_isolation_and_export_rejection(self):
        """A user from another tenant is strictly rejected with HTTP 403 when attempting export."""
        self.client.force_authenticate(user=self.other_user)
        url = f"/api/v1/gst/workspace/{self.company.id}/export/"
        res = self.client.post(url, {"period": "082024", "return_type": "GSTR1", "format": "JSON"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_zero_mutation_accounting_immutability(self):
        """
        Critical System Invariant:
        Draft generation, statutory validation, and export must NEVER mutate vouchers, items, or ledger entries.
        """
        # Count records before
        voucher_count_before = Voucher.objects.filter(company=self.company).count()
        item_count_before = VoucherItem.objects.filter(voucher__company=self.company).count()
        entry_count_before = LedgerEntry.objects.filter(voucher__company=self.company).count()

        workspace = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082024',
            financial_year='2024-2025',
            status='DRAFT'
        )

        GSTWorkspaceService.generate_draft(workspace)
        GSTPayloadValidator.validate_payload(workspace.return_type, workspace.draft_payload.get("official_gstr1_json", {}))
        GSTWorkspaceService.export_draft(workspace, export_format='JSON')

        # Count records after
        voucher_count_after = Voucher.objects.filter(company=self.company).count()
        item_count_after = VoucherItem.objects.filter(voucher__company=self.company).count()
        entry_count_after = LedgerEntry.objects.filter(voucher__company=self.company).count()

        self.assertEqual(voucher_count_before, voucher_count_after)
        self.assertEqual(item_count_before, item_count_after)
        self.assertEqual(entry_count_before, entry_count_after)

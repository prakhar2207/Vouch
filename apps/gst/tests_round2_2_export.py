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
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

User = get_user_model()


class GSTRound22ExportCertificationTests(TestCase):
    """
    Comprehensive Verification & Certification Test Suite for SriLekh GST Round 2.2.
    Validates:
    - GSTR-1 Schema Conformance against GSTN Offline Tool v3.1.2.
    - GSTR-3B Schema Conformance against GSTN Offline Tool v1.4.
    - Statutory Pre-Export Payload Validation Engine (Error/Warning/Equilibrium/PoS).
    - Period-Aware CBIC Notification No. 12/2024 Thresholds (Pre/Post Aug 2024).
    - CGST Act Section 49(4) Reverse Charge 100% Cash Invariant.
    - Net ITC Equilibrium & Table 4 Mathematical Consistency.
    - Voucher Drift Detection & Stale Export Prevention.
    - Deterministic SHA-256 Payload Hash Reproducibility.
    - Export Lifecycle State Machine (DRAFT -> REVIEWED -> EXPORTED).
    - Multi-Format Support (JSON, REVIEW_REPORT).
    - Zero Mutation Double-Entry Accounting Invariant.
    - Multi-Tenant & Role-Based Access Control (RBAC).
    """

    def setUp(self):
        self.client = APIClient()

        # Users with distinct roles
        self.owner_user = User.objects.create_user(
            email='export_owner@srilekh-gst.com',
            password='Password123!'
        )
        self.ca_user = User.objects.create_user(
            email='export_ca@srilekh-gst.com',
            password='Password123!'
        )
        self.viewer_user = User.objects.create_user(
            email='export_viewer@srilekh-gst.com',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            email='export_intruder@srilekh-gst.com',
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

        # Secondary Isolated Company in Gujarat (State 24)
        self.other_company = Company.objects.create(
            name='Isolated Gujarat Belting Store',
            legal_name='Isolated Gujarat Belting Store Pvt Ltd',
            gstin='24AAACG9999G1Z8',
            state_code='24',
            email='contact@gujarat-belts.com'
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
            is_primary=True,
            verification_status='VERIFIED'
        )

        # Ledger Groups
        self.grp_debtors = LedgerGroup.objects.create(
            company=self.company,
            name='Sundry Debtors',
            nature='ASSET'
        )
        self.grp_creditors = LedgerGroup.objects.create(
            company=self.company,
            name='Sundry Creditors',
            nature='LIABILITY'
        )
        self.grp_sales = LedgerGroup.objects.create(
            company=self.company,
            name='Sales Accounts',
            nature='INCOME'
        )
        self.grp_purchase = LedgerGroup.objects.create(
            company=self.company,
            name='Purchase Accounts',
            nature='EXPENSE'
        )
        self.grp_duties = LedgerGroup.objects.create(
            company=self.company,
            name='Duties & Taxes',
            nature='LIABILITY'
        )

        # Tax Ledgers
        self.led_output_cgst = Ledger.objects.create(
            company=self.company,
            group=self.grp_duties,
            name='Output CGST',
            ledger_type='TAX'
        )
        self.led_output_sgst = Ledger.objects.create(
            company=self.company,
            group=self.grp_duties,
            name='Output SGST',
            ledger_type='TAX'
        )
        self.led_output_igst = Ledger.objects.create(
            company=self.company,
            group=self.grp_duties,
            name='Output IGST',
            ledger_type='TAX'
        )
        self.led_input_cgst = Ledger.objects.create(
            company=self.company,
            group=self.grp_duties,
            name='Input CGST',
            ledger_type='TAX'
        )
        self.led_input_sgst = Ledger.objects.create(
            company=self.company,
            group=self.grp_duties,
            name='Input SGST',
            ledger_type='TAX'
        )
        self.led_input_igst = Ledger.objects.create(
            company=self.company,
            group=self.grp_duties,
            name='Input IGST',
            ledger_type='TAX'
        )

        # Income/Expense Ledgers
        self.led_sales = Ledger.objects.create(
            company=self.company,
            group=self.grp_sales,
            name='Sales GST 18%',
            ledger_type='SALES'
        )
        self.led_purchase = Ledger.objects.create(
            company=self.company,
            group=self.grp_purchase,
            name='Purchase GST 18%',
            ledger_type='PURCHASE'
        )

        # Party Ledgers
        self.party_registered_intra = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Mumbai Engineering Works',
            ledger_type='CUSTOMER',
            gstin='27AAACT2727Q1ZW',
            state_code='27'
        )
        self.party_registered_inter = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Indore Belting Suppliers',
            ledger_type='CUSTOMER',
            gstin='23AAACI2323P1ZL',
            state_code='23'
        )
        self.party_unregistered_intra = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Local Retail Buyer',
            ledger_type='CUSTOMER',
            gstin='',
            state_code='27'
        )
        self.party_unregistered_inter = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Bhopal Trader (Unregistered)',
            ledger_type='CUSTOMER',
            gstin='',
            state_code='23'
        )
        self.vendor_vendor_rcm = Ledger.objects.create(
            company=self.company,
            group=self.grp_creditors,
            name='National Goods Transport Co (GTA RCM)',
            ledger_type='VENDOR',
            gstin='',
            state_code='27'
        )
        self.vendor_registered_regular = Ledger.objects.create(
            company=self.company,
            group=self.grp_creditors,
            name='Pune Rubber Mills Pvt Ltd',
            ledger_type='VENDOR',
            gstin='27AAACP9999P1Z1',
            state_code='27'
        )

        # Inventory
        self.warehouse = Warehouse.objects.create(
            company=self.company,
            name='Central Depot Thane'
        )
        self.prod_belt = Product.objects.create(
            company=self.company,
            name='Heavy Duty Conveyor Belt 500mm',
            sku='SKU-BELT-EXP-01',
            hsn_code='4010',
            unit='NOS'
        )
        self.prod_service = Product.objects.create(
            company=self.company,
            name='Belt Splicing Service',
            sku='SKU-SRV-EXP-01',
            hsn_code='9987',
            unit='OTH'
        )

    # =========================================================================
    # 1. GSTR-1 Schema Conformance & Validation Tests (GSTN Schema v3.1.2)
    # =========================================================================

    def test_gstr1_valid_payload_conformance(self):
        """Verifies that a well-formed GSTR-1 payload passes pre-export validation with 0 errors."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "version": "GST3.1.2",
            "cur_gt": 118000.00,
            "b2b": [
                {
                    "ctin": "27AAACT2727Q1ZW",
                    "inv": [
                        {
                            "inum": "INV-2026-001",
                            "idt": "15-08-2026",
                            "val": 118000.00,
                            "pos": "27",
                            "rchrg": "N",
                            "inv_typ": "R",
                            "itms": [
                                {
                                    "num": 1,
                                    "itm_det": {
                                        "rt": 18.0,
                                        "txval": 100000.00,
                                        "iamt": 0.0,
                                        "camt": 9000.00,
                                        "samt": 9000.00,
                                        "csamt": 0.0
                                    }
                                }
                            ]
                        }
                    ]
                }
            ],
            "b2cl": [],
            "b2cs": [],
            "hsn": {
                "data": [
                    {
                        "num": 1,
                        "hsn_sc": "4010",
                        "desc": "Conveyor Belts",
                        "uqc": "MTR",
                        "qty": 100.0,
                        "val": 118000.00,
                        "txval": 100000.00,
                        "iamt": 0.0,
                        "camt": 9000.00,
                        "samt": 9000.00,
                        "csamt": 0.0
                    }
                ]
            },
            "doc_issue": {
                "doc_det": [
                    {
                        "doc_num": 1,
                        "doc_typ": "Invoices for outward supply",
                        "from": "INV-2026-001",
                        "to": "INV-2026-001",
                        "totnum": 1,
                        "canc": 0,
                        "net_issue": 1
                    }
                ]
            }
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["blocking_errors_count"], 0)
        self.assertEqual(res["conformance_standard"], "GSTN Offline Tool Schema v3.1.2")

    def test_gstr1_header_invalid_gstin(self):
        """Rejects malformed supplier GSTIN in GSTR-1 header."""
        payload = {"gstin": "INVALID_GSTIN_123", "fp": "082026", "version": "GST3.1.2"}
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_SCHEMA_INVALID_GSTIN", err_codes)

    def test_gstr1_header_invalid_period(self):
        """Rejects invalid return period in GSTR-1 header."""
        payload = {"gstin": "27AAACA1234A1Z5", "fp": "132026"}
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_SCHEMA_INVALID_PERIOD", err_codes)

    def test_gstr1_b2b_self_supply_prohibition(self):
        """Rejects outward B2B supply where recipient GSTIN equals supplier GSTIN."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [{"ctin": "27AAACA1234A1Z5", "inv": []}]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_B2B_SELF_SUPPLY_PROHIBITED", err_codes)

    def test_gstr1_b2b_duplicate_invoice_number(self):
        """Detects and rejects duplicate invoice numbers within the same tax period."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "27AAACT2727Q1ZW",
                    "inv": [
                        {"inum": "INV-001", "idt": "10-08-2026", "val": 1180.0, "pos": "27", "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 1000.0, "camt": 90.0, "samt": 90.0, "iamt": 0.0, "csamt": 0.0}}]},
                        {"inum": "INV-001", "idt": "12-08-2026", "val": 1180.0, "pos": "27", "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 1000.0, "camt": 90.0, "samt": 90.0, "iamt": 0.0, "csamt": 0.0}}]}
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_DUPLICATE_INVOICE_NUM", err_codes)

    def test_gstr1_b2b_invoice_total_mathematical_mismatch(self):
        """Detects mathematical discrepancy between invoice header 'val' and sum of items."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "27AAACT2727Q1ZW",
                    "inv": [
                        {
                            "inum": "INV-002",
                            "idt": "10-08-2026",
                            "val": 150000.00,  # mismatch with 118000
                            "pos": "27",
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 100000.0, "camt": 9000.0, "samt": 9000.0, "iamt": 0.0, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertTrue(res["is_valid"])
        self.assertGreater(res["warnings_count"], 0)
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_CALC_INVOICE_TOTAL_MISMATCH", err_codes)

    def test_gstr1_b2b_igst_on_intrastate_prohibited(self):
        """Rejects IGST on intrastate supplies (PoS == Supplier State)."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "27AAACT2727Q1ZW",
                    "inv": [
                        {
                            "inum": "INV-003",
                            "idt": "10-08-2026",
                            "val": 118000.00,
                            "pos": "27",  # Intrastate
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 100000.0, "camt": 0.0, "samt": 0.0, "iamt": 18000.0, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_CALC_IGST_ON_INTRASTATE", err_codes)

    def test_gstr1_b2b_cgst_sgst_on_interstate_prohibited(self):
        """Rejects CGST/SGST on interstate supplies (PoS != Supplier State)."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "23AAACI2323P1ZL",
                    "inv": [
                        {
                            "inum": "INV-004",
                            "idt": "10-08-2026",
                            "val": 118000.00,
                            "pos": "23",  # Interstate
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 100000.0, "camt": 9000.0, "samt": 9000.0, "iamt": 0.0, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_CALC_CGST_SGST_ON_INTERSTATE", err_codes)

    def test_gstr1_b2b_non_standard_gst_rate_rejected(self):
        """Rejects non-standard GST rate (e.g. 13.5%)."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "27AAACT2727Q1ZW",
                    "inv": [
                        {
                            "inum": "INV-005",
                            "idt": "10-08-2026",
                            "val": 11350.00,
                            "pos": "27",
                            "itms": [{"num": 1, "itm_det": {"rt": 13.5, "txval": 10000.0, "camt": 675.0, "samt": 675.0, "iamt": 0.0, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_RATE_NON_STANDARD", err_codes)

    def test_gstr1_b2b_negative_amounts_prohibited(self):
        """Rejects negative invoice amounts (negative amounts must be in Credit Notes Table 9B)."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2b": [
                {
                    "ctin": "27AAACT2727Q1ZW",
                    "inv": [
                        {
                            "inum": "INV-006",
                            "idt": "10-08-2026",
                            "val": -1180.00,
                            "pos": "27",
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": -1000.0, "camt": -90.0, "samt": -90.0, "iamt": 0.0, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_NEGATIVE_AMOUNT_PROHIBITED", err_codes)

    def test_gstr1_b2cl_period_aware_threshold_post_august_2024(self):
        """
        Enforces CBIC Notification No. 12/2024:
        For return periods >= August 2024, B2CL threshold is > ₹1,00,000.
        Invoice of ₹80,000 in Table 5 B2CL fails validation.
        """
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",  # Aug 2026
            "b2cl": [
                {
                    "pos": "23",
                    "inv": [
                        {
                            "inum": "B2CL-001",
                            "idt": "15-08-2026",
                            "val": 80000.00,  # <= 1,00,000
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 67796.61, "iamt": 12203.39, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_B2CL_BELOW_THRESHOLD", err_codes)

    def test_gstr1_b2cl_period_aware_threshold_pre_august_2024(self):
        """
        For return periods <= July 2024, B2CL threshold is > ₹2,50,000.
        Invoice of ₹1,80,000 in July 2024 B2CL fails validation (should be B2CS).
        """
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "072024",  # July 2024
            "b2cl": [
                {
                    "pos": "23",
                    "inv": [
                        {
                            "inum": "B2CL-002",
                            "idt": "15-07-2024",
                            "val": 180000.00,  # <= 2,50,000
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 152542.37, "iamt": 27457.63, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_B2CL_BELOW_THRESHOLD", err_codes)

    def test_gstr1_b2cl_intrastate_supply_prohibited(self):
        """Rejects intrastate supply in Table 5 (B2CL is strictly interstate)."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "b2cl": [
                {
                    "pos": "27",  # Intrastate PoS == Supplier State
                    "inv": [
                        {
                            "inum": "B2CL-003",
                            "idt": "15-08-2026",
                            "val": 150000.00,
                            "itms": [{"num": 1, "itm_det": {"rt": 18.0, "txval": 127118.64, "iamt": 22881.36, "csamt": 0.0}}]
                        }
                    ]
                }
            ]
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_B2CL_INTRASTATE_PROHIBITED", err_codes)

    def test_gstr1_hsn_invalid_code_format(self):
        """Rejects non-numeric or short HSN codes in Table 12."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "hsn": {
                "data": [
                    {
                        "num": 1,
                        "hsn_sc": "40",  # Too short (< 4 digits)
                        "txval": 10000.0,
                        "iamt": 0.0,
                        "camt": 900.0,
                        "samt": 900.0,
                        "csamt": 0.0
                    }
                ]
            }
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_HSN_CODE_INVALID", err_codes)

    def test_gstr1_document_issue_arithmetic_mismatch(self):
        """Rejects Table 13 document issue summary if totnum != net_issue + canc."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "fp": "082026",
            "doc_issue": {
                "doc_det": [
                    {
                        "doc_num": 1,
                        "doc_typ": "Invoices",
                        "totnum": 10,
                        "canc": 2,
                        "net_issue": 5  # 5 + 2 != 10
                    }
                ]
            }
        }
        res = GSTPayloadValidator.validate_gstr1_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_DOC_ISSUE_ARITHMETIC_ERROR", err_codes)

    # =========================================================================
    # 2. GSTR-3B Schema Conformance & Validation Tests (GSTN Schema v1.4)
    # =========================================================================

    def test_gstr3b_valid_payload_conformance(self):
        """Verifies that a well-formed GSTR-3B payload passes validation according to GSTN Schema v1.4."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "ret_period": "082026",
            "filing_typ": "GSTR3B",
            "version": "GST3B1.4",
            "sup_details": {
                "osup_det": {"txval": 100000.00, "iamt": 0.0, "camt": 9000.00, "samt": 9000.00, "csamt": 0.0},
                "osup_zero": {"txval": 0.0, "iamt": 0.0, "csamt": 0.0},
                "osup_nil_exmp": {"txval": 0.0},
                "isup_rev": {"txval": 20000.00, "iamt": 0.0, "camt": 1800.00, "samt": 1800.00, "csamt": 0.0},
                "osup_nongst": {"txval": 0.0}
            },
            "inter_sup": {
                "unreg_details": [{"pos": "23", "txval": 150000.00, "iamt": 27000.00}],
                "comp_details": [],
                "uin_details": []
            },
            "itc_elg": {
                "itc_avl": {
                    "import_goods": {"iamt": 0.0, "csamt": 0.0},
                    "import_services": {"iamt": 0.0, "csamt": 0.0},
                    "isup_rev": {"iamt": 0.0, "camt": 1800.00, "samt": 1800.00, "csamt": 0.0},
                    "isd": {"iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0},
                    "all_other": {"txval": 80000.00, "iamt": 0.0, "camt": 7200.00, "samt": 7200.00, "csamt": 0.0}
                },
                "itc_rev": {
                    "rule42_43": {"iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0},
                    "others": {"iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0}
                },
                "itc_net": {
                    "iamt": 0.0,
                    "camt": 9000.00,  # 7200 + 1800
                    "samt": 9000.00,  # 7200 + 1800
                    "csamt": 0.0
                },
                "itc_inelg": {
                    "as_per_sec_17_5": {"iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0},
                    "others": {"iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0}
                }
            },
            "inward_sup": {
                "isup_details": [
                    {"ty": "GST", "inter": 0.0, "intra": 0.0},
                    {"ty": "NON_GST", "inter": 0.0, "intra": 0.0}
                ]
            }
        }
        res = GSTPayloadValidator.validate_gstr3b_payload(payload)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["blocking_errors_count"], 0)
        self.assertEqual(res["conformance_standard"], "GSTN Offline Tool Schema v1.4")

    def test_gstr3b_net_itc_mathematical_inconsistency_rejected(self):
        """
        Rejects GSTR-3B payload where Table 4 itc_net does not strictly equal
        available ITC minus reversed ITC.
        """
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "ret_period": "082026",
            "filing_typ": "GSTR3B",
            "sup_details": {
                "osup_det": {"txval": 100000.00, "iamt": 0.0, "camt": 9000.00, "samt": 9000.00, "csamt": 0.0},
                "osup_zero": {"txval": 0.0, "iamt": 0.0, "csamt": 0.0},
                "osup_nil_exmp": {"txval": 0.0},
                "isup_rev": {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0},
                "osup_nongst": {"txval": 0.0}
            },
            "itc_elg": {
                "itc_avl": {
                    "all_other": {"iamt": 0.0, "camt": 5000.00, "samt": 5000.00, "csamt": 0.0}
                },
                "itc_rev": {
                    "others": {"iamt": 0.0, "camt": 1000.00, "samt": 1000.00, "csamt": 0.0}
                },
                "itc_net": {
                    "iamt": 0.0,
                    "camt": 5000.00,  # Should be 4000 (5000 - 1000)
                    "samt": 4000.00,
                    "csamt": 0.0
                }
            }
        }
        res = GSTPayloadValidator.validate_gstr3b_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_CALC_ITC_NET_INCONSISTENT", err_codes)

    def test_gstr3b_negative_value_rejected(self):
        """Rejects negative values anywhere in Table 3.1 or Table 4 of GSTR-3B."""
        payload = {
            "gstin": "27AAACA1234A1Z5",
            "ret_period": "082026",
            "filing_typ": "GSTR3B",
            "sup_details": {
                "osup_det": {"txval": -1000.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0}
            }
        }
        res = GSTPayloadValidator.validate_gstr3b_payload(payload)
        self.assertFalse(res["is_valid"])
        err_codes = [i["error_code"] for i in res["issues"]]
        self.assertIn("GST_NEGATIVE_VALUE", err_codes)

    def test_gstr3b_section49_4_rcm_cash_isolation(self):
        """
        Verifies that Section 49(4) Reverse Charge liability from Table 3.1(d)
        is isolated into 100% cash payable and strictly excluded from ITC offset.
        """
        # Create Sales Voucher (Intrastate 18%)
        v_sales = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='SAL-EXP-01',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.party_registered_intra,
            total_amount=Decimal('118000.00'),
            buyer_gstin='27AAACT2727Q1ZW',
            buyer_state_code='27',
            status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_sales,
            product=self.prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('118000.00')
        )

        # Create Inward RCM Purchase Voucher (GTA Transport ₹20,000 @ 5%)
        v_rcm = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-RCM-01',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.vendor_vendor_rcm,
            total_amount=Decimal('20000.00'),
            is_reverse_charge=True,
            status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_rcm,
            product=self.prod_service,
            quantity=Decimal('1.00'),
            rate=Decimal('20000.00'),
            taxable_amount=Decimal('20000.00'),
            gst_rate=Decimal('5.00'),
            cgst_amount=Decimal('500.00'),
            sgst_amount=Decimal('500.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('20000.00')
        )

        # Create Regular Purchase with excess ITC (₹1,00,000 @ 18% -> ₹9,000 CGST + ₹9,000 SGST)
        v_pur = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-REG-01',
            voucher_date=date(2026, 8, 14),
            party_ledger=self.vendor_registered_regular,
            total_amount=Decimal('118000.00'),
            status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v_pur,
            product=self.prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('118000.00')
        )

        gstr3b_data = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_primary,
            return_period="082026"
        )

        # Outward tax is ₹9,000 CGST and ₹9,000 SGST.
        # Regular ITC is ₹9,000 CGST and ₹9,000 SGST.
        # Outward cash payable is 0.00!
        tax_payable = gstr3b_data["tax_payable"]
        outward_cash = tax_payable["breakdown"]["outward_tax_cash"]
        self.assertEqual(outward_cash["cgst"], 0.00)
        self.assertEqual(outward_cash["sgst"], 0.00)

        # RCM cash liability is ₹500 CGST and ₹500 SGST = ₹1,000 total.
        rcm_cash = tax_payable["breakdown"]["rcm_cash_liability"]
        self.assertEqual(rcm_cash["cgst"], 500.00)
        self.assertEqual(rcm_cash["sgst"], 500.00)
        self.assertEqual(rcm_cash["total"], 1000.00)

        # Total cash payable MUST equal ₹1,000 (RCM cannot be offset against ITC!)
        self.assertEqual(tax_payable["total"], 1000.00)

        # Verify official GSTR-3B JSON contains isup_rev in Table 3.1(d)
        official_3b = gstr3b_data["official_gstr3b_json"]
        isup_rev = official_3b["sup_details"]["isup_rev"]
        self.assertEqual(isup_rev["txval"], 20000.00)
        self.assertEqual(isup_rev["camt"], 500.00)
        self.assertEqual(isup_rev["samt"], 500.00)

    # =========================================================================
    # 3. Workspace Export Lifecycle, Drift Guard & Deterministic Checksum Tests
    # =========================================================================

    def test_workspace_export_json_and_sha256_checksum(self):
        """Verifies clean export to official JSON with deterministic SHA-256 hash."""
        # Create a single sale
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-CERT-01',
            voucher_date=date(2026, 8, 5),
            party_ledger=self.party_registered_intra,
            total_amount=Decimal('118000.00'),
            buyer_gstin='27AAACT2727Q1ZW',
            buyer_state_code='27',
            status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('118000.00')
        )

        ws = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082026'
        )
        GSTWorkspaceService.generate_draft(ws)

        export_res = GSTWorkspaceService.export_draft(ws, export_format='JSON')
        self.assertTrue(export_res["success"])
        self.assertEqual(export_res["format"], "JSON")
        self.assertEqual(export_res["conformance_standard"], "GSTN Offline Tool Schema v3.1.2")
        self.assertTrue(len(export_res["payload_hash"]) == 64)

        # Refresh workspace from DB
        ws.refresh_from_db()
        self.assertEqual(ws.status, 'EXPORTED')

        # Export reproducibility: repeated export yields IDENTICAL hash
        export_res_2 = GSTWorkspaceService.export_draft(ws, export_format='JSON')
        self.assertEqual(export_res["payload_hash"], export_res_2["payload_hash"])

    def test_workspace_export_drift_guard_aborts_on_voucher_change(self):
        """
        Drift Guard: If a voucher is modified after draft generation,
        export is rejected with drift_detected=True.
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-DRIFT-01',
            voucher_date=date(2026, 8, 6),
            party_ledger=self.party_registered_intra,
            total_amount=Decimal('118000.00'),
            buyer_gstin='27AAACT2727Q1ZW',
            buyer_state_code='27',
            status='POSTED',
            created_by=self.owner_user
        )
        itm = VoucherItem.objects.create(
            voucher=v,
            product=self.prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('118000.00')
        )

        ws = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082026'
        )
        GSTWorkspaceService.generate_draft(ws)
        self.assertFalse(ws.is_stale)

        # Mutate voucher line item (simulate concurrent accounting edit)
        itm.taxable_amount = Decimal('120000.00')
        itm.total_amount = Decimal('141600.00')
        itm.save()
        v.total_amount = Decimal('141600.00')
        v.save()

        # Attempt export
        export_res = GSTWorkspaceService.export_draft(ws, export_format='JSON')
        self.assertFalse(export_res["success"])
        self.assertTrue(export_res.get("drift_detected", False))
        self.assertIn("drifted", export_res.get("error", "").lower())

    def test_workspace_export_human_review_report(self):
        """Exports human-readable audit report with statutory declaration and accounting breakdown."""
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-REV-01',
            voucher_date=date(2026, 8, 8),
            party_ledger=self.party_registered_intra,
            total_amount=Decimal('118000.00'),
            buyer_gstin='27AAACT2727Q1ZW',
            buyer_state_code='27',
            status='POSTED',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('118000.00')
        )

        ws = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082026'
        )
        GSTWorkspaceService.generate_draft(ws)

        export_res = GSTWorkspaceService.export_draft(ws, export_format='REVIEW_REPORT')
        self.assertTrue(export_res["success"])
        self.assertEqual(export_res["format"], "REVIEW_REPORT")

        report = export_res["payload"]
        self.assertIn("title", report)
        self.assertIn("statutory_declaration", report)
        self.assertIn("CGST Act 2017", report["statutory_declaration"])
        self.assertEqual(report["header"]["gstin"], "27AAACA1234A1Z5")

    def test_double_entry_immutability_zero_accounting_mutations(self):
        """
        Double-Entry Invariant:
        Draft generation, validation, sign-off, and export MUST NEVER alter
        Vouchers, VoucherItems, or LedgerEntries.
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-IMMUTABLE-01',
            voucher_date=date(2026, 8, 20),
            party_ledger=self.party_registered_intra,
            total_amount=Decimal('118000.00'),
            buyer_gstin='27AAACT2727Q1ZW',
            buyer_state_code='27',
            status='POSTED',
            created_by=self.owner_user
        )
        itm = VoucherItem.objects.create(
            voucher=v,
            product=self.prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('100000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('9000.00'),
            sgst_amount=Decimal('9000.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('118000.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.party_registered_intra,
            debit_amount=Decimal('118000.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.led_sales,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('100000.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.led_output_cgst,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('9000.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.led_output_sgst,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('9000.00')
        )

        # Record counts & checksums before GST operations
        voucher_count_before = Voucher.objects.filter(company=self.company).count()
        item_count_before = VoucherItem.objects.filter(voucher__company=self.company).count()
        entry_count_before = LedgerEntry.objects.filter(company=self.company).count()

        # Run complete lifecycle: Get -> Draft -> Sign-Off -> Export
        ws = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082026'
        )
        GSTWorkspaceService.generate_draft(ws)
        GSTWorkspaceService.sign_off_draft(ws, user=self.ca_user)
        GSTWorkspaceService.export_draft(ws, export_format='JSON')

        # Verify exact counts after
        self.assertEqual(Voucher.objects.filter(company=self.company).count(), voucher_count_before)
        self.assertEqual(VoucherItem.objects.filter(voucher__company=self.company).count(), item_count_before)
        self.assertEqual(LedgerEntry.objects.filter(company=self.company).count(), entry_count_before)

        # Verify mathematical equilibrium
        entries = LedgerEntry.objects.filter(voucher=v)
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, total_cr)
        self.assertEqual(total_dr, Decimal('118000.00'))

    # =========================================================================
    # 4. API Endpoint & RBAC Verification Tests
    # =========================================================================

    def test_api_workspace_export_as_ca(self):
        """Authenticated CA user can export workspace via API."""
        ws = GSTWorkspaceService.get_or_create_workspace(
            company=self.company,
            registration=self.reg_primary,
            return_type='GSTR1',
            return_period='082026'
        )
        GSTWorkspaceService.generate_draft(ws)

        self.client.force_authenticate(user=self.ca_user)
        url = f"/api/v1/gst/workspace/{self.company.id}/export/"
        resp = self.client.post(url, {
            "period": "082026",
            "return_type": "GSTR1",
            "format": "JSON",
            "registration_id": str(self.reg_primary.id)
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get("success"))
        self.assertEqual(resp.data.get("format"), "JSON")
        self.assertTrue("payload" in resp.data)

    def test_api_workspace_export_viewer_forbidden(self):
        """Viewer role is forbidden from exporting return drafts."""
        self.client.force_authenticate(user=self.viewer_user)
        url = f"/api/v1/gst/workspace/{self.company.id}/export/"
        resp = self.client.post(url, {
            "period": "082026",
            "return_type": "GSTR1",
            "format": "JSON"
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_workspace_export_unauthenticated_rejected(self):
        """Unauthenticated requests are rejected with 401."""
        url = f"/api/v1/gst/workspace/{self.company.id}/export/"
        resp = self.client.post(url, {
            "period": "082026",
            "return_type": "GSTR1",
            "format": "JSON"
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_tenant_isolation_guard(self):
        """User from Company B cannot access or export Company A workspace."""
        self.client.force_authenticate(user=self.other_user)
        url = f"/api/v1/gst/workspace/{self.company.id}/export/"
        resp = self.client.post(url, {
            "period": "082026",
            "return_type": "GSTR1",
            "format": "JSON"
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

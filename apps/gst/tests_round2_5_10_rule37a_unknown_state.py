"""
SriLekh GST — Round 2.5.10 Rule 37A UNKNOWN-State Fail-Closed Remediation Test Suite.
Enforces P0 Statutory Invariants:
1. Absence of evidence must NEVER be interpreted as affirmative evidence of supplier non-filing.
2. UNKNOWN + False = UNKNOWN, never VERIFIED_NOT_FILED.
3. DATA_UNAVAILABLE, PENDING, UNKNOWN, null, and missing evidence NEVER establish supplier default.
4. Raw booleans (False / True) without independently validated evidence NEVER establish non-filing or filing.
5. Explicit VERIFIED_NOT_FILED strictly requires valid GSTIN, return period, timestamp, freshness, and evidence record.
6. Deadline checker and ITC trace services fail closed with no reversals or defaults when evidence is missing.

STRICT INVARIANT:
Runs ONLY against dedicated sandbox company:
Apex Belting & Industrial Store (Demo) (4e62863a-08f9-4e99-b0bd-64873acfdd33).
"""

import io
import json
import uuid
import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from django.contrib.auth import get_user_model

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product
from apps.gst.models import (
    GSTReportingAllocation,
    GSTR2BImport,
    GSTR2BRecord,
    SupplierGSTR3BFilingRecord,
)
from apps.gst.services.allocation_service import GSTAllocationService, quantize_amount
from apps.gst.services.rule37a_evidence_service import (
    Rule37AEvidenceService,
    compute_rule37a_evidence_hash,
)
from apps.gst.services.itc_trace_service import ITCTraceService

User = get_user_model()


class Rule37AUnknownStateTestCase(TestCase):
    SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
    EXPECTED_FINGERPRINT = '6f4741bdaaf4'

    def setUp(self):
        # 1. Mandatory Environment and Isolation Invariant Check (Fail-Closed)
        from django.conf import settings
        assert connection.vendor == 'postgresql', (
            f"ABORT: Staging integration test strictly requires PostgreSQL. Found vendor '{connection.vendor}'."
        )
        raw_db_name = connection.settings_dict.get('NAME') or settings.DATABASES['default']['NAME']
        base_db_name = raw_db_name[5:] if raw_db_name.startswith('test_') else raw_db_name
        db_host = settings.DATABASES['default'].get('HOST', '')
        computed_fp = hashlib.sha256(f"{db_host}:{base_db_name}".encode()).hexdigest()[:12]

        is_neon_staging = (base_db_name == 'neondb_staging' and computed_fp == self.EXPECTED_FINGERPRINT)
        is_ci_staging = (base_db_name == 'neondb_ci_staging' and ('127.0.0.1' in db_host or 'localhost' in db_host))

        assert is_neon_staging or is_ci_staging, (
            f"ABORT: Test running on unauthorized database '{base_db_name}' with fingerprint '{computed_fp}' on host '{db_host}'! "
            f"Expected neondb_staging ({self.EXPECTED_FINGERPRINT}) or local CI test container."
        )

        self.company = Company.objects.filter(id=self.SANDBOX_COMPANY_ID).first()
        if not self.company:
            self.company = Company.objects.create(
                id=self.SANDBOX_COMPANY_ID,
                name="Apex Belting & Industrial Store (Demo)",
                gstin="27AABCU9603R1ZM"
            )
        assert str(self.company.id) == self.SANDBOX_COMPANY_ID, "ABORT: Isolation breach!"

        self.user, _ = User.objects.get_or_create(
            email="auditor_r2510@apexbelting.demo",
            defaults={"role": "OWNER", "is_staff": True, "is_active": True}
        )

        # Ledgers Setup
        grp_asset, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Current Assets",
            defaults={"nature": "ASSET"}
        )
        grp_liab, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sundry Creditors",
            defaults={"nature": "LIABILITY"}
        )
        grp_exp, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Direct Expenses",
            defaults={"nature": "EXPENSE"}
        )

        self.supplier_gstin = "27AAECK1234F1Z5"
        self.creditor_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Kalyan Belting Suppliers",
            defaults={"group": grp_liab, "gstin": self.supplier_gstin}
        )
        self.creditor_ledger.gstin = self.supplier_gstin
        self.creditor_ledger.save()

        self.purchase_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Raw Material Purchases",
            defaults={"group": grp_exp}
        )
        self.cgst_input, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="CGST Input",
            defaults={"group": grp_asset}
        )
        self.sgst_input, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="SGST Input",
            defaults={"group": grp_asset}
        )

        self.product, _ = Product.objects.get_or_create(
            company=self.company,
            sku="R2510-BELT-01",
            defaults={
                "name": "High Tensile Conveyor Belt R2510",
                "hsn_code": "40101200",
                "gst_rate": Decimal('18.00'),
                "unit": "MTR",
                "purchase_price": Decimal('1000.00'),
                "selling_price": Decimal('1500.00')
            }
        )

        # Invoice Date in FY 2025-26 (May 2025 -> Return Period 052025)
        self.inv_date = date(2025, 5, 10)
        self.inv_period = "052025"
        self.eval_date = date(2026, 10, 15) # Past 30-Sep-2026 default date!

        # Purchase Voucher with availed ITC
        self.voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number=f"VOUCH-R2510-{uuid.uuid4().hex[:6].upper()}",
            voucher_date=self.inv_date,
            party_ledger=self.creditor_ledger,
            total_amount=Decimal('59000.00'),
            created_by=self.user,
            status='POSTED'
        )

        VoucherItem.objects.create(
            voucher=self.voucher,
            product=self.product,
            quantity=Decimal('50.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('50000.00'),
            gst_rate=Decimal('18.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('4500.00'),
            sgst_amount=Decimal('4500.00'),
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_amount=Decimal('59000.00')
        )

        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.purchase_ledger,
            debit_amount=Decimal('50000.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.cgst_input,
            debit_amount=Decimal('4500.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.sgst_input,
            debit_amount=Decimal('4500.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.creditor_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('59000.00')
        )

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin
        ).delete()

        self.initial_inward = GSTReportingAllocation.objects.create(
            idempotency_key=f"inward_r2510_{self.voucher.id}_{self.inv_period}",
            company=self.company,
            voucher=self.voucher,
            event_type='INWARD_ITC',
            voucher_date=self.inv_date,
            entry_date=self.inv_date,
            original_period=self.inv_period,
            assigned_period=self.inv_period,
            financial_year='2025-26',
            total_tax=Decimal('9000.00'),
            cgst_amount=Decimal('4500.00'),
            sgst_amount=Decimal('4500.00'),
            status='APPROVED',
            is_statutorily_eligible=True,
            is_receipt_confirmed=True,
            goods_received_date=self.inv_date
        )

    # -------------------------------------------------------------------------
    # R25910-01: Resolver returns UNKNOWN and False; evaluator receives both values -> Remains UNKNOWN
    # -------------------------------------------------------------------------
    def test_r25910_01_resolver_unknown_false_evaluator_remains_unknown(self):
        """When resolver returns UNKNOWN and supplier_gstr3b_filed=False, evaluator must remain UNKNOWN."""
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'UNKNOWN')
        self.assertFalse(ev_res["supplier_gstr3b_filed"])
        self.assertEqual(ev_res["evidence_source"], 'NONE')

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_gstr3b_filed=ev_res["supplier_gstr3b_filed"],
            supplier_filing_date=ev_res["filing_date"],
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"]
        )

        self.assertEqual(st["supplier_status"], 'UNKNOWN')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])
        self.assertFalse(st["is_reversal_overdue"])
        self.assertFalse(st["interest_applicable"])
        self.assertEqual(st["default_reason"], 'Supplier status UNKNOWN. Verification required.')

    # -------------------------------------------------------------------------
    # R25910-02: No evidence exists and statutory default date has passed -> No supplier default
    # -------------------------------------------------------------------------
    def test_r25910_02_no_evidence_past_statutory_default_date_no_default(self):
        """Absence of evidence past 30-Sep default date must NOT establish supplier default."""
        # 2026-10-15 is 15 days past 30-Sep-2026 default date
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='UNKNOWN'
        )
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])
        self.assertEqual(st["supplier_status"], 'UNKNOWN')

    # -------------------------------------------------------------------------
    # R25910-03: No evidence exists and reversal evaluation is requested -> Reversal not permitted
    # -------------------------------------------------------------------------
    def test_r25910_03_no_evidence_reversal_not_permitted(self):
        """Attempting to create Rule 37A reversal when no evidence exists must be rejected."""
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'UNKNOWN')

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.eval_date,
                supplier_status=ev_res["status"],
                supplier_gstin=ev_res["supplier_gstin"],
                supplier_return_period=ev_res["return_period"],
                evidence_source=ev_res["evidence_source"],
                verification_timestamp=ev_res["verification_timestamp"],
                evidence_record=ev_res["evidence_record"],
                user=self.user
            )
        err_msg = str(ctx.exception)
        self.assertTrue("UNKNOWN" in err_msg or "verification timestamp" in err_msg)

        # Explicitly testing rejection of UNKNOWN status when timestamp is provided
        with self.assertRaises(ValidationError) as ctx2:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.eval_date,
                supplier_status='UNKNOWN',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='GSTN_PORTAL',
                verification_timestamp=timezone.now(),
                user=self.user
            )
        self.assertIn("UNKNOWN", str(ctx2.exception))

    # -------------------------------------------------------------------------
    # R25910-04: Explicit UNKNOWN with boolean False -> No conversion to VERIFIED_NOT_FILED
    # -------------------------------------------------------------------------
    def test_r25910_04_explicit_unknown_with_boolean_false_no_conversion(self):
        """Explicit UNKNOWN status with supplier_gstr3b_filed=False must never convert to VERIFIED_NOT_FILED."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='UNKNOWN',
            supplier_gstr3b_filed=False
        )
        self.assertEqual(st["supplier_status"], 'UNKNOWN')
        self.assertNotEqual(st["supplier_status"], 'VERIFIED_NOT_FILED')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])

    # -------------------------------------------------------------------------
    # R25910-05: Explicit DATA_UNAVAILABLE with boolean False -> No supplier default
    # -------------------------------------------------------------------------
    def test_r25910_05_explicit_data_unavailable_with_boolean_false_no_default(self):
        """DATA_UNAVAILABLE with boolean False must never establish supplier default."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='DATA_UNAVAILABLE',
            supplier_gstr3b_filed=False
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])
        self.assertIn("DATA_UNAVAILABLE", st["default_reason"])

    # -------------------------------------------------------------------------
    # R25910-06: Explicit PENDING with boolean False -> No supplier default
    # -------------------------------------------------------------------------
    def test_r25910_06_explicit_pending_with_boolean_false_no_default(self):
        """PENDING verification with boolean False must never establish supplier default."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='PENDING',
            supplier_gstr3b_filed=False
        )
        self.assertEqual(st["supplier_status"], 'PENDING')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])
        self.assertIn("PENDING", st["default_reason"])

    # -------------------------------------------------------------------------
    # R25910-07: Null boolean and UNKNOWN status -> No supplier default
    # -------------------------------------------------------------------------
    def test_r25910_07_null_boolean_and_unknown_status_no_default(self):
        """Null boolean (None) and UNKNOWN status must result in UNKNOWN with no supplier default."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='UNKNOWN',
            supplier_gstr3b_filed=None
        )
        self.assertEqual(st["supplier_status"], 'UNKNOWN')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])

    # -------------------------------------------------------------------------
    # R25910-08: Explicit VERIFIED_NOT_FILED with valid fresh evidence -> Validated pathway functional
    # -------------------------------------------------------------------------
    def test_r25910_08_explicit_verified_not_filed_with_valid_fresh_evidence_functional(self):
        """Explicit fresh VERIFIED_NOT_FILED record triggers valid default and allows compliant reversal."""
        rec_time = timezone.now() - timedelta(days=2)
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED',
            verified_at=rec_time,
            verification_source='GSTN_PORTAL',
            arn='',
            notes="Authoritative GSTN non-filing report"
        )

        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'VERIFIED_NOT_FILED')
        self.assertFalse(ev_res["is_stale"])
        self.assertEqual(ev_res["evidence_record"], rec)

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"],
            verification_timestamp=ev_res["verification_timestamp"]
        )
        self.assertEqual(st["supplier_status"], 'VERIFIED_NOT_FILED')
        self.assertTrue(st["is_supplier_default"])
        self.assertTrue(st["reversal_required"])

        # Reversal creation succeeds with valid evidence record
        rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            reversal_date=self.eval_date,
            supplier_status=ev_res["status"],
            supplier_gstin=ev_res["supplier_gstin"],
            supplier_return_period=ev_res["return_period"],
            evidence_source=ev_res["evidence_source"],
            verification_timestamp=ev_res["verification_timestamp"],
            evidence_record=ev_res["evidence_record"],
            user=self.user
        )
        self.assertIsNotNone(rev.id)
        self.assertEqual(rev.event_type, 'ITC_REVERSAL_RULE_37A')

    # -------------------------------------------------------------------------
    # R25910-09: Explicit VERIFIED_FILED with valid evidence -> Validated pathway functional
    # -------------------------------------------------------------------------
    def test_r25910_09_explicit_verified_filed_with_valid_evidence_functional(self):
        """Explicit VERIFIED_FILED record with ARN and timely filing date confirms compliance."""
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            filing_date=date(2025, 6, 20),
            arn="AA2706250000001",
            verified_at=timezone.now(),
            verification_source='GSTN_PORTAL'
        )

        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'VERIFIED_FILED')
        self.assertTrue(ev_res["supplier_gstr3b_filed"])
        self.assertEqual(ev_res["arn"], "AA2706250000001")

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_gstr3b_filed=ev_res["supplier_gstr3b_filed"],
            supplier_filing_date=ev_res["filing_date"],
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"]
        )
        self.assertEqual(st["supplier_status"], 'VERIFIED_FILED')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])

    # -------------------------------------------------------------------------
    # R25910-10: Wrong supplier GSTIN -> Evidence rejected
    # -------------------------------------------------------------------------
    def test_r25910_10_wrong_supplier_gstin_evidence_rejected(self):
        """Mismatched supplier GSTIN must convert evaluator status to DATA_UNAVAILABLE and reject reversal."""
        wrong_gstin = "07AAAAA0000A1Z5"
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=wrong_gstin,
            supplier_return_period=self.inv_period
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertIn("does not match invoice supplier GSTIN", st["default_reason"])

        # Creation must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.eval_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=wrong_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='GSTN_PORTAL',
                verification_timestamp=timezone.now(),
                user=self.user
            )
        self.assertIn("does not match invoice supplier GSTIN", str(ctx.exception))

    # -------------------------------------------------------------------------
    # R25910-11: Wrong return period -> Evidence rejected
    # -------------------------------------------------------------------------
    def test_r25910_11_wrong_return_period_evidence_rejected(self):
        """Mismatched return period must convert evaluator status to DATA_UNAVAILABLE and reject reversal."""
        wrong_period = "062025" # Voucher is 052025
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=wrong_period
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertIn("does not match invoice return period", st["default_reason"])

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.eval_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=wrong_period,
                evidence_source='GSTN_PORTAL',
                verification_timestamp=timezone.now(),
                user=self.user
            )
        self.assertIn("does not match invoice return period", str(ctx.exception))

    # -------------------------------------------------------------------------
    # R25910-12: Stale or missing verification timestamp -> Evidence rejected
    # -------------------------------------------------------------------------
    def test_r25910_12_stale_or_missing_verification_timestamp_evidence_rejected(self):
        """Stale or missing verification timestamp on negative evidence must be rejected."""
        # Case A: is_stale_evidence=True
        st_stale = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            is_stale_evidence=True
        )
        self.assertEqual(st_stale["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st_stale["is_supplier_default"])
        self.assertIn("stale", st_stale["default_reason"].lower())

        # Case B: verification_timestamp older than 30 days
        stale_ts = timezone.make_aware(datetime.combine(self.eval_date - timedelta(days=45), datetime.min.time()))
        st_ts_stale = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=stale_ts
        )
        self.assertEqual(st_ts_stale["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st_ts_stale["is_supplier_default"])
        self.assertIn("stale", st_ts_stale["default_reason"].lower())

        # Case C: validate_reversal_evidence requires timestamp
        with self.assertRaises(ValidationError) as ctx:
            Rule37AEvidenceService.validate_reversal_evidence(
                voucher=self.voucher,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='GSTN_PORTAL',
                verification_timestamp=None
            )
        self.assertIn("requires a verification timestamp", str(ctx.exception))

    # -------------------------------------------------------------------------
    # R25910-13: Deadline checker receives no evidence -> Must not create a reversal
    # -------------------------------------------------------------------------
    def test_r25910_13_deadline_checker_no_evidence_no_reversal_or_default(self):
        """Deadline checker command must not flag default or create reversals when evidence is missing."""
        out = io.StringIO()
        call_command(
            'check_gst_deadlines',
            company_id=self.SANDBOX_COMPANY_ID,
            as_of_date='2026-10-15',
            as_json=True,
            stdout=out
        )
        report = json.loads(out.getvalue())

        # Verify Rule 37A summary
        self.assertGreaterEqual(report["rule37a"]["evaluated"], 1)
        self.assertEqual(report["rule37a"]["verified_default_count"], 0)
        self.assertEqual(report["rule37a"]["overdue_count"], 0)
        self.assertEqual(report["rule37a"]["total_est_interest"], 0.0)

        # Confirm no findings were generated for Rule 37A
        matching_findings = [
            f for f in report["rule37a"]["findings"]
            if f.get("voucher_number") == self.voucher.voucher_number
        ]
        self.assertEqual(len(matching_findings), 0)

        # Confirm data_unavailable_count was incremented for UNKNOWN/DATA_UNAVAILABLE
        self.assertGreaterEqual(report["rule37a"]["data_unavailable_count"], 1)

    # -------------------------------------------------------------------------
    # R25910-14: API/service integration passes resolver output directly to evaluator
    # -------------------------------------------------------------------------
    def test_r25910_14_api_service_integration_passes_resolver_output_directly(self):
        """End-to-end service pipeline: resolver -> evaluator -> reversal guard."""
        # 1. Resolve evidence from empty store
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], "UNKNOWN")
        self.assertFalse(ev_res["supplier_gstr3b_filed"])

        # 2. Directly feed resolver output dictionary into evaluator
        eval_res = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_gstr3b_filed=ev_res["supplier_gstr3b_filed"],
            supplier_filing_date=ev_res["filing_date"],
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"],
            verification_timestamp=ev_res.get("verification_timestamp")
        )

        # 3. Assert fail-closed invariant is preserved end-to-end
        self.assertEqual(eval_res["supplier_status"], "UNKNOWN")
        self.assertFalse(eval_res["is_supplier_default"])
        self.assertFalse(eval_res["reversal_required"])
        self.assertFalse(eval_res["is_reversal_overdue"])
        self.assertFalse(eval_res["interest_applicable"])
        self.assertIsNone(eval_res["interest_details"])
        self.assertFalse(eval_res["reclaim_eligible"])

    # -------------------------------------------------------------------------
    # R25910-15: Boolean True with UNKNOWN status does not grant reclaim eligibility
    # -------------------------------------------------------------------------
    def test_r25910_15_boolean_true_with_unknown_status_never_establishes_filing(self):
        """A raw boolean True with UNKNOWN status must NEVER establish filing or reclaim eligibility."""
        # Setup an active reversal on this voucher to test reclaim guard
        rec_time = timezone.now() - timedelta(days=2)
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED',
            verified_at=rec_time,
            verification_source='GSTN_PORTAL'
        )
        rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            reversal_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_source='GSTN_PORTAL',
            verification_timestamp=rec_time,
            evidence_record=rec,
            user=self.user
        )
        self.assertIsNotNone(rev)

        # Now evaluate with UNKNOWN status and supplier_gstr3b_filed=True
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='UNKNOWN',
            supplier_gstr3b_filed=True
        )
        self.assertEqual(st["supplier_status"], 'UNKNOWN')
        # Invariant 5: A boolean True without independently validated filing evidence must never establish filing
        self.assertFalse(st["reclaim_eligible"])

    # -------------------------------------------------------------------------
    # R25910-16: Trace service integration with UNKNOWN status reports no default interest or reversal
    # -------------------------------------------------------------------------
    def test_r25910_16_trace_service_with_unknown_status_clean_lineage(self):
        """ITCTraceService on voucher with UNKNOWN evidence does not recommend reversal or accrue interest."""
        # Use an invoice within 180 days so Rule 37 payment condition is current
        self.voucher.voucher_date = timezone.now().date() - timedelta(days=20)
        self.voucher.save()

        trace = ITCTraceService.trace_invoice_itc_lifecycle(self.voucher)
        owner_view = trace["business_owner_view"]
        self.assertEqual(owner_view["headline"], "Pending Verification: Supplier GSTR-3B Evidence Unavailable")
        self.assertEqual(owner_view["risk_level"], "ATTENTION")
        self.assertEqual(owner_view["financials"]["estimated_interest"], Decimal('0.00'))
        self.assertTrue(any("Default cannot be presumed" in r for r in owner_view["actionable_recommendations"]))

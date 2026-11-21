"""
SriLekh GST — Round 2.5.11 Rule 37A Missing-Timestamp & Evidence-Provenance Fail-Closed Test Suite.

Mandatory Statutory & Technical Invariants:
1. For VERIFIED_NOT_FILED, a non-null, valid verification timestamp is strictly required.
2. If timestamp is missing (None), empty, malformed, timezone-invalid, future, or stale,
   effective status strictly fails closed to DATA_UNAVAILABLE (is_supplier_default = False).
3. Absence of a timestamp must NEVER establish supplier default, reversal requirement, or interest.
4. Evidence source must be valid; missing evidence source fails closed to DATA_UNAVAILABLE.
5. Supporting SupplierGSTR3BFilingRecord or GSTR2BRecord is required (or valid documented manual pathway).
6. check_gst_deadlines command and ITCTraceService must never produce false default warnings.
7. Reversal creation without timestamp raises ValidationError.
8. Valid VERIFIED_FILED and valid manual verification pathways remain fully functional.

STRICT ISOLATION POLICY:
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


class Rule37AMissingTimestampTestCase(TestCase):
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
            email="auditor_r2511@apexbelting.demo",
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

        self.supplier_gstin = "27AAACB2212R1Z1"
        self.party_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Continental Conveyor Belts Ltd (R2511)",
            defaults={
                "group": grp_liab,
                "gstin": self.supplier_gstin
            }
        )
        if self.party_ledger.gstin != self.supplier_gstin:
            self.party_ledger.gstin = self.supplier_gstin
            self.party_ledger.save()

        self.purchase_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Purchase Account (R2511)",
            defaults={
                "group": grp_exp
            }
        )
        self.cgst_input, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="CGST Input (R2511)",
            defaults={"group": grp_asset}
        )
        self.sgst_input, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="SGST Input (R2511)",
            defaults={"group": grp_asset}
        )

        self.product, _ = Product.objects.get_or_create(
            company=self.company,
            name="Industrial Conveyor Belt Type-C (R2511)",
            defaults={
                "sku": f"BELT-R2511-{uuid.uuid4().hex[:4].upper()}",
                "unit": "MTR",
                "hsn_code": "40101200",
                "gst_rate": Decimal('18.00')
            }
        )

        # Invoice dated 15-May-2025 -> FY 2025-26 -> Return Period 052025
        # Statutory supplier default date: 30-Sep-2026
        # Recipient reversal deadline: 30-Nov-2026
        self.invoice_date = date(2025, 5, 15)
        self.inv_period = "052025"
        self.eval_date = date(2026, 11, 20)  # Post 30-Sep default date

        self.voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number=f"VOUCH-R2511-{uuid.uuid4().hex[:6].upper()}",
            voucher_date=self.invoice_date,
            party_ledger=self.party_ledger,
            total_amount=Decimal('11800.00'),
            created_by=self.user,
            status='POSTED'
        )

        VoucherItem.objects.create(
            voucher=self.voucher,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00')
        )

        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.purchase_ledger,
            debit_amount=Decimal('10000.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.cgst_input,
            debit_amount=Decimal('900.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.sgst_input,
            debit_amount=Decimal('900.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=self.voucher,
            ledger=self.party_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('11800.00')
        )

        # Initial Inward Allocation
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=self.voucher,
            event_type='INWARD_ITC',
            voucher_date=self.invoice_date,
            entry_date=self.invoice_date,
            original_period=self.inv_period,
            assigned_period=self.inv_period,
            financial_year='2025-26',
            igst_amount=Decimal('0.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_tax=Decimal('1800.00'),
            status='APPROVED',
            is_statutorily_eligible=True,
            is_receipt_confirmed=True,
            is_active=True,
            idempotency_key=f"inward_r2511_{self.voucher.id}_{self.inv_period}"
        )

        # Clean any stray test filing records
        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin
        ).delete()
        GSTR2BRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin
        ).delete()

    # -------------------------------------------------------------------------
    # R25911-01: VERIFIED_NOT_FILED with timestamp=None -> DATA_UNAVAILABLE; no default
    # -------------------------------------------------------------------------
    def test_r25911_01_missing_timestamp_none_evaluates_to_data_unavailable_no_default(self):
        """VERIFIED_NOT_FILED with timestamp=None evaluated post 30-Sep must fail closed to DATA_UNAVAILABLE."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=None
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])
        self.assertFalse(st["is_reversal_overdue"])
        self.assertFalse(st["interest_applicable"])
        self.assertIn("missing", st["default_reason"].lower())

    # -------------------------------------------------------------------------
    # R25911-02: VERIFIED_NOT_FILED with empty timestamp string -> No default
    # -------------------------------------------------------------------------
    def test_r25911_02_empty_timestamp_string_evaluates_to_no_default(self):
        """VERIFIED_NOT_FILED with empty timestamp string must fail closed to DATA_UNAVAILABLE."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=""
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])

    # -------------------------------------------------------------------------
    # R25911-03: VERIFIED_NOT_FILED with malformed timestamp -> Safe validation failure
    # -------------------------------------------------------------------------
    def test_r25911_03_malformed_timestamp_safe_validation_failure_no_default(self):
        """Malformed timestamp string or invalid type must fail closed to DATA_UNAVAILABLE without crash."""
        st_str = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp="invalid-timestamp-string-here"
        )
        self.assertEqual(st_str["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st_str["is_supplier_default"])
        self.assertIn("malformed", st_str["default_reason"].lower())

        st_type = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=99999
        )
        self.assertEqual(st_type["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st_type["is_supplier_default"])

    # -------------------------------------------------------------------------
    # R25911-04: VERIFIED_NOT_FILED with future timestamp -> DATA_UNAVAILABLE; no default
    # -------------------------------------------------------------------------
    def test_r25911_04_future_timestamp_evaluates_to_data_unavailable_no_default(self):
        """Verification timestamp in the future must be rejected as invalid evidence."""
        future_ts = timezone.now() + timedelta(days=5)
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=future_ts
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertIn("future", st["default_reason"].lower())

    # -------------------------------------------------------------------------
    # R25911-05: VERIFIED_NOT_FILED with timestamp older than 30 days -> DATA_UNAVAILABLE
    # -------------------------------------------------------------------------
    def test_r25911_05_stale_timestamp_older_than_30_days_evaluates_to_data_unavailable(self):
        """Negative evidence verified >30 days ago is stale and cannot establish default."""
        stale_ts = timezone.make_aware(datetime.combine(self.eval_date - timedelta(days=40), datetime.min.time()))
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=stale_ts
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertIn("stale", st["default_reason"].lower())

    # -------------------------------------------------------------------------
    # R25911-06: VERIFIED_NOT_FILED with fresh timestamp and valid evidence provenance
    # -------------------------------------------------------------------------
    def test_r25911_06_verified_not_filed_fresh_timestamp_valid_provenance_functional(self):
        """Affirmative non-filing evidence with fresh timestamp and DB record correctly marks default."""
        fresh_ts = timezone.now() - timedelta(days=2)
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED',
            verified_at=fresh_ts,
            verification_source='GSTN_PORTAL',
            arn='',
            notes="Affirmative portal non-filing report"
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
            verification_timestamp=ev_res["verification_timestamp"],
            evidence_source=ev_res["evidence_source"],
            evidence_record=ev_res["evidence_record"]
        )
        self.assertEqual(st["supplier_status"], 'VERIFIED_NOT_FILED')
        self.assertTrue(st["is_supplier_default"])
        self.assertTrue(st["reversal_required"])

    # -------------------------------------------------------------------------
    # R25911-07: Missing evidence source with otherwise valid-looking status -> No default
    # -------------------------------------------------------------------------
    def test_r25911_07_missing_evidence_source_evaluates_to_no_default(self):
        """Calling evaluator with VERIFIED_NOT_FILED but missing evidence source fails closed."""
        fresh_ts = timezone.now() - timedelta(days=1)
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=fresh_ts,
            evidence_source=None
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertIn("source", st["default_reason"].lower())

    # -------------------------------------------------------------------------
    # R25911-08: Missing evidence record where record is required -> No default
    # -------------------------------------------------------------------------
    def test_r25911_08_missing_evidence_record_where_record_required_evaluates_to_no_default(self):
        """Calling evaluator with PORTAL source but no backing record in DB fails closed."""
        fresh_ts = timezone.now() - timedelta(days=1)
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=fresh_ts,
            evidence_source='PORTAL',
            evidence_record=None
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])
        self.assertIn("missing or unverified", st["default_reason"].lower())

    # -------------------------------------------------------------------------
    # R25911-09: Resolver returns UNKNOWN and False -> No default
    # -------------------------------------------------------------------------
    def test_r25911_09_resolver_returns_unknown_and_false_evaluates_to_no_default(self):
        """Empty store resolution (UNKNOWN + False) passes to evaluator and remains UNKNOWN."""
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'UNKNOWN')
        self.assertFalse(ev_res["supplier_gstr3b_filed"])
        self.assertIsNone(ev_res["verification_timestamp"])

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"],
            verification_timestamp=ev_res["verification_timestamp"]
        )
        self.assertEqual(st["supplier_status"], 'UNKNOWN')
        self.assertFalse(st["is_supplier_default"])

    # -------------------------------------------------------------------------
    # R25911-10: Deadline checker receives VERIFIED_NOT_FILED without timestamp -> No false warning
    # -------------------------------------------------------------------------
    def test_r25911_10_deadline_checker_no_timestamp_no_false_default_warning(self):
        """check_gst_deadlines command on voucher with missing timestamp generates 0 warnings/defaults."""
        out = io.StringIO()
        call_command(
            'check_gst_deadlines',
            company_id=self.SANDBOX_COMPANY_ID,
            as_of_date='2026-10-15',
            as_json=True,
            stdout=out
        )
        report = json.loads(out.getvalue())

        self.assertGreaterEqual(report["rule37a"]["evaluated"], 1)
        self.assertEqual(report["rule37a"]["verified_default_count"], 0)
        self.assertEqual(report["rule37a"]["overdue_count"], 0)
        self.assertEqual(report["rule37a"]["total_est_interest"], 0.0)

        matching_findings = [
            f for f in report["rule37a"]["findings"]
            if f.get("voucher_number") == self.voucher.voucher_number
        ]
        self.assertEqual(len(matching_findings), 0)

    # -------------------------------------------------------------------------
    # R25911-11: ITC trace receives missing-timestamp evidence -> Clean headline
    # -------------------------------------------------------------------------
    def test_r25911_11_itc_trace_receives_missing_timestamp_evidence_clean_headline(self):
        """ITCTraceService on voucher with missing evidence reports pending verification without reversal prompt."""
        # Use an invoice within 180 days so Rule 37 payment condition is current
        self.voucher.voucher_date = timezone.now().date() - timedelta(days=20)
        self.voucher.save()

        trace = ITCTraceService.trace_invoice_itc_lifecycle(self.voucher)
        headline = trace["business_owner_view"]["headline"]
        badge = trace["business_owner_view"]["status_badge"]

        self.assertNotEqual(headline, "At Risk: Supplier Did Not File GSTR-3B (Rule 37A)")
        self.assertEqual(headline, "Pending Verification: Supplier GSTR-3B Evidence Unavailable")
        self.assertEqual(badge, "PENDING_VERIFICATION")

    # -------------------------------------------------------------------------
    # R25911-12: Reversal creation receives missing timestamp -> ValidationError
    # -------------------------------------------------------------------------
    def test_r25911_12_reversal_creation_receives_missing_timestamp_raises_validation_error(self):
        """create_rule37a_reversal_allocation with verification_timestamp=None raises ValidationError."""
        initial_alloc_count = GSTReportingAllocation.objects.filter(
            voucher=self.voucher,
            event_type='ITC_REVERSAL_RULE_37A'
        ).count()

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.eval_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='GSTN_PORTAL',
                verification_timestamp=None,
                user=self.user
            )
        self.assertIn("requires a verification timestamp", str(ctx.exception))

        final_alloc_count = GSTReportingAllocation.objects.filter(
            voucher=self.voucher,
            event_type='ITC_REVERSAL_RULE_37A'
        ).count()
        self.assertEqual(initial_alloc_count, final_alloc_count)

    # -------------------------------------------------------------------------
    # R25911-13: Explicit valid manual verification pathway
    # -------------------------------------------------------------------------
    def test_r25911_13_explicit_valid_manual_verification_pathway(self):
        """Documented manual verification with documentary ref, reason, and user establishes valid default."""
        fresh_ts = timezone.now() - timedelta(days=2)

        # 1. Missing authorizer or reason fails closed
        st_invalid_manual = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=fresh_ts,
            evidence_source='MANUAL',
            evidence_document_ref='',
            manual_verification_reason='',
            user=None
        )
        self.assertEqual(st_invalid_manual["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st_invalid_manual["is_supplier_default"])

        # 2. Complete valid manual pathway succeeds
        st_valid_manual = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=fresh_ts,
            evidence_source='MANUAL',
            evidence_document_ref='CHALLAN-INSP-2026-99',
            manual_verification_reason='Notice issued under Sec 74; supplier confirmed non-payment in person',
            user=self.user
        )
        self.assertEqual(st_valid_manual["supplier_status"], 'VERIFIED_NOT_FILED')
        self.assertTrue(st_valid_manual["is_supplier_default"])
        self.assertTrue(st_valid_manual["reversal_required"])

    # -------------------------------------------------------------------------
    # R25911-14: Existing valid VERIFIED_FILED evidence -> Filing/reclaim behavior intact
    # -------------------------------------------------------------------------
    def test_r25911_14_existing_valid_verified_filed_evidence_reclaim_intact(self):
        """Valid VERIFIED_FILED record marks no default and enables reclaim when prior reversal exists."""
        # 1. Create prior reversal
        fresh_ts = timezone.now() - timedelta(days=2)
        rec_not_filed = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED',
            verified_at=fresh_ts,
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
            verification_timestamp=fresh_ts,
            evidence_record=rec_not_filed,
            user=self.user
        )
        self.assertIsNotNone(rev.id)

        # 2. Update record to VERIFIED_FILED with ARN and filing date
        rec_not_filed.status = 'VERIFIED_FILED'
        rec_not_filed.arn = 'AA270525000999Z'
        rec_not_filed.filing_date = date(2026, 8, 20)
        rec_not_filed.verified_at = timezone.now() - timedelta(days=1)
        rec_not_filed.save()

        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'VERIFIED_FILED')

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            supplier_filing_date=ev_res["filing_date"],
            is_stale_evidence=ev_res["is_stale"],
            verification_timestamp=ev_res["verification_timestamp"],
            evidence_source=ev_res["evidence_source"],
            evidence_record=ev_res["evidence_record"]
        )
        self.assertEqual(st["supplier_status"], 'VERIFIED_FILED')
        self.assertFalse(st["is_supplier_default"])
        self.assertTrue(st["reclaim_eligible"])

"""
SriLekh GST Engine — Round 2.5.7 Dedicated Test Suite
Payment-Event Idempotency, Supplier Evidence Certification, Section 50 Interest & Section 16 Decision Matrix.

Statutory Basis:
- CGST Act Section 16(2) Third Proviso & Rule 37(4) (Payment-Event Idempotency & Reclaim)
- CGST Act Section 16(2)(c) & Rule 37A (Supplier GSTR-3B Default & Affirmative Evidence)
- CGST Act Section 16(4), 16(5), 16(6) & Section 17(5) (ITC Eligibility Decision Matrix)
- CGST Act Section 50(1) (Leap-Year Precision & Statutory Safe Harbor)
- Multi-Tenant Isolation & Concurrency Safety
"""

import threading
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company
from apps.inventory.models import Product
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.gst.models import (
    GSTReportingAllocation,
    GSTRegistration,
    GSTReversalReclaimLineage,
    SupplierGSTR3BFilingRecord,
    GSTR2BRecord,
    GSTR2BImport,
    GSTReturnWorkspace,
)
from apps.gst.services.allocation_service import (
    GSTAllocationService,
    compute_payment_event_fingerprint,
    quantize_amount,
)
from apps.gst.services.itc_trace_service import ITCTraceService

SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
PROTECTED_PROD_COMPANY_ID = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'


class Round257PaymentAndEvidenceTests(TestCase):
    """
    Unit & Statutory Integration Tests for Round 2.5.7:
    Payment-event idempotency, supplier evidence lifecycle, Section 50 interest, and Section 16 decision table.
    """

    def setUp(self):
        # Mandatory Sandboxed Company Validation
        self.company, _ = Company.objects.get_or_create(
            id=SANDBOX_COMPANY_ID,
            defaults={
                'name': 'Apex Belting & Industrial Store (Demo)',
                'legal_name': 'Apex Belting Store',
                'gstin': '07AAAAA0000A1Z5',
                'is_active': True,
            }
        )
        assert str(self.company.id) == SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"

        self.owner_user, _ = User.objects.get_or_create(
            email='audit_r257@apexbelting.demo',
            defaults={'role': 'OWNER', 'is_active': True}
        )

        self.grp_liab, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Current Liabilities',
            defaults={'nature': 'LIABILITY'}
        )
        self.grp_exp, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Direct Expenses',
            defaults={'nature': 'EXPENSE'}
        )

        self.supplier_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Dynamic Rubber Industries Ltd',
            defaults={'group': self.grp_liab, 'gstin': '07ABCDE1234F1Z5'}
        )
        self.expense_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Raw Materials Purchase',
            defaults={'group': self.grp_exp}
        )

        self.product, _ = Product.objects.get_or_create(
            company=self.company,
            sku='BELT-IND-001',
            defaults={
                'name': 'Industrial Conveyor Belt',
                'unit': 'MTR',
                'purchase_price': Decimal('10000.00'),
                'selling_price': Decimal('12000.00'),
            }
        )

    def _create_purchase_voucher(self, number='INV-257-01', v_date=date(2026, 1, 10), taxable=Decimal('10000.00'), tax=Decimal('1800.00')):
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number=number,
            voucher_type='PURCHASE',
            voucher_date=v_date,
            party_ledger=self.supplier_ledger,
            status='POSTED',
            total_amount=taxable + tax
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=taxable,
            taxable_amount=taxable,
            gst_rate=Decimal('18.00'),
            igst_amount=tax
        )
        return v

    # =========================================================================
    # PART 1: PAYMENT-EVENT IDEMPOTENCY & CONFLICT VALIDATION (P0)
    # =========================================================================

    def test_identical_retry_returns_same_allocation_and_lineage(self):
        """
        Enforce: Exact identical payment event payload retry returns existing allocation (idempotent success).
        Verifies zero duplicate allocations and zero redundant lineages.
        """
        v = self._create_purchase_voucher('INV-IDEM-01', tax=Decimal('1800.00'))

        # Full reversal under Rule 37
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('11800.00'),
            assigned_period='072026',
            user=self.owner_user,
            reversal_date=date(2026, 7, 20)
        )

        # Initial Reclaim Call
        event_id = 'PE-2026-08-001'
        rec1 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            reclaim_date=date(2026, 8, 15),
            payment_event_id=event_id,
            payment_reference='UTR-999888'
        )

        self.assertIsNotNone(rec1.payment_fingerprint)
        self.assertEqual(len(rec1.payment_fingerprint), 64)

        # Identical Retry Call
        rec2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            reclaim_date=date(2026, 8, 15),
            payment_event_id=event_id,
            payment_reference='UTR-999888'
        )

        self.assertEqual(rec1.id, rec2.id)
        # Database verification: exactly 1 reclaim allocation and 1 lineage
        self.assertEqual(GSTReportingAllocation.objects.filter(voucher=v, event_type='ITC_RECLAIM').count(), 1)
        self.assertEqual(GSTReversalReclaimLineage.objects.filter(voucher=v).count(), 1)

    def test_conflict_amount_mismatch_on_same_event_id_raises_validation_error(self):
        """
        Enforce: Reusing payment_event_id with a different paid amount raises ValidationError.
        """
        v = self._create_purchase_voucher('INV-IDEM-02', tax=Decimal('1800.00'))
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.owner_user
        )

        event_id = 'PE-2026-08-002'
        GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id=event_id
        )

        # Retry with different amount (₹6,000 instead of ₹5,900)
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=v,
                paid_amount=Decimal('6000.00'),
                assigned_period='082026',
                user=self.owner_user,
                payment_event_id=event_id
            )
        self.assertIn("Payment-Event Idempotency Conflict", str(ctx.exception))
        self.assertIn("different fingerprint", str(ctx.exception))

    def test_conflict_cross_voucher_reuse_of_event_id_raises_validation_error(self):
        """
        Enforce: Reusing payment_event_id across different vouchers within the company raises ValidationError.
        """
        v1 = self._create_purchase_voucher('INV-IDEM-03A', tax=Decimal('1800.00'))
        v2 = self._create_purchase_voucher('INV-IDEM-03B', tax=Decimal('1800.00'))

        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v1, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.owner_user
        )
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v2, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.owner_user
        )

        event_id = 'PE-SHARED-003'
        GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v1,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id=event_id
        )

        # Attempt to use same event_id on v2
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=v2,
                paid_amount=Decimal('5900.00'),
                assigned_period='082026',
                user=self.owner_user,
                payment_event_id=event_id
            )
        self.assertIn("Payment-Event Idempotency Conflict", str(ctx.exception))
        self.assertIn("already registered against voucher", str(ctx.exception))

    def test_distinct_event_ids_with_identical_amounts_both_succeed(self):
        """
        Enforce: Legitimate sequential partial payments of identical amounts with distinct event IDs both succeed.
        """
        v = self._create_purchase_voucher('INV-IDEM-04', tax=Decimal('1800.00'))
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.owner_user
        )

        # Payment 1: ₹5,900
        rec1 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PE-PART-01',
            payment_reference='UTR-PART-1'
        )
        # Payment 2: ₹5,900 (Identical amount and period, distinct event ID)
        rec2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PE-PART-02',
            payment_reference='UTR-PART-2'
        )

        self.assertNotEqual(rec1.id, rec2.id)
        self.assertEqual(rec1.total_tax, Decimal('900.00'))
        self.assertEqual(rec2.total_tax, Decimal('900.00'))
        self.assertEqual(GSTReportingAllocation.objects.filter(voucher=v, event_type='ITC_RECLAIM').count(), 2)

    def test_missing_payment_event_id_prohibited_by_default(self):
        """
        Enforce: Reclaim without payment_event_id raises ValidationError unless allow_legacy_unidentified=True.
        """
        v = self._create_purchase_voucher('INV-IDEM-05', tax=Decimal('1800.00'))
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.owner_user
        )

        # Default: Prohibited
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=v,
                paid_amount=Decimal('5900.00'),
                assigned_period='082026',
                user=self.owner_user
            )
        self.assertIn("requires a stable source 'payment_event_id'", str(ctx.exception))

        # Explicit legacy fallback: Permitted
        rec_legacy = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            allow_legacy_unidentified=True
        )
        self.assertIsNotNone(rec_legacy.id)
        self.assertEqual(rec_legacy.total_tax, Decimal('900.00'))

    def test_supersede_payment_reclaim_allocation_workflow(self):
        """
        Enforce: Statutory correction workflow via supersede_payment_reclaim_allocation().
        Historical record is preserved with audit reason, reversal balance is restored,
        and subsequent corrected payment succeeds.
        """
        v = self._create_purchase_voucher('INV-IDEM-06', tax=Decimal('1800.00'))
        rev = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.owner_user
        )

        # 1. Erroneous Reclaim of full ₹1,800
        rec_err = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('11800.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PE-ERR-001'
        )
        self.assertEqual(rec_err.total_tax, Decimal('1800.00'))

        # Remaining reversed balance is now ₹0
        status_before = GSTAllocationService.evaluate_rule37_status(v, check_date=date(2026, 8, 20))
        self.assertEqual(status_before["remaining_reversed_tax"], Decimal('0.00'))

        # 2. Supersede Erroneous Reclaim
        rec_superseded = GSTAllocationService.supersede_payment_reclaim_allocation(
            allocation=rec_err,
            reason="Bank payment returned NSF / reversed by vendor",
            user=self.owner_user
        )
        self.assertFalse(rec_superseded.is_active)
        self.assertEqual(rec_superseded.status, 'SUPERSEDED')
        self.assertIsNotNone(rec_superseded.superseded_at)
        self.assertIn("NSF", rec_superseded.statutory_notes)

        # 3. Remaining reversed balance is restored to ₹1,800
        status_after = GSTAllocationService.evaluate_rule37_status(v, check_date=date(2026, 8, 20))
        self.assertEqual(status_after["remaining_reversed_tax"], Decimal('1800.00'))

        # 4. Corrected Payment with new event ID succeeds
        rec_corr = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='092026',
            user=self.owner_user,
            payment_event_id='PE-CORR-002'
        )
        self.assertTrue(rec_corr.is_active)
        self.assertEqual(rec_corr.total_tax, Decimal('900.00'))

    # =========================================================================
    # PART 2: SUPPLIER GSTR-3B EVIDENCE LIFECYCLE (P0)
    # =========================================================================

    def test_inconclusive_evidence_does_not_trigger_rule37a_default(self):
        """
        Enforce: DATA_UNAVAILABLE, PENDING, UNKNOWN must NEVER trigger supplier default.
        Reversal cannot be executed without affirmative VERIFIED_NOT_FILED evidence.
        """
        v = self._create_purchase_voucher('INV-SUPP-01', v_date=date(2025, 6, 15))

        # Check with DATA_UNAVAILABLE
        status_unavail = GSTAllocationService.evaluate_rule37a_status(
            voucher=v,
            check_date=date(2026, 10, 15),
            supplier_status='DATA_UNAVAILABLE'
        )
        self.assertFalse(status_unavail["is_supplier_default"])
        self.assertFalse(status_unavail["reversal_required"])
        self.assertIn("DATA_UNAVAILABLE", status_unavail["default_reason"])

        # Check with PENDING
        status_pending = GSTAllocationService.evaluate_rule37a_status(
            voucher=v,
            check_date=date(2026, 10, 15),
            supplier_status='PENDING'
        )
        self.assertFalse(status_pending["is_supplier_default"])
        self.assertFalse(status_pending["reversal_required"])

        # Attempt to create reversal with DATA_UNAVAILABLE must fail
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=v,
                assigned_period='102026',
                user=self.owner_user,
                supplier_status='DATA_UNAVAILABLE',
                supplier_gstin='07ABCDE1234F1Z5',
                supplier_return_period='062025',
                evidence_source='PORTAL',
                verification_timestamp=timezone.now(),
                reversal_date=date(2026, 10, 15)
            )
        self.assertIn("DATA_UNAVAILABLE", str(ctx.exception))

    def test_supplier_evidence_return_period_mismatch_blocks_reversal(self):
        """
        Enforce: Supplier evidence for period 082026 cannot be used to declare default for invoice dated 062025.
        """
        v = self._create_purchase_voucher('INV-SUPP-02', v_date=date(2025, 6, 15)) # Period 062025

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=v,
                assigned_period='102026',
                user=self.owner_user,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin='07ABCDE1234F1Z5',
                supplier_return_period='082025', # Mismatched return period
                evidence_source='PORTAL',
                verification_timestamp=timezone.now(),
                reversal_date=date(2026, 10, 15)
            )
        self.assertIn("does not match invoice return period", str(ctx.exception))

    def test_stale_supplier_evidence_blocks_rule37a_reversal(self):
        """
        Enforce: Stale supplier evidence (>30 days old) converts to DATA_UNAVAILABLE and blocks reversal.
        """
        v = self._create_purchase_voucher('INV-SUPP-03', v_date=date(2025, 6, 15))

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='07ABCDE1234F1Z5',
            return_period='062025',
            status='NOT_FILED'
        )
        SupplierGSTR3BFilingRecord.objects.filter(id=rec.id).update(verified_at=timezone.now() - timedelta(days=45))
        rec.refresh_from_db()
        self.assertTrue(rec.is_stale(threshold_days=30))

        # Reversal attempt with stale evidence must fail
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=v,
                assigned_period='102026',
                user=self.owner_user,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin='07ABCDE1234F1Z5',
                supplier_return_period='062025',
                is_stale_evidence=rec.is_stale(),
                evidence_source='PORTAL',
                evidence_record=rec,
                verification_timestamp=timezone.now(),
                reversal_date=date(2026, 10, 15)
            )
        self.assertIn("Supplier filing evidence is stale", str(ctx.exception))

    def test_rule37a_reversal_rejected_before_30_sep_statutory_default_date(self):
        """
        Enforce: Rule 37A reversal cannot be executed before 30th September following FY end,
        even if supplier has not filed GSTR-3B yet.
        """
        v = self._create_purchase_voucher('INV-SUPP-04', v_date=date(2025, 8, 10)) # FY 2025-26 -> Default date 30-Sep-2026

        # Attempt reversal on 15-Sep-2026 (before default date)
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=v,
                assigned_period='092026',
                user=self.owner_user,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin='07ABCDE1234F1Z5',
                supplier_return_period='082025',
                evidence_source='MANUAL',
                evidence_document_ref='DOC-REF-001',
                manual_verification_reason='Supplier confirmed in writing non-filing',
                verification_timestamp=timezone.now(),
                reversal_date=date(2026, 9, 15)
            )
        self.assertIn("Statutory default date (30-09-2026) has not been reached", str(ctx.exception))

        # Reversal on 15-Oct-2026 (after default date) succeeds
        rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='07ABCDE1234F1Z5',
            supplier_return_period='082025',
            evidence_source='MANUAL',
            evidence_document_ref='DOC-REF-001',
            manual_verification_reason='Supplier confirmed in writing non-filing',
            verification_timestamp=timezone.now(),
            reversal_date=date(2026, 10, 15)
        )
        self.assertEqual(rev.event_type, 'ITC_REVERSAL_RULE_37A')

    def test_rule37a_reclaim_requires_affirmative_arn_and_date(self):
        """
        Enforce: Rule 37A reclaim with VERIFIED_FILED requires valid ARN and filing date.
        """
        v = self._create_purchase_voucher('INV-SUPP-05', v_date=date(2025, 8, 10))
        rec_supp5 = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='07ABCDE1234F1Z5',
            return_period='082025',
            status='VERIFIED_NOT_FILED'
        )
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='07ABCDE1234F1Z5',
            supplier_return_period='082025',
            evidence_source='PORTAL',
            evidence_record=rec_supp5,
            verification_timestamp=timezone.now(),
            reversal_date=date(2026, 10, 15)
        )

        # Missing ARN
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period='122026',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                gstr3b_filing_date=date(2026, 12, 10)
            )
        self.assertIn("requires verified GSTR-3B filing Application Reference Number (ARN)", str(ctx.exception))

        # With ARN and date -> succeeds
        rec = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=v,
            assigned_period='122026',
            user=self.owner_user,
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA070826000099K',
            gstr3b_filing_date=date(2026, 12, 10)
        )
        self.assertEqual(rec.event_type, 'ITC_RECLAIM')
        self.assertEqual(rec.payment_reference, 'AA070826000099K')

    def test_gstr1_outward_declaration_cannot_satisfy_rule37a_reclaim(self):
        """
        Enforce: GSTR-1 outward date cannot be substituted for GSTR-3B tax payment.
        """
        v = self._create_purchase_voucher('INV-SUPP-06', v_date=date(2025, 8, 10))
        rec_supp6 = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='07ABCDE1234F1Z5',
            return_period='082025',
            status='VERIFIED_NOT_FILED'
        )
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='07ABCDE1234F1Z5',
            supplier_return_period='082025',
            evidence_source='PORTAL',
            evidence_record=rec_supp6,
            verification_timestamp=timezone.now(),
            reversal_date=date(2026, 10, 15)
        )

        batch = GSTR2BImport.objects.create(
            company=self.company,
            return_period='082025',
            file_name='gstr2b_test.json',
            uploaded_by=self.owner_user
        )
        GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            matched_voucher=v,
            supplier_gstin='07ABCDE1234F1Z5',
            invoice_number='INV-SUPP-06',
            invoice_date=date(2025, 8, 10),
            invoice_value=Decimal('11800.00'),
            taxable_value=Decimal('10000.00'),
            igst_amount=Decimal('1800.00'),
            gstr3b_return_period='082025',
            gstr1_filing_date=date(2025, 9, 10),
            gstr3b_filing_date=None # GSTR-3B NOT filed
        )

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period='122026',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED'
            )
        self.assertIn("Supplier has filed GSTR-1, but affirmative proof of GSTR-3B return filing", str(ctx.exception))

    def test_manually_confirmed_reclaim_audit_trail(self):
        """
        Enforce: MANUALLY_CONFIRMED reclaim requires document reference and records audit trail.
        """
        v = self._create_purchase_voucher('INV-SUPP-07', v_date=date(2025, 8, 10))
        rec_supp7 = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='07ABCDE1234F1Z5',
            return_period='082025',
            status='VERIFIED_NOT_FILED'
        )
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='07ABCDE1234F1Z5',
            supplier_return_period='082025',
            evidence_source='PORTAL',
            evidence_record=rec_supp7,
            verification_timestamp=timezone.now(),
            reversal_date=date(2026, 10, 15)
        )

        # Missing reference note fails
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period='122026',
                user=self.owner_user,
                supplier_status='MANUALLY_CONFIRMED',
                verification_reference=''
            )
        self.assertIn("requires document reference", str(ctx.exception))

        # With reference succeeds
        rec = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=v,
            assigned_period='122026',
            user=self.owner_user,
            supplier_status='MANUALLY_CONFIRMED',
            verification_reference='CA-CERT-2026-8889',
            verification_source='CA_CERTIFICATE',
            verification_timestamp=timezone.now()
        )
        self.assertEqual(rec.event_type, 'ITC_RECLAIM')
        self.assertIn("CA_CERTIFICATE", rec.statutory_notes)
        self.assertIn("CA-CERT-2026-8889", rec.statutory_notes)

    # =========================================================================
    # PART 3: SECTION 50 STATUTORY INTEREST VALIDATION (P1)
    # =========================================================================

    def test_section_50_leap_year_precision(self):
        """
        Enforce: Section 50 interest calculation precisely differentiates leap years (366 days in 2024)
        from standard years (365 days in 2025).
        """
        # Leap year 2024: 100 days delay on ₹100,000 tax @ 18% p.a.
        # Interest = (100000 * 18 * 100) / (100 * 366) = 1800000 / 366 = 4918.0327... -> ₹4,918.03
        calc_2024 = GSTAllocationService.calculate_section_50_interest(
            tax_amount=Decimal('100000.00'),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 10) # 100 days
        )
        self.assertEqual(calc_2024["days_delay"], 100)
        self.assertEqual(calc_2024["year_days"], 366)
        self.assertEqual(calc_2024["interest_amount"], Decimal('4918.03'))

        # Standard year 2025: 100 days delay on ₹100,000 tax @ 18% p.a.
        # Interest = (100000 * 18 * 100) / (100 * 365) = 1800000 / 365 = 4931.5068... -> ₹4,931.51
        calc_2025 = GSTAllocationService.calculate_section_50_interest(
            tax_amount=Decimal('100000.00'),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 4, 11) # 100 days
        )
        self.assertEqual(calc_2025["days_delay"], 100)
        self.assertEqual(calc_2025["year_days"], 365)
        self.assertEqual(calc_2025["interest_amount"], Decimal('4931.51'))

    def test_rule37a_safe_harbor_zero_interest_before_30_nov(self):
        """
        Enforce: Rule 37A safe harbor gives zero interest if reversed on or before 30-Nov following FY end.
        Reversal after 30-Nov attracts Section 50 interest.
        """
        v = self._create_purchase_voucher('INV-INT-01', v_date=date(2025, 6, 15), tax=Decimal('10000.00'))
        # FY 2025-26 -> Safe harbor deadline is 30-Nov-2026

        # Reversed on 20-Nov-2026 (Safe harbor)
        rec_safe = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='07ABCDE1234F1Z5',
            return_period='062025',
            status='VERIFIED_NOT_FILED'
        )
        rev_safe = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='112026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='07ABCDE1234F1Z5',
            supplier_return_period='062025',
            evidence_source='PORTAL',
            evidence_record=rec_safe,
            verification_timestamp=timezone.now(),
            reversal_date=date(2026, 11, 20)
        )
        self.assertNotIn("OVERDUE", rev_safe.statutory_notes)

        # Reversal after deadline on 20-Dec-2026 (20 days overdue)
        v2 = self._create_purchase_voucher('INV-INT-02', v_date=date(2025, 6, 15), tax=Decimal('10000.00'))
        rev_late = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v2,
            assigned_period='122026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='07ABCDE1234F1Z5',
            supplier_return_period='062025',
            evidence_source='PORTAL',
            evidence_record=rec_safe,
            verification_timestamp=timezone.now(),
            reversal_date=date(2026, 12, 20)
        )
        self.assertIn("OVERDUE (20 days past deadline 30-11-2026)", rev_late.statutory_notes)
        self.assertIn("Interest payable under Section 50", rev_late.statutory_notes)

    # =========================================================================
    # PART 4: SECTION 16 EVALUATOR DECISION-TABLE MATRIX (P1)
    # =========================================================================

    def test_section_16_decision_table_comprehensive(self):
        """
        Decision-Table Test Suite verifying all statutory conditions of Section 16 & 17.
        """
        # Case 1: Section 17(5) Blocked Credit
        v_blocked = self._create_purchase_voucher('INV-S16-01')
        v_blocked.is_section_17_5_blocked = True
        v_blocked.save()
        st_blocked = GSTAllocationService.evaluate_section_16_status(v_blocked)
        self.assertEqual(st_blocked["status"], "BLOCKED_SEC_17_5")
        self.assertEqual(st_blocked["category"], "PERMANENTLY_BLOCKED")
        self.assertFalse(st_blocked["is_eligible"])

        # Case 2: Section 16(2)(b) Receipt Pending
        v_unrec = self._create_purchase_voucher('INV-S16-02')
        GSTReportingAllocation.objects.create(
            company=self.company, voucher=v_unrec, event_type='INWARD_ITC',
            voucher_date=v_unrec.voucher_date, entry_date=v_unrec.voucher_date,
            assigned_period='012026', is_receipt_confirmed=False, is_active=True,
            idempotency_key=f"idem_unrec_{v_unrec.id}"
        )
        st_unrec = GSTAllocationService.evaluate_section_16_status(v_unrec)
        self.assertEqual(st_unrec["status"], "RECEIPT_PENDING")
        self.assertEqual(st_unrec["category"], "NOT_YET_ELIGIBLE")
        self.assertFalse(st_unrec["is_eligible"])

        # Case 3: First Proviso to Section 16(2) - Partial Receipt
        v_part = self._create_purchase_voucher('INV-S16-03')
        GSTReportingAllocation.objects.create(
            company=self.company, voucher=v_part, event_type='INWARD_ITC',
            voucher_date=v_part.voucher_date, entry_date=v_part.voucher_date,
            assigned_period='012026', is_receipt_confirmed=True,
            partial_received_fraction=Decimal('0.5000'), is_active=True,
            idempotency_key=f"idem_part_{v_part.id}"
        )
        st_part = GSTAllocationService.evaluate_section_16_status(v_part)
        self.assertEqual(st_part["status"], "PARTIAL_RECEIPT")
        self.assertEqual(st_part["category"], "PARTIALLY_ELIGIBLE")
        self.assertTrue(st_part["is_eligible"])

        # Case 4: Section 16(5) Finance Act 2024 Retrospective Relief (FY 2018-19)
        v_16_5 = self._create_purchase_voucher('INV-S16-04', v_date=date(2018, 10, 15))
        st_16_5 = GSTAllocationService.evaluate_section_16_status(v_16_5, check_date=date(2021, 11, 15))
        self.assertEqual(st_16_5["status"], "RELIEF_SEC_16_5")
        self.assertEqual(st_16_5["category"], "SPECIAL_STATUTORY_EXCEPTION")
        self.assertTrue(st_16_5["is_eligible"])

        # Case 5: Section 16(6) Revocation Extension
        v_16_6 = self._create_purchase_voucher('INV-S16-05', v_date=date(2025, 4, 10))
        revocation_order = date(2027, 2, 10)
        st_16_6 = GSTAllocationService.evaluate_section_16_status(
            v_16_6,
            check_date=date(2027, 2, 25),
            registration_revocation_date=revocation_order
        )
        self.assertEqual(st_16_6["status"], "RELIEF_SEC_16_6")
        self.assertEqual(st_16_6["category"], "SPECIAL_STATUTORY_EXCEPTION")
        self.assertTrue(st_16_6["is_eligible"])

        # Case 6: Section 16(4) Cutoff Exceeded (Time-Barred)
        v_barred = self._create_purchase_voucher('INV-S16-06', v_date=date(2024, 5, 10)) # FY 2024-25 -> Cutoff 30-Nov-2025
        st_barred = GSTAllocationService.evaluate_section_16_status(v_barred, check_date=date(2026, 1, 10))
        self.assertEqual(st_barred["status"], "STATUTE_BARRED_SEC_16_4")
        self.assertEqual(st_barred["category"], "TIME_BARRED")
        self.assertFalse(st_barred["is_eligible"])


class Round257ConcurrencyAndIsolationTests(TransactionTestCase):
    """
    Tests P1: Concurrency Protection on Payment Events & Strict Multi-Tenant Isolation.
    """

    def setUp(self):
        self.company, _ = Company.objects.get_or_create(
            id=SANDBOX_COMPANY_ID,
            defaults={
                'name': 'Apex Belting & Industrial Store (Demo)',
                'legal_name': 'Apex Belting Store',
                'gstin': '07AAAAA0000A1Z5',
                'is_active': True,
            }
        )
        assert str(self.company.id) == SANDBOX_COMPANY_ID

        self.user, _ = User.objects.get_or_create(
            email='audit_conc_r257@apexbelting.demo',
            defaults={'role': 'OWNER', 'is_active': True}
        )

        self.grp_liab, _ = LedgerGroup.objects.get_or_create(
            company=self.company, name='Current Liabilities', defaults={'nature': 'LIABILITY'}
        )
        self.ledger_supplier, _ = Ledger.objects.get_or_create(
            company=self.company, name='Super Power Belts Ltd', defaults={'group': self.grp_liab}
        )
        self.product, _ = Product.objects.get_or_create(
            company=self.company, sku='CONC-BELT-257',
            defaults={'name': 'High Tension Belt', 'unit': 'NOS', 'purchase_price': Decimal('5000.00'), 'selling_price': Decimal('6000.00')}
        )

    def test_concurrent_duplicate_delivery_creates_exactly_one_allocation(self):
        """
        Concurrency Invariant:
        Simulates 2 concurrent threads simultaneously delivering the EXACT same payment event
        with identical payload for a Rule 37 reclaim.
        Result: Exactly ONE allocation is persisted, and exactly ONE lineage record is created.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_number='INV-CONC-DUPL-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v, product=self.product, quantity=Decimal('1.00'),
            rate=Decimal('10000.00'), taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'), igst_amount=Decimal('1800.00')
        )

        # Full reversal of ₹1,800
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.user
        )

        event_id = 'PE-CONC-DUPL-001'
        successes = []
        errors = []
        lock = threading.Lock()

        if connection.vendor == 'sqlite':
            # SQLite locks entire DB file on thread writes; test rapid atomic serialization
            for _ in range(2):
                try:
                    alloc = GSTAllocationService.create_rule37_reclaim_allocation(
                        voucher=v,
                        paid_amount=Decimal('5900.00'),
                        assigned_period='082026',
                        user=self.user,
                        payment_event_id=event_id,
                        reclaim_date=date(2026, 8, 15),
                        payment_reference='UTR-CONC-001'
                    )
                    successes.append(alloc.id)
                except Exception as e:
                    errors.append(str(e))
        else:
            def worker():
                from django.db import connection as conn
                conn.close()
                try:
                    alloc = GSTAllocationService.create_rule37_reclaim_allocation(
                        voucher=v,
                        paid_amount=Decimal('5900.00'),
                        assigned_period='082026',
                        user=self.user,
                        payment_event_id=event_id,
                        reclaim_date=date(2026, 8, 15),
                        payment_reference='UTR-CONC-001'
                    )
                    with lock:
                        successes.append(alloc.id)
                except Exception as e:
                    with lock:
                        errors.append(str(e))
                finally:
                    conn.close()

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Both threads either receive the exact same allocation ID or 1 succeeds and 1 gets clean error/return
        unique_alloc_ids = set(successes)
        self.assertEqual(len(unique_alloc_ids), 1)

        # Database Invariant Check: Exactly 1 active allocation and 1 lineage record
        reclaims = GSTReportingAllocation.objects.filter(voucher=v, event_type='ITC_RECLAIM', is_active=True)
        self.assertEqual(reclaims.count(), 1)
        self.assertEqual(reclaims.first().payment_event_id, event_id)

        lineages = GSTReversalReclaimLineage.objects.filter(voucher=v)
        self.assertEqual(lineages.count(), 1)
        self.assertEqual(lineages.first().reclaimed_tax, Decimal('900.00'))

    def test_protected_production_tenant_isolation(self):
        """
        Enforce Strict Project Policy: Under NO circumstances may any test touch the protected
        production tenant (Maa Annapurna Belting Store: 5d2e5dea-ff86-4871-b2af-fe1c5a05c03c).
        """
        assert str(self.company.id) == SANDBOX_COMPANY_ID

        # Query production tenant: MUST NOT have any allocations created by test suite
        prod_allocations = GSTReportingAllocation.objects.filter(company_id=PROTECTED_PROD_COMPANY_ID)
        self.assertEqual(prod_allocations.count(), 0)

        # Cross-company payment_event_id isolation:
        # A payment_event_id in sandbox company cannot block the same event_id in another company
        other_company = Company.objects.create(
            name='Separate Sandbox Tenant Ltd',
            legal_name='Separate Sandbox Tenant',
            gstin='08BBBBB0000B1Z6'
        )
        v_other = Voucher.objects.create(
            company=other_company,
            created_by=self.user,
            voucher_number='INV-OTHER-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=v_other, product=self.product, quantity=Decimal('1.00'),
            rate=Decimal('10000.00'), taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'), igst_amount=Decimal('1800.00')
        )
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v_other, unpaid_amount=Decimal('11800.00'), assigned_period='072026', user=self.user
        )

        # Using same event_id 'PE-CONC-DUPL-001' in other_company succeeds because constraint is tenant-scoped
        alloc_other = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v_other,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.user,
            payment_event_id='PE-CONC-DUPL-001'
        )
        self.assertEqual(alloc_other.company_id, other_company.id)
        self.assertEqual(alloc_other.payment_event_id, 'PE-CONC-DUPL-001')

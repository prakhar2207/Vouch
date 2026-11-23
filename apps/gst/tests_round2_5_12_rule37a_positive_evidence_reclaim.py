"""
SriLekh GST — Round 2.5.12 Regression Test Suite
Rule 37A Positive Filing Evidence, Reclaim Authorization & Provenance Integrity Tests

Statutory Framework:
- CGST Rules, 2017 — Proviso to Rule 37A (Reclaim upon supplier furnishing GSTR-3B)
- CGST Act, 2017 — Section 16(2)(c) (Mandatory tax payment/discharge proof)
- CGST Act, 2017 — Section 17(5) (Ineligible blocked credit permanence)

Mandatory Invariants Tested:
1. Reclaim eligibility requires independently validated positive filing evidence (never raw booleans or status strings).
2. Exact supplier GSTIN, tenant/company, and return period match is mandatory.
3. ARN and valid filing date are mandatory for portal/supplier records.
4. Manual confirmation requires verifier identity (user), documentary reference, reason, and timestamp.
5. Inactive, contradictory, or cross-tenant records fail closed.
6. Reversal-to-reclaim lineage and balance tracking prevent over-reclaim and double-reclaim.
7. Failed validation transactions cause zero database mutations.
8. Concurrent reclaim requests serialize cleanly with zero double-reclaims.
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import threading
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounting.models import Voucher, VoucherItem
from apps.companies.models import Company, UserCompany
from apps.gst.models import (
    GSTR2BImport,
    GSTR2BRecord,
    GSTReportingAllocation,
    GSTReversalReclaimLineage,
    SupplierGSTR3BFilingRecord,
)
from apps.gst.services.allocation_service import GSTAllocationService
from apps.gst.services.rule37a_evidence_service import Rule37AEvidenceService
from apps.inventory.models import Product
from apps.ledgers.models import LedgerGroup, Ledger

User = get_user_model()


class Rule37ABaseTestCase:
    """Base setup shared between transactional and non-transactional test classes."""

    def setup_common_fixtures(self):
        engine = connection.settings_dict.get('ENGINE', '')
        if 'postgresql' not in engine:
            self.skipTest(f"Round 2.5.12 tests require PostgreSQL backend (current: {engine})")

        # Mandatory Tenant Isolation Policy
        self.SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
        self.company = Company.objects.filter(id=self.SANDBOX_COMPANY_ID).first()
        if not self.company:
            self.company = Company.objects.create(
                id=self.SANDBOX_COMPANY_ID,
                name="Apex Belting & Industrial Store (Demo)",
                gstin="27AABCU9603R1ZM"
            )
        assert str(self.company.id) == self.SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
        assert str(self.company.id) != '5d2e5dea-fe86-4871-b2af-fe1c5a05c03c', "SECURITY VIOLATION: Protected production tenant accessed!"

        # Dedicated isolated test user
        self.user, _ = User.objects.get_or_create(
            email='auditor_r25912@apexbelting.demo',
            defaults={'role': 'OWNER', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user, company=self.company, defaults={'role': 'OWNER'})

        # Isolated Ledgers
        self.group_creditors, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Sundry Creditors (R25912)',
            defaults={'nature': 'LIABILITY'}
        )

        self.supplier_gstin = '27AAAAA0000A1Z5'
        self.ledger_vendor, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Test Supplier R25912 Industrial Corp',
            defaults={
                'group': self.group_creditors,
                'gstin': self.supplier_gstin
            }
        )
        if self.ledger_vendor.gstin != self.supplier_gstin:
            self.ledger_vendor.gstin = self.supplier_gstin
            self.ledger_vendor.save()

        self.product, _ = Product.objects.get_or_create(
            company=self.company,
            name='Industrial Timing Belt B-50',
            defaults={'sku': 'BELT-R25912-B50', 'hsn_code': '40103990', 'unit': 'NOS', 'gst_rate': Decimal('18.00')}
        )

        # Standard Test Invoice (May 2025 inward supply, FY 2025-26)
        self.invoice_date = date(2025, 5, 15)
        self.inv_period = '052025'
        self.eval_date = date(2026, 11, 20)  # Post-September statutory evaluation date

        self.voucher = Voucher.objects.create(
            company=self.company,
            voucher_number=f"INV-R25912-{uuid.uuid4().hex[:6].upper()}",
            voucher_type='PURCHASE',
            voucher_date=self.invoice_date,
            party_ledger=self.ledger_vendor,
            total_amount=Decimal('11800.00'),
            created_by=self.user,
            status='POSTED'
        )

        self.v_item = VoucherItem.objects.create(
            voucher=self.voucher,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00')
        )

        # Inward ITC allocation
        self.alloc_inward = GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=self.voucher,
            event_type='INWARD_ITC',
            voucher_date=self.invoice_date,
            entry_date=self.invoice_date,
            original_period=self.inv_period,
            assigned_period=self.inv_period,
            financial_year='2025-26',
            allocation_reason='REGULAR',
            status='APPROVED',
            is_statutorily_eligible=True,
            is_receipt_confirmed=True,
            taxable_value=Decimal('10000.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_tax=Decimal('1800.00'),
            is_active=True,
            idempotency_key=f"inward_r25912_{self.voucher.id}"
        )

        self.g2b_import, _ = GSTR2BImport.objects.get_or_create(
            company=self.company,
            return_period=self.inv_period,
            defaults={
                'financial_year': '2025-26',
                'file_name': 'test_g2b_r25912.json',
                'file_format': 'JSON',
                'uploaded_by': self.user
            }
        )

    def _create_reversal_fixture(self, voucher=None, amount=Decimal('1800.00')):
        """Helper to create a valid prior Rule 37A reversal allocation."""
        v = voucher or self.voucher
        supp_rec, _ = SupplierGSTR3BFilingRecord.objects.get_or_create(
            company=v.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_NOT_FILED',
                'verified_at': timezone.now() - timedelta(days=2),
                'verification_source': 'PORTAL'
            }
        )
        if supp_rec.status != 'VERIFIED_NOT_FILED':
            supp_rec.status = 'VERIFIED_NOT_FILED'
            supp_rec.verified_at = timezone.now() - timedelta(days=2)
            supp_rec.save()

        rev, _ = GSTReportingAllocation.objects.get_or_create(
            company=v.company,
            voucher=v,
            event_type='ITC_REVERSAL_RULE_37A',
            assigned_period='102026',
            defaults={
                'created_by': self.user,
                'entry_date': date(2026, 10, 20),
                'voucher_date': v.voucher_date,
                'original_period': self.inv_period,
                'financial_year': '2025-26',
                'status': 'APPROVED',
                'is_active': True,
                'taxable_value': Decimal('10000.00'),
                'cgst_amount': Decimal('900.00'),
                'sgst_amount': Decimal('900.00'),
                'total_tax': amount,
                'evidence_source': 'PORTAL',
                'evidence_status': 'VERIFIED_NOT_FILED',
                'evidence_supplier_gstin': self.supplier_gstin,
                'evidence_return_period': self.inv_period,
                'evidence_verified_at': timezone.now() - timedelta(days=2),
                'idempotency_key': f"rule37a_rev_{v.company.id}_{v.id}_102026"
            }
        )
        return rev, supp_rec


class Rule37APositiveEvidenceReclaimTestCase(TestCase, Rule37ABaseTestCase):
    """
    Dedicated test suite for Round 2.5.12:
    Validates positive filing evidence contracts, reclaim authorization,
    lineage tracking, and statutory fail-closed invariants under Rule 37A.
    """

    def setUp(self):
        super().setUp()
        self.setup_common_fixtures()

    # =========================================================================
    # NEGATIVE TESTS (R25912-01 to R25912-20, except R25912-17)
    # =========================================================================

    def test_r25912_01_raw_verified_filed_string_without_evidence_record_rejected(self):
        """R25912-01: Raw 'VERIFIED_FILED' string without evidence record is rejected."""
        self._create_reversal_fixture()

        # 1. Evaluator rejects raw status string
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_FILED',
            evidence_record=None
        )
        self.assertFalse(st["reclaim_eligible"])
        self.assertIn("requires a verified, persisted evidence record", st["reclaim_ineligible_reason"])

        # 2. Reclaim creation rejects raw status string
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=None
            )
        self.assertIn("requires a verified, persisted evidence record", str(cm.exception))

    def test_r25912_02_raw_manually_confirmed_without_manual_proof_rejected(self):
        """R25912-02: Raw 'MANUALLY_CONFIRMED' without documentary reference & user is rejected."""
        self._create_reversal_fixture()

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='MANUALLY_CONFIRMED'
        )
        self.assertFalse(st["reclaim_eligible"])

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                user=None,
                verification_reference=''
            )
        self.assertIn("document reference", str(cm.exception))

    def test_r25912_03_supplier_gstr3b_filed_boolean_without_evidence_rejected(self):
        """R25912-03: supplier_gstr3b_filed=True without evidence is rejected."""
        self._create_reversal_fixture()

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_gstr3b_filed=True,
            supplier_status='UNKNOWN'
        )
        self.assertFalse(st["reclaim_eligible"])

    def test_r25912_04_missing_arn_where_required_rejected(self):
        """R25912-04: Positive filing evidence with missing ARN is rejected."""
        self._create_reversal_fixture()

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='27AAAAA0000A1Z9',
            return_period='072025',
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='',  # Missing ARN
            verified_at=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=rec
            )
        self.assertIn("Application Reference Number (ARN)", str(cm.exception))

    def test_r25912_05_missing_filing_date_rejected(self):
        """R25912-05: Positive filing evidence with missing filing date is rejected."""
        self._create_reversal_fixture()

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='27AAAAA0000A1Z8',
            return_period='082025',
            status='VERIFIED_FILED',
            filing_date=None,  # Missing filing date
            arn='AA271126000001B',
            verified_at=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=rec
            )
        self.assertIn("filing date", str(cm.exception))

    def test_r25912_06_supplier_gstin_mismatch_rejected(self):
        """R25912-06: Supplier GSTIN mismatch between invoice and evidence is rejected."""
        self._create_reversal_fixture()

        other_gstin = '27BBBBB1111B1Z2'
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=other_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000002C',
            verified_at=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                supplier_gstin=other_gstin,
                evidence_record=rec
            )
        self.assertIn("does not match invoice supplier GSTIN", str(cm.exception))

    def test_r25912_07_company_tenant_mismatch_rejected(self):
        """R25912-07: Cross-tenant evidence record is strictly rejected (tenant isolation)."""
        self._create_reversal_fixture()

        other_company = Company.objects.create(name='Demo Sandbox Tenant B')
        other_rec = SupplierGSTR3BFilingRecord.objects.create(
            company=other_company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000003D',
            verified_at=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=other_rec
            )
        self.assertIn("Cross-Tenant Evidence Violation", str(cm.exception))

    def test_r25912_08_return_period_mismatch_rejected(self):
        """R25912-08: Evidence return period mismatch is rejected."""
        self._create_reversal_fixture()

        mismatched_period = '062025'  # Invoice is 052025
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='27AAAAA0000A1Z7',
            return_period=mismatched_period,
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000004E',
            verified_at=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                supplier_return_period=mismatched_period,
                evidence_record=rec
            )
        self.assertIn("does not match invoice return period", str(cm.exception))

    def test_r25912_09_gstr1_filing_evidence_used_as_gstr3b_proof_rejected(self):
        """R25912-09: GSTR-1 outward date cannot prove GSTR-3B tax payment under Section 16(2)(c)."""
        self._create_reversal_fixture()

        g2b = GSTR2BRecord.objects.create(
            import_batch=self.g2b_import,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            supplier_name='Test Supplier',
            invoice_number=self.voucher.voucher_number,
            normalized_invoice_number=self.voucher.voucher_number.replace('-', ''),
            invoice_date=self.invoice_date,
            gstr3b_return_period=self.inv_period,
            gstr1_filing_date=date(2025, 6, 11),  # GSTR-1 filed
            gstr3b_filing_date=None,              # GSTR-3B NOT filed
            gstr3b_status='NOT_FILED'
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=g2b
            )
        self.assertIn("GSTR-1 outward declaration does not discharge tax liability", str(cm.exception))

    def test_r25912_10_gstr2b_statement_period_substituted_for_gstr3b_period_rejected(self):
        """R25912-10: Substituting GSTR-2B statement period for GSTR-3B return period is rejected."""
        self._create_reversal_fixture()

        batch_062025 = GSTR2BImport.objects.create(
            company=self.company,
            return_period='062025',
            financial_year='2025-26',
            file_name='test_batch_062025.json',
            file_format='JSON',
            uploaded_by=self.user
        )
        g2b = GSTR2BRecord.objects.create(
            import_batch=batch_062025,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            supplier_name='Test Supplier',
            invoice_number=self.voucher.voucher_number,
            normalized_invoice_number=self.voucher.voucher_number.replace('-', ''),
            invoice_date=self.invoice_date,
            gstr3b_return_period='072025', # Mismatched GSTR-3B period
            gstr3b_status='FILED',
            gstr3b_filing_date=date(2026, 11, 10),
            gstr3b_filing_arn='AA271126000005F'
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=g2b
            )
        self.assertIn("does not match invoice return period", str(cm.exception))

    def test_r25912_11_conflicting_positive_and_negative_evidence_rejected(self):
        """R25912-11: Contradictory evidence across sources fails closed (reclaim rejected)."""
        self._create_reversal_fixture()

        # Supplier record reports VERIFIED_FILED
        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000006G',
            verified_at=timezone.now()
        )

        # GSTR-2B simultaneously reports NOT_FILED
        GSTR2BRecord.objects.create(
            import_batch=self.g2b_import,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            supplier_name='Test Supplier',
            invoice_number=self.voucher.voucher_number,
            normalized_invoice_number=self.voucher.voucher_number.replace('-', ''),
            invoice_date=self.invoice_date,
            gstr3b_return_period=self.inv_period,
            gstr3b_status='NOT_FILED'
        )

        res = Rule37AEvidenceService.validate_positive_filing_evidence(
            voucher=self.voucher,
            supplier_status='VERIFIED_FILED',
            raise_exception=False
        )
        self.assertFalse(res.is_valid)
        self.assertIn("Conflicting positive and negative", res.validation_reason)

    def test_r25912_12_inactive_or_invalid_filing_record_rejected(self):
        """R25912-12: Record with non-positive status (e.g. VERIFIED_NOT_FILED) is rejected for reclaim."""
        self._create_reversal_fixture()

        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_NOT_FILED',
                evidence_record=rec
            )
        self.assertIn("does not establish tax payment", str(cm.exception))

    def test_r25912_13_reclaim_without_existing_reversal_rejected(self):
        """R25912-13: Reclaim attempt without prior active reversal raises ValidationError."""
        # Note: self._create_reversal_fixture is NOT called
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000007H',
            verified_at=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=rec
            )
        self.assertIn("No active prior Rule 37A reversal found", str(cm.exception))

    def test_r25912_14_reclaim_against_unrelated_vouchers_reversal_rejected(self):
        """R25912-14: Linking reclaim to an unrelated voucher's reversal is rejected."""
        rev_v1, _ = self._create_reversal_fixture()

        # Create second voucher v2
        v2 = Voucher.objects.create(
            company=self.company,
            voucher_number=f"INV-R25912-{uuid.uuid4().hex[:6].upper()}",
            voucher_type='PURCHASE',
            voucher_date=self.invoice_date,
            party_ledger=self.ledger_vendor,
            total_amount=Decimal('11800.00'),
            created_by=self.user,
            status='POSTED'
        )

        # Update existing supplier filing record for this voucher to VERIFIED_FILED
        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000008J',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        # Attempt to reclaim v2 using reversal from v1
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v2,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=rec,
                source_reversal_id=rev_v1.id
            )
        self.assertIn("not linked to invoice", str(cm.exception))

    def test_r25912_15_reclaim_exceeding_remaining_reversed_amount_rejected(self):
        """R25912-15: Reclaim amount exceeding available reversal balance is rejected."""
        rev, supp_rec = self._create_reversal_fixture()

        supp_rec.status = 'VERIFIED_FILED'
        supp_rec.filing_date = date(2026, 11, 10)
        supp_rec.arn = 'AA271126000009K'
        supp_rec.verified_at = timezone.now()
        supp_rec.save()

        # Attempt to reclaim ₹2000 when reversal is ₹1800
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=supp_rec,
                reclaim_tax=Decimal('2000.00')
            )
        self.assertIn("exceeds available reversal balance", str(cm.exception))

    def test_r25912_16_duplicate_reclaim_request_idempotency(self):
        """R25912-16: Duplicate identical reclaim request returns existing allocation (idempotent)."""
        self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000010L',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        rec1 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='VERIFIED_FILED',
            evidence_record=rec
        )

        # Duplicate request with idempotent=True returns rec1
        rec2 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='VERIFIED_FILED',
            evidence_record=rec,
            idempotent=True
        )

        self.assertEqual(rec1.id, rec2.id)
        # Database verification: exactly 1 reclaim allocation exists
        active_count = GSTReportingAllocation.objects.filter(
            voucher=self.voucher,
            event_type='ITC_RECLAIM',
            allocation_reason='RECLAIM_RULE_37A',
            is_active=True
        ).count()
        self.assertEqual(active_count, 1)

    def test_r25912_18_fully_reclaimed_reversal_rejects_additional_reclaims(self):
        """R25912-18: When prior reversal is already fully reclaimed, subsequent attempts fail."""
        self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000012N',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        # Full reclaim
        GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='VERIFIED_FILED',
            evidence_record=rec
        )

        # Attempt additional reclaim in period 012027
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='012027',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=rec
            )
        self.assertIn("already been fully reclaimed", str(cm.exception))

    def test_r25912_19_section_17_5_blocked_credit_reclaim_rejected(self):
        """R25912-19: Section 17(5) permanently ineligible credit is strictly barred from reclaim."""
        self._create_reversal_fixture()

        # Mark voucher blocked under Section 17(5)
        self.voucher.is_section_17_5_blocked = True
        self.voucher.save()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000013P',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='VERIFIED_FILED',
                evidence_record=rec
            )
        self.assertIn("Section 17(5) cannot be reclaimed", str(cm.exception))

    def test_r25912_20_failed_validation_causes_zero_database_mutation(self):
        """R25912-20: If positive evidence validation fails, transaction rolls back cleanly with 0 mutations."""
        self._create_reversal_fixture()

        count_allocations_before = GSTReportingAllocation.objects.count()
        count_lineages_before = GSTReversalReclaimLineage.objects.count()

        with self.assertRaises(ValidationError):
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.user,
                supplier_status='UNKNOWN'  # Invalid status
            )

        # Assert zero database mutations
        self.assertEqual(GSTReportingAllocation.objects.count(), count_allocations_before)
        self.assertEqual(GSTReversalReclaimLineage.objects.count(), count_lineages_before)

    # =========================================================================
    # POSITIVE TESTS (R25912-21 to R25912-28)
    # =========================================================================

    def test_r25912_21_valid_portal_filing_evidence_authorizes_reclaim(self):
        """R25912-21: Valid portal filing evidence successfully authorizes reclaim."""
        self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000014Q',
            verified_at=timezone.now(),
            verification_source='PORTAL'
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_record=rec
        )
        self.assertTrue(st["reclaim_eligible"])
        self.assertEqual(st["reclaimable_balance"], Decimal('1800.00'))

    def test_r25912_22_valid_supplier_filing_record_exact_gstin_period(self):
        """R25912-22: Valid SupplierGSTR3BFilingRecord with exact matching GSTIN and period creates reclaim."""
        self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 12),
            arn='AA271126000015R',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='VERIFIED_FILED',
            evidence_record=rec
        )
        self.assertEqual(reclaim.event_type, 'ITC_RECLAIM')
        self.assertEqual(reclaim.total_tax, Decimal('1800.00'))
        self.assertEqual(reclaim.evidence_arn, 'AA271126000015R')

    def test_r25912_23_valid_authorized_manual_evidence_authorizes_reclaim(self):
        """R25912-23: Documented manual confirmation by authorized user authorizes reclaim."""
        self._create_reversal_fixture()

        ev = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user,
            document_ref='CA-CERT-2026-999',
            reason='Verified vendor GST tax payment challan CIN 002938174628',
            verification_timestamp=timezone.now()
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=ev,
            user=self.user
        )

        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='MANUALLY_CONFIRMED',
            verification_reference='CA-CERT-2026-999',
            manual_verification_reason='Verified vendor GST tax payment challan CIN 002938174628',
            verification_timestamp=timezone.now()
        )
        self.assertEqual(reclaim.event_type, 'ITC_RECLAIM')
        self.assertEqual(reclaim.allocation_reason, 'RECLAIM_RULE_37A')
        self.assertEqual(reclaim.evidence_status, 'MANUALLY_CONFIRMED')
        self.assertEqual(reclaim.evidence_document_ref, 'CA-CERT-2026-999')

    def test_r25912_24_valid_partial_reclaim_calculates_correct_remaining_balance(self):
        """R25912-24: Partial reclaim properly prorates tax components and preserves remaining balance."""
        rev, _ = self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000016S',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        # Total reversal is ₹1800. Reclaim partial ₹1000
        rec_part = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='VERIFIED_FILED',
            evidence_record=rec,
            reclaim_tax=Decimal('1000.00')
        )
        self.assertEqual(rec_part.total_tax, Decimal('1000.00'))
        self.assertEqual(rec_part.cgst_amount + rec_part.sgst_amount, Decimal('1000.00'))

        # Remaining balance must be ₹800
        rem_balance = GSTAllocationService.get_rule37a_available_reversal_balance(self.voucher)
        self.assertEqual(rem_balance, Decimal('800.00'))

    def test_r25912_25_valid_full_reclaim_correct_lineage_and_zero_balance(self):
        """R25912-25: Full reclaim creates audit lineage and leaves zero remaining balance."""
        rev, _ = self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000017T',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.user,
            supplier_status='VERIFIED_FILED',
            evidence_record=rec
        )
        self.assertEqual(reclaim.total_tax, Decimal('1800.00'))

        # Verify lineage
        lineage = GSTReversalReclaimLineage.objects.get(
            reversal_allocation=rev,
            reclaim_allocation=reclaim
        )
        self.assertEqual(lineage.reclaimed_tax, Decimal('1800.00'))
        self.assertEqual(lineage.statutory_rule, 'RULE_37A')

        # Remaining balance is zero
        rem_balance = GSTAllocationService.get_rule37a_available_reversal_balance(self.voucher)
        self.assertEqual(rem_balance, Decimal('0.00'))

    def test_r25912_26_reversed_itc_followed_by_genuine_filing_becomes_eligible(self):
        """R25912-26: Reversal created on default date becomes reclaim eligible when supplier subsequently files."""
        rev, supp_rec = self._create_reversal_fixture()

        # Prior to filing: Reclaim is NOT eligible
        st_before = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            evidence_record=supp_rec
        )
        self.assertFalse(st_before["reclaim_eligible"])

        # Supplier files GSTR-3B with portal acknowledgment
        supp_rec.status = 'VERIFIED_FILED'
        supp_rec.filing_date = date(2026, 11, 18)
        supp_rec.arn = 'AA271126000018U'
        supp_rec.verified_at = timezone.now()
        supp_rec.save()

        # After filing: Reclaim becomes eligible
        st_after = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_FILED',
            evidence_record=supp_rec
        )
        self.assertTrue(st_after["reclaim_eligible"])
        self.assertEqual(st_after["reclaimable_balance"], Decimal('1800.00'))

    def test_r25912_27_existing_valid_historical_filing_record_without_artificial_expiry(self):
        """R25912-27: Historical positive filing record (>30 days old) remains valid without artificial expiry."""
        self._create_reversal_fixture()

        historical_ts = timezone.now() - timedelta(days=90)
        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 8, 15),
            arn='AA270826000019V',
            verified_at=historical_ts
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        res = Rule37AEvidenceService.validate_positive_filing_evidence(
            voucher=self.voucher,
            supplier_status='VERIFIED_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_record=rec,
            freshness_threshold_days=30
        )
        self.assertTrue(res.is_valid, f"Defect: Historical positive filing fact suffered artificial 30-day expiry! Reason: {res.validation_reason}")
        self.assertEqual(res.filing_arn, 'AA270826000019V')

    def test_r25912_28_repeated_evidence_resolution_deterministic_and_stable(self):
        """R25912-28: Repeated evidence resolution yields identical cryptographic hashes and stable provenance."""
        rec, _ = SupplierGSTR3BFilingRecord.objects.get_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 15),
                'arn': 'AA271126000020W',
                'verified_at': timezone.now()
            }
        )
        rec.status = 'VERIFIED_FILED'
        rec.filing_date = date(2026, 11, 15)
        rec.arn = 'AA271126000020W'
        rec.verified_at = timezone.now()
        rec.save()

        res1 = Rule37AEvidenceService.validate_positive_filing_evidence(
            voucher=self.voucher,
            supplier_status='VERIFIED_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_record=rec
        )
        res2 = Rule37AEvidenceService.validate_positive_filing_evidence(
            voucher=self.voucher,
            supplier_status='VERIFIED_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_record=rec
        )

        self.assertTrue(res1.is_valid, f"res1 invalid: {res1.validation_reason}")
        self.assertTrue(res2.is_valid, f"res2 invalid: {res2.validation_reason}")
        self.assertEqual(res1.evidence_hash, res2.evidence_hash)
        self.assertGreater(len(res1.evidence_hash), 0)


class Rule37AConcurrencyTestCase(TransactionTestCase, Rule37ABaseTestCase):
    """
    Dedicated concurrency test case running with TransactionTestCase
    to verify select_for_update row-level locking across worker threads.
    """

    def setUp(self):
        super().setUp()
        self.setup_common_fixtures()

    def test_r25912_17_concurrent_reclaim_attempts_serialized(self):
        """R25912-17: Concurrent reclaim requests serialize cleanly with select_for_update; no double-reclaim."""
        self._create_reversal_fixture()

        SupplierGSTR3BFilingRecord.objects.filter(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        ).update(
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000011M',
            verified_at=timezone.now()
        )
        rec = SupplierGSTR3BFilingRecord.objects.get(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period
        )

        successes = []
        errors = []

        def attempt_reclaim(period_str):
            try:
                alloc = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period=period_str,
                    user=self.user,
                    supplier_status='VERIFIED_FILED',
                    evidence_record=rec
                )
                successes.append(alloc)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_reclaim, args=('112026',))
        t2 = threading.Thread(target=attempt_reclaim, args=('122026',))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly 1 thread must succeed and 1 must fail with validation error
        self.assertEqual(len(successes), 1, f"Expected 1 success, got {len(successes)}: {successes}")
        self.assertEqual(len(errors), 1, f"Expected 1 error, got {len(errors)}: {errors}")

        active_reclaims = GSTReportingAllocation.objects.filter(
            voucher=self.voucher,
            event_type='ITC_RECLAIM',
            allocation_reason='RECLAIM_RULE_37A',
            is_active=True
        ).count()
        self.assertEqual(active_reclaims, 1)

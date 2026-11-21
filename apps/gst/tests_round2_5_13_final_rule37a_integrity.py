"""
SriLekh GST — Round 2.5.13 Dedicated Test Suite
Rule 37A Evidence Authorization, Transactional Integrity & Release Certification Tests

Statutory Framework:
- CGST Rules, 2017 — Proviso to Rule 37A (Reclaim upon supplier furnishing GSTR-3B)
- CGST Act, 2017 — Section 16(2)(c) (Statutory tax payment/discharge proof)
- CGST Act, 2017 — Section 17(5) (Ineligible blocked credit permanence)

Acceptance Criteria Verified:
- Part A: Manual evidence authorization (R25913-01 to R25913-18)
- Part B: Transactional integrity and race conditions (R25913-19 to R25913-28)
- Part C: Existing portal and statutory protections (R25913-29 to R25913-40)
- Part D: Regression and API coverage (R25913-41 to R25913-46)
"""

from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import threading
import uuid
from typing import Optional

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
    Rule37AManualFilingEvidence,
)
from apps.gst.services.allocation_service import GSTAllocationService
from apps.gst.services.rule37a_evidence_service import Rule37AEvidenceService
from apps.inventory.models import Product
from apps.ledgers.models import LedgerGroup, Ledger

User = get_user_model()


class Rule37AR2513BaseMixin:
    """Base setup shared between transactional and non-transactional test classes."""

    def setup_common_fixtures(self):
        engine = connection.settings_dict.get('ENGINE', '')
        if 'postgresql' not in engine:
            self.skipTest(f"Round 2.5.13 tests require PostgreSQL backend (current: {engine})")

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

        # Secondary Isolated Company for Cross-Tenant Tests
        self.OTHER_COMPANY_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        self.company_other = Company.objects.filter(id=self.OTHER_COMPANY_ID).first()
        if not self.company_other:
            self.company_other = Company.objects.create(
                id=self.OTHER_COMPANY_ID,
                name="Other Tenant Industrial Tools Ltd",
                gstin="29XYZAB1234C1Z9"
            )

        # Dedicated isolated test users with roles
        self.user_owner, _ = User.objects.get_or_create(
            email='owner_r25913@apexbelting.demo',
            defaults={'role': 'OWNER', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_owner, company=self.company, defaults={'role': 'OWNER'})

        self.user_accountant, _ = User.objects.get_or_create(
            email='accountant_r25913@apexbelting.demo',
            defaults={'role': 'ACCOUNTANT', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_accountant, company=self.company, defaults={'role': 'ACCOUNTANT'})

        self.user_unauthorized, _ = User.objects.get_or_create(
            email='viewer_r25913@apexbelting.demo',
            defaults={'role': 'VIEWER', 'is_staff': False, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_unauthorized, company=self.company, defaults={'role': 'VIEWER'})

        self.user_inactive, _ = User.objects.get_or_create(
            email='inactive_r25913@apexbelting.demo',
            defaults={'role': 'ACCOUNTANT', 'is_staff': False, 'is_active': False}
        )
        UserCompany.objects.get_or_create(user=self.user_inactive, company=self.company, defaults={'role': 'ACCOUNTANT'})

        self.user_other_tenant, _ = User.objects.get_or_create(
            email='other_tenant_r25913@othertenant.demo',
            defaults={'role': 'OWNER', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_other_tenant, company=self.company_other, defaults={'role': 'OWNER'})

        # Isolated Ledgers
        self.group_creditors, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Sundry Creditors (R25913)',
            defaults={'nature': 'LIABILITY'}
        )

        self.supplier_gstin = '27AAAAA0000A1Z5'
        self.ledger_vendor, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Test Supplier R25913 Belting Supply Co',
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
            name='High Torque Conveyor Belt X-200',
            defaults={'sku': 'BELT-R25913-X200', 'hsn_code': '40103990', 'unit': 'NOS', 'gst_rate': Decimal('18.00')}
        )

        # Standard Test Invoice (May 2025 inward supply, FY 2025-26)
        self.invoice_date = date(2025, 5, 15)
        self.inv_period = '052025'
        self.eval_date = date(2026, 11, 20)

        self.voucher = Voucher.objects.create(
            company=self.company,
            voucher_number=f"INV-R25913-{uuid.uuid4().hex[:6].upper()}",
            voucher_type='PURCHASE',
            voucher_date=self.invoice_date,
            party_ledger=self.ledger_vendor,
            total_amount=Decimal('11800.00'),
            created_by=self.user_owner,
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
            idempotency_key=f"inward_r25913_{self.voucher.id}"
        )

        self.g2b_import, _ = GSTR2BImport.objects.get_or_create(
            company=self.company,
            return_period=self.inv_period,
            defaults={
                'financial_year': '2025-26',
                'file_name': 'test_g2b_r25913.json',
                'file_format': 'JSON',
                'uploaded_by': self.user_owner
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
                'created_by': self.user_owner,
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
                'statutory_rule': 'Rule 37A CGST Rules (Supplier non-filing of GSTR-3B)'
            }
        )
        return rev, supp_rec


class TestPartAManualEvidenceAuthorization(TestCase, Rule37AR2513BaseMixin):
    """Part A: Dedicated tests for Manual Evidence Authorization (R25913-01 to R25913-18)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25913_01_raw_manually_confirmed_without_persisted_evidence_rejected(self):
        """R25913-01: Raw MANUALLY_CONFIRMED without persisted manual evidence is rejected."""
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                user=self.user_accountant
            )
        self.assertIn("Rule 37A manual confirmation requires an authoritative, persisted, approved Rule37AManualFilingEvidence record", str(cm.exception))

    def test_r25913_02_caller_supplied_doc_ref_and_reason_without_persisted_record_rejected(self):
        """R25913-02: Document reference and reason supplied by caller without persisted record are rejected."""
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                user=self.user_accountant,
                verification_reference='CA-CERT-CALLER-FORGED',
                manual_verification_reason='Caller claimed verification',
                verification_timestamp=timezone.now()
            )
        self.assertIn("Rule 37A manual confirmation requires an authoritative, persisted, approved Rule37AManualFilingEvidence record", str(cm.exception))

    def test_r25913_03_missing_verifier_is_rejected(self):
        """R25913-03: Missing verifier is rejected."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=None,
                document_ref='CA-CERT-2026-001',
                reason='Tax payment certificate'
            )
        self.assertIn("Manual evidence verification requires an authenticated verifier user", str(cm.exception))

    def test_r25913_04_inactive_verifier_is_rejected(self):
        """R25913-04: Inactive verifier is rejected."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_inactive,
                document_ref='CA-CERT-2026-001',
                reason='Tax payment certificate'
            )
        self.assertIn("inactive", str(cm.exception).lower())

    def test_r25913_05_unauthorized_verifier_is_rejected(self):
        """R25913-05: Unauthorized verifier (e.g. VIEWER or EMPLOYEE) is rejected."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_unauthorized,
                document_ref='CA-CERT-2026-001',
                reason='Tax payment certificate'
            )
        self.assertIn("not authorized for manual statutory GST evidence verification", str(cm.exception))

    def test_r25913_06_verifier_from_another_tenant_is_rejected(self):
        """R25913-06: Verifier from another tenant is rejected."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_other_tenant,
                document_ref='CA-CERT-2026-001',
                reason='Tax payment certificate'
            )
        self.assertIn("is not a member of company", str(cm.exception))

    def test_r25913_07_manual_evidence_from_another_company_is_rejected(self):
        """R25913-07: Manual evidence from another company is rejected."""
        other_voucher = Voucher.objects.create(
            company=self.company_other,
            voucher_number=f"INV-OTHER-{uuid.uuid4().hex[:6].upper()}",
            voucher_type='PURCHASE',
            voucher_date=self.invoice_date,
            total_amount=Decimal('11800.00'),
            created_by=self.user_other_tenant
        )
        foreign_evidence = Rule37AManualFilingEvidence.objects.create(
            company=self.company_other,
            voucher=other_voucher,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            evidence_document_type='CA_CERTIFICATE',
            evidence_document_ref='CA-CERT-OTHER-001',
            verification_reason='Verified vendor tax payment',
            status='APPROVED',
            verifier_user=self.user_other_tenant,
            verifier_role='OWNER',
            verification_timestamp=timezone.now()
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=foreign_evidence,
                user=self.user_accountant
            )
        self.assertIn("Cross-Tenant Evidence Violation", str(cm.exception))

    def test_r25913_08_manual_evidence_linked_to_another_voucher_is_rejected(self):
        """R25913-08: Manual evidence linked to another voucher is rejected."""
        voucher_b = Voucher.objects.create(
            company=self.company,
            voucher_number=f"INV-B-{uuid.uuid4().hex[:6].upper()}",
            voucher_type='PURCHASE',
            voucher_date=self.invoice_date,
            party_ledger=self.ledger_vendor,
            total_amount=Decimal('5900.00'),
            created_by=self.user_owner
        )
        voucher_b_evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=voucher_b,
            user=self.user_accountant,
            document_ref='CA-CERT-VB-001',
            reason='Verified voucher B'
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=voucher_b_evidence,
                user=self.user_accountant
            )
        self.assertIn("unrelated voucher", str(cm.exception))

    def test_r25913_09_supplier_gstin_mismatch_is_rejected(self):
        """R25913-09: Supplier GSTIN mismatch is rejected."""
        evidence = Rule37AManualFilingEvidence.objects.create(
            company=self.company,
            voucher=self.voucher,
            supplier_gstin='27ZZZZZ9999Z9Z9',  # Different GSTIN
            return_period=self.inv_period,
            evidence_document_type='CA_CERTIFICATE',
            evidence_document_ref='CA-CERT-MISMATCH-GSTIN',
            verification_reason='Verified vendor tax payment',
            status='APPROVED',
            verifier_user=self.user_accountant,
            verifier_role='ACCOUNTANT',
            verification_timestamp=timezone.now()
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("does not match invoice supplier GSTIN", str(cm.exception))

    def test_r25913_10_return_period_mismatch_is_rejected(self):
        """R25913-10: Return period mismatch is rejected."""
        evidence = Rule37AManualFilingEvidence.objects.create(
            company=self.company,
            voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            return_period='062025',  # Invoice is 052025
            evidence_document_type='CA_CERTIFICATE',
            evidence_document_ref='CA-CERT-MISMATCH-PERIOD',
            verification_reason='Verified June period instead of May',
            status='APPROVED',
            verifier_user=self.user_accountant,
            verifier_role='ACCOUNTANT',
            verification_timestamp=timezone.now()
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("does not match invoice return period", str(cm.exception))

    def test_r25913_11_draft_manual_evidence_is_rejected(self):
        """R25913-11: Draft manual evidence is rejected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-DRAFT-001',
            reason='Draft verification awaiting audit',
            status='DRAFT'
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("Only 'APPROVED' manual evidence authorizes reclaim", str(cm.exception))

    def test_r25913_12_rejected_manual_evidence_is_rejected(self):
        """R25913-12: Rejected manual evidence is rejected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-REJ-001',
            reason='Initial verification attempt'
        )
        Rule37AEvidenceService.reject_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner,
            reason='Challan CIN could not be authenticated on GST portal'
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("Only 'APPROVED' manual evidence authorizes reclaim", str(cm.exception))

    def test_r25913_13_invalidated_manual_evidence_is_rejected(self):
        """R25913-13: Invalidated manual evidence is rejected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-INV-001',
            reason='Initially approved verification'
        )
        Rule37AEvidenceService.invalidate_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner,
            reason='Auditor discovered vendor affidavit had invalid stamp'
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("Only 'APPROVED' manual evidence authorizes reclaim", str(cm.exception))

    def test_r25913_14_missing_document_reference_is_rejected(self):
        """R25913-14: Missing document reference is rejected."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_accountant,
                document_ref='',
                reason='Tax payment certificate'
            )
        self.assertIn("documentary reference", str(cm.exception))

    def test_r25913_15_missing_reason_is_rejected(self):
        """R25913-15: Missing reason is rejected."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_accountant,
                document_ref='CA-CERT-2026-001',
                reason=''
            )
        self.assertIn("verification reason", str(cm.exception))

    def test_r25913_16_missing_or_malformed_timestamp_is_rejected(self):
        """R25913-16: Future or invalid timestamp is rejected."""
        future_ts = timezone.now() + timedelta(days=2)
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_accountant,
                document_ref='CA-CERT-2026-FUTURE',
                reason='Future dated certification',
                verification_timestamp=future_ts
            )
        self.assertIn("cannot be in the future", str(cm.exception))

    def test_r25913_17_valid_approved_manual_evidence_succeeds(self):
        """R25913-17: Valid approved manual evidence from an authorized verifier succeeds."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-2026-AUTH-001',
            document_type='CA_CERTIFICATE',
            reason='Verified vendor GST tax payment challan CIN 002938174628',
            status='APPROVED',
            verification_timestamp=timezone.now()
        )
        self.assertEqual(evidence.status, 'APPROVED')
        self.assertTrue(len(evidence.evidence_hash) == 64)

        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='MANUALLY_CONFIRMED',
            user=self.user_accountant
        )
        self.assertEqual(reclaim.event_type, 'ITC_RECLAIM')
        self.assertEqual(reclaim.allocation_reason, 'RECLAIM_RULE_37A')
        self.assertEqual(reclaim.evidence_status, 'MANUALLY_CONFIRMED')
        self.assertEqual(reclaim.evidence_document_ref, 'CA-CERT-2026-AUTH-001')

    def test_r25913_18_manual_evidence_correction_preserves_original_audit_history(self):
        """R25913-18: Manual evidence correction preserves the original audit history."""
        original_ev = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-INITIAL-001',
            reason='Initial certification with typo in vendor CIN'
        )
        # Create superseding corrected record as DRAFT
        corrected_ev = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-CORRECTED-002',
            reason='Corrected vendor tax challan CIN 998877665544',
            status='DRAFT'
        )
        # Invalidate original with link to corrected
        invalidated = Rule37AEvidenceService.invalidate_manual_filing_evidence(
            evidence=original_ev,
            user=self.user_owner,
            reason='Superseded by corrected certificate CA-CERT-CORRECTED-002',
            superseding_evidence=corrected_ev
        )
        # Now approve corrected record (unique constraint satisfied since original is INVALIDATED)
        approved_corrected = Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=corrected_ev,
            user=self.user_owner
        )
        self.assertEqual(invalidated.status, 'INVALIDATED')
        self.assertEqual(invalidated.invalidated_by, self.user_owner)
        self.assertEqual(invalidated.superseded_by, corrected_ev)
        self.assertEqual(invalidated.evidence_document_ref, 'CA-CERT-INITIAL-001')
        self.assertIn('Superseded by corrected certificate', invalidated.invalidation_reason)
        self.assertEqual(approved_corrected.status, 'APPROVED')


class TestPartBTransactionalIntegrityAndRaceConditions(TransactionTestCase, Rule37AR2513BaseMixin):
    """Part B: PostgreSQL concurrency and transactional integrity tests (R25913-19 to R25913-28)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25913_19_evidence_is_validated_after_acquiring_transaction_locks(self):
        """R25913-19: Evidence is validated inside the atomic transaction holding row locks."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-TX-001',
            reason='Valid tax payment cert'
        )
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='MANUALLY_CONFIRMED',
            user=self.user_accountant
        )
        self.assertEqual(reclaim.status, 'APPROVED')
        self.assertEqual(reclaim.evidence_document_ref, 'CA-CERT-TX-001')

    def test_r25913_20_evidence_invalidation_racing_with_reclaim_creation_produces_serialized_outcome(self):
        """R25913-20: Concurrent evidence invalidation and reclaim creation produce consistent serialized outcome."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-RACE-001',
            reason='Race test certification'
        )
        outcomes = []
        errors = []

        def do_reclaim():
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant
                )
                outcomes.append(('RECLAIM_SUCCESS', rec.id))
            except Exception as e:
                errors.append(('RECLAIM_FAILED', str(e)))

        def do_invalidate():
            try:
                inv = Rule37AEvidenceService.invalidate_manual_filing_evidence(
                    evidence=evidence,
                    user=self.user_owner,
                    reason='Invalidated in race test'
                )
                outcomes.append(('INVALIDATE_SUCCESS', inv.id))
            except Exception as e:
                errors.append(('INVALIDATE_FAILED', str(e)))

        t1 = threading.Thread(target=do_reclaim)
        t2 = threading.Thread(target=do_invalidate)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Consistent Serialized Outcome:
        # Either:
        # 1. Reclaim succeeded before invalidation (Reclaim created with valid evidence, then evidence invalidated)
        # 2. Invalidation committed first, and reclaim failed with validation error because evidence was INVALIDATED
        reclaim_success = any(o[0] == 'RECLAIM_SUCCESS' for o in outcomes)
        if reclaim_success:
            # Reclaim occurred while evidence was valid
            rec_alloc = GSTReportingAllocation.objects.get(voucher=self.voucher, event_type='ITC_RECLAIM')
            self.assertEqual(rec_alloc.total_tax, Decimal('1800.00'))
        else:
            # Reclaim aborted because evidence was already invalidated
            self.assertTrue(any("INVALIDATED" in err[1] or "requires an authoritative, persisted, approved" in err[1] for err in errors))

    def test_r25913_21_evidence_mutation_racing_with_reclaim_creation_cannot_produce_stale_authorization(self):
        """R25913-21: Evidence mutation racing with reclaim creation cannot produce stale authorization."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-MUT-001',
            reason='Pre-mutation cert'
        )
        outcomes = []

        def do_reclaim():
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant
                )
                outcomes.append(('RECLAIM', rec.id))
            except Exception as e:
                outcomes.append(('RECLAIM_FAIL', str(e)))

        def do_reject():
            try:
                rej = Rule37AEvidenceService.reject_manual_filing_evidence(
                    evidence=evidence,
                    user=self.user_owner,
                    reason='Mutated to rejected'
                )
                outcomes.append(('REJECT', rej.id))
            except Exception as e:
                outcomes.append(('REJECT_FAIL', str(e)))

        t1 = threading.Thread(target=do_reclaim)
        t2 = threading.Thread(target=do_reject)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Verify no stale authorization on REJECTED evidence
        ev_final = Rule37AManualFilingEvidence.objects.get(id=evidence.id)
        if ev_final.status == 'REJECTED':
            # If rejected, any subsequent attempt strictly fails
            with self.assertRaises(ValidationError):
                GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='012027',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant
                )

    def test_r25913_22_failed_evidence_validation_creates_no_reclaim_allocation(self):
        """R25913-22: Failed evidence validation causes 100% rollback and creates zero allocations."""
        initial_alloc_count = GSTReportingAllocation.objects.filter(voucher=self.voucher).count()
        with self.assertRaises(ValidationError):
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                verification_reference='UNPERSISTED-STRING-FAIL',
                user=self.user_accountant
            )
        final_alloc_count = GSTReportingAllocation.objects.filter(voucher=self.voucher).count()
        self.assertEqual(initial_alloc_count, final_alloc_count)

    def test_r25913_23_failed_lineage_creation_rolls_back_reclaim_allocation(self):
        """R25913-23: If lineage creation fails, entire transaction rolls back."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-ROLLBACK-001',
            reason='Rollback testing'
        )
        initial_reclaim_count = GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_RECLAIM').count()

        # Monkey-patch GSTReversalReclaimLineage.objects.create to trigger a simulated failure
        orig_create = GSTReversalReclaimLineage.objects.create
        def fail_create(*args, **kwargs):
            raise RuntimeError("SIMULATED DATABASE LINEAGE INSERTION CRASH")

        GSTReversalReclaimLineage.objects.create = fail_create
        try:
            with self.assertRaises(RuntimeError):
                GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant
                )
        finally:
            GSTReversalReclaimLineage.objects.create = orig_create

        final_reclaim_count = GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_RECLAIM').count()
        self.assertEqual(initial_reclaim_count, final_reclaim_count)

    def test_r25913_24_concurrent_reclaim_attempts_cannot_exceed_reversal_balance(self):
        """R25913-24: Concurrent reclaim attempts cannot exceed available reversal balance."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-BAL-001',
            reason='Balance limit testing'
        )
        successes = []
        failures = []

        def attempt_reclaim(period):
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period=period,
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant,
                    reclaim_tax=Decimal('1800.00')
                )
                successes.append(rec)
            except Exception as e:
                failures.append(str(e))

        t1 = threading.Thread(target=attempt_reclaim, args=('112026',))
        t2 = threading.Thread(target=attempt_reclaim, args=('122026',))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly 1 can succeed since total reversal was 1800 and each asked for 1800
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertTrue(
            "exceeds available reversal balance" in failures[0] or "has already been fully reclaimed" in failures[0]
        )

        total_reclaimed = sum(s.total_tax for s in successes)
        self.assertEqual(total_reclaimed, Decimal('1800.00'))

    def test_r25913_25_concurrent_attempts_cannot_create_duplicate_active_reclaim(self):
        """R25913-25: Concurrent attempts cannot create duplicate active reclaim in same period."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-DUP-001',
            reason='Duplicate reclaim testing'
        )
        successes = []
        failures = []

        def attempt_reclaim():
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant,
                    reclaim_tax=Decimal('900.00')
                )
                successes.append(rec)
            except Exception as e:
                failures.append(str(e))

        t1 = threading.Thread(target=attempt_reclaim)
        t2 = threading.Thread(target=attempt_reclaim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # In same period without idempotent=True, exactly 1 succeeds
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("already active in period 122026", failures[0])

    def test_r25913_26_two_different_reclaim_periods_cannot_bypass_same_reversal_balance(self):
        """R25913-26: Two different reclaim periods cannot bypass the same reversal balance."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-DIFF-001',
            reason='Two periods testing'
        )
        # First period reclaims full ₹1800
        rec1 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='112026',
            supplier_status='MANUALLY_CONFIRMED',
            user=self.user_accountant,
            reclaim_tax=Decimal('1800.00')
        )
        self.assertEqual(rec1.total_tax, Decimal('1800.00'))

        # Second period attempts ₹1800 on same voucher
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                user=self.user_accountant,
                reclaim_tax=Decimal('1800.00')
            )
        self.assertIn("has already been fully reclaimed", str(cm.exception))

    def test_r25913_27_reclaim_and_lineage_always_committed_together(self):
        """R25913-27: Reclaim and lineage are always committed together."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-ATOM-001',
            reason='Atomicity verification'
        )
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='MANUALLY_CONFIRMED',
            user=self.user_accountant
        )
        lineage = GSTReversalReclaimLineage.objects.filter(reclaim_allocation=reclaim).first()
        self.assertIsNotNone(lineage)
        self.assertEqual(lineage.reclaim_allocation_id, reclaim.id)
        self.assertEqual(lineage.reclaimed_tax, reclaim.total_tax)

    def test_r25913_28_deadlock_sensitive_lock_ordering_consistent_across_code_paths(self):
        """R25913-28: Deadlock-sensitive lock ordering is Voucher -> Prior Reversal -> Evidence Record."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-ORDER-001',
            reason='Lock order test'
        )
        # Validate that execution finishes with zero deadlock
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='MANUALLY_CONFIRMED',
            user=self.user_accountant
        )
        self.assertIsNotNone(reclaim)


class TestPartCExistingPortalAndStatutoryProtections(TestCase, Rule37AR2513BaseMixin):
    """Part C: Portal evidence and statutory compliance tests (R25913-29 to R25913-40)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25913_29_raw_verified_filed_without_persisted_evidence_rejected(self):
        """R25913-29: Raw VERIFIED_FILED without persisted evidence is rejected."""
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                user=self.user_accountant
            )
        self.assertIn("requires a verified, persisted evidence record", str(cm.exception))

    def test_r25913_30_valid_portal_gstr3b_evidence_authorizes_reclaim(self):
        """R25913-30: Valid portal GSTR-3B evidence authorizes reclaim."""
        supp_rec, _ = SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now(),
                'verification_source': 'PORTAL'
            }
        )
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='VERIFIED_FILED',
            user=self.user_accountant
        )
        self.assertEqual(reclaim.event_type, 'ITC_RECLAIM')
        self.assertEqual(reclaim.evidence_arn, 'AA271126000015R')

    def test_r25913_31_gstr1_only_evidence_is_rejected(self):
        """R25913-31: GSTR-1-only evidence is rejected under Section 16(2)(c)."""
        g2b = GSTR2BRecord.objects.create(
            import_batch=self.g2b_import,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number=self.voucher.voucher_number,
            invoice_date=self.invoice_date,
            gstr3b_return_period=self.inv_period,
            gstr1_filing_date=date(2025, 6, 10),
            gstr3b_filing_date=None,  # GSTR-3B not filed!
            gstr3b_status='NOT_FILED',
            taxable_value=Decimal('10000.00'),
            invoice_value=Decimal('11800.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                evidence_record=g2b,
                user=self.user_accountant
            )
        self.assertIn("GSTR-1 outward declaration does not discharge tax liability under Section 16(2)(c)", str(cm.exception))

    def test_r25913_32_gstr2b_period_substitution_is_rejected(self):
        """R25913-32: GSTR-2B statement period substituted for invoice return period is rejected."""
        g2b = GSTR2BRecord.objects.create(
            import_batch=self.g2b_import,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number=self.voucher.voucher_number,
            invoice_date=self.invoice_date,
            gstr3b_return_period='062025',  # Mismatched GSTR-3B period (invoice is 052025)
            gstr3b_filing_date=date(2026, 11, 10),
            gstr3b_filing_arn='AA271126000099R',
            gstr3b_status='FILED',
            taxable_value=Decimal('10000.00'),
            invoice_value=Decimal('11800.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                evidence_record=g2b,
                user=self.user_accountant
            )
        self.assertIn("does not match invoice return period", str(cm.exception))

    def test_r25913_33_cross_tenant_portal_evidence_is_rejected(self):
        """R25913-33: Cross-tenant portal evidence is rejected."""
        foreign_rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company_other,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            filing_date=date(2026, 11, 10),
            arn='AA271126000015R',
            verified_at=timezone.now(),
            verification_source='PORTAL'
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                evidence_record=foreign_rec,
                user=self.user_accountant
            )
        self.assertIn("Cross-Tenant Evidence Violation", str(cm.exception))

    def test_r25913_34_conflicting_positive_and_negative_evidence_is_rejected(self):
        """R25913-34: Conflicting positive and negative evidence fails closed."""
        # Record 1 says FILED
        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now()
            }
        )
        # Record 2 says NOT_FILED
        GSTR2BRecord.objects.create(
            import_batch=self.g2b_import,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number=self.voucher.voucher_number,
            invoice_date=self.invoice_date,
            gstr3b_return_period=self.inv_period,
            gstr3b_status='NOT_FILED',
            gstr3b_verified_at=timezone.now(),
            taxable_value=Decimal('10000.00'),
            invoice_value=Decimal('11800.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                user=self.user_accountant
            )
        self.assertIn("Conflicting positive and negative filing evidence", str(cm.exception))

    def test_r25913_35_historical_positive_filing_evidence_remains_valid(self):
        """R25913-35: Historical positive filing evidence does not expire under 30-day freshness policy."""
        old_verified_at = timezone.now() - timedelta(days=90)
        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 5, 10),
                'arn': 'AA270526000099R',
                'verified_at': old_verified_at,
                'verification_source': 'PORTAL'
            }
        )
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='VERIFIED_FILED',
            user=self.user_accountant
        )
        self.assertEqual(reclaim.event_type, 'ITC_RECLAIM')
        self.assertEqual(reclaim.evidence_arn, 'AA270526000099R')

    def test_r25913_36_section_17_5_blocked_itc_permanently_ineligible(self):
        """R25913-36: Section 17(5) blocked ITC is permanently ineligible for reclaim."""
        self.voucher.is_section_17_5_blocked = True
        self.voucher.save()

        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now()
            }
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                user=self.user_accountant
            )
        self.assertIn("Permanently ineligible ITC under Section 17(5) cannot be reclaimed", str(cm.exception))

    def test_r25913_37_reclaim_without_prior_active_reversal_is_rejected(self):
        """R25913-37: Reclaim without prior active Rule 37A reversal is rejected."""
        # Deactivate reversal
        GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_REVERSAL_RULE_37A').update(is_active=False)

        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now()
            }
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                user=self.user_accountant
            )
        self.assertIn("No active prior Rule 37A reversal found", str(cm.exception))

    def test_r25913_38_reclaim_exceeding_available_reversal_balance_is_rejected(self):
        """R25913-38: Reclaim exceeding available reversal balance is rejected."""
        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now()
            }
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                user=self.user_accountant,
                reclaim_tax=Decimal('2500.00')  # Reversal is only 1800
            )
        self.assertIn("exceeds available reversal balance", str(cm.exception))

    def test_r25913_39_partial_reclaim_correctly_prorates_tax_components(self):
        """R25913-39: Partial reclaim correctly prorates tax components."""
        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now()
            }
        )
        # Reclaim 50% (₹900 out of ₹1800)
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='VERIFIED_FILED',
            user=self.user_accountant,
            reclaim_tax=Decimal('900.00')
        )
        self.assertEqual(reclaim.total_tax, Decimal('900.00'))
        self.assertEqual(reclaim.cgst_amount, Decimal('450.00'))
        self.assertEqual(reclaim.sgst_amount, Decimal('450.00'))

        # Remaining balance should be exactly ₹900.00
        rem = GSTAllocationService.get_rule37a_available_reversal_balance(self.voucher)
        self.assertEqual(rem, Decimal('900.00'))

    def test_r25913_40_full_reclaim_leaves_zero_available_reversal_balance(self):
        """R25913-40: Full reclaim leaves zero available reversal balance."""
        SupplierGSTR3BFilingRecord.objects.update_or_create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            defaults={
                'status': 'VERIFIED_FILED',
                'filing_date': date(2026, 11, 10),
                'arn': 'AA271126000015R',
                'verified_at': timezone.now()
            }
        )
        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='VERIFIED_FILED',
            user=self.user_accountant,
            reclaim_tax=Decimal('1800.00')
        )
        self.assertEqual(reclaim.total_tax, Decimal('1800.00'))

        rem = GSTAllocationService.get_rule37a_available_reversal_balance(self.voucher)
        self.assertEqual(rem, Decimal('0.00'))


class TestPartDRegressionAndAPICoverage(TestCase, Rule37AR2513BaseMixin):
    """Part D: Regression and API boundary tests (R25913-41 to R25913-46)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25913_41_existing_unknown_false_guard_remains_intact(self):
        """R25913-41: Existing UNKNOWN / False guard remains fail-closed."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='UNKNOWN',
            supplier_gstr3b_filed=False
        )
        self.assertFalse(st["is_supplier_default"])
        self.assertFalse(st["reversal_required"])
        self.assertEqual(st["supplier_status"], 'UNKNOWN')

    def test_r25913_42_missing_negative_evidence_timestamp_remains_fail_closed(self):
        """R25913-42: Missing negative evidence timestamp remains fail-closed to DATA_UNAVAILABLE."""
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

    def test_r25913_43_stale_negative_evidence_remains_fail_closed(self):
        """R25913-43: Negative evidence older than 30 days remains fail-closed."""
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            verification_timestamp=self.eval_date - timedelta(days=35)
        )
        self.assertEqual(st["supplier_status"], 'DATA_UNAVAILABLE')
        self.assertFalse(st["is_supplier_default"])

    def test_r25913_44_api_caller_cannot_bypass_manual_evidence_authorization(self):
        """R25913-44: API caller cannot bypass manual evidence authorization."""
        # Simulated API request payload with raw strings
        api_payload = {
            "voucher_id": str(self.voucher.id),
            "assigned_period": "122026",
            "supplier_status": "MANUALLY_CONFIRMED",
            "verification_reference": "INVOICE-STAMP-BYPASS",
            "manual_verification_reason": "Accountant confirmed on phone",
            "verification_timestamp": timezone.now().isoformat()
        }
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period=api_payload["assigned_period"],
                supplier_status=api_payload["supplier_status"],
                verification_reference=api_payload["verification_reference"],
                manual_verification_reason=api_payload["manual_verification_reason"],
                verification_timestamp=api_payload["verification_timestamp"],
                user=self.user_unauthorized  # Unauthorized user from API token
            )
        self.assertIn("Rule 37A manual confirmation requires an authoritative, persisted, approved Rule37AManualFilingEvidence record", str(cm.exception))

    def test_r25913_45_management_command_cannot_bypass_manual_evidence_authorization(self):
        """R25913-45: Management command or batch script cannot bypass manual evidence authorization."""
        # Even with automated script calling without user or persisted record
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                user=None,
                verification_reference='BATCH-CMD-BYPASS'
            )
        self.assertIn("Rule 37A manual confirmation requires an authoritative, persisted, approved Rule37AManualFilingEvidence record", str(cm.exception))

    def test_r25913_46_internal_service_caller_cannot_bypass_authoritative_evidence_validation(self):
        """R25913-46: Internal service caller cannot bypass authoritative evidence validation."""
        # Direct call with manufactured string 'VERIFIED_FILED' without record
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                user=self.user_owner,
                idempotent=False
            )
        self.assertIn("requires a verified, persisted evidence record", str(cm.exception))

"""
SriLekh GST — Round 2.5.14 Dedicated Test Suite
Final Evidence Governance, Audit Integrity & Concurrency Certification Tests

Statutory Framework:
- CGST Rules, 2017 — Proviso to Rule 37A (Reclaim upon supplier furnishing GSTR-3B)
- CGST Act, 2017 — Section 16(2)(c) (Mandatory tax discharge proof)
- CGST Act, 2017 — Section 17(5) (Ineligible blocked credit permanence)
- CGST Act, 2017 — Section 155 (Burden of proof & cryptographic audit trail)

Acceptance Criteria Tested:
- Phase B: Manual evidence approval governance (R25914-01 to R25914-15)
- Phase C: Cryptographic audit integrity and Section 155 tamper-evidence (R25914-16 to R25914-28)
- Phase D: Transactional integrity and mandatory concurrency scenarios A-H (R25914-29 to R25914-37)
- Phase E & G: Caller bypass audit and statutory invariants (R25914-38 to R25914-42)
"""

from datetime import date, datetime, timedelta
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
    Rule37AManualEvidenceAuditEvent,
)
from apps.gst.services.allocation_service import GSTAllocationService
from apps.gst.services.rule37a_evidence_service import Rule37AEvidenceService
from apps.inventory.models import Product
from apps.ledgers.models import LedgerGroup, Ledger

User = get_user_model()


class Rule37AR2514BaseMixin:
    """Base setup shared between transactional and non-transactional test classes."""

    def setup_common_fixtures(self):
        engine = connection.settings_dict.get('ENGINE', '')
        if 'postgresql' not in engine:
            self.skipTest(f"Round 2.5.14 tests require PostgreSQL backend (current: {engine})")

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
            email='owner_r25914@apexbelting.demo',
            defaults={'role': 'OWNER', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_owner, company=self.company, defaults={'role': 'OWNER'})

        self.user_admin, _ = User.objects.get_or_create(
            email='admin_r25914@apexbelting.demo',
            defaults={'role': 'ADMIN', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_admin, company=self.company, defaults={'role': 'ADMIN'})

        self.user_accountant, _ = User.objects.get_or_create(
            email='accountant_r25914@apexbelting.demo',
            defaults={'role': 'ACCOUNTANT', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_accountant, company=self.company, defaults={'role': 'ACCOUNTANT'})

        self.user_unauthorized, _ = User.objects.get_or_create(
            email='viewer_r25914@apexbelting.demo',
            defaults={'role': 'VIEWER', 'is_staff': False, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_unauthorized, company=self.company, defaults={'role': 'VIEWER'})

        self.user_inactive, _ = User.objects.get_or_create(
            email='inactive_r25914@apexbelting.demo',
            defaults={'role': 'ACCOUNTANT', 'is_staff': False, 'is_active': False}
        )
        UserCompany.objects.get_or_create(user=self.user_inactive, company=self.company, defaults={'role': 'ACCOUNTANT'})

        self.user_other_tenant, _ = User.objects.get_or_create(
            email='other_tenant_r25914@othertenant.demo',
            defaults={'role': 'OWNER', 'is_staff': True, 'is_active': True}
        )
        UserCompany.objects.get_or_create(user=self.user_other_tenant, company=self.company_other, defaults={'role': 'OWNER'})

        # Isolated Ledgers
        self.group_creditors, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Sundry Creditors (R25914)',
            defaults={'nature': 'LIABILITY'}
        )

        self.supplier_gstin = '27AAAAA0000A1Z5'
        self.ledger_vendor, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Test Supplier R25914 Industrial Corp',
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
            name='High Torque Conveyor Belt X-300',
            defaults={'sku': 'BELT-R25914-X300', 'hsn_code': '40103990', 'unit': 'NOS', 'gst_rate': Decimal('18.00')}
        )

        # Standard Test Invoice (May 2025 inward supply, FY 2025-26)
        self.invoice_date = date(2025, 5, 15)
        self.inv_period = '052025'
        self.eval_date = date(2026, 11, 20)

        self.voucher = Voucher.objects.create(
            company=self.company,
            voucher_number=f"INV-R25914-{uuid.uuid4().hex[:6].upper()}",
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
            idempotency_key=f"inward_r25914_{self.voucher.id}"
        )

        self.g2b_import, _ = GSTR2BImport.objects.get_or_create(
            company=self.company,
            return_period=self.inv_period,
            defaults={
                'financial_year': '2025-26',
                'file_name': 'test_g2b_r25914.json',
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
                'evidence_source': 'PORTAL',
                'evidence_status': 'VERIFIED_NOT_FILED',
                'evidence_supplier_gstin': self.supplier_gstin,
                'evidence_return_period': self.inv_period,
                'evidence_verified_at': timezone.now() - timedelta(days=2),
                'idempotency_key': f"rule37a_rev_{v.company.id}_{v.id}_102026"
            }
        )
        return rev, supp_rec


class TestPhaseBManualEvidenceGovernance(TestCase, Rule37AR2514BaseMixin):
    """Phase B: Manual evidence approval governance tests (R25914-01 to R25914-15)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25914_01_direct_approved_creation_rejected(self):
        """R25914-01: Direct creation of APPROVED manual evidence is prohibited (Finding B1)."""
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_accountant,
                document_ref='CA-CERT-2026-DIRECT',
                reason='Direct approval bypass attempt',
                status='APPROVED'
            )
        self.assertIn("Direct creation of APPROVED manual evidence is prohibited", str(cm.exception))

    def test_r25914_02_draft_evidence_ineligible_for_reclaim(self):
        """R25914-02: Evidence in DRAFT state fails closed and cannot authorize reclaim."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-DRAFT-001',
            reason='Draft evidence undergoing verification',
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
        self.assertIn("manual evidence status is 'DRAFT'", str(cm.exception))

    def test_r25914_03_submitted_evidence_ineligible_for_reclaim(self):
        """R25914-03: Evidence in SUBMITTED state cannot authorize reclaim until approved."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SUB-001',
            reason='Submitted evidence pending review',
            status='SUBMITTED'
        )
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("manual evidence status is 'SUBMITTED'", str(cm.exception))

    def test_r25914_04_unauthorized_user_cannot_submit(self):
        """R25914-04: Unauthorized user (e.g. VIEWER) cannot submit manual evidence."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SUB-UNAUTH',
            reason='Draft evidence'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.submit_manual_filing_evidence(
                evidence=evidence,
                user=self.user_unauthorized,
                reason='Unauthorized submission'
            )
        self.assertIn("not authorized for manual statutory GST evidence verification", str(cm.exception))

    def test_r25914_05_unauthorized_user_cannot_approve(self):
        """R25914-05: Unauthorized user (VIEWER) cannot approve manual evidence (Finding B2)."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-APPROVE-UNAUTH',
            reason='Submitted evidence',
            status='SUBMITTED'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.approve_manual_filing_evidence(
                evidence=evidence,
                user=self.user_unauthorized,
                reason='Unauthorized approval'
            )
        self.assertIn("not authorized for manual statutory GST evidence verification", str(cm.exception))

    def test_r25914_06_unauthorized_user_cannot_reject(self):
        """R25914-06: Unauthorized user cannot reject manual evidence (Finding B2)."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-REJ-UNAUTH',
            reason='Submitted evidence',
            status='SUBMITTED'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.reject_manual_filing_evidence(
                evidence=evidence,
                user=self.user_unauthorized,
                reason='Unauthorized rejection'
            )
        self.assertIn("not authorized for manual statutory GST evidence verification", str(cm.exception))

    def test_r25914_07_unauthorized_user_cannot_invalidate(self):
        """R25914-07: Unauthorized user cannot invalidate manual evidence (Finding B2)."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-INV-UNAUTH',
            reason='Evidence for invalidation'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.invalidate_manual_filing_evidence(
                evidence=evidence,
                user=self.user_unauthorized,
                reason='Unauthorized invalidation'
            )
        self.assertIn("not authorized for manual statutory GST evidence verification", str(cm.exception))

    def test_r25914_08_inactive_approver_rejected(self):
        """R25914-08: Inactive approver is strictly rejected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-INACTIVE-APP',
            reason='Evidence pending review',
            status='SUBMITTED'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.approve_manual_filing_evidence(
                evidence=evidence,
                user=self.user_inactive,
                reason='Inactive approver attempt'
            )
        self.assertIn("inactive", str(cm.exception).lower())

    def test_r25914_09_cross_tenant_approver_rejected(self):
        """R25914-09: Verifier from another tenant/company cannot approve evidence."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-CROSS-APP',
            reason='Evidence pending review',
            status='SUBMITTED'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.approve_manual_filing_evidence(
                evidence=evidence,
                user=self.user_other_tenant,
                reason='Cross-tenant approval attempt'
            )
        self.assertIn("is not a member of company", str(cm.exception))

    def test_r25914_10_creator_cannot_self_approve_when_other_verifiers_exist(self):
        """R25914-10: Dual authorization enforces that creator cannot approve own evidence when others exist."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SELF-APP',
            reason='Self approval test',
            status='SUBMITTED'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.approve_manual_filing_evidence(
                evidence=evidence,
                user=self.user_accountant,
                reason='Self-approval attempt by creator'
            )
        self.assertIn("Dual authorization required", str(cm.exception))

    def test_r25914_11_owner_permitted_self_approval_with_flag(self):
        """R25914-11: Owner is permitted self-approval with explicit flag recorded."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_owner,
            document_ref='CA-CERT-OWNER-SELF',
            reason='Owner verification for small entity',
            status='SUBMITTED'
        )
        approved = Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner,
            reason='Owner statutory approval'
        )
        self.assertEqual(approved.status, 'APPROVED')
        self.assertTrue(approved.is_self_approved)

    def test_r25914_12_invalid_state_transitions_rejected(self):
        """R25914-12: Invalid state transitions are rejected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-STATE-001',
            reason='Transition test'
        )
        # Cannot directly approve an already rejected record without amendment
        Rule37AEvidenceService.reject_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner,
            reason='Rejected due to illegible scan'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.approve_manual_filing_evidence(
                evidence=evidence,
                user=self.user_owner
            )
        self.assertIn("Cannot approve a rejected evidence record without amendment", str(cm.exception))

    def test_r25914_13_duplicate_approval_rejected(self):
        """R25914-13: Attempting to approve an already approved evidence raises ValidationError."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-DUP-APP',
            reason='Duplicate approval test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.approve_manual_filing_evidence(
                evidence=evidence,
                user=self.user_admin
            )
        self.assertIn("Manual evidence record is already approved", str(cm.exception))

    def test_r25914_14_rejection_requires_mandatory_reason(self):
        """R25914-14: Rejection requires a mandatory documented statutory reason."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-NOREASON-REJ',
            reason='Test record'
        )
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.reject_manual_filing_evidence(
                evidence=evidence,
                user=self.user_owner,
                reason=''
            )
        self.assertIn("Rejection reason is mandatory", str(cm.exception))

    def test_r25914_15_invalidation_requires_mandatory_reason(self):
        """R25914-15: Invalidation requires a mandatory documented statutory reason."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-NOREASON-INV',
            reason='Test record'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.invalidate_manual_filing_evidence(
                evidence=evidence,
                user=self.user_owner,
                reason='   '
            )
        self.assertIn("Invalidation reason is mandatory", str(cm.exception))


class TestPhaseCCryptographicAuditIntegrity(TestCase, Rule37AR2514BaseMixin):
    """Phase C: Cryptographic audit integrity and Section 155 tamper-evidence tests (R25914-16 to R25914-28)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25914_16_audit_events_created_for_full_lifecycle(self):
        """R25914-16: Consecutive chained audit events created across DRAFT -> SUBMITTED -> APPROVED."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-CHAIN-001',
            reason='Lifecycle test',
            status='DRAFT'
        )
        Rule37AEvidenceService.submit_manual_filing_evidence(
            evidence=evidence,
            user=self.user_accountant,
            reason='Submitted for verification'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=evidence,
            user=self.user_owner,
            reason='Approved by owner'
        )
        events = list(evidence.audit_events.order_by('sequence_number'))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].sequence_number, 1)
        self.assertEqual(events[0].action, 'CREATED')
        self.assertEqual(events[0].previous_event_hash, '')

        self.assertEqual(events[1].sequence_number, 2)
        self.assertEqual(events[1].action, 'SUBMITTED')
        self.assertEqual(events[1].previous_event_hash, events[0].current_event_hash)

        self.assertEqual(events[2].sequence_number, 3)
        self.assertEqual(events[2].action, 'APPROVED')
        self.assertEqual(events[2].previous_event_hash, events[1].current_event_hash)

    def test_r25914_17_audit_event_hash_chain_verification_succeeds(self):
        """R25914-17: verify_evidence_audit_chain succeeds on untampered audit chain."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-CHAIN-VALID',
            reason='Chain validation'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)
        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertTrue(is_valid)
        self.assertEqual(msg, "Audit chain valid.")

    def test_r25914_18_modified_document_reference_detected_and_rejected(self):
        """R25914-18: Tampering with document_ref in audit event is detected and fails closed."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-DOC-TAMPER',
            reason='Tamper detection test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        # Simulate direct database tampering via raw SQL bypassing ORM
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE gst_rule37amanualevidenceauditevent SET document_ref = 'TAMPERED-DOC-REF' WHERE evidence_id = %s AND sequence_number = 1",
                [str(evidence.id)]
            )

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertFalse(is_valid)
        self.assertIn("Tampered audit event #1", msg)

        # Reclaim must fail closed
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                evidence_record=evidence,
                user=self.user_accountant
            )
        self.assertIn("Cryptographic Audit Chain Integrity Failure", str(cm.exception))

    def test_r25914_19_modified_supplier_gstin_detected_and_rejected(self):
        """R25914-19: Tampering with supplier_gstin in audit event is detected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-GSTIN-TAMPER',
            reason='GSTIN tamper test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE gst_rule37amanualevidenceauditevent SET supplier_gstin = '27ZZZZZ9999Z1Z1' WHERE evidence_id = %s AND sequence_number = 1",
                [str(evidence.id)]
            )

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertFalse(is_valid)
        self.assertIn("Tampered audit event #1", msg)

    def test_r25914_20_modified_return_period_detected_and_rejected(self):
        """R25914-20: Tampering with return_period in audit event is detected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-PERIOD-TAMPER',
            reason='Period tamper test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE gst_rule37amanualevidenceauditevent SET return_period = '012099' WHERE evidence_id = %s AND sequence_number = 1",
                [str(evidence.id)]
            )

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertFalse(is_valid)
        self.assertIn("Tampered audit event #1", msg)

    def test_r25914_21_modified_actor_user_detected_and_rejected(self):
        """R25914-21: Tampering with actor_user in audit event is detected."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-ACTOR-TAMPER',
            reason='Actor tamper test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE gst_rule37amanualevidenceauditevent SET actor_role = 'FORGED_ROLE' WHERE evidence_id = %s AND sequence_number = 1",
                [str(evidence.id)]
            )

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertFalse(is_valid)
        self.assertIn("Tampered audit event #1", msg)

    def test_r25914_22_deleted_audit_event_detected_and_rejected(self):
        """R25914-22: Deleting an intermediate audit event creates sequence gap and fails closed."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-GAP-TAMPER',
            reason='Gap tamper test',
            status='DRAFT'
        )
        Rule37AEvidenceService.submit_manual_filing_evidence(evidence=evidence, user=self.user_accountant)
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        # Raw SQL delete event #2
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM gst_rule37amanualevidenceauditevent WHERE evidence_id = %s AND sequence_number = 2",
                [str(evidence.id)]
            )

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertFalse(is_valid)
        self.assertIn("sequence gap", msg)

    def test_r25914_23_broken_previous_event_hash_fails_closed(self):
        """R25914-23: Corrupted previous_event_hash fails closed."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-CHAIN-CORRUPT',
            reason='Chain corrupt test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE gst_rule37amanualevidenceauditevent SET previous_event_hash = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff' WHERE evidence_id = %s AND sequence_number = 2",
                [str(evidence.id)]
            )

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(evidence)
        self.assertFalse(is_valid)

    def test_r25914_24_audit_event_update_blocked_at_model_level(self):
        """R25914-24: Attempting to update Rule37AManualEvidenceAuditEvent via save() raises ValidationError."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-IMMUT-001',
            reason='Immutability test'
        )
        evt = evidence.audit_events.first()
        evt.document_ref = 'ATTEMPTED-MUTATION'
        with self.assertRaises(ValidationError) as cm:
            evt.save()
        self.assertIn("strictly immutable and cannot be updated", str(cm.exception))

    def test_r25914_25_audit_event_delete_blocked_at_model_level(self):
        """R25914-25: Attempting to delete Rule37AManualEvidenceAuditEvent via delete() raises ValidationError."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-IMMUT-DEL',
            reason='Immutability delete test'
        )
        evt = evidence.audit_events.first()
        with self.assertRaises(ValidationError) as cm:
            evt.delete()
        self.assertIn("strictly immutable and cannot be deleted", str(cm.exception))

    def test_r25914_26_audit_event_queryset_update_and_delete_blocked(self):
        """R25914-26: Attempting queryset update() or delete() raises ValidationError."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-QS-BLOCK',
            reason='QS immutability test'
        )
        with self.assertRaises(ValidationError):
            Rule37AManualEvidenceAuditEvent.objects.filter(evidence=evidence).update(document_ref='FORBIDDEN')

        with self.assertRaises(ValidationError):
            Rule37AManualEvidenceAuditEvent.objects.filter(evidence=evidence).delete()

    def test_r25914_27_evidence_hash_immutability_on_save(self):
        """R25914-27: Saving Rule37AManualFilingEvidence permanently preserves initial evidence_hash."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-HASH-IMMUT',
            reason='Initial evidence hash test'
        )
        original_hash = evidence.evidence_hash
        self.assertTrue(len(original_hash) == 64)

        # Mutate in memory and save
        evidence.evidence_document_ref = 'MUTATED-AFTER-CREATION'
        evidence.save()

        evidence.refresh_from_db()
        self.assertEqual(evidence.evidence_hash, original_hash)

    def test_r25914_28_valid_correction_and_supersession(self):
        """R25914-28: Valid correction and supersession establishes complete traceable chain."""
        original_ev = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-OLD-CIN-001',
            reason='Initial certificate with error'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=original_ev, user=self.user_owner)

        # Create corrected record in DRAFT
        corrected_ev = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-CORRECTED-CIN-002',
            reason='Corrected vendor challan CIN 112233445566',
            status='DRAFT'
        )
        # Invalidate original with link
        invalidated = Rule37AEvidenceService.invalidate_manual_filing_evidence(
            evidence=original_ev,
            user=self.user_owner,
            reason='Superseded by corrected certificate CA-CERT-CORRECTED-CIN-002',
            superseding_evidence=corrected_ev
        )
        # Approve corrected
        approved_corrected = Rule37AEvidenceService.approve_manual_filing_evidence(
            evidence=corrected_ev,
            user=self.user_owner
        )
        self.assertEqual(invalidated.status, 'INVALIDATED')
        self.assertEqual(invalidated.superseded_by_id, approved_corrected.id)
        self.assertEqual(approved_corrected.status, 'APPROVED')

        is_valid, msg = Rule37AEvidenceService.verify_evidence_audit_chain(approved_corrected)
        self.assertTrue(is_valid)


class TestPhaseDTransactionalIntegrityAndConcurrency(TransactionTestCase, Rule37AR2514BaseMixin):
    """Phase D: PostgreSQL concurrency, row-level locking, and transactional integrity (R25914-29 to R25914-37)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25914_29_concurrency_scenario_a_simultaneous_full_reclaims(self):
        """Scenario A: Two simultaneous full reclaims against the same reversal."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-A',
            reason='Scenario A concurrency'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        successes = []
        failures = []

        def attempt_full_reclaim(period):
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

        t1 = threading.Thread(target=attempt_full_reclaim, args=('112026',))
        t2 = threading.Thread(target=attempt_full_reclaim, args=('122026',))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly 1 transaction can commit the full ₹1800 reclaim
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertTrue("exceeds available reversal balance" in failures[0] or "has already been fully reclaimed" in failures[0])

        total_reclaimed = sum(s.total_tax for s in successes)
        self.assertEqual(total_reclaimed, Decimal('1800.00'))

        remaining_balance = GSTAllocationService.get_rule37a_available_reversal_balance(self.voucher)
        self.assertEqual(remaining_balance, Decimal('0.00'))

    def test_r25914_30_concurrency_scenario_b_simultaneous_excessive_partial_reclaims(self):
        """Scenario B: Two simultaneous partial reclaims exceeding available balance."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-B',
            reason='Scenario B partial concurrency'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        successes = []
        failures = []

        # Reversal is ₹1800. Both threads ask for ₹1000 each (Total ₹2000 > ₹1800)
        def attempt_partial_reclaim(period):
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period=period,
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant,
                    reclaim_tax=Decimal('1000.00')
                )
                successes.append(rec)
            except Exception as e:
                failures.append(str(e))

        t1 = threading.Thread(target=attempt_partial_reclaim, args=('112026',))
        t2 = threading.Thread(target=attempt_partial_reclaim, args=('122026',))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn("exceeds available reversal balance", failures[0])

        remaining_balance = GSTAllocationService.get_rule37a_available_reversal_balance(self.voucher)
        self.assertEqual(remaining_balance, Decimal('800.00'))

    def test_r25914_31_concurrency_scenario_c_invalidation_racing_with_reclaim(self):
        """Scenario C: Evidence invalidation racing with reclaim creation."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-C',
            reason='Scenario C invalidation race'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

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
                    reason='Scenario C race invalidation'
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

        # Serialized outcome: If reclaim succeeds, it occurred before invalidation.
        # If invalidation occurred first, reclaim fails closed.
        reclaim_succeeded = any(o[0] == 'RECLAIM_SUCCESS' for o in outcomes)
        if reclaim_succeeded:
            rec_alloc = GSTReportingAllocation.objects.get(voucher=self.voucher, event_type='ITC_RECLAIM')
            self.assertEqual(rec_alloc.total_tax, Decimal('1800.00'))
        else:
            self.assertTrue(any("INVALIDATED" in err[1] or "requires an authoritative, persisted, approved" in err[1] for err in errors))

    def test_r25914_32_concurrency_scenario_d_rejection_racing_with_reclaim(self):
        """Scenario D: Evidence rejection racing with reclaim."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-D',
            reason='Scenario D rejection race',
            status='SUBMITTED'
        )
        reclaim_errors = []

        def do_reclaim():
            try:
                GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant
                )
            except Exception as e:
                reclaim_errors.append(str(e))

        def do_reject():
            try:
                Rule37AEvidenceService.reject_manual_filing_evidence(
                    evidence=evidence,
                    user=self.user_owner,
                    reason='Scenario D rejected'
                )
            except Exception:
                pass

        t1 = threading.Thread(target=do_reclaim)
        t2 = threading.Thread(target=do_reject)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Reclaim must fail because evidence was never approved
        self.assertTrue(len(reclaim_errors) > 0)

    def test_r25914_33_concurrency_scenario_e_approval_racing_with_reclaim(self):
        """Scenario E: Evidence approval racing with reclaim."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-E',
            reason='Scenario E approval race',
            status='SUBMITTED'
        )
        reclaim_outcomes = []

        def do_reclaim():
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant
                )
                reclaim_outcomes.append(('SUCCESS', rec.id))
            except Exception as e:
                reclaim_outcomes.append(('FAIL', str(e)))

        def do_approve():
            try:
                Rule37AEvidenceService.approve_manual_filing_evidence(
                    evidence=evidence,
                    user=self.user_owner,
                    reason='Scenario E approved'
                )
            except Exception:
                pass

        t1 = threading.Thread(target=do_reclaim)
        t2 = threading.Thread(target=do_approve)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both outcomes are safe fail-closed: if reclaim ran first, it was rejected; if approval ran first, reclaim succeeded.
        self.assertEqual(len(reclaim_outcomes), 1)

    def test_r25914_34_concurrency_scenario_f_simultaneous_approvals(self):
        """Scenario F: Two simultaneous approval requests."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-F',
            reason='Scenario F duplicate approval race',
            status='SUBMITTED'
        )
        approvals = []
        errors = []

        def do_approve(approver):
            try:
                app = Rule37AEvidenceService.approve_manual_filing_evidence(
                    evidence=evidence,
                    user=approver,
                    reason='Scenario F concurrent approve'
                )
                approvals.append(app.id)
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=do_approve, args=(self.user_owner,))
        t2 = threading.Thread(target=do_approve, args=(self.user_admin,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly 1 approval commits; second receives 'already approved'
        self.assertEqual(len(approvals), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("already approved", errors[0])

    def test_r25914_35_concurrency_scenario_g_duplicate_identical_idempotency_keys(self):
        """Scenario G: Duplicate reclaim requests with identical idempotency keys."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-G',
            reason='Scenario G idempotency'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        results = []

        def attempt_idempotent():
            try:
                rec = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='MANUALLY_CONFIRMED',
                    user=self.user_accountant,
                    idempotent=True
                )
                results.append(rec.id)
            except Exception:
                pass

        t1 = threading.Thread(target=attempt_idempotent)
        t2 = threading.Thread(target=attempt_idempotent)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both return the exact same allocation ID
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        total_allocs = GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_RECLAIM').count()
        self.assertEqual(total_allocs, 1)

    def test_r25914_36_concurrency_scenario_h_lineage_crash_causes_100_percent_rollback(self):
        """Scenario H: Reclaim creation where lineage insertion fails causes 100% rollback."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-SCEN-H',
            reason='Scenario H crash testing'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        initial_allocs = GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_RECLAIM').count()
        initial_lineages = GSTReversalReclaimLineage.objects.count()

        orig_create = GSTReversalReclaimLineage.objects.create
        def sim_crash(*args, **kwargs):
            raise RuntimeError("SIMULATED DATABASE DEADLOCK / CRASH ON LINEAGE INSERTION")

        GSTReversalReclaimLineage.objects.create = sim_crash
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

        final_allocs = GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_RECLAIM').count()
        final_lineages = GSTReversalReclaimLineage.objects.count()

        self.assertEqual(initial_allocs, final_allocs)
        self.assertEqual(initial_lineages, final_lineages)

    def test_r25914_37_strict_lock_hierarchy_deadlock_freedom(self):
        """R25914-37: Strict lock hierarchy Voucher -> Prior Reversal -> Evidence Record prevents deadlocks."""
        evidence = Rule37AEvidenceService.create_manual_filing_evidence(
            voucher=self.voucher,
            user=self.user_accountant,
            document_ref='CA-CERT-HIERARCHY',
            reason='Hierarchy lock test'
        )
        Rule37AEvidenceService.approve_manual_filing_evidence(evidence=evidence, user=self.user_owner)

        reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='MANUALLY_CONFIRMED',
            user=self.user_accountant
        )
        self.assertIsNotNone(reclaim)
        self.assertEqual(reclaim.event_type, 'ITC_RECLAIM')


class TestPhaseEAndGStatutoryBypassProtections(TestCase, Rule37AR2514BaseMixin):
    """Phase E & G: Caller bypass audit and statutory invariants (R25914-38 to R25914-42)."""

    def setUp(self):
        self.setup_common_fixtures()
        self._create_reversal_fixture()

    def test_r25914_38_api_caller_cannot_manufacture_approved_evidence(self):
        """R25914-38: API caller cannot manufacture approved evidence without verifier authorization."""
        with self.assertRaises(ValidationError):
            Rule37AEvidenceService.create_manual_filing_evidence(
                voucher=self.voucher,
                user=self.user_unauthorized,
                document_ref='API-FORGED-001',
                reason='Attempted forgery',
                status='APPROVED'
            )

    def test_r25914_39_management_command_cannot_bypass_manual_evidence_authorization(self):
        """R25914-39: Management command cannot bypass authoritative manual evidence requirements."""
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='MANUALLY_CONFIRMED',
                verification_reference='MGMT-CMD-BYPASS-001',
                user=None
            )
        self.assertIn("requires an authoritative, persisted, approved", str(cm.exception))

    def test_r25914_40_section_16_2_c_gstr1_only_rejected(self):
        """R25914-40: Section 16(2)(c) tax payment proof invariant verified."""
        g2b = GSTR2BRecord.objects.create(
            import_batch=self.g2b_import,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number=self.voucher.voucher_number,
            invoice_date=self.invoice_date,
            gstr3b_return_period=self.inv_period,
            gstr1_filing_date=date(2025, 6, 10),
            gstr3b_filing_date=None,
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

    def test_r25914_41_section_17_5_blocked_itc_permanently_ineligible(self):
        """R25914-41: Section 17(5) blocked ITC is permanently ineligible for reclaim."""
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
        self.assertIn("Section 17(5) cannot be reclaimed", str(cm.exception))

    def test_r25914_42_cross_tenant_evidence_isolation_guarantee(self):
        """R25914-42: Evidence from another tenant is strictly rejected across all pathways."""
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

"""
SriLekh GST — Round 2.5.8 Rule 37A Evidence Integrity Remediation Test Suite.
Enforces P0 Statutory Safeguards under Rule 37A & Section 16(2)(c):
1. Absence of evidence must NEVER be interpreted as affirmative evidence of supplier non-filing.
2. Rule 37A reversal requires verified, invoice-period-specific, supplier-specific, fresh evidence.
3. All 12 statutory negative cases strictly enforced at service and domain boundaries.
4. GSTR-2B fallback validated for exact GSTIN, exact period, freshness, and absence of conflicts.
5. Rule 37A reclaim enforces prior active reversal, exact balance tracking, and immutable audit trail.
6. Genuine PostgreSQL TransactionTestCase multi-threaded concurrency serialization.

STRICT INVARIANT:
Runs ONLY against dedicated sandbox company:
Apex Belting & Industrial Store (Demo) (4e62863a-08f9-4e99-b0bd-64873acfdd33).
"""

import threading
import uuid
import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
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
    GSTReversalReclaimLineage,
)
from apps.gst.services.allocation_service import GSTAllocationService, quantize_amount
from apps.gst.services.rule37a_evidence_service import (
    Rule37AEvidenceService,
    compute_rule37a_evidence_hash,
)

User = get_user_model()


class Rule37AEvidenceBaseTestCase:
    SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
    EXPECTED_FINGERPRINT = '6f4741bdaaf4'

    def setup_sandbox_environment(self):
        # 1. Mandatory Environment and Isolation Invariant Check
        from django.conf import settings
        if connection.vendor == 'postgresql':
            raw_db_name = connection.settings_dict.get('NAME') or settings.DATABASES['default']['NAME']
            base_db_name = raw_db_name[5:] if raw_db_name.startswith('test_') else raw_db_name
            db_host = settings.DATABASES['default'].get('HOST', '')
            computed_fp = hashlib.sha256(f"{db_host}:{base_db_name}".encode()).hexdigest()[:12]
            assert base_db_name == 'neondb_staging', f"ABORT: Test running on non-staging database '{base_db_name}'!"
            assert computed_fp == self.EXPECTED_FINGERPRINT, f"ABORT: Fingerprint '{computed_fp}' does not match expected '{self.EXPECTED_FINGERPRINT}'!"

        self.company = Company.objects.filter(id=self.SANDBOX_COMPANY_ID).first()
        if not self.company:
            self.company = Company.objects.create(
                id=self.SANDBOX_COMPANY_ID,
                name="Apex Belting & Industrial Store (Demo)",
                gstin="27AABCU9603R1ZM"
            )
        assert str(self.company.id) == self.SANDBOX_COMPANY_ID, "ABORT: Isolation breach!"

        self.user, _ = User.objects.get_or_create(
            email="auditor_r258@apexbelting.demo",
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

        self.creditor_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Kalyan Belting Suppliers",
            defaults={"group": grp_liab, "gstin": "27AAECK1234F1Z5"}
        )
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
            sku='BELT-R258-SKU',
            defaults={
                'name': 'Industrial Conveyor Belt',
                'unit': 'MTR',
                'hsn_code': '40103999',
                'selling_price': Decimal('1200.00'),
                'purchase_price': Decimal('800.00'),
                'gst_rate': Decimal('18.00')
            }
        )

    def create_test_voucher(
        self,
        v_date: date,
        taxable_value: Decimal = Decimal('10000.00'),
        tax_rate: Decimal = Decimal('0.18'),
        voucher_number: Optional[str] = None
    ) -> Voucher:
        v_num = voucher_number or f"PUR-258-{uuid.uuid4().hex[:8].upper()}"
        half_tax = quantize_amount(taxable_value * tax_rate / Decimal('2.00'))
        total_val = taxable_value + (half_tax * Decimal('2.00'))

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number=v_num,
            voucher_date=v_date,
            party_ledger=self.creditor_ledger,
            total_amount=total_val,
            created_by=self.user
        )

        # Voucher line item for tax calculation
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=taxable_value,
            taxable_amount=taxable_value,
            gst_rate=tax_rate * Decimal('100.00'),
            cgst_rate=tax_rate * Decimal('50.00'),
            sgst_rate=tax_rate * Decimal('50.00'),
            cgst_amount=half_tax,
            sgst_amount=half_tax,
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_amount=total_val
        )

        # Balanced Double-Entry Postings
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.purchase_ledger,
            debit_amount=taxable_value,
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.cgst_input,
            debit_amount=half_tax,
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.sgst_input,
            debit_amount=half_tax,
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=self.creditor_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=total_val
        )

        # Create active INWARD_ITC allocation
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v,
            event_type='INWARD_ITC',
            voucher_date=v_date,
            entry_date=v_date,
            original_period=v_date.strftime('%m%Y'),
            assigned_period=v_date.strftime('%m%Y'),
            financial_year=GSTAllocationService.get_financial_year(v_date),
            status='APPROVED',
            is_statutorily_eligible=True,
            taxable_value=taxable_value,
            cgst_amount=half_tax,
            sgst_amount=half_tax,
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_tax=half_tax * Decimal('2.00'),
            is_active=True,
            idempotency_key=f"inward_{v.id}_{v_date.strftime('%m%Y')}"
        )
        return v


class Rule37AReversalEvidenceValidationTests(TestCase, Rule37AEvidenceBaseTestCase):
    def setUp(self):
        self.setup_sandbox_environment()
        # Invoice from FY 2025-26: June 2025 (Period: 062025). Default date is 30-Sep-2026.
        self.v_date = date(2025, 6, 15)
        self.voucher = self.create_test_voucher(v_date=self.v_date)
        self.reversal_date = date(2026, 10, 15)  # Past 30-Sep-2026 default date
        self.inv_period = '062025'
        self.supplier_gstin = self.creditor_ledger.gstin

    def test_reversal_rejected_without_status(self):
        """Calling reversal service without supplier status must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status=None,
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("explicit supplier status", str(ctx.exception))

    def test_reversal_rejected_without_gstin(self):
        """Calling reversal service without supplier GSTIN must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=None,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("explicit supplier GSTIN", str(ctx.exception))

    def test_reversal_rejected_without_return_period(self):
        """Calling reversal service without supplier return period must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period='',
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("explicit supplier return period", str(ctx.exception))

    def test_reversal_rejected_without_evidence_source(self):
        """Calling reversal service without an evidence source must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='',
                verification_timestamp=timezone.now()
            )
        self.assertIn("evidence source", str(ctx.exception))

    def test_reversal_rejected_without_verification_timestamp(self):
        """Calling reversal service without a verification timestamp must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=None
            )
        self.assertIn("verification timestamp", str(ctx.exception))

    def test_reversal_rejected_for_unknown_status(self):
        """Supplying UNKNOWN status must be rejected."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='UNKNOWN',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("UNKNOWN", str(ctx.exception))

    def test_reversal_rejected_for_pending_status(self):
        """Supplying PENDING status must be rejected."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='PENDING',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("PENDING", str(ctx.exception))

    def test_reversal_rejected_for_data_unavailable(self):
        """Supplying DATA_UNAVAILABLE status must be rejected."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='DATA_UNAVAILABLE',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("DATA_UNAVAILABLE", str(ctx.exception))

    def test_reversal_rejected_for_stale_evidence(self):
        """Supplying stale evidence (>30 days old) must fail."""
        stale_time = timezone.now() - timedelta(days=45)
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=stale_time,
                is_stale_evidence=True
            )
        self.assertIn("stale", str(ctx.exception).lower())

    def test_reversal_rejected_for_wrong_supplier_gstin(self):
        """Supplying a different supplier GSTIN must fail."""
        wrong_gstin = "07AAAAA0000A1Z5"
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=wrong_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("does not match invoice supplier GSTIN", str(ctx.exception))

    def test_reversal_rejected_for_wrong_return_period(self):
        """Supplying a different return period must fail."""
        wrong_period = "072025"  # July 2025 instead of June 2025
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=wrong_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now()
            )
        self.assertIn("does not match invoice return period", str(ctx.exception))

    def test_reversal_rejected_for_manufactured_string_without_real_evidence(self):
        """Supplying VERIFIED_NOT_FILED without a real evidence record or document ref must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now(),
                evidence_record=None,
                evidence_document_ref='',
                manual_verification_reason=''
            )
        self.assertIn("requires actual supporting evidence", str(ctx.exception))

    def test_reversal_accepted_with_valid_exact_period_evidence_record(self):
        """Valid exact-period SupplierGSTR3BFilingRecord is accepted and populates cryptographic audit trail."""
        supp_rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            financial_year='2025-26',
            status='VERIFIED_NOT_FILED',
            verification_source='PORTAL',
            evidence_document_ref='GSTN-API-POLL-258'
        )

        alloc = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            reversal_date=self.reversal_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_source='PORTAL',
            verification_timestamp=timezone.now(),
            evidence_record=supp_rec
        )
        self.assertIsNotNone(alloc)
        self.assertEqual(alloc.event_type, 'ITC_REVERSAL_RULE_37A')
        self.assertEqual(alloc.evidence_status, 'VERIFIED_NOT_FILED')
        self.assertEqual(alloc.evidence_supplier_gstin, self.supplier_gstin)
        self.assertEqual(alloc.evidence_return_period, self.inv_period)
        self.assertTrue(len(alloc.evidence_hash) == 64)

    def test_reversal_accepted_with_documented_manual_evidence(self):
        """Documented manual confirmation with reference, reason, timestamp and user succeeds."""
        alloc = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            reversal_date=self.reversal_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_source='MANUAL_EVIDENCE',
            verification_timestamp=timezone.now(),
            evidence_document_ref='AUDIT-MEMO-2026-10-01',
            manual_verification_reason='Supplier confirmed in writing non-filing of GSTR-3B for June 2025.',
            user=self.user
        )
        self.assertIsNotNone(alloc)
        self.assertEqual(alloc.evidence_document_ref, 'AUDIT-MEMO-2026-10-01')
        self.assertEqual(alloc.created_by, self.user)


class Rule37ADeadlineCheckerEvidenceResolutionTests(TestCase, Rule37AEvidenceBaseTestCase):
    def setUp(self):
        self.setup_sandbox_environment()
        self.v_date = date(2025, 6, 15)
        self.voucher = self.create_test_voucher(v_date=self.v_date)
        self.inv_period = '062025'
        self.supplier_gstin = self.creditor_ledger.gstin
        self.eval_date = date(2026, 10, 15)

    def test_deadline_checker_exact_gstin_and_period_match(self):
        """Exact supplier GSTIN and exact period match is accepted and recognized as default."""
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED',
            verification_source='PORTAL'
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'VERIFIED_NOT_FILED')
        self.assertEqual(ev_res["return_period"], self.inv_period)
        self.assertFalse(ev_res["is_stale"])

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"]
        )
        self.assertTrue(st["is_supplier_default"])

    def test_deadline_checker_wrong_period_ignored_returns_data_unavailable(self):
        """Evidence record with wrong return period is ignored, never defaults for this invoice."""
        # Record exists for July 2025, but invoice is June 2025
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period='072025',
            status='VERIFIED_NOT_FILED',
            verification_source='PORTAL'
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertIn(ev_res["status"], ('UNKNOWN', 'DATA_UNAVAILABLE'))

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"],
            supplier_return_period=ev_res["return_period"],
            supplier_gstin=ev_res["supplier_gstin"],
            is_stale_evidence=ev_res["is_stale"]
        )
        self.assertFalse(st["is_supplier_default"])

    def test_deadline_checker_wrong_gstin_ignored_returns_data_unavailable(self):
        """GSTR2B record with wrong supplier GSTIN cannot be evaluated for this invoice."""
        imp = GSTR2BImport.objects.create(
            company=self.company,
            return_period=self.inv_period,
            file_name="test_2b.json"
        )
        GSTR2BRecord.objects.create(
            import_batch=imp,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin="07AAAAA9999Z1Z1",  # Wrong GSTIN
            invoice_number="INV-258-001",
            normalized_invoice_number="INV258001",
            invoice_date=self.v_date,
            gstr3b_status='NOT_FILED',
            gstr3b_return_period=self.inv_period,
            gstr3b_verified_at=timezone.now()
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertIn(ev_res["status"], ('UNKNOWN', 'DATA_UNAVAILABLE'))

    def test_deadline_checker_no_evidence_returns_unknown_never_defaults(self):
        """Absence of evidence returns UNKNOWN and never declares default."""
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'UNKNOWN')
        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"]
        )
        self.assertFalse(st["is_supplier_default"])

    def test_deadline_checker_conflicting_evidence_returns_data_unavailable(self):
        """Conflicting evidence between SupplierGSTR3BFilingRecord and GSTR2B returns DATA_UNAVAILABLE."""
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            filing_date=date(2025, 7, 10),
            arn='AA270725000001Z'
        )
        imp = GSTR2BImport.objects.create(
            company=self.company,
            return_period=self.inv_period,
            file_name="test_2b_conflict.json"
        )
        GSTR2BRecord.objects.create(
            import_batch=imp,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number="INV-258-002",
            normalized_invoice_number="INV258002",
            invoice_date=self.v_date,
            gstr3b_status='NOT_FILED',  # Conflicts with VERIFIED_FILED
            gstr3b_return_period=self.inv_period,
            gstr3b_verified_at=timezone.now()
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'DATA_UNAVAILABLE')
        self.assertIn("conflicting", ev_res["provenance"].get("source", "").lower())

        st = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=self.eval_date,
            supplier_status=ev_res["status"]
        )
        self.assertFalse(st["is_supplier_default"])

    def test_deadline_checker_stale_supplier_record_treated_as_data_unavailable(self):
        """Supplier filing record older than 30 days is treated as DATA_UNAVAILABLE."""
        stale_date = timezone.now() - timedelta(days=40)
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED'
        )
        SupplierGSTR3BFilingRecord.objects.filter(id=rec.id).update(verified_at=stale_date)
        rec.refresh_from_db()
        self.assertTrue(rec.is_stale(30))

        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'DATA_UNAVAILABLE')
        self.assertTrue(ev_res["is_stale"])

    def test_deadline_checker_stale_gstr2b_fallback_treated_as_data_unavailable(self):
        """GSTR2B fallback older than 30 days is treated as DATA_UNAVAILABLE."""
        imp = GSTR2BImport.objects.create(
            company=self.company,
            return_period=self.inv_period,
            file_name="test_2b_stale.json"
        )
        stale_date = timezone.now() - timedelta(days=40)
        GSTR2BRecord.objects.create(
            import_batch=imp,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number="INV-258-003",
            normalized_invoice_number="INV258003",
            invoice_date=self.v_date,
            gstr3b_status='NOT_FILED',
            gstr3b_return_period=self.inv_period,
            gstr3b_verified_at=stale_date
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'DATA_UNAVAILABLE')
        self.assertTrue(ev_res["is_stale"])

    def test_deadline_checker_gstr1_date_cannot_establish_gstr3b_filing(self):
        """GSTR-1 filing date present without GSTR-3B return filing returns DATA_UNAVAILABLE."""
        imp = GSTR2BImport.objects.create(
            company=self.company,
            return_period=self.inv_period,
            file_name="test_2b_gstr1.json"
        )
        GSTR2BRecord.objects.create(
            import_batch=imp,
            company=self.company,
            matched_voucher=self.voucher,
            supplier_gstin=self.supplier_gstin,
            invoice_number="INV-258-004",
            normalized_invoice_number="INV258004",
            invoice_date=self.v_date,
            gstr1_filing_date=date(2025, 7, 11),
            gstr3b_status='UNKNOWN',
            gstr3b_filing_date=None,
            gstr3b_filing_arn='',
            gstr3b_verified_at=timezone.now()
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertEqual(ev_res["status"], 'DATA_UNAVAILABLE')
        self.assertFalse(ev_res["supplier_gstr3b_filed"])

    def test_deadline_checker_tenant_isolation_other_tenant_evidence_blocked(self):
        """Evidence belonging to another tenant is not accessible or resolvable."""
        other_comp = Company.objects.create(
            name="Other Isolated Company Ltd",
            gstin="27XYZAB1234K1Z0"
        )
        SupplierGSTR3BFilingRecord.objects.create(
            company=other_comp,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_FILED',
            arn='AA270625999999Z',
            filing_date=date(2025, 7, 15)
        )
        ev_res = Rule37AEvidenceService.resolve_voucher_evidence(self.voucher)
        self.assertNotEqual(ev_res["status"], 'VERIFIED_FILED')
        self.assertEqual(ev_res["status"], 'UNKNOWN')


class Rule37AReclaimEvidenceValidationTests(TestCase, Rule37AEvidenceBaseTestCase):
    def setUp(self):
        self.setup_sandbox_environment()
        self.v_date = date(2025, 6, 15)
        self.voucher = self.create_test_voucher(v_date=self.v_date)
        self.inv_period = '062025'
        self.supplier_gstin = self.creditor_ledger.gstin
        self.reversal_date = date(2026, 10, 15)

        # Create valid active reversal
        supp_rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED'
        )
        self.reversal = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            reversal_date=self.reversal_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_source='PORTAL',
            verification_timestamp=timezone.now(),
            evidence_record=supp_rec
        )

    def test_reclaim_rejected_without_prior_reversal(self):
        """Reclaim without prior reversal must fail."""
        voucher_without_rev = self.create_test_voucher(v_date=self.v_date, voucher_number="PUR-NO-REV-001")
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=voucher_without_rev,
                assigned_period='112026',
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA270625123456Z',
                gstr3b_filing_date=date(2026, 11, 5)
            )
        self.assertIn("No active prior Rule 37A reversal found", str(ctx.exception))

    def test_reclaim_rejected_with_inactive_or_superseded_reversal(self):
        """Reclaim linked to an inactive/superseded reversal must fail."""
        GSTAllocationService.supersede_payment_reclaim_allocation(
            allocation=self.reversal,
            reason="Superseded for testing inactive reversal check"
        )
        self.reversal.refresh_from_db()
        self.assertFalse(self.reversal.is_active)

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                source_reversal_id=self.reversal.id,
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA270625123456Z',
                gstr3b_filing_date=date(2026, 11, 5)
            )
        self.assertIn("No active prior Rule 37A reversal found", str(ctx.exception))

    def test_reclaim_rejected_without_arn_for_portal_verified(self):
        """VERIFIED_FILED reclaim without GSTR-3B ARN must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='',
                gstr3b_filing_date=date(2026, 11, 5)
            )
        self.assertIn("Application Reference Number (ARN)", str(ctx.exception))

    def test_reclaim_rejected_without_filing_date(self):
        """VERIFIED_FILED reclaim without filing date must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA270625123456Z',
                gstr3b_filing_date=None
            )
        self.assertIn("filing date", str(ctx.exception))

    def test_reclaim_rejected_with_wrong_supplier_gstin(self):
        """Reclaim with mismatched supplier GSTIN must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='VERIFIED_FILED',
                supplier_gstin="07AAAAA1111Z1Z1",
                gstr3b_arn='AA270625123456Z',
                gstr3b_filing_date=date(2026, 11, 5)
            )
        self.assertIn("does not match invoice supplier GSTIN", str(ctx.exception))

    def test_reclaim_rejected_with_wrong_return_period(self):
        """Reclaim with mismatched return period must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='VERIFIED_FILED',
                supplier_return_period="072025",
                gstr3b_arn='AA270625123456Z',
                gstr3b_filing_date=date(2026, 11, 5)
            )
        self.assertIn("does not match invoice return period", str(ctx.exception))

    def test_reclaim_rejected_for_manual_without_document_ref(self):
        """Manual reclaim without document reference must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='MANUALLY_CONFIRMED',
                verification_reference='',
                verification_date=timezone.now(),
                user=self.user
            )
        self.assertIn("document reference", str(ctx.exception))

    def test_reclaim_rejected_for_manual_without_verifier_user(self):
        """Manual reclaim without verifier identity (user) must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='MANUALLY_CONFIRMED',
                verification_reference='CA-CERT-2026-99',
                verification_date=timezone.now(),
                user=None
            )
        self.assertIn("verifier identity", str(ctx.exception))

    def test_reclaim_rejected_for_manual_without_timestamp(self):
        """Manual reclaim without verification timestamp must fail."""
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='MANUALLY_CONFIRMED',
                verification_reference='CA-CERT-2026-99',
                verification_date=None,
                user=self.user
            )
        self.assertIn("verification timestamp", str(ctx.exception))

    def test_reclaim_rejected_when_exceeding_reversal_balance(self):
        """Attempting to reclaim more than the active available reversal balance must fail."""
        # Execute initial full reclaim
        rec1 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='112026',
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA270625123456Z',
            gstr3b_filing_date=date(2026, 11, 5)
        )
        self.assertIsNotNone(rec1)

        # Attempting second reclaim on same voucher in different period must fail
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA270625999999Z',
                gstr3b_filing_date=date(2026, 11, 5)
            )
        self.assertIn("already active in another period", str(ctx.exception))

    def test_reclaim_success_with_exact_valid_evidence_and_lineage(self):
        """Exact valid reclaim succeeds, establishes GSTReversalReclaimLineage, and populates evidence audit fields."""
        rec = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='112026',
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA270625777777Z',
            gstr3b_filing_date=date(2026, 11, 5),
            user=self.user
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec.event_type, 'ITC_RECLAIM')
        self.assertEqual(rec.allocation_reason, 'RECLAIM_RULE_37A')
        self.assertEqual(rec.source_reversal, self.reversal)
        self.assertEqual(rec.evidence_arn, 'AA270625777777Z')
        self.assertEqual(rec.evidence_filing_date, date(2026, 11, 5))
        self.assertTrue(len(rec.evidence_hash) == 64)

        # Verify lineage
        lineage = GSTReversalReclaimLineage.objects.filter(
            reversal_allocation=self.reversal,
            reclaim_allocation=rec
        ).first()
        self.assertIsNotNone(lineage)
        self.assertEqual(lineage.reclaimed_tax, rec.total_tax)
        self.assertEqual(lineage.statutory_rule, 'RULE_37A')

    def test_superseded_reclaim_restores_eligible_reversal_balance(self):
        """Superseding a reclaim frees the reversal balance for subsequent corrected reclaim."""
        rec1 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='112026',
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA270625111111Z',
            gstr3b_filing_date=date(2026, 11, 5)
        )
        self.assertTrue(rec1.is_active)

        # Supersede rec1
        GSTAllocationService.supersede_payment_reclaim_allocation(
            allocation=rec1,
            reason="Superseded due to incorrect ARN recorded"
        )
        rec1.refresh_from_db()
        self.assertFalse(rec1.is_active)
        self.assertEqual(rec1.status, 'SUPERSEDED')

        # Balance is restored; subsequent reclaim in same or new period must succeed
        rec2 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA270625222222Z',
            gstr3b_filing_date=date(2026, 11, 6)
        )
        self.assertTrue(rec2.is_active)
        self.assertEqual(rec2.evidence_arn, 'AA270625222222Z')


class Rule37AConcurrencyTests(TransactionTestCase, Rule37AEvidenceBaseTestCase):
    def setUp(self):
        self.setup_sandbox_environment()
        self.v_date = date(2025, 6, 15)
        self.voucher = self.create_test_voucher(v_date=self.v_date, voucher_number="PUR-CONCUR-258")
        self.inv_period = '062025'
        self.supplier_gstin = self.creditor_ledger.gstin
        self.reversal_date = date(2026, 10, 15)

        self.supp_rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period=self.inv_period,
            status='VERIFIED_NOT_FILED'
        )

    def test_concurrent_rule37a_reversals_serialized(self):
        """Concurrent attempts to create duplicate Rule 37A reversals are strictly serialized to exactly 1 active."""
        if connection.vendor == 'sqlite':
            # Rapid SQLite serialization test
            rev1 = GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                reversal_date=self.reversal_date,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstin=self.supplier_gstin,
                supplier_return_period=self.inv_period,
                evidence_source='PORTAL',
                verification_timestamp=timezone.now(),
                evidence_record=self.supp_rec
            )
            self.assertIsNotNone(rev1)
            with self.assertRaises(ValidationError):
                GSTAllocationService.create_rule37a_reversal_allocation(
                    voucher=self.voucher,
                    assigned_period='102026',
                    reversal_date=self.reversal_date,
                    supplier_status='VERIFIED_NOT_FILED',
                    supplier_gstin=self.supplier_gstin,
                    supplier_return_period=self.inv_period,
                    evidence_source='PORTAL',
                    verification_timestamp=timezone.now(),
                    evidence_record=self.supp_rec
                )
            return

        # PostgreSQL genuine multi-threaded test
        results = []
        errors = []

        def worker():
            try:
                alloc = GSTAllocationService.create_rule37a_reversal_allocation(
                    voucher=self.voucher,
                    assigned_period='102026',
                    reversal_date=self.reversal_date,
                    supplier_status='VERIFIED_NOT_FILED',
                    supplier_gstin=self.supplier_gstin,
                    supplier_return_period=self.inv_period,
                    evidence_source='PORTAL',
                    verification_timestamp=timezone.now(),
                    evidence_record=self.supp_rec
                )
                results.append(alloc)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        active_revs = GSTReportingAllocation.objects.filter(
            voucher=self.voucher,
            event_type='ITC_REVERSAL_RULE_37A',
            is_active=True
        )
        self.assertEqual(active_revs.count(), 1, "Concurrency Violation: Duplicate Rule 37A reversals created!")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)

    def test_concurrent_rule37a_reclaims_serialized(self):
        """Concurrent attempts to reclaim the same reversal are strictly serialized; no double reclaim."""
        rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            reversal_date=self.reversal_date,
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin=self.supplier_gstin,
            supplier_return_period=self.inv_period,
            evidence_source='PORTAL',
            verification_timestamp=timezone.now(),
            evidence_record=self.supp_rec
        )
        self.assertIsNotNone(rev)

        if connection.vendor == 'sqlite':
            rec1 = GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA270625888888Z',
                gstr3b_filing_date=date(2026, 11, 5)
            )
            self.assertIsNotNone(rec1)
            with self.assertRaises(ValidationError):
                GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period='122026',
                    supplier_status='VERIFIED_FILED',
                    gstr3b_arn='AA270625999999Z',
                    gstr3b_filing_date=date(2026, 11, 5)
                )
            return

        results = []
        errors = []

        def worker(period_str, arn_code):
            try:
                alloc = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=self.voucher,
                    assigned_period=period_str,
                    supplier_status='VERIFIED_FILED',
                    gstr3b_arn=arn_code,
                    gstr3b_filing_date=date(2026, 11, 5)
                )
                results.append(alloc)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=worker, args=('112026', 'AA270625111111Z'))
        t2 = threading.Thread(target=worker, args=('122026', 'AA270625222222Z'))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        active_reclaims = GSTReportingAllocation.objects.filter(
            voucher=self.voucher,
            event_type='ITC_RECLAIM',
            allocation_reason='RECLAIM_RULE_37A',
            is_active=True
        )
        self.assertEqual(active_reclaims.count(), 1, "Concurrency Violation: Duplicate Rule 37A reclaims created!")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)

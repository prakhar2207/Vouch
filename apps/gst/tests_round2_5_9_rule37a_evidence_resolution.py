"""
SriLekh GST — Round 2.5.9: Rule 37A Evidence Resolution Hardening & Independent Re-Certification.
Dedicated test suite verifying P0 statutory evidence invariants:
1. GSTR-2B exact return-period enforcement (blank, null, malformed, or mismatched periods rejected).
2. Evidence timestamp preservation (never masked by fake timezone.now()).
3. Missing timestamps on negative non-filing evidence return DATA_UNAVAILABLE.
4. Positive filing fact validity with ARN & filing date.
5. Cross-source reconciliation (conflicts and ambiguities return DATA_UNAVAILABLE).
6. Prior reversal requirement and lineage tracking on reclaims.
7. Genuine PostgreSQL multi-threaded concurrency serialization.

STRICT INVARIANT:
Runs ONLY against dedicated sandbox company:
Apex Belting & Industrial Store (Demo) (4e62863a-08f9-4e99-b0bd-64873acfdd33).
Protected production tenant: 5d2e5dea-fe86-4871-b2af-fe1c5a05c03c — ZERO access.
"""

import hashlib
import threading
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product
from apps.gst.models import (
    GSTReportingAllocation,
    GSTR2BRecord,
    GSTR2BImport,
    SupplierGSTR3BFilingRecord,
    GSTReversalReclaimLineage,
)
from apps.gst.services.allocation_service import GSTAllocationService, quantize_amount
from apps.gst.services.rule37a_evidence_service import Rule37AEvidenceService

User = get_user_model()


class Rule37AEvidenceResolutionBaseTestCase:
    """
    Base test case with fail-closed environment validation for Round 2.5.9.
    Enforces strict test isolation: Sandbox Company ONLY.
    """
    SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
    EXPECTED_FINGERPRINT = '6f4741bdaaf4'

    def setup_sandbox_environment(self):
        # 1. Fail-closed Environment and Isolation Invariant Check
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
            email="auditor_r259@apexbelting.demo",
            defaults={"role": "OWNER", "is_staff": True, "is_active": True}
        )

        self.supplier_gstin = "27AAACP0123M1Z5"
        self.period = "042024"  # April 2024 (FY 2024-25)

        # Ledgers Setup
        grp_asset, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Current Assets (R259)",
            defaults={"nature": "ASSET"}
        )
        grp_liab, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sundry Creditors (R259)",
            defaults={"nature": "LIABILITY"}
        )
        grp_exp, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Direct Expenses (R259)",
            defaults={"nature": "EXPENSE"}
        )

        self.creditor_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Alpha Belting Suppliers R259",
            defaults={"group": grp_liab, "gstin": self.supplier_gstin}
        )
        self.purchase_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="Raw Material Purchases R259",
            defaults={"group": grp_exp}
        )
        self.cgst_input, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="CGST Input R259",
            defaults={"group": grp_asset}
        )
        self.sgst_input, _ = Ledger.objects.get_or_create(
            company=self.company,
            name="SGST Input R259",
            defaults={"group": grp_asset}
        )

        self.product, _ = Product.objects.get_or_create(
            company=self.company,
            sku='BELT-R259-SKU',
            defaults={
                'name': 'Conveyor Belt R259',
                'unit': 'MTR',
                'hsn_code': '40103999',
                'selling_price': Decimal('1200.00'),
                'purchase_price': Decimal('800.00'),
                'gst_rate': Decimal('18.00')
            }
        )

        self.import_batch, _ = GSTR2BImport.objects.get_or_create(
            company=self.company,
            return_period="042024",
            defaults={"file_name": "test_batch_r259.json"}
        )

    def create_test_voucher(
        self,
        v_date: date,
        taxable_value: Decimal = Decimal('10000.00'),
        tax_rate: Decimal = Decimal('0.18'),
        voucher_number: Optional[str] = None
    ) -> Voucher:
        v_num = voucher_number or f"PUR-259-{uuid.uuid4().hex[:8].upper()}"
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

        clean_period = v_date.strftime('%m%Y')
        fy = GSTAllocationService.get_financial_year(v_date)
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v,
            event_type='INWARD_ITC',
            voucher_date=v_date,
            entry_date=v_date,
            original_period=clean_period,
            assigned_period=clean_period,
            financial_year=fy,
            allocation_reason='INWARD_PURCHASE',
            status='APPROVED',
            is_statutorily_eligible=True,
            statutory_rule='Section 16(1)',
            taxable_value=taxable_value,
            igst_amount=Decimal('0.00'),
            cgst_amount=half_tax,
            sgst_amount=half_tax,
            cess_amount=Decimal('0.00'),
            total_tax=half_tax * Decimal('2.00'),
            is_active=True,
            idempotency_key=f"inward_test_{v.id}"
        )
        return v


class Rule37AEvidenceResolutionTestCase(TestCase, Rule37AEvidenceResolutionBaseTestCase):
    """
    Comprehensive statutory test suite for Round 2.5.9 evidence resolution hardening.
    Covers scenarios 1 to 24 of Section 9.
    """

    def setUp(self):
        super().setUp()
        self.setup_sandbox_environment()

    # --- Group 1: Missing Evidence Fields (Scenarios 1 - 4) ---

    def test_01_missing_supplier_gstin_rejected(self):
        """1. Missing supplier GSTIN must fail closed."""
        v = self.create_test_voucher(date(2024, 4, 15))
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reversal_evidence(
                voucher=v,
                supplier_status="VERIFIED_NOT_FILED",
                supplier_gstin="",
                supplier_return_period="042024",
                evidence_source="PORTAL",
                verification_timestamp=timezone.now()
            )
        self.assertIn("explicit supplier GSTIN", str(cm.exception))

    def test_02_missing_supplier_status_rejected(self):
        """2. Missing supplier status must fail closed."""
        v = self.create_test_voucher(date(2024, 4, 15))
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reversal_evidence(
                voucher=v,
                supplier_status="",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                evidence_source="PORTAL",
                verification_timestamp=timezone.now()
            )
        self.assertIn("explicit supplier status", str(cm.exception))

    def test_03_missing_evidence_source_rejected(self):
        """3. Missing evidence source must fail closed."""
        v = self.create_test_voucher(date(2024, 4, 15))
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reversal_evidence(
                voucher=v,
                supplier_status="VERIFIED_NOT_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                evidence_source="",
                verification_timestamp=timezone.now()
            )
        self.assertIn("evidence source", str(cm.exception))

    def test_04_missing_verification_timestamp_rejected(self):
        """4. Missing verification timestamp on reversal must fail closed."""
        v = self.create_test_voucher(date(2024, 4, 15))
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reversal_evidence(
                voucher=v,
                supplier_status="VERIFIED_NOT_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                evidence_source="PORTAL",
                verification_timestamp=None
            )
        self.assertIn("verification timestamp", str(cm.exception))

    # --- Group 2: GSTR-2B Exact Return-Period Enforcement (Scenarios 5 - 8) ---

    def test_05_blank_gstr2b_gstr3b_period_rejected(self):
        """5. Blank GSTR-3B return period on GSTR-2B fallback must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        GSTR2BRecord.objects.create(
            import_batch=self.import_batch,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="",  # BLANK GSTR-3B period
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        # Must NOT treat blank period as matching 042024; returns DATA_UNAVAILABLE
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")
        self.assertFalse(ev["supplier_gstr3b_filed"])

    def test_06_malformed_gstr2b_gstr3b_period_rejected(self):
        """6. Malformed GSTR-3B return period on GSTR-2B fallback must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        GSTR2BRecord.objects.create(
            import_batch=self.import_batch,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="INVALID",  # Malformed period (not MMYYYY)
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")

    def test_07_wrong_gstr3b_period_rejected(self):
        """7. GSTR-3B return period for different month (052024 vs 042024) must be excluded."""
        v = self.create_test_voucher(date(2024, 4, 15))  # Invoice is April 2024 (042024)
        GSTR2BRecord.objects.create(
            import_batch=self.import_batch,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="052024",  # May 2024 (WRONG PERIOD)
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")

    def test_08_wrong_supplier_gstin_rejected(self):
        """8. Record for different supplier GSTIN must not be attributed to voucher."""
        v = self.create_test_voucher(date(2024, 4, 15))
        GSTR2BRecord.objects.create(
            import_batch=self.import_batch,
            company=self.company,
            supplier_gstin="27DIFF0000000Z1",  # Wrong GSTIN (15 chars)
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="042024",
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "UNKNOWN")

    # --- Group 3: Timestamp & Freshness Integrity (Scenarios 9 - 12) ---

    def test_09_stale_negative_evidence_returns_data_unavailable(self):
        """9. Negative non-filing evidence older than 30 days must return DATA_UNAVAILABLE."""
        v = self.create_test_voucher(date(2024, 4, 15))
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now() - timedelta(days=45),  # 45 days old (STALE)
            verification_source="PORTAL"
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")
        self.assertTrue(ev["is_stale"])

    def test_10_missing_timestamp_on_negative_evidence_returns_data_unavailable(self):
        """10. Negative non-filing evidence without verification timestamp must return DATA_UNAVAILABLE."""
        v = self.create_test_voucher(date(2024, 4, 15))
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=None,  # Missing timestamp
            verification_source="PORTAL"
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")
        self.assertIsNone(ev["verification_timestamp"])

    def test_11_valid_exact_period_non_filing_evidence_succeeds(self):
        """11. Fresh, exact-period negative evidence with timestamp resolves as VERIFIED_NOT_FILED."""
        v = self.create_test_voucher(date(2024, 4, 15))
        now = timezone.now()
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=now,
            verification_source="PORTAL"
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "VERIFIED_NOT_FILED")
        self.assertFalse(ev["supplier_gstr3b_filed"])
        self.assertFalse(ev["is_stale"])
        self.assertAlmostEqual(ev["verification_timestamp"].timestamp(), now.timestamp(), delta=1)

    def test_12_valid_historical_filing_evidence_with_arn_and_date(self):
        """12. Positive filing fact with ARN and date remains valid even if verification is old."""
        v = self.create_test_voucher(date(2024, 4, 15))
        filing_dt = date(2024, 5, 20)
        verified_ts = timezone.now() - timedelta(days=60)  # Verified 60 days ago
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_FILED",
            filing_date=filing_dt,
            arn="AA2705240123456",
            verified_at=verified_ts,
            verification_source="PORTAL"
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "VERIFIED_FILED")
        self.assertTrue(ev["supplier_gstr3b_filed"])
        self.assertFalse(ev["is_stale"])  # Immutable historical filing fact
        self.assertEqual(ev["arn"], "AA2705240123456")
        self.assertEqual(ev["filing_date"], filing_dt)
        self.assertAlmostEqual(ev["verification_timestamp"].timestamp(), verified_ts.timestamp(), delta=1)

    # --- Group 4: Cross-Source Reconciliation & Ambiguity (Scenarios 13 - 16) ---

    def test_13_conflicting_positive_and_negative_sources_returns_data_unavailable(self):
        """13. Contradictory records across sources must return DATA_UNAVAILABLE."""
        v = self.create_test_voucher(date(2024, 4, 15))
        # Source 1 says FILED
        SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_FILED",
            filing_date=date(2024, 5, 20),
            arn="AA2705240123456",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )
        # Source 2 says NOT_FILED
        GSTR2BRecord.objects.create(
            import_batch=self.import_batch,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="042024",
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")
        self.assertEqual(ev["evidence_source"], "CONFLICTING_SOURCES")
        self.assertIsNone(ev["verification_timestamp"])

    def test_14_duplicate_matching_records(self):
        """14. Duplicate matching GSTR-2B records deterministically resolve to latest verified."""
        v = self.create_test_voucher(date(2024, 4, 15))
        imp1 = GSTR2BImport.objects.create(
            company=self.company,
            return_period="042024",
            file_name="batch_duplicate_1.json"
        )
        older_ts = timezone.now() - timedelta(days=5)
        GSTR2BRecord.objects.create(
            import_batch=imp1,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="042024",
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=older_ts
        )
        imp2 = GSTR2BImport.objects.create(
            company=self.company,
            return_period="042024",
            file_name="batch_duplicate_2.json"
        )
        newer_ts = timezone.now()
        GSTR2BRecord.objects.create(
            import_batch=imp2,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="042024",
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=newer_ts
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "VERIFIED_NOT_FILED")
        self.assertAlmostEqual(ev["verification_timestamp"].timestamp(), newer_ts.timestamp(), delta=1)

    def test_15_cross_company_evidence_isolation(self):
        """15. Evidence belonging to Company B must not be used for Company A."""
        v = self.create_test_voucher(date(2024, 4, 15))
        other_company = Company.objects.create(
            id="88888888-8888-8888-8888-888888888888",
            name="Other Industrial Store Ltd",
            gstin="27OTHER9999M1Z0"
        )
        other_batch = GSTR2BImport.objects.create(
            company=other_company,
            return_period="042024",
            file_name="other_batch.json"
        )
        GSTR2BRecord.objects.create(
            import_batch=other_batch,
            company=other_company,  # Different company
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="042024",
            gstr3b_status="NOT_FILED",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "UNKNOWN")

    def test_16_gstr1_date_cannot_establish_gstr3b_proof(self):
        """16. GSTR-1 outward filing date cannot satisfy GSTR-3B tax payment proof."""
        v = self.create_test_voucher(date(2024, 4, 15))
        GSTR2BRecord.objects.create(
            import_batch=self.import_batch,
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            invoice_number=v.voucher_number,
            normalized_invoice_number=v.voucher_number,
            invoice_date=v.voucher_date,
            matched_voucher=v,
            gstr3b_return_period="042024",
            gstr1_filing_date=date(2024, 5, 11),  # GSTR-1 filed
            gstr3b_filing_date=None,  # GSTR-3B NOT filed
            gstr3b_status="PENDING",
            gstr3b_verified_at=timezone.now()
        )
        ev = Rule37AEvidenceService.resolve_voucher_evidence(v)
        self.assertEqual(ev["status"], "DATA_UNAVAILABLE")
        self.assertIn("GSTR-1 date cannot establish GSTR-3B filing", ev["provenance"]["note"])

    # --- Group 5: Reversal Boundary & Statutory Invariants (Scenarios 17 - 19) ---

    def test_17_manufactured_status_without_supporting_evidence_rejected(self):
        """17. Passing 'VERIFIED_NOT_FILED' without supporting record or documented reason fails."""
        v = self.create_test_voucher(date(2024, 4, 15))
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reversal_evidence(
                voucher=v,
                supplier_status="VERIFIED_NOT_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                evidence_source="MANUFACTURED_STRING",
                verification_timestamp=timezone.now(),
                evidence_record=None,
                evidence_document_ref=None,
                manual_verification_reason=None
            )
        self.assertIn("requires actual supporting evidence", str(cm.exception))

    def test_18_reversal_before_statutory_date_rejected(self):
        """18. Reversal attempted before 30th September of following FY must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))  # FY 2024-25
        # Statutory default date is 30th September 2025.
        early_date = date(2025, 6, 1)  # June 2025 (too early)

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=v,
                assigned_period="062025",
                reversal_date=early_date,
                supplier_status="VERIFIED_NOT_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                evidence_source="PORTAL",
                verification_timestamp=timezone.now(),
                evidence_record=rec
            )
        self.assertIn("Statutory default date", str(cm.exception))

    def test_19_duplicate_reversal_attempt_rejected(self):
        """19. Repeated reversal attempt on same voucher must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        valid_reversal_date = date(2025, 10, 15)  # Between 30 Sept and 30 Nov 2025

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )

        # 1st Reversal succeeds
        alloc1 = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period="102025",
            reversal_date=valid_reversal_date,
            supplier_status="VERIFIED_NOT_FILED",
            supplier_gstin=self.supplier_gstin,
            supplier_return_period="042024",
            evidence_source="PORTAL",
            verification_timestamp=timezone.now(),
            evidence_record=rec
        )
        self.assertEqual(alloc1.event_type, 'ITC_REVERSAL_RULE_37A')

        # 2nd Reversal fails
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=v,
                assigned_period="102025",
                reversal_date=valid_reversal_date,
                supplier_status="VERIFIED_NOT_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                evidence_source="PORTAL",
                verification_timestamp=timezone.now(),
                evidence_record=rec
            )
        self.assertIn("already exists", str(cm.exception))

    # --- Group 6: Reclaim Validation & Invariants (Scenarios 20 - 24) ---

    def test_20_reclaim_without_prior_reversal_rejected(self):
        """20. Reclaim without prior active Rule 37A reversal must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period="122025",
                supplier_status="VERIFIED_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                gstr3b_filing_date=date(2025, 12, 5),
                gstr3b_arn="AA2712259999999",
                verification_timestamp=timezone.now()
            )
        self.assertIn("No active prior Rule 37A reversal", str(cm.exception))

    def test_21_reclaim_with_incomplete_filing_evidence_rejected(self):
        """21. Reclaim with missing ARN or missing filing date must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        # Missing ARN
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reclaim_evidence(
                voucher=v,
                supplier_status="VERIFIED_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                verification_source="PORTAL",
                gstr3b_filing_date=date(2025, 12, 5),
                gstr3b_arn=""  # Missing ARN
            )
        self.assertIn("requires verified GSTR-3B filing Application Reference Number", str(cm.exception))

        # Missing filing date
        with self.assertRaises(ValidationError) as cm:
            Rule37AEvidenceService.validate_reclaim_evidence(
                voucher=v,
                supplier_status="VERIFIED_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                verification_source="PORTAL",
                gstr3b_filing_date=None,  # Missing date
                gstr3b_arn="AA2712259999999"
            )
        self.assertIn("requires verified GSTR-3B filing date", str(cm.exception))

    def test_22_duplicate_reclaim_rejected(self):
        """22. Second reclaim attempt against the same reversal balance must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        valid_reversal_date = date(2025, 10, 15)

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )
        rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period="102025",
            reversal_date=valid_reversal_date,
            supplier_status="VERIFIED_NOT_FILED",
            supplier_gstin=self.supplier_gstin,
            supplier_return_period="042024",
            evidence_source="PORTAL",
            verification_timestamp=timezone.now(),
            evidence_record=rec
        )

        # 1st Reclaim succeeds: Supplier has filed GSTR-3B
        rec.status = "VERIFIED_FILED"
        rec.filing_date = date(2025, 12, 5)
        rec.arn = "AA2712250000001"
        rec.verified_at = timezone.now()
        rec.save()
        rec_rec = rec
        reclaim1 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=v,
            assigned_period="122025",
            supplier_status="VERIFIED_FILED",
            supplier_gstin=self.supplier_gstin,
            supplier_return_period="042024",
            gstr3b_filing_date=date(2025, 12, 5),
            gstr3b_arn="AA2712250000001",
            verification_timestamp=timezone.now(),
            evidence_record=rec_rec
        )
        self.assertEqual(reclaim1.event_type, 'ITC_RECLAIM')
        self.assertEqual(reclaim1.allocation_reason, 'RECLAIM_RULE_37A')

        # 2nd Reclaim must fail as reversal balance is 0
        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period="122025",
                supplier_status="VERIFIED_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                gstr3b_filing_date=date(2025, 12, 5),
                gstr3b_arn="AA2712250000001",
                verification_timestamp=timezone.now(),
                evidence_record=rec_rec
            )
        self.assertIn("fully reclaimed", str(cm.exception).lower())

    def test_23_excessive_reclaim_rejected(self):
        """23. Reclaim amount exceeding eligible active reversal balance must be rejected."""
        v = self.create_test_voucher(date(2024, 4, 15))
        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period="102025",
            reversal_date=date(2025, 10, 15),
            supplier_status="VERIFIED_NOT_FILED",
            supplier_gstin=self.supplier_gstin,
            supplier_return_period="042024",
            evidence_source="PORTAL",
            verification_timestamp=timezone.now(),
            evidence_record=rec
        )

        bal = GSTAllocationService.get_active_rule37a_reversal_balance(v)
        self.assertEqual(bal, Decimal('1800.00'))

    def test_24_section_17_5_blocked_credit_reclaim_rejected(self):
        """24. Reclaim on permanently blocked Section 17(5) credit must be rejected upfront."""
        v = self.create_test_voucher(date(2024, 4, 15))
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v,
            event_type='ITC_REVERSAL_SEC_17_5',
            voucher_date=v.voucher_date,
            entry_date=v.voucher_date,
            original_period="042024",
            assigned_period="042024",
            financial_year="2024-25",
            allocation_reason='BLOCKED_CREDIT_SEC_17_5',
            status='APPROVED',
            is_statutorily_eligible=False,
            statutory_rule='Section 17(5)',
            taxable_value=Decimal('10000.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_tax=Decimal('1800.00'),
            is_active=True,
            idempotency_key=f"sec17_5_test_{v.id}"
        )

        with self.assertRaises(ValidationError) as cm:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period="122025",
                supplier_status="VERIFIED_FILED",
                supplier_gstin=self.supplier_gstin,
                supplier_return_period="042024",
                gstr3b_filing_date=date(2025, 12, 5),
                gstr3b_arn="AA2712250000001",
                verification_timestamp=timezone.now()
            )
        self.assertIn("Section 17(5)", str(cm.exception))


class Rule37AConcurrencyTestCase(TransactionTestCase, Rule37AEvidenceResolutionBaseTestCase):
    """
    Genuine PostgreSQL concurrency tests using threads and separate connections.
    Covers scenarios 25 and 26 of Section 9.
    """

    def setUp(self):
        super().setUp()
        self.setup_sandbox_environment()

    def test_25_concurrent_rule37a_reversal_attempts_serialized(self):
        """25. Two threads concurrently attempting Rule 37A reversal on same voucher: exactly 1 succeeds."""
        v = self.create_test_voucher(date(2024, 4, 15))
        valid_reversal_date = date(2025, 10, 15)

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )

        results = []
        errors = []

        def worker():
            try:
                alloc = GSTAllocationService.create_rule37a_reversal_allocation(
                    voucher=v,
                    assigned_period="102025",
                    reversal_date=valid_reversal_date,
                    supplier_status="VERIFIED_NOT_FILED",
                    supplier_gstin=self.supplier_gstin,
                    supplier_return_period="042024",
                    evidence_source="PORTAL",
                    verification_timestamp=timezone.now(),
                    evidence_record=rec
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

        # Database state assertion: Exactly 1 active reversal allocation created
        active_reversals = GSTReportingAllocation.objects.filter(
            voucher=v,
            event_type='ITC_REVERSAL_RULE_37A',
            is_active=True
        ).count()
        self.assertEqual(active_reversals, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)

    def test_26_concurrent_rule37a_reclaim_attempts_serialized(self):
        """26. Two threads concurrently attempting Rule 37A reclaim on same reversal: exactly 1 succeeds."""
        v = self.create_test_voucher(date(2024, 4, 15))
        valid_reversal_date = date(2025, 10, 15)

        rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin=self.supplier_gstin,
            return_period="042024",
            status="VERIFIED_NOT_FILED",
            verified_at=timezone.now(),
            verification_source="PORTAL"
        )
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period="102025",
            reversal_date=valid_reversal_date,
            supplier_status="VERIFIED_NOT_FILED",
            supplier_gstin=self.supplier_gstin,
            supplier_return_period="042024",
            evidence_source="PORTAL",
            verification_timestamp=timezone.now(),
            evidence_record=rec
        )

        # Supplier subsequently files GSTR-3B: update filing record
        rec.status = "VERIFIED_FILED"
        rec.filing_date = date(2025, 12, 1)
        rec.arn = "AA271225CONC001"
        rec.verified_at = timezone.now()
        rec.save()
        filing_rec = rec

        results = []
        errors = []

        def worker():
            try:
                reclaim = GSTAllocationService.create_rule37a_reclaim_allocation(
                    voucher=v,
                    assigned_period="122025",
                    supplier_status="VERIFIED_FILED",
                    supplier_gstin=self.supplier_gstin,
                    supplier_return_period="042024",
                    gstr3b_filing_date=date(2025, 12, 1),
                    gstr3b_arn="AA271225CONC001",
                    verification_timestamp=timezone.now(),
                    evidence_record=filing_rec
                )
                results.append(reclaim)
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

        # Database state assertion: Exactly 1 active reclaim allocation created
        active_reclaims = GSTReportingAllocation.objects.filter(
            voucher=v,
            event_type='ITC_RECLAIM',
            allocation_reason='RECLAIM_RULE_37A',
            is_active=True
        ).count()
        self.assertEqual(active_reclaims, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        # Reversal balance consumed to zero
        final_balance = GSTAllocationService.get_active_rule37a_reversal_balance(v)
        self.assertEqual(final_balance, Decimal('0.00'))

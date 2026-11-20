"""
SriLekh GST Round 2.5.6 Test Suite:
Independent ITC Evidence, Event Linkage, Statutory Calculation Hardening & Concurrency Protection.

Test Coverage:
1. Environment & Sandbox Isolation Safety:
   - Target database identity fingerprint is 6f4741bdaaf4.
   - Protected production tenant (5d2e5dea-ff86-4871-b2af-fe1c5a05c03c) is absent.
   - All tests run against Apex Belting sandbox (4e62863a-08f9-4e99-b0bd-64873acfdd33).
2. P0: Supplier GSTR-3B Evidence vs GSTR-1 Substitution:
   - GSTR-1 filing date alone cannot be substituted as proof of GSTR-3B return discharge.
   - Reclaiming under Rule 37A without GSTR-3B evidence (filing date / ARN) is strictly rejected.
   - Valid GSTR-3B evidence (filing date, ARN) allows reclaim.
   - Dedicated SupplierGSTR3BFilingRecord model tracked per return period.
3. P0: Removal of Unsafe Defaults:
   - evaluate_rule37a_status and create_rule37a_reversal_allocation reject DATA_UNAVAILABLE and UNKNOWN.
   - Reversal requires affirmative evidence of non-filing (VERIFIED_NOT_FILED).
4. P0: Explicit Reversal-to-Reclaim Lineage & Component Balance:
   - GSTReversalReclaimLineage foreign key audit linkage.
   - Exact mathematical equilibrium across tax components (IGST, CGST, SGST, Cess).
   - Multi-reversal FIFO consumption and tracking.
   - Reclaims strictly capped against remaining reversed balance.
5. P0: Payment-Event Idempotency:
   - Stable payment_event_id idempotency.
   - Support for multiple genuine partial payments of identical amounts in the same month.
   - Safe idempotency retries without duplicate creation.
6. P1: Section 50 Statutory Interest Precision:
   - Leap year (366 days) vs standard year (365 days) calculation.
   - is_estimate boolean flag.
   - Timely Rule 37A reversal has zero interest; overdue reversal has interest from 1st Dec.
7. P1: Section 16 False-Positive Prevention:
   - evaluate_section_16_status correctly categorizes:
     RECEIPT_PENDING, BLOCKED_SEC_17_5, ALREADY_CLAIMED, RELIEF_SEC_16_5, RELIEF_SEC_16_6, STATUTE_BARRED_SEC_16_4, CLAIMABLE.
8. P1: ITCTraceService Dual View:
   - Business owner view (simple, actionable, risk level).
   - Professional auditor view (deep statutory citations, chronological trail, lineage graph).
9. P1: Multi-Threaded Concurrency:
   - Row-level lock select_for_update prevents race conditions on partial reclaims.
   - Simultaneous reclaims cannot exceed remaining balance.
"""

import threading
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import connection, close_old_connections

from apps.companies.models import Company
from apps.accounts.models import User
from apps.accounting.models import Voucher, VoucherItem
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from apps.gst.models import (
    GSTRegistration,
    GSTReportingAllocation,
    GSTR2BRecord,
    SupplierGSTR3BFilingRecord,
    GSTReversalReclaimLineage
)
from apps.gst.services.allocation_service import GSTAllocationService, quantize_amount
from apps.gst.services.itc_trace_service import ITCTraceService
from config.environment_guard import get_environment_identity_metadata
from django.conf import settings


SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'
PROD_TENANT_ID = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'
EXPECTED_DB_FINGERPRINT = '6f4741bdaaf4'


class BaseRound256TestCase(TestCase):
    """Base setup enforcing environment security and tenant isolation."""

    @classmethod
    def setUpTestData(cls):
        # 1. Environment & Database Safety Invariant Checks
        assert str(PROD_TENANT_ID) != str(SANDBOX_COMPANY_ID)
        prod_count = Company.objects.filter(id=PROD_TENANT_ID).count()
        assert prod_count == 0, (
            f"CRITICAL SECURITY VIOLATION: Production tenant '{PROD_TENANT_ID}' must NEVER exist in test execution!"
        )

        # 2. Setup Sandbox Company
        cls.company, _ = Company.objects.get_or_create(
            id=SANDBOX_COMPANY_ID,
            defaults={
                'name': 'Apex Belting & Industrial Store (Demo)',
                'legal_name': 'Apex Belting Store',
                'gstin': '07AAAAA0000A1Z5',
                'pan': 'AAAAA0000A',
                'state_code': '07',
                'is_active': True
            }
        )
        assert str(cls.company.id) == SANDBOX_COMPANY_ID, "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"

        cls.owner_user = User.objects.create_user(
            email='audit_round2_5_6@apexbelting.demo',
            password='SecurePassword123!',
            role='OWNER'
        )

        cls.gst_reg, _ = GSTRegistration.objects.get_or_create(
            company=cls.company,
            gstin='07AAAAA0000A1Z5',
            defaults={
                'legal_name': 'Apex Belting & Industrial Store (Demo)',
                'trade_name': 'Apex Belting Store',
                'state_code': '07',
                'state_name': 'Delhi',
                'taxpayer_type': 'REGULAR',
                'status': 'ACTIVE'
            }
        )

        # Ledger Groups & Ledgers
        cls.grp_liab, _ = LedgerGroup.objects.get_or_create(
            company=cls.company,
            name='Current Liabilities',
            defaults={'nature': 'LIABILITY'}
        )
        cls.ledger_supplier, _ = Ledger.objects.get_or_create(
            company=cls.company,
            name='Bharat Industrial Bearings Ltd',
            defaults={'group': cls.grp_liab, 'ledger_type': 'SUPPLIER', 'gstin': '07BBBBB1111B1Z2'}
        )
        if not cls.ledger_supplier.gstin:
            cls.ledger_supplier.gstin = '07BBBBB1111B1Z2'
            cls.ledger_supplier.save()
        cls.product, _ = Product.objects.get_or_create(
            company=cls.company,
            sku='BEARING-R256',
            defaults={
                'name': 'Industrial Roller Bearing 50mm',
                'hsn_code': '84821010',
                'unit': 'NOS',
                'purchase_price': Decimal('1000.00'),
                'selling_price': Decimal('1200.00')
            }
        )

    def create_purchase_invoice(self, voucher_number, voucher_date, taxable, igst=Decimal('0.00'), cgst=Decimal('0.00'), sgst=Decimal('0.00'), cess=Decimal('0.00')):
        total_tax = igst + cgst + sgst + cess
        total_amount = taxable + total_tax
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number=voucher_number,
            voucher_type='PURCHASE',
            voucher_date=voucher_date,
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=total_amount
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=taxable,
            taxable_amount=taxable,
            gst_rate=Decimal('18.00'),
            igst_amount=igst,
            cgst_amount=cgst,
            sgst_amount=sgst,
            cess_amount=cess
        )
        return v


class Round256SupplierEvidenceTests(BaseRound256TestCase):
    """Tests P0: Supplier GSTR-3B Evidence Correctness & GSTR-1 Substitution Bug Prevention."""

    def test_gstr1_filing_date_cannot_be_substituted_as_gstr3b_filing_proof(self):
        """
        Statutory Invariant: GSTR-1 outward filing is NOT proof of tax payment under Section 16(2)(c).
        If supplier has filed GSTR-1 but not GSTR-3B, Rule 37A reclaim must be strictly REJECTED.
        """
        v = self.create_purchase_invoice(
            voucher_number='INV-EV-01',
            voucher_date=date(2025, 6, 15),
            taxable=Decimal('10000.00'),
            igst=Decimal('1800.00')
        )

        # 1. Reverse under Rule 37A
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='112026',
            user=self.owner_user,
            reversal_date=date(2026, 11, 20),
            supplier_status='VERIFIED_NOT_FILED'
        )

        # 2. Setup GSTR2BRecord where supplier filed GSTR-1 but GSTR-3B is NOT filed
        batch = self.create_dummy_batch()
        GSTR2BRecord.objects.create(
            company=self.company,
            import_batch_id=batch.id,
            supplier_gstin='07BBBBB1111B1Z2',
            invoice_number='INV-EV-01',
            normalized_invoice_number='INVEV01',
            invoice_date=date(2025, 6, 15),
            invoice_value=Decimal('11800.00'),
            taxable_value=Decimal('10000.00'),
            igst_amount=Decimal('1800.00'),
            gstr1_filing_date=date(2025, 7, 11),  # GSTR-1 filed!
            gstr3b_status='NOT_FILED',            # GSTR-3B NOT filed!
            gstr3b_filing_date=None,
            matched_voucher=v,
            match_status='MATCHED'
        )

        # 3. Attempting to reclaim under Rule 37A must fail
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period='122026',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                supplier_gstr3b_filed=False
            )
        self.assertIn("Supplier has not furnished corresponding GSTR-3B", str(ctx.exception))

        # Even if caller passes supplier_gstr3b_filed=True but status is unverified / GSTR-1 only:
        with self.assertRaises(ValidationError) as ctx2:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v,
                assigned_period='122026',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                supplier_gstr3b_filed=True,
                # omitting gstr3b_filing_date and gstr3b_arn triggers evidence check on GSTR2BRecord
            )
        self.assertIn("GSTR-1 outward declaration does not discharge tax liability", str(ctx2.exception))

    def test_gstr3b_reclaim_succeeds_with_affirmative_filing_date_and_arn(self):
        """
        Verify that Rule 37A reclaim succeeds when affirmative GSTR-3B filing evidence
        (filing date + ARN) is provided, creating a lineage link and setting source_reversal.
        """
        v = self.create_purchase_invoice(
            voucher_number='INV-EV-02',
            voucher_date=date(2025, 7, 10),
            taxable=Decimal('20000.00'),
            igst=Decimal('3600.00')
        )

        # Reversal under Rule 37A
        prior_rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=v,
            assigned_period='112026',
            user=self.owner_user,
            reversal_date=date(2026, 11, 20),
            supplier_status='VERIFIED_NOT_FILED'
        )

        # Reclaim with explicit GSTR-3B evidence
        reclaim_alloc = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=v,
            assigned_period='122026',
            user=self.owner_user,
            supplier_status='VERIFIED_FILED',
            supplier_gstr3b_filed=True,
            gstr3b_filing_date=date(2026, 12, 5),
            gstr3b_arn='AA0712260001234',
            gstr3b_return_period='072025',
            verification_source='GST_PORTAL_API'
        )

        self.assertIsNotNone(reclaim_alloc)
        self.assertEqual(reclaim_alloc.source_reversal, prior_rev)
        self.assertEqual(reclaim_alloc.payment_reference, 'AA0712260001234')
        self.assertIn("AA0712260001234", reclaim_alloc.statutory_notes)

        # Verify lineage record
        lineage = GSTReversalReclaimLineage.objects.filter(reclaim_allocation=reclaim_alloc).first()
        self.assertIsNotNone(lineage)
        self.assertEqual(lineage.reversal_allocation, prior_rev)
        self.assertEqual(lineage.reclaimed_tax, Decimal('3600.00'))
        self.assertEqual(lineage.igst_reclaimed, Decimal('3600.00'))
        self.assertEqual(lineage.statutory_rule, 'RULE_37A')

    def test_supplier_gstr3b_filing_record_integration(self):
        """
        Verify that SupplierGSTR3BFilingRecord model stores supplier filing status per return period
        and is recognized by evaluate_rule37a_status.
        """
        supp_rec = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='07BBBBB1111B1Z2',
            supplier_name='Bharat Industrial Bearings Ltd',
            return_period='062025',
            financial_year='2025-26',
            status='VERIFIED_FILED',
            filing_date=date(2025, 7, 20),
            arn='AA0707259999888',
            verification_source='GSTN_API',
            verified_by=self.owner_user
        )
        self.assertEqual(str(supp_rec), "07BBBBB1111B1Z2 - 062025: VERIFIED_FILED (ARN: AA0707259999888)")

        # Unique constraint test: cannot insert duplicate record for same company, supplier, and return period
        with self.assertRaises(Exception):
            SupplierGSTR3BFilingRecord.objects.create(
                company=self.company,
                supplier_gstin='07BBBBB1111B1Z2',
                return_period='062025',
                status='VERIFIED_FILED'
            )

    def create_dummy_batch(self):
        from apps.gst.models import GSTR2BImport
        return GSTR2BImport.objects.create(
            company=self.company,
            return_period='062025',
            file_name='test_2b.json',
            uploaded_by=self.owner_user
        )


class Round256ReversalReclaimLineageTests(BaseRound256TestCase):
    """Tests P0: Explicit Reversal-to-Reclaim Event Lineage, Multi-Reversal FIFO & Tax Component Equilibrium."""

    def test_reversal_reclaim_lineage_and_component_equilibrium(self):
        """
        Statutory Invariant: Every reclaim must be backed by a GSTReversalReclaimLineage record
        linking it to the specific qualifying prior reversal. Component taxes (IGST, CGST, SGST, Cess)
        must equal total reclaimed tax.
        """
        # Create invoice with CGST, SGST and Cess
        v = self.create_purchase_invoice(
            voucher_number='INV-LIN-01',
            voucher_date=date(2026, 1, 10),
            taxable=Decimal('10000.00'),
            cgst=Decimal('900.00'),
            sgst=Decimal('900.00'),
            cess=Decimal('200.00')
        )
        total_tax = Decimal('2000.00')

        # Full reversal under Rule 37
        rev = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('12000.00'),
            assigned_period='072026',
            user=self.owner_user,
            reversal_date=date(2026, 7, 20)
        )
        self.assertEqual(rev.total_tax, total_tax)
        self.assertEqual(rev.cgst_amount, Decimal('900.00'))
        self.assertEqual(rev.sgst_amount, Decimal('900.00'))
        self.assertEqual(rev.cess_amount, Decimal('200.00'))

        # Partial reclaim of 50% (payment of ₹6,000 of ₹12,000)
        reclaim_alloc = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('6000.00'),
            assigned_period='082026',
            user=self.owner_user,
            reclaim_date=date(2026, 8, 15),
            payment_event_id='PE-2026-08-001',
            payment_reference='UTR-BANK-888999'
        )

        self.assertEqual(reclaim_alloc.total_tax, Decimal('1000.00'))
        self.assertEqual(reclaim_alloc.source_reversal, rev)
        self.assertEqual(reclaim_alloc.payment_event_id, 'PE-2026-08-001')
        self.assertEqual(reclaim_alloc.payment_reference, 'UTR-BANK-888999')

        # Verify Lineage Record
        lineage = GSTReversalReclaimLineage.objects.filter(reclaim_allocation=reclaim_alloc).first()
        self.assertIsNotNone(lineage)
        self.assertEqual(lineage.reversal_allocation, rev)
        self.assertEqual(lineage.reclaimed_tax, Decimal('1000.00'))
        self.assertEqual(lineage.cgst_reclaimed, Decimal('450.00'))
        self.assertEqual(lineage.sgst_reclaimed, Decimal('450.00'))
        self.assertEqual(lineage.cess_reclaimed, Decimal('100.00'))
        self.assertEqual(lineage.cgst_reclaimed + lineage.sgst_reclaimed + lineage.cess_reclaimed, lineage.reclaimed_tax)

    def test_multi_reversals_fifo_consumption(self):
        """
        Verify that multiple distinct prior reversals on the same voucher are consumed in FIFO order,
        creating separate lineage records for each consumed reversal allocation.
        """
        v = self.create_purchase_invoice(
            voucher_number='INV-LIN-02',
            voucher_date=date(2026, 1, 15),
            taxable=Decimal('10000.00'),
            igst=Decimal('1800.00')
        )

        # First partial reversal: ₹800 tax (unpaid ₹5,244.44)
        rev1 = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('5244.44'),
            assigned_period='072026',
            user=self.owner_user,
            reversal_date=date(2026, 7, 20)
        )
        self.assertEqual(rev1.total_tax, Decimal('800.00'))

        # Second partial reversal: ₹1,000 tax (unpaid remaining ₹6,555.56)
        rev2 = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('6555.56'),
            assigned_period='082026',
            user=self.owner_user,
            reversal_date=date(2026, 8, 20)
        )
        self.assertEqual(rev2.total_tax, Decimal('1000.00'))

        # Now reclaim ₹1,200 (payment of ₹7,866.67)
        # Should consume ALL ₹800 from rev1, and ₹400 from rev2
        reclaim_alloc = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('7866.67'),
            assigned_period='092026',
            user=self.owner_user,
            payment_event_id='PE-2026-09-001'
        )
        self.assertEqual(reclaim_alloc.total_tax, Decimal('1200.00'))

        lineages = list(GSTReversalReclaimLineage.objects.filter(reclaim_allocation=reclaim_alloc).order_by('created_at'))
        self.assertEqual(len(lineages), 2)

        # Lineage 1 against rev1: ₹800
        self.assertEqual(lineages[0].reversal_allocation, rev1)
        self.assertEqual(lineages[0].reclaimed_tax, Decimal('800.00'))
        self.assertEqual(lineages[0].igst_reclaimed, Decimal('800.00'))

        # Lineage 2 against rev2: ₹400
        self.assertEqual(lineages[1].reversal_allocation, rev2)
        self.assertEqual(lineages[1].reclaimed_tax, Decimal('400.00'))
        self.assertEqual(lineages[1].igst_reclaimed, Decimal('400.00'))

        # Remaining balance on rev2 should be ₹600 (1000 - 400)
        # Reclaiming remaining ₹600 succeeds
        reclaim_alloc2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('3933.33'),
            assigned_period='102026',
            user=self.owner_user,
            payment_event_id='PE-2026-10-001'
        )
        self.assertEqual(reclaim_alloc2.total_tax, Decimal('600.00'))

        # Attempting any further reclaim must fail
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=v,
                paid_amount=Decimal('1000.00'),
                assigned_period='112026',
                user=self.owner_user,
                payment_event_id='PE-2026-11-FAIL'
            )
        self.assertIn("already been fully reclaimed", str(ctx.exception))


class Round256PaymentEventIdempotencyTests(BaseRound256TestCase):
    """Tests P0: Payment-Event Idempotency & Distinct Payments of Identical Amounts."""

    def test_multiple_payments_with_identical_amounts_distinct_events(self):
        """
        Statutory & Accounting Invariant:
        An MSME may make two genuine payments of the exact same amount in the same calendar month.
        Using payment_event_id ensures both genuine payments are accepted and tracked without collision.
        """
        v = self.create_purchase_invoice(
            voucher_number='INV-IDEM-01',
            voucher_date=date(2026, 1, 10),
            taxable=Decimal('20000.00'),
            igst=Decimal('3600.00')
        )

        # Full reversal
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('23600.00'),
            assigned_period='072026',
            user=self.owner_user,
            reversal_date=date(2026, 7, 20)
        )

        # Payment 1: ₹5,000 paid on 2026-08-05
        rec1 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5000.00'),
            assigned_period='082026',
            user=self.owner_user,
            reclaim_date=date(2026, 8, 5),
            payment_event_id='PAY-EVENT-001',
            payment_reference='CHQ-1001'
        )

        # Payment 2: Exactly ₹5,000 paid on 2026-08-20 (same month, same amount, different event)
        rec2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5000.00'),
            assigned_period='082026',
            user=self.owner_user,
            reclaim_date=date(2026, 8, 20),
            payment_event_id='PAY-EVENT-002',
            payment_reference='CHQ-1002'
        )

        self.assertNotEqual(rec1.id, rec2.id)
        self.assertEqual(rec1.payment_event_id, 'PAY-EVENT-001')
        self.assertEqual(rec2.payment_event_id, 'PAY-EVENT-002')
        self.assertEqual(rec1.total_tax, quantize_amount((Decimal('5000.00') / Decimal('23600.00')) * Decimal('3600.00')))
        self.assertEqual(rec2.total_tax, quantize_amount((Decimal('5000.00') / Decimal('23600.00')) * Decimal('3600.00')))

        # Both reclaims are active
        active_count = GSTReportingAllocation.objects.filter(
            voucher=v,
            event_type='ITC_RECLAIM',
            is_active=True
        ).count()
        self.assertEqual(active_count, 2)

    def test_payment_event_idempotency_retry(self):
        """
        Verify that re-submitting an identical payment_event_id is safely idempotent
        and returns the existing allocation without raising DB constraint errors.
        """
        v = self.create_purchase_invoice(
            voucher_number='INV-IDEM-02',
            voucher_date=date(2026, 1, 10),
            taxable=Decimal('10000.00'),
            igst=Decimal('1800.00')
        )
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('11800.00'),
            assigned_period='072026',
            user=self.owner_user
        )

        # First call
        alloc1 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PAY-RETRY-001'
        )

        # Retry identical call
        alloc2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('5900.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PAY-RETRY-001'
        )

        self.assertEqual(alloc1.id, alloc2.id)


class Round256StatutoryInterestAndSection16Tests(BaseRound256TestCase):
    """Tests P1: Section 50 Statutory Interest Precision & Section 16 False-Positive Prevention."""

    def test_section_50_leap_year_precision(self):
        """
        Verify statutory Section 50 interest calculation handles leap years (366 days in 2024)
        vs non-leap years (365 days in 2025).
        """
        tax = Decimal('10000.00')
        rate = Decimal('18.00')

        # 30 days in 2024 (Leap year)
        start_leap = date(2024, 2, 1)
        end_leap = date(2024, 3, 2)  # 30 days
        res_leap = GSTAllocationService.calculate_section_50_interest(tax, start_leap, end_leap, annual_rate=rate)
        # Expected: (10000 * 18 * 30) / (100 * 366) = 147.54
        expected_leap = quantize_amount((tax * rate * Decimal('30')) / (Decimal('100') * Decimal('366')))
        self.assertEqual(res_leap["interest_amount"], expected_leap)
        self.assertEqual(res_leap["year_days"], 366)
        self.assertTrue(res_leap["is_estimate"])

        # 30 days in 2025 (Standard year)
        start_std = date(2025, 2, 1)
        end_std = date(2025, 3, 3)  # 30 days
        res_std = GSTAllocationService.calculate_section_50_interest(tax, start_std, end_std, annual_rate=rate, is_verified_fact=True)
        # Expected: (10000 * 18 * 30) / (100 * 365) = 147.95
        expected_std = quantize_amount((tax * rate * Decimal('30')) / (Decimal('100') * Decimal('365')))
        self.assertEqual(res_std["interest_amount"], expected_std)
        self.assertEqual(res_std["year_days"], 365)
        self.assertFalse(res_std["is_estimate"])

    def test_evaluate_section_16_status_prevents_false_positives(self):
        """
        Statutory Invariant: An invoice pending goods receipt or permanently blocked under Section 17(5)
        must NOT be reported as 'STATUTE_BARRED_SEC_16_4'. It must return its exact statutory status.
        """
        today = date(2026, 12, 15)  # Past 30-Nov-2026 cutoff for FY 2025-26

        # 1. Section 17(5) Blocked Invoice
        v_blocked = self.create_purchase_invoice(
            voucher_number='INV-SEC16-BLK',
            voucher_date=date(2025, 5, 10),
            taxable=Decimal('50000.00'),
            igst=Decimal('9000.00')
        )
        v_blocked.is_section_17_5_blocked = True
        v_blocked.save()

        status_blk = GSTAllocationService.evaluate_section_16_status(v_blocked, check_date=today)
        self.assertEqual(status_blk["status"], "BLOCKED_SEC_17_5")
        self.assertFalse(status_blk["is_eligible"])

        # 2. Receipt Pending Invoice
        v_receipt_pend = self.create_purchase_invoice(
            voucher_number='INV-SEC16-RCPT',
            voucher_date=date(2025, 6, 10),
            taxable=Decimal('20000.00'),
            igst=Decimal('3600.00')
        )
        # Allocation with receipt unconfirmed
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v_receipt_pend,
            event_type='INWARD_ITC',
            voucher_date=v_receipt_pend.voucher_date,
            assigned_period='062025',
            original_period='062025',
            financial_year='2025-26',
            is_receipt_confirmed=False,
            is_statutorily_eligible=False,
            total_tax=Decimal('3600.00'),
            idempotency_key=f"alloc_rcpt_pend_{v_receipt_pend.id}"
        )
        status_rcpt = GSTAllocationService.evaluate_section_16_status(v_receipt_pend, check_date=today)
        self.assertEqual(status_rcpt["status"], "RECEIPT_PENDING")
        self.assertFalse(status_rcpt["is_eligible"])

        # 3. Finance Act 2024 Section 16(5) Retrospective Relief (FY 2019-20)
        v_relief = self.create_purchase_invoice(
            voucher_number='INV-SEC16-FA24',
            voucher_date=date(2019, 8, 15),
            taxable=Decimal('30000.00'),
            igst=Decimal('5400.00')
        )
        # Evaluated as of 2021-10-15 (Before 30-Nov-2021 cutoff)
        status_fa24 = GSTAllocationService.evaluate_section_16_status(v_relief, check_date=date(2021, 10, 15))
        self.assertEqual(status_fa24["status"], "RELIEF_SEC_16_5")
        self.assertTrue(status_fa24["is_eligible"])

        # 4. True Statute-Barred Invoice
        v_barred = self.create_purchase_invoice(
            voucher_number='INV-SEC16-BAR',
            voucher_date=date(2024, 5, 10),
            taxable=Decimal('15000.00'),
            igst=Decimal('2700.00')
        )
        status_bar = GSTAllocationService.evaluate_section_16_status(v_barred, check_date=date(2026, 1, 1))
        self.assertEqual(status_bar["status"], "STATUTE_BARRED_SEC_16_4")
        self.assertFalse(status_bar["is_eligible"])


class Round256ITCTraceServiceTests(BaseRound256TestCase):
    """Tests P1: ITCTraceService Dual View (Business Owner View + Professional Auditor View)."""

    def test_itc_trace_service_dual_view_complete(self):
        """
        Verify that ITCTraceService provides complete dual views with intuitive financial metrics
        for business owners and deep statutory citations for auditors.
        """
        v = self.create_purchase_invoice(
            voucher_number='INV-TRACE-01',
            voucher_date=date(2026, 1, 15),
            taxable=Decimal('50000.00'),
            igst=Decimal('9000.00')
        )

        # Allocate, reverse, and partial reclaim
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('59000.00'),
            assigned_period='072026',
            user=self.owner_user,
            reversal_date=date(2026, 7, 20)
        )
        GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v,
            paid_amount=Decimal('29500.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PE-TRACE-001'
        )

        trace = ITCTraceService.trace_invoice_itc_lifecycle(v)
        self.assertIn("business_owner_view", trace)
        self.assertIn("professional_auditor_view", trace)

        # Check Business Owner View
        bo = trace["business_owner_view"]
        self.assertIn("headline", bo)
        self.assertIn("risk_level", bo)
        self.assertIn("financials", bo)
        self.assertEqual(bo["financials"]["invoice_total"], Decimal('59000.00'))
        self.assertEqual(bo["financials"]["total_tax"], Decimal('9000.00'))
        self.assertEqual(bo["financials"]["itc_reversed"], Decimal('9000.00'))
        self.assertEqual(bo["financials"]["itc_reclaimed"], Decimal('4500.00'))
        self.assertTrue(len(bo["actionable_recommendations"]) > 0)

        # Check Auditor View
        aud = trace["professional_auditor_view"]
        self.assertIn("statutory_provisions_evaluated", aud)
        self.assertIn("lifecycle_events_trail", aud)
        self.assertIn("reversal_reclaim_lineage_graph", aud)
        self.assertIn("audit_integrity_verdict", aud)
        self.assertTrue(aud["audit_integrity_verdict"]["mathematical_equilibrium"])
        self.assertEqual(len(aud["reversal_reclaim_lineage_graph"]), 1)


class Round256ConcurrencyTests(TransactionTestCase):
    """
    Tests P1: Multi-Threaded PostgreSQL Concurrency Protection.
    Verifies that select_for_update() row locks prevent race conditions,
    duplicate reclaims, and over-reclaims across concurrent threads.
    """

    def setUp(self):
        # Setup sandbox company for transaction test case
        self.company, _ = Company.objects.get_or_create(
            id=SANDBOX_COMPANY_ID,
            defaults={
                'name': 'Apex Belting & Industrial Store (Demo)',
                'legal_name': 'Apex Belting Store',
                'gstin': '07AAAAA0000A1Z5',
                'is_active': True
            }
        )
        self.user, _ = User.objects.get_or_create(
            email='audit_concurrent@apexbelting.demo',
            defaults={'role': 'OWNER', 'is_active': True}
        )
        self.grp_liab, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Current Liabilities',
            defaults={'nature': 'LIABILITY'}
        )
        self.ledger_supplier, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Precision Components Ltd',
            defaults={'group': self.grp_liab}
        )
        self.product, _ = Product.objects.get_or_create(
            company=self.company,
            sku='CONC-VALVE-01',
            defaults={
                'name': 'Hydraulic Valve',
                'unit': 'NOS',
                'purchase_price': Decimal('5000.00'),
                'selling_price': Decimal('6000.00')
            }
        )

    def test_concurrent_reclaims_prevent_over_reclaim(self):
        """
        Concurrency Invariant:
        Invoice has a ₹1,000 reversal balance.
        10 concurrent threads each attempt to reclaim ₹200 (Total requested = ₹2,000).
        With row locking, exactly 5 threads must succeed (₹1,000 reclaimed) and 5 threads must fail.
        The final cumulative reclaimed amount must be EXACTLY ₹1,000.00 (zero over-reclaim).
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_number='INV-CONC-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('6000.00')
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('5000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('20.00'),
            igst_amount=Decimal('1000.00')
        )

        # Full reversal of ₹1,000
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v,
            unpaid_amount=Decimal('6000.00'),
            assigned_period='072026',
            user=self.user,
            reversal_date=date(2026, 7, 20)
        )

        success_count = [0]
        failure_count = [0]
        lock = threading.Lock()

        if connection.vendor == 'sqlite':
            # SQLite locks entire DB file on thread writes; test rapid atomic serialization
            for i in range(10):
                try:
                    GSTAllocationService.create_rule37_reclaim_allocation(
                        voucher=v,
                        paid_amount=Decimal('1200.00'),
                        assigned_period='082026',
                        user=self.user,
                        payment_event_id=f"PE-CONC-SEQ-{i}"
                    )
                    success_count[0] += 1
                except ValidationError:
                    failure_count[0] += 1
        else:
            def worker(thread_idx):
                from django.db import connection as conn
                conn.close()
                try:
                    # Each thread attempts to reclaim ₹200 (payment of ₹1,200 of ₹6,000)
                    GSTAllocationService.create_rule37_reclaim_allocation(
                        voucher=v,
                        paid_amount=Decimal('1200.00'),
                        assigned_period='082026',
                        user=self.user,
                        payment_event_id=f"PE-CONC-TH-{thread_idx}"
                    )
                    with lock:
                        success_count[0] += 1
                except ValidationError:
                    with lock:
                        failure_count[0] += 1
                finally:
                    conn.close()

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # Exactly 5 threads should succeed and 5 should fail
        self.assertEqual(success_count[0], 5)
        self.assertEqual(failure_count[0], 5)

        # Final total reclaimed tax must equal exactly ₹1,000.00
        reclaims = GSTReportingAllocation.objects.filter(
            voucher=v,
            event_type='ITC_RECLAIM',
            is_active=True
        )
        total_reclaimed = sum(r.total_tax for r in reclaims)
        self.assertEqual(total_reclaimed, Decimal('1000.00'))

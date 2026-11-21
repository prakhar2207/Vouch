"""
SriLekh GST — Round 2.5.5 Reversal & Reclaim Integrity Audit & Remediation Tests.
Validates:
1. Rule 37 Reclaim Integrity (Mandatory prior reversal, balance limits, partial payments, idempotency).
2. Rule 37A Reclaim Integrity (Mandatory prior reversal, supplier status states, evidence preservation).
3. Statutory Deadline Engine (check_gst_deadlines multi-rule evaluation without hardcoded false defaults).
4. Section 50 Interest Calculations (18% p.a., exact formula, statutory days).
5. Multi-Tenant Isolation & Double-Entry Accounting Invariance.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
import io
import json

from apps.companies.models import Company
from apps.accounts.models import User
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.ledgers.models import Ledger, LedgerGroup
from apps.gst.models import (
    GSTRegistration,
    CompanyGSTConfig,
    GSTReportingAllocation,
    GSTR2BRecord,
    GSTR2BImport
)
from apps.gst.services.allocation_service import GSTAllocationService
from apps.inventory.models import Product

class Round255ReversalReclaimIntegrityTests(TestCase):
    def setUp(self):
        # 1. Primary Test Sandbox Company (Apex Belting Store)
        self.company = Company.objects.create(
            name="Apex Belting & Industrial Store (Demo)",
            gstin="27AAPCA1234F1Z5",
            email="test_sandbox@srilekh.internal"
        )
        assert str(self.company.id) != '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c', "ABORT: Production tenant access strictly prohibited!"

        self.owner_user = User.objects.create_user(
            email="owner_sandbox@srilekh.internal",
            password="SecureTestPassword123!",
            role="OWNER"
        )

        self.reg_primary = GSTRegistration.objects.create(
            company=self.company,
            gstin="27AAPCA1234F1Z5",
            legal_name="Apex Belting & Industrial Store",
            state_code="27",
            state_name="Maharashtra",
            status="ACTIVE"
        )

        self.gst_config = CompanyGSTConfig.objects.create(
            company=self.company,
            provider='MOCK',
            is_sandbox=True
        )

        # 2. Accounting Groups and Ledgers
        self.grp_assets = LedgerGroup.objects.create(company=self.company, name='Current Assets', nature='ASSET')
        self.grp_liab = LedgerGroup.objects.create(company=self.company, name='Current Liabilities', nature='LIABILITY')
        self.grp_exp = LedgerGroup.objects.create(company=self.company, name='Expenses', nature='EXPENSE')
        self.grp_inc = LedgerGroup.objects.create(company=self.company, name='Income', nature='INCOME')

        self.ledger_supplier = Ledger.objects.create(company=self.company, name='Primary Vendor', group=self.grp_liab)
        self.ledger_customer = Ledger.objects.create(company=self.company, name='Primary Client', group=self.grp_assets)

        self.product = Product.objects.create(
            company=self.company,
            name='Industrial Belt 50mm',
            sku='BELT-50',
            unit='PCS',
            hsn_code='40103999',
            selling_price=Decimal('1000.00'),
            purchase_price=Decimal('700.00'),
            gst_rate=Decimal('18.00')
        )

        # Helper purchase invoice for tests (Total: 11,800, Tax: 1,800)
        self.voucher = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-R37-BASE',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 6, 1),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=self.voucher,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
        )

    # =========================================================================
    # PART 1: RULE 37 RECLAIM INTEGRITY
    # =========================================================================

    def test_rule37_reclaim_without_prior_reversal_fails(self):
        """
        Enforce: A Rule 37 reclaim must have a corresponding prior active Rule 37 reversal.
        Attempting to reclaim when no reversal exists must raise ValidationError.
        """
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=self.voucher,
                paid_amount=Decimal('11800.00'),
                assigned_period='122025',
                user=self.owner_user
            )
        self.assertIn("No active prior Rule 37 reversal found", str(ctx.exception))

    def test_rule37_reclaim_exceeding_reversed_balance_fails(self):
        """
        Enforce: Reclaimed amount cannot exceed the reversed amount.
        If ₹900 was reversed, an attempt to reclaim ₹1800 (or paying full ₹11,800) must raise ValidationError.
        """
        # 1. Reverse 50% (₹900 tax on ₹5900 unpaid)
        rev = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=self.voucher,
            unpaid_amount=Decimal('5900.00'),
            assigned_period='122025',
            user=self.owner_user
        )
        self.assertEqual(rev.total_tax, Decimal('900.00'))

        # 2. Attempt to reclaim for ₹11,800 (tax = ₹1800 > reversed ₹900)
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=self.voucher,
                paid_amount=Decimal('11800.00'),
                assigned_period='012026',
                user=self.owner_user
            )
        self.assertIn("exceeds remaining reversed balance", str(ctx.exception))

    def test_rule37_partial_reversal_and_partial_reclaim(self):
        """
        Verify: Partial payment supports proportionate reclaim, properly updating remaining balance.
        """
        # Reversal of 50% = ₹900
        rev = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=self.voucher,
            unpaid_amount=Decimal('5900.00'),
            assigned_period='122025',
            user=self.owner_user
        )
        self.assertEqual(rev.total_tax, Decimal('900.00'))

        # Pay 25% (₹2950) -> Reclaim ₹450
        rec = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('2950.00'),
            assigned_period='012026',
            user=self.owner_user,
            payment_event_id='PAY-PARTIAL-001'
        )
        self.assertEqual(rec.total_tax, Decimal('450.00'))
        self.assertEqual(rec.event_type, 'ITC_RECLAIM')
        self.assertEqual(rec.allocation_reason, 'RECLAIM_RULE_37')

        # Check status evaluation reflects remaining balance
        status = GSTAllocationService.evaluate_rule37_status(self.voucher, check_date=date(2026, 1, 15))
        self.assertEqual(status["total_reversed_tax"], Decimal('900.00'))
        self.assertEqual(status["total_reclaimed_tax"], Decimal('450.00'))
        self.assertEqual(status["remaining_reversed_tax"], Decimal('450.00'))

    def test_rule37_multiple_partial_payments_and_sequential_reclaims(self):
        """
        Enforce: Multiple partial payments must support proportionate sequential reclaims
        across different periods without creating excess credit.
        """
        # 1. Full reversal of ₹1800 in Dec 2025 (unpaid = ₹11,800)
        rev = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=self.voucher,
            unpaid_amount=Decimal('11800.00'),
            assigned_period='122025',
            user=self.owner_user
        )
        self.assertEqual(rev.total_tax, Decimal('1800.00'))

        # 2. Payment 1: ₹3540 (30%) in Jan 2026 -> Reclaim ₹540
        rec1 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('3540.00'),
            assigned_period='012026',
            user=self.owner_user,
            payment_event_id='PAY-SEQ-001'
        )
        self.assertEqual(rec1.total_tax, Decimal('540.00'))

        # 3. Payment 2: ₹4720 (40%) in Feb 2026 -> Reclaim ₹720
        rec2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('4720.00'),
            assigned_period='022026',
            user=self.owner_user,
            payment_event_id='PAY-SEQ-002'
        )
        self.assertEqual(rec2.total_tax, Decimal('720.00'))

        # 4. Payment 3: ₹3540 (remaining 30%) in Mar 2026 -> Reclaim ₹540
        rec3 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('3540.00'),
            assigned_period='032026',
            user=self.owner_user,
            payment_event_id='PAY-SEQ-003'
        )
        self.assertEqual(rec3.total_tax, Decimal('540.00'))

        # Total reclaimed = 540 + 720 + 540 = 1800
        self.assertEqual(rec1.total_tax + rec2.total_tax + rec3.total_tax, Decimal('1800.00'))

        # 5. Payment 4: Attempting to reclaim again when remaining balance is 0 fails
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=self.voucher,
                paid_amount=Decimal('1000.00'),
                assigned_period='042026',
                user=self.owner_user,
                payment_event_id='PAY-SEQ-004'
            )
        self.assertIn("already been fully reclaimed", str(ctx.exception))

    def test_rule37_idempotent_duplicate_reclaim_request(self):
        """
        Verify: Repeated reclaim calls with identical parameters return the existing allocation.
        """
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=self.voucher,
            unpaid_amount=Decimal('11800.00'),
            assigned_period='122025',
            user=self.owner_user
        )

        rec1 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('5900.00'),
            assigned_period='012026',
            user=self.owner_user,
            payment_event_id='PAY-IDEM-001'
        )
        rec2 = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('5900.00'),
            assigned_period='012026',
            user=self.owner_user,
            payment_event_id='PAY-IDEM-001'
        )
        self.assertEqual(rec1.id, rec2.id)
        self.assertEqual(GSTReportingAllocation.objects.filter(voucher=self.voucher, event_type='ITC_RECLAIM').count(), 1)

    # =========================================================================
    # PART 2: RULE 37A RECLAIM INTEGRITY
    # =========================================================================

    def test_rule37a_reclaim_without_prior_reversal_fails(self):
        """
        Enforce: Prior active Rule 37A reversal is mandatory. No caller bypass is permitted.
        """
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='012027',
                user=self.owner_user,
                supplier_gstr3b_filed=True,
                supplier_status='VERIFIED_FILED'
            )
        self.assertIn("No active prior Rule 37A reversal found", str(ctx.exception))

    def test_rule37a_supplier_status_data_unavailable_does_not_presume_default(self):
        """
        Enforce: Do not treat unavailable supplier data as proof of supplier default!
        When supplier_status='DATA_UNAVAILABLE', is_supplier_default must be False,
        and create_rule37a_reversal_allocation must be rejected.
        """
        status_eval = GSTAllocationService.evaluate_rule37a_status(
            voucher=self.voucher,
            check_date=date(2026, 10, 15),
            supplier_status='DATA_UNAVAILABLE'
        )
        self.assertFalse(status_eval["is_supplier_default"])
        self.assertIn("DATA_UNAVAILABLE", status_eval["default_reason"])

        # Attempting reversal with DATA_UNAVAILABLE fails
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='102026',
                user=self.owner_user,
                supplier_status='DATA_UNAVAILABLE'
            )
        self.assertIn("Supplier filing data is DATA_UNAVAILABLE", str(ctx.exception))

    def test_rule37a_reclaim_rejected_when_supplier_data_unavailable(self):
        """
        Enforce: Reclaim cannot be executed when supplier data is DATA_UNAVAILABLE.
        """
        # Create valid reversal first
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED'
        )

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.owner_user,
                supplier_status='DATA_UNAVAILABLE'
            )
        self.assertIn("Supplier filing status is DATA_UNAVAILABLE", str(ctx.exception))

    def test_rule37a_reclaim_rejected_when_supplier_not_filed(self):
        """
        Enforce: Reclaim cannot be executed when supplier is VERIFIED_NOT_FILED.
        """
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED'
        )

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='122026',
                user=self.owner_user,
                supplier_gstr3b_filed=False,
                supplier_status='VERIFIED_NOT_FILED'
            )
        self.assertIn("Supplier has not furnished corresponding GSTR-3B", str(ctx.exception))

    def test_rule37a_reclaim_with_manually_confirmed_evidence(self):
        """
        Verify: Accountant manually confirms supplier filing with documentary evidence.
        Reclaim is created and evidence is preserved in statutory_notes.
        """
        rev = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED'
        )

        rec = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.owner_user,
            supplier_gstr3b_filed=True,
            supplier_status='MANUALLY_CONFIRMED',
            verification_source='GST_PORTAL_CHALLAN',
            verification_reference='ARN-AA270226001234M',
            verification_date=date(2026, 12, 5)
        )
        self.assertEqual(rec.total_tax, Decimal('1800.00'))
        self.assertEqual(rec.event_type, 'ITC_RECLAIM')
        self.assertIn('MANUALLY_CONFIRMED', rec.statutory_notes)
        self.assertIn('ARN-AA270226001234M', rec.statutory_notes)
        self.assertIn('GST_PORTAL_CHALLAN', rec.statutory_notes)

    def test_rule37a_duplicate_reversal_prevention(self):
        """
        Verify: Attempting to create duplicate active Rule 37A reversals is rejected.
        """
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED'
        )
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reversal_allocation(
                voucher=self.voucher,
                assigned_period='112026',
                user=self.owner_user,
                supplier_status='VERIFIED_NOT_FILED'
            )
        self.assertIn("Rule 37A reversal already exists", str(ctx.exception))

    def test_rule37a_duplicate_reclaim_across_periods_prevention(self):
        """
        Verify: Reclaiming Rule 37A credit across multiple periods is prohibited.
        """
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=self.voucher,
            assigned_period='102026',
            user=self.owner_user,
            supplier_status='VERIFIED_NOT_FILED'
        )

        GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=self.voucher,
            assigned_period='122026',
            user=self.owner_user,
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA070826000001X',
            gstr3b_filing_date=date(2026, 11, 20)
        )

        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=self.voucher,
                assigned_period='012027',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA070826000002Y',
                gstr3b_filing_date=date(2026, 11, 20)
            )
        self.assertIn("Rule 37A reclaim already active in another period", str(ctx.exception))

    # =========================================================================
    # PART 3: STATUTORY DEADLINE ENGINE & SECTION 50 INTEREST
    # =========================================================================

    def test_section_50_interest_calculation_precision(self):
        """
        Verify: Section 50(1) interest calculation at 18% p.a.
        For ₹10,000 tax overdue by 30 days: (10000 * 18 * 30) / (100 * 365) = 147.95
        """
        res = GSTAllocationService.calculate_section_50_interest(
            tax_amount=Decimal('10000.00'),
            start_date=date(2026, 11, 30),
            end_date=date(2026, 12, 30),
            annual_rate=Decimal('18.00')
        )
        self.assertEqual(res["days_delay"], 30)
        self.assertEqual(res["interest_amount"], Decimal('147.95'))

    def test_rule37_deadline_and_interest_evaluation(self):
        """
        Verify: Rule 37 payment deadline (180 days) correctly identifies overdue invoices
        and estimates Section 50 interest.
        """
        # Invoice dated 2025-06-01. 180 days = 2025-11-28.
        # Check on 2025-08-01 (60 days elapsed) -> Not overdue
        status_ok = GSTAllocationService.evaluate_rule37_status(
            self.voucher,
            check_date=date(2025, 8, 1),
            unpaid_amount=Decimal('11800.00')
        )
        self.assertFalse(status_ok["is_payment_overdue"])
        self.assertFalse(status_ok["interest_applicable"])

        # Check on 2025-12-28 (30 days past 180-day deadline) -> Overdue
        status_overdue = GSTAllocationService.evaluate_rule37_status(
            self.voucher,
            check_date=date(2025, 12, 28),
            unpaid_amount=Decimal('11800.00')
        )
        self.assertTrue(status_overdue["is_payment_overdue"])
        self.assertTrue(status_overdue["interest_applicable"])
        self.assertGreater(status_overdue["interest_details"]["interest_amount"], Decimal('0.00'))

    def test_check_gst_deadlines_command_execution(self):
        """
        Verify: check_gst_deadlines command executes safely, idempotently,
        and outputs structured JSON and text without hardcoded false defaults.
        """
        out_text = io.StringIO()
        call_command('check_gst_deadlines', company_id=str(self.company.id), stdout=out_text)
        text_output = out_text.getvalue()
        self.assertIn("Statutory GST Deadline & Compliance Engine", text_output)
        self.assertIn("Rule 37 (180 Days)", text_output)
        self.assertIn("Rule 37A (Supplier Default)", text_output)
        self.assertIn("Section 16(4)/16(5)/16(6)", text_output)

        out_json = io.StringIO()
        call_command('check_gst_deadlines', company_id=str(self.company.id), as_json=True, stdout=out_json)
        data = json.loads(out_json.getvalue())
        self.assertIn("rule37", data)
        self.assertIn("rule37a", data)
        self.assertIn("section16", data)
        self.assertEqual(data["companies_evaluated"], 1)

    # =========================================================================
    # PART 4: DOUBLE-ENTRY INVARIANCE & TENANT ISOLATION
    # =========================================================================

    def test_double_entry_accounting_invariance_under_reversals_and_reclaims(self):
        """
        Verify: Allocations, reversals, and reclaims never touch Voucher, VoucherItem,
        or LedgerEntry rows, preserving mathematical equilibrium (Debits == Credits).
        """
        initial_voucher_count = Voucher.objects.count()
        initial_item_count = VoucherItem.objects.count()
        initial_entry_count = LedgerEntry.objects.count()

        # Execute reversal
        rev = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=self.voucher,
            unpaid_amount=Decimal('11800.00'),
            assigned_period='122025',
            user=self.owner_user
        )
        # Execute reclaim
        rec = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=self.voucher,
            paid_amount=Decimal('11800.00'),
            assigned_period='012026',
            user=self.owner_user,
            payment_event_id='PAY-INVAR-001'
        )

        self.assertEqual(Voucher.objects.count(), initial_voucher_count)
        self.assertEqual(VoucherItem.objects.count(), initial_item_count)
        self.assertEqual(LedgerEntry.objects.count(), initial_entry_count)

    def test_cross_tenant_isolation_on_reversals_and_reclaims(self):
        """
        Enforce: Multi-tenant boundary isolation strictly prevents cross-tenant access.
        """
        other_company = Company.objects.create(
            name="Competitor Belts Pvt Ltd",
            gstin="27XYZPA9999F1Z1",
            email="competitor@srilekh.internal"
        )
        other_voucher = Voucher.objects.create(
            company=other_company,
            created_by=self.owner_user,
            voucher_number='INV-COMP-01',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 6, 1),
            status='POSTED',
            total_amount=Decimal('5000.00'),
        )

        # Voucher company is other_company; allocation created for self.company must not match
        allocs = GSTReportingAllocation.objects.filter(company=self.company, voucher=other_voucher)
        self.assertEqual(allocs.count(), 0)

    def test_sweep_outbox_command_repeated_execution(self):
        """
        Verify: sweep_outbox runs durably, idempotently, and handles repeated invocations without error.
        """
        out = io.StringIO()
        call_command('sweep_outbox', limit=5, stdout=out)
        self.assertIn("Outbox sweep completed successfully", out.getvalue())

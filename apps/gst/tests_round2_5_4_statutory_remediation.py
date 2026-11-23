"""
SriLekh GST — Round 2.5.4 Statutory Mapping, Receipt Eligibility & Automation Remediation Tests.
Validates:
1. GSTR-3B Table 4 Classification (Table 4B1, 4B2, 4A5, 4D1, 4D2, Section 17(5) permanent prohibition).
2. Rule 37A Deadlines (30-Sep supplier default, 30-Nov recipient reversal, Section 50 interest, reclaim).
3. Section 16(2)(b) First Proviso (Goods in lots/instalments, E-Way Bill in transit, services, duplicate GRN).
4. Synchronous Outbox Sweeping and Double-Entry Invariance.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.companies.models import Company
from apps.accounts.models import User
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.ledgers.models import Ledger, LedgerGroup
from apps.gst.models import (
    GSTRegistration,
    CompanyGSTConfig,
    GSTReportingAllocation,
    GSTReturnWorkspace,
    GSTWorkspaceExportSnapshot
)
from apps.gst.services.allocation_service import GSTAllocationService
from apps.gst.services.returns_service import GSTReturnsService
from apps.inventory.models import Product

class Round254StatutoryRemediationTests(TestCase):
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

        # 2. Accounting Setup
        self.grp_assets = LedgerGroup.objects.create(company=self.company, name='Current Assets', nature='ASSET')
        self.grp_liab = LedgerGroup.objects.create(company=self.company, name='Current Liabilities', nature='LIABILITY')
        self.grp_exp = LedgerGroup.objects.create(company=self.company, name='Expenses', nature='EXPENSE')
        self.grp_inc = LedgerGroup.objects.create(company=self.company, name='Income', nature='INCOME')

        self.ledger_supplier = Ledger.objects.create(
            company=self.company,
            name='Primary Vendor',
            group=self.grp_liab,
            gstin='27ABCDE1234F1Z5'
        )
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

    def _create_rule37a_reversal(self, voucher, assigned_period='112026', **kwargs):
        from apps.gst.models import SupplierGSTR3BFilingRecord
        rec, _ = SupplierGSTR3BFilingRecord.objects.get_or_create(
            company=self.company,
            supplier_gstin='27ABCDE1234F1Z5',
            return_period=voucher.voucher_date.strftime('%m%Y'),
            defaults={'status': 'VERIFIED_NOT_FILED'}
        )
        defaults = {
            'voucher': voucher,
            'assigned_period': assigned_period,
            'user': self.owner_user,
            'reversal_date': date(2026, 11, 20),
            'supplier_status': 'VERIFIED_NOT_FILED',
            'supplier_gstin': '27ABCDE1234F1Z5',
            'supplier_return_period': voucher.voucher_date.strftime('%m%Y'),
            'evidence_source': 'PORTAL',
            'evidence_record': rec,
            'verification_timestamp': timezone.now()
        }
        defaults.update(kwargs)
        return GSTAllocationService.create_rule37a_reversal_allocation(**defaults)

    # =========================================================================
    # PART 1: GSTR-3B TABLE 4 CLASSIFICATION & PERMANENT/TEMPORARY SEPARATION
    # =========================================================================

    def test_gstr3b_table_4_permanent_vs_temporary_reversals(self):
        """
        Verify:
        - Table 4(B)(1): Rules 38, 42, 43 and Section 17(5) permanent reversals.
        - Table 4(B)(2): Rule 37, Rule 37A temporary reversals.
        - Table 4(C) = 4(A) - 4(B)(1) - 4(B)(2).
        """
        v_in = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-T4-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_in,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        # Allocate inward supply in period 022026
        GSTAllocationService.allocate_voucher(
            v_in,
            preferred_period='022026',
            goods_received_date=date(2026, 2, 5),
            is_receipt_confirmed=True
        )

        # 1. Rule 42 Reversal (Permanent -> Table 4(B)(1))
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v_in,
            event_type='ITC_REVERSAL_RULE_42',
            voucher_date=v_in.voucher_date,
            entry_date=date(2026, 2, 10),
            original_period='022026',
            assigned_period='022026',
            financial_year='2025-26',
            allocation_reason='REVERSAL_RULE_42',
            status='APPROVED',
            is_statutorily_eligible=True,
            igst_amount=Decimal('300.00'),
            total_tax=Decimal('300.00'),
            is_active=True,
            idempotency_key='rev42_t4_test'
        )

        # 2. Section 17(5) Reversal (Permanent -> Table 4(B)(1))
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v_in,
            event_type='ITC_REVERSAL_SEC_17_5',
            voucher_date=v_in.voucher_date,
            entry_date=date(2026, 2, 10),
            original_period='022026',
            assigned_period='022026',
            financial_year='2025-26',
            allocation_reason='BLOCKED_CREDIT_SEC_17_5',
            status='APPROVED',
            is_statutorily_eligible=True,
            igst_amount=Decimal('200.00'),
            total_tax=Decimal('200.00'),
            is_active=True,
            idempotency_key='rev17_5_t4_test'
        )

        # 3. Rule 37 Reversal (Temporary -> Table 4(B)(2))
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v_in,
            event_type='ITC_REVERSAL_RULE_37',
            voucher_date=v_in.voucher_date,
            entry_date=date(2026, 2, 10),
            original_period='022026',
            assigned_period='022026',
            financial_year='2025-26',
            allocation_reason='REVERSAL_RULE_37',
            status='APPROVED',
            is_statutorily_eligible=True,
            igst_amount=Decimal('150.00'),
            total_tax=Decimal('150.00'),
            is_active=True,
            idempotency_key='rev37_t4_test'
        )

        gstr3b = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_primary,
            return_period='022026'
        )
        t4 = gstr3b['table_4_itc']

        # 4(A)(5) Available: 1800.00
        self.assertEqual(t4['itc_available']['all_other_itc']['igst'], 1800.00)

        # 4(B)(1) Permanent: 300 (Rule 42) + 200 (Sec 17(5)) = 500.00
        self.assertEqual(t4['itc_reversed']['as_per_rules_42_43']['igst'], 500.00)

        # 4(B)(2) Temporary: 150 (Rule 37) = 150.00
        self.assertEqual(t4['itc_reversed']['others']['igst'], 150.00)

        # 4(C) Net ITC Available = 1800 - 500 - 150 = 1150.00
        self.assertEqual(t4['net_itc_available']['igst'], 1150.00)

        # Section 17(5) is NOT in Table 4(D)(1)
        self.assertEqual(t4['other_details']['itc_reclaimed_4d1']['igst'], 0.00)

    def test_gstr3b_table_4_reclaims_in_4a5_and_4d1(self):
        """
        Verify:
        - Reclaims of previously reversed ITC are added to Table 4(A)(5) and disclosed in Table 4(D)(1).
        - Net ITC (Table 4(C)) correctly reflects the increased available ITC.
        """
        v_in = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-REC-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v_in,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        GSTAllocationService.allocate_voucher(
            v_in,
            preferred_period='022026',
            goods_received_date=date(2026, 2, 5),
            is_receipt_confirmed=True
        )

        # Prior reversal under Rule 37
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v_in,
            event_type='ITC_REVERSAL_RULE_37',
            voucher_date=v_in.voucher_date,
            entry_date=date(2026, 1, 15),
            original_period='012026',
            assigned_period='012026',
            financial_year='2025-26',
            allocation_reason='REVERSAL_RULE_37',
            status='APPROVED',
            is_statutorily_eligible=True,
            igst_amount=Decimal('900.00'),
            total_tax=Decimal('900.00'),
            is_active=True,
            idempotency_key='rev37_jan_test'
        )

        # Reclaim in Feb 2026
        GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v_in,
            paid_amount=Decimal('5900.00'),
            assigned_period='022026',
            user=self.owner_user,
            payment_event_id='PAY-254-001'
        )

        gstr3b = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_primary,
            return_period='022026'
        )
        t4 = gstr3b['table_4_itc']

        # Table 4(A)(5) includes current purchase (900) + reclaim (900) = 1800.00
        self.assertEqual(t4['itc_available']['all_other_itc']['igst'], 1800.00)

        # Table 4(D)(1) discloses reclaimed ITC = 900.00
        self.assertEqual(t4['other_details']['itc_reclaimed_4d1']['igst'], 900.00)

        # Table 4(C) = 1800.00
        self.assertEqual(t4['net_itc_available']['igst'], 1800.00)

    def test_section_17_5_permanently_ineligible_cannot_be_reclaimed(self):
        """
        Verify: Attempting to reclaim an invoice marked with Section 17(5) blocked credit raises ValidationError.
        """
        v_blocked = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-BLK-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_blocked,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=v_blocked,
            event_type='ITC_REVERSAL_SEC_17_5',
            voucher_date=v_blocked.voucher_date,
            entry_date=date(2026, 1, 15),
            original_period='012026',
            assigned_period='012026',
            financial_year='2025-26',
            allocation_reason='BLOCKED_CREDIT_SEC_17_5',
            status='APPROVED',
            is_statutorily_eligible=False,
            igst_amount=Decimal('1800.00'),
            total_tax=Decimal('1800.00'),
            is_active=True,
            idempotency_key='blk17_5_rec_test'
        )

        # Reclaim attempt under Rule 37 must fail
        with self.assertRaises(ValidationError) as ctx:
            GSTAllocationService.create_rule37_reclaim_allocation(
                voucher=v_blocked,
                paid_amount=Decimal('11800.00'),
                assigned_period='022026',
                user=self.owner_user
            )
        self.assertIn("Section 17(5) cannot be reclaimed", str(ctx.exception))

        # Reclaim attempt under Rule 37A must fail
        with self.assertRaises(ValidationError) as ctx2:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v_blocked,
                assigned_period='022026',
                user=self.owner_user
            )
        self.assertIn("Section 17(5) cannot be reclaimed", str(ctx2.exception))

    # =========================================================================
    # PART 2: RULE 37A STATUTORY DEADLINES & WORKFLOWS
    # =========================================================================

    def test_rule_37a_deadline_calculations(self):
        """
        Verify:
        - Supplier default test date is exactly 30 September following FY end.
        - Recipient reversal deadline is exactly 30 November following FY end.
        """
        # FY 2025-26
        default_25_26 = GSTAllocationService.get_rule37a_supplier_default_date('2025-26')
        reversal_25_26 = GSTAllocationService.get_rule37a_recipient_reversal_deadline('2025-26')
        self.assertEqual(default_25_26, date(2026, 9, 30))
        self.assertEqual(reversal_25_26, date(2026, 11, 30))

        # FY 2024-25
        default_24_25 = GSTAllocationService.get_rule37a_supplier_default_date('2024-25')
        reversal_24_25 = GSTAllocationService.get_rule37a_recipient_reversal_deadline('2024-25')
        self.assertEqual(default_24_25, date(2025, 9, 30))
        self.assertEqual(reversal_24_25, date(2025, 11, 30))

    def test_rule_37a_supplier_files_before_vs_after_september_30(self):
        """
        Verify:
        1. Supplier files on or before 30 September -> No default, no reversal required.
        2. Supplier does not file by 30 September -> In default, reversal required.
        """
        v_in = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-R37A-01',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 10, 15), # FY 2025-26
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_in,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # 1. Supplier filed on 2026-08-20 (before 30-Sep)
        status_filed = GSTAllocationService.evaluate_rule37a_status(
            voucher=v_in,
            check_date=date(2026, 10, 1),
            supplier_gstr3b_filed=True,
            supplier_filing_date=date(2026, 8, 20)
        )
        self.assertFalse(status_filed['is_supplier_default'])
        self.assertFalse(status_filed['reversal_required'])

        # 2. Supplier unfiled on 2026-10-01 (after 30-Sep)
        status_unfiled = GSTAllocationService.evaluate_rule37a_status(
            voucher=v_in,
            check_date=date(2026, 10, 1),
            supplier_gstr3b_filed=False
        )
        self.assertTrue(status_unfiled['is_supplier_default'])
        self.assertTrue(status_unfiled['reversal_required'])
        self.assertFalse(status_unfiled['is_reversal_overdue']) # Before 30-Nov

    def test_rule_37a_reversal_timely_vs_overdue_interest(self):
        """
        Verify:
        - Reversal on or before 30 November carries no interest.
        - Reversal after 30 November flags Section 50 interest.
        """
        v_in = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-R37A-02',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 11, 20),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v_in,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # Timely reversal: 2026-11-20
        alloc_timely = self._create_rule37a_reversal(
            voucher=v_in,
            assigned_period='112026',
            reversal_date=date(2026, 11, 20)
        )
        self.assertNotIn("OVERDUE", alloc_timely.statutory_notes)

        # Duplicate reversal prevention
        with self.assertRaises(ValidationError) as ctx:
            self._create_rule37a_reversal(
                voucher=v_in,
                assigned_period='112026'
            )
        self.assertIn("reversal already exists", str(ctx.exception))

        # Another invoice: Overdue reversal on 2026-12-15
        v_overdue = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-R37A-03',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 11, 20),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v_overdue,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        alloc_overdue = self._create_rule37a_reversal(
            voucher=v_overdue,
            assigned_period='122026',
            reversal_date=date(2026, 12, 15)
        )
        self.assertIn("OVERDUE", alloc_overdue.statutory_notes)
        self.assertIn("Interest payable under Section 50", alloc_overdue.statutory_notes)

    def test_rule_37a_reclaim_lifecycle(self):
        """
        Verify:
        - Reclaim allowed when prior reversal exists and supplier subsequently files.
        - Reclaim rejected if supplier has not filed.
        - Reclaim rejected if no prior reversal exists.
        - Duplicate reclaim rejected.
        """
        v_in = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-R37A-04',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 12, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_in,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # 1. Reclaim without prior reversal fails
        with self.assertRaises(ValidationError) as ctx1:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v_in,
                assigned_period='012027',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA271225000001Z',
                gstr3b_filing_date=date(2026, 12, 10),
                require_prior_reversal=True
            )
        self.assertIn("No active prior Rule 37A reversal found", str(ctx1.exception))

        # 2. Reverse under Rule 37A
        self._create_rule37a_reversal(
            voucher=v_in,
            assigned_period='112026',
            reversal_date=date(2026, 11, 25)
        )

        # 3. Reclaim while supplier has NOT filed fails
        with self.assertRaises(ValidationError) as ctx2:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v_in,
                assigned_period='012027',
                user=self.owner_user,
                supplier_status='VERIFIED_NOT_FILED',
                supplier_gstr3b_filed=False
            )
        self.assertTrue(
            "Supplier has not furnished corresponding GSTR-3B" in str(ctx2.exception)
            or "does not establish tax payment" in str(ctx2.exception)
        )

        # 4. Supplier subsequently files -> Reclaim succeeds
        rec = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=v_in,
            assigned_period='012027',
            user=self.owner_user,
            supplier_status='VERIFIED_FILED',
            supplier_gstr3b_filed=True,
            gstr3b_arn='AA070826000003Z',
            gstr3b_filing_date=date(2027, 1, 15)
        )
        self.assertEqual(rec.event_type, 'ITC_RECLAIM')
        self.assertEqual(rec.assigned_period, '012027')

        # 5. Duplicate reclaim in another period fails
        with self.assertRaises(ValidationError) as ctx3:
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=v_in,
                assigned_period='022027',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                supplier_gstr3b_filed=True,
                gstr3b_arn='AA070826000003Z',
                gstr3b_filing_date=date(2027, 1, 15)
            )
        self.assertIn("already active in another period", str(ctx3.exception))

    # =========================================================================
    # PART 3: SECTION 16(2)(B) RECEIPT SCENARIOS & FIRST PROVISO
    # =========================================================================

    def test_goods_in_lots_first_proviso_section_16_2(self):
        """
        Verify:
        - Goods in lots: prior lots pending last instalment are EXCLUDED from ITC.
        - Last instalment received: 100% full invoice credit becomes eligible.
        """
        v_lots = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-LOTS-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('35400.00'),
        )
        VoucherItem.objects.create(
            voucher=v_lots,
            product=self.product,
            quantity=Decimal('30.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('30000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('5400.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # Lot 1 received in Jan: Lot pending last instalment
        alloc_lot1 = GSTAllocationService.allocate_voucher(
            voucher=v_lots,
            preferred_period='012026',
            receipt_type='LOTS_INSTALMENTS',
            last_instalment_received=False,
            receipt_document_type='GRN',
            receipt_document_number='GRN-LOT-1',
            is_receipt_confirmed=True
        )
        self.assertFalse(alloc_lot1.is_statutorily_eligible)
        self.assertEqual(alloc_lot1.allocation_reason, 'PARTIAL_LOT_PENDING_LAST_INSTALMENT')

        # Lot 2 (final instalment) received in Feb: Full credit eligible in Feb!
        alloc_lot2 = GSTAllocationService.allocate_voucher(
            voucher=v_lots,
            preferred_period='022026',
            receipt_type='LOTS_INSTALMENTS',
            last_instalment_received=True,
            receipt_document_type='GRN',
            receipt_document_number='GRN-LOT-FINAL',
            is_receipt_confirmed=True,
            force_reallocate=True
        )
        self.assertTrue(alloc_lot2.is_statutorily_eligible)
        self.assertEqual(alloc_lot2.assigned_period, '022026')
        self.assertEqual(alloc_lot2.igst_amount, Decimal('5400.00'))

    def test_eway_bill_in_transit_fails_closed(self):
        """
        Verify: E-Way Bill without confirmed physical receipt fails closed under Section 16(2)(b).
        """
        v_in = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-EWB-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_in,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        alloc = GSTAllocationService.allocate_voucher(
            voucher=v_in,
            receipt_document_type='EWAY_BILL',
            receipt_document_number='EWB-9988776655',
            is_receipt_confirmed=False # In transit
        )
        self.assertFalse(alloc.is_statutorily_eligible)
        self.assertEqual(alloc.allocation_reason, 'GOODS_SERVICES_NOT_RECEIVED')
        self.assertIn("in transit", alloc.exclusion_reason)

    def test_duplicate_grn_rejected(self):
        """
        Verify: Same GRN number cannot be used across multiple distinct purchase vouchers.
        """
        v1 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-GRN-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v1,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        # Allocate v1 with GRN-1001
        alloc1 = GSTAllocationService.allocate_voucher(
            voucher=v1,
            receipt_document_type='GRN',
            receipt_document_number='GRN-1001',
            is_receipt_confirmed=True
        )
        self.assertTrue(alloc1.is_statutorily_eligible)

        # Allocate v2 with same GRN-1001
        v2 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-GRN-02',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 12),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v2,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        alloc2 = GSTAllocationService.allocate_voucher(
            voucher=v2,
            receipt_document_type='GRN',
            receipt_document_number='GRN-1001',
            is_receipt_confirmed=True
        )
        self.assertFalse(alloc2.is_statutorily_eligible)
        self.assertEqual(alloc2.allocation_reason, 'GOODS_SERVICES_NOT_RECEIVED')
        self.assertIn("Duplicate GRN", alloc2.exclusion_reason)

    def test_services_completion_evidence_independent_of_lots(self):
        """
        Verify: Services completion is verified by service certificate; goods-in-lots does not apply.
        """
        v_svc = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-SVC-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_svc,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        alloc_svc = GSTAllocationService.allocate_voucher(
            voucher=v_svc,
            preferred_period='022026',
            goods_received_date=date(2026, 2, 10),
            receipt_type='SERVICE_COMPLETION',
            receipt_document_type='SERVICE_COMPLETION',
            receipt_document_number='CERT-SVC-001',
            is_receipt_confirmed=True
        )
        self.assertTrue(alloc_svc.is_statutorily_eligible)
        self.assertEqual(alloc_svc.assigned_period, '022026')
        self.assertEqual(alloc_svc.igst_amount, Decimal('1800.00'))

    def test_rule_37a_multiple_invoices_same_and_different_suppliers(self):
        """
        Verify:
        - Multiple invoices from the same supplier are evaluated independently.
        - Invoices from different suppliers with different filing statuses are evaluated correctly.
        """
        ledger_supp2 = Ledger.objects.create(company=self.company, name='Secondary Vendor', group=self.grp_liab)

        # Supplier 1: Invoice A and Invoice B
        v1 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-S1-A',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 10, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v1,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00')
        )
        v2 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-S1-B',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 11, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v2,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00')
        )

        # Supplier 2: Invoice C
        v3 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-S2-C',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 12, 10),
            party_ledger=ledger_supp2,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=v3,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00')
        )

        # Case: Supplier 1 defaulted on 30-Sep-2026; Supplier 2 filed on 2026-08-15
        st_v1 = GSTAllocationService.evaluate_rule37a_status(v1, check_date=date(2026, 10, 5), supplier_gstr3b_filed=False)
        st_v2 = GSTAllocationService.evaluate_rule37a_status(v2, check_date=date(2026, 10, 5), supplier_gstr3b_filed=False)
        st_v3 = GSTAllocationService.evaluate_rule37a_status(v3, check_date=date(2026, 10, 5), supplier_gstr3b_filed=True, supplier_filing_date=date(2026, 8, 15))

        self.assertTrue(st_v1['is_supplier_default'])
        self.assertTrue(st_v2['is_supplier_default'])
        self.assertFalse(st_v3['is_supplier_default'])

    def test_goods_in_three_lots_scenario_a(self):
        """
        Verify Scenario A: Single invoice with three lots:
        - Lot 1 & Lot 2 pending final instalment -> Excluded under First Proviso to Section 16(2).
        - Lot 3 (last lot) received -> 100% full invoice credit becomes eligible.
        """
        v_three = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-LOTS-3',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 5),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('35400.00'),
        )
        VoucherItem.objects.create(
            voucher=v_three,
            product=self.product,
            quantity=Decimal('30.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('30000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('5400.00')
        )

        # Lot 1 in Jan (10 pcs)
        a1 = GSTAllocationService.allocate_voucher(
            voucher=v_three,
            preferred_period='012026',
            receipt_type='LOTS_INSTALMENTS',
            last_instalment_received=False,
            is_receipt_confirmed=True
        )
        self.assertFalse(a1.is_statutorily_eligible)
        self.assertEqual(a1.allocation_reason, 'PARTIAL_LOT_PENDING_LAST_INSTALMENT')

        # Lot 2 in Feb (10 pcs)
        a2 = GSTAllocationService.allocate_voucher(
            voucher=v_three,
            preferred_period='022026',
            receipt_type='LOTS_INSTALMENTS',
            last_instalment_received=False,
            is_receipt_confirmed=True,
            force_reallocate=True
        )
        self.assertFalse(a2.is_statutorily_eligible)
        self.assertEqual(a2.allocation_reason, 'PARTIAL_LOT_PENDING_LAST_INSTALMENT')

        # Lot 3 in Mar (10 pcs, final instalment)
        a3 = GSTAllocationService.allocate_voucher(
            voucher=v_three,
            preferred_period='032026',
            receipt_type='LOTS_INSTALMENTS',
            last_instalment_received=True,
            is_receipt_confirmed=True,
            force_reallocate=True
        )
        self.assertTrue(a3.is_statutorily_eligible)
        self.assertEqual(a3.assigned_period, '032026')
        self.assertEqual(a3.igst_amount, Decimal('5400.00'))

    def test_separate_invoices_independently_received_scenario_b(self):
        """
        Verify Scenario B: Separate invoices for independently received supplies:
        Each invoice is evaluated on its own receipt evidence and independent eligibility.
        """
        v_inv1 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-SEP-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_inv1,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00')
        )
        v_inv2 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-SEP-02',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 15),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_inv2,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00')
        )

        # Invoice 1 received in Jan
        a1 = GSTAllocationService.allocate_voucher(
            voucher=v_inv1,
            preferred_period='012026',
            goods_received_date=date(2026, 1, 12),
            is_receipt_confirmed=True
        )
        # Invoice 2 goods in transit (not confirmed)
        a2 = GSTAllocationService.allocate_voucher(
            voucher=v_inv2,
            receipt_document_type='EWAY_BILL',
            is_receipt_confirmed=False
        )

        self.assertTrue(a1.is_statutorily_eligible)
        self.assertEqual(a1.assigned_period, '012026')
        self.assertFalse(a2.is_statutorily_eligible)
        self.assertEqual(a2.allocation_reason, 'GOODS_SERVICES_NOT_RECEIVED')

    def test_outbox_sweeper_and_deadline_commands(self):
        """
        Verify:
        - `python manage.py sweep_outbox` runs synchronously without error.
        - `python manage.py check_gst_deadlines` executes and evaluates Rule 37A/37/16(4) status.
        """
        from io import StringIO
        from django.core.management import call_command

        out_sweep = StringIO()
        call_command('sweep_outbox', stdout=out_sweep)
        self.assertIn("Outbox sweep completed successfully", out_sweep.getvalue())

        out_gst = StringIO()
        call_command('check_gst_deadlines', company_id=str(self.company.id), stdout=out_gst)
        self.assertIn("[COMPLETE] Evaluated", out_gst.getvalue())

    def test_double_entry_accounting_invariance_on_reversals_and_reclaims(self):
        """
        Verify:
        - Creating Rule 37/37A reversals and reclaims does not alter the double-entry accounting ledgers.
        - Total debits == Total credits remains strictly invariant.
        """
        v_inv = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-DE-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_supplier,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_inv,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00')
        )
        le_exp = LedgerEntry.objects.create(
            company=self.company,
            voucher=v_inv,
            ledger=self.ledger_supplier,
            debit_amount=Decimal('11800.00'),
            credit_amount=Decimal('0.00')
        )
        le_supp = LedgerEntry.objects.create(
            company=self.company,
            voucher=v_inv,
            ledger=self.ledger_supplier,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('11800.00')
        )

        # Baseline ledger snapshot
        initial_debits = sum(e.debit_amount for e in LedgerEntry.objects.filter(voucher=v_inv))
        initial_credits = sum(e.credit_amount for e in LedgerEntry.objects.filter(voucher=v_inv))
        self.assertEqual(initial_debits, initial_credits)
        self.assertEqual(initial_debits, Decimal('11800.00'))

        # Create Rule 37 Reversal
        GSTAllocationService.create_rule37_reversal_allocation(
            voucher=v_inv,
            unpaid_amount=Decimal('11800.00'),
            assigned_period='072026',
            user=self.owner_user
        )

        # Create Rule 37 Reclaim
        GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=v_inv,
            paid_amount=Decimal('11800.00'),
            assigned_period='082026',
            user=self.owner_user,
            payment_event_id='PAY-254-002'
        )

        # Verify Ledgers remained 100% untouched
        le_exp.refresh_from_db()
        le_supp.refresh_from_db()
        post_debits = sum(e.debit_amount for e in LedgerEntry.objects.filter(voucher=v_inv))
        post_credits = sum(e.credit_amount for e in LedgerEntry.objects.filter(voucher=v_inv))

        self.assertEqual(post_debits, initial_debits)
        self.assertEqual(post_credits, initial_credits)
        self.assertEqual(post_debits, post_credits)


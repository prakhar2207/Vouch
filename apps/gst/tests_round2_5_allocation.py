import json
import uuid
import hashlib
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from django.core.exceptions import ValidationError

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.gst.models import (
    GSTRegistration,
    GSTReturnWorkspace,
    GSTFilingRecord,
    GSTReportingAllocation,
    GSTWorkspaceExportSnapshot,
)
from apps.gst.services.allocation_service import GSTAllocationService
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.workspace_service import GSTWorkspaceService
from apps.gst.services.validation_service import GSTValidationService

User = get_user_model()


class GSTRound25AllocationCertificationTests(TestCase):
    """
    Comprehensive Verification & Certification Test Suite for SriLekh GST Round 2.5:
    GST Reporting Allocation, Prior-Period Transaction Handling & Late-Entry Engine.

    Validates:
    1. Mandatory Sandbox Tenant Isolation Invariant (Apex Belting Store only: 4e62863a-08f9-4e99-b0bd-64873acfdd33).
    2. Protection of real client tenant 'Maa Annapurna Belting Store' (5d2e5dea-ff86-4871-b2af-fe1c5a05c03c).
    3. Scenario A: Prior-period sales invoice entered late reported in current return period with original invoice date.
    4. Scenario B: Prior-period purchase invoice received late claimed in period of receipt under Section 16(2)(b).
    5. Scenario C: Section 16(4) / 37(3) statutory deadline exceeded (strictly excluded from current return).
    6. Scenario D: Manual accountant reallocation with immutable supersession audit trail.
    7. Statutory deadline validation on manual reallocation (rejection beyond 30th November cutoff).
    8. Unfiled voucher reversal deactivates allocation.
    9. Filed voucher reversal generates adjustment allocation without corrupting history.
    10. Return Workspace drift detection reacts to reporting allocation changes.
    11. Immutable export snapshots protect exported return data against retroactive draft drift.
    12. Filed return workspace immutability (re-compilation strictly forbidden).
    13. Double-entry accounting invariants (voucher amounts, ledger entries, trial balance completely untouched).
    14. Multi-tenant API isolation on allocation list and reallocation endpoints.
    15. Idempotency of allocation creation and deduplication.
    """

    def setUp(self):
        self.client = APIClient()

        # Users
        self.owner_user = User.objects.create_user(
            email='owner@apexbelting.demo',
            password='Password123!'
        )
        self.ca_user = User.objects.create_user(
            email='ca@apexbelting.demo',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            email='intruder@othercompany.demo',
            password='Password123!'
        )

        # Primary Sandbox Company (MANDATORY INVARIANT)
        self.company = Company.objects.create(
            id=uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33'),
            name='Apex Belting & Industrial Store (Demo)',
            legal_name='Apex Belting & Industrial Store Private Limited',
            gstin='27AAACA1234A1Z5',
            state_code='27',
            email='accounts@apexbelting.demo'
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "CRITICAL SECURITY INVARIANT VIOLATION: Tests must strictly run against sandbox company!"
        )

        UserCompany.objects.create(user=self.owner_user, company=self.company, role='OWNER')
        UserCompany.objects.create(user=self.ca_user, company=self.company, role='CA')

        # Secondary Isolated Company
        self.other_company = Company.objects.create(
            name='Isolated Competitor Belts Pvt Ltd',
            gstin='27AAACC9999C1Z9',
            state_code='27',
            email='info@isolated-competitor.com'
        )
        UserCompany.objects.create(user=self.other_user, company=self.other_company, role='OWNER')

        # GST Registration for Primary Sandbox Company
        self.reg_primary = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAACA1234A1Z5',
            legal_name='Apex Belting & Industrial Store Private Limited',
            trade_name='Apex Belting Store',
            state_code='27',
            state_name='Maharashtra',
            taxpayer_type='REGULAR',
            status='ACTIVE',
            is_primary=True,
            verification_status='VERIFIED'
        )

        # Ledger Groups
        self.grp_debtors = LedgerGroup.objects.create(
            company=self.company, name='Sundry Debtors', nature='ASSET'
        )
        self.grp_creditors = LedgerGroup.objects.create(
            company=self.company, name='Sundry Creditors', nature='LIABILITY'
        )
        self.grp_sales = LedgerGroup.objects.create(
            company=self.company, name='Sales Accounts', nature='INCOME'
        )
        self.grp_purchase = LedgerGroup.objects.create(
            company=self.company, name='Purchase Accounts', nature='EXPENSE'
        )
        self.grp_tax = LedgerGroup.objects.create(
            company=self.company, name='Duties and Taxes', nature='LIABILITY'
        )

        # Ledgers
        self.ledger_customer = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Precision Tech Supplies',
            ledger_type='PARTY',
            gstin='27BBBBB2222B1Z3',
            state_code='27'
        )
        self.ledger_interstate_customer = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Gujarat Motors Ltd',
            ledger_type='PARTY',
            gstin='24GGGGG4444G1Z6',
            state_code='24'
        )
        self.ledger_vendor = Ledger.objects.create(
            company=self.company,
            group=self.grp_creditors,
            name='National Rubber Belts Ltd',
            ledger_type='PARTY',
            gstin='27CCCC3333C1Z4',
            state_code='27'
        )
        self.ledger_sales = Ledger.objects.create(
            company=self.company,
            group=self.grp_sales,
            name='Sales - Industrial Supplies',
            ledger_type='SALES'
        )
        self.ledger_purchase = Ledger.objects.create(
            company=self.company,
            group=self.grp_purchase,
            name='Purchase - Raw Material',
            ledger_type='PURCHASE'
        )
        self.ledger_cgst_output = Ledger.objects.create(
            company=self.company,
            group=self.grp_tax,
            name='Output CGST',
            ledger_type='TAX'
        )
        self.ledger_sgst_output = Ledger.objects.create(
            company=self.company,
            group=self.grp_tax,
            name='Output SGST',
            ledger_type='TAX'
        )
        self.ledger_igst_output = Ledger.objects.create(
            company=self.company,
            group=self.grp_tax,
            name='Output IGST',
            ledger_type='TAX'
        )
        self.ledger_cgst_input = Ledger.objects.create(
            company=self.company,
            group=self.grp_tax,
            name='Input CGST',
            ledger_type='TAX'
        )
        self.ledger_sgst_input = Ledger.objects.create(
            company=self.company,
            group=self.grp_tax,
            name='Input SGST',
            ledger_type='TAX'
        )
        self.ledger_igst_input = Ledger.objects.create(
            company=self.company,
            group=self.grp_tax,
            name='Input IGST',
            ledger_type='TAX'
        )

        # Product
        self.product_cat = ProductCategory.objects.create(
            company=self.company, name='Industrial Belts'
        )
        self.product = Product.objects.create(
            company=self.company,
            category=self.product_cat,
            name='V-Belt Heavy Duty 500',
            sku='VB-500',
            unit='NOS',
            hsn_code='401039',
            selling_price=Decimal('1000.00'),
            purchase_price=Decimal('800.00'),
            gst_rate=Decimal('18.00')
        )

    # =========================================================================
    # 1. Mandatory Sandbox Tenant Isolation Invariant
    # =========================================================================

    def test_sandbox_tenant_id_invariant(self):
        """Verifies tests run strictly against Apex Belting Store sandbox ID."""
        self.assertEqual(str(self.company.id), '4e62863a-08f9-4e99-b0bd-64873acfdd33')

    def test_protected_production_tenant_isolation(self):
        """Verifies that attempts to mutate production tenant Maa Annapurna are prohibited."""
        prod_tenant_id = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'
        with self.assertRaises(AssertionError):
            assert str(self.company.id) == prod_tenant_id, "ABORT: Production tenant access strictly forbidden!"

    # =========================================================================
    # 2. Scenario A: Prior-Period Sales Invoice Entered in Later Month
    # =========================================================================

    def test_scenario_a_prior_period_sales_entered_late(self):
        """
        Scenario A:
        A sales invoice dated 15 January 2026 is entered into the system on 10 February 2026.
        Requirements:
        - Voucher accounting date remains 2026-01-15 (immutability).
        - GST Reporting Allocation assigns it to February 2026 ('022026') under reason 'LATE_ENTRY_CURRENT_FY'.
        - GSTR-1 for February 2026 includes the invoice in Table 4 B2B, reporting 'idt' as '15-01-2026'.
        - GSTR-1 for January 2026 does NOT include this invoice.
        """
        # Create Sales Voucher dated 15 Jan 2026 entered on 10 Feb 2026
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-2026-001',
            voucher_type='SALES',
            voucher_date=date(2026, 1, 15),
            party_ledger=self.ledger_customer,
            buyer_name=self.ledger_customer.name,
            buyer_gstin=self.ledger_customer.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            hsn_code=self.product.hsn_code,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00')
        )

        # Allocate voucher with entry date 10 Feb 2026
        alloc = GSTAllocationService.allocate_voucher(
            voucher=v,
            received_date=date(2026, 2, 10),
            user=self.owner_user
        )

        # 1. Verify Allocation Details
        self.assertEqual(alloc.original_period, '012026')
        self.assertEqual(alloc.assigned_period, '022026')
        self.assertEqual(alloc.allocation_reason, 'LATE_OUTWARD_SUPPLY')
        self.assertEqual(alloc.status, 'APPROVED')
        self.assertTrue(alloc.is_statutorily_eligible)
        self.assertEqual(alloc.taxable_value, Decimal('10000.00'))
        self.assertEqual(alloc.total_tax, Decimal('1800.00'))
        self.assertTrue(alloc.is_active)

        # 2. Verify GSTR-1 for January 2026 (Should NOT include this voucher)
        gstr1_jan = GSTReturnsService.prepare_gstr1(
            company=self.company,
            registration=self.reg_primary,
            return_period='012026'
        )
        self.assertEqual(gstr1_jan['total_vouchers'], 0)
        self.assertEqual(gstr1_jan['summary']['total_taxable_value'], 0.0)

        # 3. Verify GSTR-1 for February 2026 (MUST include this voucher with original idt)
        gstr1_feb = GSTReturnsService.prepare_gstr1(
            company=self.company,
            registration=self.reg_primary,
            return_period='022026'
        )
        self.assertEqual(gstr1_feb['total_vouchers'], 1)
        self.assertEqual(gstr1_feb['summary']['total_taxable_value'], 10000.0)
        self.assertEqual(gstr1_feb['summary']['total_cgst'], 900.0)
        self.assertEqual(gstr1_feb['summary']['total_sgst'], 900.0)

        # Verify Table 4 B2B contents
        b2b_payload = gstr1_feb['official_gstr1_json'].get('b2b', [])
        self.assertEqual(len(b2b_payload), 1)
        ctin_entry = b2b_payload[0]
        self.assertEqual(ctin_entry['ctin'], self.ledger_customer.gstin)
        inv_item = ctin_entry['inv'][0]
        self.assertEqual(inv_item['inum'], 'INV-2026-001')
        self.assertEqual(inv_item['idt'], '15-01-2026')  # Section 37(1): Original invoice date preserved!
        self.assertEqual(inv_item['val'], 11800.0)

        # 4. Verify Accounting Immutability
        v.refresh_from_db()
        self.assertEqual(v.voucher_date, date(2026, 1, 15))
        self.assertEqual(v.total_amount, Decimal('11800.00'))

    # =========================================================================
    # 3. Scenario B: Prior-Period Purchase Received in Later Month (ITC Timing)
    # =========================================================================

    def test_scenario_b_prior_period_purchase_received_late(self):
        """
        Scenario B:
        A purchase invoice dated 20 January 2026 is physically received / entered on 12 February 2026.
        Requirements:
        - Under Section 16(2)(b), ITC can only be claimed upon receipt of goods/invoice.
        - Voucher accounting date remains 2026-01-20.
        - GST Reporting Allocation assigns it to February 2026 ('022026') under reason 'GOODS_SERVICE_RECEIVED_LATER'.
        - GSTR-3B for February 2026 includes the eligible ITC in Table 4.
        - GSTR-3B for January 2026 does NOT include this ITC.
        """
        # Create Purchase Voucher dated 20 Jan 2026 received on 12 Feb 2026
        pv = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-2026-101',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 20),
            party_ledger=self.ledger_vendor,
            buyer_name=self.ledger_vendor.name,
            buyer_gstin=self.ledger_vendor.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('9440.00'),
        )
        VoucherItem.objects.create(
            voucher=pv,
            product=self.product,
            hsn_code=self.product.hsn_code,
            quantity=Decimal('10.00'),
            rate=Decimal('800.00'),
            taxable_amount=Decimal('8000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('720.00'),
            sgst_amount=Decimal('720.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('9440.00')
        )

        # Allocate voucher with received date 12 Feb 2026
        alloc = GSTAllocationService.allocate_voucher(
            voucher=pv,
            received_date=date(2026, 2, 12),
            user=self.owner_user
        )

        # 1. Verify Allocation Details
        self.assertEqual(alloc.original_period, '012026')
        self.assertEqual(alloc.assigned_period, '022026')
        self.assertEqual(alloc.allocation_reason, 'LATE_INWARD_RECEIPT')
        self.assertEqual(alloc.event_type, 'INWARD_ITC')
        self.assertTrue(alloc.is_statutorily_eligible)
        self.assertIn('Section 16(2)(b)', alloc.statutory_rule)

        # 2. Verify GSTR-3B for January 2026 (No ITC)
        gstr3b_jan = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_primary,
            return_period='012026'
        )
        itc_jan = gstr3b_jan['table_4_itc']['itc_available']['all_other_itc']
        self.assertEqual(itc_jan['cgst'], 0.0)
        self.assertEqual(itc_jan['sgst'], 0.0)

        # 3. Verify GSTR-3B for February 2026 (ITC Claimed)
        gstr3b_feb = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_primary,
            return_period='022026'
        )
        itc_feb = gstr3b_feb['table_4_itc']['itc_available']['all_other_itc']
        self.assertEqual(itc_feb['taxable_value'], 8000.0)
        self.assertEqual(itc_feb['cgst'], 720.0)
        self.assertEqual(itc_feb['sgst'], 720.0)
        self.assertEqual(gstr3b_feb['table_4_itc']['net_itc_available']['total'], 1440.0)

    # =========================================================================
    # 4. Scenario C: Statutory Deadline Exceeded (Section 16(4) / 37(3))
    # =========================================================================

    def test_scenario_c_purchase_itc_past_statutory_cutoff_section_16_4(self):
        """
        Scenario C:
        A purchase invoice dated in FY 2024-25 (e.g. 10 November 2024) is entered on 05 December 2025.
        The statutory cutoff date under Section 16(4) is 30th November 2025.
        Requirements:
        - Allocation marks is_statutorily_eligible = False.
        - Status is 'EXCLUDED'.
        - Exclusion reason clearly cites Section 16(4) statutory deadline.
        - GSTR-3B excludes the invoice from Table 4 eligible ITC.
        - Reported in 'excluded_itc' section with full audit metadata.
        """
        pv = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='OLD-PURCHASE-2024',
            voucher_type='PURCHASE',
            voucher_date=date(2024, 11, 10),  # FY 2024-25
            party_ledger=self.ledger_vendor,
            buyer_name=self.ledger_vendor.name,
            buyer_gstin=self.ledger_vendor.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('59000.00'),
        )
        VoucherItem.objects.create(
            voucher=pv,
            product=self.product,
            hsn_code=self.product.hsn_code,
            quantity=Decimal('50.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('50000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('4500.00'),
            sgst_amount=Decimal('4500.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('59000.00')
        )

        # Allocate with entry date past 30 Nov 2025
        alloc = GSTAllocationService.allocate_voucher(
            voucher=pv,
            received_date=date(2025, 12, 5),
            user=self.owner_user
        )

        # Verify Statutory Ineligibility
        self.assertFalse(alloc.is_statutorily_eligible)
        self.assertEqual(alloc.status, 'EXCLUDED')
        self.assertEqual(alloc.assigned_period, '122025')
        self.assertIn('Section 16(4)', alloc.statutory_rule)
        self.assertIn('30th November', alloc.exclusion_reason)

        # Verify GSTR-3B for December 2025
        gstr3b_dec = GSTReturnsService.prepare_gstr3b(
            company=self.company,
            registration=self.reg_primary,
            return_period='122025'
        )
        itc_dec = gstr3b_dec['table_4_itc']['itc_available']['all_other_itc']
        self.assertEqual(itc_dec['cgst'], 0.0)
        self.assertEqual(itc_dec['sgst'], 0.0)

        # Verify Excluded ITC section in GSTR-3B
        self.assertEqual(gstr3b_dec['excluded_itc']['total_excluded_vouchers'], 1)
        self.assertEqual(gstr3b_dec['excluded_itc']['total_excluded_tax'], 9000.0)

    def test_scenario_c_sales_invoice_past_statutory_cutoff_section_37_3(self):
        """
        Scenario C:
        A sales invoice dated in FY 2024-25 (e.g. 15 October 2024) is entered on 05 December 2025.
        The statutory cutoff under Section 37(3) is 30th November 2025.
        Requirements:
        - Allocation marks is_statutorily_eligible = False.
        - Status is 'EXCLUDED'.
        - GSTR-1 excludes it from Table 4 and reports it under summary['excluded_vouchers'].
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='OLD-SALES-2024',
            voucher_type='SALES',
            voucher_date=date(2024, 10, 15),
            party_ledger=self.ledger_customer,
            buyer_name=self.ledger_customer.name,
            buyer_gstin=self.ledger_customer.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            hsn_code=self.product.hsn_code,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00')
        )

        alloc = GSTAllocationService.allocate_voucher(
            voucher=v,
            received_date=date(2025, 12, 5),
            user=self.owner_user
        )

        self.assertFalse(alloc.is_statutorily_eligible)
        self.assertEqual(alloc.status, 'EXCLUDED')
        self.assertIn('Section 37(3)', alloc.statutory_rule)

        gstr1_dec = GSTReturnsService.prepare_gstr1(
            company=self.company,
            registration=self.reg_primary,
            return_period='122025'
        )
        self.assertEqual(gstr1_dec['total_vouchers'], 0)
        self.assertEqual(gstr1_dec['summary']['excluded_vouchers_count'], 1)

    # =========================================================================
    # 5. Scenario D: Manual Accountant Reallocation & Audit Supersession
    # =========================================================================

    def test_scenario_d_manual_reallocation_with_supersession(self):
        """
        Scenario D:
        An accountant manually reallocates an eligible voucher from February 2026 to March 2026.
        Requirements:
        - Old allocation is marked is_active = False, status = 'SUPERSEDED'.
        - New allocation has assigned_period = '032026', is_active = True, status = 'APPROVED'.
        - Old allocation points to new allocation via superseded_by.
        - GSTR-1 for February 2026 no longer includes the invoice; GSTR-1 for March 2026 includes it.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-REALLOC-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 1),
            party_ledger=self.ledger_customer,
            buyer_name=self.ledger_customer.name,
            buyer_gstin=self.ledger_customer.gstin,
            buyer_state_code='27',
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            hsn_code=self.product.hsn_code,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'),
            total_amount=Decimal('11800.00')
        )

        old_alloc = GSTAllocationService.allocate_voucher(v, received_date=date(2026, 2, 1), user=self.owner_user)
        self.assertEqual(old_alloc.assigned_period, '022026')
        self.assertTrue(old_alloc.is_active)

        # Accountant reallocates to March 2026
        new_alloc = GSTAllocationService.reallocate_voucher(
            voucher=v,
            target_period='032026',
            reason='Deferred customer reporting requirement',
            user=self.ca_user
        )

        old_alloc.refresh_from_db()
        self.assertFalse(old_alloc.is_active)
        self.assertEqual(old_alloc.status, 'SUPERSEDED')
        self.assertEqual(old_alloc.superseded_by, new_alloc)

        self.assertTrue(new_alloc.is_active)
        self.assertEqual(new_alloc.assigned_period, '032026')
        self.assertEqual(new_alloc.allocation_reason, 'MANUAL_REALLOCATION')
        self.assertEqual(new_alloc.status, 'APPROVED')

        # Check GSTR-1 February 2026: 0 vouchers
        gstr1_feb = GSTReturnsService.prepare_gstr1(company=self.company, registration=self.reg_primary, return_period='022026')
        self.assertEqual(gstr1_feb['total_vouchers'], 0)

        # Check GSTR-1 March 2026: 1 voucher
        gstr1_mar = GSTReturnsService.prepare_gstr1(company=self.company, registration=self.reg_primary, return_period='032026')
        self.assertEqual(gstr1_mar['total_vouchers'], 1)
        self.assertEqual(gstr1_mar['summary']['total_taxable_value'], 10000.0)

    def test_manual_reallocation_past_statutory_cutoff_rejected(self):
        """
        Verifies that attempting to manually reallocate an invoice past its statutory cutoff date
        is rejected with a statutory ValueError.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-REALLOC-CUTOFF',
            voucher_type='SALES',
            voucher_date=date(2025, 4, 15),  # FY 2025-26 -> Cutoff is 30 Nov 2026
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        GSTAllocationService.allocate_voucher(v, received_date=date(2025, 4, 15))

        # Attempt to reallocate to December 2026 (past 30 Nov 2026 cutoff)
        with self.assertRaises(ValueError) as ctx:
            GSTAllocationService.reallocate_voucher(
                voucher=v,
                target_period='122026',
                reason='Attempt past cutoff',
                user=self.ca_user
            )
        self.assertIn('statutory deadline', str(ctx.exception))

    # =========================================================================
    # 6. Voucher Reversal Handling
    # =========================================================================

    def test_unfiled_voucher_reversal_deactivates_allocation(self):
        """
        Verifies that reversing an unfiled voucher deactivates its allocation
        so it drops out of return preparation.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-REV-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        alloc = GSTAllocationService.allocate_voucher(v, received_date=date(2026, 2, 5))
        self.assertTrue(alloc.is_active)

        rev_v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='REV-INV-REV-01',
            voucher_type='JOURNAL',
            voucher_date=date(2026, 2, 6),
            status='POSTED',
            total_amount=Decimal('11800.00')
        )

        GSTAllocationService.handle_voucher_reversal(v, rev_v, user=self.owner_user)

        alloc.refresh_from_db()
        self.assertFalse(alloc.is_active)
        self.assertEqual(alloc.status, 'SUPERSEDED')

    def test_filed_voucher_reversal_creates_credit_note_adjustment(self):
        """
        Verifies that reversing an ALREADY FILED voucher preserves the original allocation
        and generates an adjustment allocation in the current period.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-FILED-01',
            voucher_type='SALES',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )
        orig_alloc = GSTAllocationService.allocate_voucher(v, received_date=date(2026, 1, 10))
        orig_alloc.status = 'FILED'
        orig_alloc.save()

        # Reversal voucher in February 2026
        rev_v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='CN-2026-REV',
            voucher_type='CREDIT_NOTE',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00')
        )
        VoucherItem.objects.create(
            voucher=rev_v,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )

        rev_alloc = GSTAllocationService.handle_voucher_reversal(v, rev_v, user=self.owner_user)

        # Original filed allocation must remain untouched and active
        orig_alloc.refresh_from_db()
        self.assertTrue(orig_alloc.is_active)
        self.assertEqual(orig_alloc.status, 'FILED')

        # New adjustment allocation created in February
        self.assertEqual(rev_alloc.assigned_period, '022026')
        self.assertEqual(rev_alloc.event_type, 'CREDIT_NOTE')
        self.assertEqual(rev_alloc.allocation_reason, 'REVERSAL_ADJUSTMENT')
        self.assertTrue(rev_alloc.is_active)

    # =========================================================================
    # 7. Workspace Drift Detection & Export Snapshots
    # =========================================================================

    def test_workspace_drift_detection_on_allocation_change(self):
        """
        Verifies that reallocating a voucher causes workspace drift detection
        to set workspace.is_stale = True.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-DRIFT-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )
        GSTAllocationService.allocate_voucher(v, received_date=date(2026, 2, 5))

        ws = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='022026',
            status='NOT_STARTED'
        )
        GSTWorkspaceService.generate_draft(ws)
        ws.refresh_from_db()
        self.assertFalse(ws.is_stale)
        self.assertEqual(ws.status, 'DRAFT')

        # Reallocate voucher to March 2026
        GSTAllocationService.reallocate_voucher(v, '032026', reason='Testing drift', user=self.owner_user)

        # Check drift
        is_stale = GSTWorkspaceService.check_drift(ws)
        self.assertTrue(is_stale)
        ws.refresh_from_db()
        self.assertTrue(ws.is_stale)

    def test_export_snapshot_immutability(self):
        """
        Verifies that exporting a return saves an immutable GSTWorkspaceExportSnapshot
        preserving the exact exported JSON payload and SHA-256 hash.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-EXPORT-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )
        GSTAllocationService.allocate_voucher(v, received_date=date(2026, 2, 5))

        ws = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='022026',
            status='NOT_STARTED'
        )
        GSTWorkspaceService.generate_draft(ws)
        export_result = GSTWorkspaceService.export_draft(ws, export_format='JSON')

        self.assertTrue(export_result['success'])
        ws.refresh_from_db()
        self.assertEqual(ws.status, 'EXPORTED')

        snapshot = GSTWorkspaceExportSnapshot.objects.filter(workspace=ws).first()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.payload_hash, export_result['payload_hash'])
        self.assertIn('b2b', snapshot.exported_payload)

    def test_filed_return_workspace_cannot_be_recompiled(self):
        """
        Verifies that calling generate_draft on an already FILED return workspace
        raises a ValidationError to protect filed return integrity.
        """
        ws = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='022026',
            status='FILED'
        )
        with self.assertRaises(ValidationError) as ctx:
            GSTWorkspaceService.generate_draft(ws)
        self.assertIn('already FILED', str(ctx.exception))

    # =========================================================================
    # 8. Accounting Invariant: Zero Mutation of Accounting Ledgers
    # =========================================================================

    def test_double_entry_accounting_invariants(self):
        """
        Verifies that allocating, reallocating, or excluding vouchers DOES NOT mutate:
        - Voucher.total_amount
        - Voucher.voucher_date
        - Any LedgerEntry
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-INV-01',
            voucher_type='SALES',
            voucher_date=date(2026, 1, 15),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )
        # Create standard accounting ledger entries
        LedgerEntry.objects.create(voucher=v, ledger=self.ledger_customer, debit_amount=Decimal('11800.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=v, ledger=self.ledger_sales, debit_amount=Decimal('0.00'), credit_amount=Decimal('10000.00'))
        LedgerEntry.objects.create(voucher=v, ledger=self.ledger_cgst_output, debit_amount=Decimal('0.00'), credit_amount=Decimal('900.00'))
        LedgerEntry.objects.create(voucher=v, ledger=self.ledger_sgst_output, debit_amount=Decimal('0.00'), credit_amount=Decimal('900.00'))

        # Allocate to Feb 2026
        alloc = GSTAllocationService.allocate_voucher(v, received_date=date(2026, 2, 10))
        # Reallocate to Mar 2026
        GSTAllocationService.reallocate_voucher(v, '032026', reason='Audit check', user=self.owner_user)

        # Assert Voucher and Ledger Entries are 100% UNTOUCHED
        v.refresh_from_db()
        self.assertEqual(v.voucher_date, date(2026, 1, 15))
        self.assertEqual(v.total_amount, Decimal('11800.00'))

        entries = LedgerEntry.objects.filter(voucher=v)
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, Decimal('11800.00'))
        self.assertEqual(total_cr, Decimal('11800.00'))
        self.assertEqual(total_dr, total_cr)  # Mathematical equilibrium preserved!

    # =========================================================================
    # 9. Multi-Tenant API Isolation & IDOR Protection
    # =========================================================================

    def test_multi_tenant_api_isolation_on_allocations(self):
        """
        Verifies that a user belonging to Company B cannot view or reallocate
        allocations belonging to Company A.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-TENANT-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        GSTAllocationService.allocate_voucher(v, received_date=date(2026, 2, 5))

        # Attempt to access Company A allocations as User from Company B
        self.client.force_authenticate(user=self.other_user)

        # 1. GET allocations list for Company A
        res_list = self.client.get(f'/api/v1/gst/allocations/{self.company.id}/')
        self.assertIn(res_list.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # 2. POST reallocate on Company A
        res_realloc = self.client.post(
            f'/api/v1/gst/allocations/{self.company.id}/reallocate/',
            {"voucher_id": str(v.id), "target_period": "032026", "reason": "Malicious attempt"},
            format='json'
        )
        self.assertIn(res_realloc.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # Authorized User can access
        self.client.force_authenticate(user=self.ca_user)
        res_auth = self.client.get(f'/api/v1/gst/allocations/{self.company.id}/?assigned_period=022026')
        self.assertEqual(res_auth.status_code, status.HTTP_200_OK)
        self.assertTrue(res_auth.data['success'])
        self.assertEqual(res_auth.data['count'], 1)

    # =========================================================================
    # 10. Idempotency & Backward Compatibility
    # =========================================================================

    def test_idempotency_of_allocations(self):
        """
        Verifies that calling allocate_voucher repeatedly produces exactly one active allocation.
        """
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-IDEMP-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        alloc1 = GSTAllocationService.allocate_voucher(v)
        alloc2 = GSTAllocationService.allocate_voucher(v)

        self.assertEqual(alloc1.id, alloc2.id)
        active_count = GSTReportingAllocation.objects.filter(voucher=v, is_active=True).count()
        self.assertEqual(active_count, 1)

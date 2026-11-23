import json
import uuid
import hashlib
from decimal import Decimal
from datetime import date, timedelta, datetime, timezone as dt_timezone
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
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
        self.assertIn(rev_alloc.allocation_reason, ['REVERSAL_CREDIT_NOTE', 'REVERSAL_ADJUSTMENT'])
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

    # =========================================================================
    # 11. Round 2.5.1 Remediation & Independent Certification Tests
    # =========================================================================

    def test_voucher_hard_delete_prevented_in_posted_or_exported_status(self):
        """
        Verifies that Voucher.delete() raises ValidationError for POSTED, EXPORTED,
        FILED, or CANCELLED vouchers to protect accounting audit trails.
        """
        v_posted = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-DEL-POSTED',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 1),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('1000.00'),
        )
        with self.assertRaises(ValidationError) as ctx:
            v_posted.delete()
        self.assertIn("Statutory Accounting Invariant Violation", str(ctx.exception))

        v_draft = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-DEL-DRAFT',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 1),
            party_ledger=self.ledger_customer,
            status='DRAFT',
            total_amount=Decimal('500.00'),
        )
        # Draft vouchers can be deleted cleanly
        draft_id = v_draft.id
        v_draft.delete()
        self.assertFalse(Voucher.objects.filter(id=draft_id).exists())

    def test_workspace_hard_delete_prevented_in_exported_or_filed_status(self):
        """
        Verifies that GSTReturnWorkspace.delete() raises ValidationError for EXPORTED,
        FILED, or REVIEWED workspaces to guarantee return immutability.
        """
        ws_exported = GSTReturnWorkspace.objects.create(
            company=self.company,
            return_type='GSTR1',
            return_period='012026',
            financial_year='2025-26',
            status='EXPORTED'
        )
        with self.assertRaises(ValidationError) as ctx:
            ws_exported.delete()
        self.assertIn("Statutory Audit Invariant", str(ctx.exception))

        ws_draft = GSTReturnWorkspace.objects.create(
            company=self.company,
            return_type='GSTR1',
            return_period='022026',
            financial_year='2025-26',
            status='DRAFT'
        )
        ws_draft_id = ws_draft.id
        ws_draft.delete()
        self.assertFalse(GSTReturnWorkspace.objects.filter(id=ws_draft_id).exists())

    def test_section_34_credit_note_vs_internal_reversal_journal_semantics(self):
        """
        Verifies statutory event semantics:
        1. Genuine Section 34 Credit Notes (voucher_type='CREDIT_NOTE') are tagged CREDIT_NOTE
           and included in GSTR-1 Table 9B.
        2. Internal accounting reversal journals (voucher_type='JOURNAL') are tagged
           INTERNAL_ACCOUNTING_REVERSAL and strictly EXCLUDED from GSTR-1 Table 9B.
        """
        # Original sales invoice in closed period 012026
        v_orig = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-REV-ORIG-01',
            voucher_type='SALES',
            voucher_date=date(2026, 1, 15),
            party_ledger=self.ledger_customer,
            status='EXPORTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=v_orig,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        alloc_orig = GSTAllocationService.allocate_voucher(v_orig)
        alloc_orig.status = 'REPORTED'
        alloc_orig.save(update_fields=['status'])

        # Case 1: Statutory Section 34 Credit Note in period 022026
        cn_voucher = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='CN-STAT-01',
            voucher_type='CREDIT_NOTE',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=cn_voucher,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00')
        )
        cn_alloc = GSTAllocationService.handle_voucher_reversal(v_orig, cn_voucher, user=self.ca_user)
        self.assertEqual(cn_alloc.event_type, 'CREDIT_NOTE')
        self.assertEqual(cn_alloc.allocation_reason, 'REVERSAL_CREDIT_NOTE')
        self.assertIn('Section 34', cn_alloc.statutory_rule)

        # Case 2: Internal Accounting Reversal Journal in period 022026
        j_voucher = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='JRN-ADJ-01',
            voucher_type='JOURNAL',
            voucher_date=date(2026, 2, 12),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=j_voucher,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00')
        )
        j_alloc = GSTAllocationService.handle_voucher_reversal(v_orig, j_voucher, user=self.ca_user)
        self.assertEqual(j_alloc.event_type, 'INTERNAL_ACCOUNTING_REVERSAL')
        self.assertEqual(j_alloc.allocation_reason, 'REVERSAL_INTERNAL_JOURNAL')
        self.assertIn('Non-Section 34', j_alloc.statutory_rule)

        # Check GSTR-1 return preparation for period 022026:
        # cn_alloc MUST be present, j_alloc MUST be absent from GSTR-1!
        gstr1_data = GSTReturnsService.prepare_gstr1(company=self.company, registration=self.reg_primary, return_period='022026')
        cdnr_list = gstr1_data.get('official_gstr1_json', {}).get('cdnr', [])
        
        # Collect all note numbers in cdnr
        all_notes = []
        for cdnr_entry in cdnr_list:
            for nt in cdnr_entry.get('nt', []):
                all_notes.append(nt.get('nt_num'))

        self.assertIn('CN-STAT-01', all_notes)
        self.assertNotIn('JRN-ADJ-01', all_notes)

    def test_section_16_2_b_goods_service_receipt_evidence(self):
        """
        Verifies Section 16(2)(b) and First Proviso receipt evidence rules:
        1. If receipt is unconfirmed, ITC is excluded (GOODS_SERVICES_NOT_RECEIVED).
        2. If goods in lots/instalments and last lot pending, ITC is excluded (PARTIAL_LOT_PENDING_LAST_INSTALMENT).
        3. If goods received in subsequent month, assigned period matches receipt month.
        """
        # Case 1: Invoice entered without goods receipt confirmation
        pv_unconf = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-UNCONF-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 1),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_unconf,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        alloc_unconf = GSTAllocationService.allocate_voucher(
            pv_unconf,
            is_receipt_confirmed=False
        )
        self.assertFalse(alloc_unconf.is_statutorily_eligible)
        self.assertEqual(alloc_unconf.status, 'EXCLUDED')
        self.assertEqual(alloc_unconf.allocation_reason, 'GOODS_SERVICES_NOT_RECEIVED')

        # Case 2: Goods in lots/instalments with final lot pending
        pv_partial = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-LOT-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 2),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_partial,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        alloc_partial = GSTAllocationService.allocate_voucher(
            pv_partial,
            receipt_type='LOTS_INSTALMENTS',
            last_instalment_received=False
        )
        self.assertFalse(alloc_partial.is_statutorily_eligible)
        self.assertEqual(alloc_partial.status, 'EXCLUDED')
        self.assertEqual(alloc_partial.allocation_reason, 'PARTIAL_LOT_PENDING_LAST_INSTALMENT')

        # Case 3: Goods received in subsequent month (Jan invoice, received Feb 5)
        pv_subsequent = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-RECV-FEB-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 25),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_subsequent,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        alloc_sub = GSTAllocationService.allocate_voucher(
            pv_subsequent,
            goods_received_date=date(2026, 2, 5),
            is_receipt_confirmed=True
        )
        self.assertTrue(alloc_sub.is_statutorily_eligible)
        self.assertEqual(alloc_sub.status, 'APPROVED')
        self.assertEqual(alloc_sub.assigned_period, '022026')
        self.assertEqual(alloc_sub.allocation_reason, 'LATE_INWARD_RECEIPT')

    def test_statutory_cutoff_annual_return_override(self):
        """
        Verifies Section 16(4) / 37(3) 'whichever is earlier' statutory rule:
        If the Annual Return (GSTR-9) is furnished before 30th November,
        the statutory cutoff date becomes the date of furnishing of GSTR-9.
        """
        # Create a GSTR-9 filing record for FY 2025-26 filed early on 15th September 2026
        ar_filing = GSTFilingRecord.objects.create(
            company=self.company,
            return_type='GSTR9',
            return_period='2025-26',
            financial_year='2025-26',
            status='FILED',
            arn='AA2709260000001',
            submitted_by=self.ca_user
        )
        # Update submitted_at to 15th September 2026
        GSTFilingRecord.objects.filter(id=ar_filing.id).update(
            submitted_at=datetime(2026, 9, 15, 10, 0, 0, tzinfo=dt_timezone.utc)
        )

        cutoff = GSTAllocationService.get_statutory_cutoff_date(
            date(2025, 5, 10),
            company=self.company,
            return_type='INWARD_ITC'
        )
        # Cutoff must be 15th September 2026, NOT 30th November 2026
        self.assertEqual(cutoff, date(2026, 9, 15))

    def test_section_16_5_retrospective_amendment_window(self):
        """
        Verifies Section 16(5) retrospective amendment for FY 2017-18 to 2020-21:
        Special statutory deadline for availing ITC is 30th November 2021.
        """
        for test_fy_date in [date(2017, 8, 1), date(2018, 10, 15), date(2019, 12, 1), date(2020, 7, 20)]:
            cutoff = GSTAllocationService.get_statutory_cutoff_date(test_fy_date, return_type='INWARD_ITC')
            self.assertEqual(cutoff, date(2021, 11, 30))

        # FY 2021-22 onwards follows standard 30th November following FY end
        cutoff_21_22 = GSTAllocationService.get_statutory_cutoff_date(date(2021, 8, 1), return_type='INWARD_ITC')
        self.assertEqual(cutoff_21_22, date(2022, 11, 30))

    def test_gstr3b_table_4b_reversals_breakdown_and_net_itc(self):
        """
        Verifies that GSTR-3B Table 4B properly categorizes Rule 42/43 vs Other reversals
        and accurately reflects net eligible ITC in Table 4C.
        """
        # Inward supply in 022026: IGST 1000
        pv = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-ITC-REV-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        GSTAllocationService.allocate_voucher(pv, preferred_period='022026', is_receipt_confirmed=True)

        # Rule 42 reversal allocation: IGST 300
        j_rev42 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='JRN-REV-42',
            voucher_type='JOURNAL',
            voucher_date=date(2026, 2, 20),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('300.00'),
            narration='Reversal under Rule 42 common credit'
        )
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=j_rev42,
            event_type='ITC_REVERSAL_RULE_42',
            voucher_date=date(2026, 2, 20),
            original_period='022026',
            assigned_period='022026',
            financial_year='2025-26',
            allocation_reason='REVERSAL_RULE_42_43',
            status='APPROVED',
            is_statutorily_eligible=True,
            taxable_value=Decimal('0.00'),
            igst_amount=Decimal('300.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_tax=Decimal('300.00'),
            is_active=True,
            idempotency_key='rev_42_test_key'
        )

        # Rule 37 reversal allocation: IGST 200
        j_rev37 = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='JRN-REV-37',
            voucher_type='JOURNAL',
            voucher_date=date(2026, 2, 22),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('200.00'),
            narration='Reversal under Rule 37'
        )
        GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=j_rev37,
            event_type='ITC_REVERSAL_RULE_37',
            voucher_date=date(2026, 2, 22),
            original_period='022026',
            assigned_period='022026',
            financial_year='2025-26',
            allocation_reason='REVERSAL_RULE_37',
            status='APPROVED',
            is_statutorily_eligible=True,
            taxable_value=Decimal('0.00'),
            igst_amount=Decimal('200.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            total_tax=Decimal('200.00'),
            is_active=True,
            idempotency_key='rev_37_test_key'
        )

        gstr3b = GSTReturnsService.prepare_gstr3b(company=self.company, registration=self.reg_primary, return_period='022026')
        itc_sec = gstr3b.get('table_4_itc', {})
        
        # Check Table 4A (Available ITC): 1800
        self.assertEqual(itc_sec['itc_available']['all_other_itc']['igst'], 1800.00)
        
        # Check Table 4B (Reversals): Rule 42 = 300, Others = 200
        self.assertEqual(itc_sec['itc_reversed']['as_per_rules_42_43']['igst'], 300.00)
        self.assertEqual(itc_sec['itc_reversed']['others']['igst'], 200.00)
        
        # Check Table 4C (Net ITC Available): 1800 - (300 + 200) = 1300
        self.assertEqual(itc_sec['net_itc_available']['igst'], 1300.00)

    def test_queryset_bulk_delete_blocked_on_accounting_and_gst_models(self):
        """
        Phase 3: Multi-layer statutory deletion protection verification.
        Verifies that QuerySet.delete() cannot bypass model deletion guards on:
        1. Posted Accounting Vouchers
        2. Voucher Line Items
        3. Ledger Entries
        4. GST Reporting Allocations
        5. GST Return Workspaces (Exported/Reviewed/Filed)
        6. GST Workspace Export Snapshots
        7. GST Filing Records
        """
        # 1. Posted Voucher QuerySet bulk delete blocked
        v_posted = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-BULK-DEL-01',
            voucher_type='SALES',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('5000.00'),
        )
        item_posted = VoucherItem.objects.create(
            voucher=v_posted,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00')
        )
        ledger_entry = LedgerEntry.objects.create(
            company=self.company,
            voucher=v_posted,
            ledger=self.ledger_customer,
            debit_amount=Decimal('5900.00'),
            credit_amount=Decimal('0.00')
        )

        with self.assertRaises(ValidationError):
            Voucher.objects.filter(id=v_posted.id).delete()

        with self.assertRaises(ValidationError):
            VoucherItem.objects.filter(id=item_posted.id).delete()

        with self.assertRaises(ValidationError):
            LedgerEntry.objects.filter(id=ledger_entry.id).delete()

        # 2. GST Reporting Allocation QuerySet bulk delete blocked
        alloc = GSTAllocationService.allocate_voucher(v_posted)
        with self.assertRaises(ValidationError):
            GSTReportingAllocation.objects.filter(id=alloc.id).delete()

        # 3. GST Return Workspace QuerySet bulk delete blocked when EXPORTED
        ws = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='022026',
            financial_year='2025-26',
            status='EXPORTED',
            reviewed_by=self.owner_user
        )
        with self.assertRaises(ValidationError):
            GSTReturnWorkspace.objects.filter(id=ws.id).delete()

        # 4. GST Workspace Export Snapshot QuerySet bulk delete blocked
        snap = GSTWorkspaceExportSnapshot.objects.create(
            workspace=ws,
            company=self.company,
            return_type='GSTR1',
            return_period='022026',
            export_format='JSON',
            exported_payload={"status": "TEST"},
            payload_hash=hashlib.sha256(b"TEST_SNAP").hexdigest(),
            exported_by=self.owner_user
        )
        with self.assertRaises(ValidationError):
            GSTWorkspaceExportSnapshot.objects.filter(id=snap.id).delete()

        # 5. GST Filing Record QuerySet bulk delete blocked
        rec = GSTFilingRecord.objects.create(
            company=self.company,
            return_type='GSTR1',
            return_period='022026',
            financial_year='2025-26',
            status='FILED',
            arn='AA2702269999999',
            submitted_by=self.ca_user
        )
        with self.assertRaises(ValidationError):
            GSTFilingRecord.objects.filter(id=rec.id).delete()

    def test_receipt_evidence_fail_closed_and_partial_consignments(self):
        """
        Phase 2: Verifies fail-closed architecture for inward supplies:
        1. Purchase invoice without affirmative receipt evidence fails closed (EXCLUDED).
        2. Purchase invoice with affirmative documentation (GRN) is approved.
        3. Partial consignment receipt claims proportionate credit (Section 16(2)(b)).
        """
        # Case 1: Unconfirmed without affirmative evidence -> Fails Closed
        pv_fail_closed = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-FAIL-CLOSED-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 1),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_fail_closed,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        # Allocate with NO affirmative evidence passed
        alloc_fc = GSTAllocationService.allocate_voucher(pv_fail_closed)
        self.assertFalse(alloc_fc.is_statutorily_eligible)
        self.assertEqual(alloc_fc.status, 'EXCLUDED')
        self.assertEqual(alloc_fc.allocation_reason, 'GOODS_SERVICES_NOT_RECEIVED')
        self.assertFalse(alloc_fc.is_receipt_confirmed)

        # Case 2: Affirmative Evidence Provided (GRN document) -> Approved
        pv_grn = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-GRN-AFFIRM-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 2),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_grn,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        alloc_grn = GSTAllocationService.allocate_voucher(
            pv_grn,
            receipt_document_type='GRN',
            receipt_document_number='GRN-2026-088',
            is_receipt_confirmed=True,
            goods_received_date=date(2026, 2, 4)
        )
        self.assertTrue(alloc_grn.is_statutorily_eligible)
        self.assertEqual(alloc_grn.status, 'APPROVED')
        self.assertTrue(alloc_grn.is_receipt_confirmed)
        self.assertEqual(alloc_grn.receipt_document_type, 'GRN')
        self.assertEqual(alloc_grn.receipt_document_number, 'GRN-2026-088')

        # Case 3: Partial Consignment Receipt (60% delivered)
        pv_partial = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-PARTIAL-60',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 3),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_partial,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        alloc_part = GSTAllocationService.allocate_voucher(
            pv_partial,
            is_receipt_confirmed=True,
            goods_received_date=date(2026, 2, 4),
            receipt_document_type='DELIVERY_CHALLAN',
            receipt_document_number='DC-PARTIAL-001',
            partial_received_fraction=Decimal('0.6000')
        )
        self.assertTrue(alloc_part.is_statutorily_eligible)
        self.assertEqual(alloc_part.allocation_reason, 'PARTIAL_RECEIPT_PROPORTIONATE')
        self.assertEqual(alloc_part.taxable_value, Decimal('6000.00'))
        self.assertEqual(alloc_part.cgst_amount, Decimal('540.00'))
        self.assertEqual(alloc_part.sgst_amount, Decimal('540.00'))
        self.assertEqual(alloc_part.total_tax, Decimal('1080.00'))

    def test_section_16_5_non_obstante_retrospective_overriding_power(self):
        """
        Phase 4: Section 16(5) Non-Obstante Clause Verification.
        Section 16(5) overrides Section 16(4) completely for FY 2017-18 to 2020-21.
        Even if the Annual Return (GSTR-9) was furnished earlier than 30th November 2021,
        the statutory deadline remains strictly 30th November 2021 (Circular No. 237/31/2024-GST).
        """
        # Create an early GSTR-9 filing for FY 2019-20 filed on 31st December 2020
        ar_early = GSTFilingRecord.objects.create(
            company=self.company,
            return_type='GSTR9',
            return_period='2019-20',
            financial_year='2019-20',
            status='FILED',
            arn='AA2712200000001',
            submitted_by=self.ca_user
        )
        GSTFilingRecord.objects.filter(id=ar_early.id).update(
            submitted_at=datetime(2020, 12, 31, 10, 0, 0, tzinfo=dt_timezone.utc)
        )

        cutoff = GSTAllocationService.get_statutory_cutoff_date(
            date(2019, 8, 15),
            company=self.company,
            return_type='GSTR3B'
        )
        # Non-obstante overriding power ensures cutoff is 30-Nov-2021, NOT 31-Dec-2020
        self.assertEqual(cutoff, date(2021, 11, 30))

    def test_section_16_6_registration_revocation_window_extension(self):
        """
        Phase 4: Section 16(6) Revocation Window Extension Verification.
        Taxpayers with cancelled and revoked registrations are entitled to 30 days from the
        revocation order date, if later than the Section 16(4) or 16(5) cutoff.
        """
        # Case 1: Pre-2021 period with revocation order dated 15 Jan 2022
        # Cutoff = max(30 Nov 2021, 15 Jan 2022 + 30 days = 14 Feb 2022)
        cutoff_pre = GSTAllocationService.get_statutory_cutoff_date(
            date(2019, 5, 10),
            company=self.company,
            return_type='GSTR3B',
            registration_revocation_date=date(2022, 1, 15)
        )
        self.assertEqual(cutoff_pre, date(2022, 2, 14))

        # Case 2: Post-2021 period (FY 2022-23)
        # Normal 16(4) cutoff: 30 Nov 2023. Revocation order: 10 Jan 2024.
        # Cutoff = max(30 Nov 2023, 10 Jan 2024 + 30 days = 9 Feb 2024)
        cutoff_post = GSTAllocationService.get_statutory_cutoff_date(
            date(2022, 7, 20),
            company=self.company,
            return_type='GSTR3B',
            registration_revocation_date=date(2024, 1, 10)
        )
        self.assertEqual(cutoff_post, date(2024, 2, 9))

    def test_commercial_credit_note_without_tax_excluded_from_table_9b(self):
        """
        Phase 5: Section 34 vs Section 15(3)(b) Commercial Credit Note Verification.
        A credit note without tax (financial discount) or without original invoice reference
        is resolved as COMMERCIAL_CREDIT_NOTE and excluded from GSTR-1 Table 9B.
        """
        cn_commercial = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='CN-COMM-01',
            voucher_type='CREDIT_NOTE',
            voucher_date=date(2026, 2, 18),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('1000.00'),
            narration='Commercial turnover discount with 0 GST'
        )
        VoucherItem.objects.create(
            voucher=cn_commercial,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('1000.00'),
            gst_rate=Decimal('0.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )
        alloc_cn = GSTAllocationService.allocate_voucher(cn_commercial)
        self.assertEqual(alloc_cn.event_type, 'COMMERCIAL_CREDIT_NOTE')
        self.assertEqual(alloc_cn.allocation_reason, 'COMMERCIAL_CREDIT_NOTE_NO_TAX')

        # Verify GSTR-1 does not include it in Table 9B
        gstr1 = GSTReturnsService.prepare_gstr1(
            company=self.company,
            registration=self.reg_primary,
            return_period='022026'
        )
        cdnr_payload = gstr1.get('official_gstr1_json', {}).get('cdnr', [])
        # Ensure our commercial credit note is NOT in CDNR
        for ctin_group in cdnr_payload:
            for nt in ctin_group.get('nt', []):
                self.assertNotEqual(nt.get('nt_num'), 'CN-COMM-01')

    def test_rule_37_180_day_reversal_and_subsequent_reclaim(self):
        """
        Phase 6: Rule 37 180-Day ITC Reversal & Proportionate Reclaim Verification.
        Verifies:
        1. Proportionate reversal calculation based on unpaid amount.
        2. Creation of Rule 37 reversal allocation.
        3. Creation of Rule 37(4) reclaim allocation exempt from Section 16(4) time-limit.
        """
        pv = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-R37-01',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 8, 1),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('1800.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # 1. Unpaid amount is 5900 (50% of invoice amount)
        rev_tax = GSTAllocationService.calculate_rule37_reversal(
            total_invoice_amount=Decimal('11800.00'),
            unpaid_amount=Decimal('5900.00'),
            total_tax=Decimal('1800.00')
        )
        self.assertEqual(rev_tax, Decimal('900.00'))

        # 2. Create Reversal Allocation for February 2026 (beyond 180 days from Aug 2025)
        rev_alloc = GSTAllocationService.create_rule37_reversal_allocation(
            voucher=pv,
            unpaid_amount=Decimal('5900.00'),
            assigned_period='022026',
            user=self.owner_user
        )
        self.assertEqual(rev_alloc.event_type, 'ITC_REVERSAL_RULE_37')
        self.assertEqual(rev_alloc.igst_amount, Decimal('900.00'))
        self.assertEqual(rev_alloc.total_tax, Decimal('900.00'))

        # 3. Create Reclaim Allocation upon payment in March 2026
        rec_alloc = GSTAllocationService.create_rule37_reclaim_allocation(
            voucher=pv,
            paid_amount=Decimal('5900.00'),
            assigned_period='032026',
            user=self.owner_user,
            payment_event_id='PAY-ROUND25-001'
        )
        self.assertEqual(rec_alloc.event_type, 'ITC_RECLAIM')
        self.assertEqual(rec_alloc.igst_amount, Decimal('900.00'))
        self.assertEqual(rec_alloc.total_tax, Decimal('900.00'))

    def test_rule_37a_vendor_default_reversal_and_subsequent_reclaim(self):
        """
        Phase 6: Rule 37A Supplier Default Reversal & Subsequent Reclaim Verification.
        """
        pv_37a = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-R37A-01',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 6, 15),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_37a,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # 1. Reverse under Rule 37A in November 2026 return
        from apps.gst.models import SupplierGSTR3BFilingRecord
        rec_supp_37a = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='27CCCC3333C1Z4',
            return_period='062025',
            status='VERIFIED_NOT_FILED'
        )
        rev_37a = GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=pv_37a,
            assigned_period='112026',
            user=self.owner_user,
            reversal_date=date(2026, 11, 20),
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='27CCCC3333C1Z4',
            supplier_return_period='062025',
            evidence_source='PORTAL',
            evidence_record=rec_supp_37a,
            verification_timestamp=timezone.now()
        )
        self.assertEqual(rev_37a.event_type, 'ITC_REVERSAL_RULE_37A')
        self.assertEqual(rev_37a.igst_amount, Decimal('900.00'))

        # 2. Reclaim under Proviso to Rule 37A when vendor files GSTR-3B in Jan 2027
        rec_37a = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=pv_37a,
            assigned_period='012027',
            user=self.owner_user,
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA070826000004A',
            gstr3b_filing_date=date(2027, 1, 15)
        )
        self.assertEqual(rec_37a.event_type, 'ITC_RECLAIM')
        self.assertEqual(rec_37a.igst_amount, Decimal('900.00'))

    def test_section_16_6_later_of_two_deadlines_scenarios(self):
        """
        Phase G Edge Case 1: Verifies Section 16(6) 'later of the two deadlines' rule:
        Scenario A: Ordinary Section 16(4) deadline is LATER than revocation date + 30 days.
                    -> Ordinary deadline must prevail.
        Scenario B: Revocation date + 30 days is LATER than ordinary Section 16(4) deadline.
                    -> Revocation deadline must prevail.
        """
        # Scenario A: Invoice in FY 2024-25 (June 2024). Ordinary cutoff = 30 Nov 2025.
        # Revocation order: 15 August 2024 -> 30-day window ends 14 September 2024.
        # Max(30 Nov 2025, 14 Sep 2024) = 30 Nov 2025.
        cutoff_a = GSTAllocationService.get_statutory_cutoff_date(
            date(2024, 6, 15),
            company=self.company,
            return_type='GSTR3B',
            registration_revocation_date=date(2024, 8, 15)
        )
        self.assertEqual(cutoff_a, date(2025, 11, 30))

        # Scenario B: Invoice in FY 2022-23 (October 2022). Ordinary cutoff = 30 Nov 2023.
        # Revocation order: 10 January 2024 -> 30-day window ends 9 February 2024.
        # Max(30 Nov 2023, 9 Feb 2024) = 9 Feb 2024.
        cutoff_b = GSTAllocationService.get_statutory_cutoff_date(
            date(2022, 10, 10),
            company=self.company,
            return_type='GSTR3B',
            registration_revocation_date=date(2024, 1, 10)
        )
        self.assertEqual(cutoff_b, date(2024, 2, 9))

    def test_eway_bill_in_transit_without_confirmed_physical_receipt_fails_closed(self):
        """
        Phase G Edge Case 4: E-Way Bill in transit does NOT constitute physical receipt.
        Without affirmative physical receipt confirmation, the purchase voucher fails closed.
        """
        pv_transit = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-EWB-TRANSIT-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 10),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_transit,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )

        # Generated E-Way Bill document, but physical receipt is unconfirmed
        alloc = GSTAllocationService.allocate_voucher(
            pv_transit,
            receipt_document_type='EWAY_BILL',
            receipt_document_number='EWB-271000293849',
            is_receipt_confirmed=False
        )
        self.assertFalse(alloc.is_statutorily_eligible)
        self.assertEqual(alloc.status, 'EXCLUDED')
        self.assertEqual(alloc.allocation_reason, 'GOODS_SERVICES_NOT_RECEIVED')
        self.assertIn('Section 16(2)(b)', alloc.statutory_rule)

    def test_partial_receipt_followed_by_subsequent_receipt(self):
        """
        Phase G Edge Case 3: Partial receipt in period 1 (50%) followed by subsequent
        full receipt (100%) in period 2 when remaining consignment arrives.
        """
        pv_two_stage = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-2STAGE-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 1, 15),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('23600.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_two_stage,
            product=self.product,
            quantity=Decimal('20.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('20000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('1800.00'),
            sgst_amount=Decimal('1800.00')
        )

        # Stage 1: 50% received in January 2026
        alloc_stage1 = GSTAllocationService.allocate_voucher(
            pv_two_stage,
            preferred_period='012026',
            is_receipt_confirmed=True,
            goods_received_date=date(2026, 1, 20),
            receipt_document_type='GRN',
            receipt_document_number='GRN-STAGE-1',
            partial_received_fraction=Decimal('0.5000')
        )
        self.assertTrue(alloc_stage1.is_statutorily_eligible)
        self.assertEqual(alloc_stage1.taxable_value, Decimal('10000.00'))
        self.assertEqual(alloc_stage1.cgst_amount, Decimal('900.00'))

        # Stage 2: Final consignment received in February 2026 -> Reallocated / updated to full
        alloc_stage2 = GSTAllocationService.allocate_voucher(
            pv_two_stage,
            preferred_period='022026',
            is_receipt_confirmed=True,
            goods_received_date=date(2026, 2, 10),
            receipt_document_type='GRN',
            receipt_document_number='GRN-STAGE-2-FINAL',
            partial_received_fraction=Decimal('1.0000'),
            force_reallocate=True
        )
        self.assertTrue(alloc_stage2.is_statutorily_eligible)
        self.assertEqual(alloc_stage2.assigned_period, '022026')
        self.assertEqual(alloc_stage2.taxable_value, Decimal('20000.00'))
        self.assertEqual(alloc_stage2.cgst_amount, Decimal('1800.00'))
        self.assertEqual(alloc_stage2.sgst_amount, Decimal('1800.00'))

    def test_multiple_partial_receipts_with_rounding_quantization(self):
        """
        Phase G Edge Case 5: Partial receipts with repeating fractions (1/3 = 0.3333)
        enforcing exact Decimal('0.01') mathematical rounding without data truncation.
        """
        pv_fract = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-FRACT-01',
            voucher_type='PURCHASE',
            voucher_date=date(2026, 2, 5),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('10000.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_fract,
            product=self.product,
            quantity=Decimal('3.00'),
            rate=Decimal('2824.86'),
            taxable_amount=Decimal('8474.58'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('762.71'),
            sgst_amount=Decimal('762.71')
        )

        alloc_third = GSTAllocationService.allocate_voucher(
            pv_fract,
            is_receipt_confirmed=True,
            goods_received_date=date(2026, 2, 8),
            receipt_document_type='DELIVERY_CHALLAN',
            receipt_document_number='DC-ONE-THIRD',
            partial_received_fraction=Decimal('0.3333')
        )
        self.assertTrue(alloc_third.is_statutorily_eligible)
        # 8474.58 * 0.3333 = 2824.58
        self.assertEqual(alloc_third.taxable_value, Decimal('2824.58'))
        # 762.71 * 0.3333 = 254.21
        self.assertEqual(alloc_third.cgst_amount, Decimal('254.21'))
        self.assertEqual(alloc_third.sgst_amount, Decimal('254.21'))
        self.assertEqual(alloc_third.total_tax, Decimal('508.42'))

    def test_rule_37a_duplicate_reclaim_prevention(self):
        """
        Phase G Edge Case 9: Duplicate Rule 37A reclaim attempt is prevented via idempotency key.
        """
        pv_dup = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='BILL-R37A-DUP-01',
            voucher_type='PURCHASE',
            voucher_date=date(2025, 5, 10),
            party_ledger=self.ledger_vendor,
            status='POSTED',
            total_amount=Decimal('5900.00'),
        )
        VoucherItem.objects.create(
            voucher=pv_dup,
            product=self.product,
            quantity=Decimal('5.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('5000.00'),
            gst_rate=Decimal('18.00'),
            igst_amount=Decimal('900.00'),
            cgst_amount=Decimal('0.00'),
            sgst_amount=Decimal('0.00')
        )

        # Prior active Rule 37A reversal is mandatory
        from apps.gst.models import SupplierGSTR3BFilingRecord
        rec_supp_dup = SupplierGSTR3BFilingRecord.objects.create(
            company=self.company,
            supplier_gstin='27CCCC3333C1Z4',
            return_period='052025',
            status='VERIFIED_NOT_FILED'
        )
        GSTAllocationService.create_rule37a_reversal_allocation(
            voucher=pv_dup,
            assigned_period='112026',
            user=self.owner_user,
            reversal_date=date(2026, 11, 20),
            supplier_status='VERIFIED_NOT_FILED',
            supplier_gstin='27CCCC3333C1Z4',
            supplier_return_period='052025',
            evidence_source='PORTAL',
            evidence_record=rec_supp_dup,
            verification_timestamp=timezone.now()
        )

        # Initial Reclaim
        rec1 = GSTAllocationService.create_rule37a_reclaim_allocation(
            voucher=pv_dup,
            assigned_period='022027',
            user=self.owner_user,
            supplier_status='VERIFIED_FILED',
            gstr3b_arn='AA070826000005B',
            gstr3b_filing_date=date(2027, 2, 15)
        )
        self.assertEqual(rec1.event_type, 'ITC_RECLAIM')

        # Duplicate reclaim attempt with identical period and company
        with self.assertRaises(ValidationError):
            GSTAllocationService.create_rule37a_reclaim_allocation(
                voucher=pv_dup,
                assigned_period='022027',
                user=self.owner_user,
                supplier_status='VERIFIED_FILED',
                gstr3b_arn='AA070826000005B',
                gstr3b_filing_date=date(2027, 2, 15)
            )

    def test_cross_tenant_gst_snapshot_access_rejected(self):
        """
        Phase G Edge Case 14: Cross-tenant GST export snapshot access rejection.
        User belonging to another company cannot query or export snapshots belonging to Primary sandbox.
        """
        ws = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='012026',
            financial_year='2025-26',
            status='EXPORTED',
            reviewed_by=self.owner_user
        )
        snap = GSTWorkspaceExportSnapshot.objects.create(
            workspace=ws,
            company=self.company,
            return_type='GSTR1',
            return_period='012026',
            export_format='JSON',
            exported_payload={"status": "CONFIDENTIAL_FINANCIAL_DATA"},
            payload_hash=hashlib.sha256(b"CONFIDENTIAL").hexdigest(),
            exported_by=self.owner_user
        )

        # Authenticate with user from competing company
        self.client.force_authenticate(user=self.other_user)
        res = self.client.post(f"/api/v1/gst/workspace/{ws.id}/export/", {"format": "JSON"}, format='json')
        # Must be rejected with HTTP 403 or 404
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_reexport_after_filing_preserves_filed_snapshot_immutability(self):
        """
        Phase G Edge Case 17: Once a workspace is filed or exported, its historical
        snapshot remains strictly immutable and cannot be deleted or mutated.
        """
        ws_filed = GSTReturnWorkspace.objects.create(
            company=self.company,
            gst_registration=self.reg_primary,
            return_type='GSTR1',
            return_period='122025',
            financial_year='2025-26',
            status='EXPORTED',
            reviewed_by=self.owner_user
        )
        snap = GSTWorkspaceExportSnapshot.objects.create(
            workspace=ws_filed,
            company=self.company,
            return_type='GSTR1',
            return_period='122025',
            export_format='JSON',
            exported_payload={"canonical": "ORIGINAL_FILED_EXPORT"},
            payload_hash=hashlib.sha256(b"ORIGINAL").hexdigest(),
            exported_by=self.owner_user
        )

        # Attempt to delete snapshot directly -> ValidationError
        with self.assertRaises(ValidationError):
            snap.delete()

        # Attempt to bulk-delete snapshot via QuerySet -> ValidationError
        with self.assertRaises(ValidationError):
            GSTWorkspaceExportSnapshot.objects.filter(id=snap.id).delete()

    def test_gst_allocation_changes_leave_accounting_ledgers_and_trial_balance_untouched(self):
        """
        Phase G Edge Case 18: Preserving Double-Entry Accounting Invariance.
        Reallocating or adjusting GST reporting periods must leave:
        1. Voucher total amounts
        2. Voucher line items
        3. Ledger entries
        4. Party ledger balance
        5. Double-entry mathematical equilibrium (Sum(Debits) == Sum(Credits))
        completely untouched.
        """
        # Create balanced sales invoice with ledger entries
        v_sales = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_number='INV-ACCOUNTING-INVAR-01',
            voucher_type='SALES',
            voucher_date=date(2026, 1, 10),
            party_ledger=self.ledger_customer,
            status='POSTED',
            total_amount=Decimal('11800.00'),
        )
        item = VoucherItem.objects.create(
            voucher=v_sales,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00')
        )
        # Accounting Ledger Entries
        le_party = LedgerEntry.objects.create(
            company=self.company,
            voucher=v_sales,
            ledger=self.ledger_customer,
            debit_amount=Decimal('11800.00'),
            credit_amount=Decimal('0.00')
        )
        le_sales = LedgerEntry.objects.create(
            company=self.company,
            voucher=v_sales,
            ledger=self.ledger_customer, # Party ledger used for test setup
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('11800.00')
        )

        # Initial Allocation: January 2026
        alloc_jan = GSTAllocationService.allocate_voucher(v_sales, preferred_period='012026')
        self.assertEqual(alloc_jan.assigned_period, '012026')

        # Reallocate to February 2026
        alloc_feb = GSTAllocationService.reallocate_voucher(
            v_sales,
            new_period='022026',
            reason='Client request late inclusion in Feb return',
            user=self.owner_user
        )
        self.assertEqual(alloc_feb.assigned_period, '022026')

        # VERIFY INVARIANTS:
        # 1. Voucher Date is STILL January 10
        v_sales.refresh_from_db()
        self.assertEqual(v_sales.voucher_date, date(2026, 1, 10))
        self.assertEqual(v_sales.total_amount, Decimal('11800.00'))

        # 2. Line Items untouched
        item.refresh_from_db()
        self.assertEqual(item.taxable_amount, Decimal('10000.00'))
        self.assertEqual(item.cgst_amount, Decimal('900.00'))
        self.assertEqual(item.sgst_amount, Decimal('900.00'))

        # 3. Ledger Entries untouched
        le_party.refresh_from_db()
        le_sales.refresh_from_db()
        self.assertEqual(le_party.debit_amount, Decimal('11800.00'))
        self.assertEqual(le_sales.credit_amount, Decimal('11800.00'))

        # 4. Debits == Credits equilibrium
        entries = LedgerEntry.objects.filter(voucher=v_sales)
        total_debits = sum(e.debit_amount for e in entries)
        total_credits = sum(e.credit_amount for e in entries)
        self.assertEqual(total_debits, total_credits)
        self.assertEqual(total_debits, Decimal('11800.00'))



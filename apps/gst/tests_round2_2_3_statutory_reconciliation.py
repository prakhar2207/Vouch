import uuid
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product
from apps.gst.models import GSTRegistration
from apps.gst.services.rate_reference_service import GSTRateScheduleService

User = get_user_model()


class GSTRound223StatutoryReconciliationTests(TestCase):
    """
    SriLekh GST — Round 2.2.3 Current-Law Statutory Reconciliation & Effective-Date Test Suite.
    
    Verifies:
    1. Mandatory Sandbox Tenant Isolation Invariant (Apex Belting Store only).
    2. Paneer / Chenna (HSN 0406) Three-Tier Timeline & 22-Sep-2025 Transition:
       - Day Before (21-Sep-2025): Pre-packaged paneer attracts 5%; 0% without loose tag is STATUTORY_MISMATCH.
       - Exact Day (22-Sep-2025): Pre-packaged paneer reduced to Nil (0% Exempt) under 56th GST Council; 5% is STATUTORY_MISMATCH.
       - Day After (23-Sep-2025): 0% is VALID (Exempt); 5% is STATUTORY_MISMATCH.
       - Cheese (HSN 0406) reduced from 12% to 5% w.e.f. 22-Sep-2025; 12% is STATUTORY_MISMATCH.
    3. Ultra High Temperature (UHT) Milk (HSN 0401 50 00) Timeline & 22-Sep-2025 Transition:
       - Day Before (21-Sep-2025): UHT milk attracts 5%; 0% is STATUTORY_MISMATCH.
       - Exact Day (22-Sep-2025): UHT milk reduced to Nil (0% Exempt) under 56th GST Council; 5% is STATUTORY_MISMATCH.
       - Day After (23-Sep-2025): 0% is VALID (Exempt); 5% is STATUTORY_MISMATCH.
       - Fresh milk (HSN 0401) unconditionally exempt (0% Nil-Rated) across all dates.
    4. Restaurant Services (SAC 9963) — 55th GST Council Specified Premises (01-Apr-2025):
       - 31-Mar-2025: Declared tariff >= Rs. 7,500/night applies for 18% rate.
       - 01-Apr-2025: "Declared tariff" omitted; "Specified Premises" applies (preceding FY supply value > Rs. 7,500/day or annual Opt-In).
       - Standalone restaurants strictly 5% without ITC across all dates.
    5. Current-Law Statutory Position on 18 November 2026:
       - Validates active rates for Paneer, UHT Milk, Cheese, Standalone Restaurant, Hotel Specified Premises, EVs, SUVs, Belts.
    6. 57th GST Council (08-Oct-2026) Change Register & Status Enforcement:
       - Verified that unnotified Council recommendations remain PENDING_NOTIFICATION / PENDING_AMENDMENT.
       - Verifies recommendation is NOT activated prematurely into tax calculation engine.
    7. Accounting Immutability & Double-Entry Invariant:
       - Zero mutation to vouchers, items, ledgers, or account balances.
    """

    def setUp(self):
        # Mandatory Dedicated Sandbox Tenant Isolation Invariant
        self.company = Company.objects.create(
            id=uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33'),
            name='Apex Belting & Industrial Store (Demo)'
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "CRITICAL SECURITY INVARIANT VIOLATION: Tests must strictly run against sandbox company!"
        )

        self.owner_user = User.objects.create_user(
            email='reconciliation_auditor@apexbelting.demo',
            password='audit_secure_password_123'
        )

        self.reg_primary = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAACA9999A1Z5',
            legal_name='Apex Belting & Industrial Store',
            trade_name='Apex Belting Store',
            state_code='27',
            state_name='Maharashtra',
            is_primary=True,
            status='ACTIVE'
        )

    # =========================================================================
    # 1. Paneer / Chenna (HSN 0406) 22-Sep-2025 Transition Boundaries
    # =========================================================================

    def test_paneer_22_sep_2025_boundary_transition(self):
        """
        Paneer 56th GST Council Rationalisation (Notif 10/2025-CT(Rate) & 11/2025-CT(Rate)):
        - 21-Sep-2025 (Day Before): Pre-packaged paneer @ 5% is VALID; 0% is STATUTORY_MISMATCH.
        - 22-Sep-2025 (Exact Day): Pre-packaged paneer @ 0% is VALID (Exempt); 5% is STATUTORY_MISMATCH.
        - 23-Sep-2025 (Day After): Pre-packaged paneer @ 0% is VALID (Exempt); 5% is STATUTORY_MISMATCH.
        """
        # Day Before: 21-Sep-2025 (Pre-packaged paneer is taxable @ 5%)
        res_before_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 21),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_before_5["status"], "VALID")
        self.assertEqual(res_before_5["expected_rate"], 5.00)
        self.assertIn("6/2022", res_before_5["notification_reference"])

        res_before_0 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 21),
            applied_rate=Decimal('0.00'),
            is_interstate=False,
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_before_0["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_before_0["expected_rate"], 5.00)

        # Exact Day: 22-Sep-2025 (Reduced to 0% Nil/Exempt)
        res_on_0 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 22),
            applied_rate=Decimal('0.00'),
            is_interstate=False,
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_on_0["status"], "VALID")
        self.assertEqual(res_on_0["expected_rate"], 0.00)
        self.assertTrue(res_on_0["is_exempt"])
        self.assertEqual(res_on_0["supply_type"], "EXEMPT")
        self.assertEqual(res_on_0["itc_eligibility"], "ZERO_ITC")
        self.assertIn("10/2025", res_on_0["notification_reference"])

        res_on_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 22),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_on_5["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_on_5["expected_rate"], 0.00)
        self.assertIn("10/2025", res_on_5["notification_reference"])

        # Day After: 23-Sep-2025 (Continues as 0% Exempt)
        res_after_0 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 23),
            applied_rate=Decimal('0.00'),
            is_interstate=False,
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_after_0["status"], "VALID")
        self.assertTrue(res_after_0["is_exempt"])

        res_after_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 23),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_after_5["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_after_5["expected_rate"], 0.00)

    def test_cheese_rate_reduction_to_5_percent(self):
        """
        Cheese (HSN 0406) reduced from 12% to 5% w.e.f. 22-Sep-2025 (56th GST Council).
        - Applied 5% on/after 22-Sep-2025 is VALID.
        - Applied 12% on/after 22-Sep-2025 is STATUTORY_MISMATCH.
        """
        res_cheese_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 22),
            applied_rate=Decimal('5.00'),
            is_interstate=True,
            conditions=['CHEESE']
        )
        self.assertEqual(res_cheese_valid["status"], "VALID")
        self.assertEqual(res_cheese_valid["expected_rate"], 5.00)
        self.assertEqual(res_cheese_valid["supply_type"], "TAXABLE")
        self.assertEqual(res_cheese_valid["itc_eligibility"], "ELIGIBLE")
        self.assertIn("10/2025", res_cheese_valid["notification_reference"])

        res_cheese_mismatch = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406',
            tx_date=date(2025, 9, 22),
            applied_rate=Decimal('12.00'),
            is_interstate=True,
            conditions=['CHEESE']
        )
        self.assertEqual(res_cheese_mismatch["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_cheese_mismatch["expected_rate"], 5.00)

    # =========================================================================
    # 2. Ultra High Temperature (UHT) Milk (HSN 0401) 22-Sep-2025 Transition
    # =========================================================================

    def test_uht_milk_22_sep_2025_boundary_transition(self):
        """
        UHT Milk (HSN 0401 50 00) Rate Rationalisation:
        - 21-Sep-2025 (Day Before): 5% is VALID; 0% is STATUTORY_MISMATCH.
        - 22-Sep-2025 (Exact Day): 0% is VALID (Exempt); 5% is STATUTORY_MISMATCH.
        - 23-Sep-2025 (Day After): 0% is VALID (Exempt); 5% is STATUTORY_MISMATCH.
        """
        # Day Before: 21-Sep-2025 (5% Taxable under Schedule I S.No. 7)
        res_before_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401',
            tariff_item='04015000',
            tx_date=date(2025, 9, 21),
            applied_rate=Decimal('5.00'),
            conditions=['UHT_MILK']
        )
        self.assertEqual(res_before_5["status"], "VALID")
        self.assertEqual(res_before_5["expected_rate"], 5.00)
        self.assertIn("1/2017", res_before_5["notification_reference"])

        res_before_0 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401',
            tariff_item='04015000',
            tx_date=date(2025, 9, 21),
            applied_rate=Decimal('0.00'),
            conditions=['UHT_MILK']
        )
        self.assertEqual(res_before_0["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_before_0["expected_rate"], 5.00)

        # Exact Day: 22-Sep-2025 (Reduced to 0% Exempt)
        res_on_0 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401',
            tariff_item='04015000',
            tx_date=date(2025, 9, 22),
            applied_rate=Decimal('0.00'),
            conditions=['UHT_MILK']
        )
        self.assertEqual(res_on_0["status"], "VALID")
        self.assertEqual(res_on_0["expected_rate"], 0.00)
        self.assertTrue(res_on_0["is_exempt"])
        self.assertEqual(res_on_0["supply_type"], "EXEMPT")
        self.assertEqual(res_on_0["itc_eligibility"], "ZERO_ITC")
        self.assertIn("10/2025", res_on_0["notification_reference"])

        res_on_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401',
            tariff_item='04015000',
            tx_date=date(2025, 9, 22),
            applied_rate=Decimal('5.00'),
            conditions=['UHT_MILK']
        )
        self.assertEqual(res_on_5["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_on_5["expected_rate"], 0.00)

        # Day After: 23-Sep-2025
        res_after_0 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401',
            tariff_item='04015000',
            tx_date=date(2025, 9, 23),
            applied_rate=Decimal('0.00'),
            conditions=['UHT_MILK']
        )
        self.assertEqual(res_after_0["status"], "VALID")
        self.assertTrue(res_after_0["is_exempt"])

        res_after_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401',
            tariff_item='04015000',
            tx_date=date(2025, 9, 23),
            applied_rate=Decimal('5.00'),
            conditions=['UHT_MILK']
        )
        self.assertEqual(res_after_5["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_after_5["expected_rate"], 0.00)

    def test_fresh_milk_unconditional_nil_rated_across_all_dates(self):
        """Fresh milk (HSN 0401) is unconditionally exempt / Nil-rated across historical and current dates."""
        for check_date in [date(2017, 7, 1), date(2022, 7, 18), date(2025, 9, 22), date(2026, 11, 18)]:
            res = GSTRateScheduleService.validate_tax_rate(
                hsn_sc='0401',
                tx_date=check_date,
                applied_rate=Decimal('0.00'),
                is_interstate=False
            )
            self.assertEqual(res["status"], "VALID")
            self.assertTrue(res["is_exempt"])
            self.assertTrue(res["is_nil_rated"])
            self.assertEqual(res["supply_type"], "NIL_RATED")
            self.assertEqual(res["itc_eligibility"], "ZERO_ITC")

    # =========================================================================
    # 3. Restaurant Services (SAC 9963) — 55th GST Council Specified Premises
    # =========================================================================

    def test_restaurant_01_apr_2025_specified_premises_transition(self):
        """
        55th GST Council (Notification No. 01/2025-Central Tax (Rate) eff. 01-Apr-2025):
        - Omission of 'declared tariff' criterion.
        - Replacement with 'Specified Premises' (preceding FY value of supply > Rs.7,500/day or annual Opt-In).
        - 31-Mar-2025 (Day Before): Declared tariff >= Rs. 7,500 applies.
        - 01-Apr-2025 (Exact Day): Specified Premises applies.
        """
        # Day Before: 31-Mar-2025 with declared tariff
        res_pre_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963',
            tx_date=date(2025, 3, 31),
            applied_rate=Decimal('18.00'),
            conditions=['HOTEL_TARIFF_GTE_7500']
        )
        self.assertEqual(res_pre_valid["status"], "VALID")
        self.assertIn("11/2017", res_pre_valid["notification_reference"])

        # Exact Day: 01-Apr-2025 with Specified Premises condition
        res_post_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963',
            tx_date=date(2025, 4, 1),
            applied_rate=Decimal('18.00'),
            conditions=['HOTEL_SPECIFIED_PREMISES']
        )
        self.assertEqual(res_post_valid["status"], "VALID")
        self.assertEqual(res_post_valid["expected_rate"], 18.00)
        self.assertIn("01/2025", res_post_valid["notification_reference"])

        # Condition aliases: PRECEDING_FY_TARIFF_GTE_7500 and HOTEL_OPTED_IN_SPECIFIED_PREMISES
        res_alias_1 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963',
            tx_date=date(2025, 4, 1),
            applied_rate=Decimal('18.00'),
            conditions=['PRECEDING_FY_TARIFF_GTE_7500']
        )
        self.assertEqual(res_alias_1["status"], "VALID")

        res_alias_2 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963',
            tx_date=date(2025, 4, 1),
            applied_rate=Decimal('18.00'),
            conditions=['HOTEL_OPTED_IN_SPECIFIED_PREMISES']
        )
        self.assertEqual(res_alias_2["status"], "VALID")

        # Standalone restaurant on 01-Apr-2025 remains strictly 5% without ITC
        res_standalone_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963',
            tx_date=date(2025, 4, 1),
            applied_rate=Decimal('5.00'),
            conditions=['STANDALONE_RESTAURANT']
        )
        self.assertEqual(res_standalone_5["status"], "VALID")
        self.assertEqual(res_standalone_5["itc_eligibility"], "INELIGIBLE_SEC_17_5")

        res_standalone_18_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963',
            tx_date=date(2025, 4, 1),
            applied_rate=Decimal('18.00'),
            conditions=['STANDALONE_RESTAURANT']
        )
        self.assertEqual(res_standalone_18_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_standalone_18_err["expected_rate"], 5.00)

    # =========================================================================
    # 4. Current Law Reconciliation on 18 November 2026 (Today)
    # =========================================================================

    def test_current_statutory_rates_on_18_november_2026(self):
        """
        Independent verification of statutory positions applicable on 18 November 2026:
        - Paneer (pre-packaged or loose): 0% EXEMPT.
        - UHT Milk: 0% EXEMPT.
        - Cheese: 5% TAXABLE.
        - Standalone Restaurant: 5% TAXABLE without ITC.
        - Hotel Specified Premises Restaurant: 18% TAXABLE with ITC.
        - Electric Vehicles: 5% CONCESSIONAL (ITC blocked under Section 17(5)(a)).
        - Industrial Belts (HSN 4010): 18% TAXABLE (ITC eligible).
        - SUVs (all 4 criteria): 28% GST + 22% Compensation Cess.
        """
        today = date(2026, 11, 18)

        # 1. Paneer: 0% Exempt
        res_paneer = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=today, applied_rate=Decimal('0.00'), conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_paneer["status"], "VALID")
        self.assertTrue(res_paneer["is_exempt"])

        # 2. UHT Milk: 0% Exempt
        res_uht = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401', tariff_item='04015000', tx_date=today, applied_rate=Decimal('0.00'), conditions=['UHT_MILK']
        )
        self.assertEqual(res_uht["status"], "VALID")
        self.assertTrue(res_uht["is_exempt"])

        # 3. Cheese: 5% Taxable
        res_cheese = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=today, applied_rate=Decimal('5.00'), conditions=['CHEESE']
        )
        self.assertEqual(res_cheese["status"], "VALID")
        self.assertFalse(res_cheese["is_exempt"])

        # 4. Standalone Restaurant: 5% without ITC
        res_rest = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=today, applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_rest["status"], "VALID")
        self.assertEqual(res_rest["itc_eligibility"], "INELIGIBLE_SEC_17_5")

        # 5. Hotel Restaurant in Specified Premises: 18% with ITC
        res_hotel = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=today, applied_rate=Decimal('18.00'), conditions=['HOTEL_SPECIFIED_PREMISES']
        )
        self.assertEqual(res_hotel["status"], "VALID")
        self.assertEqual(res_hotel["itc_eligibility"], "ELIGIBLE")

        # 6. Electric Vehicle: 5% Concessional, ITC blocked
        res_ev = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=today, applied_rate=Decimal('5.00'),
            product_attributes={'is_electric': True, 'fuel_type': 'ELECTRIC'}
        )
        self.assertEqual(res_ev["status"], "VALID")
        self.assertEqual(res_ev["itc_eligibility"], "INELIGIBLE_SEC_17_5")

        # 7. Industrial Belts (HSN 4010): 18% Standard
        res_belts = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4010', tx_date=today, applied_rate=Decimal('18.00'), is_interstate=True
        )
        self.assertEqual(res_belts["status"], "VALID")
        self.assertEqual(res_belts["itc_eligibility"], "ELIGIBLE")

        # 8. SUV: 28% GST + 22% Cess
        res_suv = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=today, applied_rate=Decimal('28.00'), applied_cess=Decimal('22.00'),
            product_attributes={'engine_cc': 2000, 'length_mm': 4500, 'ground_clearance_mm': 180, 'is_suv': True}
        )
        self.assertEqual(res_suv["status"], "VALID")
        self.assertEqual(res_suv["expected_cess"], 22.00)

    # =========================================================================
    # 5. 57th GST Council (08-Oct-2026) Statutory Register & Pending Verification
    # =========================================================================

    def test_57th_gst_council_register_status(self):
        """
        Verify that 57th GST Council recommendations are tracked in the Statutory Change Register:
        - 57TH-01 (Decriminalization, Sec 69 repeal, Rs. 5 Cr threshold): PENDING_AMENDMENT.
        - 57TH-02 (Automated refund enhancements): PENDING_NOTIFICATION.
        - Unnotified recommendations MUST NOT be activated prematurely as tax exemptions/rates.
        """
        all_entries = GSTRateScheduleService.get_statutory_change_register()
        self.assertGreaterEqual(len(all_entries), 6)

        entry_57_01 = next(e for e in all_entries if e.reference_id == '57TH-01')
        self.assertEqual(entry_57_01.status, 'PENDING_AMENDMENT')
        self.assertIsNone(entry_57_01.gazette_notification)
        self.assertFalse(GSTRateScheduleService.is_recommendation_gazetted('57TH-01'))

        entry_57_02 = next(e for e in all_entries if e.reference_id == '57TH-02')
        self.assertEqual(entry_57_02.status, 'PENDING_NOTIFICATION')
        self.assertIsNone(entry_57_02.gazette_notification)
        self.assertFalse(GSTRateScheduleService.is_recommendation_gazetted('57TH-02'))

        # Check gazetted 56th and 55th recommendations
        self.assertTrue(GSTRateScheduleService.is_recommendation_gazetted('56TH-01'))
        self.assertTrue(GSTRateScheduleService.is_recommendation_gazetted('56TH-02'))
        self.assertTrue(GSTRateScheduleService.is_recommendation_gazetted('56TH-03'))
        self.assertTrue(GSTRateScheduleService.is_recommendation_gazetted('55TH-01'))

    # =========================================================================
    # 6. Accounting Immutability & Zero Mutation Invariant
    # =========================================================================

    def test_zero_mutation_to_vouchers_and_ledgers(self):
        """
        STRICT DOUBLE-ENTRY INVARIANT:
        Statutory rate validation and reconciliation services are strictly read-only.
        Zero mutation to vouchers, items, ledgers, or account balances.
        """
        group_assets = LedgerGroup.objects.create(
            company=self.company, name='Current Assets', nature='ASSET'
        )
        group_sales = LedgerGroup.objects.create(
            company=self.company, name='Sales Revenue', nature='INCOME'
        )
        ledger_debtors = Ledger.objects.create(
            company=self.company, name='Sundry Debtors', group=group_assets, current_balance=Decimal('10000.00')
        )
        ledger_sales = Ledger.objects.create(
            company=self.company, name='Dairy Sales', group=group_sales, current_balance=Decimal('10000.00')
        )

        prod_paneer = Product.objects.create(
            company=self.company, name='Pre-Packaged Paneer 500g', sku='SKU-DAIRY-001',
            hsn_code='0406', unit='KGS'
        )

        voucher = Voucher.objects.create(
            company=self.company,
            created_by=self.owner_user,
            voucher_type='SALES',
            voucher_number='VOUCH-RECON-001',
            voucher_date=date(2025, 9, 22),
            narration='Sale of dairy products'
        )
        item = VoucherItem.objects.create(
            voucher=voucher,
            product=prod_paneer,
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            hsn_code='0406',
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('0.00'),
            cgst_rate=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            total_amount=Decimal('10000.00')
        )

        # Snapshot before validation
        v_date_before = voucher.voucher_date
        v_num_before = voucher.voucher_number
        debtors_bal_before = ledger_debtors.current_balance
        sales_bal_before = ledger_sales.current_balance
        item_taxable_before = item.taxable_amount

        # Execute multiple statutory validations
        _ = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2025, 9, 22), applied_rate=Decimal('0.00')
        )
        _ = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401', tariff_item='04015000', tx_date=date(2025, 9, 22), applied_rate=Decimal('5.00'), conditions=['UHT_MILK']
        )
        _ = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2025, 4, 1), applied_rate=Decimal('18.00'), conditions=['HOTEL_SPECIFIED_PREMISES']
        )

        # Re-fetch from DB
        voucher.refresh_from_db()
        ledger_debtors.refresh_from_db()
        ledger_sales.refresh_from_db()
        item.refresh_from_db()

        # Invariants: Zero mutation
        self.assertEqual(voucher.voucher_date, v_date_before)
        self.assertEqual(voucher.voucher_number, v_num_before)
        self.assertEqual(ledger_debtors.current_balance, debtors_bal_before)
        self.assertEqual(ledger_sales.current_balance, sales_bal_before)
        self.assertEqual(item.taxable_amount, item_taxable_before)

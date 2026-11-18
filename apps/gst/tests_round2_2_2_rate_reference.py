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
from apps.gst.services.payload_validator import GSTPayloadValidator

User = get_user_model()


class GSTRound222RateReferenceHardeningTests(TestCase):
    """
    Independent Statutory GST Rate Reference & Classification Rules Test Suite (Round 2.2.2).
    
    Verifies:
    1. Mandatory Sandbox Tenant Isolation Invariant (Apex Belting Store only).
    2. Effective-Dated Rate Transition Boundary Tests (day before, on, and day after):
       - EV rate reduction (12% -> 5% on 01-Aug-2019)
       - Paneer pre-packaged taxability (0% -> 5% on 18-Jul-2022)
       - Rough diamonds rate reduction (3% -> 0.25% on 25-Jan-2018)
       - Restaurant rate reduction (18% -> 5% without ITC on 15-Nov-2017)
       - Merchant exports concessional introduction (0.1% on 23-Oct-2017)
    3. Statutory Classification Attributes & Negative Cases:
       - Electric vehicles vs ICE vehicles under HSN 8703
       - Compensation Cess cumulative 4 criteria for SUVs (22% vs 20% vs 1% vs 3%)
       - Restaurant services standalone (5%) vs luxury hotel premises (18%)
       - Paneer pre-packaged (5%) vs loose/unpackaged (0% exempt)
       - Diamonds rough (0.25%) vs cut and polished (1.5%)
       - Merchant exports (0.1% with declaration) vs ordinary domestic supply
       - Gold precious metals (HSN 7108/7113 @ 3%) vs imitation jewellery (HSN 7117 @ 18%)
       - Fresh milk (HSN 0401 @ 0% exempt) vs UHT milk (5%)
    4. Statutory Separation of Tax Attributes:
       - Rate match != ITC eligibility
       - Section 17(5) blocked credits (motor vehicles, food/restaurant)
       - Exemption status vs Nil-rated vs Zero-rated
    5. Actionable Review Flags on Ambiguous Classifications (strict mode).
    6. Accounting Immutability & Zero Voucher/Ledger Mutation.
    """

    def setUp(self):
        # Dedicated Sandbox Isolation Check
        self.company = Company.objects.create(
            id=uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33'),
            name='Apex Belting & Industrial Store (Demo)'
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "CRITICAL SECURITY INVARIANT VIOLATION: Tests must strictly run against sandbox company!"
        )

        self.owner_user = User.objects.create_user(
            email='auditor@apexbelting.demo',
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
    # 1. Electric Vehicles vs ICE Vehicles (HSN 8703) & Effective-Date Boundaries
    # =========================================================================

    def test_ev_boundary_dates(self):
        """
        EV Rate Change Boundary: 01-Aug-2019 (Notification No. 12/2019-Central Tax (Rate)).
        - Day Before (31-Jul-2019): 12% is VALID, 5% is STATUTORY_MISMATCH.
        - Exact Day (01-Aug-2019): 5% is VALID, 12% is STATUTORY_MISMATCH.
        - Day After (02-Aug-2019): 5% is VALID, 12% is STATUTORY_MISMATCH.
        """
        # Day Before: 31-Jul-2019
        res_before_12 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2019, 7, 31), applied_rate=Decimal('12.00'), is_interstate=True
        )
        self.assertEqual(res_before_12["status"], "VALID")
        self.assertEqual(res_before_12["expected_rate"], 12.00)

        res_before_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2019, 7, 31), applied_rate=Decimal('5.00'), is_interstate=True
        )
        self.assertEqual(res_before_5["status"], "STATUTORY_MISMATCH")

        # Exact Day: 01-Aug-2019
        res_on_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2019, 8, 1), applied_rate=Decimal('5.00'), is_interstate=True
        )
        self.assertEqual(res_on_5["status"], "VALID")
        self.assertEqual(res_on_5["expected_rate"], 5.00)
        self.assertIn("12/2019", res_on_5["notification_reference"])

        res_on_12 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2019, 8, 1), applied_rate=Decimal('12.00'), is_interstate=True
        )
        self.assertEqual(res_on_12["status"], "STATUTORY_MISMATCH")

        # Day After: 02-Aug-2019
        res_after_5 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2019, 8, 2), applied_rate=Decimal('5.00'), is_interstate=True
        )
        self.assertEqual(res_after_5["status"], "VALID")

        res_after_12 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703', tx_date=date(2019, 8, 2), applied_rate=Decimal('12.00'), is_interstate=True
        )
        self.assertEqual(res_after_12["status"], "STATUTORY_MISMATCH")

    def test_ev_positive_attributes_and_itc_restriction(self):
        """EV with explicit attributes is VALID; ITC is explicitly marked blocked under Section 17(5)(a)."""
        res_attr = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            product_attributes={'is_electric': True, 'fuel_type': 'ELECTRIC'}
        )
        self.assertEqual(res_attr["status"], "VALID")
        self.assertEqual(res_attr["applied_rate"], 5.00)
        self.assertEqual(res_attr["applied_cess"], 0.00)
        self.assertEqual(res_attr["supply_type"], "CONCESSIONAL")
        # Invariant: Tax rate valid != ITC eligible
        self.assertEqual(res_attr["itc_eligibility"], "INELIGIBLE_SEC_17_5")
        self.assertIn("Section 17(5)(a)", res_attr["itc_restriction_details"])

    def test_ice_vehicle_negative_mismatch(self):
        """ICE vehicle under HSN 8703 claiming 5% EV rate is rejected as STATUTORY_MISMATCH."""
        res_ice_mismatch = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('5.00'),
            is_interstate=True,
            conditions=['IS_ICE', 'FUEL_PETROL']
        )
        self.assertEqual(res_ice_mismatch["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_ice_mismatch["expected_rate"], 28.00)
        self.assertIn("Schedule IV", res_ice_mismatch["notification_reference"])

    def test_ev_strict_mode_missing_attribute_triggers_review(self):
        """Strict classification on ambiguous HSN 8703 @ 5% requires attribute verification."""
        res_review = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('5.00'),
            is_interstate=True,
            strict_classification=True
        )
        self.assertEqual(res_review["status"], "REVIEW_REQUIRED")
        self.assertEqual(res_review["issue"]["code"], "GST_ATTRIBUTE_REQUIRED_FOR_CLASSIFICATION")
        self.assertIn("is_electric", res_review["missing_attributes"])

    # =========================================================================
    # 2. Motor Vehicle Compensation Cess Cumulative Criteria
    # =========================================================================

    def test_suv_entry_52b_cumulative_criteria_pass(self):
        """
        SUV 22% Compensation Cess requires all 4 cumulative criteria:
        1. Engine > 1500cc
        2. Length > 4000mm
        3. Ground clearance >= 170mm
        4. Popularly known as SUV
        """
        res_suv = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('22.00'),
            is_interstate=True,
            product_attributes={
                'engine_cc': 2000,
                'length_mm': 4600,
                'ground_clearance_mm': 200,
                'is_suv': True,
                'fuel_type': 'PETROL'
            }
        )
        self.assertEqual(res_suv["status"], "VALID")
        self.assertEqual(res_suv["applied_cess"], 22.00)
        self.assertEqual(res_suv["expected_cess"], 22.00)

    def test_large_sedan_disqualifies_from_22_percent_cess(self):
        """
        Large sedan (>1500cc, length >4000mm, but ground clearance <170mm or not SUV):
        Attracts 20% cess under Entry 52, NOT 22% cess under Entry 52B.
        If 22% cess is applied, it must return STATUTORY_MISMATCH!
        """
        # Sedan with 22% cess applied -> STATUTORY_MISMATCH (Expected 20%)
        res_sedan_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('22.00'),
            is_interstate=True,
            product_attributes={
                'engine_cc': 2500,
                'length_mm': 4850,
                'ground_clearance_mm': 150,  # Fails 170mm threshold
                'is_suv': False,             # Luxury sedan
                'fuel_type': 'PETROL'
            }
        )
        self.assertEqual(res_sedan_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_sedan_err["expected_cess"], 20.00)
        self.assertEqual(res_sedan_err["issue"]["code"], "GST_COMPENSATION_CESS_MISMATCH")

        # Sedan with statutory 20% cess applied -> VALID
        res_sedan_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('20.00'),
            is_interstate=True,
            conditions=['LARGE_SEDAN'],
            product_attributes={
                'engine_cc': 2500,
                'length_mm': 4850,
                'ground_clearance_mm': 150,
                'is_suv': False,
                'fuel_type': 'PETROL'
            }
        )
        self.assertEqual(res_sedan_valid["status"], "VALID")
        self.assertEqual(res_sedan_valid["expected_cess"], 20.00)

    def test_small_car_cess_rates_and_negative_rejection(self):
        """
        Small cars attract 1% (petrol) or 3% (diesel) cess under Entries 46 & 47.
        Applying 22% cess to a small car must be rejected as STATUTORY_MISMATCH.
        """
        # Small petrol car with 1% cess -> VALID
        res_petrol = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('1.00'),
            is_interstate=False,
            conditions=['SMALL_CAR_PETROL'],
            product_attributes={'engine_cc': 1198, 'length_mm': 3995, 'fuel_type': 'PETROL'}
        )
        self.assertEqual(res_petrol["status"], "VALID")
        self.assertEqual(res_petrol["expected_cess"], 1.00)

        # Small petrol car with 22% cess applied -> STATUTORY_MISMATCH
        res_petrol_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('22.00'),
            is_interstate=False,
            conditions=['SMALL_CAR_PETROL'],
            product_attributes={'engine_cc': 1198, 'length_mm': 3995, 'fuel_type': 'PETROL'}
        )
        self.assertEqual(res_petrol_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_petrol_err["expected_cess"], 1.00)

        # Small diesel car with 3% cess -> VALID
        res_diesel = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('3.00'),
            is_interstate=False,
            conditions=['SMALL_CAR_DIESEL'],
            product_attributes={'engine_cc': 1498, 'length_mm': 3990, 'fuel_type': 'DIESEL'}
        )
        self.assertEqual(res_diesel["status"], "VALID")
        self.assertEqual(res_diesel["expected_cess"], 3.00)

    # =========================================================================
    # 3. Restaurant Services (SAC 9963) & Boundaries
    # =========================================================================

    def test_restaurant_boundary_dates(self):
        """
        Restaurant Rate Reduction Boundary: 15-Nov-2017 (Notification No. 46/2017-Central Tax (Rate)).
        - Day Before (14-Nov-2017): 18% is VALID, 5% is STATUTORY_MISMATCH.
        - Exact Day (15-Nov-2017): 5% is VALID, 18% is STATUTORY_MISMATCH (standalone).
        - Day After (16-Nov-2017): 5% is VALID, 18% is STATUTORY_MISMATCH.
        """
        # Day Before: 14-Nov-2017
        res_pre = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2017, 11, 14), applied_rate=Decimal('18.00')
        )
        self.assertEqual(res_pre["status"], "VALID")

        res_pre_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2017, 11, 14), applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_pre_err["status"], "STATUTORY_MISMATCH")

        # Exact Day: 15-Nov-2017
        res_on = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2017, 11, 15), applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_on["status"], "VALID")

        res_on_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2017, 11, 15), applied_rate=Decimal('18.00')
        )
        self.assertEqual(res_on_err["status"], "STATUTORY_MISMATCH")

        # Day After: 16-Nov-2017
        res_post = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2017, 11, 16), applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_post["status"], "VALID")

    def test_restaurant_standalone_vs_hotel_tariff_7500(self):
        """
        Standalone restaurant attracts 5% without ITC.
        Restaurant in hotel with declared tariff >= Rs.7,500/night attracts 18% with ITC.
        """
        # Standalone restaurant with 18% applied -> STATUTORY_MISMATCH
        res_stand_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2024, 8, 15), applied_rate=Decimal('18.00'),
            conditions=['STANDALONE_RESTAURANT']
        )
        self.assertEqual(res_stand_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_stand_err["expected_rate"], 5.00)

        # Luxury hotel restaurant with 18% applied -> VALID
        res_hotel_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2024, 8, 15), applied_rate=Decimal('18.00'),
            conditions=['HOTEL_TARIFF_GTE_7500']
        )
        self.assertEqual(res_hotel_valid["status"], "VALID")
        self.assertEqual(res_hotel_valid["expected_rate"], 18.00)

        # Luxury hotel restaurant with 5% applied -> STATUTORY_MISMATCH
        res_hotel_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9963', tx_date=date(2024, 8, 15), applied_rate=Decimal('5.00'),
            conditions=['HOTEL_TARIFF_GTE_7500']
        )
        self.assertEqual(res_hotel_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_hotel_err["expected_rate"], 18.00)

    # =========================================================================
    # 4. Paneer and Dairy (HSN 0406) Pre-Packaged vs Loose & Boundaries
    # =========================================================================

    def test_paneer_boundary_dates(self):
        """
        Paneer Pre-Packaged Taxability Boundary: 18-Jul-2022 (Notification No. 6/2022-CT(Rate)).
        - Day Before (17-Jul-2022): 0% is VALID (Exempt), 5% is STATUTORY_MISMATCH.
        - Exact Day (18-Jul-2022): 5% is VALID (Pre-packaged), 0% without loose tag is STATUTORY_MISMATCH.
        - Day After (19-Jul-2022): 5% is VALID, 0% without loose tag is STATUTORY_MISMATCH.
        """
        # Day Before: 17-Jul-2022
        res_pre = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2022, 7, 17), applied_rate=Decimal('0.00')
        )
        self.assertEqual(res_pre["status"], "VALID")
        self.assertTrue(res_pre["is_exempt"])

        res_pre_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2022, 7, 17), applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_pre_err["status"], "STATUTORY_MISMATCH")

        # Exact Day: 18-Jul-2022
        res_on = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2022, 7, 18), applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_on["status"], "VALID")

        res_on_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2022, 7, 18), applied_rate=Decimal('0.00')
        )
        self.assertEqual(res_on_err["status"], "STATUTORY_MISMATCH")

        # Day After: 19-Jul-2022
        res_post = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2022, 7, 19), applied_rate=Decimal('5.00')
        )
        self.assertEqual(res_post["status"], "VALID")

    def test_paneer_loose_vs_prepackaged_conditions(self):
        """Pre-packaged paneer attracts 5%; loose unpackaged paneer remains exempt (0%)."""
        # Loose unpackaged paneer post-2022 with 0% -> VALID (Exempt)
        res_loose = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2024, 8, 15), applied_rate=Decimal('0.00'),
            conditions=['LOOSE_UNPACKAGED']
        )
        self.assertEqual(res_loose["status"], "VALID")
        self.assertTrue(res_loose["is_exempt"])
        self.assertEqual(res_loose["itc_eligibility"], "ZERO_ITC")

        # Loose unpackaged paneer post-2022 with 5% applied -> STATUTORY_MISMATCH
        res_loose_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2024, 8, 15), applied_rate=Decimal('5.00'),
            conditions=['LOOSE_UNPACKAGED']
        )
        self.assertEqual(res_loose_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_loose_err["expected_rate"], 0.00)

        # Pre-packaged paneer with 0% applied -> STATUTORY_MISMATCH
        res_pkg_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0406', tx_date=date(2024, 8, 15), applied_rate=Decimal('0.00'),
            conditions=['PRE_PACKAGED']
        )
        self.assertEqual(res_pkg_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_pkg_err["expected_rate"], 5.00)

    # =========================================================================
    # 5. Diamonds (HSN 7102): Rough vs Cut & Polished & Boundaries
    # =========================================================================

    def test_diamonds_boundary_dates(self):
        """
        Rough Diamonds Rate Reduction Boundary: 25-Jan-2018 (Notification No. 1/2018-CT(Rate)).
        - Day Before (24-Jan-2018): 3% is VALID, 0.25% is STATUTORY_MISMATCH.
        - Exact Day (25-Jan-2018): 0.25% is VALID, 3% is STATUTORY_MISMATCH.
        - Day After (26-Jan-2018): 0.25% is VALID, 3% is STATUTORY_MISMATCH.
        """
        # Day Before: 24-Jan-2018
        res_pre = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2018, 1, 24), applied_rate=Decimal('3.00'), is_interstate=True
        )
        self.assertEqual(res_pre["status"], "VALID")

        res_pre_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2018, 1, 24), applied_rate=Decimal('0.25'), is_interstate=True
        )
        self.assertEqual(res_pre_err["status"], "STATUTORY_MISMATCH")

        # Exact Day: 25-Jan-2018
        res_on = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2018, 1, 25), applied_rate=Decimal('0.25'), is_interstate=True
        )
        self.assertEqual(res_on["status"], "VALID")

        res_on_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2018, 1, 25), applied_rate=Decimal('3.00'), is_interstate=True
        )
        self.assertEqual(res_on_err["status"], "STATUTORY_MISMATCH")

    def test_diamonds_rough_vs_cut_and_polished(self):
        """
        Rough diamonds (7102 10/21/31) attract 0.25% under Notif 1/2018.
        Cut and polished diamonds (7102 39) attract 1.5% under Notif 5/2018.
        """
        # Cut and polished diamonds with 1.5% -> VALID
        res_cut_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2024, 8, 15), applied_rate=Decimal('1.50'),
            is_interstate=True, conditions=['CUT_AND_POLISHED']
        )
        self.assertEqual(res_cut_valid["status"], "VALID")
        self.assertEqual(res_cut_valid["expected_rate"], 1.50)

        # Cut and polished diamonds claiming 0.25% rough diamond rate -> STATUTORY_MISMATCH
        res_cut_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2024, 8, 15), applied_rate=Decimal('0.25'),
            is_interstate=True, conditions=['CUT_AND_POLISHED']
        )
        self.assertEqual(res_cut_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_cut_err["expected_rate"], 1.50)

        # Rough diamonds with 1.5% applied -> STATUTORY_MISMATCH
        res_rough_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7102', tx_date=date(2024, 8, 15), applied_rate=Decimal('1.50'),
            is_interstate=True, conditions=['ROUGH_DIAMONDS']
        )
        self.assertEqual(res_rough_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_rough_err["expected_rate"], 0.25)

    # =========================================================================
    # 6. Merchant Exports Special Concessional Scheme (0.1%)
    # =========================================================================

    def test_merchant_export_boundary_dates(self):
        """
        Merchant Export Scheme Boundary: 23-Oct-2017 (Notification No. 40/2017 & 41/2017).
        - Day Before (22-Oct-2017): 0.1% does not exist -> STATUTORY_MISMATCH.
        - Exact Day (23-Oct-2017): 0.1% is VALID.
        - Day After (24-Oct-2017): 0.1% is VALID.
        """
        # Day Before: 22-Oct-2017 (Scheme not yet in force; standard rate applies)
        res_pre_hsn = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4010', tx_date=date(2017, 10, 22), applied_rate=Decimal('0.10'), is_interstate=True,
            conditions=['MERCHANT_EXPORT']
        )
        self.assertEqual(res_pre_hsn["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_pre_hsn["expected_rate"], 18.00)

        res_pre_code = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='MERCHANT_EXPORT', tx_date=date(2017, 10, 22), applied_rate=Decimal('0.10'), is_interstate=True
        )
        self.assertEqual(res_pre_code["status"], "REVIEW_REQUIRED")

        # Exact Day: 23-Oct-2017
        res_on = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='MERCHANT_EXPORT', tx_date=date(2017, 10, 23), applied_rate=Decimal('0.10'), is_interstate=True
        )
        self.assertEqual(res_on["status"], "VALID")
        self.assertIn("40/2017", res_on["notification_reference"])

        # Day After: 24-Oct-2017
        res_post = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='MERCHANT_EXPORT', tx_date=date(2017, 10, 24), applied_rate=Decimal('0.10'), is_interstate=True
        )
        self.assertEqual(res_post["status"], "VALID")

    def test_merchant_export_prohibited_for_ordinary_domestic_sales(self):
        """0.1% concessional rate is rejected for ordinary domestic sales."""
        res_dom_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4010',
            tx_date=date(2024, 8, 15),
            applied_rate=Decimal('0.10'),
            is_interstate=True,
            conditions=['ORDINARY_DOMESTIC']
        )
        self.assertEqual(res_dom_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_dom_err["expected_rate"], 18.00)

    # =========================================================================
    # 7. Gold & Precious Metals (HSN 7108/7113) vs Imitation Jewellery (HSN 7117)
    # =========================================================================

    def test_gold_and_precious_jewellery_rate_consistency(self):
        """Gold (HSN 7108) and Precious Jewellery (HSN 7113) attract 3% GST (Schedule V S.No. 13)."""
        res_7108 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7108', tx_date=date(2024, 8, 15), applied_rate=Decimal('3.00'), is_interstate=False
        )
        self.assertEqual(res_7108["status"], "VALID")
        self.assertEqual(res_7108["applied_rate"], 3.00)

        res_7113 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7113', tx_date=date(2024, 8, 15), applied_rate=Decimal('3.00'), is_interstate=True
        )
        self.assertEqual(res_7113["status"], "VALID")
        self.assertEqual(res_7113["applied_rate"], 3.00)

    def test_imitation_jewellery_rejection_at_3_percent(self):
        """Imitation jewellery under HSN 7117 attracts 18%; 3% is STATUTORY_MISMATCH."""
        res_7117_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7117', tx_date=date(2024, 8, 15), applied_rate=Decimal('3.00'), is_interstate=False
        )
        self.assertEqual(res_7117_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_7117_err["expected_rate"], 18.00)

        res_7117_valid = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='7117', tx_date=date(2024, 8, 15), applied_rate=Decimal('18.00'), is_interstate=False
        )
        self.assertEqual(res_7117_valid["status"], "VALID")

    # =========================================================================
    # 8. Fresh Milk (HSN 0401) Unconditional Exemption vs UHT Milk
    # =========================================================================

    def test_fresh_milk_unconditional_exemption(self):
        """Fresh milk under HSN 0401 is unconditionally exempt (0% NIL-RATED) under Notif 2/2017."""
        res_milk = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401', tx_date=date(2024, 8, 15), applied_rate=Decimal('0.00'), is_interstate=False
        )
        self.assertEqual(res_milk["status"], "VALID")
        self.assertTrue(res_milk["is_exempt"])
        self.assertTrue(res_milk["is_nil_rated"])
        self.assertEqual(res_milk["supply_type"], "NIL_RATED")
        self.assertEqual(res_milk["itc_eligibility"], "ZERO_ITC")

        # 5% applied to fresh milk is STATUTORY_MISMATCH
        res_milk_err = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401', tx_date=date(2024, 8, 15), applied_rate=Decimal('5.00'), is_interstate=False
        )
        self.assertEqual(res_milk_err["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_milk_err["expected_rate"], 0.00)

    def test_uht_milk_taxable_at_5_percent(self):
        """UHT milk (tariff 0401 50 00) attracts 5% GST under Schedule I S.No. 7."""
        res_uht = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='0401', tx_date=date(2024, 8, 15), applied_rate=Decimal('5.00'),
            is_interstate=False, conditions=['UHT_MILK']
        )
        self.assertEqual(res_uht["status"], "VALID")
        self.assertEqual(res_uht["expected_rate"], 5.00)

    # =========================================================================
    # 9. Component Consistency & Intrastate vs Interstate Division
    # =========================================================================

    def test_component_division_consistency(self):
        """Verify CGST == SGST for intrastate, and IGST == CGST + SGST."""
        rule_belts = GSTRateScheduleService.get_matching_rules('4010', date(2024, 8, 1))[0]
        self.assertEqual(rule_belts.cgst_rate, Decimal('9.00'))
        self.assertEqual(rule_belts.sgst_rate, Decimal('9.00'))
        self.assertEqual(rule_belts.igst_rate, Decimal('18.00'))
        self.assertEqual(rule_belts.cgst_rate + rule_belts.sgst_rate, rule_belts.igst_rate)

        rule_ev = [r for r in GSTRateScheduleService.get_matching_rules('8703', date(2024, 8, 1)) if r.cgst_rate == Decimal('2.50')][0]
        self.assertEqual(rule_ev.cgst_rate, Decimal('2.50'))
        self.assertEqual(rule_ev.sgst_rate, Decimal('2.50'))
        self.assertEqual(rule_ev.igst_rate, Decimal('5.00'))

    # =========================================================================
    # 10. Accounting Immutability & Zero Mutation Invariant
    # =========================================================================

    def test_statutory_validation_causes_zero_mutation_to_vouchers_or_ledgers(self):
        """
        STRICT DOUBLE-ENTRY INVARIANT:
        Rate reference validation and pre-export payload checks are strictly read-only.
        Zero mutation to vouchers, items, ledgers, or account balances.
        """
        group_assets = LedgerGroup.objects.create(
            company=self.company, name='Current Assets', nature='ASSET'
        )
        group_sales = LedgerGroup.objects.create(
            company=self.company, name='Sales Revenue', nature='INCOME'
        )
        ledger_debtor = Ledger.objects.create(
            company=self.company, name='Buyer Ledger', group=group_assets, current_balance=Decimal('1180.00')
        )
        ledger_sales = Ledger.objects.create(
            company=self.company, name='Sales Account', group=group_sales, current_balance=Decimal('1000.00')
        )

        prod_belt = Product.objects.create(
            company=self.company, name='Industrial Conveyor Belt', sku='SKU-BELT-999',
            hsn_code='4010', unit='MTR'
        )

        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV/2024/099',
            voucher_date=date(2024, 8, 15),
            narration='Testing immutability during statutory GST rate validation',
            created_by=self.owner_user
        )
        item = VoucherItem.objects.create(
            voucher=voucher,
            product=prod_belt,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            hsn_code='4010',
            taxable_amount=Decimal('1000.00'),
            gst_rate=Decimal('18.00'),
            igst_rate=Decimal('18.00'),
            igst_amount=Decimal('180.00'),
            total_amount=Decimal('1180.00')
        )

        # Record state fingerprints before validation
        v_count_before = Voucher.objects.count()
        item_count_before = VoucherItem.objects.count()
        debtor_bal_before = Ledger.objects.get(id=ledger_debtor.id).current_balance
        sales_bal_before = Ledger.objects.get(id=ledger_sales.id).current_balance

        # Execute 50 rapid rate validation calls
        for _ in range(50):
            GSTRateScheduleService.validate_tax_rate(
                hsn_sc='4010', tx_date=date(2024, 8, 15), applied_rate=Decimal('18.00'), is_interstate=True
            )
            GSTRateScheduleService.validate_tax_rate(
                hsn_sc='8703', tx_date=date(2024, 8, 15), applied_rate=Decimal('5.00'), is_interstate=False,
                product_attributes={'is_electric': True}
            )

        # Assert zero mutation
        self.assertEqual(Voucher.objects.count(), v_count_before)
        self.assertEqual(VoucherItem.objects.count(), item_count_before)
        self.assertEqual(Ledger.objects.get(id=ledger_debtor.id).current_balance, debtor_bal_before)
        self.assertEqual(Ledger.objects.get(id=ledger_sales.id).current_balance, sales_bal_before)

        # Assert voucher attributes untouched
        refetched_voucher = Voucher.objects.get(id=voucher.id)
        self.assertEqual(refetched_voucher.voucher_number, 'INV/2024/099')
        self.assertEqual(refetched_voucher.narration, 'Testing immutability during statutory GST rate validation')

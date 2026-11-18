import logging
from decimal import Decimal
from datetime import date
from typing import Dict, Any, List, Optional, Tuple, NamedTuple, Set, Union, Iterable

logger = logging.getLogger('apps.gst.rate_reference')


class GSTRateRule(NamedTuple):
    hsn_sc: str
    tariff_item: Optional[str]
    description: str
    item_type: str  # 'GOODS' or 'SERVICES'
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    cess_rate: Decimal
    effective_from: date
    effective_to: Optional[date]
    notification_ref: str
    required_conditions: Tuple[str, ...]
    excluded_conditions: Tuple[str, ...]
    supply_type: str  # 'TAXABLE', 'EXEMPT', 'NIL_RATED', 'ZERO_RATED', 'CONCESSIONAL'
    is_exempt: bool
    is_nil_rated: bool
    is_rcm: bool
    itc_eligibility: str  # 'ELIGIBLE', 'INELIGIBLE_SEC_17_5', 'CONDITIONAL_NO_ITC', 'ZERO_ITC'
    itc_restriction_details: Optional[str]


class GSTRateScheduleService:
    """
    Authoritative Effective-Dated Statutory GST Rate Reference & Rule Hardening Engine (Round 2.2.2).
    Maintains CBIC statutory rate schedules, classification criteria, compensation cess entries,
    and ITC statutory restrictions across Indian Goods and Services Tax law.

    Statutory Authorities & Notifications:
    - Notification No. 1/2017-Central Tax (Rate) dated 28-06-2017 (Goods standard rate schedule)
    - Notification No. 2/2017-Central Tax (Rate) dated 28-06-2017 (Goods unconditional/conditional exemptions)
    - Notification No. 11/2017-Central Tax (Rate) dated 28-06-2017 (Services rate schedule)
    - Notification No. 12/2017-Central Tax (Rate) dated 28-06-2017 (Services exemptions)
    - Notification No. 46/2017-Central Tax (Rate) dated 14-11-2017 (Restaurant services rate reduction to 5% without ITC)
    - Notification No. 1/2018-Central Tax (Rate) dated 25-01-2018 (Rough diamonds reduced to 0.25%)
    - Notification No. 5/2018-Central Tax (Rate) dated 25-01-2018 (Cut & polished diamonds at 1.5%)
    - Notification No. 12/2019-Central Tax (Rate) dated 31-07-2019 (Electric vehicles reduced to 5%)
    - Notification No. 6/2022-Central Tax (Rate) dated 13-07-2022 (Pre-packaged and labelled foods to 5%)
    - Notification No. 7/2022-Central Tax (Rate) dated 13-07-2022 (Exemption restriction to unpackaged/loose foods)
    - Notification No. 40/2017-Central Tax (Rate) & 41/2017-Integrated Tax (Rate) (Merchant exports 0.1% concessional)
    - Notification No. 1/2017-Compensation Cess (Rate) as amended by Notif 3/2023-Compensation Cess (Rate) (Motor vehicles cess)
    - Section 17(5) Central Goods and Services Tax Act, 2017 (Statutory blocked ITC credits)

    INVARIANT: STRICTLY READ-ONLY / PURE CALCULATION.
    Never mutates historical vouchers, ledgers, inventory stock, or accounting books.
    """

    # Comprehensive Effective-Dated Statutory Rate Rules
    STATUTORY_RULES: List[GSTRateRule] = [
        # =========================================================================
        # 1. Industrial Belts & Rubber Products (HSN 4010)
        # =========================================================================
        GSTRateRule(
            hsn_sc='4010',
            tariff_item='4010',
            description='Conveyor or transmission belts or belting, of vulcanised rubber',
            item_type='GOODS',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule III, S.No. 110',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 2. Industrial Machinery & Valves (HSN 8481)
        # =========================================================================
        GSTRateRule(
            hsn_sc='8481',
            tariff_item='8481',
            description='Taps, cocks, valves and similar appliances for pipes, boiler shells, tanks',
            item_type='GOODS',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule III, S.No. 360',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 3. Belt Installation, Splicing & Maintenance Services (SAC 9954 / 9987)
        # =========================================================================
        GSTRateRule(
            hsn_sc='9954',
            tariff_item='9954',
            description='General construction and installation services of industrial equipment',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 3',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),
        GSTRateRule(
            hsn_sc='9987',
            tariff_item='9987',
            description='Maintenance, repair and installation services of fabricated metal and machinery',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 25',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 4. Goods Transport Agency (GTA) Services (SAC 9965)
        # =========================================================================
        # 5% RCM (without ITC)
        GSTRateRule(
            hsn_sc='9965',
            tariff_item='9965',
            description='Goods transport agency (GTA) services under reverse charge (without ITC)',
            item_type='SERVICES',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 9(iii) & 13/2017-CT(Rate)',
            required_conditions=('RCM',),
            excluded_conditions=('FORWARD_CHARGE',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=True,
            itc_eligibility='CONDITIONAL_NO_ITC',
            itc_restriction_details='Supplier not entitled to ITC; recipient pays under RCM and claims ITC if eligible'
        ),
        # 12% Forward Charge (with ITC)
        GSTRateRule(
            hsn_sc='9965',
            tariff_item='9965',
            description='Goods transport agency (GTA) services under forward charge (with ITC option)',
            item_type='SERVICES',
            cgst_rate=Decimal('6.00'),
            sgst_rate=Decimal('6.00'),
            igst_rate=Decimal('12.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 9(iii)',
            required_conditions=('FORWARD_CHARGE',),
            excluded_conditions=('RCM',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 5. Restaurant Services (SAC 9963) — Effective-Dated & Condition-Aware
        # =========================================================================
        # Historical: 01-Jul-2017 to 14-Nov-2017 (18% with ITC for air-conditioned)
        GSTRateRule(
            hsn_sc='9963',
            tariff_item='996331',
            description='Restaurant services (air-conditioned premises) with input tax credit',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2017, 11, 14),
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 7(i)',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),
        # Current: 15-Nov-2017 onwards — Standalone Restaurants (5% without ITC)
        GSTRateRule(
            hsn_sc='9963',
            tariff_item='996331',
            description='Restaurant services (standalone) without input tax credit',
            item_type='SERVICES',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 11, 15),
            effective_to=None,
            notification_ref='Notification No. 46/2017-Central Tax (Rate) amending 11/2017-CT(Rate)',
            required_conditions=(),
            excluded_conditions=('HOTEL_TARIFF_GTE_7500',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Supplier cannot take ITC (Notif 46/2017); Recipient blocked under Section 17(5)(b)(i)'
        ),
        # Current: 15-Nov-2017 onwards — Restaurants in Specified Premises (Hotel declared tariff >= Rs.7500/night)
        GSTRateRule(
            hsn_sc='9963',
            tariff_item='996332',
            description='Restaurant services located in specified hotel premises with declared tariff >= Rs. 7,500/night',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 11, 15),
            effective_to=None,
            notification_ref='Notification No. 11/2017-CT(Rate) S.No. 7(vi) as amended by Notif 20/2019-CT(Rate)',
            required_conditions=('HOTEL_TARIFF_GTE_7500',),
            excluded_conditions=('STANDALONE_RESTAURANT',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details='Eligible for supplier; recipient blocked under Section 17(5)(b)(i) unless outward supply category'
        ),

        # =========================================================================
        # 6. Motor Vehicles (HSN 8703) — Electric Vehicles vs ICE Vehicles
        # =========================================================================
        # EV Historical: 01-Jul-2017 to 31-Jul-2019 (12%)
        GSTRateRule(
            hsn_sc='8703',
            tariff_item='870380',
            description='Electrically operated vehicles (EVs) for transport of persons',
            item_type='GOODS',
            cgst_rate=Decimal('6.00'),
            sgst_rate=Decimal('6.00'),
            igst_rate=Decimal('12.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2019, 7, 31),
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule II, S.No. 206',
            required_conditions=(),
            excluded_conditions=('IS_ICE', 'FUEL_PETROL', 'FUEL_DIESEL'),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)'
        ),
        # EV Current: 01-Aug-2019 onwards (5%)
        GSTRateRule(
            hsn_sc='8703',
            tariff_item='870380',
            description='Electrically operated vehicles (EVs) including two and three wheelers',
            item_type='GOODS',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2019, 8, 1),
            effective_to=None,
            notification_ref='Notification No. 12/2019-Central Tax (Rate) amending 1/2017-CT(Rate)',
            required_conditions=(),
            excluded_conditions=('IS_ICE', 'FUEL_PETROL', 'FUEL_DIESEL'),
            supply_type='CONCESSIONAL',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)'
        ),

        # ICE Standard: 01-Jul-2017 onwards (28% GST + Cess per specification)
        # 11A. Qualifying SUV (28% GST + 22% Compensation Cess)
        GSTRateRule(
            hsn_sc='8703',
            tariff_item='8703',
            description='Sports Utility Vehicles (SUVs) meeting all 4 cumulative criteria: engine > 1500cc, length > 4000mm, ground clearance >= 170mm, and popularly known as SUV',
            item_type='GOODS',
            cgst_rate=Decimal('14.00'),
            sgst_rate=Decimal('14.00'),
            igst_rate=Decimal('28.00'),
            cess_rate=Decimal('22.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-CT(Rate) & Notif 1/2017-Compensation Cess(Rate)',
            required_conditions=(),
            excluded_conditions=('IS_ELECTRIC',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)'
        ),
        # 11B. Large Motor Vehicles / Sedans > 1500cc other than SUVs (28% GST + 20% Compensation Cess)
        GSTRateRule(
            hsn_sc='8703',
            tariff_item='8703',
            description='Motor vehicles with engine capacity > 1500cc other than SUVs (e.g. sedans, luxury saloons)',
            item_type='GOODS',
            cgst_rate=Decimal('14.00'),
            sgst_rate=Decimal('14.00'),
            igst_rate=Decimal('28.00'),
            cess_rate=Decimal('20.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notif 1/2017-CT(Rate) Sched IV S.No. 188 & Notif 1/2017-Compensation Cess(Rate) Entry 52',
            required_conditions=('LARGE_SEDAN',),
            excluded_conditions=('IS_ELECTRIC', 'IS_SUV_QUALIFIED_52B'),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)'
        ),
        # 11C. Small Petrol Cars (<=1200cc, length <= 4000mm) (28% GST + 1% Compensation Cess)
        GSTRateRule(
            hsn_sc='8703',
            tariff_item='8703',
            description='Small motor vehicles (petrol/LPG/CNG), engine <= 1200cc and length <= 4000mm',
            item_type='GOODS',
            cgst_rate=Decimal('14.00'),
            sgst_rate=Decimal('14.00'),
            igst_rate=Decimal('28.00'),
            cess_rate=Decimal('1.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notif 1/2017-CT(Rate) Sched IV S.No. 188 & Notif 1/2017-Compensation Cess(Rate) Entry 46',
            required_conditions=('SMALL_CAR_PETROL',),
            excluded_conditions=('IS_ELECTRIC',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)'
        ),
        # 11D. Small Diesel Cars (<=1500cc, length <= 4000mm) (28% GST + 3% Compensation Cess)
        GSTRateRule(
            hsn_sc='8703',
            tariff_item='8703',
            description='Small motor vehicles (diesel), engine <= 1500cc and length <= 4000mm',
            item_type='GOODS',
            cgst_rate=Decimal('14.00'),
            sgst_rate=Decimal('14.00'),
            igst_rate=Decimal('28.00'),
            cess_rate=Decimal('3.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notif 1/2017-CT(Rate) Sched IV S.No. 188 & Notif 1/2017-Compensation Cess(Rate) Entry 47',
            required_conditions=('SMALL_CAR_DIESEL',),
            excluded_conditions=('IS_ELECTRIC',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='INELIGIBLE_SEC_17_5',
            itc_restriction_details='Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)'
        ),

        # =========================================================================
        # 7. Gold, Silver & Precious Metals (HSN 7108 & 7113) vs Imitation (HSN 7117)
        # =========================================================================
        GSTRateRule(
            hsn_sc='7108',
            tariff_item='7108',
            description='Gold (including gold plated with platinum) unwrought or in semi-manufactured forms',
            item_type='GOODS',
            cgst_rate=Decimal('1.50'),
            sgst_rate=Decimal('1.50'),
            igst_rate=Decimal('3.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule V, S.No. 13',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),
        GSTRateRule(
            hsn_sc='7113',
            tariff_item='7113',
            description='Articles of jewellery and parts thereof, of precious metal or of metal clad with precious metal',
            item_type='GOODS',
            cgst_rate=Decimal('1.50'),
            sgst_rate=Decimal('1.50'),
            igst_rate=Decimal('3.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule V, S.No. 13',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),
        GSTRateRule(
            hsn_sc='7117',
            tariff_item='7117',
            description='Imitation jewellery',
            item_type='GOODS',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule III, S.No. 223',
            required_conditions=(),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 8. Diamonds (HSN 7102) — Rough Diamonds vs Cut and Polished
        # =========================================================================
        # Rough Diamonds: Historical 01-Jul-2017 to 24-Jan-2018 (3%)
        GSTRateRule(
            hsn_sc='7102',
            tariff_item='71021000',
            description='Rough diamonds, unworked or simply sawn, cleaved or bruted',
            item_type='GOODS',
            cgst_rate=Decimal('1.50'),
            sgst_rate=Decimal('1.50'),
            igst_rate=Decimal('3.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2018, 1, 24),
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule V, S.No. 1',
            required_conditions=(),
            excluded_conditions=('CUT_AND_POLISHED',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),
        # Rough Diamonds: Current 25-Jan-2018 onwards (0.25%)
        GSTRateRule(
            hsn_sc='7102',
            tariff_item='71021000',
            description='Rough diamonds, unworked or simply sawn, cleaved or bruted',
            item_type='GOODS',
            cgst_rate=Decimal('0.125'),
            sgst_rate=Decimal('0.125'),
            igst_rate=Decimal('0.25'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2018, 1, 25),
            effective_to=None,
            notification_ref='Notification No. 1/2018-Central Tax (Rate), Schedule VI, S.No. 1',
            required_conditions=(),
            excluded_conditions=('CUT_AND_POLISHED',),
            supply_type='CONCESSIONAL',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),
        # Cut and Polished Diamonds: Current 25-Jan-2018 onwards (1.5%)
        GSTRateRule(
            hsn_sc='7102',
            tariff_item='710239',
            description='Diamonds, cut and polished (other than rough diamonds)',
            item_type='GOODS',
            cgst_rate=Decimal('0.75'),
            sgst_rate=Decimal('0.75'),
            igst_rate=Decimal('1.50'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2018, 1, 25),
            effective_to=None,
            notification_ref='Notification No. 5/2018-Central Tax (Rate), Schedule VII, S.No. 1',
            required_conditions=('CUT_AND_POLISHED',),
            excluded_conditions=('ROUGH_DIAMONDS',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 9. Dairy / Paneer / Cheese (HSN 0406) — Pre-Packaged vs Loose
        # =========================================================================
        # Historical: 01-Jul-2017 to 17-Jul-2022 (Exempt 0% if loose/unbranded)
        GSTRateRule(
            hsn_sc='0406',
            tariff_item='0406',
            description='Cheese and paneer (other than pre-packaged and labelled)',
            item_type='GOODS',
            cgst_rate=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2022, 7, 17),
            notification_ref='Notification No. 2/2017-Central Tax (Rate), S.No. 27',
            required_conditions=(),
            excluded_conditions=('BRANDED_UNIT_CONTAINER', 'PRE_PACKAGED'),
            supply_type='EXEMPT',
            is_exempt=True,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ZERO_ITC',
            itc_restriction_details='Exempt supply under Section 11; no ITC under Section 17(2)'
        ),
        # Current: 18-Jul-2022 onwards — Loose / unpackaged (Exempt 0%)
        GSTRateRule(
            hsn_sc='0406',
            tariff_item='0406',
            description='Chenna or paneer, other than pre-packaged and labelled',
            item_type='GOODS',
            cgst_rate=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2022, 7, 18),
            effective_to=None,
            notification_ref='Notification No. 2/2017-CT(Rate) S.No. 27 as amended by Notif 7/2022-CT(Rate)',
            required_conditions=('LOOSE_UNPACKAGED',),
            excluded_conditions=('PRE_PACKAGED', 'PRE_PACKAGED_AND_LABELLED'),
            supply_type='EXEMPT',
            is_exempt=True,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ZERO_ITC',
            itc_restriction_details='Exempt supply under Section 11; no ITC under Section 17(2)'
        ),
        # Current: 18-Jul-2022 onwards — Pre-Packaged and Labelled (5%)
        GSTRateRule(
            hsn_sc='0406',
            tariff_item='0406',
            description='Paneer and cheese when pre-packaged and labelled',
            item_type='GOODS',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2022, 7, 18),
            effective_to=None,
            notification_ref='Notification No. 6/2022-Central Tax (Rate), Schedule I, S.No. 26',
            required_conditions=(),
            excluded_conditions=('LOOSE_UNPACKAGED',),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 10. Nil-Rated / Unconditionally Exempt Fresh Milk (HSN 0401)
        # =========================================================================
        GSTRateRule(
            hsn_sc='0401',
            tariff_item='0401',
            description='Fresh milk, pasteurised milk, not concentrated nor containing added sugar',
            item_type='GOODS',
            cgst_rate=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 2/2017-Central Tax (Rate), S.No. 25',
            required_conditions=(),
            excluded_conditions=('UHT_MILK',),
            supply_type='NIL_RATED',
            is_exempt=True,
            is_nil_rated=True,
            is_rcm=False,
            itc_eligibility='ZERO_ITC',
            itc_restriction_details='Unconditional statutory exemption; no ITC allowed under Section 17(2)'
        ),
        # UHT Milk (HSN 0401 50 00) — 5% Taxable
        GSTRateRule(
            hsn_sc='0401',
            tariff_item='04015000',
            description='Ultra High Temperature (UHT) milk',
            item_type='GOODS',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule I, S.No. 7',
            required_conditions=('UHT_MILK',),
            excluded_conditions=(),
            supply_type='TAXABLE',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details=None
        ),

        # =========================================================================
        # 12. Merchant Exports Special Concessional Scheme (0.1%)
        # =========================================================================
        GSTRateRule(
            hsn_sc='MERCHANT_EXPORT',
            tariff_item=None,
            description='Supply of goods to merchant exporter for export under bond/LUT',
            item_type='GOODS',
            cgst_rate=Decimal('0.05'),
            sgst_rate=Decimal('0.05'),
            igst_rate=Decimal('0.10'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 10, 23),
            effective_to=None,
            notification_ref='Notification No. 40/2017-Central Tax (Rate) & 41/2017-Integrated Tax (Rate)',
            required_conditions=('MERCHANT_EXPORT',),
            excluded_conditions=('ORDINARY_DOMESTIC',),
            supply_type='CONCESSIONAL',
            is_exempt=False,
            is_nil_rated=False,
            is_rcm=False,
            itc_eligibility='ELIGIBLE',
            itc_restriction_details='Exporter must export goods within 90 days; supplier eligible for refund under inverted duty'
        ),
    ]

    @classmethod
    def evaluate_vehicle_cess_criteria(
        cls,
        attributes: Optional[Dict[str, Any]] = None,
        conditions: Optional[Set[str]] = None
    ) -> Tuple[Decimal, str, str, bool]:
        """
        Evaluates cumulative statutory criteria for motor vehicle compensation cess (HSN 8703)
        under Notification No. 1/2017-Compensation Cess (Rate) as amended by Notif 3/2023.

        Returns:
            (expected_cess_rate, entry_reference, description, satisfies_suv_criteria)
        """
        attrs = attributes or {}
        conds = conditions or set()

        # Check electric vehicle first
        if 'IS_ELECTRIC' in conds or attrs.get('is_electric') is True or attrs.get('fuel_type') == 'ELECTRIC':
            return Decimal('0.00'), 'Exempt from Cess', 'Electrically operated vehicle', False

        engine_cc = attrs.get('engine_cc')
        length_mm = attrs.get('length_mm')
        ground_clearance_mm = attrs.get('ground_clearance_mm')
        is_suv = attrs.get('is_suv')
        fuel_type = str(attrs.get('fuel_type', '')).upper()

        # Check explicit condition tags
        has_engine_gt_1500 = ('ENGINE_CC_GT_1500' in conds) or (engine_cc is not None and engine_cc > 1500)
        has_length_gt_4000 = ('LENGTH_GT_4000' in conds) or (length_mm is not None and length_mm > 4000)
        has_gc_gte_170 = ('GROUND_CLEARANCE_GTE_170' in conds) or (ground_clearance_mm is not None and ground_clearance_mm >= 170)
        has_suv_status = ('IS_SUV' in conds) or (is_suv is True)

        # 1. Cumulative SUV Entry 52B check (22% Cess)
        # ALL 4 conditions must be cumulatively satisfied
        if has_engine_gt_1500 and has_length_gt_4000 and has_gc_gte_170 and has_suv_status:
            return (
                Decimal('22.00'),
                'Entry 52B, Notification No. 1/2017-Compensation Cess (Rate)',
                'Qualifying SUV (Engine >1500cc, Length >4000mm, Ground Clearance >=170mm, and SUV)',
                True
            )

        # 2. Large Cars / Sedans > 1500cc other than SUVs (20% Cess)
        if has_engine_gt_1500 or ('LARGE_SEDAN' in conds):
            return (
                Decimal('20.00'),
                'Entry 52, Notification No. 1/2017-Compensation Cess (Rate)',
                'Motor vehicle with engine > 1500cc other than SUV (e.g. sedan/saloon)',
                False
            )

        # 3. Small Petrol Cars <=1200cc, Length <= 4000mm (1% Cess)
        if ('SMALL_CAR_PETROL' in conds) or (
            (fuel_type in ('PETROL', 'CNG', 'LPG')) and
            (engine_cc is not None and engine_cc <= 1200) and
            (length_mm is not None and length_mm <= 4000)
        ):
            return (
                Decimal('1.00'),
                'Entry 46, Notification No. 1/2017-Compensation Cess (Rate)',
                'Small car (petrol/CNG/LPG), engine <=1200cc, length <=4000mm',
                False
            )

        # 4. Small Diesel Cars <=1500cc, Length <= 4000mm (3% Cess)
        if ('SMALL_CAR_DIESEL' in conds) or (
            (fuel_type == 'DIESEL') and
            (engine_cc is not None and engine_cc <= 1500) and
            (length_mm is not None and length_mm <= 4000)
        ):
            return (
                Decimal('3.00'),
                'Entry 47, Notification No. 1/2017-Compensation Cess (Rate)',
                'Small car (diesel), engine <=1500cc, length <=4000mm',
                False
            )

        # 5. Default fallback for general motor cars under Entry 52B if not specified
        return (
            Decimal('22.00'),
            'Entry 52B (Standard SUV / Luxury motor car schedule)',
            'Standard luxury motor car cess schedule',
            False
        )

    @classmethod
    def get_matching_rules(
        cls,
        hsn_sc: str,
        tx_date: date,
        item_type: Optional[str] = None,
        conditions: Optional[Set[str]] = None,
        tariff_item: Optional[str] = None
    ) -> List[GSTRateRule]:
        """
        Retrieves active statutory rate rules matching HSN/SAC code on transaction date.
        Filters rules based on date bounds, item type, required conditions, and explicit disqualifying conditions.
        """
        clean_hsn = (hsn_sc or '').strip().replace(' ', '')
        cond_set = conditions or set()
        matches: List[GSTRateRule] = []

        for rule in cls.STATUTORY_RULES:
            # Check date applicability
            if tx_date < rule.effective_from:
                continue
            if rule.effective_to and tx_date > rule.effective_to:
                continue

            # Check item type if specified
            if item_type and rule.item_type != item_type:
                continue

            # Check required conditions: if rule specifies required_conditions, ALL must be in cond_set
            if rule.required_conditions:
                if not all(req in cond_set for req in rule.required_conditions):
                    continue

            # Check excluded conditions: if ANY excluded condition is in cond_set, rule is disqualified
            if any(exc in cond_set for exc in rule.excluded_conditions):
                continue

            # Check HSN code match (prefix match: rule hsn matches start of voucher hsn or vice versa)
            if clean_hsn and (clean_hsn.startswith(rule.hsn_sc) or rule.hsn_sc.startswith(clean_hsn)):
                matches.append(rule)
            elif rule.hsn_sc == 'MERCHANT_EXPORT' and ('MERCHANT_EXPORT' in clean_hsn.upper() or 'MERCHANT_EXPORT' in cond_set):
                matches.append(rule)

        return matches

    @classmethod
    def validate_tax_rate(
        cls,
        hsn_sc: str,
        tx_date: date,
        applied_rate: Decimal,
        is_interstate: bool = False,
        applied_cess: Decimal = Decimal('0.00'),
        conditions: Optional[Union[List[str], Set[str], Tuple[str, ...]]] = None,
        product_attributes: Optional[Dict[str, Any]] = None,
        tariff_item: Optional[str] = None,
        strict_classification: bool = False
    ) -> Dict[str, Any]:
        """
        Validates transaction tax rate against effective-dated statutory CBIC schedules.
        Strictly enforces classification criteria, packaging/labelling requirements,
        vehicle engine & dimension criteria for compensation cess, and Section 17(5) ITC restrictions.

        Returns structured compliance audit result:
            {
                "status": "VALID" | "STATUTORY_MISMATCH" | "REVIEW_REQUIRED",
                "is_statutorily_valid": bool,
                "applied_rate": float,
                "expected_rate": Optional[float],
                "applied_cess": float,
                "expected_cess": Optional[float],
                "matched_rules_count": int,
                "notification_reference": Optional[str],
                "description": Optional[str],
                "supply_type": str,
                "is_exempt": bool,
                "is_nil_rated": bool,
                "is_zero_rated": bool,
                "is_rcm": bool,
                "itc_eligibility": str,
                "itc_restriction_details": Optional[str],
                "cess_applicability": str,
                "missing_attributes": List[str],
                "issue": Optional[Dict[str, Any]]
            }
        """
        app_rate = Decimal(str(applied_rate or '0.00')).quantize(Decimal('0.01'))
        app_cess = Decimal(str(applied_cess or '0.00')).quantize(Decimal('0.01'))
        raw_conds = set(conditions or [])
        attrs = dict(product_attributes or {})
        clean_hsn = (hsn_sc or '').strip().replace(' ', '')

        # Normalize attributes into condition tags
        if attrs.get('is_electric') is True or (tariff_item and tariff_item.startswith('870380')):
            raw_conds.add('IS_ELECTRIC')
        if attrs.get('is_electric') is False or attrs.get('fuel_type') in ('PETROL', 'DIESEL', 'CNG', 'HYBRID'):
            raw_conds.add('IS_ICE')
        if attrs.get('is_suv') is True:
            raw_conds.add('IS_SUV')
        if attrs.get('is_prepackaged_and_labelled') is True:
            raw_conds.add('PRE_PACKAGED')
        if attrs.get('is_prepackaged_and_labelled') is False or attrs.get('is_loose') is True:
            raw_conds.add('LOOSE_UNPACKAGED')
        if attrs.get('is_merchant_export') is True or clean_hsn.upper() == 'MERCHANT_EXPORT' or 'MERCHANT_EXPORT' in clean_hsn.upper():
            raw_conds.add('MERCHANT_EXPORT')

        # Evaluate SUV Cess criteria if relevant
        if clean_hsn.startswith('8703') and (app_cess > 0 or attrs):
            exp_cess, cess_ref, cess_desc, is_suv_qual = cls.evaluate_vehicle_cess_criteria(attrs, raw_conds)
            if is_suv_qual:
                raw_conds.add('IS_SUV_QUALIFIED_52B')
                raw_conds.add('ENGINE_CC_GT_1500')
                raw_conds.add('LENGTH_GT_4000')
                raw_conds.add('GROUND_CLEARANCE_GTE_170')
                raw_conds.add('IS_SUV')

        rules = cls.get_matching_rules(
            hsn_sc=clean_hsn,
            tx_date=tx_date,
            conditions=raw_conds,
            tariff_item=tariff_item
        )

        # -------------------------------------------------------------------------
        # Case 1: Unrecognized / Ambiguous HSN (No statutory rule matches)
        # -------------------------------------------------------------------------
        if not rules:
            return {
                "status": "REVIEW_REQUIRED",
                "is_statutorily_valid": True,  # Non-blocking warning flag
                "applied_rate": float(app_rate),
                "expected_rate": None,
                "applied_cess": float(app_cess),
                "expected_cess": None,
                "matched_rules_count": 0,
                "notification_reference": None,
                "description": None,
                "supply_type": "TAXABLE",
                "is_exempt": False,
                "is_nil_rated": False,
                "is_zero_rated": False,
                "is_rcm": False,
                "itc_eligibility": "ELIGIBLE",
                "itc_restriction_details": None,
                "cess_applicability": "NOT_APPLICABLE",
                "missing_attributes": ["hsn_classification"],
                "issue": {
                    "code": "GST_RATE_REVIEW_REQUIRED",
                    "severity": "WARNING",
                    "description": f"HSN/SAC code '{hsn_sc}' has no exact statutory rule match for transaction date {tx_date}. Verification recommended.",
                    "recommendation": "Confirm applicable notification rate in CBIC tariff schedules."
                }
            }

        # -------------------------------------------------------------------------
        # Case 2: Special Condition Enforcements (Negative Checks)
        # -------------------------------------------------------------------------

        # A. Electric Vehicles vs ICE (HSN 8703)
        if clean_hsn.startswith('8703'):
            # If line item claims 5% concessional EV rate, but is identified as ICE
            if app_rate == Decimal('5.00') and ('IS_ICE' in raw_conds or 'FUEL_PETROL' in raw_conds or 'FUEL_DIESEL' in raw_conds):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 28.00,
                    "applied_cess": float(app_cess),
                    "expected_cess": 22.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 1/2017-Central Tax (Rate), Schedule IV, S.No. 188",
                    "description": "Motor vehicles with internal combustion engine (ICE) attract 28% GST + Cess",
                    "supply_type": "TAXABLE",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "INELIGIBLE_SEC_17_5",
                    "itc_restriction_details": "Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)",
                    "cess_applicability": "APPLICABLE",
                    "missing_attributes": [],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "HSN 8703 for ICE/non-electric motor vehicles attracts 28% GST + Cess under Schedule IV S.No. 188 of Notif 1/2017-CT(Rate), not 5% concessional EV rate.",
                        "recommendation": "Apply standard 28% GST and applicable Compensation Cess for ICE motor vehicles."
                    }
                }

            # If line item claims 28% rate on EV
            if app_rate == Decimal('28.00') and ('IS_ELECTRIC' in raw_conds) and tx_date >= date(2019, 8, 1):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 5.00,
                    "applied_cess": float(app_cess),
                    "expected_cess": 0.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 12/2019-Central Tax (Rate)",
                    "description": "Electrically operated vehicles (EVs) attract 5% GST without Compensation Cess w.e.f. 01-Aug-2019",
                    "supply_type": "CONCESSIONAL",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "INELIGIBLE_SEC_17_5",
                    "itc_restriction_details": "Motor vehicles for transport of persons with seating <= 13 blocked under Section 17(5)(a)",
                    "cess_applicability": "NOT_APPLICABLE",
                    "missing_attributes": [],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "Electrically operated vehicles under HSN 8703 attract 5% GST (Notif 12/2019-CT(Rate)) with 0% cess, but invoice applied 28%.",
                        "recommendation": "Update EV tax rate to 5% with 0% Compensation Cess."
                    }
                }

            # If strict classification requested and fuel type / electric attribute missing
            if strict_classification and ('IS_ELECTRIC' not in raw_conds) and ('IS_ICE' not in raw_conds) and app_rate == Decimal('5.00'):
                return {
                    "status": "REVIEW_REQUIRED",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": None,
                    "applied_cess": float(app_cess),
                    "expected_cess": None,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 12/2019-Central Tax (Rate)",
                    "description": "HSN 8703 multi-schedule heading (5% EV vs 28% ICE)",
                    "supply_type": "TAXABLE",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "INELIGIBLE_SEC_17_5",
                    "itc_restriction_details": "Section 17(5)(a) blocked credit",
                    "cess_applicability": "CONDITIONAL_REVIEW_REQUIRED",
                    "missing_attributes": ["is_electric", "fuel_type"],
                    "issue": {
                        "code": "GST_ATTRIBUTE_REQUIRED_FOR_CLASSIFICATION",
                        "severity": "WARNING",
                        "description": "HSN 8703 applies 5% only to electrically operated vehicles under Notif 12/2019-CT(Rate). Provide 'is_electric' attribute or 8-digit tariff code (870380) to verify classification.",
                        "recommendation": "Specify vehicle fuel type / electric propulsion attribute."
                    }
                }

        # B. Motor Vehicle Compensation Cess Criteria (Entry 52B vs Entry 52 vs Entry 46/47)
        if clean_hsn.startswith('8703') and app_rate == Decimal('28.00'):
            # If vehicle attributes are provided, verify cess rate
            if attrs:
                exp_cess_calc, cess_entry_ref, cess_desc, is_suv_qual = cls.evaluate_vehicle_cess_criteria(attrs, raw_conds)
                if abs(app_cess - exp_cess_calc) > Decimal('0.01'):
                    return {
                        "status": "STATUTORY_MISMATCH",
                        "is_statutorily_valid": False,
                        "applied_rate": float(app_rate),
                        "expected_rate": 28.00,
                        "applied_cess": float(app_cess),
                        "expected_cess": float(exp_cess_calc),
                        "matched_rules_count": len(rules),
                        "notification_reference": cess_entry_ref,
                        "description": cess_desc,
                        "supply_type": "TAXABLE",
                        "is_exempt": False,
                        "is_nil_rated": False,
                        "is_zero_rated": False,
                        "is_rcm": False,
                        "itc_eligibility": "INELIGIBLE_SEC_17_5",
                        "itc_restriction_details": "Section 17(5)(a) blocked credit",
                        "cess_applicability": "APPLICABLE",
                        "missing_attributes": [],
                        "issue": {
                            "code": "GST_COMPENSATION_CESS_MISMATCH",
                            "severity": "ERROR",
                            "description": (
                                f"Motor vehicle under HSN 8703 with specifications attracts {exp_cess_calc}% cess "
                                f"under {cess_entry_ref} ({cess_desc}), but invoice applied {app_cess}% cess."
                            ),
                            "recommendation": f"Update Compensation Cess rate to statutory {exp_cess_calc}%."
                        }
                    }

        # C. Diamonds (HSN 7102): Rough (0.25%) vs Cut & Polished (1.5%)
        if clean_hsn.startswith('7102') and tx_date >= date(2018, 1, 25):
            if 'CUT_AND_POLISHED' in raw_conds and app_rate == Decimal('0.25'):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 1.50,
                    "applied_cess": float(app_cess),
                    "expected_cess": 0.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 5/2018-Central Tax (Rate), Schedule VII, S.No. 1",
                    "description": "Cut and polished diamonds attract 1.5% GST, not 0.25%",
                    "supply_type": "TAXABLE",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "ELIGIBLE",
                    "itc_restriction_details": None,
                    "cess_applicability": "NOT_APPLICABLE",
                    "missing_attributes": [],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "Cut and polished diamonds (HSN 7102 39) attract 1.5% GST under Notif 5/2018-CT(Rate). 0.25% concessional rate is restricted strictly to rough diamonds.",
                        "recommendation": "Apply 1.5% GST for cut and polished diamonds."
                    }
                }
            if 'ROUGH_DIAMONDS' in raw_conds and app_rate == Decimal('1.50'):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 0.25,
                    "applied_cess": float(app_cess),
                    "expected_cess": 0.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 1/2018-Central Tax (Rate), Schedule VI, S.No. 1",
                    "description": "Rough diamonds attract 0.25% GST under Schedule VI",
                    "supply_type": "CONCESSIONAL",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "ELIGIBLE",
                    "itc_restriction_details": None,
                    "cess_applicability": "NOT_APPLICABLE",
                    "missing_attributes": [],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "Rough diamonds (HSN 7102 10/21/31) attract 0.25% GST under Notif 1/2018-CT(Rate), but invoice applied 1.5%.",
                        "recommendation": "Apply 0.25% GST for rough diamonds."
                    }
                }

        # D. Restaurant Services (SAC 9963)
        if clean_hsn.startswith('9963') and tx_date >= date(2017, 11, 15):
            # If 18% applied to standalone restaurant
            if app_rate == Decimal('18.00') and ('STANDALONE_RESTAURANT' in raw_conds or 'HOTEL_TARIFF_GTE_7500' not in raw_conds):
                if 'STANDALONE_RESTAURANT' in raw_conds:
                    return {
                        "status": "STATUTORY_MISMATCH",
                        "is_statutorily_valid": False,
                        "applied_rate": float(app_rate),
                        "expected_rate": 5.00,
                        "applied_cess": float(app_cess),
                        "expected_cess": 0.00,
                        "matched_rules_count": len(rules),
                        "notification_reference": "Notification No. 46/2017-Central Tax (Rate)",
                        "description": "Standalone restaurant services attract 5% GST without ITC",
                        "supply_type": "TAXABLE",
                        "is_exempt": False,
                        "is_nil_rated": False,
                        "is_zero_rated": False,
                        "is_rcm": False,
                        "itc_eligibility": "INELIGIBLE_SEC_17_5",
                        "itc_restriction_details": "Section 17(5)(b)(i) blocked credit; supplier cannot take ITC",
                        "cess_applicability": "NOT_APPLICABLE",
                        "missing_attributes": [],
                        "issue": {
                            "code": "GST_STATUTORY_RATE_MISMATCH",
                            "severity": "ERROR",
                            "description": "Standalone restaurant services post 15-Nov-2017 attract 5% without ITC under Notif 46/2017-CT(Rate). 18% rate applies exclusively to restaurants in hotel premises with tariff >= Rs.7,500/night.",
                            "recommendation": "Update restaurant rate to 5% without ITC."
                        }
                    }
                elif strict_classification:
                    return {
                        "status": "REVIEW_REQUIRED",
                        "is_statutorily_valid": False,
                        "applied_rate": float(app_rate),
                        "expected_rate": None,
                        "applied_cess": float(app_cess),
                        "expected_cess": None,
                        "matched_rules_count": len(rules),
                        "notification_reference": "Notification No. 46/2017-Central Tax (Rate) & 20/2019-CT(Rate)",
                        "description": "Restaurant service 18% requires hotel declared tariff >= Rs. 7,500/night",
                        "supply_type": "TAXABLE",
                        "is_exempt": False,
                        "is_nil_rated": False,
                        "is_zero_rated": False,
                        "is_rcm": False,
                        "itc_eligibility": "INELIGIBLE_SEC_17_5",
                        "itc_restriction_details": "Section 17(5)(b)(i) blocked credit",
                        "cess_applicability": "NOT_APPLICABLE",
                        "missing_attributes": ["hotel_declared_tariff"],
                        "issue": {
                            "code": "GST_ATTRIBUTE_REQUIRED_FOR_CLASSIFICATION",
                            "severity": "WARNING",
                            "description": "Restaurant services under SAC 9963 attract 5% without ITC unless located in hotel premises with declared tariff >= Rs.7,500/night. Specify declared tariff attribute to justify 18% rate.",
                            "recommendation": "Confirm whether restaurant is located in hotel premises with room tariff >= Rs.7,500."
                        }
                    }

        # E. Merchant Exports (0.1%)
        if app_rate == Decimal('0.10'):
            if 'ORDINARY_DOMESTIC' in raw_conds or ('MERCHANT_EXPORT' not in raw_conds and clean_hsn != 'MERCHANT_EXPORT'):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 18.00,
                    "applied_cess": float(app_cess),
                    "expected_cess": 0.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 40/2017-Central Tax (Rate) & 41/2017-Integrated Tax (Rate)",
                    "description": "0.1% rate is strictly conditional on statutory merchant export documentation",
                    "supply_type": "TAXABLE",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "ELIGIBLE",
                    "itc_restriction_details": None,
                    "cess_applicability": "NOT_APPLICABLE",
                    "missing_attributes": ["merchant_export_documents"],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "Concessional 0.1% rate under Notif 40/2017-CT(Rate) cannot be applied to ordinary domestic sales. It requires registered merchant exporter GSTIN and export within 90 days under bond/LUT.",
                        "recommendation": "Apply standard statutory HSN rate for domestic sales or verify merchant export declaration."
                    }
                }

        # F. Dairy / Paneer (HSN 0406)
        if clean_hsn.startswith('0406') and tx_date >= date(2022, 7, 18):
            if 'LOOSE_UNPACKAGED' in raw_conds and app_rate == Decimal('5.00'):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 0.00,
                    "applied_cess": float(app_cess),
                    "expected_cess": 0.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 2/2017-CT(Rate) S.No. 27 as amended by Notif 7/2022-CT(Rate)",
                    "description": "Unpackaged / loose paneer is unconditionally exempt (0%)",
                    "supply_type": "EXEMPT",
                    "is_exempt": True,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "ZERO_ITC",
                    "itc_restriction_details": "Exempt supply under Section 11; no ITC under Section 17(2)",
                    "cess_applicability": "NOT_APPLICABLE",
                    "missing_attributes": [],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "Unpackaged / loose paneer (other than pre-packaged and labelled) is exempt (0%) under Notif 7/2022-CT(Rate), but 5% was applied.",
                        "recommendation": "Update rate to 0% (Exempt) for loose unpackaged paneer."
                    }
                }
            if 'PRE_PACKAGED' in raw_conds and app_rate == Decimal('0.00'):
                return {
                    "status": "STATUTORY_MISMATCH",
                    "is_statutorily_valid": False,
                    "applied_rate": float(app_rate),
                    "expected_rate": 5.00,
                    "applied_cess": float(app_cess),
                    "expected_cess": 0.00,
                    "matched_rules_count": len(rules),
                    "notification_reference": "Notification No. 6/2022-Central Tax (Rate), Schedule I, S.No. 26",
                    "description": "Pre-packaged and labelled paneer attracts 5% GST w.e.f. 18-Jul-2022",
                    "supply_type": "TAXABLE",
                    "is_exempt": False,
                    "is_nil_rated": False,
                    "is_zero_rated": False,
                    "is_rcm": False,
                    "itc_eligibility": "ELIGIBLE",
                    "itc_restriction_details": None,
                    "cess_applicability": "NOT_APPLICABLE",
                    "missing_attributes": [],
                    "issue": {
                        "code": "GST_STATUTORY_RATE_MISMATCH",
                        "severity": "ERROR",
                        "description": "Pre-packaged and labelled paneer attracts 5% GST w.e.f. 18-Jul-2022 under Notif 6/2022-CT(Rate). Exemption is withdrawn.",
                        "recommendation": "Apply statutory 5% GST for pre-packaged and labelled paneer."
                    }
                }

        # G. Imitation Jewellery (HSN 7117) vs Precious Jewellery (HSN 7113)
        if clean_hsn.startswith('7117') and app_rate == Decimal('3.00'):
            return {
                "status": "STATUTORY_MISMATCH",
                "is_statutorily_valid": False,
                "applied_rate": float(app_rate),
                "expected_rate": 18.00,
                "applied_cess": float(app_cess),
                "expected_cess": 0.00,
                "matched_rules_count": len(rules),
                "notification_reference": "Notification No. 1/2017-Central Tax (Rate), Schedule III, S.No. 223",
                "description": "Imitation jewellery attracts 18% GST",
                "supply_type": "TAXABLE",
                "is_exempt": False,
                "is_nil_rated": False,
                "is_zero_rated": False,
                "is_rcm": False,
                "itc_eligibility": "ELIGIBLE",
                "itc_restriction_details": None,
                "cess_applicability": "NOT_APPLICABLE",
                "missing_attributes": [],
                "issue": {
                    "code": "GST_STATUTORY_RATE_MISMATCH",
                    "severity": "ERROR",
                    "description": "Imitation jewellery under HSN 7117 attracts 18% GST under Schedule III S.No. 223. 3% rate applies strictly to precious metals (HSN 7108/7113).",
                    "recommendation": "Apply 18% GST for imitation jewellery."
                }
            }

        # -------------------------------------------------------------------------
        # Case 3: Standard Statutory Matching
        # -------------------------------------------------------------------------
        for rule in rules:
            expected_total = rule.igst_rate if is_interstate else (rule.cgst_rate + rule.sgst_rate)
            expected_total = expected_total.quantize(Decimal('0.01'))
            expected_cess = rule.cess_rate.quantize(Decimal('0.01'))

            rate_matches = (abs(app_rate - expected_total) <= Decimal('0.01'))
            cess_matches = (abs(app_cess - expected_cess) <= Decimal('0.01'))

            if rate_matches and cess_matches:
                # Perfect statutory match
                return {
                    "status": "VALID",
                    "is_statutorily_valid": True,
                    "applied_rate": float(app_rate),
                    "expected_rate": float(expected_total),
                    "applied_cess": float(app_cess),
                    "expected_cess": float(expected_cess),
                    "matched_rules_count": len(rules),
                    "notification_reference": rule.notification_ref,
                    "description": rule.description,
                    "supply_type": rule.supply_type,
                    "is_exempt": rule.is_exempt,
                    "is_nil_rated": rule.is_nil_rated,
                    "is_zero_rated": (rule.supply_type == 'ZERO_RATED'),
                    "is_rcm": rule.is_rcm,
                    "itc_eligibility": rule.itc_eligibility,
                    "itc_restriction_details": rule.itc_restriction_details,
                    "cess_applicability": "APPLICABLE" if rule.cess_rate > 0 else "NOT_APPLICABLE",
                    "missing_attributes": [],
                    "issue": None
                }

        # -------------------------------------------------------------------------
        # Case 4: Known HSN, but applied rate diverges from statutory rules
        # -------------------------------------------------------------------------
        primary_rule = rules[0]
        expected_total = primary_rule.igst_rate if is_interstate else (primary_rule.cgst_rate + primary_rule.sgst_rate)
        expected_total = expected_total.quantize(Decimal('0.01'))
        expected_cess = primary_rule.cess_rate.quantize(Decimal('0.01'))

        return {
            "status": "STATUTORY_MISMATCH",
            "is_statutorily_valid": False,
            "applied_rate": float(app_rate),
            "expected_rate": float(expected_total),
            "applied_cess": float(app_cess),
            "expected_cess": float(expected_cess),
            "matched_rules_count": len(rules),
            "notification_reference": primary_rule.notification_ref,
            "description": primary_rule.description,
            "supply_type": primary_rule.supply_type,
            "is_exempt": primary_rule.is_exempt,
            "is_nil_rated": primary_rule.is_nil_rated,
            "is_zero_rated": (primary_rule.supply_type == 'ZERO_RATED'),
            "is_rcm": primary_rule.is_rcm,
            "itc_eligibility": primary_rule.itc_eligibility,
            "itc_restriction_details": primary_rule.itc_restriction_details,
            "cess_applicability": "APPLICABLE" if primary_rule.cess_rate > 0 else "NOT_APPLICABLE",
            "missing_attributes": [],
            "issue": {
                "code": "GST_STATUTORY_RATE_MISMATCH",
                "severity": "ERROR",
                "description": (
                    f"HSN/SAC '{hsn_sc}' on date {tx_date} has statutory rate of {expected_total}% "
                    f"(per {primary_rule.notification_ref}), but invoice applied {app_rate}%."
                ),
                "recommendation": f"Update voucher tax rate to statutory {expected_total}% or verify classification conditions."
            }
        }

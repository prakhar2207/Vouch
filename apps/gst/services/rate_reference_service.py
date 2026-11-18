import logging
from decimal import Decimal
from datetime import date
from typing import Dict, Any, List, Optional, Tuple, NamedTuple

logger = logging.getLogger('apps.gst.rate_reference')


class GSTRateRule(NamedTuple):
    hsn_sc: str
    description: str
    item_type: str  # 'GOODS' or 'SERVICES'
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    cess_rate: Decimal
    effective_from: date
    effective_to: Optional[date]
    notification_ref: str
    conditions: Tuple[str, ...]
    is_exempt: bool
    is_nil_rated: bool


class GSTRateScheduleService:
    """
    Authoritative Effective-Dated Statutory GST Rate Reference Service (Round 2.2.1).
    Maintains CBIC statutory rate schedules and amendments across goods and services.
    
    Statutory Authorities:
    - Notification No. 1/2017-Central Tax (Rate) dated 28-06-2017 (Goods standard rate schedule)
    - Notification No. 2/2017-Central Tax (Rate) dated 28-06-2017 (Goods exemption schedule)
    - Notification No. 11/2017-Central Tax (Rate) dated 28-06-2017 (Services rate schedule)
    - Notification No. 12/2017-Central Tax (Rate) dated 28-06-2017 (Services exemption schedule)
    - Notification No. 46/2017-Central Tax (Rate) dated 14-11-2017 (Restaurant rate reduction to 5%)
    - Notification No. 1/2018-Central Tax (Rate) dated 25-01-2018 (Diamond and precious stones special rates)
    - Notification No. 12/2019-Central Tax (Rate) dated 31-07-2019 (Electric vehicles reduction to 5%)
    - Notification No. 6/2022-Central Tax (Rate) dated 13-07-2022 (Pre-packaged labeled goods to 5%)
    - Notification No. 40/2017-Central Tax (Rate) & 41/2017-Integrated Tax (Rate) (Merchant exports 0.1%)
    - Goods and Services Tax (Compensation to States) Act, 2017 (Compensation Cess schedule)
    
    INVARIANT: STRICTLY READ-ONLY. Never mutates historical vouchers or accounting books.
    """

    # Comprehensive Effective-Dated Statutory Rate Rules
    STATUTORY_RULES: List[GSTRateRule] = [
        # --- 1. Industrial Belts & Rubber Products (HSN 4010) ---
        GSTRateRule(
            hsn_sc='4010',
            description='Conveyor or transmission belts or belting, of vulcanised rubber',
            item_type='GOODS',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule III, S.No. 110',
            conditions=(),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 2. Industrial Machinery & Valves (HSN 8481) ---
        GSTRateRule(
            hsn_sc='8481',
            description='Taps, cocks, valves and similar appliances for pipes, boiler shells, tanks',
            item_type='GOODS',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule III, S.No. 360',
            conditions=(),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 3. Belt Installation, Splicing & Maintenance Services (SAC 9954 / 9987) ---
        GSTRateRule(
            hsn_sc='9954',
            description='General construction and installation services of industrial equipment',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 3',
            conditions=(),
            is_exempt=False,
            is_nil_rated=False
        ),
        GSTRateRule(
            hsn_sc='9987',
            description='Maintenance, repair and installation services of fabricated metal and machinery',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 25',
            conditions=(),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 4. Goods Transport Agency (GTA) Services (SAC 9965) ---
        # 5% RCM (without ITC)
        GSTRateRule(
            hsn_sc='9965',
            description='Goods transport agency (GTA) services under reverse charge (without ITC)',
            item_type='SERVICES',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 9(iii) & 13/2017-CT(Rate)',
            conditions=('RCM', 'NO_ITC'),
            is_exempt=False,
            is_nil_rated=False
        ),
        # 12% Forward Charge (with ITC)
        GSTRateRule(
            hsn_sc='9965',
            description='Goods transport agency (GTA) services under forward charge (with ITC option)',
            item_type='SERVICES',
            cgst_rate=Decimal('6.00'),
            sgst_rate=Decimal('6.00'),
            igst_rate=Decimal('12.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 9(iii)',
            conditions=('FORWARD_CHARGE', 'WITH_ITC'),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 5. Restaurant Services (SAC 9963) — Effective-Dated Rate Change ---
        # Historical: 01-Jul-2017 to 14-Nov-2017 (18% with ITC)
        GSTRateRule(
            hsn_sc='9963',
            description='Restaurant services (standalone/air-conditioned) with input tax credit',
            item_type='SERVICES',
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            igst_rate=Decimal('18.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2017, 11, 14),
            notification_ref='Notification No. 11/2017-Central Tax (Rate), S.No. 7(i)',
            conditions=('WITH_ITC',),
            is_exempt=False,
            is_nil_rated=False
        ),
        # Current: 15-Nov-2017 onwards (5% without ITC)
        GSTRateRule(
            hsn_sc='9963',
            description='Restaurant services (standalone) without input tax credit',
            item_type='SERVICES',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 11, 15),
            effective_to=None,
            notification_ref='Notification No. 46/2017-Central Tax (Rate) amending 11/2017-CT(Rate)',
            conditions=('NO_ITC',),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 6. Electric Vehicles (HSN 8702 / 8703) — Effective-Dated Rate Change ---
        # Historical: 01-Jul-2017 to 31-Jul-2019 (12%)
        GSTRateRule(
            hsn_sc='8703',
            description='Electrically operated vehicles (EVs) for transport of persons',
            item_type='GOODS',
            cgst_rate=Decimal('6.00'),
            sgst_rate=Decimal('6.00'),
            igst_rate=Decimal('12.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2019, 7, 31),
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule II, S.No. 206',
            conditions=('EV',),
            is_exempt=False,
            is_nil_rated=False
        ),
        # Current: 01-Aug-2019 onwards (5%)
        GSTRateRule(
            hsn_sc='8703',
            description='Electrically operated vehicles (EVs) including two and three wheelers',
            item_type='GOODS',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2019, 8, 1),
            effective_to=None,
            notification_ref='Notification No. 12/2019-Central Tax (Rate) amending 1/2017-CT(Rate)',
            conditions=('EV',),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 7. Gold, Silver & Precious Metals (HSN 7108 & 7113) ---
        GSTRateRule(
            hsn_sc='7108',
            description='Gold (including gold plated with platinum) unwrought or in semi-manufactured forms',
            item_type='GOODS',
            cgst_rate=Decimal('1.50'),
            sgst_rate=Decimal('1.50'),
            igst_rate=Decimal('3.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule V, S.No. 13',
            conditions=(),
            is_exempt=False,
            is_nil_rated=False
        ),
        GSTRateRule(
            hsn_sc='7113',
            description='Articles of jewellery and parts thereof, of precious metal or of metal clad with precious metal',
            item_type='GOODS',
            cgst_rate=Decimal('1.50'),
            sgst_rate=Decimal('1.50'),
            igst_rate=Decimal('3.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule V, S.No. 13',
            conditions=(),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 8. Rough Diamonds (HSN 7102) — Special Rate 0.25% ---
        # Historical: 01-Jul-2017 to 24-Jan-2018 (3%)
        GSTRateRule(
            hsn_sc='7102',
            description='Rough diamonds, unworked or simply sawn, cleaved or bruted',
            item_type='GOODS',
            cgst_rate=Decimal('1.50'),
            sgst_rate=Decimal('1.50'),
            igst_rate=Decimal('3.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2018, 1, 24),
            notification_ref='Notification No. 1/2017-Central Tax (Rate), Schedule V, S.No. 1',
            conditions=('ROUGH_DIAMONDS',),
            is_exempt=False,
            is_nil_rated=False
        ),
        # Current: 25-Jan-2018 onwards (0.25%)
        GSTRateRule(
            hsn_sc='7102',
            description='Rough diamonds, unworked or simply sawn, cleaved or bruted',
            item_type='GOODS',
            cgst_rate=Decimal('0.125'),
            sgst_rate=Decimal('0.125'),
            igst_rate=Decimal('0.25'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2018, 1, 25),
            effective_to=None,
            notification_ref='Notification No. 1/2018-Central Tax (Rate), Schedule VI, S.No. 1',
            conditions=('ROUGH_DIAMONDS',),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 9. Pre-Packaged Dairy / Food Products (HSN 0406) ---
        # Historical: 01-Jul-2017 to 17-Jul-2022 (Exempt 0%)
        GSTRateRule(
            hsn_sc='0406',
            description='Cheese and paneer (other than pre-packaged and labelled)',
            item_type='GOODS',
            cgst_rate=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=date(2022, 7, 17),
            notification_ref='Notification No. 2/2017-Central Tax (Rate), S.No. 27',
            conditions=('UNBRANDED_LOOSE',),
            is_exempt=True,
            is_nil_rated=False
        ),
        # Current: 18-Jul-2022 onwards (5% if pre-packaged and labelled)
        GSTRateRule(
            hsn_sc='0406',
            description='Paneer and cheese when pre-packaged and labelled',
            item_type='GOODS',
            cgst_rate=Decimal('2.50'),
            sgst_rate=Decimal('2.50'),
            igst_rate=Decimal('5.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2022, 7, 18),
            effective_to=None,
            notification_ref='Notification No. 6/2022-Central Tax (Rate), Schedule I, S.No. 26',
            conditions=('PRE_PACKAGED',),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 10. Nil-Rated / Unconditionally Exempt Supplies (HSN 0401) ---
        GSTRateRule(
            hsn_sc='0401',
            description='Fresh milk, pasteurised milk, not concentrated nor containing added sugar',
            item_type='GOODS',
            cgst_rate=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 2/2017-Central Tax (Rate), S.No. 25',
            conditions=(),
            is_exempt=True,
            is_nil_rated=True
        ),

        # --- 11. Luxury Motor Vehicles with Compensation Cess (HSN 8703) ---
        GSTRateRule(
            hsn_sc='8703',
            description='Large motor cars (engine capacity > 1500cc) with Compensation Cess',
            item_type='GOODS',
            cgst_rate=Decimal('14.00'),
            sgst_rate=Decimal('14.00'),
            igst_rate=Decimal('28.00'),
            cess_rate=Decimal('22.00'),
            effective_from=date(2017, 7, 1),
            effective_to=None,
            notification_ref='Notification No. 1/2017-CT(Rate) & Notif 1/2017-Compensation Cess(Rate)',
            conditions=('LUXURY_CAR',),
            is_exempt=False,
            is_nil_rated=False
        ),

        # --- 12. Merchant Exports Special Scheme (0.1%) ---
        GSTRateRule(
            hsn_sc='MERCHANT_EXPORT',
            description='Supply of goods to merchant exporter for export under bond/LUT',
            item_type='GOODS',
            cgst_rate=Decimal('0.05'),
            sgst_rate=Decimal('0.05'),
            igst_rate=Decimal('0.10'),
            cess_rate=Decimal('0.00'),
            effective_from=date(2017, 10, 23),
            effective_to=None,
            notification_ref='Notification No. 40/2017-Central Tax (Rate) & 41/2017-Integrated Tax (Rate)',
            conditions=('MERCHANT_EXPORT',),
            is_exempt=False,
            is_nil_rated=False
        ),
    ]

    @classmethod
    def get_matching_rules(
        cls,
        hsn_sc: str,
        tx_date: date,
        item_type: Optional[str] = None
    ) -> List[GSTRateRule]:
        """
        Retrieves active statutory rate rules matching HSN/SAC code on transaction date.
        Supports 4-digit, 6-digit, and 8-digit HSN matching.
        """
        clean_hsn = (hsn_sc or '').strip().replace(' ', '')
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

            # Check HSN code match (prefix match: rule hsn matches start of voucher hsn or vice versa)
            if clean_hsn and (clean_hsn.startswith(rule.hsn_sc) or rule.hsn_sc.startswith(clean_hsn)):
                matches.append(rule)
            elif rule.hsn_sc == 'MERCHANT_EXPORT' and 'MERCHANT_EXPORT' in clean_hsn.upper():
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
        conditions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validates transaction tax rate against effective-dated statutory CBIC rules.
        
        Returns:
            {
                "status": "VALID" | "STATUTORY_MISMATCH" | "REVIEW_REQUIRED" | "EXEMPT",
                "is_statutorily_valid": bool,
                "applied_rate": Decimal,
                "expected_rate": Optional[Decimal],
                "expected_cess": Optional[Decimal],
                "matched_rules_count": int,
                "notification_reference": Optional[str],
                "issue": Optional[Dict[str, Any]]
            }
        """
        app_rate = Decimal(str(applied_rate or '0.00')).quantize(Decimal('0.01'))
        app_cess = Decimal(str(applied_cess or '0.00')).quantize(Decimal('0.01'))
        cond_set = set(conditions or [])

        rules = cls.get_matching_rules(hsn_sc, tx_date)

        # 1. Unrecognized / Ambiguous HSN
        if not rules:
            return {
                "status": "REVIEW_REQUIRED",
                "is_statutorily_valid": True,  # Non-blocking review flag
                "applied_rate": float(app_rate),
                "expected_rate": None,
                "expected_cess": None,
                "matched_rules_count": 0,
                "notification_reference": None,
                "issue": {
                    "code": "GST_RATE_REVIEW_REQUIRED",
                    "severity": "WARNING",
                    "description": f"HSN/SAC code '{hsn_sc}' has no exact statutory rule match for transaction date {tx_date}. Verification recommended.",
                    "recommendation": "Confirm applicable notification rate in CBIC tariff schedules."
                }
            }

        # 2. Check if applied rate matches any matching rule
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
                    "expected_cess": float(expected_cess),
                    "matched_rules_count": len(rules),
                    "notification_reference": rule.notification_ref,
                    "description": rule.description,
                    "issue": None
                }

        # 3. Known HSN, but applied rate diverges from all applicable statutory rules for this date
        primary_rule = rules[0]
        expected_total = primary_rule.igst_rate if is_interstate else (primary_rule.cgst_rate + primary_rule.sgst_rate)
        expected_total = expected_total.quantize(Decimal('0.01'))
        expected_cess = primary_rule.cess_rate.quantize(Decimal('0.01'))

        return {
            "status": "STATUTORY_MISMATCH",
            "is_statutorily_valid": False,
            "applied_rate": float(app_rate),
            "expected_rate": float(expected_total),
            "expected_cess": float(expected_cess),
            "matched_rules_count": len(rules),
            "notification_reference": primary_rule.notification_ref,
            "description": primary_rule.description,
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

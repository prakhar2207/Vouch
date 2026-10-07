import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear


class TDSService:
    """
    Indian Income Tax Act TDS (Tax Deducted at Source) & TCS Engine.
    Statutory Section Support:
    - 194C: Payments to Contractors / Sub-contractors (1% Ind/HUF, 2% Company/Others).
            Threshold: Single invoice > ₹30,000 or Cumulative FY > ₹1,00,000.
    - 194J: Fees for Professional (10%) or Technical (2%) Services / Royalty.
            Threshold: Cumulative FY > ₹30,000.
    - 194I: Rent (2% Plant/Machinery, 10% Land/Building).
            Threshold: Cumulative FY > ₹2,40,000.
    - 194Q: Purchase of Goods exceeding ₹50 Lakhs (0.1%).
    - 206AA: Higher penal rate (minimum 20%) if payee PAN is missing or invalid.
    """

    DEFAULT_RATES: Dict[str, Dict[str, Any]] = {
        '194C_INDIVIDUAL': {
            'section': '194C',
            'description': 'Contractors / Sub-contractors (Individual / HUF)',
            'rate': Decimal('1.00'),
            'single_threshold': Decimal('30000.00'),
            'aggregate_threshold': Decimal('100000.00'),
        },
        '194C_COMPANY': {
            'section': '194C',
            'description': 'Contractors / Sub-contractors (Company / Firm)',
            'rate': Decimal('2.00'),
            'single_threshold': Decimal('30000.00'),
            'aggregate_threshold': Decimal('100000.00'),
        },
        '194J_TECH': {
            'section': '194J',
            'description': 'Fees for Technical Services (FTS)',
            'rate': Decimal('2.00'),
            'single_threshold': None,
            'aggregate_threshold': Decimal('30000.00'),
        },
        '194J_PROF': {
            'section': '194J',
            'description': 'Fees for Professional Services / Royalty',
            'rate': Decimal('10.00'),
            'single_threshold': None,
            'aggregate_threshold': Decimal('30000.00'),
        },
        '194I_PLANT': {
            'section': '194I',
            'description': 'Rent - Plant, Machinery & Equipment',
            'rate': Decimal('2.00'),
            'single_threshold': None,
            'aggregate_threshold': Decimal('240000.00'),
        },
        '194I_BUILDING': {
            'section': '194I',
            'description': 'Rent - Land, Building & Furniture',
            'rate': Decimal('10.00'),
            'single_threshold': None,
            'aggregate_threshold': Decimal('240000.00'),
        },
        '194Q': {
            'section': '194Q',
            'description': 'Purchase of Goods exceeding ₹50 Lakhs',
            'rate': Decimal('0.10'),
            'single_threshold': None,
            'aggregate_threshold': Decimal('5000000.00'),
        },
    }

    @classmethod
    def get_or_create_tds_payable_ledger(cls, company: Company, section: str) -> Ledger:
        """
        Provisions or fetches the statutory TDS Payable ledger under Duties & Taxes.
        Example: 'TDS Payable - Sec 194C', 'TDS Payable - Sec 194J'.
        """
        sec_clean = str(section).strip().upper().replace('SEC', '').replace('SECTION', '').strip()
        ledger_name = f"TDS Payable - Sec {sec_clean}"

        tax_group = LedgerGroup.objects.filter(company=company, name__iexact="Duties & Taxes").first() or \
                    LedgerGroup.objects.filter(company=company, name__icontains="Duties").first()
        if not tax_group:
            tax_group, _ = LedgerGroup.objects.get_or_create(
                company=company,
                name="Duties & Taxes",
                defaults={"nature": "LIABILITY"}
            )

        tds_ledger = Ledger.objects.filter(company=company, name__iexact=ledger_name).first()
        if not tds_ledger:
            tds_ledger = Ledger.objects.create(
                company=company,
                group=tax_group,
                name=ledger_name,
                ledger_type="TAX",
                is_active=True
            )
        return tds_ledger

    @classmethod
    def validate_pan(cls, pan: Optional[str]) -> bool:
        """
        Validates 10-character Indian PAN format: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).
        """
        import re
        if not pan:
            return False
        return bool(re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan.strip().upper()))

    @classmethod
    def compute_ytd_purchases(
        cls,
        company: Company,
        party_ledger: Ledger,
        voucher_date: Optional[datetime.date] = None
    ) -> Decimal:
        """
        Calculates cumulative posted taxable purchases for the party in the current Financial Year.
        Used to determine statutory threshold crossing.
        """
        v_date = voucher_date or timezone.now().date()
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        fy = InvoiceSequenceService.get_or_create_active_fy(company, v_date)

        agg = Voucher.objects.filter(
            company=company,
            party_ledger=party_ledger,
            financial_year=fy,
            voucher_type__in=['PURCHASE', 'JOURNAL'],
            status='POSTED'
        ).aggregate(tot=Sum('total_amount'))['tot']

        return agg or Decimal('0.00')

    @classmethod
    def calculate_tds(
        cls,
        company: Company,
        party_ledger: Ledger,
        taxable_amount: Decimal,
        section: Optional[str] = None,
        rate: Optional[Decimal] = None,
        voucher_date: Optional[datetime.date] = None,
        check_threshold: bool = True
    ) -> Dict[str, Any]:
        """
        Calculates statutory TDS deduction for an invoice according to Indian Income Tax rules.
        Handles Section 206AA penal rate (20%) when PAN is absent.
        """
        taxable_amt = Decimal(str(taxable_amount)).quantize(Decimal('0.01'))
        if taxable_amt <= Decimal('0.00'):
            return {
                'applicable': False,
                'section': section,
                'rate': Decimal('0.00'),
                'base_amount': Decimal('0.00'),
                'tds_amount': Decimal('0.00'),
                'net_payable': Decimal('0.00'),
                'penal_206aa': False,
                'threshold_crossed': False
            }

        sec = str(section or getattr(party_ledger, 'tds_section', None) or '194C').upper()
        if sec.startswith('SEC'):
            sec = sec.replace('SEC', '').strip()

        # Check Party PAN
        gstin_val = getattr(party_ledger, 'gstin', '') or ''
        party_pan = getattr(party_ledger, 'pan', None) or (gstin_val[:10] if gstin_val else None)
        has_valid_pan = cls.validate_pan(party_pan)

        penal_206aa = False
        effective_rate = Decimal(str(rate)) if rate is not None else None

        if not has_valid_pan:
            # Section 206AA mandates minimum 20% if no PAN
            effective_rate = Decimal('20.00')
            penal_206aa = True
        elif effective_rate is None:
            # Look up configured rate on party ledger or default table
            if party_ledger and party_ledger.tds_rate and party_ledger.tds_rate > Decimal('0.00'):
                effective_rate = party_ledger.tds_rate
            else:
                # Default rate based on section
                rule = None
                for k, v in cls.DEFAULT_RATES.items():
                    if v['section'] == sec:
                        rule = v
                        break
                effective_rate = rule['rate'] if rule else Decimal('2.00')

        # Check Statutory Threshold
        threshold_crossed = True
        if check_threshold and not penal_206aa:
            rule_entry = next((v for v in cls.DEFAULT_RATES.values() if v['section'] == sec), None)
            if rule_entry:
                single_thresh = rule_entry.get('single_threshold')
                agg_thresh = rule_entry.get('aggregate_threshold')

                if single_thresh and taxable_amt >= single_thresh:
                    threshold_crossed = True
                elif agg_thresh:
                    ytd = cls.compute_ytd_purchases(company, party_ledger, voucher_date)
                    threshold_crossed = (ytd + taxable_amt) >= agg_thresh
                else:
                    threshold_crossed = True

        if not threshold_crossed:
            return {
                'applicable': False,
                'section': sec,
                'rate': effective_rate,
                'base_amount': taxable_amt,
                'tds_amount': Decimal('0.00'),
                'net_payable': taxable_amt,
                'penal_206aa': penal_206aa,
                'threshold_crossed': False,
                'reason': f"Section {sec} threshold not crossed."
            }

        tds_amount = (taxable_amt * effective_rate / Decimal('100')).quantize(Decimal('0.01'))
        net_payable = (taxable_amt - tds_amount).quantize(Decimal('0.01'))

        return {
            'applicable': True,
            'section': sec,
            'rate': effective_rate,
            'base_amount': taxable_amt,
            'tds_amount': tds_amount,
            'net_payable': net_payable,
            'penal_206aa': penal_206aa,
            'threshold_crossed': True,
            'pan': party_pan if has_valid_pan else None
        }

    @classmethod
    def generate_tds_summary(
        cls,
        company: Company,
        financial_year: Optional[FinancialYear] = None,
        quarter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates quarterly Form 26Q tax audit summary for Indian Income Tax compliance.
        Aggregates TDS deducted by Section, Vendor, and PAN.
        """
        qs = Voucher.objects.filter(
            company=company,
            tds_amount__gt=Decimal('0.00'),
            status='POSTED'
        ).select_related('party_ledger', 'tds_ledger', 'financial_year')

        if financial_year:
            qs = qs.filter(financial_year=financial_year)

        if quarter:
            q_map = {
                'Q1': (4, 6),
                'Q2': (7, 9),
                'Q3': (10, 12),
                'Q4': (1, 3)
            }
            if quarter.upper() in q_map:
                start_m, end_m = q_map[quarter.upper()]
                if quarter.upper() == 'Q4':
                    qs = qs.filter(voucher_date__month__gte=start_m, voucher_date__month__lte=end_m)
                else:
                    qs = qs.filter(voucher_date__month__gte=start_m, voucher_date__month__lte=end_m)

        vouchers = list(qs.order_by('voucher_date'))

        total_base = Decimal('0.00')
        total_tds = Decimal('0.00')
        section_summary: Dict[str, Dict[str, Any]] = {}
        party_summary: Dict[str, Dict[str, Any]] = {}
        missing_pan_count = 0

        for v in vouchers:
            sec = v.tds_section or 'OTHER'
            tds_amt = v.tds_amount or Decimal('0.00')
            # Base amount is gross taxable amount
            base_amt = v.total_amount + tds_amt

            total_base += base_amt
            total_tds += tds_amt

            # Section summary
            if sec not in section_summary:
                section_summary[sec] = {
                    'section': sec,
                    'voucher_count': 0,
                    'total_base_amount': Decimal('0.00'),
                    'total_tds_deducted': Decimal('0.00')
                }
            section_summary[sec]['voucher_count'] += 1
            section_summary[sec]['total_base_amount'] += base_amt
            section_summary[sec]['total_tds_deducted'] += tds_amt

            # Party summary
            party = v.party_ledger
            party_key = str(party.id) if party else 'UNKNOWN'
            party_pan = getattr(party, 'pan', None) or (getattr(party, 'gstin', '')[:10] if getattr(party, 'gstin', '') else None)
            is_pan_valid = cls.validate_pan(party_pan)

            if not is_pan_valid:
                missing_pan_count += 1

            if party_key not in party_summary:
                party_summary[party_key] = {
                    'party_id': party_key,
                    'party_name': party.name if party else 'Unknown Party',
                    'pan': party_pan if is_pan_valid else 'PAN NOT AVAILABLE',
                    'is_pan_valid': is_pan_valid,
                    'voucher_count': 0,
                    'total_base_amount': Decimal('0.00'),
                    'total_tds_deducted': Decimal('0.00')
                }
            party_summary[party_key]['voucher_count'] += 1
            party_summary[party_key]['total_base_amount'] += base_amt
            party_summary[party_key]['total_tds_deducted'] += tds_amt

        return {
            'company_name': company.name,
            'total_vouchers': len(vouchers),
            'total_base_amount': str(total_base.quantize(Decimal('0.01'))),
            'total_tds_deducted': str(total_tds.quantize(Decimal('0.01'))),
            'missing_pan_vouchers': missing_pan_count,
            'sections': [
                {
                    'section': s['section'],
                    'voucher_count': s['voucher_count'],
                    'total_base_amount': str(s['total_base_amount'].quantize(Decimal('0.01'))),
                    'total_tds_deducted': str(s['total_tds_deducted'].quantize(Decimal('0.01')))
                }
                for s in section_summary.values()
            ],
            'parties': [
                {
                    'party_id': p['party_id'],
                    'party_name': p['party_name'],
                    'pan': p['pan'],
                    'is_pan_valid': p['is_pan_valid'],
                    'voucher_count': p['voucher_count'],
                    'total_base_amount': str(p['total_base_amount'].quantize(Decimal('0.01'))),
                    'total_tds_deducted': str(p['total_tds_deducted'].quantize(Decimal('0.01')))
                }
                for p in party_summary.values()
            ]
        }

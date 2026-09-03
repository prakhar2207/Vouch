import datetime
from decimal import Decimal
from django.db.models import Sum, Q
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import LedgerEntry

class PeriodBalanceService:
    @staticmethod
    def parse_date(date_val):
        if not date_val:
            return None
        if isinstance(date_val, datetime.date):
            return date_val
        return datetime.date.fromisoformat(str(date_val).split('T')[0])

    @staticmethod
    def calculate_ledger_period_balance(ledger: Ledger, from_date, to_date) -> dict:
        """
        On-the-fly dynamic balance computation across continuous periods [from_date, to_date]:
        Opening Balance(from_date) = Initial Ledger Opening + Sum(Debits - Credits for t < from_date)
        Closing Balance(to_date) = Opening Balance(from_date) + Sum(Debits - Credits for from_date <= t <= to_date)
        """
        d_from = PeriodBalanceService.parse_date(from_date)
        d_to = PeriodBalanceService.parse_date(to_date) or datetime.date(2099, 12, 31)

        # 1. Initial Opening Balance Commenced
        initial_net = Decimal('0.00')
        if d_from is None or not ledger.opening_date or ledger.opening_date <= d_from:
            if ledger.opening_balance_type == 'DEBIT':
                initial_net = ledger.opening_balance
            else:
                initial_net = -ledger.opening_balance

        # 2. Prior movements strictly before from_date (t < from_date)
        if d_from is not None:
            prior_agg = LedgerEntry.objects.filter(
                ledger=ledger,
                voucher__company=ledger.company,
                voucher__voucher_date__lt=d_from,
                voucher__status='POSTED'
            ).aggregate(
                prior_dr=Sum('debit_amount'),
                prior_cr=Sum('credit_amount')
            )
            prior_dr = prior_agg.get('prior_dr') or Decimal('0.00')
            prior_cr = prior_agg.get('prior_cr') or Decimal('0.00')
        else:
            prior_dr = Decimal('0.00')
            prior_cr = Decimal('0.00')

        net_opening = initial_net + (prior_dr - prior_cr)
        if net_opening >= Decimal('0.00'):
            opening_bal = net_opening
            opening_type = 'DR'
        else:
            opening_bal = abs(net_opening)
            opening_type = 'CR'

        # 3. Movements in selected period [from_date <= t <= to_date]
        period_filter = Q(
            ledger=ledger,
            voucher__company=ledger.company,
            voucher__status='POSTED',
            voucher__voucher_date__lte=d_to
        )
        if d_from is not None:
            period_filter &= Q(voucher__voucher_date__gte=d_from)

        period_agg = LedgerEntry.objects.filter(period_filter).aggregate(
            period_dr=Sum('debit_amount'),
            period_cr=Sum('credit_amount')
        )
        period_dr = period_agg.get('period_dr') or Decimal('0.00')
        period_cr = period_agg.get('period_cr') or Decimal('0.00')

        # 4. Closing Balance at to_date
        net_closing = net_opening + (period_dr - period_cr)
        if net_closing >= Decimal('0.00'):
            closing_bal = net_closing
            closing_type = 'DR'
        else:
            closing_bal = abs(net_closing)
            closing_type = 'CR'

        return {
            "ledger_id": str(ledger.id),
            "ledger_name": ledger.name,
            "group_name": ledger.group.name if ledger.group else "",
            "group_nature": ledger.group.nature if ledger.group else "ASSET",
            "from_date": d_from.strftime('%Y-%m-%d') if d_from else "",
            "to_date": d_to.strftime('%Y-%m-%d') if d_to else "",
            "opening_balance": str(opening_bal),
            "opening_type": opening_type,
            "period_debit": str(period_dr),
            "period_credit": str(period_cr),
            "closing_balance": str(closing_bal),
            "closing_type": closing_type,
            "raw_net_closing": net_closing
        }

    @staticmethod
    def get_period_trial_balance(company: Company, from_date, to_date) -> dict:
        """
        Dynamically generates full Trial Balance for any continuous period [from_date, to_date].
        Adheres to double-entry equilibrium across continuous accounting boundaries.
        """
        d_from = PeriodBalanceService.parse_date(from_date) or datetime.date(2000, 1, 1)
        d_to = PeriodBalanceService.parse_date(to_date) or datetime.date(2099, 12, 31)

        ledgers = Ledger.objects.filter(company=company, is_active=True).select_related('group').order_by('group__nature', 'name')

        rows = []
        tot_op_dr = Decimal('0.00')
        tot_op_cr = Decimal('0.00')
        tot_period_dr = Decimal('0.00')
        tot_period_cr = Decimal('0.00')
        tot_cl_dr = Decimal('0.00')
        tot_cl_cr = Decimal('0.00')

        for ledger in ledgers:
            data = PeriodBalanceService.calculate_ledger_period_balance(ledger, d_from, d_to)
            op_val = Decimal(data['opening_balance'])
            cl_val = Decimal(data['closing_balance'])
            p_dr = Decimal(data['period_debit'])
            p_cr = Decimal(data['period_credit'])

            if data['opening_type'] == 'DR':
                tot_op_dr += op_val
            else:
                tot_op_cr += op_val

            tot_period_dr += p_dr
            tot_period_cr += p_cr

            if data['closing_type'] == 'DR':
                tot_cl_dr += cl_val
            else:
                tot_cl_cr += cl_val

            rows.append(data)

        return {
            "company_id": str(company.id),
            "company_name": company.name,
            "from_date": d_from.strftime('%Y-%m-%d'),
            "to_date": d_to.strftime('%Y-%m-%d'),
            "totals": {
                "opening_debit": str(tot_op_dr),
                "opening_credit": str(tot_op_cr),
                "period_debit": str(tot_period_dr),
                "period_credit": str(tot_period_cr),
                "closing_debit": str(tot_cl_dr),
                "closing_credit": str(tot_cl_cr),
                "is_opening_balanced": tot_op_dr == tot_op_cr,
                "is_period_balanced": tot_period_dr == tot_period_cr,
                "is_closing_balanced": tot_cl_dr == tot_cl_cr,
            },
            "rows": rows
        }

import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum, Q

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product
from apps.accounting.services.period_service import PeriodBalanceService

class FinancialStatementsService:
    @staticmethod
    def parse_date(date_val) -> Optional[datetime.date]:
        if not date_val:
            return None
        if isinstance(date_val, datetime.date):
            return date_val
        return datetime.date.fromisoformat(str(date_val).split('T')[0])

    @staticmethod
    def get_fiscal_year_start(for_date: datetime.date) -> datetime.date:
        if for_date.month >= 4:
            return datetime.date(for_date.year, 4, 1)
        else:
            return datetime.date(for_date.year - 1, 4, 1)

    @staticmethod
    def get_inventory_valuation(company: Company) -> Decimal:
        products = Product.objects.filter(company=company, is_active=True, stock_quantity__gt=0)
        total_val = Decimal('0.00')
        for p in products:
            qty = Decimal(str(p.stock_quantity or '0.00'))
            cost = Decimal(str(p.purchase_price or '0.00'))
            total_val += (qty * cost)
        return total_val.quantize(Decimal('0.01'))

    @classmethod
    def generate_profit_and_loss(cls, company: Company, from_date=None, to_date=None) -> Dict[str, Any]:
        d_to = cls.parse_date(to_date) or datetime.date.today()
        d_from = cls.parse_date(from_date) or cls.get_fiscal_year_start(d_to)

        ledgers = Ledger.objects.filter(
            company=company,
            is_active=True
        ).select_related('group').order_by('group__name', 'name')

        direct_income_rows: List[Dict[str, Any]] = []
        direct_expense_rows: List[Dict[str, Any]] = []
        indirect_income_rows: List[Dict[str, Any]] = []
        indirect_expense_rows: List[Dict[str, Any]] = []

        total_direct_income = Decimal('0.00')
        total_direct_expense = Decimal('0.00')
        total_indirect_income = Decimal('0.00')
        total_indirect_expense = Decimal('0.00')

        stock_in_hand_ledger_val = Decimal('0.00')

        for ledger in ledgers:
            nature = (ledger.group.nature if ledger.group else '').upper()
            grp_name = (ledger.group.name if ledger.group else '').upper()
            l_name = ledger.name.upper()

            if 'STOCK' in grp_name or 'STOCK IN HAND' in l_name:
                bal_data = PeriodBalanceService.calculate_ledger_period_balance(ledger, d_from, d_to)
                stock_in_hand_ledger_val += Decimal(bal_data['closing_balance'])
                continue

            if nature not in ('INCOME', 'EXPENSE'):
                continue

            bal_data = PeriodBalanceService.calculate_ledger_period_balance(ledger, d_from, d_to)
            p_dr = Decimal(bal_data['period_debit'])
            p_cr = Decimal(bal_data['period_credit'])
            net_flow = abs(p_cr - p_dr)

            if p_dr == Decimal('0.00') and p_cr == Decimal('0.00'):
                continue

            row_item = {
                "ledger_id": str(ledger.id),
                "ledger_name": ledger.name,
                "group_name": ledger.group.name if ledger.group else "",
                "debit": str(p_dr),
                "credit": str(p_cr),
                "amount": str(net_flow)
            }

            if nature == 'INCOME':
                ledger_income = p_cr - p_dr
                row_item["amount"] = str(ledger_income)

                is_direct_income = (
                    'DIRECT' in grp_name or
                    'SALES' in grp_name or
                    'OPERATING' in grp_name or
                    ledger.ledger_type == 'SALES' or
                    ('INDIRECT' not in grp_name and 'OTHER' not in grp_name)
                )

                if is_direct_income:
                    direct_income_rows.append(row_item)
                    total_direct_income += ledger_income
                else:
                    indirect_income_rows.append(row_item)
                    total_indirect_income += ledger_income

            elif nature == 'EXPENSE':
                ledger_expense = p_dr - p_cr
                row_item["amount"] = str(ledger_expense)

                is_direct_expense = (
                    'DIRECT' in grp_name or
                    'PURCHASE' in grp_name or
                    'MANUFACTURING' in grp_name or
                    'CARRIAGE INWARD' in l_name or
                    'FREIGHT' in l_name or
                    'WAGES' in l_name or
                    ledger.ledger_type == 'PURCHASE'
                ) and 'INDIRECT' not in grp_name

                if is_direct_expense:
                    direct_expense_rows.append(row_item)
                    total_direct_expense += ledger_expense
                else:
                    indirect_expense_rows.append(row_item)
                    total_indirect_expense += ledger_expense

        closing_stock = stock_in_hand_ledger_val
        if closing_stock == Decimal('0.00'):
            closing_stock = cls.get_inventory_valuation(company)

        opening_stock = Decimal('0.00')
        gross_profit = (total_direct_income + closing_stock) - (opening_stock + total_direct_expense)
        net_profit = gross_profit + total_indirect_income - total_indirect_expense

        gp_percent = Decimal('0.00')
        np_percent = Decimal('0.00')
        if total_direct_income > Decimal('0.00'):
            gp_percent = ((gross_profit / total_direct_income) * 100).quantize(Decimal('0.01'))
            np_percent = ((net_profit / total_direct_income) * 100).quantize(Decimal('0.01'))

        return {
            "company_id": str(company.id),
            "company_name": company.name,
            "from_date": d_from.strftime('%Y-%m-%d'),
            "to_date": d_to.strftime('%Y-%m-%d'),
            "trading_account": {
                "direct_income": {
                    "rows": direct_income_rows,
                    "total": str(total_direct_income)
                },
                "direct_expense": {
                    "rows": direct_expense_rows,
                    "total": str(total_direct_expense)
                },
                "opening_stock": str(opening_stock),
                "closing_stock": str(closing_stock),
                "gross_profit": str(gross_profit),
                "is_gross_profit": gross_profit >= Decimal('0.00'),
                "gross_profit_percentage": float(gp_percent)
            },
            "profit_and_loss": {
                "gross_profit_brought_forward": str(gross_profit),
                "indirect_income": {
                    "rows": indirect_income_rows,
                    "total": str(total_indirect_income)
                },
                "indirect_expense": {
                    "rows": indirect_expense_rows,
                    "total": str(total_indirect_expense)
                },
                "net_profit": str(net_profit),
                "is_net_profit": net_profit >= Decimal('0.00'),
                "net_profit_percentage": float(np_percent)
            }
        }

    @classmethod
    def generate_balance_sheet(cls, company: Company, as_of_date=None) -> Dict[str, Any]:
        d_as_of = cls.parse_date(as_of_date) or datetime.date.today()
        fy_start = cls.get_fiscal_year_start(d_as_of)

        pl_data = cls.generate_profit_and_loss(company, from_date=fy_start, to_date=d_as_of)
        net_profit = Decimal(pl_data['profit_and_loss']['net_profit'])

        ledgers = Ledger.objects.filter(
            company=company,
            is_active=True
        ).select_related('group').order_by('group__nature', 'name')

        capital_rows: List[Dict[str, Any]] = []
        loan_liability_rows: List[Dict[str, Any]] = []
        current_liability_rows: List[Dict[str, Any]] = []

        fixed_asset_rows: List[Dict[str, Any]] = []
        current_asset_rows: List[Dict[str, Any]] = []
        bank_and_cash_rows: List[Dict[str, Any]] = []

        total_capital = Decimal('0.00')
        total_drawings = Decimal('0.00')
        total_loans = Decimal('0.00')
        total_current_liabilities = Decimal('0.00')

        total_fixed_assets = Decimal('0.00')
        total_current_assets = Decimal('0.00')
        total_bank_cash = Decimal('0.00')

        stock_in_hand_val = Decimal('0.00')

        for ledger in ledgers:
            nature = (ledger.group.nature if ledger.group else '').upper()
            grp_name = (ledger.group.name if ledger.group else '').upper()
            l_name = ledger.name.upper()

            if nature in ('INCOME', 'EXPENSE'):
                continue

            bal_data = PeriodBalanceService.calculate_ledger_period_balance(ledger, None, d_as_of)
            cl_bal = Decimal(bal_data['closing_balance'])
            cl_type = bal_data['closing_type']

            if cl_bal == Decimal('0.00'):
                continue

            row_item = {
                "ledger_id": str(ledger.id),
                "ledger_name": ledger.name,
                "group_name": ledger.group.name if ledger.group else "",
                "balance": str(cl_bal),
                "balance_type": cl_type
            }

            if nature in ('LIABILITY', 'EQUITY'):
                if 'CAPITAL' in grp_name or nature == 'EQUITY':
                    if 'DRAWING' in l_name:
                        total_drawings += cl_bal
                        row_item["is_drawing"] = True
                        capital_rows.append(row_item)
                    else:
                        total_capital += cl_bal
                        capital_rows.append(row_item)
                elif 'LOAN' in grp_name or 'BORROWING' in grp_name or 'OVERDRAFT' in grp_name or 'OD' in grp_name:
                    total_loans += cl_bal
                    loan_liability_rows.append(row_item)
                else:
                    total_current_liabilities += cl_bal
                    current_liability_rows.append(row_item)

            elif nature == 'ASSET':
                if 'STOCK' in grp_name or 'STOCK IN HAND' in l_name:
                    stock_in_hand_val += cl_bal
                    continue

                if 'FIXED' in grp_name or 'PLANT' in grp_name or 'FURNITURE' in grp_name or 'EQUIPMENT' in grp_name:
                    total_fixed_assets += cl_bal
                    fixed_asset_rows.append(row_item)
                elif 'BANK' in grp_name or 'CASH' in grp_name or ledger.ledger_type in ('BANK', 'CASH'):
                    total_bank_cash += cl_bal
                    bank_and_cash_rows.append(row_item)
                else:
                    total_current_assets += cl_bal
                    current_asset_rows.append(row_item)

        closing_stock = stock_in_hand_val
        if closing_stock == Decimal('0.00'):
            closing_stock = cls.get_inventory_valuation(company)

        if closing_stock > Decimal('0.00'):
            current_asset_rows.insert(0, {
                "ledger_id": "stock-valuation",
                "ledger_name": "Closing Stock (Inventory)",
                "group_name": "Stock-in-Hand",
                "balance": str(closing_stock),
                "balance_type": "DR"
            })
            total_current_assets += closing_stock

        effective_equity = total_capital + net_profit - total_drawings
        total_liabilities = effective_equity + total_loans + total_current_liabilities
        total_assets = total_fixed_assets + total_current_assets + total_bank_cash

        diff = (total_assets - total_liabilities).quantize(Decimal('0.01'))
        is_balanced = abs(diff) <= Decimal('0.05')

        liquid_assets = total_current_assets + total_bank_cash
        working_capital = liquid_assets - total_current_liabilities
        current_ratio = float((liquid_assets / total_current_liabilities).quantize(Decimal('0.01'))) if total_current_liabilities > Decimal('0.00') else 0.0

        return {
            "company_id": str(company.id),
            "company_name": company.name,
            "as_of_date": d_as_of.strftime('%Y-%m-%d'),
            "is_balanced": is_balanced,
            "difference": str(diff),
            "liabilities_and_equity": {
                "equity": {
                    "capital_rows": capital_rows,
                    "total_capital": str(total_capital),
                    "total_drawings": str(total_drawings),
                    "net_profit": str(net_profit),
                    "effective_equity": str(effective_equity)
                },
                "loans": {
                    "rows": loan_liability_rows,
                    "total": str(total_loans)
                },
                "current_liabilities": {
                    "rows": current_liability_rows,
                    "total": str(total_current_liabilities)
                },
                "total_liabilities": str(total_liabilities)
            },
            "assets": {
                "fixed_assets": {
                    "rows": fixed_asset_rows,
                    "total": str(total_fixed_assets)
                },
                "current_assets": {
                    "rows": current_asset_rows,
                    "total": str(total_current_assets)
                },
                "bank_and_cash": {
                    "rows": bank_and_cash_rows,
                    "total": str(total_bank_cash)
                },
                "total_assets": str(total_assets)
            },
            "kpis": {
                "working_capital": str(working_capital),
                "current_ratio": current_ratio,
                "net_worth": str(effective_equity)
            }
        }

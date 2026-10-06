import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum, Q

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService


class ConsolidatedFinancialsService:
    """
    Multi-Entity Consolidated Financials & Group MIS Engine.
    Aggregates financial statements across sister entities with:
    1. Automated elimination of inter-company sales and purchases.
    2. Automated elimination of inter-company receivables and payables.
    3. Group Liquid Cash & Bank compilation.
    4. Entity-wise comparison breakdown.
    """

    @classmethod
    def get_group_consolidated_report(
        cls,
        user,
        company_ids: Optional[List[str]] = None,
        as_of_date: Optional[datetime.date] = None
    ) -> Dict[str, Any]:
        # 1. Fetch authorized active companies for this user
        user_comps = Company.objects.filter(
            users__user=user,
            is_active=True
        ).distinct()

        if company_ids:
            user_comps = user_comps.filter(id__in=company_ids)

        companies = list(user_comps.order_by('name'))
        if not companies:
            return {
                "summary": {
                    "total_companies": 0,
                    "total_liquid_cash_and_bank": 0.0,
                    "gross_debtors": 0.0,
                    "net_consolidated_debtors": 0.0,
                    "gross_creditors": 0.0,
                    "net_consolidated_creditors": 0.0,
                    "gross_revenue": 0.0,
                    "net_consolidated_revenue": 0.0,
                    "total_eliminations": 0.0,
                },
                "entities": [],
                "eliminations": []
            }

        # Build group entity lookup
        group_gstins = {c.gstin.strip().upper() for c in companies if c.gstin}
        group_names = {c.name.strip().lower() for c in companies}
        company_id_map = {str(c.id): c for c in companies}

        entities_data = []
        total_cash_and_bank = Decimal('0.00')
        total_gross_debtors = Decimal('0.00')
        total_gross_creditors = Decimal('0.00')
        total_gross_revenue = Decimal('0.00')
        total_gross_expenses = Decimal('0.00')

        total_intercompany_receivables = Decimal('0.00')
        total_intercompany_payables = Decimal('0.00')
        total_intercompany_revenue = Decimal('0.00')

        eliminations_log = []

        date_voucher_q = Q(voucher_date__lte=as_of_date) if as_of_date else Q()
        date_entry_q = Q(voucher__voucher_date__lte=as_of_date) if as_of_date else Q()

        for comp in companies:
            # A. Liquid Cash & Bank
            cash_bank_ledgers = Ledger.objects.filter(
                company=comp,
                is_archived=False,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC', 'CASH']
            )
            comp_cash_bank = Decimal('0.00')
            for l in cash_bank_ledgers:
                # Calculate live balance
                dr_cr = LedgerEntry.objects.filter(
                    company=comp,
                    ledger=l,
                    voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
                ).filter(date_entry_q).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
                dr = Decimal(str(dr_cr['dr'] or '0.00')) + (l.opening_balance if l.opening_balance_type == 'DEBIT' else Decimal('0.00'))
                cr = Decimal(str(dr_cr['cr'] or '0.00')) + (l.opening_balance if l.opening_balance_type == 'CREDIT' else Decimal('0.00'))
                comp_cash_bank += (dr - cr)

            # B. Debtors (Receivables)
            debtor_ledgers = Ledger.objects.filter(
                company=comp,
                is_archived=False,
                ledger_type__in=['CUSTOMER', 'DEBTOR', 'BOTH']
            )
            comp_gross_debtors = Decimal('0.00')
            comp_ic_debtors = Decimal('0.00')

            for l in debtor_ledgers:
                dr_cr = LedgerEntry.objects.filter(
                    company=comp,
                    ledger=l,
                    voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
                ).filter(date_entry_q).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
                dr = Decimal(str(dr_cr['dr'] or '0.00')) + (l.opening_balance if l.opening_balance_type == 'DEBIT' else Decimal('0.00'))
                cr = Decimal(str(dr_cr['cr'] or '0.00')) + (l.opening_balance if l.opening_balance_type == 'CREDIT' else Decimal('0.00'))
                net = dr - cr
                if net > Decimal('0.00'):
                    comp_gross_debtors += net
                    # Check if this debtor is a sister company
                    is_sister = False
                    if l.gstin and l.gstin.strip().upper() in group_gstins and l.gstin.strip().upper() != (comp.gstin or '').strip().upper():
                        is_sister = True
                    elif any(s_name in l.name.lower() for s_name in group_names if s_name != comp.name.lower()):
                        is_sister = True

                    if is_sister:
                        comp_ic_debtors += net
                        eliminations_log.append({
                            "type": "INTER_COMPANY_RECEIVABLE",
                            "holding_company": comp.name,
                            "counterpart": l.name,
                            "amount": float(net),
                            "rationale": f"Owed by sister company '{l.name}' to '{comp.name}'. Eliminated from external trade receivables."
                        })

            # Check dedicated Inter-Company Current Accounts
            ic_ledgers = Ledger.objects.filter(
                company=comp,
                is_archived=False,
                ledger_type='INTER_COMPANY'
            )
            for l in ic_ledgers:
                dr_cr = LedgerEntry.objects.filter(
                    company=comp,
                    ledger=l,
                    voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
                ).filter(date_entry_q).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
                dr = Decimal(str(dr_cr['dr'] or '0.00'))
                cr = Decimal(str(dr_cr['cr'] or '0.00'))
                net = dr - cr
                if net > 0:
                    comp_ic_debtors += net
                    comp_gross_debtors += net
                    eliminations_log.append({
                        "type": "INTER_COMPANY_CURRENT_ASSET",
                        "holding_company": comp.name,
                        "counterpart": l.name,
                        "amount": float(net),
                        "rationale": f"Sister company current account balance in '{comp.name}'. Eliminated from consolidated balance sheet."
                    })

            # C. Creditors (Payables)
            creditor_ledgers = Ledger.objects.filter(
                company=comp,
                is_archived=False,
                ledger_type__in=['SUPPLIER', 'CREDITOR', 'BOTH']
            )
            comp_gross_creditors = Decimal('0.00')
            comp_ic_creditors = Decimal('0.00')

            for l in creditor_ledgers:
                dr_cr = LedgerEntry.objects.filter(
                    company=comp,
                    ledger=l,
                    voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
                ).filter(date_entry_q).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
                dr = Decimal(str(dr_cr['dr'] or '0.00')) + (l.opening_balance if l.opening_balance_type == 'DEBIT' else Decimal('0.00'))
                cr = Decimal(str(dr_cr['cr'] or '0.00')) + (l.opening_balance if l.opening_balance_type == 'CREDIT' else Decimal('0.00'))
                net = cr - dr
                if net > Decimal('0.00'):
                    comp_gross_creditors += net
                    is_sister = False
                    if l.gstin and l.gstin.strip().upper() in group_gstins and l.gstin.strip().upper() != (comp.gstin or '').strip().upper():
                        is_sister = True
                    elif any(s_name in l.name.lower() for s_name in group_names if s_name != comp.name.lower()):
                        is_sister = True

                    if is_sister:
                        comp_ic_creditors += net
                        eliminations_log.append({
                            "type": "INTER_COMPANY_PAYABLE",
                            "holding_company": comp.name,
                            "counterpart": l.name,
                            "amount": float(net),
                            "rationale": f"Owed to sister company '{l.name}' by '{comp.name}'. Eliminated from external trade payables."
                        })

            # D. Revenue & Turnover
            sales_vouchers = Voucher.objects.filter(
                company=comp,
                voucher_type__in=['SALES_INVOICE', 'INVOICE'],
                status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
            ).filter(date_voucher_q)

            comp_gross_revenue = Decimal(str(sales_vouchers.aggregate(tot=Sum('total_amount'))['tot'] or '0.00'))
            comp_ic_revenue = Decimal('0.00')

            # Identify sales to sister entities
            for vch in sales_vouchers.select_related('party_ledger'):
                party = vch.party_ledger
                if party:
                    if (party.gstin and party.gstin.strip().upper() in group_gstins and party.gstin.strip().upper() != (comp.gstin or '').strip().upper()) or \
                       any(s_name in party.name.lower() for s_name in group_names if s_name != comp.name.lower()):
                        comp_ic_revenue += vch.total_amount
                        eliminations_log.append({
                            "type": "INTER_COMPANY_TURNOVER",
                            "holding_company": comp.name,
                            "counterpart": party.name,
                            "amount": float(vch.total_amount),
                            "rationale": f"Sale #{vch.voucher_number} between '{comp.name}' and sister entity '{party.name}'. Eliminated from group turnover."
                        })

            # E. Expenses & Purchases
            expense_vouchers = Voucher.objects.filter(
                company=comp,
                voucher_type__in=['PURCHASE_INVOICE', 'PURCHASE', 'EXPENSE'],
                status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
            ).filter(date_voucher_q)
            comp_gross_expenses = Decimal(str(expense_vouchers.aggregate(tot=Sum('total_amount'))['tot'] or '0.00'))

            comp_net_profit = comp_gross_revenue - comp_gross_expenses

            # Update running totals
            total_cash_and_bank += comp_cash_bank
            total_gross_debtors += comp_gross_debtors
            total_gross_creditors += comp_gross_creditors
            total_gross_revenue += comp_gross_revenue
            total_gross_expenses += comp_gross_expenses

            total_intercompany_receivables += comp_ic_debtors
            total_intercompany_payables += comp_ic_creditors
            total_intercompany_revenue += comp_ic_revenue

            entities_data.append({
                "company_id": str(comp.id),
                "company_name": comp.name,
                "gstin": comp.gstin or "",
                "liquid_cash_and_bank": float(comp_cash_bank),
                "gross_debtors": float(comp_gross_debtors),
                "intercompany_debtors": float(comp_ic_debtors),
                "external_debtors": float(comp_gross_debtors - comp_ic_debtors),
                "gross_creditors": float(comp_gross_creditors),
                "intercompany_creditors": float(comp_ic_creditors),
                "external_creditors": float(comp_gross_creditors - comp_ic_creditors),
                "gross_revenue": float(comp_gross_revenue),
                "intercompany_revenue": float(comp_ic_revenue),
                "external_revenue": float(comp_gross_revenue - comp_ic_revenue),
                "gross_expenses": float(comp_gross_expenses),
                "net_profit": float(comp_net_profit),
            })

        net_consolidated_debtors = total_gross_debtors - total_intercompany_receivables
        net_consolidated_creditors = total_gross_creditors - total_intercompany_payables
        net_consolidated_revenue = total_gross_revenue - total_intercompany_revenue
        net_consolidated_profit = (total_gross_revenue - total_intercompany_revenue) - (total_gross_expenses - total_intercompany_revenue)

        return {
            "summary": {
                "total_companies": len(companies),
                "total_liquid_cash_and_bank": float(total_cash_and_bank),
                "gross_debtors": float(total_gross_debtors),
                "net_consolidated_debtors": float(max(Decimal('0.00'), net_consolidated_debtors)),
                "intercompany_debtors_eliminated": float(total_intercompany_receivables),
                "gross_creditors": float(total_gross_creditors),
                "net_consolidated_creditors": float(max(Decimal('0.00'), net_consolidated_creditors)),
                "intercompany_creditors_eliminated": float(total_intercompany_payables),
                "gross_revenue": float(total_gross_revenue),
                "net_consolidated_revenue": float(max(Decimal('0.00'), net_consolidated_revenue)),
                "intercompany_turnover_eliminated": float(total_intercompany_revenue),
                "gross_net_profit": float(total_gross_revenue - total_gross_expenses),
                "net_consolidated_profit": float(net_consolidated_profit),
                "as_of_date": str(as_of_date) if as_of_date else str(datetime.date.today()),
            },
            "entities": entities_data,
            "eliminations": eliminations_log,
        }

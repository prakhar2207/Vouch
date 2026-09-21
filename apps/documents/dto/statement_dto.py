from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.db.models import Sum

from apps.accounting.models import LedgerEntry, Voucher
from apps.accounting.services.party_balance_service import PartyBalanceService
from apps.companies.models import Company
from apps.ledgers.models import Ledger


def build_statement_dto(
    company: Company,
    ledger: Ledger,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Constructs the canonical Document DTO for Customer, Supplier, and Ledger Statements.
    Calculates opening balance, chronological transactions with running balance,
    and period closing balance without mutating any database state.
    """
    role = ledger.canonical_role
    normal_bal = ledger.normal_balance

    # 1. Opening Balance Calculation
    has_opening_entries = LedgerEntry.objects.filter(
        ledger=ledger,
        voucher__company=company,
        voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'],
        voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
    ).exists()

    pre_period_dr = Decimal('0.00')
    pre_period_cr = Decimal('0.00')

    if from_date:
        pre_agg = LedgerEntry.objects.filter(
            ledger=ledger,
            voucher__company=company,
            voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'],
            voucher__voucher_date__lt=from_date
        ).aggregate(
            dr=Sum('debit_amount'),
            cr=Sum('credit_amount')
        )
        pre_period_dr = Decimal(str(pre_agg['dr'] or '0.00'))
        pre_period_cr = Decimal(str(pre_agg['cr'] or '0.00'))

    initial_op = Decimal('0.00') if has_opening_entries else Decimal(str(ledger.opening_balance or '0.00'))
    if ledger.opening_balance_type == 'CREDIT':
        pre_period_cr += initial_op
    else:
        pre_period_dr += initial_op

    op_balance_info = PartyBalanceService.get_balance_from_components(
        role, pre_period_dr, pre_period_cr, normal_balance=normal_bal
    )
    op_amount = op_balance_info['display_amount']
    op_type = op_balance_info['balance_direction']

    # 2. Period Transactions Query
    entries_qs = LedgerEntry.objects.filter(
        ledger=ledger,
        voucher__company=company,
        voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']
    ).select_related('voucher')

    if from_date:
        entries_qs = entries_qs.filter(voucher__voucher_date__gte=from_date)
    if to_date:
        entries_qs = entries_qs.filter(voucher__voucher_date__lte=to_date)

    entries = list(entries_qs.order_by('voucher__voucher_date', 'created_at', 'id'))

    total_period_dr = Decimal('0.00')
    total_period_cr = Decimal('0.00')

    # Running balance starts at pre-period net
    running_dr = pre_period_dr
    running_cr = pre_period_cr

    dto_txs: List[Dict[str, Any]] = []

    for entry in entries:
        dr = entry.debit_amount
        cr = entry.credit_amount
        total_period_dr += dr
        total_period_cr += cr

        running_dr += dr
        running_cr += cr

        rb_info = PartyBalanceService.get_balance_from_components(
            role, running_dr, running_cr, normal_balance=normal_bal
        )

        v_date = entry.voucher.voucher_date
        v_date_str = v_date.strftime('%Y-%m-%d') if hasattr(v_date, 'strftime') else str(v_date)

        dto_txs.append({
            'date': v_date_str,
            'voucher_id': str(entry.voucher.id),
            'voucher_number': entry.voucher.voucher_number,
            'voucher_type': entry.voucher.get_voucher_type_display() if hasattr(entry.voucher, 'get_voucher_type_display') else entry.voucher.voucher_type,
            'narration': entry.narration or entry.voucher.narration or '',
            'debit': float(dr),
            'credit': float(cr),
            'running_balance': float(rb_info['display_amount']),
            'running_type': rb_info['balance_direction'],
        })

    # 3. Closing Balance
    total_cumulative_dr = pre_period_dr + total_period_dr
    total_cumulative_cr = pre_period_cr + total_period_cr

    cl_balance_info = PartyBalanceService.get_balance_from_components(
        role, total_cumulative_dr, total_cumulative_cr, normal_balance=normal_bal
    )
    closing_amount = cl_balance_info['display_amount']
    closing_type = cl_balance_info['balance_direction']
    semantic_state = cl_balance_info['balance_state']

    # Document type tag
    doc_type = 'CUSTOMER_STATEMENT' if role == 'DEBTOR' else ('SUPPLIER_STATEMENT' if role == 'CREDITOR' else 'LEDGER')

    return {
        'schema_version': '1.0',
        'document': {
            'document_type': doc_type,
            'title': f"{ledger.name} - Statement of Account",
            'from_date': str(from_date) if from_date else None,
            'to_date': str(to_date) if to_date else None,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'company': {
            'id': str(company.id),
            'name': company.name,
            'gstin': company.gstin or '',
            'address': company.address or '',
            'city': company.city or '',
            'state_code': company.state_code or '',
            'phone': company.phone or '',
            'email': company.email or '',
        },
        'party': {
            'id': str(ledger.id),
            'name': ledger.name,
            'gstin': ledger.gstin or '',
            'address': ledger.address or '',
            'phone': ledger.phone or '',
            'email': ledger.email or '',
            'group_name': ledger.group.name if ledger.group else '',
            'canonical_role': role,
        },
        'opening_balance': {
            'amount': float(op_amount),
            'type': op_type,
        },
        'transactions': dto_txs,
        'closing_balance': {
            'amount': float(closing_amount),
            'type': closing_type,
            'semantic_state': semantic_state,
        },
        'summary': {
            'total_debit': float(total_period_dr),
            'total_credit': float(total_period_cr),
            'net_movement': float(abs(total_period_dr - total_period_cr)),
            'transaction_count': len(dto_txs),
        }
    }

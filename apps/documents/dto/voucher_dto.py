from decimal import Decimal
from typing import Any, Dict, List

from apps.accounting.models import Voucher
from apps.accounting.services.invoice_pdf_service import number_to_words


def build_voucher_dto(voucher: Voucher) -> Dict[str, Any]:
    """
    Constructs the canonical Document DTO for Payment, Receipt, Contra, and Journal Vouchers.
    """
    company = voucher.company
    party = voucher.party_ledger

    if hasattr(voucher.voucher_date, 'strftime'):
        vch_date = voucher.voucher_date.strftime('%Y-%m-%d')
    else:
        vch_date = str(voucher.voucher_date or '')

    entries_qs = voucher.ledger_entries.all().select_related('ledger')
    dto_entries: List[Dict[str, Any]] = []
    tot_dr = Decimal('0.00')
    tot_cr = Decimal('0.00')

    for entry in entries_qs:
        dr = entry.debit_amount
        cr = entry.credit_amount
        tot_dr += dr
        tot_cr += cr
        dto_entries.append({
            'ledger_id': str(entry.ledger.id),
            'ledger_name': entry.ledger.name,
            'debit_amount': float(dr),
            'credit_amount': float(cr),
            'narration': entry.narration or '',
        })

    # If entries are empty (e.g. unposted draft or direct party voucher), fallback to party & total_amount
    primary_amount = voucher.total_amount or max(tot_dr, tot_cr)

    party_info = None
    if party:
        party_info = {
            'id': str(party.id),
            'name': party.name,
            'gstin': party.gstin or '',
            'address': party.address or '',
            'phone': party.phone or '',
            'email': party.email or '',
        }

    return {
        'schema_version': '1.0',
        'document': {
            'id': str(voucher.id),
            'voucher_type': voucher.voucher_type,
            'voucher_number': voucher.voucher_number,
            'voucher_date': vch_date,
            'reference_number': voucher.reference_number or '',
            'narration': voucher.narration or '',
            'status': voucher.status,
            'total_amount': float(primary_amount),
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
        'party': party_info,
        'entries': dto_entries,
        'totals': {
            'total_debit': float(tot_dr),
            'total_credit': float(tot_cr),
            'net_amount': float(primary_amount),
        },
        'amount_in_words': number_to_words(primary_amount),
    }

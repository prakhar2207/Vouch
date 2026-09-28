"""
Canonical Document DTO Builder for Proforma Invoices and Quotations.
Mirrors the invoice_dto structure so InvoicePDFRenderer can render it,
and the public share page can display it.
"""
import urllib.parse
from decimal import Decimal
from typing import Any, Dict, List

from apps.accounting.services.invoice_pdf_service import number_to_words


def build_proforma_dto(proforma) -> Dict[str, Any]:
    """
    Constructs the canonical Document DTO for a ProformaInvoice.
    Mirrors the build_invoice_dto() structure for rendering compatibility.
    """
    company = proforma.company
    party = proforma.party_ledger

    # Dates
    inv_date = proforma.date.strftime('%Y-%m-%d') if proforma.date else ''
    valid_until = proforma.valid_until.strftime('%Y-%m-%d') if proforma.valid_until else None

    # Buyer info
    buyer_name = proforma.buyer_name or (party.name if party else 'Customer')
    buyer_addr = proforma.buyer_address or (getattr(party, 'address', '') or '' if party else '')
    buyer_gstin = proforma.buyer_gstin or (getattr(party, 'gstin', '') or '' if party else '') or 'Unregistered'
    buyer_state = proforma.buyer_state_code or (getattr(party, 'state_code', '') or '' if party else '')
    buyer_phone = proforma.buyer_phone or (getattr(party, 'phone', '') or '' if party else '')
    buyer_email = proforma.buyer_email or (getattr(party, 'email', '') or '' if party else '')

    # Company / seller info
    comp_state = company.state_name or company.state_code or ''
    pos = f"{comp_state} ({company.state_code})" if company.state_code else (comp_state or 'N/A')

    sig_url = getattr(company, 'signature_data', None) or ''
    if not sig_url and getattr(company, 'proprietor_signature', None):
        try:
            sig_url = company.proprietor_signature.url
        except Exception:
            sig_url = ''

    logo_url = getattr(company, 'logo_data', None) or ''
    if not logo_url and getattr(company, 'logo', None):
        try:
            logo_url = company.logo.url
        except Exception:
            logo_url = ''

    # Inter-state
    is_inter_state = False
    if company.state_code and buyer_state:
        is_inter_state = str(company.state_code) != str(buyer_state)

    # Line items
    items = list(proforma.items.all())
    tot_qty = Decimal('0.00')
    tot_taxable = Decimal('0.00')
    tot_cgst = Decimal('0.00')
    tot_sgst = Decimal('0.00')
    tot_igst = Decimal('0.00')

    dto_items: List[Dict[str, Any]] = []

    for idx, itm in enumerate(items, start=1):
        tot_qty += itm.quantity
        tot_taxable += itm.taxable_amount
        tot_cgst += itm.cgst_amount
        tot_sgst += itm.sgst_amount
        tot_igst += itm.igst_amount

        dto_items.append({
            'sn': idx,
            'name': itm.item_name,
            'hsn_code': itm.hsn_code or '',
            'quantity': float(itm.quantity),
            'unit': itm.unit or 'PCS',
            'rate': float(itm.rate),
            'discount_percent': float(itm.discount_percent),
            'taxable_amount': float(itm.taxable_amount),
            'gst_rate': float(itm.gst_rate),
            'cgst_rate': float(itm.cgst_rate),
            'cgst_amount': float(itm.cgst_amount),
            'sgst_rate': float(itm.sgst_rate),
            'sgst_amount': float(itm.sgst_amount),
            'igst_rate': float(itm.igst_rate),
            'igst_amount': float(itm.igst_amount),
            'total_amount': float(itm.total_amount),
        })

    tot_tax = tot_cgst + tot_sgst + tot_igst
    total_amount = float(proforma.total_amount or Decimal('0.00'))
    round_off = float(proforma.round_off or Decimal('0.00'))

    # UPI QR
    upi_id = getattr(company, 'upi_id', '') or ''
    upi_url = ''
    if upi_id:
        upi_url = (
            f"upi://pay?pa={urllib.parse.quote(upi_id)}"
            f"&pn={urllib.parse.quote(company.legal_name or company.name or 'Merchant')}"
            f"&am={total_amount:.2f}"
            f"&tn={urllib.parse.quote(proforma.proforma_number)}"
            f"&cu=INR"
        )

    doc_type_label = 'PROFORMA INVOICE' if proforma.proforma_type == 'PROFORMA' else 'QUOTATION'

    return {
        'document_type': 'PROFORMA_INVOICE',
        'proforma_type': proforma.proforma_type,
        'document_type_label': doc_type_label,
        'seller': {
            'name': company.legal_name or company.name,
            'gstin': company.gstin or 'Unregistered',
            'address': getattr(company, 'address', '') or '',
            'city': getattr(company, 'city', '') or '',
            'pincode': getattr(company, 'pincode', '') or '',
            'state': comp_state,
            'state_code': company.state_code or '',
            'phone': getattr(company, 'phone', '') or '',
            'email': getattr(company, 'email', '') or '',
            'pan': getattr(company, 'pan', '') or '',
            'logo_url': logo_url,
            'signature_url': sig_url,
            'tagline': getattr(company, 'tagline', '') or '',
            'proprietor_name': getattr(company, 'proprietor_name', '') or '',
            'bank': {
                'bank_name': getattr(company, 'bank_name', '') or '',
                'account_number': getattr(company, 'bank_account_number', '') or '',
                'ifsc': getattr(company, 'bank_ifsc', '') or '',
                'branch': getattr(company, 'bank_branch', '') or '',
                'upi_id': upi_id,
                'upi_url': upi_url,
            },
        },
        'buyer': {
            'name': buyer_name,
            'address': buyer_addr,
            'gstin': buyer_gstin,
            'state_code': buyer_state,
            'phone': buyer_phone,
            'email': buyer_email,
        },
        'document': {
            'document_type': doc_type_label,
            'document_number': proforma.proforma_number,
            'document_date': inv_date,
            'valid_until': valid_until,
            'place_of_supply': pos,
            'is_inter_state': is_inter_state,
            'narration': proforma.customer_notes or '',
            'terms_and_conditions': proforma.terms_and_conditions or '',
        },
        'items': dto_items,
        'subtotals': {
            'total_quantity': float(tot_qty),
            'taxable_amount': float(tot_taxable),
            'cgst_amount': float(tot_cgst),
            'sgst_amount': float(tot_sgst),
            'igst_amount': float(tot_igst),
            'total_tax': float(tot_tax),
            'cartage_amount': float(proforma.cartage_amount or Decimal('0.00')),
            'round_off': round_off,
            'grand_total': total_amount,
        },
        'amount_in_words': number_to_words(Decimal(str(total_amount))),
        'is_proforma': True,
    }

import urllib.parse
from decimal import Decimal
from typing import Any, Dict, List

from apps.accounting.models import Voucher
from apps.accounting.services.invoice_pdf_service import number_to_words


def build_invoice_dto(voucher: Voucher) -> Dict[str, Any]:
    """
    Constructs the canonical, immutable Document DTO for a Sales or Purchase Invoice,
    Credit Note, or Debit Note from a Voucher instance.
    All Decimal values are serialized to float or string for clean JSON compatibility.
    """
    company = voucher.company
    party = voucher.party_ledger

    # Document Dates and References
    if hasattr(voucher.voucher_date, 'strftime'):
        inv_date = voucher.voucher_date.strftime('%Y-%m-%d')
    else:
        inv_date = str(voucher.voucher_date or '')

    due_date = str(voucher.due_date) if voucher.due_date else None

    # Place of supply & transport
    comp_state = company.state_name or company.state_code or ''
    pos = f"{comp_state} ({company.state_code})" if company.state_code else (comp_state or 'N/A')

    ewb_rec = getattr(voucher, 'eway_bill', None) or getattr(voucher, 'ewaybillrecord', None)
    gr_rr = getattr(ewb_rec, 'trans_doc_no', 'N/A') or 'N/A'
    transport = getattr(ewb_rec, 'transporter_name', '') or getattr(ewb_rec, 'trans_mode_display', 'Road') or 'Road'
    vehicle_no = getattr(ewb_rec, 'vehicle_no', 'N/A') or 'N/A'
    ewb_no = getattr(ewb_rec, 'eway_bill_number', 'N/A') or 'N/A'

    # Buyer & Party info
    buyer_name = voucher.buyer_name or (party.name if party else 'Customer')
    buyer_addr = voucher.buyer_address or (party.address if party and party.address else '')
    buyer_gstin = voucher.buyer_gstin or (party.gstin if party and party.gstin else 'Unregistered')
    buyer_state = voucher.buyer_state_code or (party.state_code if party and party.state_code else '')
    buyer_phone = voucher.buyer_phone or (party.phone if party and party.phone else '')
    buyer_email = voucher.buyer_email or (party.email if party and party.email else '')

    # Inter-state check
    is_inter_state = False
    if company.state_code and buyer_state:
        is_inter_state = str(company.state_code) != str(buyer_state)

    # Line items & taxes
    items = list(voucher.items.all().select_related('product'))
    tot_qty = Decimal('0.00')
    tot_taxable = Decimal('0.00')
    tot_cgst = Decimal('0.00')
    tot_sgst = Decimal('0.00')
    tot_igst = Decimal('0.00')

    dto_items: List[Dict[str, Any]] = []
    unit_label = 'PCS'

    for idx, itm in enumerate(items, start=1):
        p_name = itm.product.name if itm.product else (getattr(itm, 'description', '') or 'Item')
        hsn = itm.hsn_code or (itm.product.hsn_code if itm.product else '')
        unit = itm.product.unit if itm.product else getattr(itm, 'unit', 'PCS')
        if unit:
            unit_label = unit

        qty = itm.quantity
        rate = getattr(itm, 'rate', getattr(itm, 'unit_price', Decimal('0.00')))
        disc_pct = getattr(itm, 'discount_percent', getattr(itm, 'discount_percentage', Decimal('0.00')))
        taxable = itm.taxable_amount
        tax_amt = itm.total_amount - itm.taxable_amount

        tot_qty += qty
        tot_taxable += taxable

        if is_inter_state:
            itm_cgst = Decimal('0.00')
            itm_sgst = Decimal('0.00')
            itm_igst = tax_amt
            tot_igst += tax_amt
        else:
            half = (tax_amt / Decimal('2')).quantize(Decimal('0.01'))
            itm_cgst = half
            itm_sgst = half
            itm_igst = Decimal('0.00')
            tot_cgst += half
            tot_sgst += half

        dto_items.append({
            'sn': idx,
            'product_id': str(itm.product.id) if itm.product else None,
            'name': p_name,
            'hsn_code': str(hsn or ''),
            'quantity': float(qty),
            'unit': str(unit or 'PCS'),
            'rate': float(rate),
            'discount_percent': float(disc_pct),
            'taxable_amount': float(taxable),
            'gst_rate': float(itm.gst_rate),
            'cgst_amount': float(itm_cgst),
            'sgst_amount': float(itm_sgst),
            'igst_amount': float(itm_igst),
            'total_amount': float(itm.total_amount),
        })

    cartage = getattr(voucher, 'cartage_amount', Decimal('0.00')) or Decimal('0.00')
    subtotal_with_taxes = tot_taxable + (tot_igst if is_inter_state else (tot_cgst + tot_sgst)) + cartage

    final_grand_total = voucher.total_amount
    round_off = (final_grand_total - subtotal_with_taxes).quantize(Decimal('0.01'))

    int_part = Decimal(int(subtotal_with_taxes))
    dec_part = subtotal_with_taxes - int_part
    if abs(round_off) < Decimal('0.005') and dec_part > Decimal('0.00'):
        final_grand_total = int_part if dec_part < Decimal('0.5') else int_part + Decimal('1.00')
        round_off = (final_grand_total - subtotal_with_taxes).quantize(Decimal('0.01'))

    # Tax rate breakdown
    tax_rates = sorted(list(set(itm.gst_rate for itm in items))) if items else [Decimal('18.00')]
    tax_breakdown: List[Dict[str, Any]] = []

    for r in tax_rates:
        rate_items = [i for i in items if i.gst_rate == r]
        r_taxable = sum(i.taxable_amount for i in rate_items)
        r_tax = sum(i.total_amount - i.taxable_amount for i in rate_items)
        if is_inter_state:
            tax_breakdown.append({
                'rate': float(r),
                'taxable_amount': float(r_taxable),
                'cgst_amount': 0.0,
                'sgst_amount': 0.0,
                'igst_amount': float(r_tax),
                'total_tax': float(r_tax),
            })
        else:
            r_cgst = (r_tax / Decimal('2')).quantize(Decimal('0.01'))
            r_sgst = (r_tax / Decimal('2')).quantize(Decimal('0.01'))
            tax_breakdown.append({
                'rate': float(r),
                'taxable_amount': float(r_taxable),
                'cgst_amount': float(r_cgst),
                'sgst_amount': float(r_sgst),
                'igst_amount': 0.0,
                'total_tax': float(r_cgst + r_sgst),
            })

    # Bank details defaults
    b_name = company.bank_name or 'Canara Bank Govind Nagar'
    b_branch = company.bank_branch or ''
    b_acc = company.bank_account_number or '125008094288'
    b_ifsc = company.bank_ifsc or 'CNRB0003827'

    # UPI URL
    phone_val = getattr(company, 'phone', '')
    upi_id = getattr(company, 'bank_upi_id', None) or (f"{phone_val}@upi" if phone_val else "vouch@upi")
    upi_url = (
        f"upi://pay?pa={upi_id}"
        f"&pn={urllib.parse.quote(company.name)}"
        f"&am={float(final_grand_total):.2f}"
        f"&cu=INR"
        f"&tn={urllib.parse.quote(f'Inv {voucher.voucher_number}')}"
    )

    sig_url = None
    sig_field = getattr(company, 'proprietor_signature', None)
    if sig_field and hasattr(sig_field, 'url'):
        sig_url = sig_field.url

    return {
        'schema_version': '1.0',
        'document': {
            'id': str(voucher.id),
            'voucher_type': voucher.voucher_type,
            'document_number': voucher.voucher_number,
            'document_date': inv_date,
            'due_date': due_date,
            'reference_number': voucher.reference_number or '',
            'place_of_supply': pos,
            'reverse_charge': 'N',
            'eway_bill_no': ewb_no,
            'gr_rr_no': gr_rr,
            'transport': transport,
            'vehicle_no': vehicle_no,
            'narration': voucher.narration or '',
        },
        'seller': {
            'id': str(company.id),
            'name': company.name,
            'legal_name': company.legal_name or company.name,
            'gstin': company.gstin or 'Unregistered',
            'pan': company.pan or '',
            'address': company.address or '',
            'city': company.city or 'Kanpur',
            'pincode': company.pincode or '',
            'state_code': company.state_code or '',
            'state_name': company.state_name or '',
            'phone': company.phone or '',
            'email': company.email or '',
            'tagline': company.tagline or '',
            'bank_name': b_name,
            'bank_branch': b_branch,
            'bank_account_number': b_acc,
            'bank_ifsc': b_ifsc,
            'bank_upi_id': upi_id,
            'proprietor_name': company.proprietor_name or '',
            'signature_url': sig_url,
        },
        'buyer': {
            'party_ledger_id': str(party.id) if party else None,
            'name': buyer_name,
            'gstin': buyer_gstin,
            'address': buyer_addr,
            'state_code': buyer_state,
            'phone': buyer_phone,
            'email': buyer_email,
        },
        'items': dto_items,
        'subtotals': {
            'total_quantity': float(tot_qty),
            'unit_label': unit_label,
            'total_taxable': float(tot_taxable),
            'total_cgst': float(tot_cgst),
            'total_sgst': float(tot_sgst),
            'total_igst': float(tot_igst),
            'total_tax': float(tot_igst if is_inter_state else (tot_cgst + tot_sgst)),
            'cartage': float(cartage),
            'round_off': float(round_off),
            'grand_total': float(final_grand_total),
            'is_inter_state': is_inter_state,
        },
        'tax_breakdown': tax_breakdown,
        'amount_in_words': number_to_words(final_grand_total),
        'upi_url': upi_url,
        'terms': [
            "Goods once sold will not be taken back.",
            "Interest @ 18% p.a. will be charged if the payment is not made within 45 days.",
            f"Subject to '{company.city or 'Kanpur'}' Jurisdiction only."
        ]
    }

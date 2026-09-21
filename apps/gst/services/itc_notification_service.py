import urllib.parse
from decimal import Decimal
from typing import Dict, Any
from apps.accounting.models import Voucher
from apps.companies.models import Company


class ITCNotificationService:
    """
    Generates professional, compliance-backed WhatsApp and Email payment notices
    for suppliers whose invoices have not been filed in GSTR-1 (Missing in GSTR-2B)
    or have value/tax rate discrepancies.
    """

    @classmethod
    def generate_whatsapp_filing_notice(cls, voucher: Voucher, buyer_company: Company) -> Dict[str, Any]:
        """
        Creates WhatsApp markdown notice and direct click-to-chat URL.
        """
        supplier_name = (
            voucher.party_ledger.name if voucher.party_ledger else (voucher.buyer_name or 'Accounts Team')
        )
        supplier_phone = ''
        if voucher.party_ledger and voucher.party_ledger.phone:
            supplier_phone = str(voucher.party_ledger.phone).strip()
        elif voucher.buyer_phone:
            supplier_phone = str(voucher.buyer_phone).strip()

        # Sanitize phone: strip spaces, dashes, +, prefix 91 if 10 digits
        clean_phone = ''.join(filter(str.isdigit, supplier_phone))
        if len(clean_phone) == 10:
            clean_phone = '91' + clean_phone

        invoice_no = voucher.external_invoice_number or voucher.reference_number or voucher.voucher_number
        invoice_date = voucher.voucher_date.strftime('%d-%b-%Y') if voucher.voucher_date else 'Recent'
        total_val = f"{voucher.total_amount:,.2f}"

        # Calculate GST amount
        items = voucher.items.all()
        tax_amount = sum((i.cgst_amount + i.sgst_amount + i.igst_amount) for i in items)
        held_amount = voucher.itc_held_amount if voucher.itc_held_amount > 0 else tax_amount
        held_val = f"{held_amount:,.2f}"

        buyer_name = buyer_company.name
        buyer_gstin = buyer_company.gstin or 'Registered Buyer'

        is_mismatch = (voucher.itc_match_status == 'MISMATCHED')

        if is_mismatch:
            message = (
                f"🚨 *GST Discrepancy Notice & Payment Hold*\n\n"
                f"Dear Accounts Team at *{supplier_name}*,\n\n"
                f"We noticed a tax / value discrepancy between your invoice and our purchase books:\n"
                f"• *Invoice Number:* {invoice_no}\n"
                f"• *Invoice Date:* {invoice_date}\n"
                f"• *Invoice Value:* ₹{total_val}\n"
                f"• *Discrepancy:* {voucher.itc_notes or 'Taxable or GST rate mismatch'}\n\n"
                f"⚠️ *Status: A payment hold of ₹{held_val} is active on this invoice.*\n"
                f"Under Section 16(2)(aa) of the CGST Act, our ITC claim is restricted until this is amended in GSTR-1.\n\n"
                f"Please review and amend this invoice in your upcoming GSTR-1 or issue an amendment/credit note so we can release your pending balance.\n\n"
                f"Warm Regards,\n"
                f"*Accounts Department*\n"
                f"{buyer_name}\n"
                f"GSTIN: {buyer_gstin}"
            )
        else:
            message = (
                f"⚠️ *URGENT: GST Filing Notice & Payment Hold*\n\n"
                f"Dear Accounts Team at *{supplier_name}*,\n\n"
                f"Our purchase invoice from you is currently *NOT reflecting in GSTR-2B*:\n"
                f"• *Invoice Number:* {invoice_no}\n"
                f"• *Invoice Date:* {invoice_date}\n"
                f"• *Invoice Value:* ₹{total_val}\n"
                f"• *Pending GST ITC:* ₹{held_val}\n\n"
                f"As per Section 16(2)(aa) of the CGST Act, Input Tax Credit cannot be claimed unless the bill is visible in our auto-drafted GSTR-2B.\n\n"
                f"🛡️ *Action Taken:* To safeguard tax compliance, the GST portion of *₹{held_val}* has been placed on *HOLD* until filed in your next GSTR-1.\n\n"
                f"Kindly ensure this invoice is uploaded in your GSTR-1 filing before the monthly cut-off date. Once it reflects in our GSTR-2B, your held payment will be released immediately.\n\n"
                f"Thank you for your prompt cooperation,\n"
                f"*Accounts Department*\n"
                f"{buyer_name}\n"
                f"GSTIN: {buyer_gstin}"
            )

        encoded_message = urllib.parse.quote(message)
        wa_url = f"https://wa.me/{clean_phone}?text={encoded_message}" if clean_phone else f"https://wa.me/?text={encoded_message}"

        return {
            'supplier_name': supplier_name,
            'supplier_phone': clean_phone,
            'invoice_number': invoice_no,
            'invoice_date': invoice_date,
            'total_amount': float(voucher.total_amount),
            'held_amount': float(held_amount),
            'message_text': message,
            'whatsapp_url': wa_url,
            'match_status': voucher.itc_match_status
        }

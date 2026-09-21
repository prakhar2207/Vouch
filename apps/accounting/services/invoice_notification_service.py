import logging
import threading
import urllib.parse
from decimal import Decimal
from typing import Dict, Any, Optional

from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone

from apps.accounting.models import Voucher
from apps.accounting.services.invoice_pdf_service import InvoicePDFService

logger = logging.getLogger(__name__)

CLAIM_TOKEN_SALT = 'vouch-invoice-claim-v1'


class InvoiceNotificationService:
    """
    Automates asynchronous dispatch of Tax Invoices via Email (with PDF attachment)
    and WhatsApp, embedding a secure viral onboarding token (/claim) that allows
    counterparties to sign up on Vouch and import the bill directly into their books.
    """

    @classmethod
    def generate_claim_token(cls, voucher: Voucher) -> str:
        """Generates a tamper-proof cryptographic token encoding invoice details."""
        party = voucher.party_ledger
        v_date = voucher.voucher_date
        v_date_str = v_date.isoformat() if hasattr(v_date, 'isoformat') else str(v_date or '')
        payload = {
            'voucher_id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'seller_company_id': str(voucher.company.id),
            'seller_name': voucher.company.name,
            'seller_gstin': voucher.company.gstin or '',
            'buyer_name': voucher.buyer_name or (party.name if party else ''),
            'buyer_gstin': voucher.buyer_gstin or (party.gstin if party else ''),
            'buyer_phone': voucher.buyer_phone or (str(party.phone) if party and party.phone else ''),
            'buyer_email': voucher.buyer_email or (party.email if party and party.email else ''),
            'total_amount': float(voucher.total_amount),
            'voucher_date': v_date_str,
            'created_at': timezone.now().timestamp(),
        }

        return signing.dumps(payload, salt=CLAIM_TOKEN_SALT)

    @classmethod
    def verify_claim_token(cls, token: str) -> Dict[str, Any]:
        """
        Verifies and decodes the claim token.
        Token is valid for 30 days.
        """
        try:
            return signing.loads(token, salt=CLAIM_TOKEN_SALT, max_age=60 * 60 * 24 * 30)
        except signing.BadSignature:
            raise ValueError("Invalid or tampered invoice claim link.")
        except signing.SignatureExpired:
            raise ValueError("This invoice claim link has expired (validity: 30 days).")

    @classmethod
    def get_claim_url(cls, voucher: Voucher, frontend_url: Optional[str] = None) -> str:
        """Constructs the full viral claim URL for this voucher."""
        token = cls.generate_claim_token(voucher)
        if not frontend_url:
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://vouch-pi-one.vercel.app' if not getattr(settings, 'DEBUG', False) else 'http://localhost:3000')
        frontend_url = str(frontend_url).rstrip('/')
        return f"{frontend_url}/claim?token={token}"

    @classmethod
    def generate_whatsapp_share_payload(cls, voucher: Voucher, frontend_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates the WhatsApp text message and direct wa.me link for sharing
        the invoice and claim link with the buyer.
        """
        party = voucher.party_ledger
        buyer_phone = voucher.buyer_phone or (str(party.phone) if party and party.phone else '')
        clean_phone = ''.join(filter(str.isdigit, buyer_phone))
        if len(clean_phone) == 10:
            clean_phone = '91' + clean_phone

        claim_url = cls.get_claim_url(voucher, frontend_url=frontend_url)
        company_name = voucher.company.name
        buyer_name = voucher.buyer_name or (party.name if party else 'Customer')
        inv_no = voucher.voucher_number
        if hasattr(voucher.voucher_date, 'strftime'):
            inv_date = voucher.voucher_date.strftime('%d-%b-%Y')
        else:
            inv_date = str(voucher.voucher_date or 'Today')
        amount_str = f"₹{voucher.total_amount:,.2f}"

        message = (
            f"📄 *TAX INVOICE #{inv_no}*\n\n"
            f"Dear *{buyer_name}*,\n\n"
            f"Here is your tax invoice from *{company_name}*:\n"
            f"• *Invoice Number:* {inv_no}\n"
            f"• *Invoice Date:* {inv_date}\n"
            f"• *Invoice Amount:* {amount_str}\n\n"
            f"📥 *View & Download Official PDF:*\n"
            f"{claim_url}\n\n"
            f"🚀 *Instant 1-Click Import into Books:*\n"
            f"{claim_url}\n\n"
            f"_Open the link above to view/download your official PDF invoice and add this purchase into your accounts with zero manual data entry._\n\n"
            f"Thank you for doing business with us!\n"
            f"*{company_name}*"
        )

        encoded = urllib.parse.quote(message)
        wa_url = f"https://wa.me/{clean_phone}?text={encoded}" if clean_phone else f"https://wa.me/?text={encoded}"

        return {
            'buyer_phone': clean_phone,
            'buyer_name': buyer_name,
            'invoice_number': inv_no,
            'total_amount': float(voucher.total_amount),
            'claim_url': claim_url,
            'message_text': message,
            'whatsapp_url': wa_url
        }

    @classmethod
    def send_invoice_email(cls, voucher: Voucher, pdf_bytes: Optional[bytes] = None) -> bool:
        """
        Sends branded HTML email with the Tax Invoice PDF attached.
        """
        party = voucher.party_ledger
        recipient_email = voucher.buyer_email or (party.email if party and party.email else '')
        if not recipient_email:
            logger.info(f"Skipping email dispatch for {voucher.voucher_number}: No recipient email found.")
            return False

        if not pdf_bytes:
            pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)

        company = voucher.company
        claim_url = cls.get_claim_url(voucher)
        inv_no = voucher.voucher_number
        if hasattr(voucher.voucher_date, 'strftime'):
            inv_date = voucher.voucher_date.strftime('%d-%b-%Y')
        else:
            inv_date = str(voucher.voucher_date or 'Today')
        amount_str = f"₹{voucher.total_amount:,.2f}"

        buyer_name = voucher.buyer_name or (party.name if party else 'Valued Customer')

        subject = f"Tax Invoice {inv_no} from {company.name} [{amount_str}]"
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'billing@vouchapp.in')

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #1e293b; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; }}
                .header {{ background: linear-gradient(135deg, #1e40af, #2563eb); padding: 32px 24px; text-align: center; color: #ffffff; }}
                .header h1 {{ margin: 0 0 6px 0; font-size: 24px; font-weight: 700; }}
                .content {{ padding: 32px 24px; }}
                .card {{ background: #f1f5f9; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #cbd5e1; }}
                .card-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }}
                .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; margin-top: 16px; text-align: center; }}
                .footer {{ background: #f8fafc; padding: 20px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{company.name}</h1>
                    <p style="margin: 0; opacity: 0.9; font-size: 14px;">Tax Invoice #{inv_no}</p>
                </div>
                <div class="content">
                    <p>Dear <strong>{buyer_name}</strong>,</p>
                    <p>Thank you for your business. Please find attached your official Tax Invoice for recent purchases.</p>
                    
                    <div class="card">
                        <div style="font-size: 13px; color: #475569; margin-bottom: 6px;">INVOICE SUMMARY</div>
                        <div style="font-size: 26px; font-weight: 800; color: #0f172a; margin-bottom: 12px;">{amount_str}</div>
                        <div><strong>Invoice Number:</strong> {inv_no}</div>
                        <div><strong>Invoice Date:</strong> {inv_date}</div>
                        <div><strong>GSTIN:</strong> {company.gstin or 'URP'}</div>
                    </div>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{claim_url}" class="btn">⚡ 1-Click Import into Your Books</a>
                        <p style="font-size: 12px; color: #64748b; margin-top: 8px;">
                            Avoid manual data entry. Claim this bill directly into your accounting software.
                        </p>
                    </div>

                    <p style="font-size: 13px; color: #64748b;">
                        The PDF copy of your Tax Invoice is also attached to this email for your records.
                    </p>
                </div>
                <div class="footer">
                    Sent securely via <strong>Vouch Connected Invoicing Network</strong><br/>
                    {company.name} &bull; {company.email or ''}
                </div>
            </div>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Dear {buyer_name},\n\nPlease find attached Tax Invoice #{inv_no} for {amount_str} from {company.name}.\n\nImport into your books: {claim_url}",
            from_email=from_email,
            to=[recipient_email]
        )
        msg.attach_alternative(html_content, "text/html")
        sanitized_filename = f"Invoice_{inv_no.replace('/', '_').replace('-', '_')}.pdf"
        msg.attach(sanitized_filename, pdf_bytes, 'application/pdf')

        try:
            msg.send(fail_silently=True)
            logger.info(f"Dispatched invoice email for {inv_no} to {recipient_email}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send invoice email for {inv_no}: {e}")
            return False

    @classmethod
    def dispatch_invoice_on_post(cls, voucher: Voucher, async_mode: bool = True):
        """
        Dispatches invoice PDF via email and generates sharing payloads.
        Executes in background thread by default to guarantee sub-second voucher posting.
        """
        def _dispatch():
            try:
                pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)
                cls.send_invoice_email(voucher, pdf_bytes=pdf_bytes)
            except Exception as e:
                logger.exception(f"Background dispatch failed for voucher {voucher.voucher_number}: {e}")

        if async_mode:
            thread = threading.Thread(target=_dispatch, daemon=True)
            thread.start()
        else:
            _dispatch()

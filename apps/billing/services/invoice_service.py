import io
import os
import logging
from decimal import Decimal
from typing import Optional, Tuple
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from apps.billing.models import BillingInvoice, Subscription, PaymentTransaction

logger = logging.getLogger(__name__)


class InvoiceService:
    """
    Generates subscription billing tax invoices and PDF receipts for SaaS purchases.
    """

    @classmethod
    def generate_invoice_number(cls) -> str:
        """
        Generates sequentially increasing invoice number: SL-INV-{YYYY}{MM}-{seq:04d}
        """
        now = timezone.now()
        prefix = f"SL-INV-{now.year}{now.month:02d}-"
        last_invoice = BillingInvoice.objects.filter(
            invoice_number__startswith=prefix
        ).order_by('-invoice_number').first()

        if last_invoice:
            try:
                last_seq = int(last_invoice.invoice_number.split('-')[-1])
                seq = last_seq + 1
            except Exception:
                seq = 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"

    @classmethod
    def create_invoice_for_transaction(
        cls,
        transaction_obj: PaymentTransaction,
        subscription_obj: Optional[Subscription] = None
    ) -> BillingInvoice:
        """
        Creates a BillingInvoice record and generates its PDF.
        """
        with transaction.atomic():
            company = transaction_obj.company
            user = transaction_obj.user
            sub = subscription_obj or transaction_obj.subscription
            plan = sub.plan if sub else None

            plan_name = plan.name if plan else "SriLekh Subscription"
            plan_desc = plan.description if plan else "SriLekh Cloud Accounting Subscription"
            period_start = sub.current_period_start.date() if sub else timezone.localdate()
            period_end = sub.current_period_end.date() if sub else timezone.localdate()

            # Base taxable amount vs 18% GST split
            total_paise = transaction_obj.amount_paise
            taxable_paise = plan.base_amount_paise if plan else int(round(total_paise / 1.18))
            tax_paise = total_paise - taxable_paise

            # Check intra-state (UP state code '09') vs inter-state
            company_state = getattr(company, 'state_code', '') or ''
            is_intra_state = (company_state == '09')

            if is_intra_state:
                cgst_paise = tax_paise // 2
                sgst_paise = tax_paise - cgst_paise
                igst_paise = 0
            else:
                cgst_paise = 0
                sgst_paise = 0
                igst_paise = tax_paise

            inv_number = cls.generate_invoice_number()

            invoice = BillingInvoice.objects.create(
                invoice_number=inv_number,
                company=company,
                user=user,
                subscription=sub,
                transaction=transaction_obj,
                customer_name=company.name,
                customer_email=company.email or (user.email if user else ""),
                customer_address=f"{company.address}, {company.city} - {company.pincode}".strip(', -'),
                customer_gstin=company.gstin or "",
                plan_name=plan_name,
                plan_description=plan_desc,
                billing_period_start=period_start,
                billing_period_end=period_end,
                taxable_amount_paise=taxable_paise,
                cgst_amount_paise=cgst_paise,
                sgst_amount_paise=sgst_paise,
                igst_amount_paise=igst_paise,
                total_amount_paise=total_paise,
                currency=transaction_obj.currency,
                status='paid',
                invoice_date=timezone.localdate(),
            )

            # Generate and store PDF
            try:
                pdf_bytes = cls.render_invoice_pdf(invoice)
                invoice_dir = os.path.join(settings.MEDIA_ROOT, 'billing_invoices')
                os.makedirs(invoice_dir, exist_ok=True)
                file_name = f"{invoice.invoice_number}.pdf"
                file_path = os.path.join(invoice_dir, file_name)
                with open(file_path, 'wb') as f:
                    f.write(pdf_bytes)
                invoice.pdf_path = f"billing_invoices/{file_name}"
                invoice.save(update_fields=['pdf_path'])
            except Exception as e:
                logger.error(f"Failed to generate invoice PDF for {invoice.invoice_number}: {e}")

            return invoice

    @classmethod
    def render_invoice_pdf(cls, invoice: BillingInvoice) -> bytes:
        """
        Renders a clean, official PDF invoice using ReportLab.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm
        )

        styles = getSampleStyleSheet()
        normal = styles['Normal']

        title_style = ParagraphStyle(
            'InvTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#162C5B'),
            alignment=TA_LEFT
        )

        sub_style = ParagraphStyle(
            'InvSub',
            parent=normal,
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#555555')
        )

        right_style = ParagraphStyle(
            'InvRight',
            parent=normal,
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT
        )

        bold_right = ParagraphStyle(
            'InvBoldRight',
            parent=normal,
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT
        )

        story = []

        # Header Table: Provider vs Invoice Meta
        provider_info = [
            Paragraph("<b>SriLekh Accounting Cloud</b>", normal),
            Paragraph("SaaS Subscription Billing", sub_style),
            Paragraph("Website: https://srilekh.com", sub_style),
            Paragraph("Support: support@srilekh.com", sub_style),
        ]

        invoice_meta = [
            Paragraph("<b>TAX INVOICE / RECEIPT</b>", title_style),
            Paragraph(f"<b>Invoice No:</b> {invoice.invoice_number}", right_style),
            Paragraph(f"<b>Date:</b> {invoice.invoice_date.strftime('%d-%b-%Y')}", right_style),
            Paragraph(f"<b>Status:</b> PAID", bold_right),
            Paragraph(f"<b>Payment Ref:</b> {invoice.transaction.razorpay_payment_id if invoice.transaction else 'N/A'}", right_style),
        ]

        header_data = [[provider_info, invoice_meta]]
        header_table = Table(header_data, colWidths=[90 * mm, 90 * mm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        # Bill To Card
        cust_lines = [
            f"<b>Bill To:</b> {invoice.customer_name}",
            f"<b>Email:</b> {invoice.customer_email}",
        ]
        if invoice.customer_address:
            cust_lines.append(f"<b>Address:</b> {invoice.customer_address}")
        if invoice.customer_gstin:
            cust_lines.append(f"<b>GSTIN:</b> {invoice.customer_gstin}")

        bill_to_data = [[Paragraph("<br/>".join(cust_lines), normal)]]
        bill_to_table = Table(bill_to_data, colWidths=[180 * mm])
        bill_to_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(bill_to_table)
        story.append(Spacer(1, 15))

        # Line Items Table
        items_data = [
            [
                Paragraph("<b>Description</b>", normal),
                Paragraph("<b>Period</b>", normal),
                Paragraph("<b>Taxable Amount</b>", bold_right),
            ],
            [
                Paragraph(f"<b>{invoice.plan_name}</b><br/>{invoice.plan_description}", sub_style),
                Paragraph(f"{invoice.billing_period_start.strftime('%d-%b-%Y')} to {invoice.billing_period_end.strftime('%d-%b-%Y')}", sub_style),
                Paragraph(f"₹{invoice.taxable_amount_rupees:,.2f}", right_style),
            ]
        ]

        # Taxes
        if invoice.cgst_amount_paise > 0 or invoice.sgst_amount_paise > 0:
            items_data.append([
                "", Paragraph("Central GST (CGST 9%)", sub_style),
                Paragraph(f"₹{Decimal(invoice.cgst_amount_paise)/100:,.2f}", right_style)
            ])
            items_data.append([
                "", Paragraph("State GST (SGST 9%)", sub_style),
                Paragraph(f"₹{Decimal(invoice.sgst_amount_paise)/100:,.2f}", right_style)
            ])
        elif invoice.igst_amount_paise > 0:
            items_data.append([
                "", Paragraph("Integrated GST (IGST 18%)", sub_style),
                Paragraph(f"₹{Decimal(invoice.igst_amount_paise)/100:,.2f}", right_style)
            ])

        items_data.append([
            "", Paragraph("<b>Total Payable (INR)</b>", normal),
            Paragraph(f"<b>₹{invoice.total_amount_rupees:,.2f}</b>", bold_right)
        ])

        items_table = Table(items_data, colWidths=[80 * mm, 55 * mm, 45 * mm])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#162C5B')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 20))

        # Footer notes
        footer_note = Paragraph(
            "This is a computer-generated tax invoice for SaaS subscription services provided by SriLekh. "
            "For billing inquiries or enterprise support, please contact billing@srilekh.com.",
            sub_style
        )
        story.append(footer_note)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

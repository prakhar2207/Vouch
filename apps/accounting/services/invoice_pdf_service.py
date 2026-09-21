import io
import logging
import os
import urllib.parse
from decimal import Decimal
from typing import Optional

import qrcode
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from apps.accounting.models import Voucher

logger = logging.getLogger(__name__)

# Register Roboto fonts for Rupee symbol support
def _ensure_roboto_fonts():
    font_dir = os.path.join(os.path.dirname(__file__), '..', 'fonts')
    try:
        pdfmetrics.registerFont(TTFont('Roboto', os.path.join(font_dir, 'Roboto-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', os.path.join(font_dir, 'Roboto-Bold.ttf')))
        pdfmetrics.registerFont(TTFont('Roboto-Oblique', os.path.join(font_dir, 'Roboto-Italic.ttf')))
        pdfmetrics.registerFont(TTFont('Roboto-BoldOblique', os.path.join(font_dir, 'Roboto-BoldItalic.ttf')))
        return True
    except Exception as e:
        logger.warning(f"Failed to register fonts: {e}")
        return False

FONTS_LOADED = _ensure_roboto_fonts()


def amount_to_words_indian(num: Decimal) -> str:
    """Converts a Decimal amount to words using the Indian numbering system (Lakhs, Crores)."""
    try:
        num = Decimal(str(num)).quantize(Decimal('0.01'))
    except Exception:
        return ""

    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def convert_upto_999(n):
        res = ""
        hundreds = n // 100
        remainder = n % 100
        if hundreds > 0:
            res += ones[hundreds] + " Hundred "
        if remainder > 0:
            if remainder < 20:
                res += ones[remainder] + " "
            else:
                res += tens[remainder // 10] + " " + (ones[remainder % 10] + " " if remainder % 10 != 0 else "")
        return res.strip()

    integer_part = int(num)
    paise_part = int(round((num - integer_part) * 100))

    if integer_part == 0:
        words = "Zero Rupees"
    else:
        crores = integer_part // 10000000
        rem_cr = integer_part % 10000000
        lakhs = rem_cr // 100000
        rem_lakh = rem_cr % 100000
        thousands = rem_lakh // 1000
        rem_th = rem_lakh % 1000

        parts = []
        if crores > 0:
            parts.append(convert_upto_999(crores) + " Crore")
        if lakhs > 0:
            parts.append(convert_upto_999(lakhs) + " Lakh")
        if thousands > 0:
            parts.append(convert_upto_999(thousands) + " Thousand")
        if rem_th > 0:
            parts.append(convert_upto_999(rem_th))

        words = " ".join(parts).strip() + " Rupees"

    if paise_part > 0:
        words += f" and {convert_upto_999(paise_part)} Paise"

    return words + " Only"


class InvoicePDFService:
    """
    Generates high-definition, compliant GST Tax Invoice PDFs matching the
    exact standard Indian B2B boxed layout (mirroring the browser print / Save as PDF view).
    Guarantees a complete, full A4 page fit without empty white space or overflow.
    """

    @classmethod
    def generate_invoice_pdf(cls, voucher: Voucher) -> bytes:
        buffer = io.BytesIO()

        # Page Dimensions & Margins
        # A4 = 595.27 x 841.89 pt
        TOP_MARGIN = 5 * mm      # 14.17 pt
        BOTTOM_MARGIN = 5 * mm   # 14.17 pt
        LEFT_MARGIN = 6.5 * mm   # 18.43 pt
        RIGHT_MARGIN = 6.5 * mm  # 18.43 pt

        WIDTH = 556
        # Usable frame height is ~801.5 pt; target 792 pt ensures exactly 1 single full page
        TARGET_DOC_HEIGHT = 792.0

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=LEFT_MARGIN,
            rightMargin=RIGHT_MARGIN,
            topMargin=TOP_MARGIN,
            bottomMargin=BOTTOM_MARGIN,
        )

        company = voucher.company
        party = voucher.party_ledger

        # Typography Styles matching the print sheet
        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        fnt_b = 'Roboto-Bold' if FONTS_LOADED else 'Helvetica-Bold'
        fnt_i = 'Roboto-Oblique' if FONTS_LOADED else 'Helvetica-Oblique'

        s_top_left = ParagraphStyle('TopLeft', fontName=fnt_b, fontSize=8, leading=10, textColor=colors.black)
        s_top_right = ParagraphStyle('TopRight', fontName=fnt_i, fontSize=8, leading=10, alignment=TA_RIGHT, textColor=colors.black)
        s_inv_title = ParagraphStyle('InvTitle', fontName=fnt_b, fontSize=10, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_comp_name = ParagraphStyle('CompName', fontName=fnt_b, fontSize=16, leading=20, alignment=TA_CENTER, textColor=colors.black)
        s_comp_addr = ParagraphStyle('CompAddr', fontName=fnt, fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.black)
        s_comp_contact = ParagraphStyle('CompContact', fontName=fnt, fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.black)
        s_comp_tagline = ParagraphStyle('CompTagline', fontName=fnt_b, fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.black)

        s_meta_cell = ParagraphStyle('MetaCell', fontName=fnt, fontSize=9, leading=12, textColor=colors.black)
        s_party_cell = ParagraphStyle('PartyCell', fontName=fnt, fontSize=9, leading=12, textColor=colors.black)

        s_th = ParagraphStyle('TH', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_td_c = ParagraphStyle('TDC', fontName=fnt, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=9, leading=12, alignment=TA_LEFT, textColor=colors.black)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_td_bold_r = ParagraphStyle('TDBoldR', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_td_bold_c = ParagraphStyle('TDBoldC', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_td_tax_label = ParagraphStyle('TaxLabel', fontName=fnt_i, fontSize=8, leading=10, alignment=TA_RIGHT, textColor=colors.black)

        s_tax_th_l = ParagraphStyle('TaxTHL', fontName=fnt_b, fontSize=7.5, leading=9.5, alignment=TA_LEFT, textColor=colors.black)
        s_tax_th_r = ParagraphStyle('TaxTHR', fontName=fnt_b, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)
        s_tax_td_l = ParagraphStyle('TaxTDL', fontName=fnt, fontSize=7.5, leading=9.5, alignment=TA_LEFT, textColor=colors.black)
        s_tax_td_r = ParagraphStyle('TaxTDR', fontName=fnt, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)

        s_words = ParagraphStyle('Words', fontName=fnt, fontSize=8.5, leading=11, textColor=colors.black)
        s_bank_text = ParagraphStyle('BankText', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.black)

        s_terms = ParagraphStyle('Terms', fontName=fnt, fontSize=7.5, leading=9.5, textColor=colors.black)
        s_qr_label = ParagraphStyle('QRLabel', fontName=fnt_b, fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.black)
        s_sign_rcvr = ParagraphStyle('SignRcvr', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_LEFT, textColor=colors.black)
        s_sign_auth = ParagraphStyle('SignAuth', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_RIGHT, textColor=colors.black)

        # ================= 1. HEADER =================
        header_rows = [
            [
                Paragraph(f"GSTIN : <b>{company.gstin or 'Unregistered'}</b>", s_top_left),
                Paragraph("Original For Recipient", s_top_right)
            ],
            [Paragraph("<u>TAX INVOICE</u>", s_inv_title), ""],
            [Paragraph(f"<b>{company.name}</b>", s_comp_name), ""],
            [Paragraph(company.address or "", s_comp_addr), ""],
            [Paragraph(f"Ph: {company.phone or 'N/A'} | Email: {company.email or 'N/A'}", s_comp_contact), ""],
        ]
        if company.tagline:
            header_rows.append([Paragraph(company.tagline.upper(), s_comp_tagline), ""])

        header_table = Table(header_rows, colWidths=[WIDTH / 2, WIDTH / 2])
        h_style = [
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('SPAN', (0, 1), (1, 1)),
            ('SPAN', (0, 2), (1, 2)),
            ('SPAN', (0, 3), (1, 3)),
            ('SPAN', (0, 4), (1, 4)),
            ('PADDING', (0, 0), (-1, -1), 1.5),
            ('TOPPADDING', (0, 0), (-1, 0), 2.5),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 2.5),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
        ]
        if company.tagline:
            h_style.append(('SPAN', (0, 5), (1, 5)))
        header_table.setStyle(TableStyle(h_style))

        # ================= 2. META GRID =================
        inv_no = voucher.voucher_number
        if hasattr(voucher.voucher_date, 'strftime'):
            inv_date = voucher.voucher_date.strftime('%Y-%m-%d')
        else:
            inv_date = str(voucher.voucher_date or '')

        comp_state = company.state_name or company.state_code or ''
        pos = f"{comp_state} ({company.state_code})" if company.state_code else (comp_state or 'N/A')

        ewb_rec = getattr(voucher, 'eway_bill', None) or getattr(voucher, 'ewaybillrecord', None)
        gr_rr = getattr(ewb_rec, 'trans_doc_no', 'N/A') or 'N/A'
        transport = getattr(ewb_rec, 'transporter_name', '') or getattr(ewb_rec, 'trans_mode_display', 'Road') or 'Road'
        vehicle_no = getattr(ewb_rec, 'vehicle_no', 'N/A') or 'N/A'
        ewb_no = getattr(ewb_rec, 'eway_bill_number', 'N/A') or 'N/A'

        meta_left = (
            f"Invoice No. &nbsp;&nbsp;&nbsp;&nbsp;: <b>{inv_no}</b><br/>"
            f"Dated &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{inv_date}</b><br/>"
            f"Place of Supply : {pos}<br/>"
            f"Reverse Charge : N"
        )
        meta_right = (
            f"GR/RR No. &nbsp;&nbsp;&nbsp;&nbsp;: {gr_rr}<br/>"
            f"Transport &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {transport}<br/>"
            f"Vehicle No. &nbsp;&nbsp;&nbsp;&nbsp;: <b>{vehicle_no}</b><br/>"
            f"E-Way Bill No. : <b>{ewb_no}</b>"
        )

        meta_table = Table(
            [[Paragraph(meta_left, s_meta_cell), Paragraph(meta_right, s_meta_cell)]],
            colWidths=[WIDTH / 2, WIDTH / 2]
        )
        meta_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEAFTER', (0, 0), (0, -1), 1, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 2.5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # ================= 3. BILLED TO / SHIPPED TO GRID =================
        buyer_name = voucher.buyer_name or (party.name if party else 'Customer')
        raw_addr = voucher.buyer_address or (party.address if party and party.address else '')
        clean_addr = raw_addr.replace('\r\n', '\n').replace('\n', '<br/>').strip()
        buyer_gstin = voucher.buyer_gstin or (party.gstin if party and party.gstin else 'Unregistered')

        billed_to = (
            f"<i>Billed to :</i><br/>"
            f"<b>{buyer_name}</b><br/>"
            f"{clean_addr}<br/>"
            f"GSTIN / UIN &nbsp;&nbsp;: <b>{buyer_gstin}</b>"
        )
        shipped_to = (
            f"<i>Shipped to :</i><br/>"
            f"<b>{buyer_name}</b><br/>"
            f"{clean_addr}<br/>"
            f"GSTIN / UIN &nbsp;&nbsp;: <b>{buyer_gstin}</b>"
        )

        party_table = Table(
            [[Paragraph(billed_to, s_party_cell), Paragraph(shipped_to, s_party_cell)]],
            colWidths=[WIDTH / 2, WIDTH / 2]
        )
        party_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEAFTER', (0, 0), (0, -1), 1, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 2.5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # ================= 5. TAX DETAILS TABLE (Constructed early to measure exact height) =================
        items = list(voucher.items.all().select_related('product'))
        tot_cgst = sum(i.cgst_amount for i in items)
        tot_sgst = sum(i.sgst_amount for i in items)
        tot_igst = sum(i.igst_amount for i in items)
        tot_taxable = sum(i.taxable_amount for i in items)
        tot_qty = sum(i.quantity for i in items)
        grand_total = voucher.total_amount

        is_inter_state = False
        if company.state_code and voucher.buyer_state_code:
            is_inter_state = str(company.state_code) != str(voucher.buyer_state_code)
        elif company.state_code and party and party.state_code:
            is_inter_state = str(company.state_code) != str(party.state_code)

        tax_rates = sorted(list(set(itm.gst_rate for itm in items))) if items else [Decimal('18.00')]
        tax_col_w = [90, 115, 115, 115, 121] if not is_inter_state else [120, 145, 145, 146]
        tax_rows = []

        if not is_inter_state:
            tax_rows.append([
                Paragraph("<b>Tax Rate</b>", s_tax_th_l),
                Paragraph("<b>Taxable Amt.</b>", s_tax_th_r),
                Paragraph("<b>CGST Amt.</b>", s_tax_th_r),
                Paragraph("<b>SGST Amt.</b>", s_tax_th_r),
                Paragraph("<b>Total Tax</b>", s_tax_th_r),
            ])
            for r in tax_rates:
                rate_items = [i for i in items if i.gst_rate == r]
                r_taxable = sum(i.taxable_amount for i in rate_items)
                r_cgst = sum(i.cgst_amount for i in rate_items)
                r_sgst = sum(i.sgst_amount for i in rate_items)
                r_tot = r_cgst + r_sgst
                tax_rows.append([
                    Paragraph(f"{r:.0f}%", s_tax_td_l),
                    Paragraph(f"{r_taxable:,.2f}", s_tax_td_r),
                    Paragraph(f"{r_cgst:,.2f}", s_tax_td_r),
                    Paragraph(f"{r_sgst:,.2f}", s_tax_td_r),
                    Paragraph(f"{r_tot:,.2f}", s_tax_td_r),
                ])
        else:
            tax_rows.append([
                Paragraph("<b>Tax Rate</b>", s_tax_th_l),
                Paragraph("<b>Taxable Amt.</b>", s_tax_th_r),
                Paragraph("<b>IGST Amt.</b>", s_tax_th_r),
                Paragraph("<b>Total Tax</b>", s_tax_th_r),
            ])
            for r in tax_rates:
                rate_items = [i for i in items if i.gst_rate == r]
                r_taxable = sum(i.taxable_amount for i in rate_items)
                r_igst = sum(i.igst_amount for i in rate_items)
                tax_rows.append([
                    Paragraph(f"{r:.0f}%", s_tax_td_l),
                    Paragraph(f"{r_taxable:,.2f}", s_tax_td_r),
                    Paragraph(f"{r_igst:,.2f}", s_tax_td_r),
                    Paragraph(f"{r_igst:,.2f}", s_tax_td_r),
                ])

        tax_table = Table(tax_rows, colWidths=tax_col_w)
        tax_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 1.5),
        ]))

        # ================= 6. AMOUNT IN WORDS =================
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'
        words_text = f"Total Amount in Words : <b>{curr_sym} {amount_to_words_indian(grand_total)}</b>"
        words_table = Table([[Paragraph(words_text, s_words)]], colWidths=[WIDTH])
        words_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 2.5),
        ]))

        # ================= 7. BANK DETAILS =================
        b_name = company.bank_name or 'Canara Bank Govind Nagar'
        b_branch = company.bank_branch or ''
        b_acc = company.bank_account_number or '125008094288'
        b_ifsc = company.bank_ifsc or 'CNRB0003827'

        bank_cell = (
            f"<b><u>BANK DETAILS</u></b><br/>"
            f"{b_name} {b_branch}, ACCOUNT NO- {b_acc}, IFSCODE: {b_ifsc}"
        )
        bank_table = Table([[Paragraph(bank_cell, s_bank_text)]], colWidths=[WIDTH])
        bank_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 2),
        ]))

        # ================= 8. BOTTOM FOOTER =================
        city = company.city or 'Kanpur'
        terms_content = (
            f"<b>Terms &amp; Conditions</b><br/>"
            f"<b>E.&amp; O.E.</b><br/>"
            f"1. Goods once sold will not be taken back.<br/>"
            f"2. Interest @ 18% p.a. will be charged if the payment is not made within 45 days.<br/>"
            f"3. Subject to '{city}' Jurisdiction only."
        )

        qr_img = None
        try:
            phone_val = getattr(company, 'phone', '')
            upi_id = getattr(company, 'bank_upi_id', None) or (f"{phone_val}@upi" if phone_val else "vouch@upi")
            upi_url = (
                f"upi://pay?pa={upi_id}"
                f"&pn={urllib.parse.quote(company.name)}"
                f"&am={float(grand_total):.2f}"
                f"&cu=INR"
                f"&tn={urllib.parse.quote(f'Inv {inv_no}')}"
            )
            qr = qrcode.QRCode(version=1, box_size=3, border=1)
            qr.add_data(upi_url)
            qr.make(fit=True)
            pil_qr = qr.make_image(fill_color="black", back_color="white")
            qr_buf = io.BytesIO()
            pil_qr.save(qr_buf, format='PNG')
            qr_buf.seek(0)
            qr_img = RLImage(qr_buf, width=22 * mm, height=22 * mm)
        except Exception as e:
            logger.warning(f"Could not generate QR code: {e}")

        qr_cell_content = [
            Paragraph("<b>E-Invoice QR Code</b>", s_qr_label),
            Spacer(1, 1),
            qr_img if qr_img else Paragraph("", s_terms),
        ]

        # Optional Proprietor Signature
        sig_img = None
        sig_field = getattr(company, 'proprietor_signature', None)
        if sig_field:
            try:
                sig_path = getattr(sig_field, 'path', None)
                if sig_path and os.path.exists(sig_path):
                    sig_img = RLImage(sig_path, width=32 * mm, height=12 * mm)
            except Exception:
                sig_img = None

        sig_inner_elements = [Paragraph(f"<b>for {company.name}</b>", s_sign_auth)]
        if sig_img:
            sig_inner_elements.append(Spacer(1, 2))
            sig_inner_elements.append(sig_img)
            sig_inner_elements.append(Spacer(1, 2))
        else:
            sig_inner_elements.append(Paragraph("<br/><br/><br/>", s_sign_auth))
        sig_inner_elements.append(Paragraph("<b>Authorised Signatory</b>", s_sign_auth))

        sig_subtable = Table([
            [Paragraph("<b>Receiver's Signature :</b>", s_sign_rcvr)],
            [sig_inner_elements]
        ], colWidths=[210], rowHeights=[24, 76])
        sig_subtable.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, 0), 'TOP'),
            ('VALIGN', (0, 1), (-1, 1), 'TOP'),
        ]))

        footer_table = Table(
            [[
                Paragraph(terms_content, s_terms),
                qr_cell_content,
                sig_subtable
            ]],
            colWidths=[236, 110, 210],
            rowHeights=[100]
        )
        footer_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEAFTER', (0, 0), (0, -1), 1, colors.black),
            ('LINEAFTER', (1, 0), (1, -1), 1, colors.black),
            ('PADDING', (0, 0), (1, -1), 2.5),
            ('LEFTPADDING', (2, 0), (2, -1), 0),
            ('RIGHTPADDING', (2, 0), (2, -1), 0),
            ('TOPPADDING', (2, 0), (2, -1), 0),
            ('BOTTOMPADDING', (2, 0), (2, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # Exact height measurement of fixed tables
        h_header = header_table.wrap(WIDTH, 2000)[1]
        h_meta = meta_table.wrap(WIDTH, 2000)[1]
        h_party = party_table.wrap(WIDTH, 2000)[1]
        h_tax = tax_table.wrap(WIDTH, 2000)[1]
        h_words = words_table.wrap(WIDTH, 2000)[1]
        h_bank = bank_table.wrap(WIDTH, 2000)[1]
        h_footer = footer_table.wrap(WIDTH, 2000)[1]

        fixed_height = h_header + h_meta + h_party + h_tax + h_words + h_bank + h_footer

        # ================= 4. ITEMS TABLE =================
        col_w = [30, 216, 56, 40, 34, 48, 42, 90]  # sum = 556
        items_data = [
            [
                Paragraph("<b>S.N.</b>", s_th),
                Paragraph("<b>Description of Goods</b>", s_th),
                Paragraph("<b>HSN</b>", s_th),
                Paragraph("<b>Qty.</b>", s_th),
                Paragraph("<b>Unit</b>", s_th),
                Paragraph("<b>Price</b>", s_th),
                Paragraph("<b>Disc%</b>", s_th),
                Paragraph("<b>Amount(₹)</b>", s_th),
            ]
        ]

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

            items_data.append([
                Paragraph(str(idx), s_td_c),
                Paragraph(p_name, s_td_l),
                Paragraph(str(hsn or ''), s_td_c),
                Paragraph(f"{qty:.2f}", s_td_r),
                Paragraph(str(unit or 'PCS'), s_td_c),
                Paragraph(f"{rate:.2f}", s_td_r),
                Paragraph(f"{disc_pct:.2f}%" if disc_pct > 0 else "0.00%", s_td_c),
                Paragraph(f"{taxable:,.2f}", s_td_r),
            ])

        num_item_rows = len(items)

        # Empty filler row placeholder
        filler_idx = len(items_data)
        items_data.append(["", "", "", "", "", "", "", ""])

        # Subtotal row
        subtotal_idx = len(items_data)
        items_data.append([
            "", "", "", "", "", "", "",
            Paragraph(f"{tot_taxable:,.2f}", s_td_r)
        ])

        # Taxes rows
        first_item_gst = items[0].gst_rate if items else Decimal('18.00')
        num_tax_rows = 0
        
        # Helper to add tax rows aligned perfectly to columns
        def add_tax_row(label, rate_label, amount):
            items_data.append([

                "", "", "", "",
                Paragraph(label, s_td_tax_label),
                "",
                Paragraph(rate_label, s_td_tax_label),
                Paragraph(f"{amount:,.2f}", s_td_r)
            ])
            
        if is_inter_state or tot_igst > 0:
            rate_disp = f"@ {(first_item_gst):.2f} %"
            add_tax_row("Add : IGST", rate_disp, tot_igst)
            num_tax_rows += 1
        else:
            half_rate = f"@ {(first_item_gst / 2):.2f} %"
            add_tax_row("Add : CGST", half_rate, tot_cgst)
            add_tax_row("Add : SGST", half_rate, tot_sgst)
            num_tax_rows += 2

        cartage = getattr(voucher, 'cartage_amount', Decimal('0.00')) or Decimal('0.00')
        if cartage > 0:
            add_tax_row("Add : Cartage", "", cartage)
            num_tax_rows += 1

        round_off = getattr(voucher, 'round_off', Decimal('0.00')) or Decimal('0.00')
        if abs(round_off) >= Decimal('0.005'):
            lbl = "Add : Round Off" if round_off > 0 else "Less : Round Off"
            add_tax_row(lbl, "", round_off)
            num_tax_rows += 1

        grand_total_idx = len(items_data)
        items_data.append([
            Paragraph("<b>Grand Total</b>", s_td_bold_r),
            "", "", "",
            Paragraph(f"<b>{tot_qty:.2f} {unit_label}</b>", s_td_bold_c),
            "", "",
            Paragraph(f"<b>{grand_total:,.2f}</b>", s_td_bold_r)
        ])

        # Dynamic filler height calculation:
        target_items_table_height = TARGET_DOC_HEIGHT - fixed_height
        content_rows_height = 18 + (num_item_rows * 16) + 16 + (num_tax_rows * 14.5) + 20
        filler_height = max(10.0, target_items_table_height - content_rows_height)

        row_heights = [18] + [16] * num_item_rows + [filler_height] + [16] + [14.5] * num_tax_rows + [20]
        items_table = Table(items_data, colWidths=col_w, rowHeights=row_heights)

        it_style = [
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LINEAFTER', (0, 0), (0, filler_idx), 1, colors.black),
            ('LINEAFTER', (1, 0), (1, filler_idx), 1, colors.black),
            ('LINEAFTER', (2, 0), (2, filler_idx), 1, colors.black),
            ('LINEAFTER', (3, 0), (3, filler_idx), 1, colors.black),
            ('LINEAFTER', (4, 0), (4, filler_idx), 1, colors.black),
            ('LINEAFTER', (5, 0), (5, filler_idx), 1, colors.black),
            ('LINEAFTER', (6, 0), (6, -1), 1, colors.black),
            ('LINEBELOW', (0, filler_idx), (-1, filler_idx), 1, colors.black),
            ('LINEABOVE', (0, grand_total_idx), (-1, grand_total_idx), 1, colors.black),
            ('LINEBELOW', (0, grand_total_idx), (-1, grand_total_idx), 1, colors.black),
            ('SPAN', (0, grand_total_idx), (3, grand_total_idx)),
            ('SPAN', (4, grand_total_idx), (6, grand_total_idx)),
            ('PADDING', (0, 0), (-1, -1), 1.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # For Subtotal row
        it_style.append(('SPAN', (0, subtotal_idx), (6, subtotal_idx)))
        
        # For Tax rows
        for r in range(subtotal_idx + 1, grand_total_idx):
            it_style.append(('SPAN', (0, r), (3, r)))
            it_style.append(('SPAN', (4, r), (5, r)))
            # Col 6 is unspanned for rate
            
        items_table.setStyle(TableStyle(it_style))

        elements = [
            header_table,
            meta_table,
            party_table,
            items_table,
            tax_table,
            words_table,
            bank_table,
            footer_table,
        ]

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()


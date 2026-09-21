import io
import logging
import os
import qrcode
from decimal import Decimal
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

from apps.documents.renderers.base import FONTS_LOADED

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that counts total pages and writes 'Page X of Y' on every page.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        self.setFont(fnt, 7.5)
        self.setFillColor(colors.HexColor('#475569'))
        # Margin X = 19.5, Width = 556
        margin_x = 19.5
        page_w = A4[0]
        self.drawString(margin_x, 10, "This is a Computer Generated Invoice")
        self.drawRightString(page_w - margin_x, 10, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


class InvoicePDFRenderer:
    """
    Renders deterministic, high-definition GST Tax Invoices strictly from Canonical DTO.
    Replicates the exact standard Indian B2B boxed layout (matching INVOICE-105.pdf benchmark).
    Guarantees:
      - Strictly 1 single A4 page for normal/moderate invoices (<= ~12 items).
      - Seamless multi-page flow for large invoices (> 12 items) with the footer present
        on EVERY page and 'Page X of Y' on every page.
    """

    @classmethod
    def render(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()

        # Page Dimensions & Margins
        PAGE_WIDTH, PAGE_HEIGHT = A4
        WIDTH = 556.0
        MARGIN_X = (PAGE_WIDTH - WIDTH) / 2.0   # ~19.64 pt
        FOOTER_HEIGHT = 86.0
        TOP_MARGIN = 16.0
        FRAME_BOTTOM = 22.0 + FOOTER_HEIGHT + 2.0  # = 110.0 pt
        FRAME_HEIGHT = PAGE_HEIGHT - TOP_MARGIN - FRAME_BOTTOM  # ~715.89 pt

        doc_meta = dto.get('document', {})
        seller = dto.get('seller', {})
        buyer = dto.get('buyer', {})
        items = dto.get('items', [])
        subtotals = dto.get('subtotals', {})
        tax_breakdown = dto.get('tax_breakdown', [])
        is_inter_state = subtotals.get('is_inter_state', False)

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
        s_th_l = ParagraphStyle('THL', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_LEFT, textColor=colors.black)
        s_th_r = ParagraphStyle('THR', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_td_c = ParagraphStyle('TDC', fontName=fnt, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=9, leading=12, alignment=TA_LEFT, textColor=colors.black)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_td_bold_r = ParagraphStyle('TDBoldR', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_td_bold_c = ParagraphStyle('TDBoldC', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_td_tax_label = ParagraphStyle('TaxLabel', fontName=fnt_i, fontSize=8.5, leading=10.5, alignment=TA_RIGHT, textColor=colors.black)

        s_tax_th_l = ParagraphStyle('TaxTHL', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_LEFT, textColor=colors.black)
        s_tax_th_r = ParagraphStyle('TaxTHR', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_RIGHT, textColor=colors.black)
        s_tax_td_l = ParagraphStyle('TaxTDL', fontName=fnt, fontSize=8, leading=10, alignment=TA_LEFT, textColor=colors.black)
        s_tax_td_r = ParagraphStyle('TaxTDR', fontName=fnt, fontSize=8, leading=10, alignment=TA_RIGHT, textColor=colors.black)

        s_words = ParagraphStyle('Words', fontName=fnt, fontSize=9, leading=12, textColor=colors.black)
        s_bank_text = ParagraphStyle('BankText', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.black)

        s_terms = ParagraphStyle('Terms', fontName=fnt, fontSize=7, leading=8.5, textColor=colors.black)
        s_qr_label = ParagraphStyle('QRLabel', fontName=fnt_b, fontSize=7, leading=8.5, alignment=TA_CENTER, textColor=colors.black)
        s_sign_rcvr = ParagraphStyle('SignRcvr', fontName=fnt_b, fontSize=7.5, leading=9.5, alignment=TA_LEFT, textColor=colors.black)
        s_sign_auth = ParagraphStyle('SignAuth', fontName=fnt_b, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)

        # ================= 1. HEADER =================
        gstin_str = seller.get('gstin', 'Unregistered')
        header_rows = [
            [
                Paragraph(f"GSTIN : <b>{gstin_str}</b>", s_top_left),
                Paragraph("Original For Recipient", s_top_right)
            ],
            [Paragraph("<u>TAX INVOICE</u>", s_inv_title), ""],
            [Paragraph(f"<b>{seller.get('name', '')}</b>", s_comp_name), ""],
            [Paragraph(seller.get('address', ''), s_comp_addr), ""],
            [Paragraph(f"Ph: {seller.get('phone', 'N/A')} | Email: {seller.get('email', 'N/A')}", s_comp_contact), ""],
        ]
        if seller.get('tagline'):
            header_rows.append([Paragraph(seller.get('tagline').upper(), s_comp_tagline), ""])

        header_table = Table(header_rows, colWidths=[WIDTH / 2, WIDTH / 2])
        h_style = [
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('SPAN', (0, 1), (1, 1)),
            ('SPAN', (0, 2), (1, 2)),
            ('SPAN', (0, 3), (1, 3)),
            ('SPAN', (0, 4), (1, 4)),
            ('PADDING', (0, 0), (-1, -1), 1.5),
            ('TOPPADDING', (0, 0), (-1, 0), 2),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 2),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
        ]
        if seller.get('tagline'):
            h_style.append(('SPAN', (0, 5), (1, 5)))
        header_table.setStyle(TableStyle(h_style))

        # ================= 2. META GRID =================
        inv_no = doc_meta.get('document_number', '')
        inv_date = doc_meta.get('document_date', '')
        pos = doc_meta.get('place_of_supply', 'N/A')
        gr_rr = doc_meta.get('gr_rr_no', 'N/A')
        transport = doc_meta.get('transport', 'Road')
        vehicle_no = doc_meta.get('vehicle_no', 'N/A')
        ewb_no = doc_meta.get('eway_bill_no', 'N/A')

        meta_rows = [
            [
                Paragraph("Invoice No.", s_meta_cell),
                Paragraph(f": <b>{inv_no}</b>", s_meta_cell),
                Paragraph("GR/RR No.", s_meta_cell),
                Paragraph(f": {gr_rr}", s_meta_cell),
            ],
            [
                Paragraph("Dated", s_meta_cell),
                Paragraph(f": <b>{inv_date}</b>", s_meta_cell),
                Paragraph("Transport", s_meta_cell),
                Paragraph(f": {transport}", s_meta_cell),
            ],
            [
                Paragraph("Place of Supply", s_meta_cell),
                Paragraph(f": {pos}", s_meta_cell),
                Paragraph("Vehicle No.", s_meta_cell),
                Paragraph(f": <b>{vehicle_no}</b>", s_meta_cell),
            ],
            [
                Paragraph("Reverse Charge", s_meta_cell),
                Paragraph(": N", s_meta_cell),
                Paragraph("E-Way Bill No.", s_meta_cell),
                Paragraph(f": <b>{ewb_no}</b>", s_meta_cell),
            ],
        ]

        meta_table = Table(meta_rows, colWidths=[85, 193, 85, 193])
        meta_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEAFTER', (1, 0), (1, -1), 1, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 1.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # ================= 3. BILLED TO / SHIPPED TO GRID =================
        buyer_name = buyer.get('name', 'Customer')
        raw_addr = buyer.get('address', '')
        clean_addr = raw_addr.replace('\r\n', '\n').replace('\n', '<br/>').strip()
        buyer_gstin = buyer.get('gstin', 'Unregistered')

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
            ('PADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # ================= 5. TAX DETAILS TABLE =================
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
            for tb in tax_breakdown:
                tax_rows.append([
                    Paragraph(f"{tb['rate']:.0f}%", s_tax_td_l),
                    Paragraph(f"{tb['taxable_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['cgst_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['sgst_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['total_tax']:,.2f}", s_tax_td_r),
                ])
        else:
            tax_rows.append([
                Paragraph("<b>Tax Rate</b>", s_tax_th_l),
                Paragraph("<b>Taxable Amt.</b>", s_tax_th_r),
                Paragraph("<b>IGST Amt.</b>", s_tax_th_r),
                Paragraph("<b>Total Tax</b>", s_tax_th_r),
            ])
            for tb in tax_breakdown:
                tax_rows.append([
                    Paragraph(f"{tb['rate']:.0f}%", s_tax_td_l),
                    Paragraph(f"{tb['taxable_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['igst_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['total_tax']:,.2f}", s_tax_td_r),
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
        words_text = f"Total Amount in Words : <b>{curr_sym} {dto.get('amount_in_words', '')}</b>"
        words_table = Table([[Paragraph(words_text, s_words)]], colWidths=[WIDTH])
        words_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 2),
        ]))

        # ================= 7. BANK DETAILS =================
        b_name = seller.get('bank_name', 'Canara Bank Govind Nagar')
        b_branch = seller.get('bank_branch', '')
        b_acc = seller.get('bank_account_number', '125008094288')
        b_ifsc = seller.get('bank_ifsc', 'CNRB0003827')

        bank_cell = (
            f"<b><u>BANK DETAILS</u></b><br/>"
            f"{b_name} {b_branch}, ACCOUNT NO- {b_acc}, IFSCODE: {b_ifsc}"
        )
        bank_table = Table([[Paragraph(bank_cell, s_bank_text)]], colWidths=[WIDTH])
        bank_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.black),
            ('PADDING', (0, 0), (-1, -1), 1.5),
        ]))

        # Measure fixed top and bottom heights
        h_header = header_table.wrap(WIDTH, 2000)[1]
        h_meta = meta_table.wrap(WIDTH, 2000)[1]
        h_party = party_table.wrap(WIDTH, 2000)[1]
        h_top = h_header + h_meta + h_party

        h_tax = tax_table.wrap(WIDTH, 2000)[1]
        h_words = words_table.wrap(WIDTH, 2000)[1]
        h_bank = bank_table.wrap(WIDTH, 2000)[1]
        h_bottom = h_tax + h_words + h_bank

        # ================= 8. BOTTOM FOOTER (Rendered on EVERY Page) =================
        city = seller.get('city', 'Kanpur')
        terms_list = dto.get('terms', [
            "Goods once sold will not be taken back.",
            "Interest @ 18% p.a. will be charged if the payment is not made within 45 days.",
            f"Subject to '{city}' Jurisdiction only."
        ])
        terms_content = "<b>Terms &amp; Conditions</b><br/><b>E.&amp; O.E.</b><br/>" + "<br/>".join(
            f"{i+1}. {t}" for i, t in enumerate(terms_list)
        )

        qr_img = None
        try:
            upi_url = dto.get('upi_url', '')
            if upi_url:
                qr = qrcode.QRCode(version=1, box_size=3, border=1)
                qr.add_data(upi_url)
                qr.make(fit=True)
                pil_qr = qr.make_image(fill_color="black", back_color="white")
                qr_buf = io.BytesIO()
                pil_qr.save(qr_buf, format='PNG')
                qr_buf.seek(0)
                qr_img = RLImage(qr_buf, width=20 * mm, height=20 * mm)
        except Exception as e:
            logger.warning(f"Could not generate QR code: {e}")

        qr_cell_content = [
            Paragraph("<b>Scan to Verify</b>", s_qr_label),
            Spacer(1, 1),
            qr_img if qr_img else Paragraph("", s_terms),
        ]

        sig_img = None
        sig_url = seller.get('signature_url')
        if sig_url and os.path.exists(sig_url):
            try:
                sig_img = RLImage(sig_url, width=32 * mm, height=12 * mm)
            except Exception:
                sig_img = None

        comp_name_str = seller.get('name', 'Vouch')
        sig_inner_elements = [Paragraph(f"<b>for {comp_name_str}</b>", s_sign_auth)]
        if sig_img:
            sig_inner_elements.append(Spacer(1, 1))
            sig_inner_elements.append(sig_img)
            sig_inner_elements.append(Spacer(1, 1))
        else:
            sig_inner_elements.append(Paragraph("<br/><br/>", s_sign_auth))
        sig_inner_elements.append(Paragraph("<b>Authorised Signatory</b>", s_sign_auth))

        sig_subtable = Table([
            [Paragraph("<b>Receiver's Signature :</b>", s_sign_rcvr)],
            [sig_inner_elements]
        ], colWidths=[200], rowHeights=[20, 66])
        sig_subtable.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
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
            colWidths=[246, 110, 200],
            rowHeights=[FOOTER_HEIGHT]
        )
        footer_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEAFTER', (0, 0), (0, -1), 1, colors.black),
            ('LINEAFTER', (1, 0), (1, -1), 1, colors.black),
            ('PADDING', (0, 0), (1, -1), 2),
            ('LEFTPADDING', (2, 0), (2, -1), 0),
            ('RIGHTPADDING', (2, 0), (2, -1), 0),
            ('TOPPADDING', (2, 0), (2, -1), 0),
            ('BOTTOMPADDING', (2, 0), (2, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # ================= 4. ITEMS TABLE =================
        col_w = [30, 196, 54, 40, 32, 50, 58, 96]
        items_data = [
            [
                Paragraph("<b>S.N.</b>", s_th),
                Paragraph("<b>Description of Goods</b>", s_th_l),
                Paragraph("<b>HSN</b>", s_th),
                Paragraph("<b>Qty.</b>", s_th),
                Paragraph("<b>Unit</b>", s_th),
                Paragraph("<b>Price</b>", s_th),
                Paragraph("<b>Disc%</b>", s_th),
                Paragraph("<b>Amount(Rs.)</b>", s_th_r),
            ]
        ]

        unit_label = subtotals.get('unit_label', 'PCS')
        for itm in items:
            sn = str(itm.get('sn', ''))
            p_name = itm.get('name', 'Item')
            hsn = str(itm.get('hsn_code', ''))
            qty = itm.get('quantity', 0.0)
            unit = itm.get('unit', 'PCS')
            rate = itm.get('rate', 0.0)
            disc_pct = itm.get('discount_percent', 0.0)
            taxable = itm.get('taxable_amount', 0.0)

            items_data.append([
                Paragraph(sn, s_td_c),
                Paragraph(p_name, s_td_l),
                Paragraph(hsn, s_td_c),
                Paragraph(f"{qty:.2f}", s_td_r),
                Paragraph(unit, s_td_c),
                Paragraph(f"{rate:.2f}", s_td_r),
                Paragraph(f"{disc_pct:.2f}%" if disc_pct > 0 else "0.00%", s_td_c),
                Paragraph(f"{taxable:,.2f}", s_td_r),
            ])

        num_item_rows = len(items)
        tot_taxable = subtotals.get('total_taxable', 0.0)
        first_item_gst = items[0].get('gst_rate', 18.0) if items else 18.0
        tot_igst = subtotals.get('total_igst', 0.0)
        tot_cgst = subtotals.get('total_cgst', 0.0)
        tot_sgst = subtotals.get('total_sgst', 0.0)
        cartage = subtotals.get('cartage', 0.0)
        round_off = subtotals.get('round_off', 0.0)
        final_grand_total = subtotals.get('grand_total', 0.0)
        tot_qty = subtotals.get('total_quantity', 0.0)

        num_tax_rows = 1 if (is_inter_state or tot_igst > 0.0) else 2
        if cartage > 0.0:
            num_tax_rows += 1
        if abs(round_off) >= 0.005:
            num_tax_rows += 1

        content_rows_height = 18 + (num_item_rows * 16) + 16 + (num_tax_rows * 14.5) + 20
        total_needed = h_top + content_rows_height + h_bottom
        is_single_page = total_needed <= FRAME_HEIGHT

        filler_idx = -1
        if is_single_page:
            filler_height = max(4.0, FRAME_HEIGHT - total_needed - 4.0)
            filler_idx = len(items_data)
            items_data.append(["", "", "", "", "", "", "", ""])

        # Subtotal row
        subtotal_idx = len(items_data)
        items_data.append([
            "", "", "", "", "", "", "",
            Paragraph(f"{tot_taxable:,.2f}", s_td_r)
        ])

        def add_tax_row(label, rate_label, amount_str):
            items_data.append([
                "", "", "", "",
                Paragraph(label, s_td_tax_label),
                "",
                Paragraph(rate_label, s_td_tax_label),
                Paragraph(amount_str, s_td_r)
            ])

        if is_inter_state or tot_igst > 0.0:
            rate_disp = f"@ {first_item_gst:.2f} %"
            add_tax_row("Add : IGST", rate_disp, f"{tot_igst:,.2f}")
        else:
            half_rate = f"@ {(first_item_gst / 2.0):.2f} %"
            add_tax_row("Add : CGST", half_rate, f"{tot_cgst:,.2f}")
            add_tax_row("Add : SGST", half_rate, f"{tot_sgst:,.2f}")

        if cartage > 0.0:
            add_tax_row("Add : Cartage", "", f"{cartage:,.2f}")

        if abs(round_off) >= 0.005:
            lbl = "Add : Round Off" if round_off > 0.0 else "Less : Round Off"
            sign_str = f"+{round_off:.2f}" if round_off > 0.0 else f"{round_off:.2f}"
            add_tax_row(lbl, "", sign_str)

        grand_total_idx = len(items_data)
        items_data.append([
            Paragraph("<b>Grand Total</b>", s_td_bold_r),
            "", "", "",
            Paragraph(f"<b><u>&nbsp;&nbsp;{tot_qty:.2f} {unit_label}&nbsp;&nbsp;</u></b>", s_td_bold_c),
            "", "",
            Paragraph(f"<b>{final_grand_total:,.2f}</b>", s_td_bold_r)
        ])

        if is_single_page:
            row_heights = [18] + [16] * num_item_rows + [filler_height] + [16] + [14.5] * num_tax_rows + [20]
        else:
            row_heights = [18] + [16] * num_item_rows + [16] + [14.5] * num_tax_rows + [20]

        items_table = Table(items_data, colWidths=col_w, rowHeights=row_heights, repeatRows=1)

        it_style = [
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LINEAFTER', (0, 0), (0, -1), 1, colors.black),
            ('LINEAFTER', (1, 0), (1, -1), 1, colors.black),
            ('LINEAFTER', (2, 0), (2, -1), 1, colors.black),
            ('LINEAFTER', (3, 0), (3, -1), 1, colors.black),
            ('LINEAFTER', (4, 0), (4, -1), 1, colors.black),
            ('LINEAFTER', (5, 0), (5, -1), 1, colors.black),
            ('LINEAFTER', (6, 0), (6, -1), 1, colors.black),
            ('LINEABOVE', (0, grand_total_idx), (-1, grand_total_idx), 1, colors.black),
            ('LINEBELOW', (0, grand_total_idx), (-1, grand_total_idx), 1, colors.black),
            ('SPAN', (0, grand_total_idx), (3, grand_total_idx)),
            ('SPAN', (4, grand_total_idx), (6, grand_total_idx)),
            ('PADDING', (0, 0), (-1, -1), 1.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        if is_single_page and filler_idx > 0:
            it_style.append(('LINEBELOW', (0, filler_idx), (-1, filler_idx), 1, colors.black))

        it_style.append(('SPAN', (0, subtotal_idx), (6, subtotal_idx)))
        for r in range(subtotal_idx + 1, grand_total_idx):
            it_style.append(('SPAN', (0, r), (3, r)))
            it_style.append(('SPAN', (4, r), (5, r)))

        items_table.setStyle(TableStyle(it_style))

        # onPage callback: Draws footer on EVERY page at fixed bottom position
        def draw_page_footer(canv, doc):
            footer_table.wrapOn(canv, WIDTH, FOOTER_HEIGHT)
            footer_table.drawOn(canv, MARGIN_X, 22)

        doc = BaseDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=TOP_MARGIN,
            bottomMargin=FRAME_BOTTOM,
        )
        frame = Frame(
            MARGIN_X,
            FRAME_BOTTOM,
            WIDTH,
            FRAME_HEIGHT,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
            id='normal',
        )
        doc.addPageTemplates([PageTemplate(id='All', frames=frame, pagesize=A4, onPage=draw_page_footer)])

        elements = [
            header_table,
            meta_table,
            party_table,
            items_table,
            tax_table,
            words_table,
            bank_table,
        ]

        doc.build(elements, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

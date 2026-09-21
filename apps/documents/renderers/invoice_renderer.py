import io
import logging
import os
import qrcode
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
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

from apps.documents.renderers.base import SEGOE_LOADED, ROBOTO_LOADED, FONTS_LOADED

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that counts total pages and writes
    'This is a Computer Generated Invoice' and 'Page X of Y' on every page.
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
        fnt = 'SegoeUI' if SEGOE_LOADED else ('Roboto' if ROBOTO_LOADED else 'Helvetica')
        self.setFont(fnt, 7.5)
        self.setFillColor(colors.HexColor('#64748b'))
        # Margin X = 18.8, Width = 558.0 -> Right X = 576.8
        self.drawString(18.8, 18, "This is a Computer Generated Invoice")
        self.drawRightString(576.8, 18, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


class InvoicePDFRenderer:
    """
    Renders deterministic, pixel-perfect GST Tax Invoices strictly from Canonical DTO.
    Faithfully reproduces the exact standard Indian B2B boxed document geometry
    matching golden reference INVOICE-108.pdf.
    Guarantees:
      - Continuous 1.5 pt outer rectangular border.
      - Strictly 1 single A4 page for normal invoices (<= ~7 items).
      - Seamless multi-page flow for large invoices with the complete footer
        and 'Page X of Y' present on EVERY page.
      - Zero PDF BLOBs in PostgreSQL (pure DTO snapshot).
    """

    @classmethod
    def render(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()

        PAGE_WIDTH, PAGE_HEIGHT = A4  # 595.275 x 841.89 pt
        LEFT_X = 18.8
        WIDTH = 558.0
        RIGHT_X = LEFT_X + WIDTH  # 576.8
        OUTER_TOP = 841.89 - 30.8  # 811.09 pt
        OUTER_BOTTOM = 841.89 - 798.8  # 43.09 pt
        OUTER_HEIGHT = OUTER_TOP - OUTER_BOTTOM  # 768.0 pt

        FOOTER_HEIGHT = 132.8
        FRAME_BOTTOM = OUTER_BOTTOM + FOOTER_HEIGHT  # 175.89 pt
        FRAME_HEIGHT = OUTER_TOP - FRAME_BOTTOM  # 635.2 pt

        # Extract DTO fields
        doc_meta = dto.get('document', {})
        seller = dto.get('seller', {})
        buyer = dto.get('buyer', {})
        items = dto.get('items', [])
        subtotals = dto.get('subtotals', {})
        tax_breakdown = dto.get('tax_breakdown', [])
        is_inter_state = subtotals.get('is_inter_state', False)

        # Fonts configuration
        if SEGOE_LOADED:
            f_norm = 'SegoeUI'
            f_bold = 'SegoeUI-Bold'
            f_italic = 'SegoeUI-Italic'
            f_bold_italic = 'SegoeUI-BoldItalic'
            f_semi = 'SegoeUI-Semibold'
            f_black = 'SegoeUI-Black'
        elif ROBOTO_LOADED:
            f_norm = 'Roboto'
            f_bold = 'Roboto-Bold'
            f_italic = 'Roboto-Oblique'
            f_bold_italic = 'Roboto-BoldOblique'
            f_semi = 'Roboto-Bold'
            f_black = 'Roboto-Bold'
        else:
            f_norm = 'Helvetica'
            f_bold = 'Helvetica-Bold'
            f_italic = 'Helvetica-Oblique'
            f_bold_italic = 'Helvetica-BoldOblique'
            f_semi = 'Helvetica-Bold'
            f_black = 'Helvetica-Bold'

        # Typography Styles
        s_gstin = ParagraphStyle('GSTIN', fontName=f_bold, fontSize=9.0, leading=11, textColor=colors.black)
        s_orig = ParagraphStyle('Orig', fontName=f_bold_italic, fontSize=9.0, leading=11, alignment=TA_RIGHT, textColor=colors.black)
        s_inv_title = ParagraphStyle('InvTitle', fontName=f_bold, fontSize=13.5, leading=16, alignment=TA_CENTER, textColor=colors.black)
        s_comp_name = ParagraphStyle('CompName', fontName=f_black, fontSize=22.5, leading=26, alignment=TA_CENTER, textColor=colors.black)
        s_comp_addr = ParagraphStyle('CompAddr', fontName=f_norm, fontSize=10.5, leading=13, alignment=TA_CENTER, textColor=colors.black)
        s_comp_contact = ParagraphStyle('CompContact', fontName=f_norm, fontSize=10.5, leading=13, alignment=TA_CENTER, textColor=colors.black)
        s_comp_tagline = ParagraphStyle('CompTagline', fontName=f_bold, fontSize=10.5, leading=13, alignment=TA_CENTER, textColor=colors.black)

        # ================= 1. HEADER =================
        gstin_str = seller.get('gstin', 'Unregistered')
        header_rows = [
            [
                Paragraph(f"GSTIN : <b>{gstin_str}</b>", s_gstin),
                Paragraph("Original For Recipient", s_orig)
            ],
            [Paragraph("<u>TAX INVOICE</u>", s_inv_title), ""],
            [Paragraph(seller.get('name', ''), s_comp_name), ""],
            [Paragraph(seller.get('address', ''), s_comp_addr), ""],
            [Paragraph(f"Ph: {seller.get('phone', 'N/A')} | Email: {seller.get('email', 'N/A')}", s_comp_contact), ""],
        ]
        if seller.get('tagline'):
            header_rows.append([Paragraph(seller.get('tagline').upper(), s_comp_tagline), ""])

        header_table = Table(header_rows, colWidths=[WIDTH / 2, WIDTH / 2])
        h_style = [
            ('SPAN', (0, 1), (1, 1)),
            ('SPAN', (0, 2), (1, 2)),
            ('SPAN', (0, 3), (1, 3)),
            ('SPAN', (0, 4), (1, 4)),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, 0), 6),
            ('RIGHTPADDING', (1, 0), (1, 0), 6),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 1), (-1, 1), 3),
            ('TOPPADDING', (0, 2), (-1, 2), 2),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
        ]
        if seller.get('tagline'):
            h_style.append(('SPAN', (0, 5), (1, 5)))
        header_table.setStyle(TableStyle(h_style))

        # ================= 2. META GRID =================
        s_meta_lbl = ParagraphStyle('MetaLbl', fontName=f_norm, fontSize=10.5, leading=13, textColor=colors.black)
        s_meta_val = ParagraphStyle('MetaVal', fontName=f_norm, fontSize=10.5, leading=13, textColor=colors.black)
        s_meta_val_b = ParagraphStyle('MetaValB', fontName=f_bold, fontSize=10.5, leading=13, textColor=colors.black)

        inv_no = doc_meta.get('document_number', '')
        inv_date = doc_meta.get('document_date', '')
        pos = doc_meta.get('place_of_supply', 'N/A')
        gr_rr = doc_meta.get('gr_rr_no', 'N/A')
        transport = doc_meta.get('transport', 'Road')
        vehicle_no = doc_meta.get('vehicle_no', 'N/A')
        ewb_no = doc_meta.get('eway_bill_no', 'N/A')

        meta_rows = [
            [
                Paragraph("Invoice No.", s_meta_lbl),
                Paragraph(f": <b>{inv_no}</b>", s_meta_val_b),
                Paragraph("GR/RR No.", s_meta_lbl),
                Paragraph(f": {gr_rr}", s_meta_val),
            ],
            [
                Paragraph("Dated", s_meta_lbl),
                Paragraph(f": <b>{inv_date}</b>", s_meta_val_b),
                Paragraph("Transport", s_meta_lbl),
                Paragraph(f": {transport}", s_meta_val),
            ],
            [
                Paragraph("Place of Supply", s_meta_lbl),
                Paragraph(f": {pos}", s_meta_val),
                Paragraph("Vehicle No.", s_meta_lbl),
                Paragraph(f": <b>{vehicle_no}</b>", s_meta_val_b),
            ],
            [
                Paragraph("Reverse Charge", s_meta_lbl),
                Paragraph(": N", s_meta_val),
                Paragraph("E-Way Bill No.", s_meta_lbl),
                Paragraph(f": <b>{ewb_no}</b>", s_meta_val_b),
            ],
        ]
        meta_table = Table(meta_rows, colWidths=[96, 181.4, 96, 184.6])
        meta_table.setStyle(TableStyle([
            ('LINEAFTER', (1, 0), (1, -1), 1.5, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, -1), 6),
            ('LEFTPADDING', (2, 0), (2, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # ================= 3. BILLED TO / SHIPPED TO GRID =================
        s_party_title = ParagraphStyle('PartyTitle', fontName=f_italic, fontSize=10.5, leading=13, textColor=colors.black)
        s_party_name = ParagraphStyle('PartyName', fontName=f_bold, fontSize=12.0, leading=15, textColor=colors.black)
        s_party_addr = ParagraphStyle('PartyAddr', fontName=f_norm, fontSize=10.5, leading=13, textColor=colors.black)
        s_party_gstin = ParagraphStyle('PartyGST', fontName=f_norm, fontSize=10.5, leading=13, textColor=colors.black)

        buyer_name = buyer.get('name', 'Customer')
        raw_addr = buyer.get('address', '')
        clean_addr = raw_addr.replace('\r\n', '\n').replace('\n', '<br/>').strip()
        buyer_gstin = buyer.get('gstin', 'Unregistered')

        billed_to = [
            Paragraph("<i>Billed to :</i>", s_party_title),
            Paragraph(f"<b>{buyer_name}</b>", s_party_name),
            Paragraph(clean_addr, s_party_addr),
        ]
        billed_gstin = Paragraph(f"GSTIN / UIN &nbsp;&nbsp;: <b>{buyer_gstin}</b>", s_party_gstin)

        shipped_to = [
            Paragraph("<i>Shipped to :</i>", s_party_title),
            Paragraph(f"<b>{buyer_name}</b>", s_party_name),
            Paragraph(clean_addr, s_party_addr),
        ]
        shipped_gstin = Paragraph(f"GSTIN / UIN &nbsp;&nbsp;: <b>{buyer_gstin}</b>", s_party_gstin)

        left_party_tbl = Table([
            [billed_to],
            [billed_gstin]
        ], colWidths=[277.4], rowHeights=[135.0, 25.5])
        left_party_tbl.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (0, 0), 4),
            ('BOTTOMPADDING', (0, 1), (0, 1), 4),
            ('VALIGN', (0, 0), (0, 0), 'TOP'),
            ('VALIGN', (0, 1), (0, 1), 'BOTTOM'),
        ]))

        right_party_tbl = Table([
            [shipped_to],
            [shipped_gstin]
        ], colWidths=[280.6], rowHeights=[135.0, 25.5])
        right_party_tbl.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (0, 0), 4),
            ('BOTTOMPADDING', (0, 1), (0, 1), 4),
            ('VALIGN', (0, 0), (0, 0), 'TOP'),
            ('VALIGN', (0, 1), (0, 1), 'BOTTOM'),
        ]))

        party_table = Table([[left_party_tbl, right_party_tbl]], colWidths=[277.4, 280.6])
        party_table.setStyle(TableStyle([
            ('LINEAFTER', (0, 0), (0, -1), 1.5, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # ================= 4. ITEMS TABLE =================
        col_w = [37.0, 171.8, 60.0, 48.0, 36.0, 60.0, 60.0, 85.2]

        s_th_c = ParagraphStyle('THC', fontName=f_bold, fontSize=10.5, leading=13, alignment=TA_CENTER, textColor=colors.black)
        s_th_l = ParagraphStyle('THL', fontName=f_bold, fontSize=10.5, leading=13, alignment=TA_LEFT, textColor=colors.black)
        s_th_r = ParagraphStyle('THR', fontName=f_bold, fontSize=10.5, leading=13, alignment=TA_RIGHT, textColor=colors.black)

        s_td_c = ParagraphStyle('TDC', fontName=f_norm, fontSize=10.5, leading=13, alignment=TA_CENTER, textColor=colors.black)
        s_td_l = ParagraphStyle('TDL', fontName=f_semi, fontSize=10.5, leading=13, alignment=TA_LEFT, textColor=colors.black)
        s_td_r = ParagraphStyle('TDR', fontName=f_norm, fontSize=10.5, leading=13, alignment=TA_RIGHT, textColor=colors.black)
        s_td_amt = ParagraphStyle('TDAmt', fontName=f_semi, fontSize=10.5, leading=13, alignment=TA_RIGHT, textColor=colors.black)

        items_data = [
            [
                Paragraph("S.N.", s_th_c),
                Paragraph("Description of Goods", s_th_l),
                Paragraph("HSN", s_th_c),
                Paragraph("Qty.", s_th_c),
                Paragraph("Unit", s_th_c),
                Paragraph("Price", s_th_c),
                Paragraph("Disc%", s_th_c),
                Paragraph("Amount(Rs.)", s_th_r),
            ]
        ]

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
                Paragraph(f"{taxable:,.2f}", s_td_amt),
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
        unit_label = subtotals.get('unit_label', 'PCS')

        # Subtotals and Tax rows styles
        s_sub_label = ParagraphStyle('SubLbl', fontName=f_italic, fontSize=8.2, leading=11, alignment=TA_RIGHT, textColor=colors.black)
        s_sub_rate = ParagraphStyle('SubRate', fontName=f_italic, fontSize=8.2, leading=11, alignment=TA_RIGHT, textColor=colors.black)
        s_sub_amt = ParagraphStyle('SubAmt', fontName=f_semi, fontSize=9.0, leading=11, alignment=TA_RIGHT, textColor=colors.black)

        # Dynamic filler row calculation
        h_header = header_table.wrap(WIDTH, 2000)[1]
        h_meta = meta_table.wrap(WIDTH, 2000)[1]
        h_party = party_table.wrap(WIDTH, 2000)[1]
        h_top = h_header + h_meta + h_party

        num_tax_rows = 1 if (is_inter_state or tot_igst > 0.0) else 2
        if cartage > 0.0:
            num_tax_rows += 1
        if abs(round_off) >= 0.005:
            num_tax_rows += 1

        items_content_h = 24.0 + (num_item_rows * 27.0) + 17.0 + (num_tax_rows * 17.0) + 21.0
        h_tax_est = 33.2
        h_words_est = 27.0
        h_bank_est = 38.3
        total_needed = h_top + items_content_h + h_tax_est + h_words_est + h_bank_est

        is_single_page = total_needed <= FRAME_HEIGHT

        filler_idx = -1
        filler_height = 0
        if is_single_page:
            filler_height = max(0.0, FRAME_HEIGHT - total_needed)
            if filler_height > 2.0:
                filler_idx = len(items_data)
                items_data.append(["", "", "", "", "", "", "", ""])

        # Subtotal row
        subtotal_idx = len(items_data)
        items_data.append([
            "", "", "", "", "", "", "",
            Paragraph(f"{tot_taxable:,.2f}", s_sub_amt)
        ])

        # Taxes rows
        if is_inter_state or tot_igst > 0.0:
            rate_disp = f"@ {first_item_gst:.2f} %"
            items_data.append([
                "", "", "", "",
                Paragraph("Add : IGST", s_sub_label),
                "",
                Paragraph(rate_disp, s_sub_rate),
                Paragraph(f"{tot_igst:,.2f}", s_sub_amt)
            ])
        else:
            half_rate = f"@ {(first_item_gst / 2.0):.2f} %"
            items_data.append([
                "", "", "", "",
                Paragraph("Add : CGST", s_sub_label),
                "",
                Paragraph(half_rate, s_sub_rate),
                Paragraph(f"{tot_cgst:,.2f}", s_sub_amt)
            ])
            items_data.append([
                "", "", "", "",
                Paragraph("Add : SGST", s_sub_label),
                "",
                Paragraph(half_rate, s_sub_rate),
                Paragraph(f"{tot_sgst:,.2f}", s_sub_amt)
            ])

        if cartage > 0.0:
            items_data.append([
                "", "", "", "",
                Paragraph("Add : Cartage", s_sub_label),
                "", "",
                Paragraph(f"{cartage:,.2f}", s_sub_amt)
            ])

        if abs(round_off) >= 0.005:
            lbl = "Add : Round Off" if round_off > 0.0 else "Less : Round Off"
            sign_str = f"+{round_off:.2f}" if round_off > 0.0 else f"{round_off:.2f}"
            items_data.append([
                "", "", "", "",
                Paragraph(lbl, s_sub_label),
                "", "",
                Paragraph(sign_str, s_sub_amt)
            ])

        # Grand Total row
        grand_total_idx = len(items_data)
        s_gt_lbl = ParagraphStyle('GTLbl', fontName=f_bold, fontSize=9.0, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_gt_qty = ParagraphStyle('GTQty', fontName=f_bold, fontSize=9.0, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_gt_amt = ParagraphStyle('GTAmt', fontName=f_bold, fontSize=9.0, leading=12, alignment=TA_RIGHT, textColor=colors.black)

        items_data.append([
            Paragraph("Grand Total", s_gt_lbl),
            "", "", "", "",
            Paragraph(f"<u>&nbsp;&nbsp;{tot_qty:.2f} {unit_label}&nbsp;&nbsp;</u>", s_gt_qty),
            "",
            Paragraph(f"{final_grand_total:,.2f}", s_gt_amt)
        ])

        # Row heights configuration
        if filler_idx > 0:
            row_heights = [24.0] + [27.0] * num_item_rows + [filler_height] + [17.0] + [17.0] * num_tax_rows + [21.0]
        else:
            row_heights = [24.0] + [27.0] * num_item_rows + [17.0] + [17.0] * num_tax_rows + [21.0]

        items_table = Table(items_data, colWidths=col_w, rowHeights=row_heights, repeatRows=1)

        it_style = [
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
            ('LINEAFTER', (0, 0), (-2, 0), 0.8, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 0), 3),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 3),
        ]

        for r in range(1, num_item_rows + 1):
            it_style.extend([
                ('LINEAFTER', (0, r), (-2, r), 0.8, colors.black),
                ('TOPPADDING', (0, r), (-1, r), 4),
                ('BOTTOMPADDING', (0, r), (-1, r), 4),
                ('LEFTPADDING', (1, r), (1, r), 6),
                ('RIGHTPADDING', (-1, r), (-1, r), 6),
                ('RIGHTPADDING', (3, r), (3, r), 4),
                ('RIGHTPADDING', (5, r), (5, r), 4),
            ])

        it_style.append(('LINEBELOW', (0, num_item_rows if filler_idx < 0 else filler_idx), (-1, num_item_rows if filler_idx < 0 else filler_idx), 0.8, colors.black))

        for r in range(subtotal_idx, grand_total_idx):
            it_style.extend([
                ('LINEAFTER', (6, r), (6, r), 0.8, colors.black),
                ('RIGHTPADDING', (-1, r), (-1, r), 6),
                ('SPAN', (0, r), (3, r)),
                ('SPAN', (4, r), (5, r)),
                ('TOPPADDING', (0, r), (-1, r), 2),
                ('BOTTOMPADDING', (0, r), (-1, r), 2),
            ])

        it_style.extend([
            ('LINEABOVE', (0, grand_total_idx), (-1, grand_total_idx), 0.8, colors.black),
            ('LINEBELOW', (0, grand_total_idx), (-1, grand_total_idx), 0.8, colors.black),
            ('LINEAFTER', (6, grand_total_idx), (6, grand_total_idx), 0.8, colors.black),
            ('SPAN', (0, grand_total_idx), (4, grand_total_idx)),
            ('SPAN', (5, grand_total_idx), (6, grand_total_idx)),
            ('RIGHTPADDING', (-1, grand_total_idx), (-1, grand_total_idx), 6),
            ('RIGHTPADDING', (0, grand_total_idx), (0, grand_total_idx), 20),
            ('TOPPADDING', (0, grand_total_idx), (-1, grand_total_idx), 3),
            ('BOTTOMPADDING', (0, grand_total_idx), (-1, grand_total_idx), 3),
        ])

        items_table.setStyle(TableStyle(it_style))

        # ================= 5. TAX SUMMARY TABLE =================
        s_tax_th_l = ParagraphStyle('TaxTHL', fontName=f_bold, fontSize=7.5, leading=9.5, alignment=TA_LEFT, textColor=colors.black)
        s_tax_th_r = ParagraphStyle('TaxTHR', fontName=f_bold, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)
        s_tax_td_l = ParagraphStyle('TaxTDL', fontName=f_norm, fontSize=7.5, leading=9.5, alignment=TA_LEFT, textColor=colors.black)
        s_tax_td_r = ParagraphStyle('TaxTDR', fontName=f_norm, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)

        tax_col_w = [48.0, 64.0, 56.0, 56.0, 56.0] if not is_inter_state else [65.0, 75.0, 70.0, 70.0]
        tax_rows = []
        if not is_inter_state:
            tax_rows.append([
                Paragraph("Tax Rate", s_tax_th_l),
                Paragraph("Taxable Amt.", s_tax_th_r),
                Paragraph("CGST Amt.", s_tax_th_r),
                Paragraph("SGST Amt.", s_tax_th_r),
                Paragraph("Total Tax", s_tax_th_r),
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
                Paragraph("Tax Rate", s_tax_th_l),
                Paragraph("Taxable Amt.", s_tax_th_r),
                Paragraph("IGST Amt.", s_tax_th_r),
                Paragraph("Total Tax", s_tax_th_r),
            ])
            for tb in tax_breakdown:
                tax_rows.append([
                    Paragraph(f"{tb['rate']:.0f}%", s_tax_td_l),
                    Paragraph(f"{tb['taxable_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['igst_amount']:,.2f}", s_tax_td_r),
                    Paragraph(f"{tb['total_tax']:,.2f}", s_tax_td_r),
                ])

        tax_subtable = Table(tax_rows, colWidths=tax_col_w)
        tax_subtable.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ]))

        tax_table = Table([[tax_subtable, ""]], colWidths=[280.0, WIDTH - 280.0])
        tax_table.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
        ]))

        # ================= 6. AMOUNT IN WORDS =================
        s_words = ParagraphStyle('Words', fontName=f_semi, fontSize=9.0, leading=12, textColor=colors.black)
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'
        words_text = f"Total Amount in Words : <b>{curr_sym} {dto.get('amount_in_words', '')}</b>"
        words_table = Table([[Paragraph(words_text, s_words)]], colWidths=[WIDTH])
        words_table.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
        ]))

        # ================= 7. BANK DETAILS =================
        b_name = seller.get('bank_name', 'Canara Bank')
        b_branch = seller.get('bank_branch', 'Govind Nagar')
        b_acc = seller.get('bank_account_number', '125008094288')
        b_ifsc = seller.get('bank_ifsc', 'CNRB0003827')

        s_bank_title = ParagraphStyle('BankT', fontName=f_bold, fontSize=9.8, leading=12, alignment=TA_CENTER, textColor=colors.black)
        s_bank_body = ParagraphStyle('BankB', fontName=f_semi, fontSize=9.0, leading=12, alignment=TA_CENTER, textColor=colors.black)

        bank_cell = [
            Paragraph("<u>BANK DETAILS</u>", s_bank_title),
            Spacer(1, 2),
            Paragraph(f"{b_name} {b_branch}, ACCOUNT NO- {b_acc}, IFSCODE: {b_ifsc}", s_bank_body)
        ]
        bank_table = Table([[bank_cell]], colWidths=[WIDTH])
        bank_table.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        # ================= 8. 3-COLUMN FOOTER (Rendered on EVERY Page) =================
        city = seller.get('city', 'Kanpur')
        terms_list = dto.get('terms', [
            "Goods once sold will not be taken back.",
            "Interest @ 18% p.a. will be charged if the payment is not made within 45 days.",
            f"Subject to '{city}' Jurisdiction only."
        ])

        s_terms_title = ParagraphStyle('TermsT', fontName=f_bold, fontSize=8.2, leading=10.5, textColor=colors.black)
        s_terms_eoe = ParagraphStyle('TermsEOE', fontName=f_bold, fontSize=9.0, leading=11.5, textColor=colors.black)
        s_terms_item = ParagraphStyle('TermsItem', fontName=f_norm, fontSize=9.0, leading=12.0, textColor=colors.black)

        terms_elements = [
            Paragraph("Terms &amp; Conditions", s_terms_title),
            Paragraph("E.&amp; O.E.", s_terms_eoe),
            Spacer(1, 2),
        ]
        for i, t in enumerate(terms_list, 1):
            terms_elements.append(Paragraph(f"{i}. {t}", s_terms_item))

        # QR Code
        qr_img = None
        try:
            upi_url = dto.get('upi_url', '')
            if upi_url:
                qr = qrcode.QRCode(version=1, box_size=3, border=0)
                qr.add_data(upi_url)
                qr.make(fit=True)
                pil_qr = qr.make_image(fill_color="black", back_color="white")
                qr_buf = io.BytesIO()
                pil_qr.save(qr_buf, format='PNG')
                qr_buf.seek(0)
                qr_img = RLImage(qr_buf, width=75.0, height=75.0)
        except Exception as e:
            logger.warning(f"Could not generate QR code: {e}")

        s_qr_lbl = ParagraphStyle('QRLbl', fontName=f_bold, fontSize=7.5, leading=9.5, alignment=TA_CENTER, textColor=colors.black)
        qr_cell = [
            Paragraph("E-Invoice QR Code", s_qr_lbl),
            Spacer(1, 6),
            qr_img if qr_img else Paragraph("", s_terms_item),
        ]

        # Signatures Cell
        s_rcvr = ParagraphStyle('Rcvr', fontName=f_bold, fontSize=8.2, leading=10.5, alignment=TA_LEFT, textColor=colors.black)
        s_auth_top = ParagraphStyle('AuthTop', fontName=f_bold, fontSize=10.5, leading=13, alignment=TA_RIGHT, textColor=colors.black)
        s_auth_bot = ParagraphStyle('AuthBot', fontName=f_bold, fontSize=10.5, leading=13, alignment=TA_RIGHT, textColor=colors.black)

        sig_img = None
        sig_url = seller.get('signature_url')
        if sig_url:
            # Handle relative URL
            sig_path = sig_url.lstrip('/')
            if os.path.exists(sig_path):
                try:
                    sig_img = RLImage(sig_path, width=32 * 2.83, height=12 * 2.83)
                except Exception:
                    sig_img = None

        comp_name_str = seller.get('name', 'Vouch')
        sig_inner = [Paragraph(f"for {comp_name_str}", s_auth_top)]
        if sig_img:
            sig_inner.append(Spacer(1, 4))
            sig_inner.append(sig_img)
            sig_inner.append(Spacer(1, 4))
        else:
            sig_inner.append(Spacer(1, 45))
        sig_inner.append(Paragraph("Authorised Signatory", s_auth_bot))

        sig_subtable = Table([
            [Paragraph("Receiver's Signature :", s_rcvr)],
            [sig_inner]
        ], colWidths=[196.6], rowHeights=[34.5, 98.3])
        sig_subtable.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, 0), 6),
            ('TOPPADDING', (0, 0), (0, 0), 4),
            ('RIGHTPADDING', (0, 1), (0, 1), 12),
            ('TOPPADDING', (0, 1), (0, 1), 6),
            ('BOTTOMPADDING', (0, 1), (0, 1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        footer_table = Table([[
            terms_elements,
            qr_cell,
            sig_subtable
        ]], colWidths=[250.4, 111.0, 196.6], rowHeights=[FOOTER_HEIGHT])
        footer_table.setStyle(TableStyle([
            ('LINEAFTER', (0, 0), (0, -1), 1.5, colors.black),
            ('LINEAFTER', (1, 0), (1, -1), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, 0), 6),
            ('RIGHTPADDING', (0, 0), (0, 0), 4),
            ('TOPPADDING', (0, 0), (0, 0), 4),
            ('BOTTOMPADDING', (0, 0), (0, 0), 4),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('TOPPADDING', (1, 0), (1, 0), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # Callback: Draws outer border and footer on EVERY page
        def draw_decorations(canv, doc):
            canv.saveState()
            canv.setLineWidth(1.5)
            canv.setStrokeColor(colors.black)
            # Continuous outer rectangle
            canv.rect(LEFT_X, OUTER_BOTTOM, WIDTH, OUTER_HEIGHT, stroke=1, fill=0)
            # Dividing line above footer
            canv.line(LEFT_X, FRAME_BOTTOM, RIGHT_X, FRAME_BOTTOM)
            # Footer table drawn at fixed bottom position on EVERY page
            footer_table.wrapOn(canv, WIDTH, FOOTER_HEIGHT)
            footer_table.drawOn(canv, LEFT_X, OUTER_BOTTOM)
            canv.restoreState()

        doc = BaseDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=LEFT_X,
            rightMargin=LEFT_X,
            topMargin=30.8,
            bottomMargin=FRAME_BOTTOM,
        )
        frame = Frame(
            LEFT_X,
            FRAME_BOTTOM,
            WIDTH,
            FRAME_HEIGHT,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
            id='normal',
        )
        doc.addPageTemplates([PageTemplate(id='All', frames=frame, pagesize=A4, onPage=draw_decorations)])

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

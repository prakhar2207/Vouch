import io
import logging
import os
import qrcode
from typing import Any, Dict, List

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
    PageBreak,
    Image as RLImage,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

from apps.documents.renderers.base import SEGOE_LOADED, ROBOTO_LOADED, FONTS_LOADED, STATE_NAMES

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that counts total pages and writes
    'This is a Computer Generated Invoice' and 'Page X of Y' on every page.
    """
    footer_text = "This is a Computer Generated Invoice"

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
        footer_msg = getattr(self, 'footer_text', self.__class__.footer_text)
        self.drawString(18.8, 18, footer_msg)
        self.drawRightString(576.8, 18, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


class InvoicePDFRenderer:
    """
    Renders deterministic, pixel-perfect GST Tax Invoices strictly from Canonical DTO.
    Faithfully reproduces the exact standard Indian B2B boxed document geometry
    matching golden reference INVOICE-108.pdf.
    Features:
      - Continuous 1.5 pt outer rectangular border.
      - Dynamic Single-Page Auto-Fit for up to 15 items (eliminates orphan 2-page splits).
      - Proportional Multi-Page Balancing with Carried Over and Brought Forward subtotal rows.
      - Vertical grid filler rows that seamlessly extend column lines down to subtotal (NO empty voids).
      - Dynamic omission of 0% discount column to widen product descriptions.
      - Recipient State & State Code display (Rule 46(e) compliant).
    """

    @classmethod
    def render(cls, dto: Dict[str, Any], watermark: bool = False, copy_type: str = 'ORIGINAL', show_brand: bool = True) -> bytes:
        copy_upper = str(copy_type or 'ORIGINAL').upper()

        if copy_upper in ['BUNDLE_LOCAL', 'BUNDLE_2']:
            pdf_rec = cls.render_single(dto, watermark=watermark, copy_type='ORIGINAL', show_brand=show_brand)
            pdf_sup = cls.render_single(dto, watermark=watermark, copy_type='SUPPLIER_LOCAL', show_brand=show_brand)
            return cls._merge_pdfs([pdf_rec, pdf_sup])
        elif copy_upper in ['BUNDLE_TRANSPORT', 'BUNDLE_3', 'ALL']:
            pdf_rec = cls.render_single(dto, watermark=watermark, copy_type='ORIGINAL', show_brand=show_brand)
            pdf_trans = cls.render_single(dto, watermark=watermark, copy_type='TRANSPORTER', show_brand=show_brand)
            pdf_sup = cls.render_single(dto, watermark=watermark, copy_type='SUPPLIER', show_brand=show_brand)
            return cls._merge_pdfs([pdf_rec, pdf_trans, pdf_sup])

        return cls.render_single(dto, watermark=watermark, copy_type=copy_upper, show_brand=show_brand)

    @staticmethod
    def _merge_pdfs(pdf_list: list) -> bytes:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for pdf_bytes in pdf_list:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    @classmethod
    def render_single(cls, dto: Dict[str, Any], watermark: bool = False, copy_type: str = 'ORIGINAL', show_brand: bool = True) -> bytes:
        buffer = io.BytesIO()

        PAGE_WIDTH, PAGE_HEIGHT = A4
        LEFT_X = 18.8
        WIDTH = 558.0
        RIGHT_X = LEFT_X + WIDTH
        OUTER_TOP = 841.89 - 30.8
        OUTER_BOTTOM = 841.89 - 798.8
        OUTER_HEIGHT = OUTER_TOP - OUTER_BOTTOM

        FOOTER_HEIGHT = 132.8
        FRAME_BOTTOM = OUTER_BOTTOM + FOOTER_HEIGHT
        FRAME_HEIGHT = OUTER_TOP - FRAME_BOTTOM

        doc_meta = dto.get('document', {})
        seller = dto.get('seller', {})
        buyer = dto.get('buyer', {})
        items = dto.get('items', [])
        show_item_description = dto.get('show_item_description', True)
        if dto.get('branding') and isinstance(dto['branding'], dict):
            show_item_description = dto['branding'].get('show_item_description', show_item_description)
        subtotals = dto.get('subtotals', {})
        tax_breakdown = dto.get('tax_breakdown', [])
        is_inter_state = subtotals.get('is_inter_state', False)
        num_item_rows = len(items)

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

        # Document Type & Mode Detection
        is_proforma = bool(dto.get('is_proforma') or dto.get('document_type') == 'PROFORMA_INVOICE' or doc_meta.get('document_type') in ['PROFORMA INVOICE', 'QUOTATION'])
        raw_doc_type = doc_meta.get('voucher_type') or dto.get('document_type') or ''
        is_credit_note = raw_doc_type == 'CREDIT_NOTE'
        is_debit_note = raw_doc_type == 'DEBIT_NOTE'

        if is_credit_note:
            doc_type_label = "CREDIT NOTE"
        elif is_debit_note:
            doc_type_label = "DEBIT NOTE"
        else:
            doc_type_label = dto.get('document_type_label') or doc_meta.get('document_type') or ('PROFORMA INVOICE' if is_proforma else 'TAX INVOICE')

        if is_proforma:
            header_title_text = f"<u>{doc_type_label.upper()}</u>"
            sub_copy_text = "Commercial Quotation" if 'QUOT' in doc_type_label.upper() else "Commercial Proforma"
            inv_no_label = "Quotation No." if 'QUOT' in doc_type_label.upper() else "Proforma No."
            canvas_footer_text = f"This is a {doc_type_label} — Not a GST Tax Invoice"
            rcvr_sig_text = "Customer Acceptance :"
        elif is_credit_note or is_debit_note:
            header_title_text = f"<u>{doc_type_label.upper()}</u>"
            sub_copy_text = "Original For Recipient"
            inv_no_label = f"{doc_type_label.title()} No."
            canvas_footer_text = f"This is a Computer Generated {doc_type_label.title()}"
            rcvr_sig_text = "Receiver's Signature :"
        else:
            header_title_text = "<u>TAX INVOICE</u>"
            copy_upper = str(copy_type or 'ORIGINAL').upper()
            if copy_upper == 'TRANSPORTER':
                sub_copy_text = "Duplicate For Transporter"
                rcvr_sig_text = "Transporter / Driver Signature :"
            elif copy_upper in ['SUPPLIER_LOCAL', 'SUPPLIER_DUPLICATE']:
                sub_copy_text = "Duplicate For Supplier"
                rcvr_sig_text = "Customer's Acknowledgment :"
            elif copy_upper == 'SUPPLIER':
                sub_copy_text = "Triplicate For Supplier"
                rcvr_sig_text = "Customer's Acknowledgment :"
            else:
                sub_copy_text = "Original For Recipient"
                rcvr_sig_text = "Receiver's Signature :"

            inv_no_label = "Invoice No."
            canvas_footer_text = f"This is a Computer Generated Invoice — {sub_copy_text}"

        # Check if invoice can fit on 1 single page via adaptive density
        # Invoices with <= 15 items and short product descriptions fit easily on 1 page!
        has_long_desc = any(bool(it.get('description') and it.get('description') != it.get('name')) for it in items) if show_item_description else False
        can_fit_single_page = (num_item_rows <= 8) or (num_item_rows <= 15 and not has_long_desc)
        is_compact_density = can_fit_single_page and (num_item_rows >= 9)

        # Dynamic Discount Column Check
        has_discounts = any(float(it.get('discount_percent', 0.0) or 0.0) > 0.001 for it in items)
        if has_discounts:
            col_w = [34.0, 174.8, 55.0, 45.0, 34.0, 55.0, 55.0, 105.2]
        else:
            col_w = [34.0, 229.8, 55.0, 45.0, 34.0, 55.0, 105.2]

        # Typography Styles based on density
        if is_compact_density:
            s_gstin = ParagraphStyle('GSTIN', fontName=f_bold, fontSize=8.5, leading=10, textColor=colors.black)
            s_orig = ParagraphStyle('Orig', fontName=f_bold_italic, fontSize=8.5, leading=10, alignment=TA_RIGHT, textColor=colors.black)
            s_inv_title = ParagraphStyle('InvTitle', fontName=f_bold, fontSize=12.0, leading=14, alignment=TA_CENTER, textColor=colors.black)
            s_comp_name = ParagraphStyle('CompName', fontName=f_black, fontSize=18.0, leading=21, alignment=TA_CENTER, textColor=colors.black)
            s_comp_addr = ParagraphStyle('CompAddr', fontName=f_norm, fontSize=9.0, leading=11, alignment=TA_CENTER, textColor=colors.black)
            s_comp_contact = ParagraphStyle('CompContact', fontName=f_norm, fontSize=9.0, leading=11, alignment=TA_CENTER, textColor=colors.black)
            s_comp_tagline = ParagraphStyle('CompTagline', fontName=f_bold, fontSize=9.0, leading=11, alignment=TA_CENTER, textColor=colors.black)

            s_meta_lbl = ParagraphStyle('MetaLbl', fontName=f_norm, fontSize=8.5, leading=10.5, textColor=colors.black)
            s_meta_val = ParagraphStyle('MetaVal', fontName=f_norm, fontSize=8.5, leading=10.5, textColor=colors.black)
            s_meta_val_b = ParagraphStyle('MetaValB', fontName=f_bold, fontSize=8.5, leading=10.5, textColor=colors.black)

            s_party_title = ParagraphStyle('PartyTitle', fontName=f_italic, fontSize=8.5, leading=10.5, textColor=colors.black)
            s_party_name = ParagraphStyle('PartyName', fontName=f_bold, fontSize=10.0, leading=12, textColor=colors.black)
            s_party_addr = ParagraphStyle('PartyAddr', fontName=f_norm, fontSize=8.5, leading=10.5, textColor=colors.black)
            s_party_gstin = ParagraphStyle('PartyGST', fontName=f_norm, fontSize=8.5, leading=10.5, textColor=colors.black)

            s_th_c = ParagraphStyle('THC', fontName=f_bold, fontSize=8.5, leading=10.5, alignment=TA_CENTER, textColor=colors.black)
            s_th_l = ParagraphStyle('THL', fontName=f_bold, fontSize=8.5, leading=10.5, alignment=TA_LEFT, textColor=colors.black)
            s_th_r = ParagraphStyle('THR', fontName=f_bold, fontSize=8.5, leading=10.5, alignment=TA_RIGHT, textColor=colors.black)

            s_td_c = ParagraphStyle('TDC', fontName=f_norm, fontSize=8.0, leading=10.0, alignment=TA_CENTER, textColor=colors.black)
            s_td_l = ParagraphStyle('TDL', fontName=f_semi, fontSize=8.0, leading=10.0, alignment=TA_LEFT, textColor=colors.black)
            s_td_brand = ParagraphStyle('TDBrand', fontName=f_bold, fontSize=6.5, leading=7.5, alignment=TA_LEFT, textColor=colors.HexColor('#475569'))
            s_td_desc = ParagraphStyle('TDDesc', fontName=f_norm, fontSize=6.5, leading=7.5, alignment=TA_LEFT, textColor=colors.HexColor('#64748b'))
            s_td_r = ParagraphStyle('TDR', fontName=f_norm, fontSize=8.0, leading=10.0, alignment=TA_RIGHT, textColor=colors.black)
            s_td_amt = ParagraphStyle('TDAmt', fontName=f_semi, fontSize=8.0, leading=10.0, alignment=TA_RIGHT, textColor=colors.black)

            s_sub_label = ParagraphStyle('SubLbl', fontName=f_italic, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)
            s_sub_rate = ParagraphStyle('SubRate', fontName=f_italic, fontSize=7.5, leading=9.5, alignment=TA_RIGHT, textColor=colors.black)
            s_sub_amt = ParagraphStyle('SubAmt', fontName=f_semi, fontSize=8.0, leading=10.0, alignment=TA_RIGHT, textColor=colors.black)

            s_gt_lbl = ParagraphStyle('GTLbl', fontName=f_bold, fontSize=8.5, leading=11, alignment=TA_RIGHT, textColor=colors.black)
            s_gt_qty = ParagraphStyle('GTQty', fontName=f_bold, fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.black)
            s_gt_amt = ParagraphStyle('GTAmt', fontName=f_bold, fontSize=8.5, leading=11, alignment=TA_RIGHT, textColor=colors.black)

            item_row_h = 18.0
            th_h = 18.0
        else:
            s_gstin = ParagraphStyle('GSTIN', fontName=f_bold, fontSize=9.0, leading=11, textColor=colors.black)
            s_orig = ParagraphStyle('Orig', fontName=f_bold_italic, fontSize=9.0, leading=11, alignment=TA_RIGHT, textColor=colors.black)
            s_inv_title = ParagraphStyle('InvTitle', fontName=f_bold, fontSize=13.5, leading=16, alignment=TA_CENTER, textColor=colors.black)
            s_comp_name = ParagraphStyle('CompName', fontName=f_black, fontSize=21.0, leading=25, alignment=TA_CENTER, textColor=colors.black)
            s_comp_addr = ParagraphStyle('CompAddr', fontName=f_norm, fontSize=10.0, leading=12.5, alignment=TA_CENTER, textColor=colors.black)
            s_comp_contact = ParagraphStyle('CompContact', fontName=f_norm, fontSize=10.0, leading=12.5, alignment=TA_CENTER, textColor=colors.black)
            s_comp_tagline = ParagraphStyle('CompTagline', fontName=f_bold, fontSize=10.0, leading=12.5, alignment=TA_CENTER, textColor=colors.black)

            s_meta_lbl = ParagraphStyle('MetaLbl', fontName=f_norm, fontSize=9.5, leading=12, textColor=colors.black)
            s_meta_val = ParagraphStyle('MetaVal', fontName=f_norm, fontSize=9.5, leading=12, textColor=colors.black)
            s_meta_val_b = ParagraphStyle('MetaValB', fontName=f_bold, fontSize=9.5, leading=12, textColor=colors.black)

            s_party_title = ParagraphStyle('PartyTitle', fontName=f_italic, fontSize=9.5, leading=12, textColor=colors.black)
            s_party_name = ParagraphStyle('PartyName', fontName=f_bold, fontSize=11.0, leading=14, textColor=colors.black)
            s_party_addr = ParagraphStyle('PartyAddr', fontName=f_norm, fontSize=9.5, leading=12, textColor=colors.black)
            s_party_gstin = ParagraphStyle('PartyGST', fontName=f_norm, fontSize=9.5, leading=12, textColor=colors.black)

            s_th_c = ParagraphStyle('THC', fontName=f_bold, fontSize=9.5, leading=12, alignment=TA_CENTER, textColor=colors.black)
            s_th_l = ParagraphStyle('THL', fontName=f_bold, fontSize=9.5, leading=12, alignment=TA_LEFT, textColor=colors.black)
            s_th_r = ParagraphStyle('THR', fontName=f_bold, fontSize=9.5, leading=12, alignment=TA_RIGHT, textColor=colors.black)

            s_td_c = ParagraphStyle('TDC', fontName=f_norm, fontSize=9.0, leading=11.5, alignment=TA_CENTER, textColor=colors.black)
            s_td_l = ParagraphStyle('TDL', fontName=f_semi, fontSize=9.0, leading=11.5, alignment=TA_LEFT, textColor=colors.black)
            s_td_brand = ParagraphStyle('TDBrand', fontName=f_bold, fontSize=7.0, leading=8.5, alignment=TA_LEFT, textColor=colors.HexColor('#475569'))
            s_td_desc = ParagraphStyle('TDDesc', fontName=f_norm, fontSize=7.0, leading=8.5, alignment=TA_LEFT, textColor=colors.HexColor('#64748b'))
            s_td_r = ParagraphStyle('TDR', fontName=f_norm, fontSize=9.0, leading=11.5, alignment=TA_RIGHT, textColor=colors.black)
            s_td_amt = ParagraphStyle('TDAmt', fontName=f_semi, fontSize=9.0, leading=11.5, alignment=TA_RIGHT, textColor=colors.black)

            s_sub_label = ParagraphStyle('SubLbl', fontName=f_italic, fontSize=8.0, leading=10, alignment=TA_RIGHT, textColor=colors.black)
            s_sub_rate = ParagraphStyle('SubRate', fontName=f_italic, fontSize=8.0, leading=10, alignment=TA_RIGHT, textColor=colors.black)
            s_sub_amt = ParagraphStyle('SubAmt', fontName=f_semi, fontSize=8.5, leading=11, alignment=TA_RIGHT, textColor=colors.black)

            s_gt_lbl = ParagraphStyle('GTLbl', fontName=f_bold, fontSize=9.0, leading=12, alignment=TA_RIGHT, textColor=colors.black)
            s_gt_qty = ParagraphStyle('GTQty', fontName=f_bold, fontSize=9.0, leading=12, alignment=TA_CENTER, textColor=colors.black)
            s_gt_amt = ParagraphStyle('GTAmt', fontName=f_bold, fontSize=9.0, leading=12, alignment=TA_RIGHT, textColor=colors.black)

            item_row_h = 24.0
            th_h = 20.0

        # ================= 1. HEADER =================
        gstin_str = seller.get('gstin', 'Unregistered')
        header_rows = [
            [
                Paragraph(f"GSTIN : <b>{gstin_str}</b>", s_gstin),
                Paragraph(sub_copy_text, s_orig)
            ],
            [Paragraph(header_title_text, s_inv_title), ""],
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
            ('LEFTPADDING', (0, 0), (0, 0), 4),
            ('RIGHTPADDING', (1, 0), (1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 1.5 if is_compact_density else 3),
            ('TOPPADDING', (0, 1), (-1, 1), 1.5 if is_compact_density else 2),
            ('TOPPADDING', (0, 2), (-1, 2), 1),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 2 if is_compact_density else 3),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
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
        valid_until = doc_meta.get('valid_until')
        orig_inv_no = doc_meta.get('original_invoice_number') or doc_meta.get('reference_number') or 'N/A'

        if is_credit_note or is_debit_note:
            meta_rows = [
                [
                    Paragraph(inv_no_label, s_meta_lbl),
                    Paragraph(f": <b>{inv_no}</b>", s_meta_val_b),
                    Paragraph("Original Inv No.", s_meta_lbl),
                    Paragraph(f": <b>{orig_inv_no}</b>", s_meta_val_b),
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
        else:
            meta_rows = [
                [
                    Paragraph(inv_no_label, s_meta_lbl),
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
                    Paragraph("Valid Until" if (is_proforma and valid_until) else "Reverse Charge", s_meta_lbl),
                    Paragraph(f": <b>{valid_until}</b>" if (is_proforma and valid_until) else ": N", s_meta_val_b if (is_proforma and valid_until) else s_meta_val),
                    Paragraph("E-Way Bill No.", s_meta_lbl),
                    Paragraph(f": <b>{ewb_no}</b>", s_meta_val_b),
                ],
            ]
        meta_table = Table(meta_rows, colWidths=[96, 181.4, 96, 184.6])
        meta_table.setStyle(TableStyle([
            ('LINEAFTER', (1, 0), (1, -1), 1.5, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, -1), 4),
            ('LEFTPADDING', (2, 0), (2, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 0.5 if is_compact_density else 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5 if is_compact_density else 1.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # ================= 3. BILLED TO / SHIPPED TO GRID =================
        buyer_name = buyer.get('name', 'Customer')
        raw_addr = buyer.get('address', '')
        clean_addr = raw_addr.replace('\r\n', '\n').replace('\n', '<br/>').strip()
        buyer_gstin = buyer.get('gstin', 'Unregistered')
        buyer_state_code = buyer.get('state_code', '')
        buyer_state_name = STATE_NAMES.get(buyer_state_code, '')

        state_suffix = ""
        if buyer_state_name and buyer_state_code:
            state_suffix = f" | State: {buyer_state_name} ({buyer_state_code})"
        elif buyer_state_code:
            state_suffix = f" | State Code: {buyer_state_code}"

        billed_elements = [
            Paragraph("<i>Billed to :</i>", s_party_title),
            Paragraph(f"<b>{buyer_name}</b>", s_party_name),
        ]
        if clean_addr:
            billed_elements.append(Paragraph(clean_addr, s_party_addr))

        shipped_elements = [
            Paragraph("<i>Shipped to :</i>", s_party_title),
            Paragraph(f"<b>{buyer_name}</b>", s_party_name),
        ]
        if clean_addr:
            shipped_elements.append(Paragraph(clean_addr, s_party_addr))

        billed_gstin = Paragraph(f"GSTIN / UIN : <b>{buyer_gstin}</b>{state_suffix}", s_party_gstin)
        shipped_gstin = Paragraph(f"GSTIN / UIN : <b>{buyer_gstin}</b>{state_suffix}", s_party_gstin)

        party_table = Table([
            [billed_elements, shipped_elements],
            [billed_gstin, shipped_gstin]
        ], colWidths=[277.4, 280.6])
        party_table.setStyle(TableStyle([
            ('LINEAFTER', (0, 0), (0, -1), 1.5, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 1 if is_compact_density else 3),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 1 if is_compact_density else 3),
            ('TOPPADDING', (0, 1), (-1, 1), 0.5 if is_compact_density else 2),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 1 if is_compact_density else 3),
            ('VALIGN', (0, 0), (-1, 0), 'TOP'),
            ('VALIGN', (0, 1), (-1, 1), 'MIDDLE'),
        ]))

        # Subtotals and calculations
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

        # Items Table Column Header
        th_row = [
            Paragraph("S.N.", s_th_c),
            Paragraph("Description of Goods", s_th_l),
            Paragraph("HSN", s_th_c),
            Paragraph("Qty.", s_th_c),
            Paragraph("Unit", s_th_c),
            Paragraph("Price", s_th_c),
        ]
        if has_discounts:
            th_row.append(Paragraph("Disc%", s_th_c))
        th_row.append(Paragraph("Amount(Rs.)", s_th_r))

        row_len = len(th_row)

        def build_item_row(itm):
            sn = str(itm.get('sn', ''))
            p_name = itm.get('name', 'Item')
            hsn = str(itm.get('hsn_code', ''))
            qty = itm.get('quantity', 0.0)
            unit = itm.get('unit', 'PCS')
            rate = itm.get('rate', 0.0)
            disc_pct = itm.get('discount_percent', 0.0)
            taxable = itm.get('taxable_amount', 0.0)
            brand = (itm.get('brand') or '').strip()
            desc = (itm.get('description') or '').strip()

            desc_elements = [Paragraph(p_name, s_td_l)]
            if show_brand and brand:
                desc_elements.append(Paragraph(
                    f"<b>BRAND:</b> {brand}",
                    s_td_brand
                ))
            if show_item_description and desc and desc != p_name:
                desc_elements.append(Paragraph(
                    desc,
                    s_td_desc
                ))

            res = [
                Paragraph(sn, s_td_c),
                desc_elements if len(desc_elements) > 1 else desc_elements[0],
                Paragraph(hsn, s_td_c),
                Paragraph(f"{qty:.2f}", s_td_r),
                Paragraph(unit, s_td_c),
                Paragraph(f"{rate:.2f}", s_td_r),
            ]
            if has_discounts:
                res.append(Paragraph(f"{disc_pct:.2f}%" if disc_pct > 0 else "0.00%", s_td_c))
            res.append(Paragraph(f"{taxable:,.2f}", s_td_amt))
            return res

        def calc_item_row_height(itm, base_h):
            p_name = itm.get('name', 'Item')
            brand = (itm.get('brand') or '').strip() if show_brand else ''
            desc = (itm.get('description') or '').strip() if show_item_description else ''

            desc_w = col_w[1] - 8.0
            h_name = Paragraph(p_name, s_td_l).wrap(desc_w, 2000)[1]
            h_brand = Paragraph(f"<b>BRAND:</b> {brand}", s_td_brand).wrap(desc_w, 2000)[1] if brand else 0.0
            h_desc = Paragraph(desc, s_td_desc).wrap(desc_w, 2000)[1] if (desc and desc != p_name) else 0.0

            needed = h_name + h_brand + h_desc + 4.0
            return max(base_h, needed)

        # ================= 5. TAX SUMMARY SUBTABLE =================
        s_tax_th_l = ParagraphStyle('TaxTHL', fontName=f_bold, fontSize=7.0, leading=8.5, alignment=TA_LEFT, textColor=colors.black)
        s_tax_th_r = ParagraphStyle('TaxTHR', fontName=f_bold, fontSize=7.0, leading=8.5, alignment=TA_RIGHT, textColor=colors.black)
        s_tax_td_l = ParagraphStyle('TaxTDL', fontName=f_norm, fontSize=7.0, leading=8.5, alignment=TA_LEFT, textColor=colors.black)
        s_tax_td_r = ParagraphStyle('TaxTDR', fontName=f_norm, fontSize=7.0, leading=8.5, alignment=TA_RIGHT, textColor=colors.black)

        tax_col_w = [45.0, 60.0, 52.0, 52.0, 52.0] if not is_inter_state else [65.0, 75.0, 60.0, 60.0]
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
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))

        tax_table = Table([[tax_subtable, ""]], colWidths=[265.0, WIDTH - 265.0])
        tax_table.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5 if is_compact_density else 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5 if is_compact_density else 3),
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
        ]))

        # ================= 6. AMOUNT IN WORDS =================
        s_words = ParagraphStyle('Words', fontName=f_semi, fontSize=8.5, leading=11, textColor=colors.black)
        curr_sym = '\\u20B9' if FONTS_LOADED else 'Rs.'
        words_text = f"Total Amount in Words : <b>{curr_sym} {dto.get('amount_in_words', '')}</b>"
        words_table = Table([[Paragraph(words_text, s_words)]], colWidths=[WIDTH])
        words_table.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5 if is_compact_density else 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5 if is_compact_density else 4),
            ('LINEBELOW', (0, -1), (-1, -1), 0.8, colors.black),
        ]))

        # ================= 7. BANK DETAILS =================
        b_name = (seller.get('bank_name') or seller.get('bank', {}).get('bank_name') or '').strip()
        b_branch = (seller.get('bank_branch') or seller.get('bank', {}).get('branch') or '').strip()
        b_acc = (seller.get('bank_account_number') or seller.get('bank', {}).get('account_number') or '').strip()
        b_ifsc = (seller.get('bank_ifsc') or seller.get('bank', {}).get('ifsc') or '').strip()
        upi_id = (seller.get('upi_id') or seller.get('bank_upi_id') or seller.get('bank', {}).get('upi_id') or '').strip()

        s_bank_title = ParagraphStyle('BankT', fontName=f_bold, fontSize=9.0, leading=11, alignment=TA_CENTER, textColor=colors.black)
        s_bank_body = ParagraphStyle('BankB', fontName=f_semi, fontSize=8.0, leading=10, alignment=TA_CENTER, textColor=colors.black)

        if b_name or b_acc or upi_id:
            bank_parts = []
            if b_name:
                b_str = b_name
                if b_branch:
                    b_str += f" {b_branch}"
                bank_parts.append(b_str)
            if b_acc:
                bank_parts.append(f"ACCOUNT NO- {b_acc}")
            if b_ifsc:
                bank_parts.append(f"IFSCODE: {b_ifsc}")
            if upi_id:
                bank_parts.append(f"UPI ID: {upi_id}")

            bank_detail_text = ", ".join(bank_parts)
            bank_cell = [
                Paragraph("<u>BANK DETAILS</u>", s_bank_title),
                Spacer(1, 1),
                Paragraph(bank_detail_text, s_bank_body)
            ]
        else:
            bank_cell = [Paragraph("", s_bank_body)]

        bank_table = Table([[bank_cell]], colWidths=[WIDTH])
        bank_table.setStyle(TableStyle([
            ('PADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2 if is_compact_density else 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 if is_compact_density else 3),
        ]))

        # ================= 8. 3-COLUMN FOOTER =================
        city = seller.get('city', 'Kanpur')
        terms_list = dto.get('terms', [
            "Goods once sold will not be taken back.",
            "Interest @ 18% p.a. will be charged if the payment is not made within 45 days.",
            f"Subject to '{city}' Jurisdiction only."
        ])

        if is_proforma:
            custom_terms = doc_meta.get('terms_and_conditions') or dto.get('terms_and_conditions') or doc_meta.get('narration')
            if custom_terms and isinstance(custom_terms, str) and custom_terms.strip():
                terms_list = [t.strip() for t in custom_terms.split('\\n') if t.strip()][:4]
            else:
                terms_list = [
                    "Prices valid for 15 days from date of issue.",
                    "100% advance payment required prior to dispatch.",
                    f"Subject to '{city}' Jurisdiction only."
                ]

        s_terms_title = ParagraphStyle('TermsT', fontName=f_bold, fontSize=8.0, leading=10, textColor=colors.black)
        s_terms_eoe = ParagraphStyle('TermsEOE', fontName=f_bold, fontSize=8.5, leading=10.5, textColor=colors.black)
        s_terms_item = ParagraphStyle('TermsItem', fontName=f_norm, fontSize=8.0, leading=10.5, textColor=colors.black)

        terms_elements = [
            Paragraph("Terms &amp; Conditions", s_terms_title),
            Paragraph("E.&amp; O.E.", s_terms_eoe),
            Spacer(1, 2),
        ]
        for i, t in enumerate(terms_list, 1):
            terms_elements.append(Paragraph(f"{i}. {t}", s_terms_item))

        cust_notes = (dto.get('customer_notes') or doc_meta.get('narration') or dto.get('narration') or '').strip()
        if cust_notes:
            terms_elements.append(Spacer(1, 2))
            terms_elements.append(Paragraph(f"<b>Notes:</b> {cust_notes}", s_terms_item))

        # QR Code
        qr_img = None
        upi_url = dto.get('upi_url') or seller.get('bank', {}).get('upi_url') or ''
        try:
            if upi_url:
                qr = qrcode.QRCode(version=1, box_size=3, border=0)
                qr.add_data(upi_url)
                qr.make(fit=True)
                pil_qr = qr.make_image(fill_color="black", back_color="white")
                qr_buf = io.BytesIO()
                pil_qr.save(qr_buf, format='PNG')
                qr_buf.seek(0)
                qr_img = RLImage(qr_buf, width=68.0, height=68.0)
        except Exception as e:
            logger.warning(f"Could not generate QR code: {e}")

        s_qr_lbl = ParagraphStyle('QRLbl', fontName=f_bold, fontSize=7.0, leading=9.0, alignment=TA_CENTER, textColor=colors.black)
        s_qr_upi = ParagraphStyle('QRUpi', fontName=f_semi, fontSize=6.0, leading=7.2, alignment=TA_CENTER, textColor=colors.black)

        if qr_img:
            qr_title = "UPI Payment QR" if upi_url else "E-Invoice QR Code"
            qr_cell = [
                Paragraph(qr_title, s_qr_lbl),
                Spacer(1, 2),
                qr_img,
            ]
            if upi_id:
                qr_cell.extend([
                    Spacer(1, 2),
                    Paragraph(f"UPI: {upi_id}", s_qr_upi)
                ])
        else:
            qr_cell = [Paragraph("", s_terms_item)]

        # Signatures Cell
        s_rcvr = ParagraphStyle('Rcvr', fontName=f_bold, fontSize=8.0, leading=10, alignment=TA_LEFT, textColor=colors.black)
        s_auth_top = ParagraphStyle('AuthTop', fontName=f_bold, fontSize=9.5, leading=12, alignment=TA_RIGHT, textColor=colors.black)
        s_auth_bot = ParagraphStyle('AuthBot', fontName=f_bold, fontSize=9.5, leading=12, alignment=TA_RIGHT, textColor=colors.black)

        sig_img = None
        sig_url = seller.get('signature_url')
        if sig_url:
            if isinstance(sig_url, str) and sig_url.startswith('data:image'):
                try:
                    import base64
                    _, b64data = sig_url.split(',', 1)
                    sig_buf = io.BytesIO(base64.b64decode(b64data))
                    sig_img = RLImage(sig_buf, width=32 * 2.83, height=12 * 2.83)
                except Exception:
                    sig_img = None
            else:
                sig_path = sig_url.lstrip('/')
                if os.path.exists(sig_path):
                    try:
                        sig_img = RLImage(sig_path, width=32 * 2.83, height=12 * 2.83)
                    except Exception:
                        sig_img = None

        comp_name_str = seller.get('name', 'SriLekh')
        sig_inner = [Paragraph(f"for {comp_name_str}", s_auth_top)]
        if sig_img:
            sig_inner.append(Spacer(1, 4))
            sig_inner.append(sig_img)
            sig_inner.append(Spacer(1, 4))
        else:
            sig_inner.append(Spacer(1, 38))
        sig_inner.append(Paragraph("Authorised Signatory", s_auth_bot))

        sig_subtable = Table([
            [Paragraph(rcvr_sig_text, s_rcvr)],
            [sig_inner]
        ], colWidths=[196.6], rowHeights=[30.0, 102.8])
        sig_subtable.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
            ('PADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (0, 0), 4),
            ('TOPPADDING', (0, 0), (0, 0), 2),
            ('RIGHTPADDING', (0, 1), (0, 1), 8),
            ('TOPPADDING', (0, 1), (0, 1), 4),
            ('BOTTOMPADDING', (0, 1), (0, 1), 4),
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
            ('LEFTPADDING', (0, 0), (0, 0), 4),
            ('RIGHTPADDING', (0, 0), (0, 0), 4),
            ('TOPPADDING', (0, 0), (0, 0), 2),
            ('BOTTOMPADDING', (0, 0), (0, 0), 2),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        # Measure top sections and summary tables directly
        h_h = header_table.wrap(WIDTH, 2000)[1]
        h_m = meta_table.wrap(WIDTH, 2000)[1]
        h_p = party_table.wrap(WIDTH, 2000)[1]
        h_top = h_h + h_m + h_p

        h_tax = tax_table.wrap(WIDTH, 2000)[1]
        h_words = words_table.wrap(WIDTH, 2000)[1]
        h_bank = bank_table.wrap(WIDTH, 2000)[1]
        h_summary = h_tax + h_words + h_bank

        # Number of tax rows in totals
        num_tax_rows = 1 if (is_inter_state or tot_igst > 0.0) else 2
        if cartage > 0.0:
            num_tax_rows += 1
        if abs(round_off) >= 0.005:
            num_tax_rows += 1

        sub_tax_rows_h = 14.0 + (num_tax_rows * 14.0) + 18.0

        # ==============================================================
        # SCENARIO A: SINGLE PAGE FIT
        # ==============================================================
        if can_fit_single_page:
            items_data = [th_row]
            item_row_heights = []
            for itm in items:
                items_data.append(build_item_row(itm))
                item_row_heights.append(calc_item_row_height(itm, item_row_h))

            # Calculate remaining space for filler row
            used_h = h_top + th_h + sum(item_row_heights) + sub_tax_rows_h + h_summary
            filler_h = max(2.0, FRAME_HEIGHT - used_h)

            filler_idx = len(items_data)
            items_data.append([""] * row_len)

            # Subtotal row
            subtotal_idx = len(items_data)
            sub_r = [""] * row_len
            sub_r[-1] = Paragraph(f"{tot_taxable:,.2f}", s_sub_amt)
            items_data.append(sub_r)

            # Taxes
            if is_inter_state or tot_igst > 0.0:
                rate_disp = f"@ {first_item_gst:.2f} %"
                r_tax = [""] * row_len
                r_tax[-4] = Paragraph("Add : IGST", s_sub_label)
                r_tax[-2] = Paragraph(rate_disp, s_sub_rate)
                r_tax[-1] = Paragraph(f"{tot_igst:,.2f}", s_sub_amt)
                items_data.append(r_tax)
            else:
                half_rate = f"@ {(first_item_gst / 2.0):.2f} %"
                r_cgst = [""] * row_len
                r_cgst[-4] = Paragraph("Add : CGST", s_sub_label)
                r_cgst[-2] = Paragraph(half_rate, s_sub_rate)
                r_cgst[-1] = Paragraph(f"{tot_cgst:,.2f}", s_sub_amt)
                items_data.append(r_cgst)

                r_sgst = [""] * row_len
                r_sgst[-4] = Paragraph("Add : SGST", s_sub_label)
                r_sgst[-2] = Paragraph(half_rate, s_sub_rate)
                r_sgst[-1] = Paragraph(f"{tot_sgst:,.2f}", s_sub_amt)
                items_data.append(r_sgst)

            if cartage > 0.0:
                r_cart = [""] * row_len
                r_cart[-4] = Paragraph("Add : Cartage", s_sub_label)
                r_cart[-1] = Paragraph(f"{cartage:,.2f}", s_sub_amt)
                items_data.append(r_cart)

            if abs(round_off) >= 0.005:
                lbl = "Add : Round Off" if round_off > 0 else "Less : Round Off"
                sign_str = f"+{round_off:.2f}" if round_off > 0 else f"{round_off:.2f}"
                r_ro = [""] * row_len
                r_ro[-4] = Paragraph(lbl, s_sub_label)
                r_ro[-1] = Paragraph(sign_str, s_sub_amt)
                items_data.append(r_ro)

            # Grand Total
            grand_total_idx = len(items_data)
            gt_r = [""] * row_len
            gt_r[0] = Paragraph("Grand Total", s_gt_lbl)
            gt_r[-3] = Paragraph(f"<u>&nbsp;&nbsp;{tot_qty:.2f} {unit_label}&nbsp;&nbsp;</u>", s_gt_qty)
            gt_r[-1] = Paragraph(f"{final_grand_total:,.2f}", s_gt_amt)
            items_data.append(gt_r)

            row_heights = [th_h] + item_row_heights + [filler_h] + [14.0] + [14.0] * num_tax_rows + [18.0]
            items_table = Table(items_data, colWidths=col_w, rowHeights=row_heights)

            it_style = [
                ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
                ('LINEAFTER', (0, 0), (-2, 0), 0.8, colors.black),
                ('PADDING', (0, 0), (-1, -1), 0),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, 0), 2),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ]
            for r_idx in range(1, num_item_rows + 1):
                it_style.extend([
                    ('LINEAFTER', (0, r_idx), (-2, r_idx), 0.8, colors.black),
                    ('LINEBELOW', (0, r_idx), (-1, r_idx), 0.8, colors.black),
                    ('TOPPADDING', (0, r_idx), (-1, r_idx), 2.0),
                    ('BOTTOMPADDING', (0, r_idx), (-1, r_idx), 2.0),
                    ('LEFTPADDING', (1, r_idx), (1, r_idx), 4),
                    ('RIGHTPADDING', (-1, r_idx), (-1, r_idx), 4),
                    ('VALIGN', (1, r_idx), (1, r_idx), 'TOP'),
                ])

            # Filler row styling: continues vertical lines down to subtotal
            it_style.extend([
                ('LINEAFTER', (0, filler_idx), (-2, filler_idx), 0.8, colors.black),
                ('LINEBELOW', (0, filler_idx), (-1, filler_idx), 0.8, colors.black),
            ])

            for r_idx in range(subtotal_idx, grand_total_idx):
                it_style.extend([
                    ('LINEAFTER', (-2, r_idx), (-2, r_idx), 0.8, colors.black),
                    ('RIGHTPADDING', (-1, r_idx), (-1, r_idx), 4),
                    ('SPAN', (0, r_idx), (-5, r_idx)),
                    ('SPAN', (-4, r_idx), (-3, r_idx)),
                    ('TOPPADDING', (0, r_idx), (-1, r_idx), 1),
                    ('BOTTOMPADDING', (0, r_idx), (-1, r_idx), 1),
                ])

            it_style.extend([
                ('LINEABOVE', (0, grand_total_idx), (-1, grand_total_idx), 0.8, colors.black),
                ('LINEBELOW', (0, grand_total_idx), (-1, grand_total_idx), 0.8, colors.black),
                ('LINEAFTER', (-2, grand_total_idx), (-2, grand_total_idx), 0.8, colors.black),
                ('SPAN', (0, grand_total_idx), (-4, grand_total_idx)),
                ('SPAN', (-3, grand_total_idx), (-2, grand_total_idx)),
                ('RIGHTPADDING', (-1, grand_total_idx), (-1, grand_total_idx), 4),
                ('TOPPADDING', (0, grand_total_idx), (-1, grand_total_idx), 2),
                ('BOTTOMPADDING', (0, grand_total_idx), (-1, grand_total_idx), 2),
            ])
            items_table.setStyle(TableStyle(it_style))

            elements = [
                header_table,
                meta_table,
                party_table,
                items_table,
                tax_table,
                words_table,
                bank_table,
            ]

        # ==============================================================
        # SCENARIO B: MULTI-PAGE BALANCED FIT (16+ items or multi-line)
        # ==============================================================
        else:
            # Proportional distribution:
            if num_item_rows <= 24:
                p1_count = max(8, min(14, int(num_item_rows * 0.58)))
                chunks = [items[:p1_count], items[p1_count:]]
            else:
                chunks = []
                rem = list(items)
                chunks.append(rem[:12])
                rem = rem[12:]
                while rem:
                    if len(rem) <= 10:
                        chunks.append(rem)
                        break
                    else:
                        take = min(15, len(rem) - 5)
                        chunks.append(rem[:take])
                        rem = rem[take:]

            total_pages = len(chunks)
            elements = []
            running_taxable = 0.0

            for p_idx, chunk_items in enumerate(chunks):
                p_num = p_idx + 1
                is_first = (p_num == 1)
                is_last = (p_num == total_pages)
                chunk_len = len(chunk_items)

                p_data = [th_row]

                # If not first page, add Brought Forward row
                if not is_first:
                    bf_r = [""] * row_len
                    bf_r[0] = Paragraph(f"<b>Brought Forward from Page {p_num - 1}</b>", s_sub_label)
                    bf_r[-1] = Paragraph(f"<b>{running_taxable:,.2f}</b>", s_sub_amt)
                    p_data.append(bf_r)

                chunk_taxable = 0.0
                for itm in chunk_items:
                    amt = float(itm.get('taxable_amount') or 0.0)
                    chunk_taxable += amt
                    p_data.append(build_item_row(itm))

                running_taxable += chunk_taxable

                if is_first:
                    # Page 1 top height: h_top
                    # P1 Items: th_h + (chunk_len * item_row_h) + Carried Over (16 pt)
                    p1_chunk_r_heights = [calc_item_row_height(itm, item_row_h) for itm in chunk_items]
                    p1_used = h_top + th_h + sum(p1_chunk_r_heights) + 16.0
                    p1_filler_h = max(4.0, FRAME_HEIGHT - p1_used)

                    p1_filler_idx = len(p_data)
                    p_data.append([""] * row_len)

                    # Carried Over row
                    co_r = [""] * row_len
                    co_r[0] = Paragraph(f"<b>Carried Over to Page {p_num + 1}</b>", s_sub_label)
                    co_r[-1] = Paragraph(f"<b>{running_taxable:,.2f}</b>", s_sub_amt)
                    p_data.append(co_r)

                    p1_r_heights = [th_h] + p1_chunk_r_heights + [p1_filler_h, 16.0]
                    p1_table = Table(p_data, colWidths=col_w, rowHeights=p1_r_heights)

                    p1_s = [
                        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
                        ('LINEAFTER', (0, 0), (-2, 0), 0.8, colors.black),
                        ('PADDING', (0, 0), (-1, -1), 0),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]
                    for r_idx in range(1, chunk_len + 1):
                        p1_s.extend([
                            ('LINEAFTER', (0, r_idx), (-2, r_idx), 0.8, colors.black),
                            ('LINEBELOW', (0, r_idx), (-1, r_idx), 0.8, colors.black),
                            ('TOPPADDING', (0, r_idx), (-1, r_idx), 2.0),
                            ('BOTTOMPADDING', (0, r_idx), (-1, r_idx), 2.0),
                            ('LEFTPADDING', (1, r_idx), (1, r_idx), 4),
                            ('RIGHTPADDING', (-1, r_idx), (-1, r_idx), 4),
                            ('VALIGN', (1, r_idx), (1, r_idx), 'TOP'),
                        ])
                    p1_s.extend([
                        ('LINEAFTER', (0, p1_filler_idx), (-2, p1_filler_idx), 0.8, colors.black),
                        ('LINEBELOW', (0, p1_filler_idx), (-1, p1_filler_idx), 0.8, colors.black),
                        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
                        ('SPAN', (0, -1), (-2, -1)),
                        ('RIGHTPADDING', (-1, -1), (-1, -1), 4),
                        ('TOPPADDING', (0, -1), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, -1), (-1, -1), 2),
                        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
                    ])
                    p1_table.setStyle(TableStyle(p1_s))

                    elements.extend([
                        header_table,
                        meta_table,
                        party_table,
                        p1_table,
                        PageBreak(),
                    ])
                elif not is_last:
                    # Intermediate Page
                    s_cont = ParagraphStyle('Cont', fontName=f_bold, fontSize=8.5, leading=11, textColor=colors.black)
                    cont_text = f"{doc_type_label} (Page {p_num} of {total_pages}) &nbsp;&bull;&nbsp; {inv_no} &nbsp;&bull;&nbsp; Dated: {inv_date} &nbsp;&bull;&nbsp; Buyer: {buyer_name}"
                    cont_hdr = Table([[Paragraph(cont_text, s_cont)]], colWidths=[WIDTH], rowHeights=[18.0])
                    cont_hdr.setStyle(TableStyle([
                        ('PADDING', (0, 0), (-1, -1), 0),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
                    ]))

                    mid_chunk_r_heights = [calc_item_row_height(itm, item_row_h) for itm in chunk_items]
                    mid_used = 18.0 + th_h + 16.0 + sum(mid_chunk_r_heights) + 16.0
                    mid_filler_h = max(4.0, FRAME_HEIGHT - mid_used)

                    mid_filler_idx = len(p_data)
                    p_data.append([""] * row_len)

                    co_r = [""] * row_len
                    co_r[0] = Paragraph(f"<b>Carried Over to Page {p_num + 1}</b>", s_sub_label)
                    co_r[-1] = Paragraph(f"<b>{running_taxable:,.2f}</b>", s_sub_amt)
                    p_data.append(co_r)

                    mid_r_heights = [th_h, 16.0] + mid_chunk_r_heights + [mid_filler_h, 16.0]
                    mid_table = Table(p_data, colWidths=col_w, rowHeights=mid_r_heights)

                    mid_s = [
                        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
                        ('LINEAFTER', (0, 0), (-2, 0), 0.8, colors.black),
                        ('PADDING', (0, 0), (-1, -1), 0),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LINEBELOW', (0, 1), (-1, 1), 0.8, colors.black),
                        ('SPAN', (0, 1), (-2, 1)),
                        ('RIGHTPADDING', (-1, 1), (-1, 1), 4),
                        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F8FAFC')),
                    ]
                    for r_idx in range(2, 2 + chunk_len):
                        mid_s.extend([
                            ('LINEAFTER', (0, r_idx), (-2, r_idx), 0.8, colors.black),
                            ('LINEBELOW', (0, r_idx), (-1, r_idx), 0.8, colors.black),
                            ('TOPPADDING', (0, r_idx), (-1, r_idx), 2.0),
                            ('BOTTOMPADDING', (0, r_idx), (-1, r_idx), 2.0),
                            ('LEFTPADDING', (1, r_idx), (1, r_idx), 4),
                            ('RIGHTPADDING', (-1, r_idx), (-1, r_idx), 4),
                            ('VALIGN', (1, r_idx), (1, r_idx), 'TOP'),
                        ])
                    mid_s.extend([
                        ('LINEAFTER', (0, mid_filler_idx), (-2, mid_filler_idx), 0.8, colors.black),
                        ('LINEBELOW', (0, mid_filler_idx), (-1, mid_filler_idx), 0.8, colors.black),
                        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
                        ('SPAN', (0, -1), (-2, -1)),
                        ('RIGHTPADDING', (-1, -1), (-1, -1), 4),
                        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
                    ])
                    mid_table.setStyle(TableStyle(mid_s))

                    elements.extend([
                        cont_hdr,
                        mid_table,
                        PageBreak(),
                    ])
                else:
                    # Final Page
                    s_cont = ParagraphStyle('Cont', fontName=f_bold, fontSize=8.5, leading=11, textColor=colors.black)
                    cont_text = f"{doc_type_label} (Page {p_num} of {total_pages}) &nbsp;&bull;&nbsp; {inv_no} &nbsp;&bull;&nbsp; Dated: {inv_date} &nbsp;&bull;&nbsp; Buyer: {buyer_name}"
                    cont_hdr = Table([[Paragraph(cont_text, s_cont)]], colWidths=[WIDTH], rowHeights=[18.0])
                    cont_hdr.setStyle(TableStyle([
                        ('PADDING', (0, 0), (-1, -1), 0),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
                    ]))

                    # Calculate filler height for final page so subtotal and grand total sit right above summary
                    last_chunk_r_heights = [calc_item_row_height(itm, item_row_h) for itm in chunk_items]
                    last_used = 18.0 + th_h + 16.0 + sum(last_chunk_r_heights) + sub_tax_rows_h + h_summary
                    last_filler_h = max(4.0, FRAME_HEIGHT - last_used)

                    last_filler_idx = len(p_data)
                    p_data.append([""] * row_len)

                    # Subtotal
                    last_sub_idx = len(p_data)
                    sub_r = [""] * row_len
                    sub_r[-1] = Paragraph(f"{tot_taxable:,.2f}", s_sub_amt)
                    p_data.append(sub_r)

                    # Taxes
                    if is_inter_state or tot_igst > 0.0:
                        rate_disp = f"@ {first_item_gst:.2f} %"
                        r_tax = [""] * row_len
                        r_tax[-4] = Paragraph("Add : IGST", s_sub_label)
                        r_tax[-2] = Paragraph(rate_disp, s_sub_rate)
                        r_tax[-1] = Paragraph(f"{tot_igst:,.2f}", s_sub_amt)
                        p_data.append(r_tax)
                    else:
                        half_rate = f"@ {(first_item_gst / 2.0):.2f} %"
                        r_cgst = [""] * row_len
                        r_cgst[-4] = Paragraph("Add : CGST", s_sub_label)
                        r_cgst[-2] = Paragraph(half_rate, s_sub_rate)
                        r_cgst[-1] = Paragraph(f"{tot_cgst:,.2f}", s_sub_amt)
                        p_data.append(r_cgst)

                        r_sgst = [""] * row_len
                        r_sgst[-4] = Paragraph("Add : SGST", s_sub_label)
                        r_sgst[-2] = Paragraph(half_rate, s_sub_rate)
                        r_sgst[-1] = Paragraph(f"{tot_sgst:,.2f}", s_sub_amt)
                        p_data.append(r_sgst)

                    if cartage > 0.0:
                        r_cart = [""] * row_len
                        r_cart[-4] = Paragraph("Add : Cartage", s_sub_label)
                        r_cart[-1] = Paragraph(f"{cartage:,.2f}", s_sub_amt)
                        p_data.append(r_cart)

                    if abs(round_off) >= 0.005:
                        lbl = "Add : Round Off" if round_off > 0 else "Less : Round Off"
                        sign_str = f"+{round_off:.2f}" if round_off > 0 else f"{round_off:.2f}"
                        r_ro = [""] * row_len
                        r_ro[-4] = Paragraph(lbl, s_sub_label)
                        r_ro[-1] = Paragraph(sign_str, s_sub_amt)
                        p_data.append(r_ro)

                    # Grand Total
                    last_gt_idx = len(p_data)
                    gt_r = [""] * row_len
                    gt_r[0] = Paragraph("Grand Total", s_gt_lbl)
                    gt_r[-3] = Paragraph(f"<u>&nbsp;&nbsp;{tot_qty:.2f} {unit_label}&nbsp;&nbsp;</u>", s_gt_qty)
                    gt_r[-1] = Paragraph(f"{final_grand_total:,.2f}", s_gt_amt)
                    p_data.append(gt_r)

                    last_r_heights = [th_h, 16.0] + last_chunk_r_heights + [last_filler_h, 14.0] + [14.0] * num_tax_rows + [18.0]
                    last_table = Table(p_data, colWidths=col_w, rowHeights=last_r_heights)

                    last_s = [
                        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),
                        ('LINEAFTER', (0, 0), (-2, 0), 0.8, colors.black),
                        ('PADDING', (0, 0), (-1, -1), 0),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LINEBELOW', (0, 1), (-1, 1), 0.8, colors.black),
                        ('SPAN', (0, 1), (-2, 1)),
                        ('RIGHTPADDING', (-1, 1), (-1, 1), 4),
                        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F8FAFC')),
                    ]
                    for r_idx in range(2, 2 + chunk_len):
                        last_s.extend([
                            ('LINEAFTER', (0, r_idx), (-2, r_idx), 0.8, colors.black),
                            ('LINEBELOW', (0, r_idx), (-1, r_idx), 0.8, colors.black),
                            ('TOPPADDING', (0, r_idx), (-1, r_idx), 2.0),
                            ('BOTTOMPADDING', (0, r_idx), (-1, r_idx), 2.0),
                            ('LEFTPADDING', (1, r_idx), (1, r_idx), 4),
                            ('RIGHTPADDING', (-1, r_idx), (-1, r_idx), 4),
                            ('VALIGN', (1, r_idx), (1, r_idx), 'TOP'),
                        ])

                    last_s.extend([
                        ('LINEAFTER', (0, last_filler_idx), (-2, last_filler_idx), 0.8, colors.black),
                        ('LINEBELOW', (0, last_filler_idx), (-1, last_filler_idx), 0.8, colors.black),
                    ])

                    for r_idx in range(last_sub_idx, last_gt_idx):
                        last_s.extend([
                            ('LINEAFTER', (-2, r_idx), (-2, r_idx), 0.8, colors.black),
                            ('RIGHTPADDING', (-1, r_idx), (-1, r_idx), 4),
                            ('SPAN', (0, r_idx), (-5, r_idx)),
                            ('SPAN', (-4, r_idx), (-3, r_idx)),
                            ('TOPPADDING', (0, r_idx), (-1, r_idx), 1),
                            ('BOTTOMPADDING', (0, r_idx), (-1, r_idx), 1),
                        ])

                    last_s.extend([
                        ('LINEABOVE', (0, last_gt_idx), (-1, last_gt_idx), 0.8, colors.black),
                        ('LINEBELOW', (0, last_gt_idx), (-1, last_gt_idx), 0.8, colors.black),
                        ('LINEAFTER', (-2, last_gt_idx), (-2, last_gt_idx), 0.8, colors.black),
                        ('SPAN', (0, last_gt_idx), (-4, last_gt_idx)),
                        ('SPAN', (-3, last_gt_idx), (-2, last_gt_idx)),
                        ('RIGHTPADDING', (-1, last_gt_idx), (-1, last_gt_idx), 4),
                        ('TOPPADDING', (0, last_gt_idx), (-1, last_gt_idx), 2),
                        ('BOTTOMPADDING', (0, last_gt_idx), (-1, last_gt_idx), 2),
                    ])
                    last_table.setStyle(TableStyle(last_s))

                    elements.extend([
                        cont_hdr,
                        last_table,
                        tax_table,
                        words_table,
                        bank_table,
                    ])

        # Watermark & Logo assets
        logo_data = seller.get('logo_url') or seller.get('logo_data')
        logo_img_path = None
        if logo_data:
            if isinstance(logo_data, str) and logo_data.startswith('data:image'):
                try:
                    import base64
                    _, b64data = logo_data.split(',', 1)
                    raw_b = base64.b64decode(b64data)
                    logo_img_path = io.BytesIO(raw_b)
                except Exception:
                    logo_img_path = None
            elif isinstance(logo_data, str) and logo_data.strip():
                clean_p = logo_data.lstrip('/')
                if os.path.exists(clean_p):
                    logo_img_path = clean_p
                else:
                    from django.conf import settings
                    med = os.path.join(getattr(settings, 'MEDIA_ROOT', ''), clean_p)
                    if os.path.exists(med):
                        logo_img_path = med

        # Callback: Draws outer border, watermark, and footer on EVERY page
        def draw_decorations(canv, doc):
            canv.saveState()

            # Watermark layer (centered, subtle opacity)
            if watermark:
                canv.saveState()
                if logo_img_path:
                    try:
                        canv.setFillAlpha(0.045)
                        wm_dim = 260
                        canv.drawImage(
                            logo_img_path,
                            (PAGE_WIDTH - wm_dim) / 2,
                            (PAGE_HEIGHT - wm_dim) / 2,
                            width=wm_dim,
                            height=wm_dim,
                            preserveAspectRatio=True,
                            mask='auto'
                        )
                    except Exception as e:
                        logger.warning(f"Could not draw logo watermark: {e}")
                else:
                    canv.setFont(f_bold, 36)
                    canv.setFillColor(colors.HexColor('#0f172a'))
                    canv.setFillAlpha(0.035)
                    canv.translate(PAGE_WIDTH / 2, PAGE_HEIGHT / 2)
                    canv.rotate(35)
                    canv.drawCentredString(0, 0, (seller.get('name') or "PROFORMA INVOICE").upper())
                canv.restoreState()

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

        class DocumentNumberedCanvas(NumberedCanvas):
            footer_text = canvas_footer_text

        doc.build(elements, canvasmaker=DocumentNumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

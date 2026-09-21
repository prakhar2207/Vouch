import io
import logging
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from apps.documents.renderers.base import FONTS_LOADED

logger = logging.getLogger(__name__)


class VoucherPDFRenderer:
    """
    Renders deterministic PDF slips for Payment, Receipt, Contra, and Journal Vouchers.
    """

    @classmethod
    def render(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()

        PAGE_WIDTH, PAGE_HEIGHT = A4
        MARGIN_X = 24.0
        MARGIN_Y = 28.0
        WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=MARGIN_Y,
            bottomMargin=MARGIN_Y,
        )

        doc_meta = dto.get('document', {})
        company = dto.get('company', {})
        party = dto.get('party')
        entries = dto.get('entries', [])
        totals = dto.get('totals', {})
        vch_type = doc_meta.get('voucher_type', 'VOUCHER')

        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        fnt_b = 'Roboto-Bold' if FONTS_LOADED else 'Helvetica-Bold'
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'

        s_comp_name = ParagraphStyle('CompName', fontName=fnt_b, fontSize=16, leading=20, alignment=TA_CENTER)
        s_comp_sub = ParagraphStyle('CompSub', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_CENTER)
        s_title = ParagraphStyle('VchTitle', fontName=fnt_b, fontSize=12, leading=15, alignment=TA_CENTER)

        s_meta_l = ParagraphStyle('MetaL', fontName=fnt, fontSize=9, leading=12)
        s_meta_r = ParagraphStyle('MetaR', fontName=fnt, fontSize=9, leading=12, alignment=TA_RIGHT)

        s_th = ParagraphStyle('TH', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_CENTER)
        s_th_l = ParagraphStyle('THL', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_LEFT)
        s_th_r = ParagraphStyle('THR', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_RIGHT)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=9, leading=12)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=9, leading=12, alignment=TA_RIGHT)
        s_td_bold_r = ParagraphStyle('TDBoldR', fontName=fnt_b, fontSize=9, leading=12, alignment=TA_RIGHT)

        s_words = ParagraphStyle('Words', fontName=fnt, fontSize=9, leading=13)
        s_sign_l = ParagraphStyle('SignL', fontName=fnt_b, fontSize=8.5, leading=11, alignment=TA_LEFT)
        s_sign_r = ParagraphStyle('SignR', fontName=fnt_b, fontSize=8.5, leading=11, alignment=TA_RIGHT)

        elements = []

        # 1. Company Header
        elements.append(Paragraph(f"<b>{company.get('name', 'Vouch ERP')}</b>", s_comp_name))
        c_addr = company.get('address', '')
        c_city = company.get('city', '')
        c_gstin = company.get('gstin', '')
        c_contact = f"GSTIN: {c_gstin}" if c_gstin else ""
        if company.get('phone'):
            c_contact += f" | Phone: {company.get('phone')}"
        addr_line = f"{c_addr}, {c_city}".strip(', ')
        if addr_line:
            elements.append(Paragraph(addr_line, s_comp_sub))
        if c_contact:
            elements.append(Paragraph(c_contact, s_comp_sub))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph(f"<b><u>{vch_type} VOUCHER</u></b>", s_title))
        elements.append(Spacer(1, 10))

        # 2. Meta Box
        v_num = doc_meta.get('voucher_number', '')
        v_date = doc_meta.get('voucher_date', '')
        ref_num = doc_meta.get('reference_number', 'N/A') or 'N/A'
        party_name = party.get('name', 'N/A') if party else 'N/A'

        meta_data = [
            [
                Paragraph(f"<b>Voucher No :</b> {v_num}", s_meta_l),
                Paragraph(f"<b>Date :</b> {v_date}", s_meta_r),
            ],
            [
                Paragraph(f"<b>Party :</b> {party_name}", s_meta_l),
                Paragraph(f"<b>Ref No :</b> {ref_num}", s_meta_r),
            ]
        ]
        meta_table = Table(meta_data, colWidths=[WIDTH * 0.55, WIDTH * 0.45])
        meta_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 12))

        # 3. Entries Table
        col_w = [WIDTH * 0.45, WIDTH * 0.25, WIDTH * 0.15, WIDTH * 0.15]
        table_data = [
            [
                Paragraph("<b>Particulars / Ledger</b>", s_th_l),
                Paragraph("<b>Narration</b>", s_th_l),
                Paragraph("<b>Debit ({})</b>".format(curr_sym), s_th_r),
                Paragraph("<b>Credit ({})</b>".format(curr_sym), s_th_r),
            ]
        ]

        if entries:
            for ent in entries:
                dr_val = ent.get('debit_amount', 0.0)
                cr_val = ent.get('credit_amount', 0.0)
                dr_str = f"{dr_val:,.2f}" if dr_val > 0 else "-"
                cr_str = f"{cr_val:,.2f}" if cr_val > 0 else "-"
                table_data.append([
                    Paragraph(f"<b>{ent.get('ledger_name', '')}</b>", s_td_l),
                    Paragraph(ent.get('narration', ''), s_td_l),
                    Paragraph(dr_str, s_td_r),
                    Paragraph(cr_str, s_td_r),
                ])
        else:
            # Fallback when single total amount exists
            net_amt = totals.get('net_amount', 0.0)
            table_data.append([
                Paragraph(party_name, s_td_l),
                Paragraph(doc_meta.get('narration', ''), s_td_l),
                Paragraph(f"{net_amt:,.2f}", s_td_r),
                Paragraph("-", s_td_r),
            ])

        # Totals row
        tot_dr = totals.get('total_debit', 0.0)
        tot_cr = totals.get('total_credit', 0.0)
        table_data.append([
            Paragraph("<b>Total</b>", s_td_bold_r),
            "",
            Paragraph(f"<b>{tot_dr:,.2f}</b>", s_td_bold_r),
            Paragraph(f"<b>{tot_cr:,.2f}</b>", s_td_bold_r),
        ])

        v_style = [
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ('SPAN', (0, -1), (1, -1)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]
        entries_table = Table(table_data, colWidths=col_w)
        entries_table.setStyle(TableStyle(v_style))
        elements.append(entries_table)
        elements.append(Spacer(1, 10))

        # 4. Words & Remarks
        words = dto.get('amount_in_words', '')
        if words:
            elements.append(Paragraph(f"<b>Amount in Words :</b> {curr_sym} {words}", s_words))
            elements.append(Spacer(1, 6))

        narration = doc_meta.get('narration')
        if narration:
            elements.append(Paragraph(f"<b>Narration / Remarks :</b> {narration}", s_words))
            elements.append(Spacer(1, 12))

        # 5. Signatures
        elements.append(Spacer(1, 30))
        sig_data = [
            [
                Paragraph("<b>Receiver's Signature</b>", s_sign_l),
                Paragraph(f"<b>For {company.get('name', '')}</b><br/><br/><br/>Authorised Signatory", s_sign_r)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[WIDTH / 2, WIDTH / 2])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

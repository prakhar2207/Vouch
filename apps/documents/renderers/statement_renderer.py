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
    KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from apps.documents.renderers.base import FONTS_LOADED, NumberedCanvas

logger = logging.getLogger(__name__)


class StatementPDFRenderer:
    """
    Renders multi-page, deterministic PDF statements for Customer, Supplier, and Ledger accounts.
    Includes running balances, repeated table headers, and page numbering.
    """

    @classmethod
    def render(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()

        PAGE_WIDTH, PAGE_HEIGHT = A4
        MARGIN_X = 20.0
        MARGIN_Y = 24.0
        WIDTH = PAGE_WIDTH - (2 * MARGIN_X)

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=MARGIN_Y,
            bottomMargin=MARGIN_Y + 12,
        )

        doc_meta = dto.get('document', {})
        company = dto.get('company', {})
        party = dto.get('party', {})
        op_bal = dto.get('opening_balance', {})
        cl_bal = dto.get('closing_balance', {})
        summary = dto.get('summary', {})
        txs = dto.get('transactions', [])

        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        fnt_b = 'Roboto-Bold' if FONTS_LOADED else 'Helvetica-Bold'
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'

        s_comp_name = ParagraphStyle('CompName', fontName=fnt_b, fontSize=15, leading=18, alignment=TA_CENTER)
        s_comp_sub = ParagraphStyle('CompSub', fontName=fnt, fontSize=8, leading=10, alignment=TA_CENTER)
        s_title = ParagraphStyle('StmtTitle', fontName=fnt_b, fontSize=11, leading=14, alignment=TA_CENTER)

        s_party_l = ParagraphStyle('PartyL', fontName=fnt, fontSize=8.5, leading=11)
        s_party_r = ParagraphStyle('PartyR', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_RIGHT)

        s_th = ParagraphStyle('TH', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_CENTER)
        s_th_l = ParagraphStyle('THL', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_LEFT)
        s_th_r = ParagraphStyle('THR', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_RIGHT)
        s_td_c = ParagraphStyle('TDC', fontName=fnt, fontSize=8, leading=10, alignment=TA_CENTER)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=8, leading=10)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=8, leading=10, alignment=TA_RIGHT)
        s_td_bold_r = ParagraphStyle('TDBoldR', fontName=fnt_b, fontSize=8, leading=10, alignment=TA_RIGHT)

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

        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"<b><u>{doc_meta.get('title', 'STATEMENT OF ACCOUNT')}</u></b>", s_title))
        elements.append(Spacer(1, 8))

        # 2. Party & Period Information Grid
        from_d = doc_meta.get('from_date') or 'Inception'
        to_d = doc_meta.get('to_date') or 'Present'
        period_str = f"Period : <b>{from_d}</b> to <b>{to_d}</b>"
        p_name = party.get('name', '')
        p_gstin = party.get('gstin') or 'Unregistered'
        p_phone = party.get('phone') or 'N/A'

        info_data = [
            [
                Paragraph(f"Account : <b>{p_name}</b>", s_party_l),
                Paragraph(period_str, s_party_r),
            ],
            [
                Paragraph(f"GSTIN : {p_gstin} | Phone: {p_phone}", s_party_l),
                Paragraph(f"Generated On: {doc_meta.get('generated_at', '')}", s_party_r),
            ]
        ]
        info_table = Table(info_data, colWidths=[WIDTH * 0.6, WIDTH * 0.4])
        info_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # 3. Transactions Table (Multi-Page with repeatRows=1)
        col_w = [60, 80, 65, 140, 65, 65, 81]  # sum = 556
        table_rows = [
            [
                Paragraph("<b>Date</b>", s_th_l),
                Paragraph("<b>Vch No.</b>", s_th_l),
                Paragraph("<b>Type</b>", s_th),
                Paragraph("<b>Narration</b>", s_th_l),
                Paragraph(f"<b>Debit ({curr_sym})</b>", s_th_r),
                Paragraph(f"<b>Credit ({curr_sym})</b>", s_th_r),
                Paragraph(f"<b>Balance ({curr_sym})</b>", s_th_r),
            ]
        ]

        # Opening Balance row
        op_amount = op_bal.get('amount', 0.0)
        op_type = op_bal.get('type', 'DR')
        table_rows.append([
            Paragraph(str(from_d), s_td_l),
            Paragraph("<b>OPENING</b>", s_td_l),
            Paragraph("-", s_td_c),
            Paragraph("<b>Opening Balance B/F</b>", s_td_l),
            Paragraph(f"{op_amount:,.2f}" if op_type == 'DR' else "-", s_td_r),
            Paragraph(f"{op_amount:,.2f}" if op_type == 'CR' else "-", s_td_r),
            Paragraph(f"<b>{op_amount:,.2f} {op_type}</b>", s_td_bold_r),
        ])

        for tx in txs:
            dr_amt = tx.get('debit', 0.0)
            cr_amt = tx.get('credit', 0.0)
            rb_amt = tx.get('running_balance', 0.0)
            rb_type = tx.get('running_type', 'DR')

            dr_str = f"{dr_amt:,.2f}" if dr_amt > 0 else "-"
            cr_str = f"{cr_amt:,.2f}" if cr_amt > 0 else "-"
            rb_str = f"{rb_amt:,.2f} {rb_type}"

            table_rows.append([
                Paragraph(tx.get('date', ''), s_td_l),
                Paragraph(f"<b>{tx.get('voucher_number', '')}</b>", s_td_l),
                Paragraph(tx.get('voucher_type', ''), s_td_c),
                Paragraph(tx.get('narration', '') or '-', s_td_l),
                Paragraph(dr_str, s_td_r),
                Paragraph(cr_str, s_td_r),
                Paragraph(rb_str, s_td_r),
            ])

        # Closing Summary row
        tot_dr = summary.get('total_debit', 0.0)
        tot_cr = summary.get('total_credit', 0.0)
        cl_amount = cl_bal.get('amount', 0.0)
        cl_type = cl_bal.get('type', 'DR')

        table_rows.append([
            Paragraph("<b>Total / Closing</b>", s_td_bold_r),
            "", "", "",
            Paragraph(f"<b>{tot_dr:,.2f}</b>", s_td_bold_r),
            Paragraph(f"<b>{tot_cr:,.2f}</b>", s_td_bold_r),
            Paragraph(f"<b><u>{cl_amount:,.2f} {cl_type}</u></b>", s_td_bold_r),
        ])

        stmt_table = Table(table_rows, colWidths=col_w, repeatRows=1)
        t_style = [
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FEF3C7')),  # Highlight opening row
            ('LINEBELOW', (0, -2), (-1, -2), 1, colors.black),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F9FAFB')),
            ('SPAN', (0, -1), (3, -1)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]
        stmt_table.setStyle(TableStyle(t_style))
        elements.append(stmt_table)
        elements.append(Spacer(1, 14))

        # 4. Closing Balance Banner
        summary_box = [
            [
                Paragraph(
                    f"<b>Closing Balance as of {to_d} :</b> "
                    f"<font size=11 color='#1E40AF'><b>{curr_sym} {cl_amount:,.2f} ({cl_type})</b></font>",
                    s_party_l
                ),
                Paragraph(f"Total Transactions : <b>{summary.get('transaction_count', len(txs))}</b>", s_party_r)
            ]
        ]
        summary_table = Table(summary_box, colWidths=[WIDTH * 0.7, WIDTH * 0.3])
        summary_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#3B82F6')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(KeepTogether(summary_table))

        doc.build(elements, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

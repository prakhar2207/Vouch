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


class ReportPDFRenderer:
    """
    Renders multi-page, deterministic PDF reports for:
    - Trial Balance
    - Profit & Loss
    - Balance Sheet
    """

    @classmethod
    def render(cls, dto: Dict[str, Any]) -> bytes:
        doc_meta = dto.get('document', {})
        report_type = doc_meta.get('document_type', 'REPORT')

        if report_type == 'TRIAL_BALANCE':
            return cls._render_trial_balance(dto)
        elif report_type == 'PROFIT_AND_LOSS':
            return cls._render_profit_and_loss(dto)
        elif report_type == 'BALANCE_SHEET':
            return cls._render_balance_sheet(dto)
        else:
            raise ValueError(f"Unsupported report type: {report_type}")

    @classmethod
    def _create_doc(cls, buffer):
        PAGE_WIDTH, PAGE_HEIGHT = A4
        MARGIN_X = 20.0
        MARGIN_Y = 24.0
        return SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=MARGIN_Y,
            bottomMargin=MARGIN_Y + 12,
        ), PAGE_WIDTH - (2 * MARGIN_X)

    @classmethod
    def _render_trial_balance(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        doc, width = cls._create_doc(buffer)

        company = dto.get('company', {})
        doc_meta = dto.get('document', {})
        rep = dto.get('report_data', {})
        ledgers = rep.get('ledgers', [])
        totals = rep.get('totals', {})

        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        fnt_b = 'Roboto-Bold' if FONTS_LOADED else 'Helvetica-Bold'
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'

        s_comp = ParagraphStyle('CompName', fontName=fnt_b, fontSize=15, leading=18, alignment=TA_CENTER)
        s_sub = ParagraphStyle('CompSub', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_CENTER)
        s_title = ParagraphStyle('RepTitle', fontName=fnt_b, fontSize=11, leading=14, alignment=TA_CENTER)

        s_th_l = ParagraphStyle('THL', fontName=fnt_b, fontSize=8.5, leading=10, alignment=TA_LEFT)
        s_th_r = ParagraphStyle('THR', fontName=fnt_b, fontSize=8.5, leading=10, alignment=TA_RIGHT)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=8, leading=10)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=8, leading=10, alignment=TA_RIGHT)
        s_bold_r = ParagraphStyle('BoldR', fontName=fnt_b, fontSize=8.5, leading=11, alignment=TA_RIGHT)

        elements = []
        elements.append(Paragraph(f"<b>{company.get('name', 'Vouch ERP')}</b>", s_comp))
        elements.append(Paragraph(f"GSTIN: {company.get('gstin', 'N/A')} | {company.get('city', '')}", s_sub))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b><u>TRIAL BALANCE</u></b>", s_title))
        elements.append(Paragraph(f"As of: <b>{doc_meta.get('as_of_date', '')}</b>", s_sub))
        elements.append(Spacer(1, 10))

        col_w = [width * 0.45, width * 0.25, width * 0.15, width * 0.15]
        table_rows = [
            [
                Paragraph("<b>Ledger Name</b>", s_th_l),
                Paragraph("<b>Group / Nature</b>", s_th_l),
                Paragraph(f"<b>Debit ({curr_sym})</b>", s_th_r),
                Paragraph(f"<b>Credit ({curr_sym})</b>", s_th_r),
            ]
        ]

        for itm in ledgers:
            dr = itm.get('debit', 0.0)
            cr = itm.get('credit', 0.0)
            table_rows.append([
                Paragraph(f"<b>{itm.get('ledger_name', '')}</b>", s_td_l),
                Paragraph(f"{itm.get('group_name', '')} ({itm.get('nature', '')})", s_td_l),
                Paragraph(f"{dr:,.2f}" if dr > 0 else "-", s_td_r),
                Paragraph(f"{cr:,.2f}" if cr > 0 else "-", s_td_r),
            ])

        tot_dr = totals.get('total_debit', 0.0)
        tot_cr = totals.get('total_credit', 0.0)
        table_rows.append([
            Paragraph("<b>Total</b>", s_bold_r),
            "",
            Paragraph(f"<b>{tot_dr:,.2f}</b>", s_bold_r),
            Paragraph(f"<b>{tot_cr:,.2f}</b>", s_bold_r),
        ])

        tb_table = Table(table_rows, colWidths=col_w, repeatRows=1)
        tb_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F9FAFB')),
            ('SPAN', (0, -1), (1, -1)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(tb_table)
        elements.append(Spacer(1, 10))

        # Equilibrium badge
        is_balanced = totals.get('is_balanced', abs(tot_dr - tot_cr) < 0.01)
        badge_text = "<font color='green'><b>✓ Balanced (Total Debit == Total Credit)</b></font>" if is_balanced else "<font color='red'><b>⚠ Out of balance!</b></font>"
        badge_table = Table([[Paragraph(badge_text, s_sub)]], colWidths=[width])
        badge_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#10B981') if is_balanced else colors.HexColor('#EF4444')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ECFDF5') if is_balanced else colors.HexColor('#FEF2F2')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(KeepTogether(badge_table))

        doc.build(elements, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _render_profit_and_loss(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        doc, width = cls._create_doc(buffer)

        company = dto.get('company', {})
        doc_meta = dto.get('document', {})
        rep = dto.get('report_data', {})

        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        fnt_b = 'Roboto-Bold' if FONTS_LOADED else 'Helvetica-Bold'
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'

        s_comp = ParagraphStyle('CompName', fontName=fnt_b, fontSize=15, leading=18, alignment=TA_CENTER)
        s_sub = ParagraphStyle('CompSub', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_CENTER)
        s_title = ParagraphStyle('RepTitle', fontName=fnt_b, fontSize=11, leading=14, alignment=TA_CENTER)

        s_th_l = ParagraphStyle('THL', fontName=fnt_b, fontSize=8.5, leading=10, alignment=TA_LEFT)
        s_th_r = ParagraphStyle('THR', fontName=fnt_b, fontSize=8.5, leading=10, alignment=TA_RIGHT)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=8, leading=10)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=8, leading=10, alignment=TA_RIGHT)
        s_bold_r = ParagraphStyle('BoldR', fontName=fnt_b, fontSize=8.5, leading=11, alignment=TA_RIGHT)
        s_sec_hdr = ParagraphStyle('SecHdr', fontName=fnt_b, fontSize=8.5, leading=10, textColor=colors.HexColor('#1E3A8A'))

        elements = []
        elements.append(Paragraph(f"<b>{company.get('name', 'Vouch ERP')}</b>", s_comp))
        elements.append(Paragraph(f"GSTIN: {company.get('gstin', 'N/A')} | {company.get('city', '')}", s_sub))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b><u>PROFIT &amp; LOSS STATEMENT</u></b>", s_title))
        period_str = f"From <b>{doc_meta.get('from_date', '')}</b> to <b>{doc_meta.get('to_date', '')}</b>"
        elements.append(Paragraph(period_str, s_sub))
        elements.append(Spacer(1, 10))

        col_w = [width * 0.7, width * 0.3]
        rows = [
            [Paragraph("<b>Particulars</b>", s_th_l), Paragraph(f"<b>Amount ({curr_sym})</b>", s_th_r)],
            [Paragraph("<b>Trading Income (Sales &amp; Direct Income)</b>", s_sec_hdr), ""],
        ]

        trading = rep.get('trading_account', {})
        pl_sec = rep.get('profit_and_loss', {})

        # Direct Income
        d_inc_rows = trading.get('direct_income', {}).get('rows', []) if isinstance(trading.get('direct_income'), dict) else rep.get('direct_income', [])
        for itm in d_inc_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('amount', itm.get('balance', 0.0))):,.2f}", s_td_r)])

        closing_stock = trading.get('closing_stock') or rep.get('closing_stock_valuation')
        if closing_stock:
            rows.append([Paragraph("Closing Stock", s_td_l), Paragraph(f"{float(closing_stock):,.2f}", s_td_r)])

        # Direct Expenses
        rows.append([Paragraph("<b>Cost of Goods Sold &amp; Direct Expenses</b>", s_sec_hdr), ""])
        opening_stock = trading.get('opening_stock') or rep.get('opening_stock_valuation')
        if opening_stock:
            rows.append([Paragraph("Opening Stock", s_td_l), Paragraph(f"{float(opening_stock):,.2f}", s_td_r)])

        d_exp_rows = trading.get('direct_expense', {}).get('rows', []) if isinstance(trading.get('direct_expense'), dict) else rep.get('direct_expenses', [])
        for itm in d_exp_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('amount', itm.get('balance', 0.0))):,.2f}", s_td_r)])

        gp = trading.get('gross_profit') or rep.get('gross_profit', 0.0)
        rows.append([
            Paragraph("<b>Gross Profit / (Loss)</b>", s_bold_r),
            Paragraph(f"<b>{float(gp):,.2f}</b>", s_bold_r)
        ])

        # Indirect Expenses
        rows.append([Paragraph("<b>Indirect Operating Expenses</b>", s_sec_hdr), ""])
        ind_exp_rows = pl_sec.get('indirect_expense', {}).get('rows', []) if isinstance(pl_sec.get('indirect_expense'), dict) else rep.get('indirect_expenses', [])
        for itm in ind_exp_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('amount', itm.get('balance', 0.0))):,.2f}", s_td_r)])

        # Indirect Income
        ind_inc_rows = pl_sec.get('indirect_income', {}).get('rows', []) if isinstance(pl_sec.get('indirect_income'), dict) else rep.get('indirect_income', [])
        if ind_inc_rows:
            rows.append([Paragraph("<b>Other / Indirect Income</b>", s_sec_hdr), ""])
            for itm in ind_inc_rows:
                if isinstance(itm, dict):
                    rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('amount', itm.get('balance', 0.0))):,.2f}", s_td_r)])

        np_val = pl_sec.get('net_profit') or rep.get('net_profit', 0.0)
        rows.append([
            Paragraph("<b>Net Profit / (Loss) for the Period</b>", s_bold_r),
            Paragraph(f"<b>{float(np_val):,.2f}</b>", s_bold_r)
        ])

        pl_table = Table(rows, colWidths=col_w, repeatRows=1)
        pl_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EFF6FF')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(pl_table)

        doc.build(elements, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def _render_balance_sheet(cls, dto: Dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        doc, width = cls._create_doc(buffer)

        company = dto.get('company', {})
        doc_meta = dto.get('document', {})
        rep = dto.get('report_data', {})

        fnt = 'Roboto' if FONTS_LOADED else 'Helvetica'
        fnt_b = 'Roboto-Bold' if FONTS_LOADED else 'Helvetica-Bold'
        curr_sym = '\u20B9' if FONTS_LOADED else 'Rs.'

        s_comp = ParagraphStyle('CompName', fontName=fnt_b, fontSize=15, leading=18, alignment=TA_CENTER)
        s_sub = ParagraphStyle('CompSub', fontName=fnt, fontSize=8.5, leading=11, alignment=TA_CENTER)
        s_title = ParagraphStyle('RepTitle', fontName=fnt_b, fontSize=11, leading=14, alignment=TA_CENTER)

        s_th_l = ParagraphStyle('THL', fontName=fnt_b, fontSize=8.5, leading=10, alignment=TA_LEFT)
        s_th_r = ParagraphStyle('THR', fontName=fnt_b, fontSize=8.5, leading=10, alignment=TA_RIGHT)
        s_td_l = ParagraphStyle('TDL', fontName=fnt, fontSize=8, leading=10)
        s_td_r = ParagraphStyle('TDR', fontName=fnt, fontSize=8, leading=10, alignment=TA_RIGHT)
        s_bold_r = ParagraphStyle('BoldR', fontName=fnt_b, fontSize=8.5, leading=11, alignment=TA_RIGHT)
        s_sec = ParagraphStyle('Sec', fontName=fnt_b, fontSize=8.5, leading=10, textColor=colors.HexColor('#1E3A8A'))

        elements = []
        elements.append(Paragraph(f"<b>{company.get('name', 'Vouch ERP')}</b>", s_comp))
        elements.append(Paragraph(f"GSTIN: {company.get('gstin', 'N/A')} | {company.get('city', '')}", s_sub))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b><u>BALANCE SHEET</u></b>", s_title))
        elements.append(Paragraph(f"As of <b>{doc_meta.get('as_of_date', '')}</b>", s_sub))
        elements.append(Spacer(1, 10))

        col_w = [width * 0.7, width * 0.3]
        rows = [
            [Paragraph("<b>Capital &amp; Liabilities</b>", s_sec), ""],
        ]

        liab_and_eq = rep.get('liabilities_and_equity', {})
        eq_sec = liab_and_eq.get('equity', {})
        cap_rows = eq_sec.get('capital_rows', []) if isinstance(eq_sec, dict) else rep.get('capital_account', [])
        for itm in cap_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('balance', itm.get('amount', 0.0))):,.2f}", s_td_r)])

        net_profit = eq_sec.get('net_profit') if isinstance(eq_sec, dict) else rep.get('profit_loss_surplus')
        if net_profit:
            rows.append([Paragraph("Profit &amp; Loss A/c (Surplus)", s_td_l), Paragraph(f"{float(net_profit):,.2f}", s_td_r)])

        loans_sec = liab_and_eq.get('loans', {})
        loans_rows = loans_sec.get('rows', []) if isinstance(loans_sec, dict) else []
        for itm in loans_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('balance', itm.get('amount', 0.0))):,.2f}", s_td_r)])

        cur_liab_sec = liab_and_eq.get('current_liabilities', {})
        cur_liab_rows = cur_liab_sec.get('rows', []) if isinstance(cur_liab_sec, dict) else rep.get('liabilities', [])
        for itm in cur_liab_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('balance', itm.get('amount', 0.0))):,.2f}", s_td_r)])

        tot_liab = liab_and_eq.get('total_liabilities') or rep.get('total_liabilities', 0.0)
        rows.append([
            Paragraph("<b>Total Capital &amp; Liabilities</b>", s_bold_r),
            Paragraph(f"<b>{float(tot_liab):,.2f}</b>", s_bold_r)
        ])

        # Assets
        rows.append([Paragraph("<b>Property &amp; Assets</b>", s_sec), ""])
        assets_sec = rep.get('assets', {})
        fa_rows = assets_sec.get('fixed_assets', {}).get('rows', []) if isinstance(assets_sec, dict) and isinstance(assets_sec.get('fixed_assets'), dict) else []
        for itm in fa_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('balance', itm.get('amount', 0.0))):,.2f}", s_td_r)])

        ca_rows = assets_sec.get('current_assets', {}).get('rows', []) if isinstance(assets_sec, dict) and isinstance(assets_sec.get('current_assets'), dict) else (assets_sec if isinstance(assets_sec, list) else [])
        for itm in ca_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('balance', itm.get('amount', 0.0))):,.2f}", s_td_r)])

        bc_rows = assets_sec.get('bank_and_cash', {}).get('rows', []) if isinstance(assets_sec, dict) and isinstance(assets_sec.get('bank_and_cash'), dict) else []
        for itm in bc_rows:
            if isinstance(itm, dict):
                rows.append([Paragraph(itm.get('ledger_name', itm.get('name', '')), s_td_l), Paragraph(f"{float(itm.get('balance', itm.get('amount', 0.0))):,.2f}", s_td_r)])

        closing_stock = rep.get('closing_stock')
        if closing_stock:
            rows.append([Paragraph("Closing Stock", s_td_l), Paragraph(f"{float(closing_stock):,.2f}", s_td_r)])

        tot_assets = assets_sec.get('total_assets') if isinstance(assets_sec, dict) else rep.get('total_assets', 0.0)
        rows.append([
            Paragraph("<b>Total Property &amp; Assets</b>", s_bold_r),
            Paragraph(f"<b>{float(tot_assets or 0.0):,.2f}</b>", s_bold_r)
        ])

        bs_table = Table(rows, colWidths=col_w, repeatRows=1)
        bs_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F3F4F6')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(bs_table)

        doc.build(elements, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()

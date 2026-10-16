import io

from reportlab.platypus.flowables import Flowable

class PushToBottomAndDraw(Flowable):
    def __init__(self, elements):
        Flowable.__init__(self)
        self.elements = elements
        self.width = 0
        self.height = 0
        self.req_h = 0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        req_h = 0
        for el in self.elements:
            _, h = el.wrap(availWidth, availHeight)
            req_h += h
        self.req_h = req_h
        
        if req_h > availHeight:
            return availWidth, availHeight + 1
            
        self.height = availHeight
        return availWidth, self.height

    def split(self, availWidth, availHeight):
        return []

    def draw(self):
        canv = self.canv
        current_y = self.req_h
        for el in self.elements:
            _, h = el.wrap(self.width, self.req_h)
            current_y -= h
            el.drawOn(canv, 0, current_y)

import logging
import os
import base64
import urllib.parse
from decimal import Decimal
from typing import Any, Dict, Optional

import qrcode
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    KeepTogether,
    HRFlowable,
    PageBreak,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

from apps.documents.renderers.base import SEGOE_LOADED, ROBOTO_LOADED, FONTS_LOADED

logger = logging.getLogger(__name__)

# State code to State Name mapping
STATE_NAMES: Dict[str, str] = {
    '01': 'Jammu & Kashmir',
    '02': 'Himachal Pradesh',
    '03': 'Punjab',
    '04': 'Chandigarh',
    '05': 'Uttarakhand',
    '06': 'Haryana',
    '07': 'Delhi',
    '08': 'Rajasthan',
    '09': 'Uttar Pradesh',
    '10': 'Bihar',
    '11': 'Sikkim',
    '12': 'Arunachal Pradesh',
    '13': 'Nagaland',
    '14': 'Manipur',
    '15': 'Mizoram',
    '16': 'Tripura',
    '17': 'Meghalaya',
    '18': 'Assam',
    '19': 'West Bengal',
    '20': 'Jharkhand',
    '21': 'Odisha',
    '22': 'Chhattisgarh',
    '23': 'Madhya Pradesh',
    '24': 'Gujarat',
    '26': 'Dadra and Nagar Haveli and Daman and Diu',
    '27': 'Maharashtra',
    '28': 'Andhra Pradesh',
    '29': 'Karnataka',
    '30': 'Goa',
    '31': 'Lakshadweep',
    '32': 'Kerala',
    '33': 'Tamil Nadu',
    '34': 'Puducherry',
    '35': 'Andaman & Nicobar Islands',
    '36': 'Telangana',
    '37': 'Andhra Pradesh',
    '38': 'Ladakh',
    '97': 'Other Territory',
}


def fmt_curr(val: Any) -> str:
    """Format numeric values as Indian Currency string."""
    try:
        f = float(val or 0)
        parts = f"{f:.2f}".split('.')
        int_p, dec_p = parts[0], parts[1]
        neg = False
        if int_p.startswith('-'):
            neg = True
            int_p = int_p[1:]
        if len(int_p) > 3:
            last3 = int_p[-3:]
            rest = int_p[:-3]
            groups = []
            while len(rest) > 2:
                groups.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                groups.append(rest)
            groups.reverse()
            int_formatted = ','.join(groups) + ',' + last3
        else:
            int_formatted = int_p
        prefix = '-' if neg else ''
        return f"{prefix}{int_formatted}.{dec_p}"
    except Exception:
        return '0.00'


class ProformaNumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas for Proforma Documents.
    Draws watermark in background and dynamic page numbers in footer.
    """
    doc_number = ""
    footer_legal_text = "This is a Commercial Proforma — Not a GST Tax Invoice"

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
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, total_pages: int):
        self.saveState()
        fnt = 'SegoeUI' if SEGOE_LOADED else ('Roboto' if ROBOTO_LOADED else 'Helvetica')
        PAGE_WIDTH = 595.275
        MARGIN_X = 28.35

        # Horizontal divider above footer matching ProformaDocumentSheet
        self.setStrokeColor(colors.HexColor('#cbd5e1'))
        self.setLineWidth(0.75)
        self.line(MARGIN_X, 32, PAGE_WIDTH - MARGIN_X, 32)

        # Footer text matching ProformaDocumentSheet
        self.setFont(fnt, 8)
        self.setFillColor(colors.HexColor('#64748b'))

        # Safe separator (bullet or dash)
        sep = " • " if (SEGOE_LOADED or ROBOTO_LOADED) else " - "
        left_text = f"{self.doc_number}{sep}{self.footer_legal_text}" if self.doc_number else self.footer_legal_text
        self.drawString(MARGIN_X, 18, left_text)

        # Right page number
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(PAGE_WIDTH - MARGIN_X, 18, page_str)
        self.restoreState()


def estimate_item_height(itm: dict, show_brand: bool = True) -> float:
    """
    Estimates the vertical rendered height in points for an item row.
    Matches ReportLab and HTML table rendering metrics.
    """
    h = 16.5
    name = str(itm.get('name') or itm.get('item_name') or '')
    if len(name) > 35:
        h += 10.0 * (len(name) // 35)
    brand = str(itm.get('brand') or '').strip()
    if show_brand and brand:
        h += 10.0
    desc = str(itm.get('description') or '').strip()
    if desc:
        lines = max(1, (len(desc) + 40) // 45)
        h += 9.5 * lines
    return h


def chunk_proforma_items(items: list, show_brand: bool = True) -> list:
    """
    Dynamic space calculation and multi-page pagination engine matching Tally, Busy and sales invoices:
    - Calculates the actual vertical height required by each item based on name length, brand, and description.
    - Single page capacity: <= 265 pt of items (fits full header, bill/ship parties, items, and full closing summary).
    - 2-page capacity: Up to (H_P1 + H_LAST) ~980 pt of items (~40-45 single-line items).
      Page 1 holds ~70% of item height, filling the page properly without leaving an empty void.
      Page 2 holds remaining items (at least 80 pt / 5 items) + full statutory closing summary.
    - 3+ pages capacity: Page 1 holds up to 520 pt, intermediate pages up to 680 pt,
      and the final page holds remaining items + full closing summary.
    - Completely eliminates arbitrary 12-item cutoffs, empty white voids, and orphan pages.
    """
    if not items:
        return [{
            'page_number': 1,
            'totalPages': 1,
            'items': [],
            'is_first': True,
            'is_last': True,
            'start_index': 0,
            'brought_forward': 0.0,
            'carried_over': 0.0,
        }]

    # Usable item heights (in points) per page type
    H_SINGLE_ITEMS = 265.0   # Max item height on 1-page document with full footer
    H_P1_MULTI = 520.0       # Max item height on Page 1 of multi-page
    H_MID_MULTI = 680.0      # Max item height on intermediate pages
    H_LAST_MULTI = 460.0     # Max item height on final page with full footer
    MIN_LAST_H = 80.0        # At least 80pt (~4-5 items) on final page to prevent orphan footer

    item_heights = [estimate_item_height(it, show_brand) for it in items]
    total_h = sum(item_heights)

    # 1. Fits on single page
    if total_h <= H_SINGLE_ITEMS:
        tot_taxable = sum(float(it.get('taxable_amount') or 0.0) for it in items)
        return [{
            'page_number': 1,
            'totalPages': 1,
            'items': items,
            'is_first': True,
            'is_last': True,
            'start_index': 0,
            'brought_forward': 0.0,
            'carried_over': tot_taxable,
        }]

    # 2. Fits on 2 pages (Proportional Tally/Busy Balancing)
    chunks = []
    if total_h <= (H_P1_MULTI + H_LAST_MULTI):
        p1_items = []
        p1_h = 0.0
        target_p1_h = min(H_P1_MULTI, max(total_h - H_LAST_MULTI, total_h * 0.70))
        for idx, (it, h) in enumerate(zip(items, item_heights)):
            remaining_h = sum(item_heights[idx:])
            if p1_h + h <= target_p1_h and remaining_h - h >= MIN_LAST_H:
                p1_items.append(it)
                p1_h += h
            else:
                break
        
        if len(p1_items) == 0:
            p1_items = items[:max(1, len(items) // 2)]
        p2_items = items[len(p1_items):]
        chunks = [p1_items, p2_items]
    else:
        # 3 or more pages
        chunks = []
        rem_items = list(items)
        rem_heights = list(item_heights)

        # Page 1
        p1_items = []
        p1_h = 0.0
        while rem_items:
            h = rem_heights[0]
            if p1_h + h <= H_P1_MULTI and len(rem_items) > 3:
                p1_items.append(rem_items.pop(0))
                p1_h += rem_heights.pop(0)
            else:
                break
        chunks.append(p1_items)

        # Middle and final pages
        while rem_items:
            rem_total_h = sum(rem_heights)
            if rem_total_h <= H_LAST_MULTI:
                chunks.append(rem_items)
                break
            else:
                mid_items = []
                mid_h = 0.0
                while rem_items:
                    h = rem_heights[0]
                    if mid_h + h <= H_MID_MULTI and sum(rem_heights[1:]) >= MIN_LAST_H:
                        mid_items.append(rem_items.pop(0))
                        mid_h += rem_heights.pop(0)
                    else:
                        break
                if not mid_items:
                    mid_items.append(rem_items.pop(0))
                    rem_heights.pop(0)
                chunks.append(mid_items)

    total_pages = len(chunks)
    result = []
    running_subtotal = 0.0
    current_start = 0

    for idx, chk in enumerate(chunks):
        p_num = idx + 1
        is_first = (idx == 0)
        is_last = (idx == total_pages - 1)
        bf = running_subtotal
        chk_taxable = sum(float(it.get('taxable_amount') or 0.0) for it in chk)
        running_subtotal += chk_taxable
        co = running_subtotal

        result.append({
            'page_number': p_num,
            'totalPages': total_pages,
            'items': chk,
            'is_first': is_first,
            'is_last': is_last,
            'start_index': current_start,
            'brought_forward': bf,
            'carried_over': co,
        })
        current_start += len(chk)

    return result


class ModernProformaPDFRenderer:
    """
    High-definition, modern, vector PDF renderer for Proforma Invoices and Quotations.
    Matches the exact on-screen ProformaDocumentSheet design:
    - Pure white A4 page with 10mm margins (NO outer black box).
    - Top header: Company logo (optional) + details on left, pill & metadata card on right.
    - Two clean rounded cards for BILL TO and SHIP TO.
    - Hairline items table with slate-50 header and no vertical borders.
    - Amount in words, Bank details with dynamic UPI QR code, and Terms & Conditions.
    - Subtotals and Grand Total card with brand accent highlight.
    - Subtle centered watermark (optional).
    """

    @classmethod
    def render(
        cls,
        dto: Dict[str, Any],
        watermark: bool = True,
        show_logo: bool = True,
        show_brand: bool = True,
    ) -> bytes:
        buffer = io.BytesIO()

        PAGE_WIDTH, PAGE_HEIGHT = A4  # 595.275 x 841.89 pt
        MARGIN_X = 28.35  # 10 mm
        MARGIN_Y = 28.35  # 10 mm
        USABLE_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)  # 538.575 pt

        # Extract DTO fields
        doc_meta = dto.get('document', {})
        seller = dto.get('seller', {})
        buyer = dto.get('buyer', {})
        items = dto.get('items', [])
        subtotals = dto.get('subtotals', {})
        branding = dto.get('branding', {}) or {}

        # Brand accent color
        accent_hex = branding.get('accent_color') or '#0f172a'
        try:
            c_accent = colors.HexColor(accent_hex)
        except Exception:
            c_accent = colors.HexColor('#0f172a')

        # Neutral colors
        c_text = colors.HexColor('#0f172a')
        c_muted = colors.HexColor('#64748b')
        c_dark_muted = colors.HexColor('#334155')
        c_card_bg = colors.HexColor('#f8fafc')
        c_card_border = colors.HexColor('#e2e8f0')
        c_pill_bg = colors.HexColor('#f1f5f9')
        c_row_border = colors.HexColor('#f1f5f9')
        c_table_divider = colors.HexColor('#cbd5e1')
        c_white = colors.HexColor('#ffffff')

        # Fonts configuration
        if SEGOE_LOADED:
            f_norm = 'SegoeUI'
            f_bold = 'SegoeUI-Bold'
            f_italic = 'SegoeUI-Italic'
            f_semi = 'SegoeUI-Semibold'
        elif ROBOTO_LOADED:
            f_norm = 'Roboto'
            f_bold = 'Roboto-Bold'
            f_italic = 'Roboto-Oblique'
            f_semi = 'Roboto-Bold'
        else:
            f_norm = 'Helvetica'
            f_bold = 'Helvetica-Bold'
            f_italic = 'Helvetica-Oblique'
            f_semi = 'Helvetica-Bold'

        # Document type and labels
        doc_type_label = (
            dto.get('document_type_label')
            or doc_meta.get('document_type')
            or ('COMMERCIAL QUOTATION' if dto.get('proforma_type') == 'QUOTATION' else 'PROFORMA INVOICE')
        ).upper()
        is_pi = 'QUOT' not in doc_type_label
        legal_subtitle = (
            "This is a Commercial Proforma — Not a GST Tax Invoice"
            if is_pi
            else "Commercial Estimate / Quotation — Not a GST Tax Invoice"
        )
        inv_no_label = "Proforma No" if is_pi else "Quotation No"

        # Resolve logo data
        logo_img_bytes = None
        logo_data = seller.get('logo_url') or seller.get('logo_data')
        if logo_data and show_logo:
            if isinstance(logo_data, str) and logo_data.startswith('data:image'):
                try:
                    _, b64data = logo_data.split(',', 1)
                    logo_img_bytes = base64.b64decode(b64data)
                except Exception as e:
                    logger.warning(f"Error decoding base64 logo: {e}")
            elif isinstance(logo_data, str) and logo_data.strip():
                clean_p = logo_data.lstrip('/')
                if os.path.exists(clean_p):
                    try:
                        with open(clean_p, 'rb') as f:
                            logo_img_bytes = f.read()
                    except Exception:
                        pass
                else:
                    from django.conf import settings
                    med = os.path.join(getattr(settings, 'MEDIA_ROOT', ''), clean_p)
                    if os.path.exists(med):
                        try:
                            with open(med, 'rb') as f:
                                logo_img_bytes = f.read()
                        except Exception:
                            pass

        # Resolve signature data
        sig_img_bytes = None
        sig_data = seller.get('signature_url') or seller.get('signature_data')
        if sig_data:
            if isinstance(sig_data, str) and sig_data.startswith('data:image'):
                try:
                    _, b64data = sig_data.split(',', 1)
                    sig_img_bytes = base64.b64decode(b64data)
                except Exception:
                    pass
            elif isinstance(sig_data, str) and sig_data.strip():
                clean_p = sig_data.lstrip('/')
                if os.path.exists(clean_p):
                    try:
                        with open(clean_p, 'rb') as f:
                            sig_img_bytes = f.read()
                    except Exception:
                        pass

        # Resolve stamp data
        stamp_img_bytes = None
        stamp_data = seller.get('stamp_url') or seller.get('stamp_data')
        if stamp_data:
            if isinstance(stamp_data, str) and stamp_data.startswith('data:image'):
                try:
                    _, b64data = stamp_data.split(',', 1)
                    stamp_img_bytes = base64.b64decode(b64data)
                except Exception:
                    pass
            elif isinstance(stamp_data, str) and stamp_data.strip():
                clean_p = stamp_data.lstrip('/')
                if os.path.exists(clean_p):
                    try:
                        with open(clean_p, 'rb') as f:
                            stamp_img_bytes = f.read()
                    except Exception:
                        pass

        # Helper to generate RL Image from bytes with fixed max dimensions
        def create_rl_image(img_bytes: bytes, max_w: float, max_h: float) -> Optional[RLImage]:
            try:
                pil_img = PILImage.open(io.BytesIO(img_bytes))
                w, h = pil_img.size
                if w <= 0 or h <= 0:
                    return None
                scale = min(max_w / w, max_h / h)
                target_w = w * scale
                target_h = h * scale
                bio = io.BytesIO(img_bytes)
                return RLImage(bio, width=target_w, height=target_h)
            except Exception as e:
                logger.warning(f"Failed to create RLImage: {e}")
                return None

        # Build styles
        firm_name_size = branding.get('firm_name_size') or 'large'
        if firm_name_size == 'extra_large':
            f_seller_size, f_seller_leading = 22, 25
        elif firm_name_size == 'normal':
            f_seller_size, f_seller_leading = 15, 18
        else:  # default large (matches printed copy text-xl/2xl)
            f_seller_size, f_seller_leading = 18, 21

        s_title_pill = ParagraphStyle(
            'TitlePill',
            fontName=f_bold,
            fontSize=11,
            leading=13.5,
            alignment=TA_CENTER,
            textColor=c_text,
        )
        s_title_sub = ParagraphStyle(
            'TitleSub',
            fontName=f_italic,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_CENTER,
            textColor=c_muted,
        )
        s_seller_name = ParagraphStyle(
            'SellerName',
            fontName=f_bold,
            fontSize=f_seller_size,
            leading=f_seller_leading,
            alignment=TA_LEFT,
            textColor=c_accent,
        )
        s_seller_tagline = ParagraphStyle(
            'SellerTagline',
            fontName=f_italic,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_LEFT,
            textColor=c_muted,
        )
        s_seller_details = ParagraphStyle(
            'SellerDetails',
            fontName=f_norm,
            fontSize=8.5,
            leading=11.5,
            alignment=TA_LEFT,
            textColor=c_dark_muted,
        )
        s_meta_label = ParagraphStyle(
            'MetaLabel',
            fontName=f_norm,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_LEFT,
            textColor=c_muted,
        )
        s_meta_value = ParagraphStyle(
            'MetaValue',
            fontName=f_bold,
            fontSize=9,
            leading=11,
            alignment=TA_RIGHT,
            textColor=c_text,
        )
        s_card_head = ParagraphStyle(
            'CardHead',
            fontName=f_bold,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_LEFT,
            textColor=c_muted,
        )
        s_card_party_name = ParagraphStyle(
            'CardPartyName',
            fontName=f_bold,
            fontSize=11.5,
            leading=14,
            alignment=TA_LEFT,
            textColor=c_text,
        )
        s_card_body = ParagraphStyle(
            'CardBody',
            fontName=f_norm,
            fontSize=8.5,
            leading=11,
            alignment=TA_LEFT,
            textColor=c_dark_muted,
        )
        s_th = ParagraphStyle(
            'TableHead',
            fontName=f_bold,
            fontSize=6.5,
            leading=8.5,
            alignment=TA_LEFT,
            textColor=colors.HexColor('#475569'),
        )
        s_th_center = ParagraphStyle(
            'TableHeadCenter',
            parent=s_th,
            alignment=TA_CENTER,
        )
        s_th_right = ParagraphStyle(
            'TableHeadRight',
            parent=s_th,
            alignment=TA_RIGHT,
        )
        s_td = ParagraphStyle(
            'TableData',
            fontName=f_norm,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_LEFT,
            textColor=c_text,
        )
        s_td_bold = ParagraphStyle(
            'TableDataBold',
            parent=s_td,
            fontName=f_bold,
        )
        s_td_center = ParagraphStyle(
            'TableDataCenter',
            parent=s_td,
            alignment=TA_CENTER,
        )
        s_td_right = ParagraphStyle(
            'TableDataRight',
            parent=s_td,
            alignment=TA_RIGHT,
        )
        s_total_label = ParagraphStyle(
            'TotalLabel',
            fontName=f_norm,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
            textColor=c_muted,
        )
        s_total_val = ParagraphStyle(
            'TotalVal',
            fontName=f_bold,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_RIGHT,
            textColor=c_text,
        )
        s_grand_label = ParagraphStyle(
            'GrandLabel',
            fontName=f_bold,
            fontSize=10.5,
            leading=13,
            alignment=TA_LEFT,
            textColor=c_accent,
        )
        s_grand_val = ParagraphStyle(
            'GrandVal',
            fontName=f_bold,
            fontSize=11.5,
            leading=14,
            alignment=TA_RIGHT,
            textColor=c_accent,
        )
        s_words_head = ParagraphStyle(
            'WordsHead',
            fontName=f_bold,
            fontSize=7.5,
            leading=9.5,
            textColor=c_muted,
        )
        s_words_val = ParagraphStyle(
            'WordsVal',
            fontName=f_bold,
            fontSize=8.5,
            leading=11,
            textColor=c_text,
        )
        s_bank_title = ParagraphStyle(
            'BankTitle',
            fontName=f_bold,
            fontSize=7.5,
            leading=9.5,
            textColor=c_muted,
        )
        s_bank_body = ParagraphStyle(
            'BankBody',
            fontName=f_norm,
            fontSize=8,
            leading=10.5,
            textColor=c_dark_muted,
        )
        s_terms_title = ParagraphStyle(
            'TermsTitle',
            fontName=f_bold,
            fontSize=7.5,
            leading=9.5,
            textColor=c_muted,
        )
        s_terms_body = ParagraphStyle(
            'TermsBody',
            fontName=f_norm,
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor('#475569'),
        )
        s_sig_title = ParagraphStyle(
            'SigTitle',
            fontName=f_bold,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_CENTER,
            textColor=c_muted,
        )
        s_sig_comp = ParagraphStyle(
            'SigComp',
            fontName=f_bold,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_CENTER,
            textColor=c_text,
        )
        s_compact_seller = ParagraphStyle(
            'CompactSeller',
            fontName=f_bold,
            fontSize=9.5,
            leading=11.5,
            textColor=c_accent,
        )
        s_compact_meta = ParagraphStyle(
            'CompactMeta',
            fontName=f_norm,
            fontSize=8.5,
            leading=10.5,
            alignment=TA_RIGHT,
            textColor=c_dark_muted,
        )
        s_carry_label = ParagraphStyle(
            'CarryLabel',
            fontName=f_italic,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_RIGHT,
            textColor=c_dark_muted,
        )
        s_carry_val = ParagraphStyle(
            'CarryVal',
            fontName=f_bold,
            fontSize=7.5,
            leading=9.5,
            alignment=TA_RIGHT,
            textColor=c_text,
        )
        s_cont_main = ParagraphStyle(
            'ContMain',
            fontName=f_italic,
            fontSize=7.5,
            leading=9.5,
            textColor=c_dark_muted,
        )
        s_cont_sub = ParagraphStyle(
            'ContSub',
            fontName=f_norm,
            fontSize=7,
            leading=9,
            alignment=TA_RIGHT,
            textColor=c_muted,
        )

        story = []

        # ═══════════════════════════════════════════════════════════════════
        # 1. HEADER SECTION (Left: Seller details / logo; Right: Pill & Meta)
        # ═══════════════════════════════════════════════════════════════════
        left_header_w = 328.5
        right_header_w = 210.0

        # Build Seller Left Content
        seller_elements = []
        company_name = seller.get('name') or 'VOUCH MERCHANT'
        tagline = seller.get('tagline') or ''

        # If logo enabled and available, show logo alongside / above name
        rl_logo = None
        if show_logo and logo_img_bytes:
            rl_logo = create_rl_image(logo_img_bytes, max_w=120, max_h=42)

        if rl_logo:
            # Table with Logo on left and Name on right
            logo_sub_table = Table(
                [[
                    rl_logo,
                    [
                        Paragraph(company_name.upper(), s_seller_name),
                        Paragraph(tagline, s_seller_tagline) if tagline else Spacer(1, 0),
                    ]
                ]],
                colWidths=[rl_logo.drawWidth + 8, left_header_w - rl_logo.drawWidth - 8]
            )
            logo_sub_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            seller_elements.append(logo_sub_table)
            seller_elements.append(Spacer(1, 4))
        else:
            # Clean typography header without placeholder box
            seller_elements.append(Paragraph(company_name.upper(), s_seller_name))
            if tagline:
                seller_elements.append(Paragraph(tagline, s_seller_tagline))
            seller_elements.append(Spacer(1, 2))

        # Address & Tax info
        addr_lines = []
        raw_addr = seller.get('address') or ''
        city_pin = f"{seller.get('city') or ''} {seller.get('pincode') or ''}".strip()
        state_info = seller.get('state') or ''
        if seller.get('state_code'):
            state_info += f" ({seller.get('state_code')})"
        
        full_addr_line = ", ".join(filter(bool, [raw_addr, city_pin, state_info]))
        if full_addr_line:
            addr_lines.append(full_addr_line)

        tax_contacts = []
        if seller.get('gstin') and seller.get('gstin') != 'Unregistered':
            tax_contacts.append(f"GSTIN: <b>{seller.get('gstin')}</b>")
        if seller.get('pan'):
            tax_contacts.append(f"PAN: <b>{seller.get('pan')}</b>")
        if seller.get('phone'):
            tax_contacts.append(f"Ph: {seller.get('phone')}")
        if tax_contacts:
            addr_lines.append("  |  ".join(tax_contacts))

        web_contacts = []
        if seller.get('email'):
            web_contacts.append(f"Email: {seller.get('email')}")
        if seller.get('website'):
            web_contacts.append(f"Web: {seller.get('website')}")
        if web_contacts:
            addr_lines.append("  |  ".join(web_contacts))

        seller_elements.append(Paragraph("<br/>".join(addr_lines), s_seller_details))

        # Build Right Metadata Content
        # Pill badge
        pill_table = Table(
            [[
                Paragraph(f"<b>{doc_type_label}</b>", s_title_pill),
            ], [
                Paragraph(legal_subtitle, s_title_sub),
            ]],
            colWidths=[right_header_w]
        )
        pill_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_pill_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))

        # Metadata Card
        doc_num = doc_meta.get('document_number') or 'DRAFT'
        doc_date = doc_meta.get('document_date') or ''
        valid_until = doc_meta.get('valid_until') or 'N/A'
        pos = doc_meta.get('place_of_supply') or 'N/A'

        meta_rows = [
            [Paragraph(f"{inv_no_label}:", s_meta_label), Paragraph(f"<b>{doc_num}</b>", s_meta_value)],
            [Paragraph("Date:", s_meta_label), Paragraph(f"<b>{doc_date}</b>", s_meta_value)],
            [Paragraph("Valid Until:", s_meta_label), Paragraph(f"<b>{valid_until}</b>", s_meta_value)],
            [Paragraph("Place of Supply:", s_meta_label), Paragraph(f"<b>{pos}</b>", s_meta_value)],
        ]
        meta_table = Table(meta_rows, colWidths=[72, right_header_w - 72])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, c_pill_bg),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        right_elements = [pill_table, Spacer(1, 4), meta_table]

        header_table = Table(
            [[seller_elements, right_elements]],
            colWidths=[left_header_w, right_header_w]
        )
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        # ═══════════════════════════════════════════════════════════════════
        # 2. PARTIES SECTION (BILL TO & SHIP TO CARDS)
        # ═══════════════════════════════════════════════════════════════════
        card_w = (USABLE_WIDTH - 8.0) / 2.0  # 265.28 pt

        # Buyer info
        buyer_name = buyer.get('name') or 'Customer'
        buyer_addr = buyer.get('address') or ''
        buyer_gstin = buyer.get('gstin') or 'Unregistered'
        buyer_state_code = str(buyer.get('state_code') or '').zfill(2) if buyer.get('state_code') else ''
        buyer_state_name = STATE_NAMES.get(buyer_state_code, buyer.get('state_code') or '')

        # Intra-state vs Inter-state
        is_inter_state = doc_meta.get('is_inter_state', False)
        supply_mode_text = (
            "Inter-State (IGST Applicable)"
            if is_inter_state
            else "Intra-State (CGST + SGST Applicable)"
        )

        bill_to_content = [
            Paragraph("BILL TO (CUSTOMER DETAILS)", s_card_head),
            Spacer(1, 2),
            Paragraph(buyer_name, s_card_party_name),
            Spacer(1, 1),
            Paragraph(buyer_addr if buyer_addr else "Address on record", s_card_body),
            Spacer(1, 2),
            Paragraph(f"GSTIN / UIN: <b>{buyer_gstin}</b>", s_card_body),
            Paragraph(f"State: {buyer_state_name} ({buyer_state_code})" if buyer_state_code else f"State: {buyer_state_name or 'N/A'}", s_card_body),
        ]
        if buyer.get('phone') or buyer.get('email'):
            contacts = filter(bool, [f"Ph: {buyer.get('phone')}" if buyer.get('phone') else '', f"Email: {buyer.get('email')}" if buyer.get('email') else ''])
            bill_to_content.append(Paragraph(" | ".join(contacts), s_card_body))

        ship_to_content = [
            Paragraph("SHIP TO / PLACE OF DELIVERY", s_card_head),
            Spacer(1, 2),
            Paragraph(buyer_name, s_card_party_name),
            Spacer(1, 1),
            Paragraph(buyer_addr if buyer_addr else "Same as billing address", s_card_body),
            Spacer(1, 2),
            Paragraph(f"Destination State: <b>{buyer_state_name or pos}</b>", s_card_body),
            Paragraph(f"Supply Mode: <b>{supply_mode_text}</b>", s_card_body),
        ]

        bill_to_table = Table([[bill_to_content]], colWidths=[card_w])
        bill_to_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        ship_to_table = Table([[ship_to_content]], colWidths=[card_w])
        ship_to_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        parties_table = Table([[bill_to_table, '', ship_to_table]], colWidths=[card_w, 8, card_w])
        parties_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        # ═══════════════════════════════════════════════════════════════════
        # 3. BOTTOM SECTION COMPONENTS (SUMMARY, BANK DETAILS, TERMS & TOTALS)
        # ═══════════════════════════════════════════════════════════════════
        left_bot_w = 314.5
        right_bot_w = 216.0

        # Build Left Column:
        # A. Amount in Words Box
        words_text = dto.get('amount_in_words') or 'Zero Rupees Only'
        if not words_text.startswith('INR '):
            words_text = f"INR {words_text}"
        words_table = Table(
            [[
                [
                    Paragraph("AMOUNT CHARGEABLE (IN WORDS)", s_words_head),
                    Spacer(1, 1),
                    Paragraph(f"<b>{words_text}</b>", s_words_val),
                ]
            ]],
            colWidths=[left_bot_w]
        )
        words_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        # B. Bank Details with optional UPI QR
        bank = seller.get('bank', {})
        bank_name = bank.get('bank_name') or ''
        acc_no = bank.get('account_number') or ''
        ifsc = bank.get('ifsc') or ''
        branch = bank.get('branch') or ''
        upi_id = bank.get('upi_id') or seller.get('upi_id') or dto.get('upi_id') or ''
        upi_url = bank.get('upi_url') or seller.get('upi_url') or dto.get('upi_url') or ''

        if not upi_url and upi_id:
            tot_amt = subtotals.get('grand_total', 0)
            upi_url = (
                f"upi://pay?pa={urllib.parse.quote(upi_id)}"
                f"&pn={urllib.parse.quote(seller.get('name') or 'Merchant')}"
                f"&am={tot_amt:.2f}&tn={urllib.parse.quote(f'Adv {doc_num}')}&cu=INR"
            )
        elif not upi_url and not upi_id and acc_no and ifsc:
            clean_acc = ''.join(c for c in str(acc_no) if c.isalnum())
            clean_ifsc = ''.join(c for c in str(ifsc) if c.isalnum()).upper()
            if clean_acc and clean_ifsc:
                upi_id = f"{clean_acc}@{clean_ifsc}.ifsc.npci"
                tot_amt = subtotals.get('grand_total', 0)
                upi_url = (
                    f"upi://pay?pa={urllib.parse.quote(upi_id)}"
                    f"&pn={urllib.parse.quote(seller.get('name') or 'Merchant')}"
                    f"&am={tot_amt:.2f}&tn={urllib.parse.quote(f'Adv {doc_num}')}&cu=INR"
                )

        rl_upi_qr = None
        if upi_url:
            try:
                qr = qrcode.QRCode(box_size=4, border=1)
                qr.add_data(upi_url)
                qr.make(fit=True)
                qr_pil = qr.make_image(fill_color="black", back_color="white")
                qr_bio = io.BytesIO()
                qr_pil.save(qr_bio, format='PNG')
                qr_bio.seek(0)
                rl_upi_qr = RLImage(qr_bio, width=54, height=54)
            except Exception as e:
                logger.warning(f"Error generating UPI QR: {e}")

        bank_lines = []
        if bank_name:
            bank_lines.append(f"Bank: <b>{bank_name}</b>")
        if acc_no:
            bank_lines.append(f"A/C No: <b>{acc_no}</b>")
        if ifsc:
            bank_lines.append(f"IFSC: <b>{ifsc}</b>")
        if branch:
            bank_lines.append(f"Branch: {branch}")
        if upi_id:
            bank_lines.append(f"UPI ID: <b>{upi_id}</b>")

        bank_text_flow = [
            Paragraph("BANK & PAYMENT DETAILS", s_bank_title),
            Spacer(1, 2),
            Paragraph("<br/>".join(bank_lines) if bank_lines else "Bank details available on request", s_bank_body),
        ]

        if rl_upi_qr:
            bank_inner_table = Table(
                [[
                    bank_text_flow,
                    [
                        rl_upi_qr,
                        Spacer(1, 1),
                        Paragraph("<font size=5 color='#475569'><b>SCAN &amp; PAY UPI</b></font>", s_th_center)
                    ]
                ]],
                colWidths=[left_bot_w - 65, 57]
            )
            bank_inner_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('LINEBEFORE', (1, 0), (1, 0), 0.5, c_card_border),
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('RIGHTPADDING', (0, 0), (0, 0), 4),
                ('LEFTPADDING', (1, 0), (1, 0), 4),
                ('RIGHTPADDING', (1, 0), (1, 0), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            bank_table_content = bank_inner_table
        else:
            bank_table_content = bank_text_flow

        bank_card = Table([[bank_table_content]], colWidths=[left_bot_w])
        bank_card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))

        # C. Terms & Conditions
        raw_terms = doc_meta.get('terms_and_conditions') or (
            "1. Prices quoted are valid for 15 days from the date of issuance.\n"
            "2. Delivery within 3-5 business days upon order confirmation.\n"
            "3. 100% payment required prior to dispatch / delivery.\n"
            "4. Applicable GST will be invoiced on the final Tax Invoice."
        )
        terms_paragraphs = [
            Paragraph("TERMS & CONDITIONS:", s_terms_title),
            Spacer(1, 2),
            Paragraph(raw_terms.replace('\n', '<br/>'), s_terms_body),
        ]

        customer_notes = str(dto.get('customer_notes') or doc_meta.get('customer_notes') or doc_meta.get('narration') or '').strip()

        left_bottom_elements = [
            words_table,
            Spacer(1, 5),
            bank_card,
            Spacer(1, 5),
            terms_paragraphs,
        ]

        # D. Customer Notes / Remarks (matching ProformaDocumentSheet)
        if customer_notes:
            left_bottom_elements.append(Spacer(1, 4))
            left_bottom_elements.append(Paragraph("REMARKS / NOTES:", s_terms_title))
            left_bottom_elements.append(Spacer(1, 1))
            left_bottom_elements.append(Paragraph(f"<i>{customer_notes.replace(chr(10), '<br/>')}</i>", s_terms_body))

        # Build Right Column: Subtotals & Grand Total Card + HSN Summary
        taxable_tot = subtotals.get('taxable_amount', 0)
        cgst_tot = subtotals.get('cgst_amount', 0)
        sgst_tot = subtotals.get('sgst_amount', 0)
        igst_tot = subtotals.get('igst_amount', 0)
        cartage = subtotals.get('cartage_amount', 0)
        round_off = subtotals.get('round_off', 0)
        grand_total = subtotals.get('grand_total', 0)

        tot_rows = [
            [Paragraph("Taxable Amount", s_total_label), Paragraph(fmt_curr(taxable_tot), s_total_val)],
        ]
        if is_inter_state:
            tot_rows.append([Paragraph("Integrated GST (IGST)", s_total_label), Paragraph(fmt_curr(igst_tot), s_total_val)])
        else:
            tot_rows.append([Paragraph("Central GST (CGST)", s_total_label), Paragraph(fmt_curr(cgst_tot), s_total_val)])
            tot_rows.append([Paragraph("State GST (SGST)", s_total_label), Paragraph(fmt_curr(sgst_tot), s_total_val)])

        if cartage > 0:
            tot_rows.append([Paragraph("Cartage / Delivery", s_total_label), Paragraph(fmt_curr(cartage), s_total_val)])
        if abs(round_off) >= 0.005:
            tot_rows.append([Paragraph("Round Off", s_total_label), Paragraph(f"+{round_off:.2f}" if round_off > 0 else f"{round_off:.2f}", s_total_val)])

        tot_rows.append([
            Paragraph("Grand Total", s_grand_label),
            Paragraph(f"₹ {fmt_curr(grand_total)}", s_grand_val),
        ])

        totals_table = Table(tot_rows, colWidths=[right_bot_w - 90, 90])
        totals_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -2), c_card_bg),
            ('BACKGROUND', (0, -1), (-1, -1), c_pill_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LINEBELOW', (0, -2), (-1, -2), 0.75, c_table_divider),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -2), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -2), 3),
            ('TOPPADDING', (0, -1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        right_bottom_elements = [totals_table]

        # Small HSN Summary Table (matching ProformaDocumentSheet)
        hsn_summary = dto.get('hsn_summary') or []
        if hsn_summary:
            hsn_rows = [[
                Paragraph("HSN/SAC", s_th),
                Paragraph("Taxable", s_th_right),
                Paragraph("Tax", s_th_right),
            ]]
            for h in hsn_summary:
                code_str = f"{h.get('hsn_code', '—')} ({h.get('gst_rate', 0):.0f}%)"
                hsn_rows.append([
                    Paragraph(code_str, s_td),
                    Paragraph(fmt_curr(h.get('taxable_amount', 0)), s_td_right),
                    Paragraph(fmt_curr(h.get('total_tax', 0)), s_td_right),
                ])
            hsn_table = Table(hsn_rows, colWidths=[right_bot_w - 110, 55, 55])
            hsn_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), c_card_bg),
                ('BOX', (0, 0), (-1, -1), 0.5, c_card_border),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, c_pill_bg),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            right_bottom_elements.append(Spacer(1, 4))
            right_bottom_elements.append(hsn_table)

        bottom_table = Table([[left_bottom_elements, '', right_bottom_elements]], colWidths=[left_bot_w, 8, right_bot_w])
        bottom_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        # Signature Block: Full-width matching ProformaDocumentSheet
        rl_sig = create_rl_image(sig_img_bytes, max_w=85, max_h=30) if sig_img_bytes else None
        rl_stamp = create_rl_image(stamp_img_bytes, max_w=50, max_h=30) if stamp_img_bytes else None

        sig_media_flow = []
        if rl_sig or rl_stamp:
            sig_row = []
            if rl_sig:
                sig_row.append(rl_sig)
            if rl_stamp:
                sig_row.append(rl_stamp)
            sig_media_table = Table([sig_row])
            sig_media_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            sig_media_flow.append(sig_media_table)
        else:
            sig_media_flow.append(Spacer(1, 22))

        cust_acc_sub = Table(
            [[
                Paragraph("Authorized Signatory", s_terms_body),
                Paragraph("Date: ____________", s_total_val),
            ]],
            colWidths=[120, 131]
        )
        cust_acc_sub.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        cust_acc_flow = [
            Paragraph("CUSTOMER ACCEPTANCE / SEAL & SIGNATURE", s_card_head),
            Spacer(1, 24),
            cust_acc_sub,
        ]
        cust_acc_card = Table([[cust_acc_flow]], colWidths=[card_w])
        cust_acc_card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        seller_sig_flow = [
            Paragraph(f"For <b>{company_name}</b>", s_sig_comp),
            Spacer(1, 2),
            sig_media_flow,
            Spacer(1, 2),
            Paragraph("Authorised Signatory", s_sig_title),
        ]
        seller_sig_card = Table([[seller_sig_flow]], colWidths=[card_w])
        seller_sig_card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
            ('BOX', (0, 0), (-1, -1), 0.75, c_card_border),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        full_sig_table = Table([[cust_acc_card, '', seller_sig_card]], colWidths=[card_w, 8, card_w])
        full_sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        # ═══════════════════════════════════════════════════════════════════
        # 4. MULTI-PAGE STORY ASSEMBLY (EXACT MATCH TO PROFORMA DOCUMENT SHEET)
        # ═══════════════════════════════════════════════════════════════════
        col_widths = [22, 154, 46, 34, 30, 50, 40, 56, 42, 64.5]
        page_chunks = chunk_proforma_items(items, show_brand=show_brand)
        total_pages = len(page_chunks)

        for p_idx, chunk_data in enumerate(page_chunks):
            if p_idx > 0:
                story.append(PageBreak())

            p_num = chunk_data['page_number']
            is_first = chunk_data['is_first']
            is_last = chunk_data['is_last']
            chunk_items = chunk_data['items']
            start_idx = chunk_data['start_index']
            bf_subtotal = chunk_data['brought_forward']
            co_subtotal = chunk_data['carried_over']

            if is_first:
                story.append(header_table)
                story.append(Spacer(1, 5))
                story.append(HRFlowable(
                    width=USABLE_WIDTH,
                    thickness=0.75,
                    color=c_card_border,
                    spaceBefore=0,
                    spaceAfter=5,
                ))
                story.append(parties_table)
                story.append(Spacer(1, 6))
            else:
                sep = " • " if (SEGOE_LOADED or ROBOTO_LOADED) else " - "
                compact_header_table = Table(
                    [[
                        Paragraph(f"<b>{company_name.upper()}</b>  <font color='#94a3b8'>{sep}</font>  <font color='#475569'><b>{doc_type_label}</b></font>", s_compact_seller),
                        Paragraph(f"<font color='#64748b'>Doc:</font> <b>{doc_num}</b>    <font color='#64748b'>Date:</font> <b>{doc_date}</b>", s_compact_meta),
                    ]],
                    colWidths=[USABLE_WIDTH * 0.6, USABLE_WIDTH * 0.4]
                )
                compact_header_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LINEBELOW', (0, 0), (-1, -1), 0.75, c_card_border),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]))
                story.append(compact_header_table)
                story.append(Spacer(1, 6))

            # Table Data for this page
            page_table_data = [[
                Paragraph("#", s_th_center),
                Paragraph("DESCRIPTION OF GOODS / SERVICES", s_th),
                Paragraph("HSN/SAC", s_th_center),
                Paragraph("QTY", s_th_right),
                Paragraph("UNIT", s_th_center),
                Paragraph("RATE", s_th_right),
                Paragraph("DISC%", s_th_right),
                Paragraph("TAXABLE", s_th_right),
                Paragraph("GST", s_th_center),
                Paragraph("AMOUNT", s_th_right),
            ]]

            table_styles = [
                ('BACKGROUND', (0, 0), (-1, 0), c_card_bg),
                ('LINEABOVE', (0, 0), (-1, 0), 0.75, c_card_border),
                ('LINEBELOW', (0, 0), (-1, 0), 1.0, c_table_divider),
                ('TOPPADDING', (0, 0), (-1, -1), 3.0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3.0),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ]

            # Brought forward row on Page 2+
            if not is_first:
                bf_row_idx = len(page_table_data)
                page_table_data.append([
                    Paragraph(f"<i>Total Brought Forward from Page {p_num - 1} &rarr;</i>", s_carry_label),
                    "", "", "", "", "", "",
                    Paragraph(fmt_curr(bf_subtotal), s_carry_val),
                    "", ""
                ])
                table_styles.extend([
                    ('SPAN', (0, bf_row_idx), (6, bf_row_idx)),
                    ('BACKGROUND', (0, bf_row_idx), (-1, bf_row_idx), colors.HexColor('#f8fafc')),
                    ('LINEBELOW', (0, bf_row_idx), (-1, bf_row_idx), 1.0, colors.HexColor('#cbd5e1')),
                    ('TOPPADDING', (0, bf_row_idx), (-1, bf_row_idx), 3.0),
                    ('BOTTOMPADDING', (0, bf_row_idx), (-1, bf_row_idx), 3.0),
                ])

            # Page items
            for idx, itm in enumerate(chunk_items):
                row_serial = start_idx + idx + 1
                name = itm.get('name') or itm.get('item_name') or 'Item'
                brand = (itm.get('brand') or '').strip()
                desc = (itm.get('description') or '').strip()
                hsn = itm.get('hsn_code') or '-'
                qty = itm.get('quantity', 0)
                unit = itm.get('unit') or 'PCS'
                rate = itm.get('rate', 0)
                disc = itm.get('discount_percent', 0)
                taxable = itm.get('taxable_amount', 0)
                gst_r = itm.get('gst_rate', 0)
                amount = itm.get('total_amount', 0)

                disc_str = f"{disc:.2f}%" if disc > 0 else "-"
                gst_str = f"{gst_r:.0f}%" if gst_r % 1 == 0 else f"{gst_r:.1f}%"

                desc_elements = [Paragraph(f"<b>{name}</b>", s_td_bold)]
                if show_brand and brand:
                    desc_elements.append(Spacer(1, 1))
                    desc_elements.append(Paragraph(f"<font size=5.5 color='#1d4ed8'><b>BRAND: {brand.upper()}</b></font>", s_td))
                if desc:
                    desc_elements.append(Spacer(1, 1))
                    desc_elements.append(Paragraph(f"<font size=5.5 color='#64748b'>{desc}</font>", s_td))

                item_row_idx = len(page_table_data)
                page_table_data.append([
                    Paragraph(str(row_serial), s_td_center),
                    desc_elements,
                    Paragraph(str(hsn), s_td_center),
                    Paragraph(f"{qty:.2f}".rstrip('0').rstrip('.') if qty % 1 == 0 else f"{qty:.2f}", s_td_right),
                    Paragraph(unit.upper(), s_td_center),
                    Paragraph(fmt_curr(rate), s_td_right),
                    Paragraph(disc_str, s_td_right),
                    Paragraph(fmt_curr(taxable), s_td_right),
                    Paragraph(gst_str, s_td_center),
                    Paragraph(fmt_curr(amount), s_td_right),
                ])
                table_styles.append(('LINEBELOW', (0, item_row_idx), (-1, item_row_idx), 0.5, c_row_border))

            # Carried over row on non-final pages
            if not is_last:
                co_row_idx = len(page_table_data)
                page_table_data.append([
                    Paragraph(f"<i>Total Carried Over to Page {p_num + 1} &rarr;</i>", s_carry_label),
                    "", "", "", "", "", "",
                    Paragraph(fmt_curr(co_subtotal), s_carry_val),
                    "", ""
                ])
                table_styles.extend([
                    ('SPAN', (0, co_row_idx), (6, co_row_idx)),
                    ('BACKGROUND', (0, co_row_idx), (-1, co_row_idx), colors.HexColor('#f8fafc')),
                    ('LINEABOVE', (0, co_row_idx), (-1, co_row_idx), 1.0, colors.HexColor('#cbd5e1')),
                    ('TOPPADDING', (0, co_row_idx), (-1, co_row_idx), 3.0),
                    ('BOTTOMPADDING', (0, co_row_idx), (-1, co_row_idx), 3.0),
                ])

            p_table = Table(page_table_data, colWidths=col_widths)
            p_table.setStyle(TableStyle(table_styles))
            story.append(p_table)

            if not is_last:
                # Continuation Notice - pushed to bottom of page matching ProformaDocumentSheet
                cont_table = Table(
                    [[
                        Paragraph(f"<i>Document continued on Page {p_num + 1} of {total_pages}...</i>", s_cont_main),
                        Paragraph(f"(Commercial Summary, Bank Details &amp; Signatures on Page {total_pages})", s_cont_sub),
                    ]],
                    colWidths=[USABLE_WIDTH * 0.55, USABLE_WIDTH * 0.45]
                )
                cont_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), c_pill_bg),
                    ('BOX', (0, 0), (-1, -1), 0.5, c_card_border),
                    ('LINEABOVE', (0, 0), (-1, -1), 1.0, colors.HexColor('#cbd5e1')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(PushToBottomAndDraw([cont_table]))
            else:
                # Final Page Summary & Signatures Block - PUSHED TO BOTTOM TO MATCH PROFORMA DOCUMENT SHEET
                story.append(PushToBottomAndDraw([
                    bottom_table,
                    Spacer(1, 8),
                    full_sig_table,
                ]))

        # ═══════════════════════════════════════════════════════════════════
        # 5. WATERMARK CALLBACK
        # ═══════════════════════════════════════════════════════════════════
        def on_page_decorations(canv, doc):
            if watermark:
                canv.saveState()
                if show_logo and logo_img_bytes:
                    try:
                        canv.setFillAlpha(0.045)
                        wm_dim = 250
                        bio = io.BytesIO(logo_img_bytes)
                        canv.drawImage(
                            bio,
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
                    canv.setFont(f_bold, 32)
                    canv.setFillColor(colors.HexColor('#0f172a'))
                    canv.setFillAlpha(0.035)
                    canv.translate(PAGE_WIDTH / 2, PAGE_HEIGHT / 2)
                    canv.rotate(35)
                    canv.drawCentredString(0, 0, (company_name or "PROFORMA INVOICE").upper())
                canv.restoreState()

        # Build Document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=MARGIN_Y,
            bottomMargin=44,
        )

        class CustomNumberedCanvas(ProformaNumberedCanvas):
            doc_number = doc_num
            footer_legal_text = legal_subtitle

        doc.build(
            story,
            onFirstPage=on_page_decorations,
            onLaterPages=on_page_decorations,
            canvasmaker=CustomNumberedCanvas,
        )

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

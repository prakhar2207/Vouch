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
    BaseDocTemplate,
    PageTemplate,
    Frame,
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


def number_to_words(num_amount: Decimal) -> str:
    """Converts a Decimal amount to words using the exact Indian numbering system from print page."""
    a = ['', 'One ', 'Two ', 'Three ', 'Four ', 'Five ', 'Six ', 'Seven ', 'Eight ', 'Nine ', 'Ten ', 'Eleven ', 'Twelve ', 'Thirteen ', 'Fourteen ', 'Fifteen ', 'Sixteen ', 'Seventeen ', 'Eighteen ', 'Nineteen ']
    b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

    num_val = int(round(float(num_amount)))
    num_str = str(num_val)
    if len(num_str) > 9:
        return 'overflow'

    padded = num_str.zfill(9)
    c_crore = int(padded[0:2])
    c_lakh = int(padded[2:4])
    c_th = int(padded[4:6])
    c_h = int(padded[6:7])
    c_tens = int(padded[7:9])

    def two_digits(val):
        if val < 20:
            return a[val]
        return b[val // 10] + ' ' + a[val % 10]

    s = ''
    if c_crore > 0:
        s += two_digits(c_crore).strip() + ' Crore '
    if c_lakh > 0:
        s += two_digits(c_lakh).strip() + ' Lakh '
    if c_th > 0:
        s += two_digits(c_th).strip() + ' Thousand '
    if c_h > 0:
        s += two_digits(c_h).strip() + ' Hundred '
    if c_tens > 0:
        if s:
            s += 'and '
        s += two_digits(c_tens).strip()

    return s.strip() + ' Only'


# Alias for backwards compatibility
amount_to_words_indian = number_to_words


class InvoicePDFService:
    """
    Generates high-definition, compliant GST Tax Invoice PDFs matching the
    exact standard Indian B2B boxed layout (mirroring the browser print / Save as PDF view).
    Guarantees:
      - Strictly 1 single page for moderate invoices (<= ~12 items).
      - Multi-page with footer on every page and 'Page X of Y' for large invoices (> 12 items).
    Delegates to the canonical InvoicePDFRenderer to ensure single-source-of-truth.
    """

    @classmethod
    def generate_invoice_pdf(cls, voucher: Voucher) -> bytes:
        from apps.documents.dto.invoice_dto import build_invoice_dto
        from apps.documents.renderers.invoice_renderer import InvoicePDFRenderer
        dto = build_invoice_dto(voucher)
        return InvoicePDFRenderer.render(dto)



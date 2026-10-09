import logging
from typing import Optional
from django.core.cache import cache

from apps.accounting.models import Voucher
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.documents.models import DocumentSnapshot
from apps.documents.renderers import (
    InvoicePDFRenderer,
    ModernProformaPDFRenderer,
    VoucherPDFRenderer,
    StatementPDFRenderer,
    ReportPDFRenderer,
)
from apps.documents.services.snapshot_service import DocumentSnapshotService

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 3600  # 1 Hour Cache


class DocumentPDFService:
    """
    Renders deterministic PDF documents on demand.
    Uses temporary caching (Redis / LocMem) with TTL.
    Zero PDF BLOBs stored in PostgreSQL database.
    """

    @classmethod
    def get_cache_key(
        cls,
        snapshot: DocumentSnapshot,
        watermark: bool = False,
        show_logo: bool = True,
        copy_type: str = 'ORIGINAL',
    ) -> str:
        version = getattr(snapshot, 'source_version', 1) or 1
        updated_ts = ''
        if isinstance(snapshot.snapshot_json, dict):
            updated_ts = snapshot.snapshot_json.get('_voucher_updated_at') or snapshot.snapshot_json.get('_proforma_updated_at') or ''
        ts_clean = ''.join(c for c in str(updated_ts) if c.isalnum())
        cp_clean = ''.join(c for c in str(copy_type or 'ORIGINAL').upper() if c.isalnum())
        return f"vouch_pdf_{snapshot.id}_v{version}_{ts_clean}_{snapshot.template_version}_wm{int(watermark)}_lg{int(show_logo)}_cp{cp_clean}"

    @classmethod
    def invalidate_cache_for_snapshot(cls, snapshot: DocumentSnapshot):
        for wm in [0, 1]:
            for lg in [0, 1]:
                cache.delete(f"vouch_pdf_{snapshot.id}_{snapshot.template_version}_wm{wm}_lg{lg}")
                cache.delete(cls.get_cache_key(snapshot, watermark=bool(wm), show_logo=bool(lg)))

    @classmethod
    def generate_pdf_from_snapshot(
        cls,
        snapshot: DocumentSnapshot,
        bypass_cache: bool = False,
        watermark: bool = False,
        show_logo: bool = True,
        copy_type: str = 'ORIGINAL',
    ) -> bytes:
        cache_key = cls.get_cache_key(snapshot, watermark=watermark, show_logo=show_logo, copy_type=copy_type)

        if not bypass_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data

        dto = snapshot.snapshot_json
        doc_type = snapshot.document_type

        # Check document-level branding preference for logo if default True
        if show_logo is True:
            branding = dto.get('branding') or {}
            if branding.get('show_logo') is False:
                show_logo = False

        if doc_type == 'PROFORMA_INVOICE' or dto.get('is_proforma'):
            pdf_bytes = ModernProformaPDFRenderer.render(
                dto, watermark=watermark, show_logo=show_logo
            )
        elif doc_type in ['SALES_INVOICE', 'PURCHASE_INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE']:
            pdf_bytes = InvoicePDFRenderer.render(dto, watermark=watermark, copy_type=copy_type)
        elif doc_type in ['PAYMENT', 'RECEIPT', 'CONTRA', 'JOURNAL']:
            pdf_bytes = VoucherPDFRenderer.render(dto)
        elif doc_type in ['CUSTOMER_STATEMENT', 'SUPPLIER_STATEMENT', 'LEDGER']:
            pdf_bytes = StatementPDFRenderer.render(dto)
        elif doc_type in ['TRIAL_BALANCE', 'PROFIT_AND_LOSS', 'BALANCE_SHEET']:
            pdf_bytes = ReportPDFRenderer.render(dto)
        else:
            # Fallback to invoice renderer
            pdf_bytes = InvoicePDFRenderer.render(dto, watermark=watermark, copy_type=copy_type)

        # Store in ephemeral cache
        try:
            cache.set(cache_key, pdf_bytes, timeout=CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Could not cache PDF {cache_key}: {e}")

        return pdf_bytes

    @classmethod
    def generate_pdf_for_voucher(
        cls,
        voucher: Voucher,
        bypass_cache: bool = False,
        copy_type: str = 'ORIGINAL',
    ) -> bytes:
        """
        Convenience method to render any Voucher (Sales, Purchase, Payment, etc.).
        Retrieves or lazy-creates the DocumentSnapshot first.
        """
        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(
            voucher, force_refresh=bypass_cache
        )
        return cls.generate_pdf_from_snapshot(snapshot, bypass_cache=bypass_cache, copy_type=copy_type)

    @classmethod
    def generate_pdf_for_statement(
        cls,
        company: Company,
        ledger: Ledger,
        from_date=None,
        to_date=None,
    ) -> bytes:
        """
        Generates PDF for customer, supplier, or general ledger statement.
        """
        from apps.documents.dto import build_statement_dto
        dto = build_statement_dto(company, ledger, from_date=from_date, to_date=to_date)
        return StatementPDFRenderer.render(dto)

    @classmethod
    def generate_pdf_for_report(
        cls,
        report_type: str,
        company: Company,
        from_date=None,
        to_date=None,
        as_of_date=None,
    ) -> bytes:
        """
        Generates PDF for Trial Balance, P&L, or Balance Sheet.
        """
        from apps.documents.dto import build_report_dto
        dto = build_report_dto(
            report_type,
            company,
            from_date=from_date,
            to_date=to_date,
            as_of_date=as_of_date,
        )
        return ReportPDFRenderer.render(dto)

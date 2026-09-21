import logging
from datetime import date
from typing import Optional

from django.db import transaction
from apps.accounting.models import Voucher
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.documents.models import DocumentSnapshot
from apps.documents.dto import (
    build_invoice_dto,
    build_voucher_dto,
    build_statement_dto,
    build_report_dto,
)

logger = logging.getLogger(__name__)

VOUCHER_TYPE_TO_DOC_TYPE = {
    'SALES': 'SALES_INVOICE',
    'PURCHASE': 'PURCHASE_INVOICE',
    'CREDIT_NOTE': 'CREDIT_NOTE',
    'DEBIT_NOTE': 'DEBIT_NOTE',
    'PAYMENT': 'PAYMENT',
    'RECEIPT': 'RECEIPT',
    'CONTRA': 'CONTRA',
    'JOURNAL': 'JOURNAL',
}


class DocumentSnapshotService:
    """
    Manages generation and retrieval of immutable DocumentSnapshots.
    Ensures canonical DTO is persisted in PostgreSQL as JSON (zero PDF BLOBs).
    """

    @classmethod
    def get_or_create_voucher_snapshot(
        cls,
        voucher: Voucher,
        user=None,
        force_refresh: bool = False,
    ) -> DocumentSnapshot:
        """
        Retrieves existing snapshot for a voucher, or lazy-generates one.
        If force_refresh is True, updates the snapshot JSON with freshly computed DTO.
        """
        doc_type = VOUCHER_TYPE_TO_DOC_TYPE.get(voucher.voucher_type, 'SALES_INVOICE')
        source_id = str(voucher.id)

        CURRENT_TEMPLATE_VERSION = '2.0'
        if not force_refresh:
            existing = DocumentSnapshot.objects.filter(
                company=voucher.company,
                source_type='Voucher',
                source_id=source_id,
            ).first()
            if existing and existing.template_version == CURRENT_TEMPLATE_VERSION:
                return existing

        # Build Canonical DTO
        if doc_type in ['SALES_INVOICE', 'PURCHASE_INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE']:
            dto = build_invoice_dto(voucher)
            template_code = 'gst_invoice_classic'
        else:
            dto = build_voucher_dto(voucher)
            template_code = 'voucher_slip'

        with transaction.atomic():
            snapshot, _ = DocumentSnapshot.objects.update_or_create(
                company=voucher.company,
                source_type='Voucher',
                source_id=source_id,
                defaults={
                    'document_type': doc_type,
                    'document_number': voucher.voucher_number,
                    'document_date': voucher.voucher_date,
                    'total_amount': voucher.total_amount,
                    'snapshot_json': dto,
                    'template_code': template_code,
                    'template_version': CURRENT_TEMPLATE_VERSION,
                    'created_by': user or voucher.created_by,
                }
            )
        return snapshot

    @classmethod
    def create_statement_snapshot(
        cls,
        company: Company,
        ledger: Ledger,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        user=None,
    ) -> DocumentSnapshot:
        """
        Creates an immutable snapshot for a ledger or party statement.
        """
        dto = build_statement_dto(company, ledger, from_date=from_date, to_date=to_date)
        doc_type = dto['document']['document_type']

        range_str = f"{from_date or 'init'}_{to_date or 'now'}"
        source_id = f"{ledger.id}:{range_str}"

        snapshot = DocumentSnapshot.objects.create(
            company=company,
            document_type=doc_type,
            source_type='Ledger',
            source_id=source_id,
            document_number=f"STMT/{ledger.name[:10]}/{range_str}",
            document_date=to_date or date.today(),
            total_amount=dto['closing_balance']['amount'],
            snapshot_json=dto,
            template_code='standard_statement',
            template_version='1.0',
            created_by=user,
        )
        return snapshot

    @classmethod
    def create_report_snapshot(
        cls,
        report_type: str,
        company: Company,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        user=None,
    ) -> DocumentSnapshot:
        """
        Creates an immutable snapshot for financial statements (Trial Balance, P&L, Balance Sheet).
        """
        dto = build_report_dto(
            report_type,
            company,
            from_date=from_date,
            to_date=to_date,
            as_of_date=as_of_date,
        )

        d_date = as_of_date or to_date or date.today()
        snapshot = DocumentSnapshot.objects.create(
            company=company,
            document_type=report_type.upper(),
            source_type='Report',
            source_id=f"{report_type.upper()}:{d_date}",
            document_number=f"REP/{report_type.upper()}/{d_date}",
            document_date=d_date,
            total_amount=None,
            snapshot_json=dto,
            template_code='financial_report',
            template_version='1.0',
            created_by=user,
        )
        return snapshot

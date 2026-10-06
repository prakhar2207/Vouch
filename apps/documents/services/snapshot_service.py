import logging
from decimal import Decimal
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
        If force_refresh is True, or if the voucher was edited/updated, updates the snapshot JSON with freshly computed DTO.
        """
        doc_type = VOUCHER_TYPE_TO_DOC_TYPE.get(voucher.voucher_type, 'SALES_INVOICE')
        source_id = str(voucher.id)

        CURRENT_TEMPLATE_VERSION = '2.1'
        v_updated_at = str(voucher.updated_at) if hasattr(voucher, 'updated_at') and voucher.updated_at else ''

        if not force_refresh:
            existing = DocumentSnapshot.objects.filter(
                company=voucher.company,
                source_type='Voucher',
                source_id=source_id,
            ).first()
            if existing and existing.template_version == CURRENT_TEMPLATE_VERSION:
                # Check for staleness: does the existing snapshot reflect current voucher state?
                existing_snap = existing.snapshot_json or {}
                snap_updated_at = existing_snap.get('_voucher_updated_at', '')
                
                is_stale = False
                if v_updated_at and snap_updated_at and snap_updated_at != v_updated_at:
                    is_stale = True
                elif not snap_updated_at:
                    # Legacy snapshot missing timestamp, verify amounts and party
                    if existing.total_amount is not None and voucher.total_amount is not None:
                        if Decimal(str(existing.total_amount)) != Decimal(str(voucher.total_amount)):
                            is_stale = True
                    if existing.document_number != voucher.voucher_number:
                        is_stale = True
                    if str(existing.document_date or '') != str(voucher.voucher_date or ''):
                        is_stale = True
                    # Check party name
                    existing_party = existing_snap.get('buyer', {}).get('name', '')
                    current_party = voucher.party_ledger.name if (voucher.party_ledger and voucher.party_ledger.name.strip().upper() not in ['CASH', 'COUNTER SALE']) else (voucher.buyer_name or '')
                    if existing_party and current_party and existing_party.strip().upper() != current_party.strip().upper():
                        is_stale = True
                else:
                    # Even if timestamps match, double check voucher fields
                    if existing.total_amount is not None and voucher.total_amount is not None:
                        if Decimal(str(existing.total_amount)) != Decimal(str(voucher.total_amount)):
                            is_stale = True
                    if existing.document_number != voucher.voucher_number:
                        is_stale = True
                    if str(existing.document_date or '') != str(voucher.voucher_date or ''):
                        is_stale = True

                if not is_stale:
                    return existing

        # Build Canonical DTO
        if doc_type in ['SALES_INVOICE', 'PURCHASE_INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE']:
            dto = build_invoice_dto(voucher)
            template_code = 'gst_invoice_classic'
        else:
            dto = build_voucher_dto(voucher)
            template_code = 'voucher_slip'

        if v_updated_at:
            dto['_voucher_updated_at'] = v_updated_at

        with transaction.atomic():
            existing = DocumentSnapshot.objects.filter(
                company=voucher.company,
                source_type='Voucher',
                source_id=source_id,
            ).first()
            next_version = (existing.source_version + 1) if existing else 1

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
                    'source_version': next_version,
                    'created_by': user or voucher.created_by,
                }
            )

        # Invalidate any cached PDF for this snapshot
        try:
            from apps.documents.services.pdf_service import DocumentPDFService
            DocumentPDFService.invalidate_cache_for_snapshot(snapshot)
        except Exception:
            pass

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

    @classmethod
    def get_or_create_proforma_snapshot(cls, proforma, user=None, force_refresh: bool = False) -> DocumentSnapshot:
        """
        Retrieves or creates an immutable DocumentSnapshot for a ProformaInvoice.
        This enables the standard share token infrastructure to work for proformas.
        """
        from apps.documents.dto.proforma_dto import build_proforma_dto

        CURRENT_TEMPLATE_VERSION = '2.0'
        source_id = str(proforma.id)
        p_updated_at = str(proforma.updated_at) if hasattr(proforma, 'updated_at') and proforma.updated_at else ''

        if not force_refresh:
            existing = DocumentSnapshot.objects.filter(
                company=proforma.company,
                source_type='ProformaInvoice',
                source_id=source_id,
            ).first()
            if existing and existing.template_version == CURRENT_TEMPLATE_VERSION:
                existing_snap = existing.snapshot_json or {}
                snap_updated_at = existing_snap.get('_proforma_updated_at', '')
                is_stale = False
                if p_updated_at and snap_updated_at and snap_updated_at != p_updated_at:
                    is_stale = True
                elif not snap_updated_at:
                    if existing.total_amount is not None and proforma.total_amount is not None:
                        if Decimal(str(existing.total_amount)) != Decimal(str(proforma.total_amount)):
                            is_stale = True
                    if existing.document_number != proforma.proforma_number:
                        is_stale = True
                else:
                    if existing.total_amount is not None and proforma.total_amount is not None:
                        if Decimal(str(existing.total_amount)) != Decimal(str(proforma.total_amount)):
                            is_stale = True

                if not is_stale:
                    return existing

        dto = build_proforma_dto(proforma)
        if p_updated_at:
            dto['_proforma_updated_at'] = p_updated_at

        with transaction.atomic():
            existing = DocumentSnapshot.objects.filter(
                company=proforma.company,
                source_type='ProformaInvoice',
                source_id=source_id,
            ).first()
            next_version = (existing.source_version + 1) if existing else 1

            snapshot, _ = DocumentSnapshot.objects.update_or_create(
                company=proforma.company,
                source_type='ProformaInvoice',
                source_id=source_id,
                defaults={
                    'document_type': 'PROFORMA_INVOICE',
                    'document_number': proforma.proforma_number,
                    'document_date': proforma.date,
                    'total_amount': proforma.total_amount,
                    'snapshot_json': dto,
                    'template_code': 'proforma_invoice',
                    'template_version': CURRENT_TEMPLATE_VERSION,
                    'source_version': next_version,
                    'created_by': user or proforma.created_by,
                }
            )

        try:
            from apps.documents.services.pdf_service import DocumentPDFService
            DocumentPDFService.invalidate_cache_for_snapshot(snapshot)
        except Exception:
            pass

        return snapshot


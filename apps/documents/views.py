import logging
from decimal import Decimal
from datetime import date
from django.http import HttpResponse, JsonResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounting.models import Voucher
from apps.accounts.permissions import IsCompanyMember
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.documents.capabilities import get_document_capabilities, can_edi
from apps.documents.models import DocumentSnapshot, DocumentShare
from apps.documents.services import (
    DocumentSnapshotService,
    DocumentPDFService,
    DocumentShareService,
    InvoiceEDIService,
)

logger = logging.getLogger(__name__)


def _get_active_company(request):
    cid = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
    if cid:
        return Company.objects.filter(id=cid, users__user=request.user).first()
    return Company.objects.filter(users__user=request.user).first()


class VoucherSnapshotAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, voucher_id):
        company = _get_active_company(request)
        voucher = Voucher.objects.filter(id=voucher_id, company=company).defer('attachment_data', 'attachment_mime').first()
        if not voucher:
            return Response({'error': 'Voucher not found'}, status=status.HTTP_404_NOT_FOUND)

        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(voucher, user=request.user)
        caps = get_document_capabilities(snapshot.document_type)

        return Response({
            'snapshot_id': str(snapshot.id),
            'document_type': snapshot.document_type,
            'document_number': snapshot.document_number,
            'document_date': snapshot.document_date,
            'total_amount': snapshot.total_amount,
            'capabilities': {
                'pdf': caps.pdf,
                'preview': caps.preview,
                'share': caps.share,
                'email': caps.email,
                'whatsapp': caps.whatsapp,
                'edi': caps.edi,
            },
            'dto': snapshot.snapshot_json,
        })


class VoucherPDFStreamAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, voucher_id):
        company = _get_active_company(request)
        voucher = Voucher.objects.filter(id=voucher_id, company=company).defer('attachment_data', 'attachment_mime').first()
        if not voucher:
            return Response({'error': 'Voucher not found'}, status=status.HTTP_404_NOT_FOUND)

        copy_type = request.query_params.get('copy', 'ORIGINAL').upper()
        bypass_cache = request.query_params.get('fresh') == '1' or request.query_params.get('download') == '1'
        pdf_bytes = DocumentPDFService.generate_pdf_for_voucher(voucher, bypass_cache=bypass_cache, copy_type=copy_type)

        disposition = 'attachment' if request.query_params.get('download') == '1' else 'inline'
        
        suffix = ''
        if copy_type == 'TRANSPORTER':
            suffix = '_Transporter_Copy'
        elif copy_type in ['SUPPLIER', 'SUPPLIER_LOCAL']:
            suffix = '_Supplier_Copy'
        elif copy_type in ['BUNDLE_LOCAL', 'BUNDLE_2']:
            suffix = '_Local_2Copies'
        elif copy_type in ['BUNDLE_TRANSPORT', 'BUNDLE_3', 'ALL']:
            suffix = '_Triplicate_3Copies'

        filename = f"{voucher.voucher_number.replace('/', '_')}{suffix}.pdf"

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        response['Content-Length'] = len(pdf_bytes)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        return response


class VoucherShareAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def post(self, request, voucher_id):
        company = _get_active_company(request)
        voucher = Voucher.objects.filter(id=voucher_id, company=company).defer('attachment_data', 'attachment_mime').first()
        if not voucher:
            return Response({'error': 'Voucher not found'}, status=status.HTTP_404_NOT_FOUND)

        expires_in_days = int(request.data.get('expires_in_days', 30))
        # Always force refresh snapshot on share creation so share URL and WhatsApp message contain latest data
        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(voucher, user=request.user, force_refresh=True)

        try:
            raw_token, share = DocumentShareService.create_share(
                snapshot, user=request.user, expires_in_days=expires_in_days
            )
            share_url = DocumentShareService.build_share_url(raw_token, share.share_type)
            whatsapp_msg = DocumentShareService.generate_whatsapp_message(snapshot, raw_token)

            return Response({
                'success': True,
                'share_id': str(share.id),
                'share_type': share.share_type,
                'raw_token': raw_token,
                'share_url': share_url,
                'whatsapp_message': whatsapp_msg,
                'expires_at': share.expires_at,
            })
        except PermissionDenied as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)


class StatementShareAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def post(self, request, ledger_id):
        company = _get_active_company(request)
        ledger = Ledger.objects.filter(id=ledger_id, company=company).first()
        if not ledger:
            return Response({'error': 'Ledger account not found'}, status=status.HTTP_404_NOT_FOUND)

        from_date_str = request.data.get('from_date') or request.query_params.get('from_date')
        to_date_str = request.data.get('to_date') or request.query_params.get('to_date')

        d_from = date.fromisoformat(from_date_str) if from_date_str else None
        d_to = date.fromisoformat(to_date_str) if to_date_str else None

        snapshot = DocumentSnapshotService.create_statement_snapshot(
            company, ledger, from_date=d_from, to_date=d_to, user=request.user
        )

        raw_token, share = DocumentShareService.create_share(
            snapshot, user=request.user, expires_in_days=int(request.data.get('expires_in_days', 30))
        )
        share_url = DocumentShareService.build_share_url(raw_token, share.share_type)
        whatsapp_msg = DocumentShareService.generate_whatsapp_message(snapshot, raw_token)

        return Response({
            'success': True,
            'share_id': str(share.id),
            'share_type': share.share_type,
            'raw_token': raw_token,
            'share_url': share_url,
            'whatsapp_message': whatsapp_msg,
            'expires_at': share.expires_at,
        })


class PublicShareResolveAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            share = DocumentShareService.resolve_share(token, request=request, record_event='VIEWED')
        except PermissionDenied as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        snapshot = share.document_snapshot
        if snapshot.source_type == 'Voucher':
            try:
                voucher = Voucher.objects.filter(id=snapshot.source_id, company=snapshot.company).first()
                if voucher:
                    existing_snap = snapshot.snapshot_json or {}
                    existing_up = existing_snap.get('_voucher_updated_at')
                    v_up = str(voucher.updated_at) if hasattr(voucher, 'updated_at') and voucher.updated_at else None
                    is_stale = (
                        snapshot.template_version != '2.1' or
                        (v_up and existing_up != v_up) or
                        (snapshot.total_amount is not None and voucher.total_amount is not None and Decimal(str(snapshot.total_amount)) != Decimal(str(voucher.total_amount))) or
                        (snapshot.document_number != voucher.voucher_number)
                    )
                    if is_stale:
                        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(voucher, force_refresh=True)
                        share.document_snapshot = snapshot
                        share.save(update_fields=['document_snapshot'])
            except Exception as e:
                logger.warning(f"Could not refresh stale public share snapshot {snapshot.id}: {e}")

        caps = get_document_capabilities(snapshot.document_type)

        response = Response({
            'share_type': share.share_type,
            'document_type': snapshot.document_type,
            'document_number': snapshot.document_number,
            'document_date': snapshot.document_date,
            'total_amount': snapshot.total_amount,
            'expires_at': share.expires_at,
            'capabilities': {
                'pdf': caps.pdf,
                'preview': caps.preview,
                'share': caps.share,
                'email': caps.email,
                'whatsapp': caps.whatsapp,
                'edi': caps.edi,
            },
            'dto': snapshot.snapshot_json,
        })
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        return response


class PublicShareDownloadPDFAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            share = DocumentShareService.resolve_share(token, request=request, record_event='DOWNLOADED')
        except PermissionDenied as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        watermark = request.query_params.get('watermark') != '0'
        snapshot = share.document_snapshot
        if snapshot.source_type == 'Voucher':
            try:
                voucher = Voucher.objects.filter(id=snapshot.source_id, company=snapshot.company).first()
                if voucher:
                    existing_snap = snapshot.snapshot_json or {}
                    existing_up = existing_snap.get('_voucher_updated_at')
                    v_up = str(voucher.updated_at) if hasattr(voucher, 'updated_at') and voucher.updated_at else None
                    is_stale = (
                        snapshot.template_version != '2.1' or
                        (v_up and existing_up != v_up) or
                        (snapshot.total_amount is not None and voucher.total_amount is not None and Decimal(str(snapshot.total_amount)) != Decimal(str(voucher.total_amount))) or
                        (snapshot.document_number != voucher.voucher_number)
                    )
                    if is_stale:
                        snapshot = DocumentSnapshotService.get_or_create_voucher_snapshot(voucher, force_refresh=True)
                        share.document_snapshot = snapshot
                        share.save(update_fields=['document_snapshot'])
            except Exception as e:
                logger.warning(f"Could not refresh stale public download snapshot {snapshot.id}: {e}")

        pdf_bytes = DocumentPDFService.generate_pdf_from_snapshot(snapshot, watermark=watermark, bypass_cache=True)

        filename = f"{snapshot.document_number.replace('/', '_') or 'document'}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = len(pdf_bytes)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        return response


class ShareEDIImportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        try:
            share = DocumentShareService.resolve_share(token, request=request)
        except PermissionDenied as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        snapshot = share.document_snapshot
        if not can_edi(snapshot.document_type):
            return Response(
                {'error': f"EDI import is not permitted for document type: {snapshot.document_type}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        buyer_company = _get_active_company(request)
        if not buyer_company:
            return Response({'error': 'Active company not found for this user.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            edi_doc = InvoiceEDIService.get_or_create_edi_document(snapshot)
            result = InvoiceEDIService.import_invoice_to_buyer(edi_doc, buyer_company, request.user)
            return Response(result, status=status.HTTP_201_CREATED if not result.get('already_imported') else status.HTTP_200_OK)
        except (PermissionDenied, ValidationError) as e:
            msg = e.messages if hasattr(e, 'messages') else str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)


class ReportPDFExportAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, report_type):
        company = _get_active_company(request)
        if not company:
            return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

        rep_type = report_type.upper().replace('-', '_')
        from_d = request.query_params.get('from_date')
        to_d = request.query_params.get('to_date')
        as_of = request.query_params.get('as_of_date')

        d_from = date.fromisoformat(from_d) if from_d else None
        d_to = date.fromisoformat(to_d) if to_d else None
        d_as_of = date.fromisoformat(as_of) if as_of else None

        try:
            pdf_bytes = DocumentPDFService.generate_pdf_for_report(
                rep_type, company, from_date=d_from, to_date=d_to, as_of_date=d_as_of
            )
            filename = f"{company.name[:10]}_{rep_type}_{date.today()}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            response['Content-Length'] = len(pdf_bytes)
            return response
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LedgerStatementPDFExportAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, ledger_id):
        company = _get_active_company(request)
        ledger = Ledger.objects.filter(id=ledger_id, company=company).first()
        if not ledger:
            return Response({'error': 'Ledger not found'}, status=status.HTTP_404_NOT_FOUND)

        from_d = request.query_params.get('from_date')
        to_d = request.query_params.get('to_date')
        d_from = date.fromisoformat(from_d) if from_d else None
        d_to = date.fromisoformat(to_d) if to_d else None

        pdf_bytes = DocumentPDFService.generate_pdf_for_statement(company, ledger, from_date=d_from, to_date=d_to)
        filename = f"{ledger.name.replace(' ', '_')}_Statement.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = len(pdf_bytes)
        return response


class ProformaShareAPIView(APIView):
    """
    Generates a public, tokenized share link for a ProformaInvoice.
    The resulting share URL is accessible without authentication via
    PublicShareResolveAPIView + PublicShareDownloadPDFAPIView.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, proforma_id):
        from apps.accounting.models_proforma import ProformaInvoice

        proforma = ProformaInvoice.objects.filter(
            id=proforma_id, company__users__user=request.user
        ).select_related('company', 'party_ledger').prefetch_related('items').first()

        if not proforma:
            return Response({'error': 'Proforma invoice not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

        expires_in_days = int(request.data.get('expires_in_days', 30))

        snapshot = DocumentSnapshotService.get_or_create_proforma_snapshot(proforma, user=request.user)

        try:
            raw_token, share = DocumentShareService.create_share(
                snapshot, user=request.user, expires_in_days=expires_in_days
            )
            share_url = DocumentShareService.build_share_url(raw_token, share.share_type)

            return Response({
                'success': True,
                'share_id': str(share.id),
                'share_type': share.share_type,
                'raw_token': raw_token,
                'share_url': share_url,
                'expires_at': share.expires_at,
            })
        except PermissionDenied as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)


class ProformaPDFStreamAPIView(APIView):
    """
    Renders and streams deterministic, vector PDF for ProformaInvoice.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, proforma_id):
        from apps.accounting.models_proforma import ProformaInvoice

        proforma = ProformaInvoice.objects.filter(
            id=proforma_id, company__users__user=request.user
        ).select_related('company', 'party_ledger').prefetch_related('items').first()

        if not proforma:
            return Response({'error': 'Proforma invoice not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)

        bypass_cache = request.query_params.get('fresh') == '1'
        watermark = request.query_params.get('watermark') != '0'
        show_logo = request.query_params.get('logo') != '0'

        snapshot = DocumentSnapshotService.get_or_create_proforma_snapshot(
            proforma, user=request.user, force_refresh=bypass_cache
        )
        pdf_bytes = DocumentPDFService.generate_pdf_from_snapshot(
            snapshot, bypass_cache=bypass_cache, watermark=watermark, show_logo=show_logo
        )

        disposition = 'attachment' if request.query_params.get('download') == '1' else 'inline'
        filename = f"{proforma.proforma_number.replace('/', '_')}.pdf"

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        response['Content-Length'] = len(pdf_bytes)
        return response



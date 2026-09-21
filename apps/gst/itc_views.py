import json
import logging
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.models import GSTR2BImport, GSTR2BRecord
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
from apps.gst.services.itc_notification_service import ITCNotificationService

logger = logging.getLogger(__name__)


def get_requested_company(request) -> Company:
    """Helper to extract active company from request headers or query params."""
    company_id = (
        request.headers.get('X-Company-ID')
        or request.headers.get('company-id')
        or request.query_params.get('company_id')
        or request.data.get('company_id')
    )
    if not company_id:
        # Fall back to user's first accessible company
        company = request.user.companies.first()
        if not company:
            raise ValueError("No company found for this user.")
        return company
    return Company.objects.get(id=company_id)


class GSTR2BUploadView(APIView):
    """
    Ingests official GSTR-2B JSON or Excel file downloaded from the GST portal,
    and runs the 4-way reconciliation delta engine against purchase vouchers.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, *args, **kwargs):
        try:
            company = get_requested_company(request)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        file_obj = request.FILES.get('file')
        return_period = request.data.get('return_period', '').strip()

        # Handle raw JSON body upload as well
        if not file_obj and 'json_data' in request.data:
            json_data = request.data['json_data']
            try:
                import_batch = ITCReconciliationService.ingest_gstr2b_json(
                    company=company,
                    json_data=json_data,
                    user=request.user,
                    file_name='api_upload.json',
                    return_period=return_period
                )
                stats = ITCReconciliationService.get_summary_stats(company, return_period=import_batch.return_period)
                return Response({
                    'message': 'GSTR-2B JSON processed successfully.',
                    'import_id': str(import_batch.id),
                    'total_invoices': import_batch.total_invoices_count,
                    'total_itc': float(import_batch.total_itc_available),
                    'stats': stats
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.exception("Error processing GSTR-2B JSON payload")
                return Response({'error': f"Failed to parse GSTR-2B JSON: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if not file_obj:
            return Response({'error': 'No file uploaded. Please provide a GSTR-2B JSON or Excel file.'}, status=status.HTTP_400_BAD_REQUEST)

        file_name = file_obj.name.lower()

        try:
            if file_name.endswith('.json'):
                content = file_obj.read().decode('utf-8')
                json_data = json.loads(content)
                import_batch = ITCReconciliationService.ingest_gstr2b_json(
                    company=company,
                    json_data=json_data,
                    user=request.user,
                    file_name=file_obj.name,
                    return_period=return_period
                )
            elif file_name.endswith(('.xlsx', '.xls')):
                import_batch = ITCReconciliationService.ingest_gstr2b_excel(
                    company=company,
                    file_obj=file_obj,
                    user=request.user,
                    file_name=file_obj.name,
                    return_period=return_period
                )
            else:
                return Response({'error': 'Unsupported file format. Please upload .json or .xlsx file.'}, status=status.HTTP_400_BAD_REQUEST)

            stats = ITCReconciliationService.get_summary_stats(company, return_period=import_batch.return_period)

            return Response({
                'message': f"GSTR-2B {import_batch.return_period} imported and reconciled successfully.",
                'import_id': str(import_batch.id),
                'return_period': import_batch.return_period,
                'total_invoices': import_batch.total_invoices_count,
                'total_taxable': float(import_batch.total_taxable_amount),
                'total_itc': float(import_batch.total_itc_available),
                'stats': stats
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("Error processing GSTR-2B file upload")
            return Response({'error': f"Processing failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class ITCReconciliationListView(APIView):
    """
    Returns reconciled invoice items with filtering by status:
    ALL, MATCHED, MISMATCHED, MISSING_IN_2B, MISSING_IN_BOOKS.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            company = get_requested_company(request)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        filter_status = request.query_params.get('status', 'ALL').upper()
        return_period = request.query_params.get('return_period')
        search_query = request.query_params.get('search', '').strip().lower()

        results = []

        # 1. Purchase Vouchers (Books side)
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=['POSTED', 'VALIDATING']
        ).select_related('party_ledger').prefetch_related('items', 'gstr2b_matches')

        for v in vouchers:
            if filter_status not in ['ALL', 'MATCHED', 'MISMATCHED', 'MISSING_IN_2B']:
                if filter_status == 'MISSING_IN_BOOKS':
                    continue

            # Check status match
            if filter_status != 'ALL' and v.itc_match_status != filter_status:
                continue

            # Calculate book values
            b_taxable = sum(i.taxable_amount for i in v.items.all())
            b_cgst = sum(i.cgst_amount for i in v.items.all())
            b_sgst = sum(i.sgst_amount for i in v.items.all())
            b_igst = sum(i.igst_amount for i in v.items.all())
            b_total_tax = b_cgst + b_sgst + b_igst

            supplier_name = v.party_ledger.name if v.party_ledger else (v.buyer_name or 'Unknown')
            supplier_gstin = (v.party_ledger.gstin if v.party_ledger and v.party_ledger.gstin else (v.buyer_gstin or '')).upper()
            inv_no = v.external_invoice_number or v.reference_number or v.voucher_number

            # Search filter
            if search_query:
                q = search_query
                if q not in supplier_name.lower() and q not in supplier_gstin.lower() and q not in inv_no.lower():
                    continue

            # Matched 2B Record details if any
            matched_rec = v.gstr2b_matches.first()
            g2b_data = None
            if matched_rec:
                g2b_data = {
                    'invoice_number': matched_rec.invoice_number,
                    'invoice_date': matched_rec.invoice_date.isoformat(),
                    'taxable_value': float(matched_rec.taxable_value),
                    'total_tax': float(matched_rec.cgst_amount + matched_rec.sgst_amount + matched_rec.igst_amount),
                    'cgst': float(matched_rec.cgst_amount),
                    'sgst': float(matched_rec.sgst_amount),
                    'igst': float(matched_rec.igst_amount),
                    'mismatch_details': matched_rec.mismatch_details
                }

            results.append({
                'source': 'BOOKS',
                'voucher_id': str(v.id),
                'voucher_number': v.voucher_number,
                'invoice_number': inv_no,
                'invoice_date': v.voucher_date.isoformat() if v.voucher_date else '',
                'supplier_name': supplier_name,
                'supplier_gstin': supplier_gstin,
                'books_taxable': float(b_taxable),
                'books_tax': float(b_total_tax),
                'books_total': float(v.total_amount),
                'itc_match_status': v.itc_match_status,
                'itc_held_amount': float(v.itc_held_amount),
                'itc_notes': v.itc_notes,
                'gstr2b_record': g2b_data
            })

        # 2. GSTR-2B Records missing in books (Supplier filed, but buyer hasn't booked)
        if filter_status in ['ALL', 'MISSING_IN_BOOKS']:
            rec_qs = GSTR2BRecord.objects.filter(
                company=company,
                match_status='MISSING_IN_BOOKS'
            )
            if return_period:
                rec_qs = rec_qs.filter(import_batch__return_period=return_period)

            for rec in rec_qs:
                if search_query:
                    q = search_query
                    if q not in rec.supplier_name.lower() and q not in rec.supplier_gstin.lower() and q not in rec.invoice_number.lower():
                        continue

                rec_total_tax = rec.cgst_amount + rec.sgst_amount + rec.igst_amount
                results.append({
                    'source': 'GSTR2B',
                    'voucher_id': None,
                    'record_id': str(rec.id),
                    'invoice_number': rec.invoice_number,
                    'invoice_date': rec.invoice_date.isoformat() if rec.invoice_date else '',
                    'supplier_name': rec.supplier_name or 'Unmapped Vendor',
                    'supplier_gstin': rec.supplier_gstin,
                    'books_taxable': 0.0,
                    'books_tax': 0.0,
                    'books_total': 0.0,
                    'itc_match_status': 'MISSING_IN_BOOKS',
                    'itc_held_amount': 0.0,
                    'itc_notes': 'Reflecting in GSTR-2B but missing in your Purchase Register. You may be missing out on this ITC!',
                    'gstr2b_record': {
                        'invoice_number': rec.invoice_number,
                        'invoice_date': rec.invoice_date.isoformat(),
                        'taxable_value': float(rec.taxable_value),
                        'total_tax': float(rec_total_tax),
                        'cgst': float(rec.cgst_amount),
                        'sgst': float(rec.sgst_amount),
                        'igst': float(rec.igst_amount),
                        'mismatch_details': {}
                    }
                })

        return Response({
            'count': len(results),
            'results': results
        })


class ITCSmartPaymentHoldView(APIView):
    """
    Enables/updates the Smart GST Payment Hold on a specific purchase voucher.
    MSMEs use this to pay base amount and withhold the GST portion until supplier files GSTR-1.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        voucher_id = request.data.get('voucher_id')
        held_amount = request.data.get('held_amount')
        notes = request.data.get('notes', '')

        if not voucher_id:
            return Response({'error': 'voucher_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            company = get_requested_company(request)
            voucher = Voucher.objects.get(id=voucher_id, company=company)
        except Voucher.DoesNotExist:
            return Response({'error': 'Voucher not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if held_amount is not None:
            voucher.itc_held_amount = Decimal(str(held_amount))
        else:
            # Auto-calculate GST tax amount to hold
            tax_amt = sum((i.cgst_amount + i.sgst_amount + i.igst_amount) for i in voucher.items.all())
            voucher.itc_held_amount = tax_amt

        if notes:
            voucher.itc_notes = notes

        voucher.save(update_fields=['itc_held_amount', 'itc_notes', 'updated_at'])

        return Response({
            'message': f"GST Payment Hold of ₹{voucher.itc_held_amount:,.2f} applied to {voucher.voucher_number}.",
            'voucher_id': str(voucher.id),
            'itc_held_amount': float(voucher.itc_held_amount),
            'itc_notes': voucher.itc_notes
        })


class ITCVendorNoticeView(APIView):
    """
    Generates the WhatsApp Notice content and 1-click wa.me URL for chasing a defaulting vendor.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, voucher_id, *args, **kwargs):
        try:
            company = get_requested_company(request)
            voucher = Voucher.objects.select_related('party_ledger').prefetch_related('items').get(id=voucher_id, company=company)
        except Voucher.DoesNotExist:
            return Response({'error': 'Voucher not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        notice_data = ITCNotificationService.generate_whatsapp_filing_notice(voucher, company)
        return Response(notice_data)


class ITCSummaryView(APIView):
    """
    Provides aggregated risk stats: ITC at risk, Safe ITC, Held amounts, Section 16(4) counts.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            company = get_requested_company(request)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        period = request.query_params.get('return_period')
        stats = ITCReconciliationService.get_summary_stats(company, return_period=period)
        radar = ITCReconciliationService.get_sec16_4_expiry_radar(company)

        return Response({
            'summary': stats,
            'expiry_radar': radar
        })


class ITCRunReconciliationView(APIView):
    """
    Manually re-triggers reconciliation across existing GSTR-2B data and purchase vouchers.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            company = get_requested_company(request)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        period = request.data.get('return_period')
        stats = ITCReconciliationService.reconcile_period(company, return_period=period)
        return Response({
            'message': 'Reconciliation refreshed successfully.',
            'stats': stats
        })

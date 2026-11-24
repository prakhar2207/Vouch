import json
import logging
from decimal import Decimal
from datetime import date
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from rest_framework.exceptions import PermissionDenied, NotFound

from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.accounts.permissions import get_authorized_company, user_has_company_roles, CanViewGST, CanReconcileGST
from apps.gst.models import GSTR2BImport, GSTR2BRecord, GSTRegistration
from apps.gst.services.period_service import GSTPeriodService
import io
from apps.accounting.services.upload_security import (
    MAX_IMPORT_FILE_SIZE,
    UploadValidationError,
    read_validated_upload_bytes,
)
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
from apps.gst.services.itc_notification_service import ITCNotificationService

logger = logging.getLogger(__name__)


class GSTR2BUploadView(APIView):
    """
    Ingests official GSTR-2B JSON or Excel file downloaded from the GST portal,
    and runs the 4-way reconciliation delta engine against purchase vouchers.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE']):
            return Response({'error': 'Permission denied: Insufficient role to upload GSTR-2B.'}, status=status.HTTP_403_FORBIDDEN)

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
            except (ValueError, KeyError, TypeError):
                logger.exception("Error processing GSTR-2B JSON payload")
                return Response({'error': "Invalid GSTR-2B JSON structure."}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                logger.exception("Unexpected error processing GSTR-2B JSON payload")
                return Response({'error': "Failed to process GSTR-2B JSON payload."}, status=status.HTTP_400_BAD_REQUEST)

        if not file_obj:
            return Response({'error': 'No file uploaded. Please provide a GSTR-2B JSON or Excel file.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            raw_bytes = read_validated_upload_bytes(
                file_obj,
                allowed_extensions={'.json', '.xlsx', '.xls'},
                max_bytes=MAX_IMPORT_FILE_SIZE,
            )
            file_name = file_obj.name.lower()
            if file_name.endswith('.json'):
                content = raw_bytes.decode('utf-8')
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
                    file_obj=io.BytesIO(raw_bytes),
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

        except UploadValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response({'error': "Invalid or malformed GSTR-2B JSON file."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Error processing GSTR-2B file upload")
            return Response({'error': "Failed to process uploaded GSTR-2B file."}, status=status.HTTP_400_BAD_REQUEST)


class ITCReconciliationListView(APIView):
    """
    Returns reconciled invoice items with filtering by status:
    ALL, MATCHED, MISMATCHED, MISSING_IN_2B, MISSING_IN_BOOKS, REVIEW_REQUIRED, LATER_PERIOD_MATCH.
    Supports multi-GSTIN registration isolation and strict period validation.
    Delegates to ITCReconciliationService.get_scoped_reconciliation_data for 100% mathematical consistency.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        filter_status = request.query_params.get('status', 'ALL').upper()
        return_period = request.query_params.get('return_period')
        reg_id = request.query_params.get('registration_id')
        search_query = request.query_params.get('search', '').strip()

        # Strict return period validation
        if return_period and return_period != 'ALL':
            try:
                p_info = GSTPeriodService.parse_return_period(return_period)
                return_period = p_info.normalized_period
            except Exception:
                return Response({
                    'error': f"Invalid return period '{return_period}'. Format must be MMYYYY (e.g. 102026).",
                    'error_code': 'INVALID_RETURN_PERIOD'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Strict registration resolution and tenant isolation
        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
            if not registration:
                return Response({
                    'error': f"GST Registration '{reg_id}' was not found for this company.",
                    'error_code': 'INVALID_REGISTRATION'
                }, status=status.HTTP_400_BAD_REQUEST)
            if registration.status != 'ACTIVE':
                return Response({
                    'error': f"GST Registration '{registration.gstin}' is inactive.",
                    'error_code': 'INVALID_REGISTRATION'
                }, status=status.HTTP_400_BAD_REQUEST)

        scoped = ITCReconciliationService.get_scoped_reconciliation_data(
            company=company,
            return_period=return_period,
            registration=registration,
            status_filter=filter_status,
            search_query=search_query
        )

        return Response({
            'count': scoped['count'],
            'results': scoped['results']
        })


class ITCSmartPaymentHoldView(APIView):
    """
    Enables/updates the Smart GST Payment Hold on a specific purchase voucher.
    MSMEs use this to pay base amount and withhold the GST portion until supplier files GSTR-1.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, *args, **kwargs):
        voucher_id = request.data.get('voucher_id')
        held_amount = request.data.get('held_amount')
        notes = request.data.get('notes', '')

        if not voucher_id:
            return Response({'error': 'voucher_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        company = get_authorized_company(request)

        try:
            voucher = Voucher.objects.defer('attachment_data', 'attachment_mime').get(id=voucher_id, company=company)
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
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, voucher_id, *args, **kwargs):
        company = get_authorized_company(request)
        try:
            voucher = Voucher.objects.select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime').get(id=voucher_id, company=company)
        except Voucher.DoesNotExist:
            return Response({'error': 'Voucher not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        notice_data = ITCNotificationService.generate_whatsapp_filing_notice(voucher, company)
        return Response(notice_data)


class ITCSummaryView(APIView):
    """
    Provides aggregated risk stats: ITC at risk, Safe ITC, Held amounts, Section 16(4) counts.
    Supports multi-GSTIN registration isolation and strict return period validation.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        period = request.query_params.get('return_period')
        reg_id = request.query_params.get('registration_id')

        # Strict return period validation
        if period and period != 'ALL':
            try:
                p_info = GSTPeriodService.parse_return_period(period)
                period = p_info.normalized_period
            except Exception:
                return Response({
                    'error': f"Invalid return period '{period}'. Format must be MMYYYY (e.g. 102026).",
                    'error_code': 'INVALID_RETURN_PERIOD'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Strict registration resolution
        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
            if not registration:
                return Response({
                    'error': f"GST Registration '{reg_id}' was not found for this company.",
                    'error_code': 'INVALID_REGISTRATION'
                }, status=status.HTTP_400_BAD_REQUEST)
            if registration.status != 'ACTIVE':
                return Response({
                    'error': f"GST Registration '{registration.gstin}' is inactive.",
                    'error_code': 'INVALID_REGISTRATION'
                }, status=status.HTTP_400_BAD_REQUEST)

        stats = ITCReconciliationService.get_summary_stats(company, return_period=period, registration=registration)
        radar = ITCReconciliationService.get_sec16_4_expiry_radar(company, registration=registration)

        return Response({
            'summary': stats,
            'expiry_radar': radar
        })


class ITCAvailablePeriodsView(APIView):
    """
    GET /api/v1/gst/itc/periods/
    Returns all available return periods for the company dynamically:
    - Ingested GSTR-2B statement periods
    - Purchase voucher periods in books
    - Standard monthly compliance periods for recent financial years (e.g. FY 2024-25, 2025-26, 2026-27)
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, *args, **kwargs):
        company = get_authorized_company(request)
        reg_id = request.query_params.get('registration_id')

        registration = None
        if reg_id:
            try:
                registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
            except (ValueError, ValidationError):
                return Response({
                    "success": False,
                    "error": f"Invalid registration ID format: '{reg_id}'.",
                    "error_code": "INVALID_REGISTRATION"
                }, status=status.HTTP_400_BAD_REQUEST)

            if not registration:
                return Response({
                    "success": False,
                    "error": f"GST registration '{reg_id}' was not found for this company.",
                    "error_code": "INVALID_REGISTRATION"
                }, status=status.HTTP_400_BAD_REQUEST)

            if registration.status != 'ACTIVE':
                return Response({
                    "success": False,
                    "error": f"GST registration '{registration.gstin}' is inactive.",
                    "error_code": "INACTIVE_REGISTRATION"
                }, status=status.HTTP_400_BAD_REQUEST)

        # Ingested periods from 2B
        batch_qs = GSTR2BImport.objects.filter(company=company, status='PROCESSED')
        if registration:
            batch_qs = batch_qs.filter(gst_registration=registration)
        ingested_periods = set(batch_qs.values_list('return_period', flat=True))

        # Periods from purchase register vouchers in books
        voucher_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES,
            voucher_date__isnull=False
        )
        if registration and registration.gstin:
            voucher_qs = voucher_qs.filter(buyer_gstin=registration.gstin)

        book_periods = set()
        for v_date in voucher_qs.values_list('voucher_date', flat=True).distinct():
            if v_date:
                book_periods.add(f"{str(v_date.month).zfill(2)}{v_date.year}")

        # Calendar generation for 3 financial years: FY 24-25, FY 25-26, FY 26-27
        today = timezone.now().date()
        base_year = today.year if today.month >= 4 else today.year - 1
        calendar_periods = []
        for fy_start_y in [base_year - 2, base_year - 1, base_year]:
            fy_label = f"{fy_start_y}-{str(fy_start_y + 1)[-2:]}"
            # Apr to Dec of fy_start_y
            for m in range(4, 13):
                p_code = f"{str(m).zfill(2)}{fy_start_y}"
                calendar_periods.append((p_code, fy_label))
            # Jan to Mar of fy_start_y + 1
            for m in range(1, 4):
                p_code = f"{str(m).zfill(2)}{fy_start_y + 1}"
                calendar_periods.append((p_code, fy_label))

        seen = set()
        period_list = []
        # Sort descending so newest periods appear first
        for p_code, fy in reversed(calendar_periods):
            if p_code not in seen:
                seen.add(p_code)
                try:
                    p_info = GSTPeriodService.parse_return_period(p_code)
                    period_list.append({
                        'period': p_info.normalized_period,
                        'label': p_info.period_label,
                        'financial_year': fy,
                        'has_ingested_data': p_info.normalized_period in ingested_periods,
                        'has_book_data': p_info.normalized_period in book_periods,
                    })
                except Exception:
                    continue

        return Response({
            'count': len(period_list),
            'periods': period_list
        })


class ITCRunReconciliationView(APIView):
    """
    Manually re-triggers reconciliation across existing GSTR-2B data and purchase vouchers.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE']):
            return Response({'error': 'Permission denied: Insufficient role to run reconciliation.'}, status=status.HTTP_403_FORBIDDEN)

        period = request.data.get('return_period')
        stats = ITCReconciliationService.reconcile_period(company, return_period=period)
        return Response({
            'message': 'Reconciliation refreshed successfully.',
            'stats': stats
        })


class ITCVoucherAttributionAPIView(APIView):
    """
    POST /api/v1/gst/itc/attribute-voucher/
    Explicit GSTIN Attribution Workflow for UNMAPPED_GSTIN purchase vouchers (DEF-04).
    Safely assigns vouchers lacking a buyer_gstin to a verified active GSTRegistration,
    recording an immutable audit trail of who performed the attribution and when.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER', 'CA', 'ACCOUNTANT']):
            return Response({'error': 'Permission denied: Insufficient role to attribute vouchers to GSTIN.'}, status=status.HTTP_403_FORBIDDEN)

        voucher_ids = request.data.get('voucher_ids') or []
        if isinstance(voucher_ids, str):
            voucher_ids = [voucher_ids]
        reg_id = request.data.get('registration_id')

        if not voucher_ids or not isinstance(voucher_ids, (list, tuple)):
            return Response({'success': False, 'error': 'voucher_ids must be a non-empty list.'}, status=status.HTTP_400_BAD_REQUEST)
        if not reg_id:
            return Response({'success': False, 'error': 'registration_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            registration = GSTRegistration.objects.get(id=reg_id, company=company)
        except GSTRegistration.DoesNotExist:
            return Response({'success': False, 'error': f"GST Registration '{reg_id}' not found for this company."}, status=status.HTTP_404_NOT_FOUND)

        if registration.status != 'ACTIVE':
            return Response({'success': False, 'error': f"GST Registration '{registration.gstin}' is inactive."}, status=status.HTTP_400_BAD_REQUEST)

        vouchers = Voucher.objects.filter(
            id__in=voucher_ids,
            company=company,
            voucher_type__in=['PURCHASE', 'DEBIT_NOTE']
        )
        if not vouchers.exists():
            return Response({'success': False, 'error': 'No eligible purchase vouchers found for attribution.'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        source = request.data.get('attribution_source') or 'MANUAL_USER_ATTRIBUTION'
        updated_count = 0

        for v in vouchers:
            v.buyer_gstin = registration.gstin
            v.itc_gstin_attributed_by = request.user
            v.itc_gstin_attributed_at = now
            v.itc_gstin_attribution_source = source
            v.itc_match_status = 'UNCHECKED'
            v.save(update_fields=[
                'buyer_gstin', 'itc_gstin_attributed_by',
                'itc_gstin_attributed_at', 'itc_gstin_attribution_source',
                'itc_match_status'
            ])
            updated_count += 1

        # Re-trigger reconciliation for the newly mapped registration
        ITCReconciliationService.reconcile_period(company, registration=registration)

        return Response({
            'success': True,
            'message': f"Successfully attributed {updated_count} voucher(s) to GSTIN {registration.gstin}.",
            'attributed_count': updated_count,
            'attributed_gstin': registration.gstin
        }, status=status.HTTP_200_OK)

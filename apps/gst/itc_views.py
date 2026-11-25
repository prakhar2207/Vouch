import json
import logging
import uuid
import hashlib
from decimal import Decimal
from datetime import date
from django.db import transaction
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
from apps.gst.models import (
    GSTR2BImport, GSTR2BRecord, GSTRegistration,
    VoucherGSTINAttributionLog, VoucherAttributionOperation
)
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
    Explicit GSTIN Attribution Workflow for UNMAPPED_GSTIN purchase vouchers (P0 DEF-04, Round 2.4.1).
    Safely assigns genuinely unmapped vouchers to an active verified GSTRegistration.
    Enforces atomic batch processing, row-level locks, cross-tenant rejection, and append-only audit trail.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, *args, **kwargs):
        company = get_authorized_company(request)

        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER', 'CA', 'ACCOUNTANT']):
            return Response(
                {'success': False, 'error': 'Permission denied: Insufficient role to attribute vouchers to GSTIN.', 'error_code': 'FORBIDDEN'},
                status=status.HTTP_403_FORBIDDEN
            )

        raw_ids = request.data.get('voucher_ids') or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        reg_id = request.data.get('registration_id')
        is_correction = bool(request.data.get('is_correction', False))
        reason = (request.data.get('reason') or '').strip()
        source = request.data.get('attribution_source') or ('USER_CORRECTION' if is_correction else 'MANUAL_USER_ATTRIBUTION')

        if not raw_ids or not isinstance(raw_ids, (list, tuple)):
            return Response({'success': False, 'error': 'voucher_ids must be a non-empty list.', 'error_code': 'INVALID_VOUCHER_IDS'}, status=status.HTTP_400_BAD_REQUEST)
        if not reg_id:
            return Response({'success': False, 'error': 'registration_id is required.', 'error_code': 'REGISTRATION_REQUIRED'}, status=status.HTTP_400_BAD_REQUEST)
        if is_correction and len(reason) < 5:
            return Response({
                'success': False,
                'error': 'A justification reason of at least 5 non-whitespace characters is required when correcting an existing attribution.',
                'error_code': 'REASON_REQUIRED'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Deduplicate voucher IDs preserving submission order
        clean_voucher_ids = list(dict.fromkeys(raw_ids))

        try:
            registration = GSTRegistration.objects.get(id=reg_id, company=company)
        except (GSTRegistration.DoesNotExist, ValueError):
            return Response({'success': False, 'error': f"GST Registration '{reg_id}' not found for this company.", 'error_code': 'INVALID_REGISTRATION'}, status=status.HTTP_404_NOT_FOUND)

        if registration.status != 'ACTIVE':
            return Response({'success': False, 'error': f"GST Registration '{registration.gstin}' is inactive.", 'error_code': 'INACTIVE_REGISTRATION'}, status=status.HTTP_400_BAD_REQUEST)

        # Canonical request fingerprint for durable operation-level idempotency (P0 / Round 2.4.3)
        canonical_dict = {
            'actor_id': str(request.user.id),
            'attribution_source': str(source).strip().upper(),
            'company_id': str(company.id),
            'is_correction': bool(is_correction),
            'reason': str(reason).strip(),
            'registration_id': str(reg_id),
            'voucher_ids': sorted([str(vid) for vid in clean_voucher_ids]),
        }
        canonical_bytes = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
        request_fingerprint = hashlib.sha256(canonical_bytes).hexdigest()

        client_op_ref = (request.data.get('operation_ref') or '').strip()
        operation_ref = client_op_ref or f"ATTR_{uuid.uuid4().hex[:12].upper()}"

        # Fast-path idempotency replay check prior to entering atomic write transaction
        if client_op_ref:
            existing_op = VoucherAttributionOperation.objects.filter(
                company=company,
                operation_ref=client_op_ref
            ).first()
            if existing_op and existing_op.status != 'FAILED':
                if existing_op.request_fingerprint != request_fingerprint:
                    return Response({
                        'success': False,
                        'error': f"Operation reference conflict: Reused operation_ref '{client_op_ref}' with conflicting request parameters.",
                        'error_code': 'OPERATION_REFERENCE_CONFLICT'
                    }, status=status.HTTP_409_CONFLICT)
                if existing_op.status == 'COMPLETED':
                    return Response(existing_op.response_payload, status=status.HTTP_200_OK)

        now = timezone.now()

        with transaction.atomic():
            # Reserve or lock operation row for (company, operation_ref)
            op_record, created = VoucherAttributionOperation.objects.select_for_update().get_or_create(
                company=company,
                operation_ref=operation_ref,
                defaults={
                    'request_fingerprint': request_fingerprint,
                    'actor': request.user,
                    'target_registration': registration,
                    'is_correction': is_correction,
                    'status': 'PENDING'
                }
            )

            if not created:
                if op_record.status != 'FAILED':
                    # Re-validate under lock: check if fingerprints conflict
                    if op_record.request_fingerprint != request_fingerprint:
                        return Response({
                            'success': False,
                            'error': f"Operation reference conflict: Reused operation_ref '{operation_ref}' with conflicting request parameters.",
                            'error_code': 'OPERATION_REFERENCE_CONFLICT'
                        }, status=status.HTTP_409_CONFLICT)

                    # Replay completed response if previously finished
                    if op_record.status == 'COMPLETED':
                        return Response(op_record.response_payload, status=status.HTTP_200_OK)

                    if op_record.status == 'PENDING' and op_record.actor_id != request.user.id:
                        return Response({
                            'success': False,
                            'error': f"Operation '{operation_ref}' is currently in progress by another worker.",
                            'error_code': 'OPERATION_IN_PROGRESS'
                        }, status=status.HTTP_409_CONFLICT)

                # Reset to PENDING with current fingerprint and target
                op_record.status = 'PENDING'
                op_record.request_fingerprint = request_fingerprint
                op_record.target_registration = registration
                op_record.is_correction = is_correction
                op_record.save(update_fields=['status', 'request_fingerprint', 'target_registration', 'is_correction'])

            # Acquire row-level locks on candidate vouchers
            vouchers = list(
                Voucher.objects.select_for_update()
                .filter(id__in=clean_voucher_ids, company=company, voucher_type__in=['PURCHASE', 'DEBIT_NOTE'])
            )

            # Strict batch completeness check: every requested voucher ID must belong to this company
            found_ids = {str(v.id) for v in vouchers}
            missing_ids = [vid for vid in clean_voucher_ids if str(vid) not in found_ids]
            if missing_ids:
                op_record.status = 'FAILED'
                op_record.save(update_fields=['status'])
                return Response({
                    'success': False,
                    'error': f"One or more voucher IDs are invalid, belong to a different company, or are not purchase vouchers: {missing_ids[:3]}.",
                    'error_code': 'CROSS_TENANT_OR_INVALID_VOUCHERS'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Attribution integrity validation:
            # Under standard attribution, vouchers already assigned to another GSTIN or already attributed are rejected
            for v in vouchers:
                existing_gstin = (v.buyer_gstin or '').strip().upper()
                if not is_correction and (existing_gstin or v.itc_gstin_attributed_at):
                    op_record.status = 'FAILED'
                    op_record.save(update_fields=['status'])
                    return Response({
                        'success': False,
                        'error': f"Voucher '{v.voucher_number}' is already attributed to GSTIN '{existing_gstin or v.buyer_gstin}'. Use the correction workflow with an explicit reason to re-attribute.",
                        'error_code': 'ALREADY_ATTRIBUTED'
                    }, status=status.HTTP_400_BAD_REQUEST)

            attribution_logs = []
            for v in vouchers:
                prev_gstin = (v.buyer_gstin or '').strip().upper()
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
                attribution_logs.append(
                    VoucherGSTINAttributionLog(
                        company=company,
                        voucher=v,
                        gst_registration=registration,
                        previous_gstin=prev_gstin,
                        new_gstin=registration.gstin,
                        attributed_by=request.user,
                        attributed_at=now,
                        attribution_source=source,
                        reason=reason,
                        operation_ref=operation_ref,
                        is_correction=is_correction
                    )
                )

            VoucherGSTINAttributionLog.objects.bulk_create(attribution_logs)

            action_word = "corrected" if is_correction else "attributed"
            response_data = {
                'success': True,
                'message': f"Successfully {action_word} {len(vouchers)} voucher(s) to GSTIN {registration.gstin}.",
                'attributed_count': len(vouchers),
                'attributed_gstin': registration.gstin,
                'operation_ref': operation_ref,
                'is_correction': is_correction
            }

            op_record.status = 'COMPLETED'
            op_record.completed_at = now
            op_record.response_payload = response_data
            op_record.save(update_fields=['status', 'completed_at', 'response_payload'])

        # Trigger registration reconciliation after transaction commit
        ITCReconciliationService.reconcile_period(company, registration=registration)

        return Response(response_data, status=status.HTTP_200_OK)


class ITCVoucherAttributionCorrectionAPIView(APIView):
    """
    POST /api/v1/gst/itc/correct-attribution/
    Dedicated Attribution Correction Workflow (P0 DEF-04, Round 2.4.1).
    Allows authorized compliance officers to re-attribute previously assigned vouchers
    with mandatory justification audit logging.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, *args, **kwargs):
        request.data['is_correction'] = True
        return ITCVoucherAttributionAPIView().post(request, *args, **kwargs)

import json
from datetime import date
from django.http import HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.accounts.permissions import (
    user_has_company_roles,
    get_authorized_company,
    IsCompanyMember,
    IsCompanyAdmin,
    CanViewGST,
    CanPrepareGST,
    CanReconcileGST,
    CanFileGST,
    CanManageGSTCredentials,
    CanGenerateEWayBill,
    CanCancelEWayBill,
    CanGenerateEInvoice,
)
from apps.gst.models import CompanyGSTConfig, EWayBillRecord, GSTFilingRecord
from apps.gst.services.gstin_lookup_service import GSTINLookupService
from apps.gst.services.eway_bill_service import EWayBillService
from apps.gst.services.gstr_report_service import GSTRReportService
from apps.gst.services.gst_sandbox_service import GSTPortalService
from rest_framework.exceptions import NotFound, PermissionDenied

def get_company_or_404(user_or_request, company_id=None):
    if hasattr(user_or_request, 'user'):
        return get_authorized_company(user_or_request, company_id=company_id)
    from apps.companies.models import UserCompany
    try:
        comp = Company.objects.get(id=company_id, is_active=True)
        if not getattr(user_or_request, 'is_superuser', False) and not UserCompany.objects.filter(user=user_or_request, company=comp).exists():
            raise PermissionDenied("Access denied: You are not authorized to access this company's GST records.")
        return comp
    except Company.DoesNotExist:
        raise NotFound("Company not found or access denied.")

class GSTINLookupAPIView(APIView):
    """
    GET /api/v1/gst/lookup/<str:gstin>/
    Validates GSTIN and auto-fetches trade name, legal name, registered address,
    state, and taxpayer status for instant party creation.
    """
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, gstin):
        company_id = request.headers.get('X-Company-ID') or request.query_params.get('company_id')
        company = None
        if company_id:
            try:
                company = Company.objects.filter(id=company_id, users__user=request.user, is_active=True).first()
            except Exception:
                company = None

        force_refresh = request.query_params.get('refresh', '').lower() in ['true', '1']
        result = GSTINLookupService.lookup_gstin(gstin, company=company, force_refresh=force_refresh)

        if not result.get('success'):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class CompanyGSTConfigAPIView(APIView):
    """
    GET/POST /api/v1/gst/config/<uuid:company_id>/
    Manage company GST portal credentials, sandbox toggle, and provider choice.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), CanViewGST()]
        return [IsAuthenticated(), CanManageGSTCredentials()]

    def get(self, request, company_id):
        from django.utils import timezone
        company = get_company_or_404(request.user, company_id)
        config, _ = CompanyGSTConfig.objects.get_or_create(company=company)
        is_connected = bool(config.auth_token and (not config.token_expires_at or config.token_expires_at > timezone.now()))
        return Response({
            "success": True,
            "config": {
                "provider": config.provider,
                "is_sandbox": config.is_sandbox,
                "is_portal_connected": is_connected,
                "token_expires_at": config.token_expires_at.strftime('%Y-%m-%d %H:%M:%S') if config.token_expires_at else None,
                "portal_username": config.eway_username or "",
                "api_key": config.api_key[:4] + "****" if config.api_key else "",
                "eway_username": config.eway_username,
                "has_eway_password": bool(config.eway_password),
                "einvoice_username": config.einvoice_username,
                "has_einvoice_password": bool(config.einvoice_password),
                "updated_at": config.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER']):
            return Response({"success": False, "error": "Permission denied: Only Company Admins and Owners can manage GST credentials."}, status=status.HTTP_403_FORBIDDEN)

        config, _ = CompanyGSTConfig.objects.get_or_create(company=company)
        data = request.data

        if 'provider' in data:
            config.provider = data['provider']
        if 'is_sandbox' in data:
            config.is_sandbox = bool(data['is_sandbox'])
        if 'api_key' in data and data['api_key'] and not data['api_key'].endswith('****'):
            config.api_key = data['api_key'].strip()
        if 'api_secret' in data and data['api_secret']:
            config.api_secret = data['api_secret'].strip()
        if 'eway_username' in data:
            config.eway_username = data['eway_username'].strip()
        if 'eway_password' in data and data['eway_password']:
            config.eway_password = data['eway_password'].strip()
        if 'einvoice_username' in data:
            config.einvoice_username = data['einvoice_username'].strip()
        if 'einvoice_password' in data and data['einvoice_password']:
            config.einvoice_password = data['einvoice_password'].strip()

        config.save()
        return Response({"success": True, "message": "GST configuration updated successfully."})


class EWayBillGenerateAPIView(APIView):
    """
    POST /api/v1/gst/eway-bill/generate/
    Generates official Part-A and Part-B E-Way bill for a sales/purchase voucher.
    """
    permission_classes = [IsAuthenticated, CanGenerateEWayBill]

    def post(self, request):
        voucher_id = request.data.get('voucher_id')
        if not voucher_id:
            return Response({"success": False, "error": "voucher_id is required."}, status=400)

        voucher = Voucher.objects.filter(id=voucher_id, company__users__user=request.user).defer('attachment_data', 'attachment_mime').first()
        if not voucher:
            return Response({"success": False, "error": "Voucher not found or access denied."}, status=404)

        transport_details = {
            "transport_mode": request.data.get('transport_mode', '1'),
            "distance_km": request.data.get('distance_km', 100),
            "vehicle_number": (request.data.get('vehicle_number') or '').strip().upper(),
            "vehicle_type": request.data.get('vehicle_type', 'R'),
            "transporter_id": (request.data.get('transporter_id') or '').strip().upper(),
            "transporter_name": (request.data.get('transporter_name') or '').strip(),
            "transporter_doc_no": (request.data.get('transporter_doc_no') or '').strip(),
            "transporter_doc_date": request.data.get('transporter_doc_date', ''),
        }

        result = EWayBillService.generate_for_voucher(voucher, transport_details, request.user)
        if not result.get('success'):
            return Response(result, status=400)

        return Response(result, status=status.HTTP_201_CREATED)


class EWayBillUpdateVehicleAPIView(APIView):
    """
    POST /api/v1/gst/eway-bill/update-vehicle/
    Updates Part-B vehicle details for an active E-Way bill.
    """
    permission_classes = [IsAuthenticated, CanGenerateEWayBill]

    def post(self, request):
        ewb_number = request.data.get('ewb_number')
        new_vehicle_number = request.data.get('vehicle_number')
        if not ewb_number or not new_vehicle_number:
            return Response({"success": False, "error": "ewb_number and vehicle_number are required."}, status=400)

        ewb = EWayBillRecord.objects.filter(ewb_number=ewb_number, company__users__user=request.user).first()
        if not ewb:
            return Response({"success": False, "error": "E-Way bill not found."}, status=404)

        result = EWayBillService.update_vehicle(
            ewb_record=ewb,
            new_vehicle_number=new_vehicle_number,
            reason=request.data.get('reason', 'Breakdown'),
            remarks=request.data.get('remarks', '')
        )
        return Response(result)


class EWayBillCancelAPIView(APIView):
    """
    POST /api/v1/gst/eway-bill/cancel/
    Cancels an active E-Way bill.
    """
    permission_classes = [IsAuthenticated, CanCancelEWayBill]

    def post(self, request):
        ewb_number = request.data.get('ewb_number')
        if not ewb_number:
            return Response({"success": False, "error": "ewb_number is required."}, status=400)

        ewb = EWayBillRecord.objects.filter(ewb_number=ewb_number, company__users__user=request.user).first()
        if not ewb:
            return Response({"success": False, "error": "E-Way bill not found."}, status=404)

        result = EWayBillService.cancel_eway_bill(
            ewb_record=ewb,
            reason=request.data.get('reason', '1'),
            remarks=request.data.get('remarks', 'Cancelled by user')
        )
        return Response(result)


class EWayBillVoucherDetailAPIView(APIView):
    """
    GET /api/v1/gst/eway-bill/voucher/<uuid:voucher_id>/
    Fetches all E-Way bills generated for a given voucher.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, voucher_id):
        ewbs = EWayBillRecord.objects.filter(
            voucher_id=voucher_id,
            company__users__user=request.user
        ).order_by('-ewb_date')

        data = [{
            "id": str(e.id),
            "ewb_number": e.ewb_number,
            "ewb_date": e.ewb_date.strftime('%Y-%m-%d %H:%M:%S'),
            "valid_until": e.valid_until.strftime('%Y-%m-%d %H:%M:%S'),
            "status": e.status,
            "transport_mode": e.get_transport_mode_display(),
            "distance_km": e.distance_km,
            "vehicle_number": e.vehicle_number,
            "transporter_id": e.transporter_id,
            "transporter_name": e.transporter_name,
            "cancelled_at": e.cancelled_at.strftime('%Y-%m-%d %H:%M:%S') if e.cancelled_at else None,
        } for e in ewbs]

        return Response({"success": True, "eway_bills": data})


class GSTR1ExportAPIView(APIView):
    """
    GET /api/v1/gst/reports/gstr1/<uuid:company_id>/
    Exports GSTR-1 payload JSON compliant with the official GST Offline Tool.
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        start_date = request.query_params.get('start_date', date.today().replace(day=1).isoformat())
        end_date = request.query_params.get('end_date', date.today().isoformat())

        download = request.query_params.get('download', '').lower() in ['true', '1']
        payload = GSTRReportService.generate_gstr1(company, start_date, end_date)

        if download:
            response = HttpResponse(
                json.dumps(payload, indent=2),
                content_type='application/json'
            )
            filename = f"GSTR1_{company.gstin or 'URP'}_{payload.get('fp', 'RETURN')}.json"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        return Response({"success": True, "gstr1": payload})


class GSTR3BSummaryAPIView(APIView):
    """
    GET /api/v1/gst/reports/gstr3b/<uuid:company_id>/
    Computes Outward Tax Liability (Table 3.1) vs Eligible ITC (Table 4).
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        start_date = request.query_params.get('start_date', date.today().replace(day=1).isoformat())
        end_date = request.query_params.get('end_date', date.today().isoformat())

        data = GSTRReportService.generate_gstr3b_summary(company, start_date, end_date)
        return Response({"success": True, "data": data})


class GSTRPreFilingExceptionsAPIView(APIView):
    """
    GET /api/v1/gst/returns/exceptions/<uuid:company_id>/
    Pre-filing Health Check ("Triangulation"):
    Scans vouchers for the period and returns clean count vs exceptions needing correction.
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        start_date = request.query_params.get('start_date', date.today().replace(day=1).isoformat())
        end_date = request.query_params.get('end_date', date.today().isoformat())

        result = GSTRReportService.get_return_exceptions(company, start_date, end_date)
        return Response({"success": True, "data": result})


class GSTR9AnnualSummaryAPIView(APIView):
    """
    GET /api/v1/gst/reports/gstr9/<uuid:company_id>/
    Annual Return (GSTR-9) reconciliation summary across 4 quarters / 12 months.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        year_code = request.query_params.get('year_code', '2025-2026')

        result = GSTRReportService.generate_annual_gstr9_summary(company, year_code)
        return Response({"success": True, "data": result})


class GSTRMarkPeriodFiledAPIView(APIView):
    """
    GET/POST /api/v1/gst/returns/mark-filed/<uuid:company_id>/
    Durable recording and query of GST return filing state machine.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), CanViewGST()]
        return [IsAuthenticated(), CanFileGST()]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        filings = GSTFilingRecord.objects.filter(company=company).order_by('-submitted_at')[:24]
        return Response({
            "success": True,
            "filings": [{
                "id": str(f.id),
                "return_type": f.return_type,
                "return_period": f.return_period,
                "financial_year": f.financial_year,
                "status": f.status,
                "arn": f.arn,
                "provider_reference": f.provider_reference,
                "total_taxable_value": float(f.total_taxable_value),
                "total_tax_amount": float(f.total_tax_amount),
                "filing_mode": f.filing_mode,
                "submitted_at": f.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
                "submitted_by": f.submitted_by.email if f.submitted_by else None,
            } for f in filings]
        })

    def post(self, request, company_id):
        from decimal import Decimal
        from django.utils import timezone
        import hashlib

        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period') or request.data.get('return_period') or 'Current Period'
        return_type = request.data.get('return_type', 'GSTR1').upper()
        arn = request.data.get('arn', '').strip()
        filing_mode = request.data.get('filing_mode', 'MANUAL').upper()
        taxable_value = Decimal(str(request.data.get('total_taxable_value', '0.00')))
        tax_amount = Decimal(str(request.data.get('total_tax_amount', '0.00')))
        invoices_count = int(request.data.get('invoices_count', 0))

        # Check if caller wants to unmark / revert filing
        is_unmark = bool(request.data.get('unmark') or request.data.get('status') in ['PENDING', 'UNFILED', 'NOT_FILED', 'DRAFT'])
        candidate_periods = [period]
        if '-' in period and len(period) == 7:
            parts = period.split('-')
            candidate_periods.append(f"{parts[1]}{parts[0]}")
        elif len(period) == 6 and period.isdigit():
            candidate_periods.append(f"{period[2:]}-{period[:2]}")

        if is_unmark:
            GSTFilingRecord.objects.filter(
                company=company,
                return_type=return_type,
                return_period__in=candidate_periods
            ).update(status='DRAFT')
            return Response({
                "success": True,
                "message": f"GST return for period '{period}' marked as unfiled.",
                "status": "DRAFT",
                "return_period": period,
                "return_type": return_type,
            })

        # P0-08: Strictly eliminate pseudo-government ARNs!
        # If user provides genuine government ARN, persist it.
        # Otherwise, keep arn blank and use provider_reference for internal tracking.
        ts_str = timezone.now().strftime('%Y%m%d%H%M%S')
        h = hashlib.sha256(f"{company.id}:{period}:{ts_str}".encode()).hexdigest()[:8].upper()
        provider_ref = request.data.get('provider_reference') or f"VOUCH-INTERNAL-REF-{period.replace('-', '')}-{h}"
        payload_hash = hashlib.sha256(f"{company.id}:{return_type}:{period}:{taxable_value}:{tax_amount}".encode()).hexdigest()

        record, _ = GSTFilingRecord.objects.update_or_create(
            company=company,
            return_type=return_type,
            return_period=period,
            defaults={
                'status': 'FILED',
                'arn': arn,
                'provider_reference': provider_ref,
                'payload_hash': payload_hash,
                'filing_mode': filing_mode,
                'total_taxable_value': taxable_value,
                'total_tax_amount': tax_amount,
                'invoices_count': invoices_count,
                'submitted_by': request.user,
                'response_snapshot': request.data if isinstance(request.data, dict) else {},
            }
        )

        return Response({
            "success": True,
            "message": f"GST return for period '{period}' successfully recorded as FILED.",
            "filing_id": str(record.id),
            "arn": record.arn or None,
            "provider_reference": record.provider_reference,
            "return_type": record.return_type,
            "return_period": record.return_period,
            "status": record.status,
            "filing_mode": record.filing_mode,
            "submitted_at": record.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
        })


class GSTRDirectPortalOTPRequestAPIView(APIView):
    """
    POST /api/v1/gst/portal/request-otp/
    Requests taxpayer OTP from GST Portal / Sandbox for direct filing.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request):
        company_id = request.data.get('company_id')
        if not company_id:
            return Response({"success": False, "error": "company_id is required."}, status=400)
        company = get_company_or_404(request.user, company_id)
        gstin = request.data.get('gstin')
        username = request.data.get('username')

        result = GSTPortalService.request_portal_otp(company, gstin=gstin, username=username)
        return Response(result)


class GSTRDirectPortalVerifyOTPAPIView(APIView):
    """
    POST /api/v1/gst/portal/verify-otp/
    Verifies 6-digit OTP and generates an active GST Portal session token.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request):
        company_id = request.data.get('company_id')
        otp = request.data.get('otp')
        if not company_id or not otp:
            return Response({"success": False, "error": "company_id and otp are required."}, status=400)
        company = get_company_or_404(request.user, company_id)

        result = GSTPortalService.verify_portal_otp(
            company=company,
            otp=otp,
            txn_id=request.data.get('txn_id'),
            gstin=request.data.get('gstin'),
            username=request.data.get('username')
        )
        if not result.get('success'):
            return Response(result, status=400)
        return Response(result)


class GSTRDirectPortalUploadGSTR1APIView(APIView):
    """
    POST /api/v1/gst/portal/upload-gstr1/
    Directly uploads GSTR-1 returns to the GST Portal / Sandbox without manual JSON file download.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request):
        company_id = request.data.get('company_id')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        if not company_id or not start_date or not end_date:
            return Response({"success": False, "error": "company_id, start_date, and end_date are required."}, status=400)

        company = get_company_or_404(request.user, company_id)
        auth_token = request.data.get('auth_token')

        result = GSTPortalService.upload_gstr1_direct(
            company=company,
            start_date=start_date,
            end_date=end_date,
            auth_token=auth_token
        )
        return Response(result)


class GSTRDirectPortalStatusAPIView(APIView):
    """
    GET /api/v1/gst/portal/status/<uuid:company_id>/<str:ref_id>/
    Queries return processing status by Reference ID.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id, ref_id):
        company = get_company_or_404(request.user, company_id)
        result = GSTPortalService.get_portal_status(company, ref_id)
        return Response(result)




# ==============================================================================
# PHASE 2 & 3: MULTI-GSTIN, SANDBOX PROVIDER & RECONCILIATION WORKSPACES
# ==============================================================================

from apps.gst.models import GSTRegistration, GSTAuditLog, EInvoiceRecord
from apps.gst.serializers import (
    GSTRegistrationSerializer,
    GSTRegistrationWriteSerializer,
    EInvoiceRecordSerializer,
    EWayBillRecordSerializer,
    GSTR2BRecordSerializer,
    GSTAuditLogSerializer
)
from apps.gst.permissions import HasGSTPermission, CanManageGSTRegistration
from apps.accounts.permissions import user_has_company_roles
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gstin_service import GSTINService
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.reconciliation_service import GSTReconciliationService
from apps.gst.services.einvoice_service import EInvoiceService
from apps.gst.services.ewaybill_service import EWayBillService as EWayBillServiceV2


from apps.gst.services.registration_service import GSTRegistrationService
from apps.gst.exceptions import GSTINValidationError, DuplicateSubmissionError, GSTRegistrationAccessDenied


class GSTRegistrationListCreateAPIView(APIView):
    """
    GET /api/v1/gst/registrations/<uuid:company_id>/
    POST /api/v1/gst/registrations/<uuid:company_id>/
    Manages multi-state / multi-GSTIN registrations for a company.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasGSTPermission()]
        return [IsAuthenticated(), CanManageGSTRegistration()]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        registrations = GSTRegistrationService.list_registrations(company)
        serializer = GSTRegistrationSerializer(registrations, many=True)
        return Response({"success": True, "registrations": serializer.data})

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        gstin = request.data.get('gstin', '')
        state_code = request.data.get('state_code')
        legal_name = request.data.get('legal_name')
        trade_name = request.data.get('trade_name')
        address = request.data.get('address')
        pincode = request.data.get('pincode')
        taxpayer_type = request.data.get('taxpayer_type', 'REGULAR')
        is_primary = bool(request.data.get('is_primary', False))
        auto_verify = bool(request.data.get('auto_verify', True))

        try:
            reg = GSTRegistrationService.create_registration(
                company=company,
                gstin=gstin,
                state_code=state_code,
                legal_name=legal_name,
                trade_name=trade_name,
                address=address,
                pincode=pincode,
                taxpayer_type=taxpayer_type,
                is_primary=is_primary,
                auto_verify=auto_verify,
                user=request.user
            )
            return Response({
                "success": True,
                "message": f"GST registration for '{reg.gstin}' ({reg.state_name}) created successfully.",
                "registration": GSTRegistrationSerializer(reg).data
            }, status=201)
        except (GSTINValidationError, DuplicateSubmissionError) as e:
            return Response({"success": False, "error": str(e)}, status=400)
        except Exception as e:
            logger.exception(f"Error creating GST registration: {e}")
            return Response({"success": False, "error": f"Failed to create registration: {str(e)}"}, status=500)


class GSTRegistrationDetailAPIView(APIView):
    """
    GET/PUT/DELETE /api/v1/gst/registrations/<uuid:company_id>/<uuid:pk>/
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), HasGSTPermission()]
        return [IsAuthenticated(), CanManageGSTRegistration()]

    def get(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        try:
            reg = GSTRegistrationService.get_registration(company, pk)
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)

        return Response({"success": True, "registration": GSTRegistrationSerializer(reg).data})

    def put(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        try:
            updated_reg = GSTRegistrationService.update_registration(
                company=company,
                registration_id=pk,
                data=request.data,
                user=request.user
            )
            return Response({
                "success": True,
                "message": "GST registration updated successfully.",
                "registration": GSTRegistrationSerializer(updated_reg).data
            })
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def delete(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        hard_delete = request.query_params.get('hard_delete', 'false').lower() == 'true'
        try:
            reg = GSTRegistrationService.get_registration(company, pk)
            if hard_delete:
                # Only hard delete if zero vouchers reference it
                from apps.accounting.models import Voucher
                if Voucher.objects.filter(company=company).filter(buyer_gstin=reg.gstin).exists():
                    reg.status = 'INACTIVE'
                    reg.save(update_fields=['status'])
                    return Response({
                        "success": True,
                        "message": "Historical vouchers exist; registration marked as INACTIVE."
                    })
                reg.delete()
                return Response({"success": True, "message": "GST registration deleted successfully."})
            else:
                GSTRegistrationService.deactivate_registration(company, pk, user=request.user)
                return Response({"success": True, "message": "GST registration deactivated successfully."})
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)


class GSTRegistrationVerifyPreviewAPIView(APIView):
    """
    POST /api/v1/gst/registrations/<uuid:company_id>/verify-preview/
    Pre-validates a GSTIN with Luhn check and Sandbox search for user review before registration creation.
    """
    permission_classes = [IsAuthenticated, HasGSTPermission]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN', 'ACCOUNTANT', 'CA']):
            return Response({"success": False, "error": "Permission denied: Cannot perform GST pre-verification."}, status=403)
        gstin = request.data.get('gstin', '')
        result = GSTRegistrationService.verify_preview(company, gstin, user=request.user)
        status_code = 200 if result.get('success') else 400
        return Response(result, status=status_code)


class GSTRegistrationVerifyAPIView(APIView):
    """
    POST /api/v1/gst/registrations/<uuid:company_id>/<uuid:pk>/verify/
    Re-verifies an existing registration with Sandbox and updates verification status.
    """
    permission_classes = [IsAuthenticated, HasGSTPermission]

    def post(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN', 'ACCOUNTANT', 'CA']):
            return Response({"success": False, "error": "Permission denied: Cannot re-verify GST registrations."}, status=403)
        force_refresh = bool(request.data.get('force_refresh', True))
        try:
            res = GSTRegistrationService.verify_existing_registration(
                company=company,
                registration_id=pk,
                force_refresh=force_refresh,
                user=request.user
            )
            return Response(res, status=200 if res.get('success') else 400)
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)


class GSTRegistrationDeactivateAPIView(APIView):
    """
    POST /api/v1/gst/registrations/<uuid:company_id>/<uuid:pk>/deactivate/
    """
    permission_classes = [IsAuthenticated, CanManageGSTRegistration]

    def post(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        try:
            reg = GSTRegistrationService.deactivate_registration(company, pk, user=request.user)
            return Response({
                "success": True,
                "message": f"Registration '{reg.gstin}' is now INACTIVE.",
                "registration": GSTRegistrationSerializer(reg).data
            })
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)


class GSTRegistrationReactivateAPIView(APIView):
    """
    POST /api/v1/gst/registrations/<uuid:company_id>/<uuid:pk>/reactivate/
    """
    permission_classes = [IsAuthenticated, CanManageGSTRegistration]

    def post(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        try:
            reg = GSTRegistrationService.update_registration(
                company=company,
                registration_id=pk,
                data={'status': 'ACTIVE'},
                user=request.user
            )
            return Response({
                "success": True,
                "message": f"Registration '{reg.gstin}' reactivated.",
                "registration": GSTRegistrationSerializer(reg).data
            })
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)


class UnifiedGSTINVerifyAPIView(APIView):
    """
    POST /api/v1/gst/verify-gstin/
    Validates format locally and queries Sandbox GST API.
    Optionally compares with an existing party for pre-update diff preview.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        gstin = request.data.get('gstin', '')
        company_id = request.data.get('company_id')
        party_id = request.data.get('party_id')
        force_refresh = bool(request.data.get('force_refresh', False))

        company = None
        if company_id:
            try:
                company = get_company_or_404(request.user, company_id)
            except Exception:
                company = None

        result = GSTINService.verify_gstin(
            gstin=gstin,
            company=company,
            force_refresh=force_refresh,
            user=request.user
        )

        # If party_id provided, generate diff preview
        if result.get('success') and party_id and company:
            from apps.ledgers.models import Ledger
            party = Ledger.objects.filter(id=party_id, company=company).first()
            if party:
                diff_preview = GSTINService.preview_party_enrichment(party, result)
                result['party_enrichment_preview'] = diff_preview

        status_code = 200 if result.get('success') else 400
        return Response(result, status=status_code)


class PartyEnrichmentApplyAPIView(APIView):
    """
    POST /api/v1/gst/party/enrich/
    Applies user-selected verified fields to party ledger.
    INVARIANT: Never silently corrupts or overwrites party without explicit field selections.
    Strictly enforces role authorization and verified source data (no arbitrary browser payloads).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get('company_id')
        party_id = request.data.get('party_id')
        fields_to_update = request.data.get('fields_to_update', {})  # dict or list of fields

        if not company_id or not party_id or not fields_to_update:
            return Response({"success": False, "error": "company_id, party_id, and fields_to_update are required."}, status=400)

        company = get_company_or_404(request.user, company_id)
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN', 'ACCOUNTANT']):
            return Response({"success": False, "error": "Permission denied: Only OWNER, ADMIN, or ACCOUNTANT can enrich party ledgers."}, status=403)

        from apps.ledgers.models import Ledger
        try:
            party = Ledger.objects.get(id=party_id, company=company)
        except Ledger.DoesNotExist:
            return Response({"success": False, "error": "Party ledger not found."}, status=404)

        target_gstin = (
            request.data.get('gstin')
            or (fields_to_update.get('gstin') if isinstance(fields_to_update, dict) else '')
            or party.gstin
            or ''
        ).strip().upper()

        if not target_gstin:
            return Response({"success": False, "error": "No GSTIN associated with this party or request."}, status=400)

        # Resolve verified taxpayer data from authoritative cache or live check
        verify_res = GSTINService.verify_gstin(target_gstin, company=company, user=request.user)
        if not verify_res.get('success'):
            return Response({
                "success": False,
                "error": f"Cannot enrich party: GSTIN '{target_gstin}' verification failed ({verify_res.get('error')})."
            }, status=400)

        selected_keys = set(fields_to_update.keys()) if isinstance(fields_to_update, dict) else set(fields_to_update)

        apply_legal = bool('legal_name' in selected_keys or 'name' in selected_keys)
        apply_trade = bool('trade_name' in selected_keys and not apply_legal)
        apply_state = bool('state_code' in selected_keys)
        apply_addr = bool('address' in selected_keys)
        apply_gst = bool('gstin' in selected_keys)

        updated_party = GSTINService.apply_party_enrichment(
            ledger_id=party.id,
            verified_data=verify_res,
            apply_legal_name=apply_legal,
            apply_trade_name=apply_trade,
            apply_state=apply_state,
            apply_address=apply_addr,
            apply_gstin=apply_gst,
            user=request.user
        )

        return Response({
            "success": True,
            "message": f"Successfully enriched party '{updated_party.name}'.",
            "party_id": str(updated_party.id),
            "party_name": updated_party.name,
            "gstin": updated_party.gstin,
            "state_code": updated_party.state_code,
            "address": updated_party.address
        })


class GSTOverviewAPIView(APIView):
    """
    GET /api/v1/gst/overview/<uuid:company_id>/
    Aggregates filing status, registrations, recent e-invoices, e-way bills, and ITC metrics.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        client = SandboxGSTClient(company=company)

        registrations_count = GSTRegistration.objects.filter(company=company).count()
        recent_einvoices = EInvoiceRecord.objects.filter(company=company).order_by('-created_at')[:5]
        recent_ewaybills = EWayBillRecord.objects.filter(company=company).order_by('-created_at')[:5]
        recent_filings = GSTFilingRecord.objects.filter(company=company).order_by('-submitted_at')[:5]

        # Recent reconciliation metrics
        latest_import = GSTR2BImport.objects.filter(company=company).order_by('-created_at').first()
        matched_count = GSTR2BRecord.objects.filter(company=company, match_status='MATCHED').count()
        mismatched_count = GSTR2BRecord.objects.filter(company=company).exclude(match_status='MATCHED').count()

        return Response({
            "success": True,
            "company_name": company.name,
            "gateway_configured": client.is_configured(),
            "gateway_provider": "Sandbox by Quicko (api.sandbox.co.in)",
            "registrations_count": registrations_count,
            "itc_reconciliation": {
                "latest_period": latest_import.return_period if latest_import else None,
                "matched_records": matched_count,
                "mismatched_records": mismatched_count,
            },
            "recent_einvoices": EInvoiceRecordSerializer(recent_einvoices, many=True).data,
            "recent_ewaybills": EWayBillRecordSerializer(recent_ewaybills, many=True).data,
            "recent_filings": [
                {
                    "return_type": f.return_type,
                    "return_period": f.return_period,
                    "status": f.status,
                    "arn": f.arn,
                    "submitted_at": f.submitted_at.isoformat()
                } for f in recent_filings
            ]
        })


class GSTR1WorkspaceAPIView(APIView):
    """
    GET /api/v1/gst/returns/gstr1/<uuid:company_id>/
    Prepares GSTR-1 outward supply data and official JSON schema.
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period', '082026')
        reg_id = request.query_params.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        result = GSTReturnsService.prepare_gstr1(
            company=company,
            registration=registration,
            return_period=period
        )
        return Response({"success": True, "data": result})


class GSTR1SubmitAPIView(APIView):
    """
    POST /api/v1/gst/returns/gstr1/submit/<uuid:company_id>/
    Submits GSTR-1 to Sandbox / GST Portal after explicit user confirmation.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        reg_id = request.data.get('registration_id')
        confirmed = bool(request.data.get('confirmed', False))

        if not confirmed:
            return Response({
                "success": False,
                "error": "Explicit user confirmation is required to submit returns to the GST portal."
            }, status=400)

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        data = GSTReturnsService.prepare_gstr1(company, registration, period)
        official_json = data["official_gstr1_json"]

        client = SandboxGSTClient(company=company, registration=registration)
        session_token = registration.auth_token if registration else None

        if not client.is_configured():
            return Response({
                "success": False,
                "error": "Sandbox GST API is not configured. Supply API credentials."
            }, status=503)

        res = client.save_gstr1(payload=official_json, session_token=session_token, user=request.user)
        if not res.get("success"):
            return Response(res, status=400)

        # Record filing state
        filing_rec = GSTReturnsService.record_filing(
            company=company,
            registration=registration,
            return_type='GSTR1',
            return_period=period,
            arn=res.get("data", {}).get("ref_id", ""),
            status='SUBMITTED',
            payload=official_json,
            response=res.get("data"),
            user=request.user
        )

        return Response({
            "success": True,
            "message": f"GSTR-1 for period {period} submitted successfully.",
            "filing_id": str(filing_rec.id),
            "ref_id": filing_rec.arn,
            "status": filing_rec.status
        })


class GSTR3BWorkspaceAPIView(APIView):
    """
    GET /api/v1/gst/returns/gstr3b/<uuid:company_id>/
    Computes GSTR-3B monthly summary (Table 3.1 outward liabilities, Table 4 eligible ITC, Net Payable).
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period', '082026')
        reg_id = request.query_params.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        result = GSTReturnsService.prepare_gstr3b(company, registration, period)
        return Response({"success": True, "data": result})


class GSTR2BReconciliationAPIView(APIView):
    """
    GET /api/v1/gst/reconciliation/gstr2b/<uuid:company_id>/
    Returns 11-category reconciliation breakdown and individual record diffs.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period')
        status_filter = request.query_params.get('match_status')

        summary = GSTReconciliationService.reconcile_period(
            company=company,
            return_period=period
        )

        records_qs = GSTR2BRecord.objects.filter(company=company).order_by('-invoice_date')
        if period:
            records_qs = records_qs.filter(import_batch__return_period=period)
        if status_filter:
            records_qs = records_qs.filter(match_status=status_filter)

        page_records = records_qs[:100]
        serializer = GSTR2BRecordSerializer(page_records, many=True)

        return Response({
            "success": True,
            "summary": summary,
            "records": serializer.data
        })


class GSTR2BSyncFromSandboxAPIView(APIView):
    """
    POST /api/v1/gst/reconciliation/gstr2b/sync/<uuid:company_id>/
    Fetches GSTR-2B data directly from Sandbox and executes reconciliation.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        reg_id = request.data.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        res = GSTReconciliationService.fetch_and_ingest_from_sandbox(
            company=company,
            registration=registration,
            return_period=period,
            user=request.user
        )
        status_code = 200 if res.get("success") else 400
        return Response(res, status=status_code)


class GSTR2BReviewRecordAPIView(APIView):
    """
    POST /api/v1/gst/reconciliation/gstr2b/review/<uuid:record_id>/
    Allows user to mark discrepancy as reviewed/resolved with notes.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, record_id):
        try:
            record = GSTR2BRecord.objects.get(id=record_id)
        except GSTR2BRecord.DoesNotExist:
            return Response({"success": False, "error": "GSTR-2B record not found."}, status=404)

        # Tenant authorization
        company = get_company_or_404(request.user, record.company.id)

        notes = request.data.get('review_notes', '')
        is_reviewed = bool(request.data.get('is_reviewed', True))

        record.is_reviewed = is_reviewed
        record.reviewed_at = timezone.now() if is_reviewed else None
        record.reviewed_by = request.user if is_reviewed else None
        record.review_notes = notes
        record.save(update_fields=['is_reviewed', 'reviewed_at', 'reviewed_by', 'review_notes'])

        return Response({
            "success": True,
            "message": "Record review status updated successfully.",
            "record": GSTR2BRecordSerializer(record).data
        })


class EInvoiceGenerateAPIView(APIView):
    """
    POST /api/v1/gst/einvoice/generate/<uuid:voucher_id>/
    Generates IRN & Signed QR Code for an eligible sales voucher.
    """
    permission_classes = [IsAuthenticated, CanGenerateEInvoice]

    def post(self, request, voucher_id):
        try:
            voucher = Voucher.objects.get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({"success": False, "error": "Voucher not found."}, status=404)

        company = get_company_or_404(request.user, voucher.company.id)
        reg_id = request.data.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        try:
            res = EInvoiceService.generate_irn(voucher, registration=registration, user=request.user)
            return Response(res)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class EInvoiceCancelAPIView(APIView):
    """
    POST /api/v1/gst/einvoice/cancel/<uuid:voucher_id>/
    Cancels an active IRN within the statutory 24-hour window.
    """
    permission_classes = [IsAuthenticated, CanGenerateEInvoice]

    def post(self, request, voucher_id):
        try:
            voucher = Voucher.objects.get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({"success": False, "error": "Voucher not found."}, status=404)

        company = get_company_or_404(request.user, voucher.company.id)
        reason = request.data.get('cancel_reason', '1')
        remarks = request.data.get('cancel_remarks', 'Order cancelled')

        res = EInvoiceService.cancel_irn(voucher, cancel_reason=reason, cancel_remarks=remarks, user=request.user)
        status_code = 200 if res.get("success") else 400
        return Response(res, status=status_code)


class EInvoiceDetailAPIView(APIView):
    """
    GET /api/v1/gst/einvoice/voucher/<uuid:voucher_id>/
    Returns active IRN and QR code for printing on invoice layout.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, voucher_id):
        try:
            voucher = Voucher.objects.get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({"success": False, "error": "Voucher not found."}, status=404)

        company = get_company_or_404(request.user, voucher.company.id)
        record = EInvoiceRecord.objects.filter(voucher=voucher).first()
        if not record:
            return Response({"success": False, "error": "No e-Invoice record found for this voucher."}, status=404)

        return Response({"success": True, "einvoice": EInvoiceRecordSerializer(record).data})


class EWayBillGenerateV2APIView(APIView):
    """
    POST /api/v1/gst/ewaybill/generate/<uuid:voucher_id>/
    Generates E-Way Bill for a voucher via Sandbox.
    """
    permission_classes = [IsAuthenticated, CanGenerateEWayBill]

    def post(self, request, voucher_id):
        try:
            voucher = Voucher.objects.get(id=voucher_id)
        except Voucher.DoesNotExist:
            return Response({"success": False, "error": "Voucher not found."}, status=404)

        company = get_company_or_404(request.user, voucher.company.id)
        reg_id = request.data.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        try:
            res = EWayBillServiceV2.generate_ewaybill(
                voucher=voucher,
                trans_mode=request.data.get('trans_mode', '1'),
                distance_km=int(request.data.get('distance_km', 10)),
                transporter_id=request.data.get('transporter_id', ''),
                transporter_name=request.data.get('transporter_name', ''),
                vehicle_number=request.data.get('vehicle_number', ''),
                vehicle_type=request.data.get('vehicle_type', 'R'),
                registration=registration,
                user=request.user
            )
            return Response(res)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class EWayBillVehicleUpdateAPIView(APIView):
    """
    POST /api/v1/gst/ewaybill/update-vehicle/<uuid:ewaybill_id>/
    Updates Part-B Vehicle Details on an active E-Way Bill.
    """
    permission_classes = [IsAuthenticated, CanGenerateEWayBill]

    def post(self, request, ewaybill_id):
        try:
            ewaybill = EWayBillRecord.objects.get(id=ewaybill_id)
        except EWayBillRecord.DoesNotExist:
            return Response({"success": False, "error": "E-Way Bill not found."}, status=404)

        company = get_company_or_404(request.user, ewaybill.company.id)
        res = EWayBillServiceV2.update_vehicle(
            eway_bill=ewaybill,
            vehicle_number=request.data.get('vehicle_number', ''),
            from_place=request.data.get('from_place', company.city or 'City'),
            from_state=request.data.get('from_state', company.state_code or '09'),
            reason_code=request.data.get('reason_code', '1'),
            remarks=request.data.get('remarks', ''),
            user=request.user
        )
        status_code = 200 if res.get("success") else 400
        return Response(res, status=status_code)


class EWayBillCancelV2APIView(APIView):
    """
    POST /api/v1/gst/ewaybill/cancel/<uuid:ewaybill_id>/
    Cancels an active E-Way Bill within 24 hours.
    """
    permission_classes = [IsAuthenticated, CanCancelEWayBill]

    def post(self, request, ewaybill_id):
        try:
            ewaybill = EWayBillRecord.objects.get(id=ewaybill_id)
        except EWayBillRecord.DoesNotExist:
            return Response({"success": False, "error": "E-Way Bill not found."}, status=404)

        company = get_company_or_404(request.user, ewaybill.company.id)
        reason = request.data.get('cancel_reason', '1')
        remarks = request.data.get('cancel_remarks', 'Order cancelled')

        res = EWayBillServiceV2.cancel_ewaybill(ewaybill, cancel_reason=reason, cancel_remarks=remarks, user=request.user)
        status_code = 200 if res.get("success") else 400
        return Response(res, status=status_code)


class GSTAuditLogsAPIView(APIView):
    """
    GET /api/v1/gst/audit-logs/<uuid:company_id>/
    Returns redacted audit log entries for all outbound GST Sandbox interactions.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        logs = GSTAuditLog.objects.filter(company=company).order_by('-created_at')[:100]
        serializer = GSTAuditLogSerializer(logs, many=True)
        return Response({"success": True, "logs": serializer.data})

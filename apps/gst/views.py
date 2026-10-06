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



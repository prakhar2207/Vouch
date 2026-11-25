import json
from datetime import date
from django.utils import timezone
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
from apps.gst.services.period_service import GSTPeriodService
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
        import os
        from django.conf import settings
        from django.utils import timezone
        company = get_company_or_404(request.user, company_id)
        config, _ = CompanyGSTConfig.objects.get_or_create(company=company)

        # 1. Auto-purge any stale mock/simulated tokens so user isn't stuck on fake sessions
        if config.auth_token and (config.auth_token.startswith('GSTN-SANDBOX-') or config.auth_token.startswith('SIMULATED-')):
            config.auth_token = ''
            config.token_expires_at = None
            config.save(update_fields=['auth_token', 'token_expires_at', 'updated_at'])

        # 2. Check if credentials are provided in Render environment variables or DB
        client = SandboxGSTClient(company=company)
        api_key, api_secret, base_url, is_sb = client.get_api_credentials()
        has_env_credentials = bool(
            os.environ.get('SANDBOX_API_KEY')
            or os.environ.get('GST_SANDBOX_API_KEY')
            or os.environ.get('QUICKO_API_KEY')
            or os.environ.get('SANDBOX_KEY')
            or os.environ.get('GST_API_KEY')
            or os.environ.get('SANDBOX_CO_IN_API_KEY')
            or getattr(settings, 'SANDBOX_API_KEY', '')
            or getattr(settings, 'GST_SANDBOX_API_KEY', '')
        )

        # If credentials exist and provider was still MOCK, auto-promote to SANDBOX_CO_IN
        if client.is_configured() and config.provider == 'MOCK':
            config.provider = 'SANDBOX_CO_IN'
            config.save(update_fields=['provider', 'updated_at'])

        is_connected = bool(config.auth_token and (not config.token_expires_at or config.token_expires_at > timezone.now()))
        return Response({
            "success": True,
            "config": {
                "is_portal_connected": is_connected,
                "token_expires_at": config.token_expires_at.strftime('%Y-%m-%d %H:%M:%S') if config.token_expires_at else None,
                "portal_username": config.eway_username or "",
                "gstin": company.gstin or "",
                "registered_name": company.name or "",
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
        if 'sandbox_api_key' in data and data['sandbox_api_key'] and not data['sandbox_api_key'].endswith('****'):
            config.sandbox_api_key = data['sandbox_api_key'].strip()
        if 'sandbox_api_secret' in data and data['sandbox_api_secret']:
            config.sandbox_api_secret = data['sandbox_api_secret'].strip()
        if 'sandbox_base_url' in data and data['sandbox_base_url']:
            config.sandbox_base_url = data['sandbox_base_url'].strip()
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


class CompanyGSTConfigTestConnectionAPIView(APIView):
    """
    POST /api/v1/gst/config/<uuid:company_id>/test-connection/
    Developer/staff diagnostic operation: strictly restricted from ordinary production UI.
    Accessible only through authorized internal diagnostics or staff tooling.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, company_id):
        # Strict restriction: developer diagnostic operation not accessible to ordinary users
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                "success": False,
                "error": "Test connection is an internal diagnostic tool restricted to system administrators."
            }, status=status.HTTP_403_FORBIDDEN)

        company = get_company_or_404(request.user, company_id)
        from apps.gst.services.authentication_service import SandboxAuthenticationService
        result = SandboxAuthenticationService.test_connection(company=company)
        status_code = status.HTTP_200_OK if result.get('healthy') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=status_code)


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

        reg, _ = GSTPortalService.resolve_registration(company, request.data.get('gstin'))

        if is_unmark:
            GSTFilingRecord.objects.filter(
                company=company,
                gst_registration=reg,
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
            gst_registration=reg,
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


class GSTRDirectPortalPreflightAPIView(APIView):
    """
    GET /api/v1/gst/portal/preflight/<uuid:company_id>/
    Phase 2: Automatic Preflight Readiness Check.
    Validates company GSTIN, provider gateway availability, and active session status
    without exposing internal infrastructure, vendor names, or API credentials.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        gstin = request.query_params.get('gstin') or request.data.get('gstin') if hasattr(request, 'data') else request.query_params.get('gstin')
        result = GSTPortalService.get_preflight_status(company, gstin=gstin)
        return Response({"success": True, "preflight": result})


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

        result = GSTPortalService.request_portal_otp(company, gstin=gstin, username=username, user=request.user)
        if not result.get('success'):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
            username=request.data.get('username'),
            user=request.user
        )
        if not result.get('success'):
            return Response(result, status=400)
        return Response(result)


class GSTRDirectPortalUploadGSTR1APIView(APIView):
    """
    POST /api/v1/gst/portal/upload-gstr1/
    Directly uploads GSTR-1 returns to the GST Portal / Sandbox without manual JSON file download.
    Requires an active taxpayer session token.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request):
        company_id = request.data.get('company_id')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        if not company_id or not start_date or not end_date:
            return Response({"success": False, "error": "company_id, start_date, and end_date are required."}, status=400)

        company = get_company_or_404(request.user, company_id)
        gstin = request.data.get('gstin')

        if gstin:
            clean_gstin = str(gstin).strip().upper()
            if not GSTRegistration.objects.filter(company=company, gstin=clean_gstin).exists() and clean_gstin != (company.gstin or '').strip().upper():
                return Response({
                    "success": False,
                    "code": "GSTIN_NOT_REGISTERED",
                    "error": f"GSTIN '{clean_gstin}' is not registered under this company."
                }, status=status.HTTP_400_BAD_REQUEST)

        result = GSTPortalService.upload_gstr1_direct(
            company=company,
            start_date=start_date,
            end_date=end_date,
            gstin=gstin,
            user=request.user
        )
        status_code = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=status_code)


class GSTRDirectPortalStatusAPIView(APIView):
    """
    GET /api/v1/gst/portal/status/<uuid:company_id>/<str:ref_id>/
    Queries return processing status by Reference ID.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id, ref_id):
        company = get_company_or_404(request.user, company_id)
        gstin = request.query_params.get('gstin')
        result = GSTPortalService.get_portal_status(company, ref_id, gstin=gstin, user=request.user)
        return Response(result)


class GSTRDirectPortalDisconnectAPIView(APIView):
    """
    POST /api/v1/gst/portal/disconnect/
    Revokes the active GST Portal session token and marks the taxpayer portal as disconnected.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request):
        company_id = request.data.get('company_id')
        if not company_id:
            return Response({"success": False, "error": "company_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_company_or_404(request.user, company_id)
        gstin = request.data.get('gstin')

        result = GSTPortalService.disconnect_portal_session(company, gstin=gstin, user=request.user)
        return Response(result)


class GSTRDirectPortalRefreshSessionAPIView(APIView):
    """
    POST /api/v1/gst/portal/refresh/
    Refreshes the active GST Portal session token.
    """
    permission_classes = [IsAuthenticated, CanFileGST]

    def post(self, request):
        company_id = request.data.get('company_id')
        if not company_id:
            return Response({"success": False, "error": "company_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        company = get_company_or_404(request.user, company_id)
        gstin = request.data.get('gstin')

        result = GSTPortalService.refresh_portal_session(company, gstin=gstin, user=request.user)
        if not result.get('success'):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)




# ==============================================================================
# PHASE 2 & 3: MULTI-GSTIN, SANDBOX PROVIDER & RECONCILIATION WORKSPACES
# ==============================================================================

from apps.gst.models import (
    GSTRegistration,
    GSTAuditLog,
    EInvoiceRecord,
    GSTReturnWorkspace,
    GSTR2BImport,
    GSTR2BRecord
)
from apps.gst.serializers import (
    GSTRegistrationSerializer,
    GSTRegistrationWriteSerializer,
    EInvoiceRecordSerializer,
    EWayBillRecordSerializer,
    GSTR2BRecordSerializer,
    GSTAuditLogSerializer,
    GSTReturnWorkspaceSerializer
)
from apps.gst.permissions import HasGSTPermission, CanManageGSTRegistration
from apps.accounts.permissions import user_has_company_roles
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gstin_service import GSTINService
from apps.gst.services.returns_service import GSTReturnsService
from apps.gst.services.reconciliation_service import GSTReconciliationService
from apps.gst.services.workspace_service import GSTWorkspaceService
from apps.gst.services.validation_service import GSTValidationService
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
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
            self.check_object_permissions(request, reg)
        except GSTRegistrationAccessDenied:
            return Response({"success": False, "error": "GST registration not found."}, status=404)

        return Response({"success": True, "registration": GSTRegistrationSerializer(reg).data})

    def put(self, request, company_id, pk):
        company = get_company_or_404(request.user, company_id)
        try:
            reg = GSTRegistrationService.get_registration(company, pk)
            self.check_object_permissions(request, reg)
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
            self.check_object_permissions(request, reg)
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
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN', 'ACCOUNTANT', 'CA']):
            return Response({"success": False, "error": "Permission denied: Only OWNER, ADMIN, ACCOUNTANT, or CA can enrich party ledgers."}, status=403)

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
    Supports single period, list of periods, or from_period / to_period range.
    Enforces tenant isolation, multi-GSTIN validation, and structured outcome contracts.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, company_id):
        try:
            company = get_company_or_404(request.user, company_id)
            period = request.data.get('period')
            periods = request.data.get('periods')
            from_period = request.data.get('from_period')
            to_period = request.data.get('to_period')
            reg_id = request.data.get('registration_id')

            registration = None
            if reg_id:
                registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
                if not registration:
                    return Response({
                        "status": "VALIDATION_ERROR",
                        "success": False,
                        "error": f"GST Registration '{reg_id}' was not found for this company."
                    }, status=status.HTTP_400_BAD_REQUEST)
                if registration.status != 'ACTIVE':
                    return Response({
                        "status": "VALIDATION_ERROR",
                        "success": False,
                        "error": f"GST Registration '{registration.gstin}' is inactive."
                    }, status=status.HTTP_400_BAD_REQUEST)

            if periods or (from_period and to_period):
                if from_period and to_period:
                    try:
                        p_from = GSTPeriodService.parse_return_period(from_period)
                        p_to = GSTPeriodService.parse_return_period(to_period)
                        if p_from.start_date > p_to.start_date:
                            return Response({
                                "status": "VALIDATION_ERROR",
                                "success": False,
                                "error": "Reversed return period range: from_period cannot be later than to_period.",
                                "error_code": "INVALID_PERIOD_RANGE"
                            }, status=status.HTTP_400_BAD_REQUEST)
                    except Exception as e:
                        return Response({
                            "status": "VALIDATION_ERROR",
                            "success": False,
                            "error": f"Invalid period in range: {str(e)}",
                            "error_code": "INVALID_RETURN_PERIOD"
                        }, status=status.HTTP_400_BAD_REQUEST)

                res = GSTReconciliationService.fetch_and_ingest_range(
                    company=company,
                    registration=registration,
                    periods=periods,
                    from_period=from_period,
                    to_period=to_period,
                    user=request.user
                )
            else:
                if not period:
                    return Response({
                        "status": "VALIDATION_ERROR",
                        "success": False,
                        "error": "Return period (MMYYYY) or period range (from_period, to_period) is required.",
                        "error_code": "PERIOD_REQUIRED"
                    }, status=status.HTTP_400_BAD_REQUEST)

                try:
                    p_info = GSTPeriodService.parse_return_period(period)
                    clean_period = p_info.normalized_period
                except Exception:
                    return Response({
                        "status": "VALIDATION_ERROR",
                        "success": False,
                        "error": f"Invalid return period '{period}'. Format must be MMYYYY (e.g. 102026).",
                        "error_code": "INVALID_RETURN_PERIOD"
                    }, status=status.HTTP_400_BAD_REQUEST)

                res = GSTReconciliationService.fetch_and_ingest_from_sandbox(
                    company=company,
                    registration=registration,
                    return_period=clean_period,
                    user=request.user
                )

            # Return 200 for SUCCESS, PARTIAL_SUCCESS, or NOT_APPLICABLE so client receives structured outcome
            # Return 401 for AUTHENTICATION_REQUIRED
            # Return 400 for VALIDATION_ERROR or FAILED
            st = res.get("status")
            if st in ["SUCCESS", "EMPTY_SUCCESS", "PARTIAL_SUCCESS", "NOT_APPLICABLE"] or (st is None and res.get("success")):
                status_code = status.HTTP_200_OK
            elif st == "AUTHENTICATION_REQUIRED":
                status_code = status.HTTP_401_UNAUTHORIZED
            else:
                status_code = status.HTTP_400_BAD_REQUEST

            return Response(res, status=status_code)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"GSTR-2B sync failed for company {company_id}: {e}")
            return Response({
                "status": "RECONCILIATION_ERROR",
                "success": False,
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


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


# ==============================================================================
# ROUND 2.0: GST RETURN WORKSPACE, VALIDATION & RECONCILIATION API
# ==============================================================================

class GSTWorkspacePeriodAPIView(APIView):
    """
    GET /api/v1/gst/workspace/<uuid:company_id>/
    POST /api/v1/gst/workspace/<uuid:company_id>/init-period/
    Unified GST Workspace tracking return periods, data availability, validations, and drift.
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), CanViewGST()]
        return [IsAuthenticated(), CanPrepareGST()]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period', '082026')
        return_type = request.query_params.get('return_type', 'GSTR1').upper()
        reg_id = request.query_params.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
        if not registration:
            registration = GSTRegistration.objects.filter(company=company, is_primary=True).first()

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type=return_type,
            return_period=period
        )
        GSTWorkspaceService.check_drift(workspace)

        serializer = GSTReturnWorkspaceSerializer(workspace)
        return Response({
            "success": True,
            "workspace": serializer.data
        })

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        return_type = request.data.get('return_type', 'GSTR1').upper()
        reg_id = request.data.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
        if not registration:
            registration = GSTRegistration.objects.filter(company=company, is_primary=True).first()

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type=return_type,
            return_period=period
        )
        GSTWorkspaceService.check_drift(workspace)

        serializer = GSTReturnWorkspaceSerializer(workspace)
        return Response({
            "success": True,
            "message": f"GST return workspace period '{period}' initialized.",
            "workspace": serializer.data
        })


class GSTWorkspaceDraftAPIView(APIView):
    """
    POST /api/v1/gst/workspace/<uuid:company_id>/generate-draft/
    GET /api/v1/gst/workspace/<uuid:company_id>/draft/
    Compiles or retrieves official return draft snapshot (GSTR-1, GSTR-3B).
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), CanViewGST()]
        return [IsAuthenticated(), CanPrepareGST()]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        return_type = request.data.get('return_type', 'GSTR1').upper()
        reg_id = request.data.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
        if not registration:
            registration = GSTRegistration.objects.filter(company=company, is_primary=True).first()

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type=return_type,
            return_period=period
        )

        updated_ws = GSTWorkspaceService.generate_draft(workspace, user=request.user)
        serializer = GSTReturnWorkspaceSerializer(updated_ws)

        return Response({
            "success": True,
            "message": f"Draft snapshot compiled for {return_type} ({period}).",
            "workspace": serializer.data,
            "draft": updated_ws.draft_payload
        })

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period', '082026')
        return_type = request.query_params.get('return_type', 'GSTR1').upper()
        reg_id = request.query_params.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()
        if not registration:
            registration = GSTRegistration.objects.filter(company=company, is_primary=True).first()

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type=return_type,
            return_period=period
        )
        is_stale = GSTWorkspaceService.check_drift(workspace)
        serializer = GSTReturnWorkspaceSerializer(workspace)

        return Response({
            "success": True,
            "workspace": serializer.data,
            "draft": workspace.draft_payload,
            "is_stale": is_stale
        })


class GSTWorkspaceValidateAPIView(APIView):
    """
    POST /api/v1/gst/workspace/<uuid:company_id>/validate/
    Executes centralized pre-filing validation checks against period vouchers.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        return_type = request.data.get('return_type', 'GSTR1').upper()
        reg_id = request.data.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        start_date, end_date, _, _ = GSTReturnsService.parse_period(period)
        val_res = GSTValidationService.validate_period_vouchers(
            company=company,
            registration=registration,
            start_date=start_date,
            end_date=end_date,
            return_type=return_type
        )
        return Response({
            "success": True,
            "validation": val_res
        })


class GSTWorkspaceSignOffAPIView(APIView):
    """
    POST /api/v1/gst/workspace/<uuid:company_id>/sign-off/
    Marks return draft as REVIEWED following accountant/CA sign-off.
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        return_type = request.data.get('return_type', 'GSTR1').upper()
        reg_id = request.data.get('registration_id')

        # Enforce authorized roles
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN', 'ACCOUNTANT', 'CA']):
            return Response({
                "success": False,
                "error": "Only company Owner, Admin, Accountant, or Chartered Accountant may sign off return drafts."
            }, status=status.HTTP_403_FORBIDDEN)

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type=return_type,
            return_period=period
        )

        res = GSTWorkspaceService.sign_off_draft(workspace, user=request.user)
        status_code = 200 if res.get("success") else 400
        return Response(res, status=status_code)


class GSTWorkspaceExportAPIView(APIView):
    """
    POST /api/v1/gst/workspace/<uuid:company_id>/export/
    Exports official portal JSON payload or structured return data.
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.data.get('period', '082026')
        return_type = request.data.get('return_type', 'GSTR1').upper()
        reg_id = request.data.get('registration_id')
        fmt = request.data.get('format', 'JSON').upper()

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        workspace = GSTWorkspaceService.get_or_create_workspace(
            company=company,
            registration=registration,
            return_type=return_type,
            return_period=period
        )

        res = GSTWorkspaceService.export_draft(workspace, export_format=fmt)
        return Response(res)


class GSTReconciliationUploadAPIView(APIView):
    """
    POST /api/v1/gst/reconciliation/<uuid:company_id>/upload-2b/
    Securely uploads GSTR-2B JSON or Excel file with duplicate detection and automatic matching.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        file_obj = request.FILES.get('file')
        period = request.data.get('period', '').strip()
        reg_id = request.data.get('registration_id')

        if not file_obj:
            return Response({"success": False, "error": "No file provided for upload."}, status=400)

        file_name = file_obj.name.lower()
        if not (file_name.endswith('.json') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
            return Response({
                "success": False,
                "error": "Unsupported file format. Please upload official GSTR-2B in .json or .xlsx format."
            }, status=400)

        # File size check (15MB maximum)
        if file_obj.size > 15 * 1024 * 1024:
            return Response({
                "success": False,
                "error": "File exceeds maximum permitted size of 15MB."
            }, status=400)

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        # Check duplicate import
        if period and GSTR2BImport.objects.filter(
            company=company,
            return_period=period,
            file_name=file_obj.name,
            status='PROCESSED'
        ).exists():
            return Response({
                "success": False,
                "error": f"Duplicate import: A file named '{file_obj.name}' has already been processed for period '{period}'."
            }, status=400)

        try:
            if file_name.endswith('.json'):
                content = file_obj.read().decode('utf-8')
                import json
                json_data = json.loads(content)
                import_batch = ITCReconciliationService.ingest_gstr2b_json(
                    company=company,
                    json_data=json_data,
                    user=request.user,
                    file_name=file_obj.name,
                    return_period=period or None
                )
            else:
                import_batch = ITCReconciliationService.ingest_gstr2b_excel(
                    company=company,
                    file_obj=file_obj,
                    user=request.user,
                    file_name=file_obj.name,
                    return_period=period or None
                )

            if registration:
                import_batch.gst_registration = registration
                import_batch.save(update_fields=['gst_registration'])
                import_batch.records.update(gst_registration=registration)

            # Execute matching
            rec_summary = GSTReconciliationService.reconcile_period(
                company=company,
                registration=registration,
                return_period=import_batch.return_period
            )

            return Response({
                "success": True,
                "message": f"Successfully ingested {import_batch.total_invoices_count} records from '{file_obj.name}'.",
                "import_batch_id": str(import_batch.id),
                "return_period": import_batch.return_period,
                "total_invoices": import_batch.total_invoices_count,
                "reconciliation_summary": rec_summary
            })
        except Exception as e:
            logger.exception("Error processing GSTR-2B file upload")
            return Response({"success": False, "error": f"Failed to parse GSTR-2B file: {str(e)}"}, status=400)


class GSTReconciliationSummaryAPIView(APIView):
    """
    GET /api/v1/gst/reconciliation/<uuid:company_id>/summary/
    Returns 9-category match breakdown and financial metrics.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period')
        reg_id = request.query_params.get('registration_id')

        registration = None
        if reg_id:
            registration = GSTRegistration.objects.filter(id=reg_id, company=company).first()

        summary = GSTReconciliationService.reconcile_period(
            company=company,
            registration=registration,
            return_period=period
        )
        return Response({"success": True, "data": summary})


class GSTReconciliationRecordsAPIView(APIView):
    """
    GET /api/v1/gst/reconciliation/<uuid:company_id>/records/
    Paginated list of GSTR-2B records with individual match status and diffs.
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        period = request.query_params.get('period')
        status_filter = request.query_params.get('match_status')

        records_qs = GSTR2BRecord.objects.filter(company=company).order_by('-invoice_date')
        if period:
            records_qs = records_qs.filter(import_batch__return_period=period)
        if status_filter and status_filter != 'ALL':
            records_qs = records_qs.filter(match_status=status_filter)

        page_records = records_qs[:200]
        serializer = GSTR2BRecordSerializer(page_records, many=True)
        return Response({
            "success": True,
            "count": records_qs.count(),
            "records": serializer.data
        })


class GSTReconciliationManualMatchAPIView(APIView):
    """
    POST /api/v1/gst/reconciliation/<uuid:company_id>/manual-match/
    Manually associates a GSTR-2B record with a purchase voucher with audit trail.
    """
    permission_classes = [IsAuthenticated, CanReconcileGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        record_id = request.data.get('record_id')
        voucher_id = request.data.get('voucher_id')
        notes = request.data.get('notes', '')

        try:
            record = GSTR2BRecord.objects.get(id=record_id, company=company)
        except GSTR2BRecord.DoesNotExist:
            return Response({"success": False, "error": "GSTR-2B record not found."}, status=404)

        try:
            voucher = Voucher.objects.get(id=voucher_id, company=company)
        except Voucher.DoesNotExist:
            return Response({"success": False, "error": "Purchase voucher not found."}, status=404)

        record.matched_voucher = voucher
        record.match_status = 'MATCHED'
        record.is_reviewed = True
        record.reviewed_at = timezone.now()
        record.reviewed_by = request.user
        record.review_notes = notes or f"Manually linked to voucher {voucher.voucher_number} by {request.user.email}"
        record.save(update_fields=['matched_voucher', 'match_status', 'is_reviewed', 'reviewed_at', 'reviewed_by', 'review_notes'])

        return Response({
            "success": True,
            "message": f"Successfully linked record '{record.invoice_number}' with voucher '{voucher.voucher_number}'.",
            "record": GSTR2BRecordSerializer(record).data
        })


class GSTReportingAllocationListAPIView(APIView):
    """
    GET /api/v1/gst/allocations/<uuid:company_id>/
    Lists GST reporting allocations for a company and period with statutory metadata.
    Query params:
    - assigned_period: e.g. 022026
    - status: PENDING | APPROVED | EXCLUDED | SUPERSEDED | ALL
    - event_type: OUTWARD_SUPPLY | INWARD_ITC | INWARD_RCM | CREDIT_NOTE | DEBIT_NOTE
    - is_active: true | false (default: true)
    """
    permission_classes = [IsAuthenticated, CanViewGST]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        assigned_period = request.query_params.get('assigned_period')
        status_filter = request.query_params.get('status', 'ALL').strip().upper()
        event_type = request.query_params.get('event_type')
        is_active_param = request.query_params.get('is_active', 'true').strip().lower()

        from apps.gst.models import GSTReportingAllocation
        from apps.gst.services.allocation_service import GSTAllocationService

        if assigned_period:
            clean_period = assigned_period.strip().replace('-', '').replace('/', '')
            GSTAllocationService.ensure_allocations_for_period(company, clean_period)
            qs = GSTReportingAllocation.objects.filter(company=company, assigned_period=clean_period)
        else:
            qs = GSTReportingAllocation.objects.filter(company=company)

        if is_active_param in ('true', '1', 'yes'):
            qs = qs.filter(is_active=True)
        elif is_active_param in ('false', '0', 'no'):
            qs = qs.filter(is_active=False)

        if status_filter and status_filter != 'ALL':
            qs = qs.filter(status=status_filter)

        if event_type:
            qs = qs.filter(event_type=event_type.strip().upper())

        qs = qs.select_related('voucher', 'voucher__party_ledger', 'superseded_by').order_by('-created_at')[:300]

        allocations_data = []
        for alloc in qs:
            v = alloc.voucher
            allocations_data.append({
                "id": str(alloc.id),
                "voucher_id": str(v.id) if v else None,
                "voucher_number": v.voucher_number if v else "",
                "voucher_type": v.voucher_type if v else "",
                "voucher_date": alloc.voucher_date.strftime('%Y-%m-%d'),
                "entry_date": alloc.entry_date.strftime('%Y-%m-%d'),
                "original_period": alloc.original_period,
                "assigned_period": alloc.assigned_period,
                "financial_year": alloc.financial_year,
                "event_type": alloc.event_type,
                "allocation_reason": alloc.allocation_reason,
                "status": alloc.status,
                "is_statutorily_eligible": alloc.is_statutorily_eligible,
                "statutory_rule": alloc.statutory_rule,
                "statutory_notes": alloc.statutory_notes,
                "exclusion_reason": alloc.exclusion_reason,
                "taxable_value": float(alloc.taxable_value),
                "igst_amount": float(alloc.igst_amount),
                "cgst_amount": float(alloc.cgst_amount),
                "sgst_amount": float(alloc.sgst_amount),
                "cess_amount": float(alloc.cess_amount),
                "total_tax": float(alloc.total_tax),
                "is_active": alloc.is_active,
                "superseded_by_id": str(alloc.superseded_by_id) if alloc.superseded_by_id else None,
                "created_at": alloc.created_at.isoformat(),
            })

        return Response({
            "success": True,
            "count": len(allocations_data),
            "allocations": allocations_data
        })


class GSTReportingReallocateAPIView(APIView):
    """
    POST /api/v1/gst/allocations/<uuid:company_id>/reallocate/
    Reallocates a voucher to a different GST return period with statutory validation.
    Body:
    {
        "voucher_id": "<uuid>",
        "target_period": "032026",
        "reason": "Accountant deferred reporting to March 2026"
    }
    """
    permission_classes = [IsAuthenticated, CanPrepareGST]

    def post(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        voucher_id = request.data.get('voucher_id')
        target_period = request.data.get('target_period')
        reason = request.data.get('reason', 'Manual accountant reallocation')

        if not voucher_id:
            return Response({"success": False, "error": "voucher_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not target_period:
            return Response({"success": False, "error": "target_period is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            voucher = Voucher.objects.get(id=voucher_id, company=company)
        except Voucher.DoesNotExist:
            return Response({"success": False, "error": "Voucher not found for this company."}, status=status.HTTP_404_NOT_FOUND)

        from apps.gst.services.allocation_service import GSTAllocationService
        try:
            new_alloc = GSTAllocationService.reallocate_voucher(
                voucher=voucher,
                target_period=target_period,
                reason=reason,
                user=request.user
            )
        except ValueError as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"success": False, "error": f"Reallocation failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": f"Voucher {voucher.voucher_number} successfully reallocated to period {new_alloc.assigned_period}.",
            "allocation": {
                "id": str(new_alloc.id),
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "original_period": new_alloc.original_period,
                "assigned_period": new_alloc.assigned_period,
                "financial_year": new_alloc.financial_year,
                "allocation_reason": new_alloc.allocation_reason,
                "status": new_alloc.status,
                "is_statutorily_eligible": new_alloc.is_statutorily_eligible,
                "statutory_rule": new_alloc.statutory_rule,
                "taxable_value": float(new_alloc.taxable_value),
                "total_tax": float(new_alloc.total_tax),
                "is_active": new_alloc.is_active,
            }
        })


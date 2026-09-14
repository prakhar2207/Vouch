import json
from datetime import date
from django.http import HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.models import CompanyGSTConfig, EWayBillRecord
from apps.gst.services.gstin_lookup_service import GSTINLookupService
from apps.gst.services.eway_bill_service import EWayBillService
from apps.gst.services.gstr_report_service import GSTRReportService
from rest_framework.exceptions import NotFound

def get_company_or_404(user, company_id):
    try:
        return Company.objects.get(id=company_id, users__user=user, is_active=True)
    except Exception:
        raise NotFound("Company not found or access denied.")

class GSTINLookupAPIView(APIView):
    """
    GET /api/v1/gst/lookup/<str:gstin>/
    Validates GSTIN and auto-fetches trade name, legal name, registered address,
    state, and taxpayer status for instant party creation.
    """
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        config, _ = CompanyGSTConfig.objects.get_or_create(company=company)
        return Response({
            "success": True,
            "config": {
                "provider": config.provider,
                "is_sandbox": config.is_sandbox,
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        voucher_id = request.data.get('voucher_id')
        if not voucher_id:
            return Response({"success": False, "error": "voucher_id is required."}, status=400)

        voucher = Voucher.objects.filter(id=voucher_id, company__users__user=request.user).first()
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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        company = get_company_or_404(request.user, company_id)
        start_date = request.query_params.get('start_date', date.today().replace(day=1).isoformat())
        end_date = request.query_params.get('end_date', date.today().isoformat())

        data = GSTRReportService.generate_gstr3b_summary(company, start_date, end_date)
        return Response({"success": True, "data": data})

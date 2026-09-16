from decimal import Decimal
import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db.models import Sum

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import FinancialYear, Voucher, LedgerEntry, LedgerBalance
from .services.sequence_service import InvoiceSequenceService
from .services.year_end_service import YearEndClosingService

class FinancialYearListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        List all Financial Years for the active company.
        Auto-provisions current Indian FY if none exists.
        """
        company_id = request.query_params.get('company_id')
        if not company_id:
            company = Company.objects.filter(users__user=request.user).first()
        else:
            company = Company.objects.filter(id=company_id, users__user=request.user).first()

        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        # Ensure at least current FY exists
        InvoiceSequenceService.get_or_create_active_fy(company)

        fys = FinancialYear.objects.filter(company=company).order_by('-start_date')
        data = []
        for fy in fys:
            v_count = Voucher.objects.filter(company=company, financial_year=fy).count()
            data.append({
                "id": str(fy.id),
                "name": fy.name,
                "code": fy.code,
                "start_date": fy.start_date.strftime('%Y-%m-%d'),
                "end_date": fy.end_date.strftime('%Y-%m-%d'),
                "is_closed": fy.is_closed,
                "voucher_count": v_count,
                "is_current": fy.start_date <= datetime.date.today() <= fy.end_date,
            })

        return Response({"success": True, "data": data})

    def post(self, request):
        """
        Create a new Financial Year explicitly or auto-generate next FY.
        """
        company_id = request.data.get('company_id')
        if not company_id:
            company = Company.objects.filter(users__user=request.user).first()
        else:
            company = Company.objects.filter(id=company_id, users__user=request.user).first()

        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')

        if start_date_str and end_date_str:
            start_date = datetime.date.fromisoformat(start_date_str)
            end_date = datetime.date.fromisoformat(end_date_str)
            start_yy = str(start_date.year)[-2:]
            end_yy = str(end_date.year)[-2:]
            code = f"{start_yy}-{end_yy}"
            name = request.data.get('name') or f"FY {start_date.year}-{end_yy}"

            fy, created = FinancialYear.objects.get_or_create(
                company=company,
                code=code,
                defaults={
                    'name': name,
                    'start_date': start_date,
                    'end_date': end_date,
                    'is_closed': False
                }
            )
        else:
            # Auto-generate next FY after latest existing FY
            latest_fy = FinancialYear.objects.filter(company=company).order_by('-end_date').first()
            if latest_fy:
                next_start = latest_fy.end_date + datetime.timedelta(days=1)
                fy = InvoiceSequenceService.get_or_create_active_fy(company, next_start)
                created = True
            else:
                fy = InvoiceSequenceService.get_or_create_active_fy(company)
                created = True

        return Response({
            "success": True,
            "message": f"Financial Year {fy.name} ready.",
            "data": {
                "id": str(fy.id),
                "name": fy.name,
                "code": fy.code,
                "start_date": fy.start_date.strftime('%Y-%m-%d'),
                "end_date": fy.end_date.strftime('%Y-%m-%d'),
                "is_closed": fy.is_closed,
            }
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class FinancialYearPreCloseAuditAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = Company.objects.filter(users__user=request.user).first()
        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        try:
            audit = YearEndClosingService.pre_close_audit(company.id, str(pk))
            return Response({"success": True, "data": audit})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class FinancialYearCloseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        company = Company.objects.filter(users__user=request.user).first()
        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        next_fy_id = request.data.get('next_fy_id')

        try:
            result = YearEndClosingService.close_and_roll_forward(company.id, str(pk), next_fy_id)
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"success": False, "error": str(ve.message if hasattr(ve, 'message') else ve)}, status=400)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class SequencePreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company_id = request.query_params.get('company_id')
        if not company_id:
            company = Company.objects.filter(users__user=request.user).first()
        else:
            company = Company.objects.filter(id=company_id, users__user=request.user).first()

        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        voucher_type = request.query_params.get('voucher_type', 'SALES')
        voucher_date = request.query_params.get('voucher_date') or request.query_params.get('date')
        custom_prefix = request.query_params.get('prefix')
        resync = request.query_params.get('resync', '').lower() in ('true', '1')

        try:
            if resync:
                fy = InvoiceSequenceService.get_or_create_active_fy(company, voucher_date)
                InvoiceSequenceService.resync_sequence(company, fy, voucher_type, custom_prefix, force=True)

            preview = InvoiceSequenceService.preview_next_number(company, voucher_type, voucher_date, custom_prefix)
            return Response({"success": True, "data": preview})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request):
        """Allow explicit resync of sequence counter to match actual existing vouchers."""
        company_id = request.data.get('company_id') or request.query_params.get('company_id')
        if not company_id:
            company = Company.objects.filter(users__user=request.user).first()
        else:
            company = Company.objects.filter(id=company_id, users__user=request.user).first()

        if not company:
            return Response({"success": False, "error": "Company not found"}, status=404)

        voucher_type = request.data.get('voucher_type', 'SALES')
        voucher_date = request.data.get('voucher_date') or request.data.get('date')
        custom_prefix = request.data.get('prefix')

        try:
            fy = InvoiceSequenceService.get_or_create_active_fy(company, voucher_date)
            InvoiceSequenceService.resync_sequence(company, fy, voucher_type, custom_prefix, force=True)
            preview = InvoiceSequenceService.preview_next_number(company, voucher_type, voucher_date, custom_prefix)
            return Response({"success": True, "message": "Sequence resynced successfully", "data": preview})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


# Canonical LedgerStatementAPIView alias for backwards compatibility
from apps.accounting.views import LedgerStatementAPIView


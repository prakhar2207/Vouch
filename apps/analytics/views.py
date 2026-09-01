from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.companies.models import Company
from .services.ai_service import AnalyticsEngine

class InsightsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id=None):
        try:
            if not company_id:
                company = Company.objects.filter(users__user=request.user).first()
            else:
                company = Company.objects.get(id=company_id, users__user=request.user)

            if not company:
                return Response({"success": False, "error": "Company not found"}, status=404)

            data = AnalyticsEngine.get_full_insights(company)
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class RFMAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            data = AnalyticsEngine.get_rfm_segments(company)
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class SalesForecastView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            days = int(request.query_params.get('days', 30))
            data = AnalyticsEngine.forecast_sales(company, days=days)
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        try:
            from django.db.models import Sum
            from decimal import Decimal
            from apps.accounting.models import Voucher
            company = Company.objects.get(id=company_id, users__user=request.user)
            
            total_sales = Voucher.objects.filter(
                company=company, voucher_type='SALES', status='POSTED'
            ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            
            total_purchases = Voucher.objects.filter(
                company=company, voucher_type='PURCHASE', status='POSTED'
            ).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            
            return Response({
                "success": True,
                "data": {
                    "total_sales_volume": total_sales,
                    "total_purchase_volume": total_purchases
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

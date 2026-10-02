from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import get_authorized_company, IsCompanyMember
from .services.ai_service import AnalyticsEngine

class InsightsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id=None):
        try:
            company = get_authorized_company(request, company_id=company_id)
            data = AnalyticsEngine.get_full_insights(company)
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class RFMAnalysisView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id):
        try:
            company = get_authorized_company(request, company_id=company_id)
            data = AnalyticsEngine.get_rfm_segments(company)
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class SalesForecastView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id=None):
        try:
            company = get_authorized_company(request, company_id=company_id)
            days = int(request.query_params.get('days', 30))
            data = AnalyticsEngine.forecast_sales(company, days=days)
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class MonthlyComparisonView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id=None):
        try:
            company = get_authorized_company(request, company_id=company_id)
            days = int(request.query_params.get('days', 30))
            forecast = AnalyticsEngine.forecast_sales(company, days=days)
            return Response({"success": True, "data": forecast.get("monthly_comparison")})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id):
        try:
            from django.db.models import Sum
            from decimal import Decimal
            from apps.accounting.models import Voucher
            company = get_authorized_company(request, company_id=company_id)
            
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


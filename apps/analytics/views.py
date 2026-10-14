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


class CashCycleSnapshotView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id):
        try:
            from .models import CashCycleSnapshot
            company = get_authorized_company(request, company_id=company_id)
            snapshots = CashCycleSnapshot.objects.filter(company=company).order_by('recorded_date')
            data = [
                {
                    "id": str(s.id),
                    "period_label": s.period_label,
                    "date": s.recorded_date.strftime('%Y-%m-%d'),
                    "net_ccc_days": s.net_ccc_days,
                    "dio_days": s.dio_days,
                    "dso_days": s.dso_days,
                    "dpo_days": s.dpo_days,
                    "accounts_receivable": float(s.accounts_receivable),
                    "accounts_payable": float(s.accounts_payable),
                    "inventory_valuation": float(s.inventory_valuation),
                    "working_capital_health": s.working_capital_health,
                    "notes": s.notes or "",
                    "is_system_generated": s.is_system_generated,
                    "created_at": s.created_at.strftime('%Y-%m-%d %H:%M')
                }
                for s in snapshots
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
            company = get_authorized_company(request, company_id=company_id)
            period_label = request.data.get('period_label')
            notes = request.data.get('notes')
            snapshot = AnalyticsEngine.record_cash_cycle_snapshot(company, period_label=period_label, notes=notes)
            return Response({
                "success": True,
                "message": f"Cash conversion cycle snapshot recorded for '{snapshot.period_label}'.",
                "data": {
                    "id": str(snapshot.id),
                    "period_label": snapshot.period_label,
                    "net_ccc_days": snapshot.net_ccc_days,
                    "dio_days": snapshot.dio_days,
                    "dso_days": snapshot.dso_days,
                    "dpo_days": snapshot.dpo_days,
                    "working_capital_health": snapshot.working_capital_health,
                    "notes": snapshot.notes,
                    "date": snapshot.recorded_date.strftime('%Y-%m-%d')
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)



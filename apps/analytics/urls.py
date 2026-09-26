from django.urls import path
from .views import RFMAnalysisView, SalesForecastView, DashboardSummaryView, InsightsAPIView, MonthlyComparisonView

urlpatterns = [
    path('insights/', InsightsAPIView.as_view(), name='insights_default'),
    path('insights/<uuid:company_id>/', InsightsAPIView.as_view(), name='insights_company'),
    path('rfm/<uuid:company_id>/', RFMAnalysisView.as_view(), name='rfm_analysis'),
    path('forecast/', SalesForecastView.as_view(), name='sales_forecast_default'),
    path('forecast/<uuid:company_id>/', SalesForecastView.as_view(), name='sales_forecast'),
    path('monthly-comparison/', MonthlyComparisonView.as_view(), name='monthly_comparison_default'),
    path('monthly-comparison/<uuid:company_id>/', MonthlyComparisonView.as_view(), name='monthly_comparison'),
    path('dashboard/<uuid:company_id>/', DashboardSummaryView.as_view(), name='dashboard_summary'),
]

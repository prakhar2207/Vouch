from django.urls import path
from .views import RFMAnalysisView, SalesForecastView, DashboardSummaryView, InsightsAPIView

urlpatterns = [
    path('insights/', InsightsAPIView.as_view(), name='insights_default'),
    path('insights/<uuid:company_id>/', InsightsAPIView.as_view(), name='insights_company'),
    path('rfm/<uuid:company_id>/', RFMAnalysisView.as_view(), name='rfm_analysis'),
    path('forecast/<uuid:company_id>/', SalesForecastView.as_view(), name='sales_forecast'),
    path('dashboard/<uuid:company_id>/', DashboardSummaryView.as_view(), name='dashboard_summary'),
]

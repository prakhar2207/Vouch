from django.urls import path
from .views import (
    GSTINLookupAPIView,
    CompanyGSTConfigAPIView,
    EWayBillGenerateAPIView,
    EWayBillUpdateVehicleAPIView,
    EWayBillCancelAPIView,
    EWayBillVoucherDetailAPIView,
    GSTR1ExportAPIView,
    GSTR3BSummaryAPIView,
)

urlpatterns = [
    # Party Creation & Verification via GSTIN
    path('lookup/<str:gstin>/', GSTINLookupAPIView.as_view(), name='gst_lookup'),
    
    # Company GST & E-Way Portal Configuration
    path('config/<uuid:company_id>/', CompanyGSTConfigAPIView.as_view(), name='gst_config'),
    
    # E-Way Bill Lifecycle Endpoints
    path('eway-bill/generate/', EWayBillGenerateAPIView.as_view(), name='eway_bill_generate'),
    path('eway-bill/update-vehicle/', EWayBillUpdateVehicleAPIView.as_view(), name='eway_bill_update_vehicle'),
    path('eway-bill/cancel/', EWayBillCancelAPIView.as_view(), name='eway_bill_cancel'),
    path('eway-bill/voucher/<uuid:voucher_id>/', EWayBillVoucherDetailAPIView.as_view(), name='eway_bill_voucher_detail'),
    
    # GST Returns Export
    path('reports/gstr1/<uuid:company_id>/', GSTR1ExportAPIView.as_view(), name='gstr1_export'),
    path('reports/gstr3b/<uuid:company_id>/', GSTR3BSummaryAPIView.as_view(), name='gstr3b_summary'),
]

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
    GSTRPreFilingExceptionsAPIView,
    GSTR9AnnualSummaryAPIView,
    GSTRMarkPeriodFiledAPIView,
    GSTRDirectPortalOTPRequestAPIView,
    GSTRDirectPortalVerifyOTPAPIView,
    GSTRDirectPortalUploadGSTR1APIView,
    GSTRDirectPortalStatusAPIView,
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
    
    # GST Returns Center & Exports
    path('reports/gstr1/<uuid:company_id>/', GSTR1ExportAPIView.as_view(), name='gstr1_export'),
    path('reports/gstr3b/<uuid:company_id>/', GSTR3BSummaryAPIView.as_view(), name='gstr3b_summary'),
    path('reports/gstr9/<uuid:company_id>/', GSTR9AnnualSummaryAPIView.as_view(), name='gstr9_annual_summary'),
    path('returns/exceptions/<uuid:company_id>/', GSTRPreFilingExceptionsAPIView.as_view(), name='gstr_exceptions'),
    path('returns/mark-filed/<uuid:company_id>/', GSTRMarkPeriodFiledAPIView.as_view(), name='gstr_mark_filed'),

    # Direct GST Portal Sandbox & Live API Upload
    path('portal/request-otp/', GSTRDirectPortalOTPRequestAPIView.as_view(), name='gst_portal_request_otp'),
    path('portal/verify-otp/', GSTRDirectPortalVerifyOTPAPIView.as_view(), name='gst_portal_verify_otp'),
    path('portal/upload-gstr1/', GSTRDirectPortalUploadGSTR1APIView.as_view(), name='gst_portal_upload_gstr1'),
    path('portal/status/<uuid:company_id>/<str:ref_id>/', GSTRDirectPortalStatusAPIView.as_view(), name='gst_portal_status'),
]

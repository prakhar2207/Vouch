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
    # Phase 2 & 3 Sandbox by Quicko Integration Views
    GSTRegistrationListCreateAPIView,
    GSTRegistrationDetailAPIView,
    GSTRegistrationVerifyPreviewAPIView,
    GSTRegistrationVerifyAPIView,
    GSTRegistrationDeactivateAPIView,
    GSTRegistrationReactivateAPIView,
    UnifiedGSTINVerifyAPIView,
    PartyEnrichmentApplyAPIView,
    GSTOverviewAPIView,
    GSTR1WorkspaceAPIView,
    GSTR1SubmitAPIView,
    GSTR3BWorkspaceAPIView,
    GSTR2BReconciliationAPIView,
    GSTR2BSyncFromSandboxAPIView,
    GSTR2BReviewRecordAPIView,
    EInvoiceGenerateAPIView,
    EInvoiceCancelAPIView,
    EInvoiceDetailAPIView,
    EWayBillGenerateV2APIView,
    EWayBillVehicleUpdateAPIView,
    EWayBillCancelV2APIView,
    GSTAuditLogsAPIView,
    GSTWorkspacePeriodAPIView,
    GSTWorkspaceDraftAPIView,
    GSTWorkspaceValidateAPIView,
    GSTWorkspaceSignOffAPIView,
    GSTWorkspaceExportAPIView,
    GSTReconciliationUploadAPIView,
    GSTReconciliationSummaryAPIView,
    GSTReconciliationRecordsAPIView,
    GSTReconciliationManualMatchAPIView,
)
from .itc_views import (
    GSTR2BUploadView,
    ITCReconciliationListView,
    ITCSmartPaymentHoldView,
    ITCVendorNoticeView,
    ITCSummaryView,
    ITCRunReconciliationView,
)


urlpatterns = [
    # 1. Multi-GSTIN Registrations
    path('registrations/<uuid:company_id>/', GSTRegistrationListCreateAPIView.as_view(), name='gst_registrations_list_create'),
    path('registrations/<uuid:company_id>/verify-preview/', GSTRegistrationVerifyPreviewAPIView.as_view(), name='gst_registration_verify_preview'),
    path('registrations/<uuid:company_id>/<uuid:pk>/', GSTRegistrationDetailAPIView.as_view(), name='gst_registration_detail'),
    path('registrations/<uuid:company_id>/<uuid:pk>/verify/', GSTRegistrationVerifyAPIView.as_view(), name='gst_registration_verify'),
    path('registrations/<uuid:company_id>/<uuid:pk>/deactivate/', GSTRegistrationDeactivateAPIView.as_view(), name='gst_registration_deactivate'),
    path('registrations/<uuid:company_id>/<uuid:pk>/reactivate/', GSTRegistrationReactivateAPIView.as_view(), name='gst_registration_reactivate'),

    # 2. Unified GSTIN Verification & Party Auto-fill
    path('verify-gstin/', UnifiedGSTINVerifyAPIView.as_view(), name='gst_unified_verify'),
    path('party/enrich/', PartyEnrichmentApplyAPIView.as_view(), name='gst_party_enrich'),
    path('lookup/<str:gstin>/', GSTINLookupAPIView.as_view(), name='gst_lookup'),

    # 3. GST Overview Dashboard
    path('overview/<uuid:company_id>/', GSTOverviewAPIView.as_view(), name='gst_overview'),
    path('config/<uuid:company_id>/', CompanyGSTConfigAPIView.as_view(), name='gst_config'),

    # 4. GSTR-1 Outward Supplies Workspace
    path('returns/gstr1/<uuid:company_id>/', GSTR1WorkspaceAPIView.as_view(), name='gst_returns_gstr1_workspace'),
    path('returns/gstr1/submit/<uuid:company_id>/', GSTR1SubmitAPIView.as_view(), name='gst_returns_gstr1_submit'),
    path('reports/gstr1/<uuid:company_id>/', GSTR1ExportAPIView.as_view(), name='gstr1_export'),
    path('returns/exceptions/<uuid:company_id>/', GSTRPreFilingExceptionsAPIView.as_view(), name='gstr_exceptions'),
    path('returns/mark-filed/<uuid:company_id>/', GSTRMarkPeriodFiledAPIView.as_view(), name='gstr_mark_filed'),

    # 5. GSTR-3B Tax Summary Workspace
    path('returns/gstr3b/<uuid:company_id>/', GSTR3BWorkspaceAPIView.as_view(), name='gst_returns_gstr3b_workspace'),
    path('reports/gstr3b/<uuid:company_id>/', GSTR3BSummaryAPIView.as_view(), name='gstr3b_summary'),
    path('reports/gstr9/<uuid:company_id>/', GSTR9AnnualSummaryAPIView.as_view(), name='gstr9_annual_summary'),

    # 6. GSTR-2B Purchase Reconciliation Workspace
    path('reconciliation/gstr2b/<uuid:company_id>/', GSTR2BReconciliationAPIView.as_view(), name='gst_reconciliation_gstr2b'),
    path('reconciliation/gstr2b/sync/<uuid:company_id>/', GSTR2BSyncFromSandboxAPIView.as_view(), name='gst_reconciliation_gstr2b_sync'),
    path('reconciliation/gstr2b/review/<uuid:record_id>/', GSTR2BReviewRecordAPIView.as_view(), name='gst_reconciliation_review'),
    path('reconciliation/<uuid:company_id>/upload-2b/', GSTReconciliationUploadAPIView.as_view(), name='gst_reconciliation_upload_2b'),
    path('reconciliation/<uuid:company_id>/run/', GSTReconciliationSummaryAPIView.as_view(), name='gst_reconciliation_run'),
    path('reconciliation/<uuid:company_id>/summary/', GSTReconciliationSummaryAPIView.as_view(), name='gst_reconciliation_summary'),
    path('reconciliation/<uuid:company_id>/records/', GSTReconciliationRecordsAPIView.as_view(), name='gst_reconciliation_records'),
    path('reconciliation/<uuid:company_id>/manual-match/', GSTReconciliationManualMatchAPIView.as_view(), name='gst_reconciliation_manual_match'),

    # 6B. Unified GST Return Workspace (Round 2.0)
    path('workspace/<uuid:company_id>/', GSTWorkspacePeriodAPIView.as_view(), name='gst_workspace_period'),
    path('workspace/<uuid:company_id>/init-period/', GSTWorkspacePeriodAPIView.as_view(), name='gst_workspace_init_period'),
    path('workspace/<uuid:company_id>/generate-draft/', GSTWorkspaceDraftAPIView.as_view(), name='gst_workspace_generate_draft'),
    path('workspace/<uuid:company_id>/draft/', GSTWorkspaceDraftAPIView.as_view(), name='gst_workspace_draft_get'),
    path('workspace/<uuid:company_id>/validate/', GSTWorkspaceValidateAPIView.as_view(), name='gst_workspace_validate'),
    path('workspace/<uuid:company_id>/sign-off/', GSTWorkspaceSignOffAPIView.as_view(), name='gst_workspace_sign_off'),
    path('workspace/<uuid:company_id>/export/', GSTWorkspaceExportAPIView.as_view(), name='gst_workspace_export'),

    # Legacy ITC views
    path('itc/upload-2b/', GSTR2BUploadView.as_view(), name='itc_upload_2b'),
    path('itc/reconciliation/', ITCReconciliationListView.as_view(), name='itc_reconciliation_list'),
    path('itc/reconcile-now/', ITCRunReconciliationView.as_view(), name='itc_run_reconciliation'),
    path('itc/hold-gst/', ITCSmartPaymentHoldView.as_view(), name='itc_hold_gst'),
    path('itc/vendor-notice/<uuid:voucher_id>/', ITCVendorNoticeView.as_view(), name='itc_vendor_notice'),
    path('itc/summary/', ITCSummaryView.as_view(), name='itc_summary'),

    # 7. E-Invoice (IRN) Lifecycle
    path('einvoice/generate/<uuid:voucher_id>/', EInvoiceGenerateAPIView.as_view(), name='gst_einvoice_generate'),
    path('einvoice/cancel/<uuid:voucher_id>/', EInvoiceCancelAPIView.as_view(), name='gst_einvoice_cancel'),
    path('einvoice/voucher/<uuid:voucher_id>/', EInvoiceDetailAPIView.as_view(), name='gst_einvoice_detail'),

    # 8. E-Way Bill Lifecycle
    path('ewaybill/generate/<uuid:voucher_id>/', EWayBillGenerateV2APIView.as_view(), name='gst_ewaybill_generate_v2'),
    path('ewaybill/update-vehicle/<uuid:ewaybill_id>/', EWayBillVehicleUpdateAPIView.as_view(), name='gst_ewaybill_update_vehicle'),
    path('ewaybill/cancel/<uuid:ewaybill_id>/', EWayBillCancelV2APIView.as_view(), name='gst_ewaybill_cancel_v2'),
    path('eway-bill/generate/', EWayBillGenerateAPIView.as_view(), name='eway_bill_generate'),
    path('eway-bill/update-vehicle/', EWayBillUpdateVehicleAPIView.as_view(), name='eway_bill_update_vehicle'),
    path('eway-bill/cancel/', EWayBillCancelAPIView.as_view(), name='eway_bill_cancel'),
    path('eway-bill/voucher/<uuid:voucher_id>/', EWayBillVoucherDetailAPIView.as_view(), name='eway_bill_voucher_detail'),

    # 9. Direct GST Portal OTP Endpoints
    path('portal/request-otp/', GSTRDirectPortalOTPRequestAPIView.as_view(), name='gst_portal_request_otp'),
    path('portal/verify-otp/', GSTRDirectPortalVerifyOTPAPIView.as_view(), name='gst_portal_verify_otp'),
    path('portal/upload-gstr1/', GSTRDirectPortalUploadGSTR1APIView.as_view(), name='gst_portal_upload_gstr1'),
    path('portal/status/<uuid:company_id>/<str:ref_id>/', GSTRDirectPortalStatusAPIView.as_view(), name='gst_portal_status'),

    # 10. Audit History
    path('audit-logs/<uuid:company_id>/', GSTAuditLogsAPIView.as_view(), name='gst_audit_logs'),
]

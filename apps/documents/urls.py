from django.urls import path
from apps.documents import views

urlpatterns = [
    # Voucher Document Endpoints
    path('vouchers/<uuid:voucher_id>/snapshot/', views.VoucherSnapshotAPIView.as_view(), name='doc_voucher_snapshot'),
    path('vouchers/<uuid:voucher_id>/pdf/', views.VoucherPDFStreamAPIView.as_view(), name='doc_voucher_pdf'),
    path('vouchers/<uuid:voucher_id>/share/', views.VoucherShareAPIView.as_view(), name='doc_voucher_share'),

    # Statement Document Endpoints
    path('statements/<uuid:ledger_id>/share/', views.StatementShareAPIView.as_view(), name='doc_statement_share'),
    path('statements/<uuid:ledger_id>/pdf/', views.LedgerStatementPDFExportAPIView.as_view(), name='doc_statement_pdf'),

    # Financial Reports PDF Export
    path('reports/<str:report_type>/pdf/', views.ReportPDFExportAPIView.as_view(), name='doc_report_pdf'),

    # Public Secure Tokenized Sharing & EDI Handshake Endpoints
    path('share/resolve/<str:token>/', views.PublicShareResolveAPIView.as_view(), name='doc_share_resolve'),
    path('share/download/<str:token>/', views.PublicShareDownloadPDFAPIView.as_view(), name='doc_share_download'),
    path('share/import/<str:token>/', views.ShareEDIImportAPIView.as_view(), name='doc_share_edi_import'),
]

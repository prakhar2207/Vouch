from django.urls import path
from .views import (
    CreateSalesInvoiceAPIView, CreatePurchaseInvoiceAPIView, TrialBalanceAPIView, 
    ProfitAndLossReportAPIView, BalanceSheetReportAPIView,
    ListVouchersAPIView, VoucherDetailAPIView, PublicVoucherDetailAPIView, VoucherDownloadPermissionAPIView, VoucherAttachmentAPIView, LedgerStatementAPIView, 
    CreatePaymentReceiptAPIView, ListPaymentReceiptAPIView, UniversalVoucherAPIView,
    SyncTaxLedgersAPIView, PartyRatesAPIView, RebuildBalancesAPIView,
    AgingReportAPIView, AutoFIFOReconciliationAPIView, VoucherAuditHistoryAPIView
)
from .ocr_views import OCRExtractAPIView
from .b2b_views import (
    InwardVoucherInboxView, InwardVoucherDetailView, InwardVoucherAcceptView, InwardVoucherRejectView
)
from .tally_views import TallyExportAPIView
import apps.accounting.banking_views
import apps.accounting.health_views

urlpatterns = [
    path('vouchers/', UniversalVoucherAPIView.as_view(), name='universal_vouchers'),
    path('vouchers/<uuid:company_id>/', UniversalVoucherAPIView.as_view(), name='universal_vouchers_company'),
    path('ocr/extract/', OCRExtractAPIView.as_view(), name='ocr_extract'),
    path('sales-invoice/', CreateSalesInvoiceAPIView.as_view(), name='create_sales_invoice'),
    path('purchase-invoice/', CreatePurchaseInvoiceAPIView.as_view(), name='create_purchase_invoice'),
    path('payment-receipt/', CreatePaymentReceiptAPIView.as_view(), name='create_payment_receipt'),
    path('payment-receipts/<uuid:company_id>/', ListPaymentReceiptAPIView.as_view(), name='list_payment_receipts'),
    path('reports/trial-balance/<uuid:company_id>/', TrialBalanceAPIView.as_view(), name='trial_balance'),
    path('reports/profit-and-loss/', ProfitAndLossReportAPIView.as_view(), name='profit_and_loss_report'),
    path('reports/profit-and-loss/<uuid:company_id>/', ProfitAndLossReportAPIView.as_view(), name='profit_and_loss_report_company'),
    path('reports/balance-sheet/', BalanceSheetReportAPIView.as_view(), name='balance_sheet_report'),
    path('reports/balance-sheet/<uuid:company_id>/', BalanceSheetReportAPIView.as_view(), name='balance_sheet_report_company'),
    path('reports/aging/', AgingReportAPIView.as_view(), name='aging_report'),
    path('reports/aging/<uuid:company_id>/', AgingReportAPIView.as_view(), name='aging_report_company'),
    path('allocation/auto-fifo/', AutoFIFOReconciliationAPIView.as_view(), name='auto_fifo_reconciliation'),
    path('allocation/auto-fifo/<uuid:company_id>/', AutoFIFOReconciliationAPIView.as_view(), name='auto_fifo_reconciliation_company'),
    path('vouchers/detail/<uuid:voucher_id>/', VoucherDetailAPIView.as_view(), name='voucher_detail'),
    path('voucher-detail/<uuid:voucher_id>/', VoucherDetailAPIView.as_view(), name='voucher_detail_alias'),
    path('vouchers/<uuid:voucher_id>/history/', VoucherAuditHistoryAPIView.as_view(), name='voucher_history'),
    path('vouchers/public/<uuid:voucher_id>/', PublicVoucherDetailAPIView.as_view(), name='public_voucher_detail'),
    path('vouchers/<uuid:voucher_id>/download-permission/', VoucherDownloadPermissionAPIView.as_view(), name='voucher_download_permission'),
    path('vouchers/<uuid:voucher_id>/attachment/', VoucherAttachmentAPIView.as_view(), name='voucher_attachment'),
    path('reports/ledger-statement/<uuid:company_id>/<uuid:ledger_id>/', LedgerStatementAPIView.as_view(), name='ledger_statement'),
    
    # B2B EDI Network
    path('b2b/inbox/', InwardVoucherInboxView.as_view(), name='b2b_inbox'),
    path('b2b/inbox/<uuid:pk>/', InwardVoucherDetailView.as_view(), name='b2b_inbox_detail'),
    path('b2b/inbox/<uuid:pk>/accept/', InwardVoucherAcceptView.as_view(), name='b2b_inbox_accept'),
    path('b2b/inbox/<uuid:pk>/reject/', InwardVoucherRejectView.as_view(), name='b2b_inbox_reject'),

    # Tally Export
    path('export/tally/xml/', TallyExportAPIView.as_view(), name='export_tally_xml'),

    # Tax Ledgers Auto-healing & Sync
    path('sync-tax-ledgers/', SyncTaxLedgersAPIView.as_view(), name='sync_tax_ledgers'),
    path('sync-tax-ledgers/<uuid:company_id>/', SyncTaxLedgersAPIView.as_view(), name='sync_tax_ledgers_company'),

    # Rebuild Balances
    path('rebuild-balances/', RebuildBalancesAPIView.as_view(), name='rebuild_balances'),
    path('rebuild-balances/<uuid:company_id>/', RebuildBalancesAPIView.as_view(), name='rebuild_balances_company'),

    # Party Past Item Rates
    path('party-rates/', PartyRatesAPIView.as_view(), name='party_rates'),
    path('party-rates/<uuid:company_id>/', PartyRatesAPIView.as_view(), name='party_rates_company'),

    # Bank Intelligence & Reconciliation
    path('banking/upload/', apps.accounting.banking_views.BankStatementUploadAPIView.as_view(), name='banking_upload'),
    path('banking/statements/', apps.accounting.banking_views.BankStatementImportListAPIView.as_view(), name='banking_statements'),
    path('banking/statements/<uuid:pk>/', apps.accounting.banking_views.BankStatementImportDetailAPIView.as_view(), name='banking_statement_detail'),
    path('banking/transactions/', apps.accounting.banking_views.BankTransactionListAPIView.as_view(), name='banking_transactions'),
    path('banking/transactions/<uuid:pk>/', apps.accounting.banking_views.BankTransactionDetailAPIView.as_view(), name='banking_transaction_detail'),
    path('banking/transactions/<uuid:pk>/toggle-direction/', apps.accounting.banking_views.BankTransactionToggleDirectionAPIView.as_view(), name='banking_transaction_toggle_direction'),
    path('banking/transactions/<uuid:pk>/resolve/', apps.accounting.banking_views.BankTransactionResolveAPIView.as_view(), name='banking_transaction_resolve'),
    path('banking/transactions/bulk-resolve/', apps.accounting.banking_views.BankTransactionBulkResolveAPIView.as_view(), name='banking_transaction_bulk_resolve'),
    path('banking/mappings/', apps.accounting.banking_views.PartyMappingListAPIView.as_view(), name='banking_mappings'),
    path('banking/mappings/<uuid:pk>/', apps.accounting.banking_views.PartyMappingListAPIView.as_view(), name='banking_mapping_detail'),
    path('banking/summary/', apps.accounting.banking_views.BankSummaryAPIView.as_view(), name='banking_summary'),

    # Accounting Health & Vouch Assistant
    path('health/', apps.accounting.health_views.AccountingHealthAPIView.as_view(), name='accounting_health'),
    path('health/diagnose-balance/', apps.accounting.health_views.DiagnoseBalanceAPIView.as_view(), name='diagnose_balance'),
    path('health/findings/<uuid:pk>/preview/', apps.accounting.health_views.FindingFixPreviewAPIView.as_view(), name='finding_fix_preview'),
    path('health/findings/<uuid:pk>/fix/', apps.accounting.health_views.FindingFixExecuteAPIView.as_view(), name='finding_fix_execute'),

    # Offline-First Batch Sync (Accounting Namespace)
    path('sync/pull/', apps.accounting.sync_views.SyncPullAPIView.as_view(), name='accounting_sync_pull'),
    path('sync/push/', apps.accounting.sync_views.SyncPushAPIView.as_view(), name='accounting_sync_push'),
]


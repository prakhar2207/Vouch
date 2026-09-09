from django.urls import path
from .views import (
    CreateSalesInvoiceAPIView, CreatePurchaseInvoiceAPIView, TrialBalanceAPIView, 
    ListVouchersAPIView, VoucherDetailAPIView, LedgerStatementAPIView, 
    CreatePaymentReceiptAPIView, ListPaymentReceiptAPIView, UniversalVoucherAPIView,
    SyncTaxLedgersAPIView, PartyRatesAPIView, RebuildBalancesAPIView
)
from .ocr_views import OCRExtractAPIView
from .b2b_views import (
    InwardVoucherInboxView, InwardVoucherDetailView, InwardVoucherAcceptView, InwardVoucherRejectView
)
from .tally_views import TallyExportAPIView

urlpatterns = [
    path('vouchers/', UniversalVoucherAPIView.as_view(), name='universal_vouchers'),
    path('vouchers/<uuid:company_id>/', UniversalVoucherAPIView.as_view(), name='universal_vouchers_company'),
    path('ocr/extract/', OCRExtractAPIView.as_view(), name='ocr_extract'),
    path('sales-invoice/', CreateSalesInvoiceAPIView.as_view(), name='create_sales_invoice'),
    path('purchase-invoice/', CreatePurchaseInvoiceAPIView.as_view(), name='create_purchase_invoice'),
    path('payment-receipt/', CreatePaymentReceiptAPIView.as_view(), name='create_payment_receipt'),
    path('payment-receipts/<uuid:company_id>/', ListPaymentReceiptAPIView.as_view(), name='list_payment_receipts'),
    path('reports/trial-balance/<uuid:company_id>/', TrialBalanceAPIView.as_view(), name='trial_balance'),
    path('vouchers/detail/<uuid:voucher_id>/', VoucherDetailAPIView.as_view(), name='voucher_detail'),
    path('voucher-detail/<uuid:voucher_id>/', VoucherDetailAPIView.as_view(), name='voucher_detail_alias'),
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
]


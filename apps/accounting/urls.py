from django.urls import path
from .views import (
    CreateSalesInvoiceAPIView, CreatePurchaseInvoiceAPIView, TrialBalanceAPIView, 
    ListVouchersAPIView, VoucherDetailAPIView, LedgerStatementAPIView, 
    CreatePaymentReceiptAPIView, ListPaymentReceiptAPIView, UniversalVoucherAPIView
)
from .ocr_views import OCRExtractAPIView

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
]


# apps/payments/urls.py
from django.urls import path
from apps.payments import views

app_name = 'payments'

urlpatterns = [
    # Merchant configuration
    path('account/', views.MerchantAccountAPIView.as_view(), name='merchant_account'),

    # Beneficiary Discovery & Directory
    path('beneficiaries/', views.BeneficiaryListCreateAPIView.as_view(), name='beneficiary_list_create'),
    path('beneficiaries/discover/', views.BeneficiaryDiscoveryAPIView.as_view(), name='beneficiary_discover'),
    path('beneficiaries/<uuid:pk>/', views.BeneficiaryDetailAPIView.as_view(), name='beneficiary_detail'),
    path('beneficiaries/<uuid:pk>/favorite/', views.BeneficiaryToggleFavoriteAPIView.as_view(), name='beneficiary_toggle_favorite'),
    path('beneficiaries/<uuid:pk>/verify/', views.BeneficiaryVerifyAPIView.as_view(), name='beneficiary_verify'),

    # Payment Requests
    path('requests/', views.PaymentRequestListCreateAPIView.as_view(), name='payment_request_list_create'),
    path('requests/<uuid:pk>/', views.PaymentRequestDetailAPIView.as_view(), name='payment_request_detail'),
    path('requests/<uuid:pk>/verify/', views.PaymentVerifyStatusAPIView.as_view(), name='payment_verify'),
    path('requests/<uuid:pk>/confirm/', views.PaymentManualConfirmAPIView.as_view(), name='payment_confirm_manual'),

    # Suspense / Unmatched receipts
    path('unmatched/', views.UnmatchedPaymentListAPIView.as_view(), name='unmatched_payment_list'),
    path('unmatched/<uuid:pk>/resolve/', views.UnmatchedPaymentResolveAPIView.as_view(), name='unmatched_payment_resolve'),

    # Provider Webhooks
    path('webhooks/setu/', views.SetuWebhookAPIView.as_view(), name='setu_webhook'),
    path('webhooks/bank/', views.BankWebhookAPIView.as_view(), name='bank_webhook'),
]

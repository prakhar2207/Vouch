from django.urls import path
from apps.billing.views import (
    SubscriptionPlanListView,
    SubscriptionPlanDetailView,
    CompanySubscriptionView,
    CheckoutCreateOrderAPIView,
    CheckoutVerifyAPIView,
    CompanyPaymentsAPIView,
    CompanyInvoicesAPIView,
    InvoiceDownloadAPIView,
    CancelSubscriptionAPIView,
    RazorpayWebhookAPIView,
)

urlpatterns = [
    # Plans
    path('plans/', SubscriptionPlanListView.as_view(), name='billing-plans-list'),
    path('plans/<str:plan_id>/', SubscriptionPlanDetailView.as_view(), name='billing-plan-detail'),

    # Company Subscription & Entitlements
    path('subscription/', CompanySubscriptionView.as_view(), name='billing-subscription'),
    path('subscription/cancel/', CancelSubscriptionAPIView.as_view(), name='billing-subscription-cancel'),

    # Checkout & Verification
    path('checkout/create-order/', CheckoutCreateOrderAPIView.as_view(), name='billing-checkout-create-order'),
    path('checkout/verify/', CheckoutVerifyAPIView.as_view(), name='billing-checkout-verify'),

    # Payments & Invoices
    path('payments/', CompanyPaymentsAPIView.as_view(), name='billing-payments-list'),
    path('invoices/', CompanyInvoicesAPIView.as_view(), name='billing-invoices-list'),
    path('invoices/<uuid:invoice_id>/download/', InvoiceDownloadAPIView.as_view(), name='billing-invoice-download'),

    # Webhook
    path('webhooks/razorpay/', RazorpayWebhookAPIView.as_view(), name='billing-razorpay-webhook'),
]

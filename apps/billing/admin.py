from django.contrib import admin
from apps.billing.models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    BillingInvoice,
    WebhookEvent,
    DailyUsageTracker,
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'billing_interval', 'base_amount_rupees', 'tax_amount_rupees', 'total_amount_rupees', 'is_active', 'tier_order')
    list_filter = ('is_active', 'billing_interval')
    search_fields = ('id', 'name')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'company', 'plan', 'status', 'current_period_start', 'current_period_end', 'is_currently_active')
    list_filter = ('status', 'billing_interval')
    search_fields = ('company__name', 'company__id', 'plan__name', 'razorpay_subscription_id')
    raw_id_fields = ('company', 'user')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_number', 'company', 'amount_rupees', 'status', 'signature_verified', 'created_at')
    list_filter = ('status', 'signature_verified')
    search_fields = ('transaction_number', 'company__name', 'razorpay_order_id', 'razorpay_payment_id')
    raw_id_fields = ('company', 'user', 'subscription')


@admin.register(BillingInvoice)
class BillingInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'company', 'plan_name', 'total_amount_rupees', 'status', 'invoice_date')
    list_filter = ('status', 'invoice_date')
    search_fields = ('invoice_number', 'company__name', 'customer_name', 'customer_gstin')
    raw_id_fields = ('company', 'user', 'subscription', 'transaction')


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'signature_verified', 'processing_status', 'created_at')
    list_filter = ('processing_status', 'event_type', 'signature_verified')
    search_fields = ('event_id', 'event_type')


@admin.register(DailyUsageTracker)
class DailyUsageTrackerAdmin(admin.ModelAdmin):
    list_display = ('company', 'metric', 'date', 'count')
    list_filter = ('metric', 'date')
    search_fields = ('company__name', 'metric')
    raw_id_fields = ('company',)

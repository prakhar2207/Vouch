from rest_framework import serializers
from decimal import Decimal
from apps.billing.models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    BillingInvoice,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    base_amount_rupees = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    tax_amount_rupees = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_amount_rupees = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'name',
            'tagline',
            'description',
            'target_persona',
            'billing_interval',
            'base_amount_paise',
            'base_amount_rupees',
            'tax_rate',
            'tax_amount_paise',
            'tax_amount_rupees',
            'total_amount_paise',
            'total_amount_rupees',
            'currency',
            'tier_order',
            'features',
            'limits',
            'is_active',
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    is_currently_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id',
            'company_id',
            'company_name',
            'plan',
            'billing_interval',
            'status',
            'current_period_start',
            'current_period_end',
            'next_billing_at',
            'cancelled_at',
            'is_currently_active',
            'created_at',
        ]


class PaymentTransactionSerializer(serializers.ModelSerializer):
    amount_rupees = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id',
            'transaction_number',
            'razorpay_order_id',
            'razorpay_payment_id',
            'amount_paise',
            'amount_rupees',
            'currency',
            'status',
            'payment_method',
            'signature_verified',
            'failure_reason',
            'created_at',
        ]


class BillingInvoiceSerializer(serializers.ModelSerializer):
    taxable_amount_rupees = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    cgst_amount_rupees = serializers.SerializerMethodField()
    sgst_amount_rupees = serializers.SerializerMethodField()
    igst_amount_rupees = serializers.SerializerMethodField()
    total_amount_rupees = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = BillingInvoice
        fields = [
            'id',
            'invoice_number',
            'customer_name',
            'customer_email',
            'customer_address',
            'customer_gstin',
            'plan_name',
            'plan_description',
            'billing_period_start',
            'billing_period_end',
            'taxable_amount_paise',
            'taxable_amount_rupees',
            'cgst_amount_rupees',
            'sgst_amount_rupees',
            'igst_amount_rupees',
            'total_amount_paise',
            'total_amount_rupees',
            'currency',
            'status',
            'invoice_date',
            'pdf_path',
            'created_at',
        ]

    def get_cgst_amount_rupees(self, obj) -> Decimal:
        return Decimal(obj.cgst_amount_paise) / Decimal(100)

    def get_sgst_amount_rupees(self, obj) -> Decimal:
        return Decimal(obj.sgst_amount_paise) / Decimal(100)

    def get_igst_amount_rupees(self, obj) -> Decimal:
        return Decimal(obj.igst_amount_paise) / Decimal(100)


class CheckoutOrderRequestSerializer(serializers.Serializer):
    plan_id = serializers.CharField(max_length=50)
    company_id = serializers.UUIDField(required=False)


class CheckoutVerifyRequestSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=255)
    company_id = serializers.UUIDField(required=False)


class CancelSubscriptionRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    company_id = serializers.UUIDField(required=False)

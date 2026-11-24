# apps/payments/serializers.py
from decimal import Decimal
from rest_framework import serializers
from apps.payments.models import (
    MerchantPaymentAccount,
    PaymentRequest,
    PaymentRefund,
    UnmatchedPaymentRecord,
    Beneficiary
)
from apps.payments.constants import (
    PaymentMethod,
    PaymentProviderType,
    PaymentStatus,
    BeneficiaryType,
    VerificationStatus
)


class BeneficiarySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    masked_account_number = serializers.CharField(read_only=True)
    masked_mobile_number = serializers.CharField(read_only=True)
    linked_party_name = serializers.CharField(source='linked_party.name', read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            'id',
            'company',
            'company_name',
            'beneficiary_type',
            'name',
            'nickname',
            'mobile_number',
            'masked_mobile_number',
            'vpa',
            'account_number',
            'masked_account_number',
            'ifsc_code',
            'bank_name',
            'branch_name',
            'is_verified',
            'verification_status',
            'verified_name',
            'verification_source',
            'verification_timestamp',
            'is_favorite',
            'is_active',
            'linked_party',
            'linked_party_name',
            'last_paid_at',
            'total_payments_count',
            'total_paid_amount',
            'notes',
            'metadata',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'company',
            'is_verified',
            'verification_status',
            'verified_name',
            'verification_source',
            'verification_timestamp',
            'last_paid_at',
            'total_payments_count',
            'total_paid_amount',
            'created_at',
            'updated_at'
        ]


class BeneficiaryDiscoverySerializer(serializers.Serializer):
    discovery_mode = serializers.ChoiceField(choices=['MOBILE', 'VPA', 'QR', 'IFSC'])
    query = serializers.CharField(required=True, allow_blank=False)


class MerchantPaymentAccountSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    settlement_ledger_name = serializers.CharField(source='default_settlement_ledger.name', read_only=True)
    clearing_ledger_name = serializers.CharField(source='payment_clearing_ledger.name', read_only=True)
    gateway_charges_ledger_name = serializers.CharField(source='gateway_charges_ledger.name', read_only=True)

    class Meta:
        model = MerchantPaymentAccount
        fields = [
            'id',
            'company',
            'company_name',
            'merchant_id',
            'vpa',
            'is_onboarded',
            'onboarding_status',
            'default_settlement_ledger',
            'settlement_ledger_name',
            'payment_clearing_ledger',
            'clearing_ledger_name',
            'gateway_charges_ledger',
            'gateway_charges_ledger_name',
            'virtual_account_prefix',
            'virtual_account_ifsc',
            'auto_post_accounting',
            'metadata',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']


class PaymentRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices, default=PaymentMethod.UPI)
    beneficiary_id = serializers.UUIDField(required=False, allow_null=True)
    payer_party_id = serializers.UUIDField(required=False, allow_null=True)
    recipient_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    recipient_vpa = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    recipient_account_number = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)
    recipient_ifsc = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    recipient_company_id = serializers.UUIDField(required=False, allow_null=True)
    invoice_id = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class PaymentRequestDetailSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    recipient_company_name = serializers.CharField(source='recipient_company.name', read_only=True)
    payer_party_name = serializers.CharField(source='payer_party.name', read_only=True)
    recipient_party_name = serializers.CharField(source='recipient_party.name', read_only=True)
    payer_voucher_number = serializers.CharField(source='payer_voucher.voucher_number', read_only=True)
    recipient_voucher_number = serializers.CharField(source='recipient_voucher.voucher_number', read_only=True)
    invoice_number = serializers.CharField(source='invoice.voucher_number', read_only=True)

    class Meta:
        model = PaymentRequest
        fields = [
            'id',
            'srilekh_pay_id',
            'company',
            'company_name',
            'recipient_company',
            'recipient_company_name',
            'payer_party',
            'payer_party_name',
            'recipient_party',
            'recipient_party_name',
            'recipient_name',
            'recipient_vpa',
            'recipient_account_number',
            'recipient_ifsc',
            'invoice',
            'invoice_number',
            'amount',
            'currency',
            'payment_method',
            'provider',
            'provider_reference',
            'utr',
            'payer_vpa',
            'status',
            'settlement_status',
            'accounting_status',
            'gateway_fee',
            'net_settled_amount',
            'qr_data',
            'payment_url',
            'initiated_at',
            'confirmed_at',
            'settled_at',
            'payer_voucher',
            'payer_voucher_number',
            'recipient_voucher',
            'recipient_voucher_number',
            'idempotency_key',
            'notes',
            'metadata'
        ]
        read_only_fields = fields


class PaymentConfirmManualSerializer(serializers.Serializer):
    utr = serializers.CharField(max_length=100, required=True)
    payer_vpa = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class UnmatchedPaymentRecordSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    srilekh_pay_id = serializers.CharField(source='payment_request.srilekh_pay_id', read_only=True)
    resolved_voucher_number = serializers.CharField(source='resolved_voucher.voucher_number', read_only=True)

    class Meta:
        model = UnmatchedPaymentRecord
        fields = [
            'id',
            'company',
            'company_name',
            'payment_request',
            'srilekh_pay_id',
            'amount',
            'utr',
            'payer_identifier',
            'unmatched_reason',
            'is_resolved',
            'resolved_voucher',
            'resolved_voucher_number',
            'resolved_at',
            'created_at'
        ]
        read_only_fields = ['id', 'company', 'payment_request', 'created_at']


class ResolveUnmatchedPaymentSerializer(serializers.Serializer):
    customer_ledger_id = serializers.UUIDField(required=True)
    invoice_id = serializers.UUIDField(required=False, allow_null=True)

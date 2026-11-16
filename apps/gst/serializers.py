from rest_framework import serializers
from apps.companies.models import Company
from apps.gst.models import (
    CompanyGSTConfig,
    GSTRegistration,
    EWayBillRecord,
    EInvoiceRecord,
    GSTR2BImport,
    GSTR2BRecord,
    GSTFilingRecord,
    GSTAuditLog
)


class GSTRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for multi-state / multi-GSTIN enterprise entities.
    Credentials and session tokens are strictly masked on read.
    """
    has_portal_auth = serializers.SerializerMethodField()
    has_einvoice_auth = serializers.SerializerMethodField()
    has_eway_auth = serializers.SerializerMethodField()

    class Meta:
        model = GSTRegistration
        fields = [
            'id', 'company', 'gstin', 'legal_name', 'trade_name',
            'state_code', 'state_name', 'address', 'pincode',
            'taxpayer_type', 'status', 'registration_date', 'is_primary',
            'taxpayer_username', 'einvoice_username', 'eway_username',
            'has_portal_auth', 'has_einvoice_auth', 'has_eway_auth',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_has_portal_auth(self, obj) -> bool:
        return bool(obj.auth_token)

    def get_has_einvoice_auth(self, obj) -> bool:
        return bool(obj.einvoice_username and obj.einvoice_password)

    def get_has_eway_auth(self, obj) -> bool:
        return bool(obj.eway_username and obj.eway_password)


class GSTRegistrationWriteSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating GST registrations with encrypted credentials.
    """
    einvoice_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    eway_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = GSTRegistration
        fields = [
            'id', 'company', 'gstin', 'legal_name', 'trade_name',
            'state_code', 'state_name', 'address', 'pincode',
            'taxpayer_type', 'status', 'registration_date', 'is_primary',
            'taxpayer_username', 'einvoice_username', 'einvoice_password',
            'eway_username', 'eway_password'
        ]


class CompanyGSTConfigSerializer(serializers.ModelSerializer):
    """
    Serializer for Company GST & Sandbox Provider Configuration.
    API keys and secrets are never returned in plaintext.
    """
    is_configured = serializers.SerializerMethodField()
    api_key_masked = serializers.SerializerMethodField()
    sandbox_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = CompanyGSTConfig
        fields = [
            'id', 'company', 'provider', 'is_sandbox',
            'sandbox_base_url', 'is_configured',
            'api_key_masked', 'sandbox_key_masked',
            'eway_username', 'einvoice_username',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_is_configured(self, obj) -> bool:
        key = obj.sandbox_api_key or obj.api_key
        secret = obj.sandbox_api_secret or obj.api_secret
        return bool(key and secret)

    def get_api_key_masked(self, obj) -> str:
        if obj.api_key:
            return f"{obj.api_key[:4]}...{obj.api_key[-4:]}" if len(obj.api_key) > 8 else "***"
        return ""

    def get_sandbox_key_masked(self, obj) -> str:
        if obj.sandbox_api_key:
            return f"{obj.sandbox_api_key[:4]}...{obj.sandbox_api_key[-4:]}" if len(obj.sandbox_api_key) > 8 else "***"
        return ""


class EInvoiceRecordSerializer(serializers.ModelSerializer):
    voucher_number = serializers.CharField(source='voucher.voucher_number', read_only=True)
    voucher_date = serializers.DateField(source='voucher.voucher_date', read_only=True)
    total_amount = serializers.DecimalField(source='voucher.total_amount', max_digits=15, decimal_places=2, read_only=True)
    party_name = serializers.SerializerMethodField()

    class Meta:
        model = EInvoiceRecord
        fields = [
            'id', 'voucher', 'voucher_number', 'voucher_date',
            'total_amount', 'party_name', 'irn', 'ack_number',
            'ack_date', 'status', 'signed_qr_code', 'cancel_reason',
            'cancel_remarks', 'cancelled_at', 'created_at'
        ]

    def get_party_name(self, obj) -> str:
        v = obj.voucher
        if v.party_ledger:
            return v.party_ledger.name
        return v.buyer_name or "Counter Customer"


class EWayBillRecordSerializer(serializers.ModelSerializer):
    voucher_number = serializers.CharField(source='voucher.voucher_number', read_only=True)
    party_name = serializers.SerializerMethodField()

    class Meta:
        model = EWayBillRecord
        fields = [
            'id', 'voucher', 'voucher_number', 'party_name',
            'ewb_number', 'ewb_date', 'valid_until', 'status',
            'transport_mode', 'distance_km', 'transporter_id',
            'transporter_name', 'vehicle_number', 'vehicle_type',
            'cancel_reason', 'cancelled_at', 'created_at'
        ]

    def get_party_name(self, obj) -> str:
        v = obj.voucher
        if v.party_ledger:
            return v.party_ledger.name
        return v.buyer_name or "Customer"


class GSTR2BRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = GSTR2BRecord
        fields = [
            'id', 'supplier_gstin', 'supplier_name', 'invoice_number',
            'invoice_date', 'invoice_value', 'taxable_value',
            'igst_amount', 'cgst_amount', 'sgst_amount', 'cess_amount',
            'place_of_supply', 'itc_available', 'itc_ineligible_reason',
            'match_status', 'mismatch_details', 'is_reviewed',
            'reviewed_at', 'review_notes', 'created_at'
        ]


class GSTAuditLogSerializer(serializers.ModelSerializer):
    performed_by_email = serializers.EmailField(source='performed_by.email', read_only=True)

    class Meta:
        model = GSTAuditLog
        fields = [
            'id', 'action', 'correlation_id', 'endpoint',
            'http_method', 'status_code', 'is_success',
            'request_summary', 'response_summary', 'error_message',
            'performed_by_email', 'ip_address', 'created_at'
        ]

from django.contrib import admin
from .models import CompanyGSTConfig, EWayBillRecord, EInvoiceRecord, GSTTaxpayerCache

@admin.register(CompanyGSTConfig)
class CompanyGSTConfigAdmin(admin.ModelAdmin):
    list_display = ('company', 'provider', 'is_sandbox', 'updated_at')
    search_fields = ('company__name',)

@admin.register(EWayBillRecord)
class EWayBillRecordAdmin(admin.ModelAdmin):
    list_display = ('ewb_number', 'company', 'voucher', 'status', 'ewb_date', 'valid_until', 'vehicle_number')
    list_filter = ('status', 'transport_mode')
    search_fields = ('ewb_number', 'voucher__voucher_number', 'vehicle_number')

@admin.register(EInvoiceRecord)
class EInvoiceRecordAdmin(admin.ModelAdmin):
    list_display = ('irn', 'company', 'voucher', 'status', 'ack_number', 'ack_date')
    list_filter = ('status',)
    search_fields = ('irn', 'voucher__voucher_number', 'ack_number')

@admin.register(GSTTaxpayerCache)
class GSTTaxpayerCacheAdmin(admin.ModelAdmin):
    list_display = ('gstin', 'trade_name', 'legal_name', 'state_name', 'status', 'taxpayer_type', 'updated_at')
    search_fields = ('gstin', 'legal_name', 'trade_name')

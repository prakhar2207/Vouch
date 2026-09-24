from django.contrib import admin
from .models import FinancialYear, VoucherSequence, Voucher, VoucherItem, LedgerEntry
from .models_proforma import ProformaInvoice, ProformaItem

class VoucherItemInline(admin.TabularInline):
    model = VoucherItem
    extra = 0
    raw_id_fields = ('product',)

class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    raw_id_fields = ('ledger',)

@admin.register(FinancialYear)
class FinancialYearAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'start_date', 'end_date', 'is_closed')
    list_filter = ('is_closed',)
    search_fields = ('code', 'name', 'company__name')

@admin.register(VoucherSequence)
class VoucherSequenceAdmin(admin.ModelAdmin):
    list_display = ('company', 'financial_year', 'voucher_type', 'prefix', 'last_number')
    list_filter = ('voucher_type',)
    search_fields = ('company__name', 'prefix')

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ('voucher_number', 'company', 'voucher_type', 'voucher_date', 'party_ledger', 'buyer_name', 'total_amount', 'status')
    list_filter = ('voucher_type', 'status', 'voucher_date')
    search_fields = ('voucher_number', 'buyer_name', 'party_ledger__name', 'company__name', 'reference_number')
    raw_id_fields = ('company', 'party_ledger', 'financial_year', 'created_by')
    inlines = [VoucherItemInline, LedgerEntryInline]
    ordering = ('-voucher_date', '-created_at')

class ProformaItemInline(admin.TabularInline):
    model = ProformaItem
    extra = 0
    raw_id_fields = ('product',)

@admin.register(ProformaInvoice)
class ProformaInvoiceAdmin(admin.ModelAdmin):
    list_display = ('proforma_number', 'company', 'proforma_type', 'date', 'buyer_name', 'total_amount', 'status')
    list_filter = ('proforma_type', 'status', 'date')
    search_fields = ('proforma_number', 'buyer_name', 'company__name')
    raw_id_fields = ('company', 'party_ledger', 'financial_year', 'created_by')
    inlines = [ProformaItemInline]
    ordering = ('-date', '-created_at')

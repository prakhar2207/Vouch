from django.contrib import admin
from .models import LedgerGroup, Ledger

@admin.register(LedgerGroup)
class LedgerGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'nature', 'parent_group')
    list_filter = ('nature',)
    search_fields = ('name', 'company__name')

@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'group', 'ledger_type', 'gstin', 'state_code', 'phone')
    list_filter = ('ledger_type', 'group__nature')
    search_fields = ('name', 'gstin', 'company__name', 'phone')
    raw_id_fields = ('company', 'group')

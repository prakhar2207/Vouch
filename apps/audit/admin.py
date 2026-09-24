from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'model_name', 'record_id', 'user', 'company', 'created_at')
    list_filter = ('action', 'model_name', 'created_at')
    search_fields = ('model_name', 'record_id', 'user__email', 'company__name')
    readonly_fields = ('company', 'user', 'action', 'model_name', 'record_id', 'changes', 'ip_address', 'created_at')

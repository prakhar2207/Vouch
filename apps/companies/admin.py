from django.contrib import admin
from .models import Company, UserCompany, CompanySettings

class UserCompanyInline(admin.TabularInline):
    model = UserCompany
    extra = 1
    raw_id_fields = ('user',)

class CompanySettingsInline(admin.StackedInline):
    model = CompanySettings
    can_delete = False

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'gstin', 'pan', 'state_code', 'email', 'phone', 'is_active', 'created_at')
    list_filter = ('is_active', 'state_code')
    search_fields = ('name', 'gstin', 'pan', 'email', 'phone')
    ordering = ('-created_at',)
    inlines = [UserCompanyInline, CompanySettingsInline]

@admin.register(UserCompany)
class UserCompanyAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__email', 'company__name')
    raw_id_fields = ('user', 'company')

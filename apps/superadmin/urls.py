from django.urls import path
from .views import (
    SuperadminMetricsView,
    SuperadminCompaniesView,
    SuperadminCompanyToggleStatusView,
    SuperadminUsersView,
    SuperadminUserToggleStaffView,
    SuperadminUserToggleActiveView,
    SuperadminAuditLogsView,
    SuperadminImpersonateCompanyView
)

urlpatterns = [
    path('metrics/', SuperadminMetricsView.as_view(), name='superadmin_metrics'),
    path('companies/', SuperadminCompaniesView.as_view(), name='superadmin_companies'),
    path('companies/<uuid:pk>/toggle-status/', SuperadminCompanyToggleStatusView.as_view(), name='superadmin_company_toggle_status'),
    path('companies/<uuid:pk>/impersonate/', SuperadminImpersonateCompanyView.as_view(), name='superadmin_company_impersonate'),
    path('users/', SuperadminUsersView.as_view(), name='superadmin_users'),
    path('users/<uuid:pk>/toggle-staff/', SuperadminUserToggleStaffView.as_view(), name='superadmin_user_toggle_staff'),
    path('users/<uuid:pk>/toggle-active/', SuperadminUserToggleActiveView.as_view(), name='superadmin_user_toggle_active'),
    path('audit/', SuperadminAuditLogsView.as_view(), name='superadmin_audit_logs'),
]

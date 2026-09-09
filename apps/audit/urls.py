from django.urls import path
from .views import AuditLogListView

urlpatterns = [
    path('', AuditLogListView.as_view(), name='audit_log_list'),
    path('<uuid:company_id>/', AuditLogListView.as_view(), name='audit_log_list_company'),
]

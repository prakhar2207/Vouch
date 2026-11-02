from django.urls import path
from .views import AuditLogListView, AuditVerificationAPIView

urlpatterns = [
    path('verify/', AuditVerificationAPIView.as_view(), name='audit_verify'),
    path('verify/<uuid:company_id>/', AuditVerificationAPIView.as_view(), name='audit_verify_company'),
    path('', AuditLogListView.as_view(), name='audit_log_list'),
    path('<uuid:company_id>/', AuditLogListView.as_view(), name='audit_log_list_company'),
]

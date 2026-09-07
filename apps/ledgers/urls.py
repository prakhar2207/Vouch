from django.urls import path
from .views import LedgerListView, LedgerDetailView, PartyCleanupView, LedgerGroupListView
from apps.accounting.views import LedgerStatementAPIView

urlpatterns = [
    path('<uuid:company_id>/', LedgerListView.as_view(), name='ledger-list'),
    path('<uuid:company_id>/groups/', LedgerGroupListView.as_view(), name='ledger-groups'),
    path('<uuid:company_id>/cleanup-duplicates/', PartyCleanupView.as_view(), name='party-cleanup'),
    path('<uuid:company_id>/<uuid:ledger_id>/statement/', LedgerStatementAPIView.as_view(), name='ledger-statement'),
    path('<uuid:company_id>/<uuid:ledger_id>/', LedgerDetailView.as_view(), name='ledger-detail'),
]


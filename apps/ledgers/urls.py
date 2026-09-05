from django.urls import path
from .views import LedgerListView, LedgerDetailView, PartyCleanupView

urlpatterns = [
    path('<uuid:company_id>/', LedgerListView.as_view(), name='ledger-list'),
    path('<uuid:company_id>/cleanup-duplicates/', PartyCleanupView.as_view(), name='party-cleanup'),
    path('<uuid:company_id>/<uuid:ledger_id>/', LedgerDetailView.as_view(), name='ledger-detail'),
]


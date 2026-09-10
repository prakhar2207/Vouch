from django.urls import path
from .views import (
    LedgerListView, LedgerDetailView, LedgerGroupListView,
    PartyArchiveView, PartyMergePreviewView, PartyMergeExecuteView,
    PartyKhataView, PartyCleanupView
)
from apps.accounting.views import LedgerStatementAPIView

urlpatterns = [
    path('<uuid:company_id>/', LedgerListView.as_view(), name='ledger-list'),
    path('<uuid:company_id>/groups/', LedgerGroupListView.as_view(), name='ledger-groups'),
    path('<uuid:company_id>/merge-preview/', PartyMergePreviewView.as_view(), name='party-merge-preview'),
    path('<uuid:company_id>/merge-execute/', PartyMergeExecuteView.as_view(), name='party-merge-execute'),
    path('<uuid:company_id>/cleanup-duplicates/', PartyCleanupView.as_view(), name='party-cleanup'),
    path('<uuid:company_id>/<uuid:ledger_id>/archive/', PartyArchiveView.as_view(), name='party-archive'),
    path('<uuid:company_id>/<uuid:ledger_id>/khata/', PartyKhataView.as_view(), name='party-khata'),
    path('<uuid:company_id>/<uuid:ledger_id>/statement/', LedgerStatementAPIView.as_view(), name='ledger-statement'),
    path('<uuid:company_id>/<uuid:ledger_id>/', LedgerDetailView.as_view(), name='ledger-detail'),
]

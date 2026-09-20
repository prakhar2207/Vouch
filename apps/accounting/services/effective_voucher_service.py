from typing import Optional
from django.db.models import QuerySet, Q
from apps.accounting.models import Voucher, LedgerEntry

class EffectiveVoucherService:
    """
    Single source of truth for voucher effectiveness across Vouch ERP.
    Eliminates divergent status filtering across services, views, and reports.
    """
    
    ACTIVE_STATUSES = ('POSTED',)
    ACCOUNTING_STATUSES = ('POSTED', 'REVERSED', 'CORRECTED')
    INACTIVE_STATUSES = ('DRAFT', 'VALIDATING', 'CANCELLED', 'SUPERSEDED')

    @classmethod
    def is_active(cls, voucher: Voucher) -> bool:
        if not voucher:
            return False
        return voucher.status in cls.ACTIVE_STATUSES

    @classmethod
    def is_accounting_effective(cls, voucher: Voucher) -> bool:
        if not voucher:
            return False
        return voucher.status in cls.ACCOUNTING_STATUSES

    @classmethod
    def get_active_vouchers(cls, company=None, **filters) -> QuerySet:
        qs = Voucher.objects.filter(status__in=cls.ACTIVE_STATUSES).defer('attachment_data', 'attachment_mime')
        if company:
            qs = qs.filter(company=company)
        if filters:
            qs = qs.filter(**filters)
        return qs

    @classmethod
    def get_accounting_vouchers(cls, company=None, **filters) -> QuerySet:
        qs = Voucher.objects.filter(status__in=cls.ACCOUNTING_STATUSES).defer('attachment_data', 'attachment_mime')
        if company:
            qs = qs.filter(company=company)
        if filters:
            qs = qs.filter(**filters)
        return qs

    @classmethod
    def get_accounting_ledger_entries(cls, company=None, **filters) -> QuerySet:
        qs = LedgerEntry.objects.filter(
            voucher__status__in=cls.ACCOUNTING_STATUSES
        ).defer('voucher__attachment_data', 'voucher__attachment_mime')
        if company:
            qs = qs.filter(voucher__company=company)
        if filters:
            qs = qs.filter(**filters)
        return qs

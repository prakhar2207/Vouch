import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Company
from .services import CompanyBankService

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Company)
def handle_company_bank_sync(sender, instance, **kwargs):
    """
    Ensures any save of Company with bank details automatically guarantees
    the existence and synchronization of a Bank Ledger in Chart of Accounts.
    """
    if kwargs.get('raw'):
        return
    try:
        CompanyBankService.sync_company_bank_ledger(instance)
    except Exception as e:
        logger.error(f"Error auto-syncing bank ledger for company {instance.id}: {e}", exc_info=True)

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import Voucher, LedgerEntry, PaymentAllocation, BankTransaction, SyncEvent
from apps.ledgers.models import Ledger
from apps.inventory.models import Product

def log_sync_event(company_id, entity_type, entity_id, operation):
    if not company_id or not entity_id:
        return
    # Use on_commit if needed, but since we want the event ATOMICALLY committed, we just save it now.
    # If the transaction rolls back, this save rolls back too.
    SyncEvent.objects.create(
        company_id=company_id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation
    )

def get_company_id(instance):
    if hasattr(instance, 'company_id'):
        return instance.company_id
    if hasattr(instance, 'company'):
        return instance.company.id if instance.company else None
    return None

@receiver(post_save, sender=Voucher)
@receiver(post_save, sender=LedgerEntry)
@receiver(post_save, sender=PaymentAllocation)
@receiver(post_save, sender=BankTransaction)
@receiver(post_save, sender=Ledger)
@receiver(post_save, sender=Product)
def emit_sync_event_on_save(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    company_id = get_company_id(instance)
    operation = 'CREATE' if created else 'UPDATE'
    log_sync_event(company_id, sender.__name__.upper(), instance.id, operation)

@receiver(post_delete, sender=Voucher)
@receiver(post_delete, sender=LedgerEntry)
@receiver(post_delete, sender=PaymentAllocation)
@receiver(post_delete, sender=BankTransaction)
@receiver(post_delete, sender=Ledger)
@receiver(post_delete, sender=Product)
def emit_sync_event_on_delete(sender, instance, **kwargs):
    company_id = get_company_id(instance)
    log_sync_event(company_id, sender.__name__.upper(), instance.id, 'DELETE')

@receiver(post_delete, sender=Voucher)
def cleanup_voucher_inventory_entries(sender, instance, **kwargs):
    """
    Prevents orphaned InventoryEntry records from persisting when a Voucher is deleted.
    Protects product deletion and prevents phantom stock drift.
    """
    from apps.inventory.models import InventoryEntry
    InventoryEntry.objects.filter(voucher_id=instance.id).delete()


@receiver(post_save, sender=Voucher)
def invalidate_voucher_document_snapshot(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    try:
        from apps.documents.models import DocumentSnapshot
        from apps.documents.services.pdf_service import DocumentPDFService
        snaps = DocumentSnapshot.objects.filter(source_type='Voucher', source_id=str(instance.id))
        for snap in snaps:
            DocumentPDFService.invalidate_cache_for_snapshot(snap)
    except Exception:
        pass



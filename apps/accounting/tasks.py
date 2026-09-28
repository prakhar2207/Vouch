import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_invoice_notification_task(self, voucher_id: str):
    """
    Celery background worker task to render PDF and dispatch tax invoice
    notifications via email and WhatsApp payload generation asynchronously.
    Guarantees sub-second voucher save times by completely offloading PDF rendering
    and SMTP network communication to background workers.
    """
    from apps.accounting.models import Voucher
    from apps.accounting.services.invoice_notification_service import InvoiceNotificationService
    from apps.accounting.services.invoice_pdf_service import InvoicePDFService

    try:
        voucher = Voucher.objects.select_related('company', 'party_ledger').get(id=voucher_id)
        pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)
        success = InvoiceNotificationService.send_invoice_email(voucher, pdf_bytes=pdf_bytes)
        logger.info(f"[Celery] Invoice email dispatch result for {voucher.voucher_number}: {success}")
        return {
            "success": success,
            "voucher_id": str(voucher_id),
            "voucher_number": voucher.voucher_number
        }
    except Voucher.DoesNotExist:
        logger.warning(f"[Celery] Voucher ID {voucher_id} not found in database. Notification aborted.")
        return {"success": False, "error": "Voucher not found"}
    except Exception as exc:
        logger.exception(f"[Celery] Transient error dispatching invoice {voucher_id}: {exc}")
        raise self.retry(exc=exc)

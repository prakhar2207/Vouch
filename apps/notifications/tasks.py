import logging
from celery import shared_task
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_outbox_event_task(self, event_id: str):
    """
    Celery background worker task for asynchronous outbox event processing.
    Ensures that high-volume voucher postings are never blocked by PDF generation or email delivery.
    """
    from apps.notifications.outbox_service import OutboxService

    try:
        success = OutboxService.process_outbox_event(event_id)
        if not success:
            logger.warning(f"[Celery] Outbox processing reported failure for event {event_id}")
        return {"success": success, "event_id": event_id}
    except Exception as exc:
        logger.exception(f"[Celery] Unhandled exception processing outbox event {event_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task
def retry_pending_outbox_events_task():
    """
    Periodic maintenance task to sweep and retry any pending or delayed outbox events.
    Recovers from transient worker crashes or network interruptions.
    """
    from apps.notifications.models import TransactionalOutboxEvent
    from apps.notifications.outbox_service import OutboxService

    now = timezone.now()
    pending_events = TransactionalOutboxEvent.objects.filter(
        status='PENDING'
    ).filter(
        models.Q(next_retry_at__isnull=True) | models.Q(next_retry_at__lte=now)
    )[:50]

    count = 0
    for event in pending_events:
        OutboxService.dispatch_outbox_event_async(event.id)
        count += 1

    logger.info(f"Triggered async retry for {count} pending outbox events.")
    return count

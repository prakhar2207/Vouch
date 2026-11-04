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
    Periodic maintenance task to sweep and retry pending, retry-eligible, and abandoned outbox events.
    Worker Crash Recovery: Detects PROCESSING events with expired leases and safely resets them to RETRY_PENDING.
    """
    from datetime import timedelta
    from django.db import transaction
    from apps.notifications.models import TransactionalOutboxEvent
    from apps.notifications.outbox_service import OutboxService

    now = timezone.now()

    # 1. Crash recovery: Detect abandoned PROCESSING events whose leases have expired
    abandoned_events = TransactionalOutboxEvent.objects.filter(
        status='PROCESSING',
        lease_expires_at__lte=now
    )[:50]

    recovered = 0
    for ev in abandoned_events:
        with transaction.atomic():
            locked = (
                TransactionalOutboxEvent.objects
                .select_for_update()
                .filter(id=ev.id, status='PROCESSING', lease_expires_at__lte=now)
                .first()
            )
            if locked:
                locked.retry_count += 1
                locked.claim_token = None
                locked.lease_expires_at = None
                if locked.retry_count >= locked.max_retries:
                    locked.status = 'DEAD_LETTER'
                    locked.error_log = "Processing lease expired and maximum retries exceeded (suspected worker crash)."
                else:
                    locked.status = 'RETRY_PENDING'
                    locked.next_retry_at = now + timedelta(seconds=15)
                locked.save(update_fields=['status', 'retry_count', 'claim_token', 'lease_expires_at', 'error_log', 'next_retry_at'])
                recovered += 1

    if recovered > 0:
        logger.warning(f"Recovered {recovered} abandoned outbox event(s) with expired leases.")

    # 2. Dispatch eligible PENDING and RETRY_PENDING events
    eligible_events = TransactionalOutboxEvent.objects.filter(
        status__in=['PENDING', 'RETRY_PENDING']
    ).filter(
        models.Q(next_retry_at__isnull=True) | models.Q(next_retry_at__lte=now)
    )[:50]

    count = 0
    for event in eligible_events:
        OutboxService.dispatch_outbox_event_async(event.id)
        count += 1

    logger.info(f"Triggered async dispatch for {count} outbox events (recovered {recovered} abandoned).")
    return count

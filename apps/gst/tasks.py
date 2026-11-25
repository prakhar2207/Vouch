import logging
from celery import shared_task
from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='apps.gst.tasks.recover_itc_reconciliation_jobs_task',
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=150
)
def recover_itc_reconciliation_jobs_task(self, limit=50, lease_seconds=300):
    """
    Automated Celery Beat sweeper task for pending or expired ITC reconciliation jobs (Round 2.4.6 P1).
    Sweeps for jobs that were interrupted by process crashes or restarts,
    safely claims them using PostgreSQL row locks with lease exclusivity,
    and executes reconciliation without duplicating accounting effects.
    """
    logger.info("Initiating automated recovery sweep for pending/stale ITC reconciliation jobs...")
    try:
        recovered = ITCReconciliationJobService.recover_pending_jobs(
            limit=limit,
            lease_seconds=lease_seconds,
            worker_id=f"celery_sweeper_{self.request.id or 'auto'}"
        )
        logger.info(f"Automated recovery sweep completed: {len(recovered)} job(s) processed.")
        return {'status': 'SUCCESS', 'recovered_count': len(recovered)}
    except Exception as exc:
        logger.exception(f"Automated recovery sweep failed: {exc}")
        raise self.retry(exc=exc)

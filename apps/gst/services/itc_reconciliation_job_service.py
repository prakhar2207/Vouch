import logging
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class ITCReconciliationJobService:
    """
    Durable Reconciliation Recovery & Outbox Service (Round 2.4.5 P1).
    Provides concurrency-safe job execution, crash recovery, and state synchronization
    between asynchronous reconciliation work records and VoucherAttributionOperation payloads.
    """

    @classmethod
    def create_job(cls, company, registration, operation, operation_ref):
        """
        Creates an ITCReconciliationJob inside the voucher attribution transaction.
        Must be invoked within the same database transaction that commits the attribution.
        """
        from apps.gst.models import ITCReconciliationJob
        return ITCReconciliationJob.objects.create(
            company=company,
            gst_registration=registration,
            operation=operation,
            operation_ref=operation_ref,
            status='PENDING'
        )

    @classmethod
    def execute_job(cls, job_id):
        """
        Executes a reconciliation job safely with database-level row locking.
        Uses select_for_update(skip_locked=True) to guarantee that competing workers
        never process the same job concurrently.
        """
        from apps.gst.models import ITCReconciliationJob, VoucherAttributionOperation
        from apps.gst.services.itc_reconciliation_service import ITCReconciliationService

        # Phase 1: Atomically claim the job
        with transaction.atomic():
            job = ITCReconciliationJob.objects.select_for_update(skip_locked=True).filter(id=job_id).first()
            if not job:
                # Job is locked by another worker or does not exist
                logger.info(f"ITCReconciliationJob {job_id} is already claimed by another worker or does not exist.")
                return None

            if job.status == 'COMPLETED':
                return job

            if job.status == 'FAILED' and job.attempt_count >= job.max_attempts:
                return job

            job.status = 'PROCESSING'
            job.attempt_count += 1
            job.last_attempt_at = timezone.now()
            job.save(update_fields=['status', 'attempt_count', 'last_attempt_at', 'updated_at'])

        # Phase 2: Execute reconciliation (idempotent; no financial vouchers modified)
        try:
            summary = ITCReconciliationService.reconcile_period(job.company, registration=job.gst_registration)
            job.status = 'COMPLETED'
            job.summary_result = summary or {}
            job.completed_at = timezone.now()
            job.last_error = ''
            job.error_classification = ''
            job.save(update_fields=['status', 'summary_result', 'completed_at', 'last_error', 'error_classification', 'updated_at'])

            # Synchronize with VoucherAttributionOperation response payload
            if job.operation_id:
                op = VoucherAttributionOperation.objects.filter(id=job.operation_id).first()
                if op and op.response_payload:
                    cached = dict(op.response_payload)
                    cached['reconciliation_status'] = 'RECONCILED'
                    cached['reconciliation_summary'] = summary
                    cached['reconciliation_error'] = None
                    op.response_payload = cached
                    op.save(update_fields=['response_payload'])
            return job
        except Exception as e:
            logger.exception(f"ITCReconciliationJob {job.id} failed on attempt {job.attempt_count}: {e}")
            job.last_error = str(e)
            job.error_classification = type(e).__name__
            if job.attempt_count >= job.max_attempts:
                job.status = 'FAILED'
            else:
                job.status = 'PENDING'  # Retryable by background recovery
            job.save(update_fields=['status', 'last_error', 'error_classification', 'updated_at'])

            if job.operation_id:
                op = VoucherAttributionOperation.objects.filter(id=job.operation_id).first()
                if op and op.response_payload:
                    cached = dict(op.response_payload)
                    cached['reconciliation_status'] = 'RECONCILIATION_FAILED' if job.status == 'FAILED' else 'PENDING'
                    cached['reconciliation_error'] = str(e)
                    op.response_payload = cached
                    op.save(update_fields=['response_payload'])
            return job

    @classmethod
    def recover_pending_jobs(cls, company=None, limit=50, stale_minutes=5):
        """
        Sweeper and crash recovery mechanism.
        Recovers jobs left in PENDING or crashed PROCESSING state and executes them.
        """
        from apps.gst.models import ITCReconciliationJob

        qs = ITCReconciliationJob.objects.filter(status__in=['PENDING', 'PROCESSING'])
        if company:
            qs = qs.filter(company=company)

        # Reset stale jobs crashed during PROCESSING
        stale_threshold = timezone.now() - timedelta(minutes=stale_minutes)
        stale_jobs = qs.filter(status='PROCESSING', last_attempt_at__lt=stale_threshold)
        for stale in stale_jobs:
            stale.status = 'PENDING'
            stale.save(update_fields=['status'])

        recovered = []
        eligible_job_ids = list(
            qs.filter(status='PENDING', attempt_count__lt=models_max_attempts(qs))
            .values_list('id', flat=True)[:limit]
        )

        for job_id in eligible_job_ids:
            res = cls.execute_job(job_id)
            if res:
                recovered.append(res)
        return recovered

    @classmethod
    def retry_job(cls, job_id, reset_attempts=True):
        """
        Authorized administrative recovery path for inspectable and manual retry of failed jobs.
        """
        from apps.gst.models import ITCReconciliationJob
        job = ITCReconciliationJob.objects.filter(id=job_id).first()
        if not job:
            return None
        if reset_attempts:
            job.attempt_count = 0
        job.status = 'PENDING'
        job.last_error = ''
        job.error_classification = ''
        job.save(update_fields=['status', 'attempt_count', 'last_error', 'error_classification', 'updated_at'])
        return cls.execute_job(job.id)


def models_max_attempts(qs):
    return 3

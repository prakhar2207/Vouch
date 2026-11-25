import logging
import uuid
from datetime import timedelta
from django.db import transaction, models
from django.utils import timezone

logger = logging.getLogger(__name__)


class ITCReconciliationJobService:
    """
    Durable Reconciliation Recovery & Outbox Service (Round 2.4.5 & Round 2.4.6 P1).
    Provides concurrency-safe job execution with lease-based worker exclusivity,
    claim tokens, generation counters, stale-worker completion guards, and automated crash recovery.
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
    def execute_job(cls, job_id, worker_id='default', lease_seconds=300):
        """
        Executes a reconciliation job safely with database-level row locking and worker lease exclusivity.
        - Uses select_for_update(skip_locked=True) to prevent simultaneous lock contention.
        - Enforces active lease: if job is PROCESSING and claim_expires_at > now, another worker cannot claim it.
        - Generates a unique claim_token and increments generation on claim.
        - Guarded completion: verifies claim_token before persisting outcome so stale workers whose lease expired
          cannot overwrite a newer worker's results.
        """
        from apps.gst.models import ITCReconciliationJob, VoucherAttributionOperation
        from apps.gst.services.itc_reconciliation_service import ITCReconciliationService

        now = timezone.now()
        claim_token = uuid.uuid4().hex

        # Phase 1: Atomically claim the job
        with transaction.atomic():
            job = ITCReconciliationJob.objects.select_for_update(skip_locked=True).filter(id=job_id).first()
            if not job:
                logger.info(f"ITCReconciliationJob {job_id} is locked by another worker or does not exist.")
                return None

            if job.status == 'COMPLETED':
                return job

            if job.status == 'FAILED' and job.attempt_count >= job.max_attempts:
                return job

            # Active lease exclusivity check (Round 2.4.6 P1)
            if job.status == 'PROCESSING':
                if job.claim_expires_at and job.claim_expires_at > now:
                    logger.info(
                        f"ITCReconciliationJob {job_id} is actively claimed by worker '{job.claimed_by}' "
                        f"until {job.claim_expires_at}. Claim rejected for worker '{worker_id}'."
                    )
                    return None
                else:
                    logger.warning(
                        f"ITCReconciliationJob {job_id} lease expired for worker '{job.claimed_by}' at {job.claim_expires_at}. "
                        f"Recovering job for worker '{worker_id}'."
                    )

            job.status = 'PROCESSING'
            job.claimed_by = str(worker_id)
            job.claim_token = claim_token
            job.generation += 1
            job.attempt_count += 1
            job.last_attempt_at = now
            job.claim_expires_at = now + timedelta(seconds=lease_seconds)
            job.save(update_fields=[
                'status', 'claimed_by', 'claim_token', 'generation',
                'attempt_count', 'last_attempt_at', 'claim_expires_at', 'updated_at'
            ])

        # Phase 2: Execute reconciliation outside the lock (idempotent calculation)
        try:
            summary = ITCReconciliationService.reconcile_period(job.company, registration=job.gst_registration)
            completed_now = timezone.now()

            # Phase 3: Guarded completion - ensure claim_token is still valid and not superseded
            with transaction.atomic():
                claimed = ITCReconciliationJob.objects.select_for_update().filter(id=job.id, claim_token=claim_token).first()
                if not claimed:
                    logger.warning(
                        f"ITCReconciliationJob {job.id} lease expired or claim token was superseded during execution. "
                        f"Stale completion by worker '{worker_id}' aborted to prevent overwriting newer worker result."
                    )
                    return None

                claimed.status = 'COMPLETED'
                claimed.summary_result = summary or {}
                claimed.completed_at = completed_now
                claimed.last_error = ''
                claimed.error_classification = ''
                claimed.claim_expires_at = None
                claimed.save(update_fields=[
                    'status', 'summary_result', 'completed_at',
                    'last_error', 'error_classification', 'claim_expires_at', 'updated_at'
                ])

                # Synchronize with VoucherAttributionOperation response payload
                if claimed.operation_id:
                    op = VoucherAttributionOperation.objects.filter(id=claimed.operation_id).first()
                    if op and op.response_payload:
                        cached = dict(op.response_payload)
                        cached['reconciliation_status'] = 'RECONCILED'
                        cached['reconciliation_summary'] = summary
                        cached['reconciliation_error'] = None
                        op.response_payload = cached
                        op.save(update_fields=['response_payload'])
                return claimed

        except Exception as e:
            logger.exception(f"ITCReconciliationJob {job.id} failed on attempt {job.attempt_count} by worker '{worker_id}': {e}")
            with transaction.atomic():
                claimed = ITCReconciliationJob.objects.select_for_update().filter(id=job.id, claim_token=claim_token).first()
                if not claimed:
                    logger.warning(
                        f"ITCReconciliationJob {job.id} lease expired or superseded during exception handling for worker '{worker_id}'."
                    )
                    return None

                claimed.last_error = str(e)
                claimed.error_classification = type(e).__name__
                if claimed.attempt_count >= claimed.max_attempts:
                    claimed.status = 'FAILED'
                else:
                    claimed.status = 'PENDING'  # Retryable by background recovery
                claimed.claim_expires_at = None
                claimed.save(update_fields=[
                    'status', 'last_error', 'error_classification', 'claim_expires_at', 'updated_at'
                ])

                if claimed.operation_id:
                    op = VoucherAttributionOperation.objects.filter(id=claimed.operation_id).first()
                    if op and op.response_payload:
                        cached = dict(op.response_payload)
                        cached['reconciliation_status'] = 'RECONCILIATION_FAILED'
                        cached['reconciliation_error'] = str(e)
                        op.response_payload = cached
                        op.save(update_fields=['response_payload'])
                return claimed

    @classmethod
    def recover_pending_jobs(cls, company=None, limit=50, lease_seconds=300, worker_id='recovery_sweeper'):
        """
        Sweeper and crash recovery mechanism.
        Recovers jobs left in PENDING or crashed/expired PROCESSING state and executes them.
        """
        from apps.gst.models import ITCReconciliationJob

        now = timezone.now()
        qs = ITCReconciliationJob.objects.filter(
            models.Q(status='PENDING') |
            models.Q(status='PROCESSING', claim_expires_at__lt=now)
        ).exclude(status__in=['COMPLETED', 'FAILED'])

        if company:
            qs = qs.filter(company=company)

        eligible_job_ids = list(
            qs.filter(attempt_count__lt=models.F('max_attempts'))
            .order_by('created_at')
            .values_list('id', flat=True)[:limit]
        )

        recovered = []
        for job_id in eligible_job_ids:
            res = cls.execute_job(job_id, worker_id=worker_id, lease_seconds=lease_seconds)
            if res:
                recovered.append(res)
        return recovered

    @classmethod
    def retry_job(cls, job_id, reset_attempts=True, worker_id='admin_retry', lease_seconds=300):
        """
        Authorized administrative recovery path for inspectable and manual retry of failed jobs.
        """
        from apps.gst.models import ITCReconciliationJob
        with transaction.atomic():
            job = ITCReconciliationJob.objects.select_for_update().filter(id=job_id).first()
            if not job:
                return None
            if reset_attempts:
                job.attempt_count = 0
            job.status = 'PENDING'
            job.claim_token = ''
            job.claimed_by = ''
            job.claim_expires_at = None
            job.last_error = ''
            job.error_classification = ''
            job.save(update_fields=[
                'status', 'attempt_count', 'claim_token', 'claimed_by',
                'claim_expires_at', 'last_error', 'error_classification', 'updated_at'
            ])
        return cls.execute_job(job.id, worker_id=worker_id, lease_seconds=lease_seconds)

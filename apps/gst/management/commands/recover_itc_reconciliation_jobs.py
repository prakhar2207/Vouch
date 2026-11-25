from django.core.management.base import BaseCommand
from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService
from apps.companies.models import Company


class Command(BaseCommand):
    help = "Authorized recovery command for pending, stale, or failed ITC reconciliation jobs (Round 2.4.5 P1)."

    def add_arguments(self, parser):
        parser.add_argument('--company-id', type=str, help="Optional Company UUID filter.")
        parser.add_argument('--retry-job-id', type=str, help="Specific ITCReconciliationJob UUID to force retry.")
        parser.add_argument('--limit', type=int, default=50, help="Maximum jobs to process in this run.")

    def handle(self, *args, **options):
        retry_job_id = options.get('retry_job_id')
        if retry_job_id:
            self.stdout.write(f"Initiating authorized retry for ITCReconciliationJob {retry_job_id}...")
            job = ITCReconciliationJobService.retry_job(retry_job_id, reset_attempts=True)
            if job:
                self.stdout.write(self.style.SUCCESS(f"Job {job.id} processed successfully: status={job.status}"))
            else:
                self.stdout.write(self.style.ERROR(f"Job {retry_job_id} not found."))
            return

        company_id = options.get('company_id')
        company = None
        if company_id:
            try:
                company = Company.objects.get(id=company_id)
            except Company.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Company {company_id} does not exist."))
                return

        limit = options.get('limit', 50)
        self.stdout.write(f"Sweeping pending/stale reconciliation jobs (limit={limit})...")
        recovered = ITCReconciliationJobService.recover_pending_jobs(company=company, limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Recovery complete: {len(recovered)} job(s) processed."))

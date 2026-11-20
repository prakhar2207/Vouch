import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.notifications.tasks import retry_pending_outbox_events_task
from apps.notifications.models import TransactionalOutboxEvent

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Synchronously sweeps and processes pending, retry-eligible, and abandoned transactional outbox events."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of events to process in this run (default: 50)'
        )

    def handle(self, *args, **options):
        limit = options.get('limit', 50)
        self.stdout.write(f"[{timezone.now().isoformat()}] Starting synchronous outbox sweep (limit: {limit})...")

        pending_count = TransactionalOutboxEvent.objects.filter(status__in=['PENDING', 'RETRY_PENDING']).count()
        processing_count = TransactionalOutboxEvent.objects.filter(status='PROCESSING').count()

        self.stdout.write(f"  Existing Queue State: PENDING/RETRY={pending_count}, PROCESSING={processing_count}")

        # Run synchronous task
        try:
            retry_pending_outbox_events_task()
            self.stdout.write(self.style.SUCCESS(f"  [SUCCESS] Outbox sweep completed successfully."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"  [ERROR] Outbox sweep failed: {e}"))
            raise

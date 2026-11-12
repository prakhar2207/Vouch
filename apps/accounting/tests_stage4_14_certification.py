import datetime
import smtplib
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounting.models import FinancialYear, LedgerEntry, Voucher
from apps.companies.models import Company, UserCompany
from apps.companies.views import provision_company_defaults
from apps.ledgers.models import Ledger, LedgerGroup
from apps.notifications.models import EmailDeliveryLog, NotificationPreference, TransactionalOutboxEvent
from apps.notifications.outbox_service import OutboxService
from apps.notifications.tasks import process_outbox_event_task, retry_pending_outbox_events_task
from config.celery import app as celery_app


def _make_outbox_fixture(prefix: str, party_email: str = ""):
    user = User.objects.create_user(
        email=f"owner_{prefix}@s414.test", password="Password123!", role="OWNER", email_verified=True
    )
    company = Company.objects.create(name=f"Outbox S414 {prefix}", state_code="27")
    UserCompany.objects.create(user=user, company=company, role="OWNER")
    provision_company_defaults(company)
    NotificationPreference.objects.update_or_create(
        company=company, defaults={"send_invoice_email_on_post": True, "attach_invoice_pdf": False}
    )
    fy, _ = FinancialYear.objects.get_or_create(
        company=company,
        code="26-27",
        defaults={
            "name": "FY 26-27",
            "start_date": datetime.date(2026, 4, 1),
            "end_date": datetime.date(2027, 3, 31),
        },
    )
    grp_d = LedgerGroup.objects.get(company=company, name="Sundry Debtors")
    party = Ledger.objects.create(
        company=company, group=grp_d, name=f"Party {prefix}", ledger_type="CUSTOMER",
        email=party_email or None,
    )
    sales = Ledger.objects.get(company=company, ledger_type="SALES")
    voucher = Voucher.objects.create(
        company=company, financial_year=fy, voucher_type="SALES",
        voucher_number=f"INV-{prefix[:8]}", voucher_date=datetime.date(2026, 5, 1),
        party_ledger=party, status="POSTED", total_amount=Decimal("1180.00"), created_by=user,
    )
    LedgerEntry.objects.create(voucher=voucher, ledger=party, debit_amount=Decimal("1180.00"), credit_amount=Decimal("0.00"))
    LedgerEntry.objects.create(voucher=voucher, ledger=sales, debit_amount=Decimal("0.00"), credit_amount=Decimal("1180.00"))
    return company, user, party, sales, voucher


class Stage414CeleryConfigAndOutboxScenariosTests(TestCase):
    """Covers Stage 4.14 Sections 4 & 5: Celery config/autodiscovery + Outbox Scenarios 1-9."""

    def test_01_celery_autodiscovery_and_reliability_settings(self):
        celery_app.loader.import_default_modules()
        self.assertIn("apps.notifications.tasks.process_outbox_event_task", celery_app.tasks)
        self.assertIn("apps.notifications.tasks.retry_pending_outbox_events_task", celery_app.tasks)
        self.assertIn("apps.accounting.tasks.automated_nightly_backup_task", celery_app.tasks)
        self.assertIn("sweep-and-retry-outbox-notifications", settings.CELERY_BEAT_SCHEDULE)
        self.assertTrue(settings.CELERY_TASK_ACKS_LATE)
        self.assertTrue(settings.CELERY_TASK_REJECT_ON_WORKER_LOST)
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)

    def test_02_valid_recipient_and_duplicate_dispatch_idempotency(self):
        company, _, party, sales, voucher = _make_outbox_fixture("s1_valid", party_email="buyer@example.com")
        ev = OutboxService.create_invoice_outbox_event(voucher)
        self.assertIsNotNone(ev)

        calls = []

        def fake_send(**kwargs):
            calls.append(kwargs["idempotency_key"])
            log = EmailDeliveryLog.objects.create(
                company=company, recipient_email=kwargs["to_email"], subject="Inv",
                email_type="INVOICE_POSTED", status="SENT",
                idempotency_key=kwargs["idempotency_key"], sent_at=timezone.now(),
            )
            return True, log, None

        with patch("apps.notifications.outbox_service.EmailService.send_invoice_posted_email", side_effect=fake_send):
            res1 = process_outbox_event_task(str(ev.id))
            res2 = process_outbox_event_task(str(ev.id))  # Scenario 7: duplicate delivery task

        self.assertTrue(res1["success"])
        self.assertTrue(res2["success"])
        self.assertEqual(len(calls), 1)
        ev.refresh_from_db()
        self.assertEqual(ev.status, "PROCESSED")
        self.assertEqual(EmailDeliveryLog.objects.filter(company=company, status="SENT").count(), 1)
        # No accounting entries altered
        self.assertEqual(Voucher.objects.filter(company=company).count(), 1)
        self.assertEqual(LedgerEntry.objects.filter(voucher=voucher).count(), 2)

    def test_03_missing_recipient_skips_safely_preserving_voucher(self):
        company, _, _, _, voucher = _make_outbox_fixture("s2_noemail", party_email="")
        ev = OutboxService.create_invoice_outbox_event(voucher)
        res = process_outbox_event_task(str(ev.id))
        self.assertTrue(res["success"])
        ev.refresh_from_db()
        voucher.refresh_from_db()
        self.assertEqual(ev.status, "SKIPPED")
        self.assertEqual(voucher.status, "POSTED")
        self.assertEqual(EmailDeliveryLog.objects.filter(company=company, status="SKIPPED").count(), 1)

    def test_04_invalid_payload_transitions_to_dead_letter(self):
        company, _, _, _, _ = _make_outbox_fixture("s3_bad", party_email="")
        ev_bad_type = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id="bad",
            company=company, payload=["not-a-dict"], idempotency_key=f"bad_list_{uuid.uuid4()}", status="PENDING",
        )
        ev_missing_vch = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id=str(uuid.uuid4()),
            company=company, payload={"voucher_id": str(uuid.uuid4())}, idempotency_key=f"bad_vch_{uuid.uuid4()}", status="PENDING",
        )
        OutboxService.process_outbox_event(ev_bad_type.id)
        OutboxService.process_outbox_event(ev_missing_vch.id)
        ev_bad_type.refresh_from_db()
        ev_missing_vch.refresh_from_db()
        self.assertEqual(ev_bad_type.status, "DEAD_LETTER")
        self.assertEqual(ev_missing_vch.status, "DEAD_LETTER")

    def test_05_worker_interruption_active_lease_and_restart_expired_lease_recovery(self):
        company, _, _, _, voucher = _make_outbox_fixture("s4_5_6", party_email="buyer@example.com")
        # Scenario 4: Active unexpired lease -> suppressed
        ev_active = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id=str(voucher.id),
            company=company, payload={"voucher_id": str(voucher.id)}, idempotency_key=f"act_{uuid.uuid4()}",
            status="PROCESSING", claim_token="live_worker",
            lease_expires_at=timezone.now() + datetime.timedelta(minutes=5),
        )
        self.assertFalse(OutboxService.process_outbox_event(ev_active.id))

        # Scenario 6a: Expired lease where prior worker actually sent email -> advance to PROCESSED without resend
        sent_log = EmailDeliveryLog.objects.create(
            company=company, recipient_email="buyer@example.com", subject="Inv",
            email_type="INVOICE_POSTED", status="SENT", idempotency_key=f"exp_sent_{uuid.uuid4()}",
        )
        ev_exp_sent = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id=str(voucher.id),
            company=company, payload={"voucher_id": str(voucher.id)}, idempotency_key=sent_log.idempotency_key,
            email_delivery_log=sent_log, status="PROCESSING", claim_token="crashed_worker",
            lease_expires_at=timezone.now() - datetime.timedelta(minutes=5),
        )

        # Scenario 5: Expired lease with no email sent -> worker restart sweeper resets to RETRY_PENDING, then processes
        ev_exp_retry = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id=str(voucher.id),
            company=company, payload={"voucher_id": str(voucher.id)}, idempotency_key=f"exp_retry_{uuid.uuid4()}",
            status="PROCESSING", claim_token="crashed_worker_2",
            lease_expires_at=timezone.now() - datetime.timedelta(minutes=5),
        )

        # Scenario 6b: Expired lease with DELIVERY_UNKNOWN halts safely
        unk_log = EmailDeliveryLog.objects.create(
            company=company, recipient_email="buyer@example.com", subject="Inv",
            email_type="INVOICE_POSTED", status="DELIVERY_UNKNOWN", idempotency_key=f"exp_unk_{uuid.uuid4()}",
        )
        ev_unk = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id=str(voucher.id),
            company=company, payload={"voucher_id": str(voucher.id)}, idempotency_key=unk_log.idempotency_key,
            email_delivery_log=unk_log, status="PROCESSING", claim_token="crashed_worker_3",
            lease_expires_at=timezone.now() - datetime.timedelta(minutes=5),
        )

        retry_pending_outbox_events_task()
        ev_exp_sent.refresh_from_db()
        ev_exp_retry.refresh_from_db()
        ev_unk.refresh_from_db()
        self.assertEqual(ev_exp_sent.status, "PROCESSED")
        self.assertEqual(ev_exp_retry.status, "RETRY_PENDING")
        self.assertEqual(ev_unk.status, "DELIVERY_UNKNOWN")

    def test_06_temporary_failure_retries_and_recovers_while_permanent_dead_letters(self):
        company, _, _, _, voucher = _make_outbox_fixture("s8_9", party_email="retry@example.com")
        ev = OutboxService.create_invoice_outbox_event(voucher)
        attempt_counter = {"n": 0}

        def flaky_send(**kwargs):
            attempt_counter["n"] += 1
            if attempt_counter["n"] == 1:
                return False, None, "Transient 421 SMTP timeout"
            log = EmailDeliveryLog.objects.create(
                company=company, recipient_email=kwargs["to_email"], subject="Inv",
                email_type="INVOICE_POSTED", status="SENT",
                idempotency_key=kwargs["idempotency_key"], sent_at=timezone.now(),
            )
            return True, log, None

        with patch("apps.notifications.outbox_service.EmailService.send_invoice_posted_email", side_effect=flaky_send):
            first = OutboxService.process_outbox_event(ev.id)
            self.assertFalse(first)
            ev.refresh_from_db()
            self.assertEqual(ev.status, "RETRY_PENDING")
            self.assertEqual(ev.retry_count, 1)

            # Force eligibility & sweep again -> succeeds
            ev.next_retry_at = timezone.now() - datetime.timedelta(seconds=5)
            ev.save(update_fields=["next_retry_at"])
            with self.settings(SYNCHRONOUS_NOTIFICATIONS=True):
                retry_pending_outbox_events_task()

        ev.refresh_from_db()
        self.assertEqual(ev.status, "PROCESSED")
        self.assertEqual(attempt_counter["n"], 2)

        # Scenario 9: Permanent failure hits max_retries -> DEAD_LETTER
        ev_perm = TransactionalOutboxEvent.objects.create(
            event_type="INVOICE_POSTED", aggregate_type="Voucher", aggregate_id=str(voucher.id),
            company=company, payload={"voucher_id": str(voucher.id)}, idempotency_key=f"perm_{uuid.uuid4()}",
            status="PENDING", retry_count=2, max_retries=3,
        )
        with patch(
            "apps.notifications.outbox_service.EmailService.send_invoice_posted_email",
            side_effect=smtplib.SMTPException("550 Permanent Bounce"),
        ):
            res = OutboxService.process_outbox_event(ev_perm.id)
        self.assertFalse(res)
        ev_perm.refresh_from_db()
        self.assertEqual(ev_perm.status, "DEAD_LETTER")


class Stage414ConcurrentOutboxWorkerTests(TransactionTestCase):
    """Scenario 10: Concurrent worker threads processing the same PostgreSQL outbox event."""

    def test_concurrent_workers_send_exactly_once(self):
        company, _, _, _, voucher = _make_outbox_fixture("s10_conc", party_email="conc@example.com")
        ev = OutboxService.create_invoice_outbox_event(voucher)
        send_count = {"n": 0}

        def locked_send(**kwargs):
            send_count["n"] += 1
            log, _ = EmailDeliveryLog.objects.get_or_create(
                idempotency_key=kwargs["idempotency_key"],
                defaults={
                    "company": company, "recipient_email": kwargs["to_email"], "subject": "Inv",
                    "email_type": "INVOICE_POSTED", "status": "SENT", "sent_at": timezone.now(),
                },
            )
            return True, log, None

        def worker_fn(_):
            close_old_connections()
            try:
                return OutboxService.process_outbox_event(ev.id)
            finally:
                close_old_connections()

        with patch("apps.notifications.outbox_service.EmailService.send_invoice_posted_email", side_effect=locked_send):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(worker_fn, [1, 2]))

        ev.refresh_from_db()
        self.assertEqual(ev.status, "PROCESSED")
        self.assertEqual(send_count["n"], 1)
        self.assertEqual(EmailDeliveryLog.objects.filter(company=company, status="SENT").count(), 1)
        self.assertTrue(any(results))

import logging
import secrets
import threading
from datetime import timedelta
from typing import Optional, Union
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import Voucher
from apps.accounting.services.invoice_pdf_service import InvoicePDFService
from apps.notifications.email_service import EmailService
from apps.notifications.models import (
    TransactionalOutboxEvent,
    NotificationPreference,
    SecureInvoiceAccessToken,
    EmailDeliveryLog,
)

logger = logging.getLogger(__name__)


class OutboxService:
    """
    Transactional Outbox Service for SriLekh.
    Guarantees reliable, decoupled, idempotent delivery of business notifications.
    Outbox events are created within the same database transaction as the financial voucher,
    ensuring no notification is ever dispatched for an uncommitted or rolled-back transaction.
    """

    @classmethod
    def create_invoice_outbox_event(cls, voucher: Voucher) -> Optional[TransactionalOutboxEvent]:
        """
        Creates an outbox event for a posted sales invoice.
        Must be called within the voucher's posting transaction.
        """
        company = voucher.company

        # 1. Check Company Notification Preferences
        pref, _ = NotificationPreference.objects.get_or_create(company=company)
        if not pref.send_invoice_email_on_post:
            logger.info(f"Skipping outbox event for voucher {voucher.voucher_number}: send_invoice_email_on_post is disabled.")
            return None

        # 2. Stable Idempotency Key
        idempotency_key = f"inv_post_{company.id}_{voucher.id}_v{getattr(voucher, 'version', 1)}"

        # 3. Check for existing event to avoid duplicate insertion
        existing = TransactionalOutboxEvent.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

        payload = {
            'voucher_id': str(voucher.id),
            'voucher_number': voucher.voucher_number,
            'voucher_type': voucher.voucher_type,
            'company_id': str(company.id),
            'total_amount': str(voucher.total_amount),
        }

        event = TransactionalOutboxEvent.objects.create(
            event_type='INVOICE_POSTED',
            aggregate_type='Voucher',
            aggregate_id=str(voucher.id),
            company=company,
            payload=payload,
            idempotency_key=idempotency_key,
            status='PENDING',
        )
        return event

    @classmethod
    def process_outbox_event(cls, event_id: Union[str, UUID]) -> bool:
        """
        Processes a single TransactionalOutboxEvent with row-level locking.
        Resolves customer recipient email, generates secure view token, renders PDF, and dispatches email.
        """
        worker_id = secrets.token_urlsafe(16)
        now = timezone.now()
        lease_seconds = getattr(settings, 'OUTBOX_LEASE_SECONDS', 300)
        lease_expires_at = now + timedelta(seconds=lease_seconds)

        with transaction.atomic():
            event = (
                TransactionalOutboxEvent.objects
                .select_for_update()
                .filter(id=event_id)
                .first()
            )
            if not event:
                logger.warning(f"Outbox event {event_id} not found.")
                return False

            if event.status in ('PROCESSED', 'DEAD_LETTER', 'SKIPPED'):
                logger.info(f"Outbox event {event_id} already in terminal state {event.status}.")
                return True

            if event.status == 'PROCESSING':
                if event.lease_expires_at and event.lease_expires_at > now:
                    logger.info(f"Outbox event {event_id} actively claimed by worker until {event.lease_expires_at}. Suppressing duplicate.")
                    return True
                else:
                    logger.warning(f"Outbox event {event_id} lease expired ({event.lease_expires_at}). Taking over claim via worker {worker_id}.")

            event.status = 'PROCESSING'
            event.claimed_at = now
            event.claim_token = worker_id
            event.lease_expires_at = lease_expires_at
            event.save(update_fields=['status', 'claimed_at', 'claim_token', 'lease_expires_at'])

        # Outside the lock on the outbox row, execute the notification delivery
        try:
            if event.event_type == 'INVOICE_POSTED':
                success = cls._process_invoice_posted_event(event)
            else:
                logger.warning(f"Unhandled outbox event type: {event.event_type}")
                success = True

            with transaction.atomic():
                event = TransactionalOutboxEvent.objects.select_for_update().filter(id=event_id).first()
                if not event:
                    return False

                # Invariant: verify that this worker still holds the claim
                if event.claim_token != worker_id:
                    logger.warning(f"Worker {worker_id} lost claim on event {event_id} (current claim: {event.claim_token}). Aborting commit.")
                    return False

                event.claim_token = None
                event.lease_expires_at = None

                if event.status in ('SKIPPED', 'DEAD_LETTER'):
                    event.save(update_fields=['status', 'claim_token', 'lease_expires_at', 'error_log'])
                elif success:
                    event.status = 'PROCESSED'
                    event.processed_at = timezone.now()
                    event.save(update_fields=['status', 'processed_at', 'claim_token', 'lease_expires_at'])
                else:
                    event.retry_count += 1
                    if event.retry_count >= event.max_retries:
                        event.status = 'DEAD_LETTER'
                    else:
                        event.status = 'RETRY_PENDING'
                        # Exponential backoff: 30s, 60s, 120s...
                        event.next_retry_at = timezone.now() + timedelta(seconds=(2 ** event.retry_count) * 30)
                    event.save(update_fields=['status', 'retry_count', 'next_retry_at', 'claim_token', 'lease_expires_at', 'error_log'])
                return success

        except Exception as exc:
            logger.exception(f"Fatal error processing outbox event {event_id}: {exc}")
            with transaction.atomic():
                event = TransactionalOutboxEvent.objects.select_for_update().filter(id=event_id).first()
                if event and event.claim_token == worker_id:
                    event.retry_count += 1
                    event.error_log = str(exc)
                    event.claim_token = None
                    event.lease_expires_at = None
                    if event.retry_count >= event.max_retries:
                        event.status = 'DEAD_LETTER'
                    else:
                        event.status = 'RETRY_PENDING'
                        event.next_retry_at = timezone.now() + timedelta(seconds=(2 ** event.retry_count) * 30)
                    event.save(update_fields=['status', 'retry_count', 'error_log', 'next_retry_at', 'claim_token', 'lease_expires_at'])
            return False

    @classmethod
    def _process_invoice_posted_event(cls, event: TransactionalOutboxEvent) -> bool:
        """Internal worker logic for INVOICE_POSTED."""
        voucher_id = event.payload.get('voucher_id') or event.aggregate_id
        voucher = (
            Voucher.objects
            .select_related('company', 'party_ledger')
            .filter(id=voucher_id)
            .first()
        )

        if not voucher:
            logger.error(f"Voucher {voucher_id} referenced in outbox event {event.id} does not exist.")
            event.status = 'DEAD_LETTER'
            event.error_log = "Referenced voucher does not exist"
            event.save(update_fields=['status', 'error_log'])
            return False

        # Invariant: Only posted vouchers trigger email notifications
        if voucher.status != 'POSTED':
            logger.warning(f"Voucher {voucher.voucher_number} is not in POSTED status (status: {voucher.status}). Skipping.")
            event.status = 'SKIPPED'
            event.error_log = f"Voucher status is {voucher.status}, not POSTED"
            event.save(update_fields=['status', 'error_log'])
            return True

        company = voucher.company
        party = voucher.party_ledger

        # 1. Recipient email resolution
        recipient_email = (
            voucher.buyer_email or (party.email if party and party.email else '')
        )
        recipient_email = str(recipient_email).strip().lower()

        # Guard: Never send to seller's own email by mistake
        company_email = str(company.email or '').strip().lower()
        if recipient_email and company_email and recipient_email == company_email:
            logger.warning(f"Recipient email '{recipient_email}' matches seller company email. Skipping notification.")
            recipient_email = ''

        if not recipient_email or '@' not in recipient_email:
            logger.info(f"Skipping invoice email for {voucher.voucher_number}: No valid recipient email found.")
            event.status = 'SKIPPED'
            event.error_log = f"No recipient email found for party {party.name if party else 'Unknown'}"
            event.save(update_fields=['status', 'error_log'])

            EmailDeliveryLog.objects.create(
                company=company,
                recipient_email=recipient_email or 'unspecified@customer.local',
                sender_email=EmailService.get_default_from_email(),
                subject=f"New Invoice {voucher.voucher_number}",
                email_type='INVOICE_POSTED',
                status='SKIPPED',
                error_message="Skipped: No valid recipient customer email provided on voucher or party ledger.",
                idempotency_key=event.idempotency_key,
            )
            return True

        # 2. Notification Preferences check
        pref, _ = NotificationPreference.objects.get_or_create(company=company)
        attach_pdf = pref.attach_invoice_pdf

        # 3. Secure Invoice Access Token Generation (Mitigates IDOR)
        token_str = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(days=30)
        SecureInvoiceAccessToken.objects.create(
            voucher=voucher,
            token=token_str,
            expires_at=expires_at,
        )

        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://srilekh.com' if not settings.DEBUG else 'http://localhost:3000').rstrip('/')
        secure_view_url = f"{frontend_url}/invoices/view?token={token_str}"

        # 4. Generate PDF if preferred
        pdf_bytes = None
        pdf_filename = None
        if attach_pdf:
            try:
                pdf_bytes = InvoicePDFService.generate_invoice_pdf(voucher)
                clean_inv_no = str(voucher.voucher_number).replace('/', '_').replace('\\', '_').replace('-', '_')
                pdf_filename = f"Invoice_{clean_inv_no}.pdf"
            except Exception as e:
                logger.error(f"Failed to generate PDF for {voucher.voucher_number}: {e}")
                # We proceed with email sending even if PDF rendering fails; the customer has the secure viewing link!

        # 5. Calculate formatted amounts from items
        total_amt = f"{voucher.total_amount:,.2f}"
        items = list(voucher.items.all()) if hasattr(voucher, 'items') else []
        taxable_amt = sum(getattr(i, 'taxable_amount', 0) for i in items) if items else voucher.total_amount
        cgst_val = sum(getattr(i, 'cgst_amount', 0) for i in items) if items else 0
        sgst_val = sum(getattr(i, 'sgst_amount', 0) for i in items) if items else 0
        igst_val = sum(getattr(i, 'igst_amount', 0) for i in items) if items else 0
        taxable_str = f"{taxable_amt:,.2f}"
        cgst_str = f"{cgst_val:,.2f}" if cgst_val else None
        sgst_str = f"{sgst_val:,.2f}" if sgst_val else None
        igst_str = f"{igst_val:,.2f}" if igst_val else None

        inv_date_str = (
            voucher.voucher_date.strftime('%d-%b-%Y')
            if hasattr(voucher.voucher_date, 'strftime')
            else str(voucher.voucher_date or '')
        )
        due_date_str = (
            voucher.due_date.strftime('%d-%b-%Y')
            if getattr(voucher, 'due_date', None) and hasattr(voucher.due_date, 'strftime')
            else None
        )

        recipient_name = voucher.buyer_name or (party.name if party else 'Valued Customer')

        # 6. Dispatch Email via Centralized Service
        success, log, err = EmailService.send_invoice_posted_email(
            to_email=recipient_email,
            recipient_name=recipient_name,
            seller_name=company.name,
            invoice_number=voucher.voucher_number,
            invoice_date=inv_date_str,
            total_amount=total_amt,
            taxable_amount=taxable_str,
            cgst_amount=cgst_str,
            sgst_amount=sgst_str,
            igst_amount=igst_str,
            due_date=due_date_str,
            seller_gstin=company.gstin,
            recipient_gstin=voucher.buyer_gstin or (party.gstin if party else None),
            seller_address=company.address,
            seller_phone=company.phone,
            seller_email=company.email,
            secure_view_url=secure_view_url,
            pdf_content=pdf_bytes,
            pdf_filename=pdf_filename,
            idempotency_key=event.idempotency_key,
            company=company,
        )

        if not success:
            event.error_log = err or "Email delivery failed"
            event.save(update_fields=['error_log'])
            return False

        return True

    @classmethod
    def dispatch_outbox_event_async(cls, event_id: Union[str, UUID]):
        """
        Offloads outbox event processing asynchronously.
        In testing or synchronous notification mode, processes synchronously.
        In production/staging, dispatches to durable Celery worker.
        Daemon thread fallback is strictly removed in production to avoid orphaned jobs on process restart.
        If Celery broker is temporarily unavailable, the event remains durable in the database
        (status PENDING or RETRY_PENDING) and will be picked up by the periodic sweeper.
        """
        event_id_str = str(event_id)

        if getattr(settings, 'TESTING', False) or getattr(settings, 'SYNCHRONOUS_NOTIFICATIONS', False):
            cls.process_outbox_event(event_id_str)
            return

        try:
            from apps.notifications.tasks import process_outbox_event_task
            process_outbox_event_task.delay(event_id_str)
            logger.info(f"Dispatched outbox event {event_id_str} to Celery worker.")
        except Exception as e:
            logger.warning(
                f"Celery broker dispatch failed for outbox event {event_id_str}: {e}. "
                f"Event remains durably recorded in database and will be retried by the periodic sweeper."
            )

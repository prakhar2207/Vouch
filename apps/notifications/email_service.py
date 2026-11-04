import secrets
from datetime import timedelta
import logging
import uuid
from typing import Optional, Dict, Any, List, Tuple
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from apps.notifications.models import EmailDeliveryLog

logger = logging.getLogger(__name__)


class EmailService:
    """
    Centralized Transactional Email Service for SriLekh.
    All transactional emails originate from SriLekh <admin@srilekh.com> with reply-to support@srilekh.com.
    Guarantees idempotency, audit trail logging, non-blocking financial operations, and responsive HTML/text rendering.
    """

    @classmethod
    def get_default_from_email(cls) -> str:
        return getattr(settings, 'DEFAULT_FROM_EMAIL', 'SriLekh <admin@srilekh.com>')

    @classmethod
    def get_default_reply_to(cls) -> List[str]:
        reply_to = getattr(settings, 'EMAIL_REPLY_TO', 'support@srilekh.com')
        return [reply_to] if reply_to else []

    @classmethod
    def send_email(
        cls,
        to_email: str,
        subject: str,
        template_name: str,
        context: Dict[str, Any],
        email_type: str = 'SYSTEM_ALERT',
        idempotency_key: Optional[str] = None,
        attachments: Optional[List[Tuple[str, bytes, str]]] = None,
        company: Optional[Any] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """
        Core email delivery method.
        Returns: (success: bool, delivery_log: Optional[EmailDeliveryLog], error_or_message: Optional[str])
        """
        if not to_email or '@' not in to_email:
            logger.warning(f"Email delivery skipped: invalid recipient '{to_email}'")
            return False, None, "Invalid recipient email"

        sender = from_email or cls.get_default_from_email()
        reply_to_list = reply_to if reply_to is not None else cls.get_default_reply_to()

        worker_claim_token = secrets.token_urlsafe(16)
        now = timezone.now()
        claim_timeout = getattr(settings, 'EMAIL_SENDING_LEASE_SECONDS', 180)
        lease_expiry = now + timedelta(seconds=claim_timeout)

        # Sanitize metadata to avoid logging sensitive credentials
        sanitized_meta = {
            k: str(v) for k, v in context.items()
            if k not in ['otp_code', 'password', 'token', 'pdf_content', 'pdf_bytes']
        }

        from django.db import transaction
        log_entry = None

        if idempotency_key:
            with transaction.atomic():
                log_entry, created = (
                    EmailDeliveryLog.objects
                    .select_for_update()
                    .get_or_create(
                        idempotency_key=idempotency_key,
                        defaults={
                            'company': company,
                            'recipient_email': to_email,
                            'sender_email': sender,
                            'subject': subject,
                            'email_type': email_type,
                            'status': 'SENDING',
                            'claim_token': worker_claim_token,
                            'claim_expires_at': lease_expiry,
                            'attempts': 1,
                            'metadata': sanitized_meta,
                        }
                    )
                )
                if not created:
                    if log_entry.status in ('SENT', 'DELIVERY_ACCEPTED'):
                        logger.info(f"Email delivery skipped (idempotent duplicate): key={idempotency_key}")
                        return True, log_entry, "idempotent_duplicate"
                    elif log_entry.status == 'SENDING':
                        if log_entry.claim_expires_at and log_entry.claim_expires_at > now:
                            logger.info(f"Email delivery already in-flight for key={idempotency_key}. Suppressing duplicate.")
                            # Mandatory Invariant: active SENDING is NOT confirmed sent!
                            return False, log_entry, "in_flight_send"
                        else:
                            # In-flight lease expired without transition to SENT!
                            # Could the previous worker have completed delivery before crashing?
                            # Mark DELIVERY_UNKNOWN rather than blindly sending duplicate emails to customers
                            logger.warning(f"In-flight lease expired for key={idempotency_key}. Transitioning to DELIVERY_UNKNOWN.")
                            log_entry.status = 'DELIVERY_UNKNOWN'
                            log_entry.claim_token = None
                            log_entry.claim_expires_at = None
                            log_entry.reconciliation_notes = (
                                f"Worker lease expired while in SENDING status at {log_entry.claim_expires_at}. "
                                f"Marked DELIVERY_UNKNOWN to prevent duplicate customer emails pending reconciliation."
                            )
                            log_entry.save(update_fields=['status', 'claim_token', 'claim_expires_at', 'reconciliation_notes'])
                            return False, log_entry, "delivery_unknown_lease_expired"
                    elif log_entry.status == 'DELIVERY_UNKNOWN':
                        logger.warning(f"Email delivery log for key={idempotency_key} is in DELIVERY_UNKNOWN status. Blind retry suppressed.")
                        return False, log_entry, "delivery_unknown_suppressed"
                    elif log_entry.status == 'FAILED':
                        logger.warning(f"Email delivery log for key={idempotency_key} is permanently FAILED.")
                        return False, log_entry, "already_failed"

                    # For PENDING or RETRY_PENDING: claim the send slot
                    log_entry.status = 'SENDING'
                    log_entry.claim_token = worker_claim_token
                    log_entry.claim_expires_at = lease_expiry
                    log_entry.last_attempt_at = now
                    log_entry.attempts += 1
                    log_entry.save(update_fields=['status', 'claim_token', 'claim_expires_at', 'last_attempt_at', 'attempts'])
        else:
            log_entry = EmailDeliveryLog.objects.create(
                company=company,
                recipient_email=to_email,
                sender_email=sender,
                subject=subject,
                email_type=email_type,
                status='SENDING',
                claim_token=worker_claim_token,
                claim_expires_at=lease_expiry,
                attempts=1,
                metadata=sanitized_meta,
            )

        # Render HTML and Plain-Text templates
        try:
            html_content = render_to_string(f"emails/{template_name}.html", context)
        except Exception as e:
            logger.error(f"Failed to render HTML template emails/{template_name}.html: {str(e)}")
            html_content = None

        try:
            text_content = render_to_string(f"emails/{template_name}.txt", context)
        except Exception as e:
            logger.warning(f"Plain-text template emails/{template_name}.txt not found or failed: {str(e)}")
            text_content = html_content or ""

        client_msg_id = f"<{idempotency_key or secrets.token_hex(16)}@srilekh.com>"
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=sender,
                to=[to_email],
                reply_to=reply_to_list,
                headers={'Message-ID': client_msg_id, 'X-SriLekh-Idempotency': str(idempotency_key or '')}
            )

            if html_content:
                msg.attach_alternative(html_content, "text/html")

            if attachments:
                for att in attachments:
                    filename, content, mimetype = att
                    msg.attach(filename, content, mimetype)

            msg.send(fail_silently=False)

            with transaction.atomic():
                locked = EmailDeliveryLog.objects.select_for_update().filter(id=log_entry.id).first()
                if locked:
                    if idempotency_key and locked.claim_token != worker_claim_token:
                        logger.warning(f"Claim lost on email delivery log {log_entry.id} (worker {worker_claim_token} vs {locked.claim_token}).")
                        return False, locked, "claim_lost"

                    locked.status = 'SENT'
                    locked.sent_at = timezone.now()
                    locked.claim_token = None
                    locked.claim_expires_at = None
                    locked.provider_name = getattr(settings, 'EMAIL_BACKEND', 'SMTP').split('.')[-1]
                    locked.provider_message_id = client_msg_id
                    locked.save(update_fields=['status', 'sent_at', 'claim_token', 'claim_expires_at', 'provider_name', 'provider_message_id'])
                    return True, locked, None
            return True, log_entry, None

        except Exception as exc:
            err_msg = str(exc)
            is_timeout = any(term in err_msg.lower() for term in ['timed out', 'timeout', 'connection reset', 'econnreset'])
            logger.error(f"Email delivery exception to {to_email}: {err_msg} (is_timeout={is_timeout})")
            with transaction.atomic():
                locked = EmailDeliveryLog.objects.select_for_update().filter(id=log_entry.id).first()
                if locked:
                    locked.claim_token = None
                    locked.claim_expires_at = None
                    if is_timeout:
                        locked.status = 'DELIVERY_UNKNOWN'
                        locked.error_message = f"Ambiguous timeout: {err_msg[:400]}"
                        locked.reconciliation_notes = "Marked DELIVERY_UNKNOWN due to connection timeout/reset during transmission."
                    elif locked.attempts >= locked.max_attempts:
                        locked.status = 'FAILED'
                        locked.error_message = err_msg[:500]
                    else:
                        locked.status = 'RETRY_PENDING'
                        locked.error_message = err_msg[:500]
                    locked.save(update_fields=['status', 'claim_token', 'claim_expires_at', 'error_message', 'reconciliation_notes'])
                    return False, locked, ("timeout_ambiguous" if is_timeout else err_msg)
            return False, log_entry, err_msg

    # =========================================================================
    # High-level Workflow Helpers
    # =========================================================================

    @classmethod
    def send_registration_otp(cls, to_email: str, otp_code: str, idempotency_key: Optional[str] = None) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends single-use 6-digit registration OTP with 5-minute expiry and stable challenge idempotency."""
        subject = "Verify your email address — SriLekh"
        context = {
            'otp_code': otp_code,
            'subject': subject,
        }
        if not idempotency_key:
            import hashlib
            idempotency_key = f"reg_otp_{to_email}_{hashlib.sha256(otp_code.encode()).hexdigest()[:16]}"
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="registration_otp",
            context=context,
            email_type='REGISTRATION_OTP',
            idempotency_key=idempotency_key,
        )

    @classmethod
    def send_welcome_email(
        cls,
        to_email: str,
        company_name: str,
        user_name: Optional[str] = None,
        gstin: Optional[str] = None,
        state: Optional[str] = None,
        login_url: Optional[str] = None,
        company: Optional[Any] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends welcoming onboarding email after successful business registration."""
        subject = f"Welcome to SriLekh — Account Activated for {company_name}"
        context = {
            'subject': subject,
            'company_name': company_name,
            'user_name': user_name or "Partner",
            'gstin': gstin,
            'state': state,
            'login_url': login_url or f"{getattr(settings, 'FRONTEND_URL', 'https://srilekh.com')}/login",
        }
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="welcome",
            context=context,
            email_type='WELCOME',
            company=company,
        )

    @classmethod
    def send_password_reset_email(
        cls,
        to_email: str,
        reset_url: str,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends time-limited password reset link."""
        subject = "Reset Your Password — SriLekh"
        context = {
            'subject': subject,
            'email': to_email,
            'reset_url': reset_url,
        }
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="password_reset",
            context=context,
            email_type='PASSWORD_RESET',
        )

    @classmethod
    def send_password_changed_email(
        cls,
        to_email: str,
        timestamp: Optional[str] = None,
        login_url: Optional[str] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends confirmation that password was successfully altered."""
        subject = "Security Alert: Your Password Was Changed — SriLekh"
        if not timestamp:
            timestamp = timezone.now().strftime("%d %b %Y, %I:%M %p UTC")
        context = {
            'subject': subject,
            'email': to_email,
            'timestamp': timestamp,
            'login_url': login_url or f"{getattr(settings, 'FRONTEND_URL', 'https://srilekh.com')}/login",
        }
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="password_changed",
            context=context,
            email_type='PASSWORD_CHANGED',
        )

    @classmethod
    def send_invoice_posted_email(
        cls,
        to_email: str,
        recipient_name: str,
        seller_name: str,
        invoice_number: str,
        invoice_date: str,
        total_amount: str,
        taxable_amount: str,
        cgst_amount: Optional[str] = None,
        sgst_amount: Optional[str] = None,
        igst_amount: Optional[str] = None,
        due_date: Optional[str] = None,
        seller_gstin: Optional[str] = None,
        recipient_gstin: Optional[str] = None,
        seller_address: Optional[str] = None,
        seller_phone: Optional[str] = None,
        seller_email: Optional[str] = None,
        secure_view_url: Optional[str] = None,
        pdf_content: Optional[bytes] = None,
        pdf_filename: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        company: Optional[Any] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends official invoice notification with optional PDF attachment."""
        subject = f"New Invoice {invoice_number} issued to {recipient_name} — SriLekh"
        has_attachment = bool(pdf_content and pdf_filename)
        context = {
            'subject': subject,
            'recipient_name': recipient_name,
            'seller_name': seller_name,
            'invoice_number': invoice_number,
            'invoice_date': invoice_date,
            'due_date': due_date,
            'seller_gstin': seller_gstin,
            'recipient_gstin': recipient_gstin,
            'taxable_amount': taxable_amount,
            'cgst_amount': cgst_amount,
            'sgst_amount': sgst_amount,
            'igst_amount': igst_amount,
            'total_amount': total_amount,
            'seller_address': seller_address,
            'seller_phone': seller_phone,
            'seller_email': seller_email,
            'secure_view_url': secure_view_url,
            'has_attachment': has_attachment,
        }

        attachments = None
        if has_attachment:
            attachments = [(pdf_filename, pdf_content, 'application/pdf')]

        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="invoice_posted",
            context=context,
            email_type='INVOICE_POSTED',
            idempotency_key=idempotency_key,
            attachments=attachments,
            company=company,
        )

    @classmethod
    def send_revised_invoice_email(
        cls,
        to_email: str,
        seller_name: str,
        invoice_number: str,
        invoice_date: str,
        total_amount: str,
        seller_email: Optional[str] = None,
        secure_view_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        company: Optional[Any] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends amendment notification for revised invoices."""
        subject = f"Revised Tax Invoice {invoice_number} from {seller_name} — SriLekh"
        context = {
            'subject': subject,
            'seller_name': seller_name,
            'invoice_number': invoice_number,
            'invoice_date': invoice_date,
            'total_amount': total_amount,
            'seller_email': seller_email,
            'secure_view_url': secure_view_url,
        }
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="invoice_revised",
            context=context,
            email_type='INVOICE_REVISED',
            idempotency_key=idempotency_key,
            company=company,
        )

    @classmethod
    def send_payment_received_email(
        cls,
        to_email: str,
        recipient_name: str,
        seller_name: str,
        voucher_number: str,
        payment_date: str,
        amount: str,
        payment_mode: Optional[str] = None,
        reference_no: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        company: Optional[Any] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends payment receipt confirmation."""
        subject = f"Payment Receipt {voucher_number} from {seller_name} — SriLekh"
        context = {
            'subject': subject,
            'recipient_name': recipient_name,
            'seller_name': seller_name,
            'voucher_number': voucher_number,
            'payment_date': payment_date,
            'amount': amount,
            'payment_mode': payment_mode,
            'reference_no': reference_no,
        }
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="payment_received",
            context=context,
            email_type='PAYMENT_RECEIVED',
            idempotency_key=idempotency_key,
            company=company,
        )

    @classmethod
    def send_credit_note_email(
        cls,
        to_email: str,
        recipient_name: str,
        seller_name: str,
        note_number: str,
        note_date: str,
        amount: str,
        original_invoice_no: Optional[str] = None,
        reason: Optional[str] = None,
        secure_view_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        company: Optional[Any] = None,
    ) -> Tuple[bool, Optional[EmailDeliveryLog], Optional[str]]:
        """Sends credit note notification."""
        subject = f"Credit Note {note_number} from {seller_name} — SriLekh"
        context = {
            'subject': subject,
            'recipient_name': recipient_name,
            'seller_name': seller_name,
            'note_number': note_number,
            'note_date': note_date,
            'amount': amount,
            'original_invoice_no': original_invoice_no,
            'reason': reason,
            'secure_view_url': secure_view_url,
        }
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name="credit_note_issued",
            context=context,
            email_type='CREDIT_NOTE_ISSUED',
            idempotency_key=idempotency_key,
            company=company,
        )

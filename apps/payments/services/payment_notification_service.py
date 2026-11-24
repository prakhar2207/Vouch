# apps/payments/services/payment_notification_service.py
import logging
from django.utils import timezone
from apps.companies.models import UserCompany
from apps.notifications.models import Notification, PushSubscription, TransactionalOutboxEvent
from apps.accounts.models import User
from apps.payments.models import PaymentRequest

logger = logging.getLogger(__name__)


class PaymentNotificationService:
    """
    Delivers multi-channel real-time notifications for payment events:
      1. In-App Notification Feed (Bell icon in SriLekh top bar)
      2. Transactional Outbox Events (Reliable asynchronous dispatch)
      3. Mobile & PWA Push Notifications
    """

    @classmethod
    def _resolve_company_user(cls, company, preferred_user=None):
        if preferred_user:
            return preferred_user
        if not company:
            return None
        uc = UserCompany.objects.filter(company=company, role__in=['OWNER', 'ADMIN']).select_related('user').first()
        if uc and uc.user:
            return uc.user
        any_uc = UserCompany.objects.filter(company=company).select_related('user').first()
        if any_uc and any_uc.user:
            return any_uc.user
        return None

    @classmethod
    def notify_payment_success(cls, payment_request: PaymentRequest):
        """
        Dispatches dual notifications: to payer and to recipient.
        """
        payer_company = payment_request.company
        recipient_company = payment_request.recipient_company
        amount_fmt = f"₹{payment_request.amount:,.2f}"

        # ---------------------------------------------------------------------
        # 1. Payer Notification
        # ---------------------------------------------------------------------
        payer_title = f"Payment Successful: {amount_fmt}"
        payer_msg = (
            f"Your payment of {amount_fmt} to {payment_request.recipient_name} "
            f"via {payment_request.payment_method} has been verified. "
            f"UTR: {payment_request.utr or 'N/A'}. Double-entry voucher posted."
        )
        payer_link = f"/pay/{payment_request.id}"

        # Target initiating user or company admin
        payer_user = cls._resolve_company_user(payer_company, payment_request.created_by)
        if payer_user:
            Notification.objects.create(
                user=payer_user,
                title=payer_title,
                message=payer_msg,
                link=payer_link
            )

        # Register Payer Transactional Outbox Event
        payer_outbox_key = f"slp_{payment_request.srilekh_pay_id}_payer_{payer_company.id}"
        if not TransactionalOutboxEvent.objects.filter(idempotency_key=payer_outbox_key).exists():
            TransactionalOutboxEvent.objects.create(
                company=payer_company,
                aggregate_type='PaymentRequest',
                aggregate_id=payment_request.id,
                event_type='PAYMENT_OUTFLOW_CONFIRMED',
                idempotency_key=payer_outbox_key,
                payload={
                    "srilekh_pay_id": payment_request.srilekh_pay_id,
                    "amount": str(payment_request.amount),
                    "recipient_name": payment_request.recipient_name,
                    "payment_method": payment_request.payment_method,
                    "utr": payment_request.utr,
                    "voucher_number": payment_request.payer_voucher.voucher_number if payment_request.payer_voucher else None
                }
            )

        # ---------------------------------------------------------------------
        # 2. Recipient Notification (if SriLekh Platform Company)
        # ---------------------------------------------------------------------
        if recipient_company:
            recip_title = f"Payment Received: {amount_fmt}"
            recip_msg = (
                f"You received {amount_fmt} from {payer_company.name} "
                f"via {payment_request.payment_method}. UTR: {payment_request.utr or 'N/A'}."
            )
            recip_link = f"/pay/{payment_request.id}"

            recip_user = cls._resolve_company_user(recipient_company)
            if recip_user:
                Notification.objects.create(
                    user=recip_user,
                    title=recip_title,
                    message=recip_msg,
                    link=recip_link
                )

            recip_outbox_key = f"slp_{payment_request.srilekh_pay_id}_recipient_{recipient_company.id}"
            if not TransactionalOutboxEvent.objects.filter(idempotency_key=recip_outbox_key).exists():
                TransactionalOutboxEvent.objects.create(
                    company=recipient_company,
                    aggregate_type='PaymentRequest',
                    aggregate_id=payment_request.id,
                    event_type='PAYMENT_INFLOW_CONFIRMED',
                    idempotency_key=recip_outbox_key,
                    payload={
                        "srilekh_pay_id": payment_request.srilekh_pay_id,
                        "amount": str(payment_request.amount),
                        "payer_name": payer_company.name,
                        "payment_method": payment_request.payment_method,
                        "utr": payment_request.utr,
                        "voucher_number": payment_request.recipient_voucher.voucher_number if payment_request.recipient_voucher else None
                    }
                )

        logger.info("Dispatched payment confirmation notifications for %s", payment_request.srilekh_pay_id)

    @classmethod
    def notify_payment_failed(cls, payment_request: PaymentRequest, error_message: str = ""):
        """
        Notifies initiating user of payment failure.
        """
        amount_fmt = f"₹{payment_request.amount:,.2f}"
        title = f"Payment Failed: {amount_fmt}"
        msg = f"Payment of {amount_fmt} to {payment_request.recipient_name} could not be completed. {error_message}"
        link = f"/pay/{payment_request.id}"

        user = cls._resolve_company_user(payment_request.company, payment_request.created_by)
        if user:
            Notification.objects.create(
                user=user,
                title=title,
                message=msg,
                link=link
            )

# apps/payments/services/payment_orchestrator.py
import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher
from apps.payments.models import PaymentRequest, MerchantPaymentAccount
from apps.payments.constants import (
    PaymentStatus,
    PaymentMethod,
    PaymentProviderType,
    SettlementStatus,
    AccountingPostingStatus,
)
from apps.payments.providers import get_payment_provider
from apps.payments.services.payment_matching_service import PaymentMatchingService
from apps.payments.services.accounting_posting_service import AccountingPostingService

logger = logging.getLogger(__name__)


class PaymentOrchestrator:
    """
    Central orchestration engine for all SriLekh Pay operations.
    Coordinates payment initiation, provider dispatch, cross-company matching,
    idempotency protection, and automated double-entry accounting execution.
    """

    @classmethod
    def generate_srilekh_pay_id(cls) -> str:
        """Generates a human-friendly traceable reference ID e.g. SLP-202611-A8F29"""
        now = timezone.now()
        prefix = f"SLP-{now.strftime('%Y%m')}"
        random_suffix = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{random_suffix}"

    @classmethod
    @transaction.atomic
    def initiate_payment(
        cls,
        company: Company,
        amount: Decimal,
        payment_method: str = PaymentMethod.UPI,
        beneficiary=None,
        payer_party: Optional[Ledger] = None,
        recipient_name: str = "",
        recipient_vpa: Optional[str] = None,
        recipient_account_number: Optional[str] = None,
        recipient_ifsc: Optional[str] = None,
        recipient_company: Optional[Company] = None,
        invoice: Optional[Voucher] = None,
        idempotency_key: Optional[str] = None,
        notes: str = "",
        user=None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentRequest:
        """
        Creates, configures, and registers an outbound or inbound payment request with the provider.
        """
        if amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be strictly greater than 0.00")

        # Prefill from beneficiary directory if provided
        if beneficiary:
            if not recipient_name:
                recipient_name = beneficiary.name
            if not recipient_vpa and beneficiary.vpa:
                recipient_vpa = beneficiary.vpa
            if not recipient_account_number and beneficiary.account_number:
                recipient_account_number = beneficiary.account_number
            if not recipient_ifsc and beneficiary.ifsc_code:
                recipient_ifsc = beneficiary.ifsc_code
            if not payer_party and beneficiary.linked_party:
                payer_party = beneficiary.linked_party

        # Idempotency check: if key already exists, return existing record
        if idempotency_key:
            existing = PaymentRequest.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing:
                logger.info("Idempotent hit for payment key %s -> %s", idempotency_key, existing.srilekh_pay_id)
                return existing

        # Select provider based on payment method
        if payment_method in [PaymentMethod.UPI]:
            provider_type = PaymentProviderType.SETU
        else:
            provider_type = PaymentProviderType.BANK_TRANSFER

        provider = get_payment_provider(provider_type)

        # Cross-company tenant matching
        target_recipient_company = recipient_company
        if not target_recipient_company and (recipient_vpa or recipient_name):
            target_recipient_company = PaymentMatchingService.match_recipient_company(recipient_vpa or recipient_name)

        recipient_party = None
        if target_recipient_company:
            recipient_party = PaymentMatchingService.match_customer_ledger(target_recipient_company, company)

        srilekh_pay_id = cls.generate_srilekh_pay_id()

        pr = PaymentRequest.objects.create(
            srilekh_pay_id=srilekh_pay_id,
            company=company,
            beneficiary=beneficiary,
            payer_party=payer_party,
            recipient_company=target_recipient_company,
            recipient_party=recipient_party,
            recipient_name=recipient_name or (target_recipient_company.name if target_recipient_company else "Supplier"),
            recipient_vpa=recipient_vpa,
            recipient_account_number=recipient_account_number,
            recipient_ifsc=recipient_ifsc,
            invoice=invoice,
            amount=amount,
            payment_method=payment_method,
            provider=provider_type,
            status=PaymentStatus.INITIATED,
            settlement_status=SettlementStatus.PENDING,
            accounting_status=AccountingPostingStatus.PENDING,
            idempotency_key=idempotency_key,
            notes=notes,
            created_by=user,
            metadata=metadata or {}
        )

        # Call provider adapter to generate dynamic QR / links / VAN instructions
        try:
            prov_res = provider.create_payment_request(pr)
            pr.provider_reference = prov_res.get('provider_reference')
            pr.qr_data = prov_res.get('qr_data')
            pr.payment_url = prov_res.get('payment_url')
            pr.metadata['provider_init_response'] = prov_res.get('raw_response', {})
            pr.save(update_fields=['provider_reference', 'qr_data', 'payment_url', 'metadata'])
        except Exception as e:
            logger.error("Provider initialization error for %s: %s", pr.srilekh_pay_id, e)
            pr.status = PaymentStatus.FAILED
            pr.metadata['provider_init_error'] = str(e)
            pr.save(update_fields=['status', 'metadata'])
            raise ValidationError(f"Payment provider initialization failed: {str(e)}")

        logger.info("Payment %s initiated successfully via %s", pr.srilekh_pay_id, provider_type)
        return pr

    @classmethod
    @transaction.atomic
    def confirm_payment_success(
        cls,
        payment_request: PaymentRequest,
        utr: Optional[str] = None,
        payer_vpa: Optional[str] = None,
        raw_response: Optional[Dict[str, Any]] = None,
        user=None
    ) -> PaymentRequest:
        """
        Idempotently marks a payment as successful and posts double-entry vouchers.
        """
        pr = PaymentRequest.objects.select_for_update().get(id=payment_request.id)

        if pr.status == PaymentStatus.SUCCESS and pr.accounting_status in [AccountingPostingStatus.POSTED, AccountingPostingStatus.PAYER_ONLY]:
            logger.info("Payment %s already marked SUCCESS and posted.", pr.srilekh_pay_id)
            return pr

        pr.status = PaymentStatus.SUCCESS
        pr.confirmed_at = timezone.now()
        if utr:
            pr.utr = utr
        if payer_vpa:
            pr.payer_vpa = payer_vpa
        if raw_response:
            pr.metadata['confirmation_payload'] = raw_response

        pr.save(update_fields=['status', 'confirmed_at', 'utr', 'payer_vpa', 'metadata'])

        # Update beneficiary statistics if linked
        if pr.beneficiary:
            pr.beneficiary.last_paid_at = pr.confirmed_at
            pr.beneficiary.total_payments_count += 1
            pr.beneficiary.total_paid_amount += pr.amount
            pr.beneficiary.save(update_fields=['last_paid_at', 'total_payments_count', 'total_paid_amount'])

        # Auto-post double-entry accounting
        posted_pr = AccountingPostingService.post_payment_accounting(pr, user=user)

        # Dispatch real-time Web, In-App and PWA Push notifications
        try:
            with transaction.atomic():
                from apps.payments.services.payment_notification_service import PaymentNotificationService
                PaymentNotificationService.notify_payment_success(posted_pr)
        except Exception as notif_err:
            logger.warning("Notification dispatch non-critical warning for %s: %s", pr.srilekh_pay_id, notif_err)

        return posted_pr

    @classmethod
    @transaction.atomic
    def mark_payment_failed(cls, payment_request: PaymentRequest, error_message: str = "") -> PaymentRequest:
        """
        Marks payment as failed and dispatches failure notification.
        """
        pr = PaymentRequest.objects.select_for_update().get(id=payment_request.id)
        pr.status = PaymentStatus.FAILED
        pr.metadata['failure_reason'] = error_message
        pr.save(update_fields=['status', 'metadata'])

        try:
            from apps.payments.services.payment_notification_service import PaymentNotificationService
            PaymentNotificationService.notify_payment_failed(pr, error_message)
        except Exception as notif_err:
            logger.warning("Notification dispatch non-critical warning for %s: %s", pr.srilekh_pay_id, notif_err)

        return pr

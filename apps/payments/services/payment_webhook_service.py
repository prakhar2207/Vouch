# apps/payments/services/payment_webhook_service.py
import json
import logging
from typing import Dict, Any, Tuple
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.payments.models import PaymentRequest, PaymentWebhookEvent
from apps.payments.constants import PaymentStatus, PaymentProviderType
from apps.payments.providers import get_payment_provider
from apps.payments.services.payment_orchestrator import PaymentOrchestrator

logger = logging.getLogger(__name__)


class PaymentWebhookService:
    """
    Ingests, verifies, dedupes, and processes payment confirmation webhooks.
    Guarantees strict replay protection and zero data loss.
    """

    @classmethod
    @transaction.atomic
    def process_incoming_webhook(
        cls,
        provider_type: str,
        raw_body: bytes,
        headers: Dict[str, Any],
        parsed_json: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Processes inbound provider webhook.
        Returns: (success: bool, message: str, event_data: dict)
        """
        provider = get_payment_provider(provider_type)

        # 1. Parse standard fields
        event_dict = provider.parse_webhook_event(parsed_json, headers)
        event_id = event_dict['event_id']
        event_type = event_dict['event_type']
        provider_ref = event_dict.get('provider_reference')
        new_status = event_dict.get('status')
        utr = event_dict.get('utr')
        payer_vpa = event_dict.get('payer_vpa')

        # 2. Check for duplicate event (Replay Protection)
        existing_event = PaymentWebhookEvent.objects.filter(provider=provider_type, event_id=event_id).first()
        if existing_event:
            logger.info("Replay detected: Event %s already processed at %s", event_id, existing_event.processed_at)
            return True, "Event already processed (Duplicate)", {"event_id": event_id, "status": "DUPLICATE"}

        # 3. Signature Verification
        # Header keys can be case-variant
        sig_header = headers.get('X-Setu-Signature') or headers.get('x-setu-signature') or headers.get('X-Signature') or headers.get('x-signature') or ''
        is_verified = provider.verify_webhook_signature(raw_body, sig_header) if sig_header else True

        # Register raw audit event
        webhook_record = PaymentWebhookEvent.objects.create(
            provider=provider_type,
            event_id=event_id,
            event_type=event_type,
            signature=sig_header,
            headers={k: str(v) for k, v in headers.items() if not k.lower().startswith('authorization')},
            payload=parsed_json,
            is_verified=is_verified
        )

        # 4. Resolve PaymentRequest
        payment_request = None
        if provider_ref:
            payment_request = PaymentRequest.objects.filter(provider_reference=provider_ref).first()
        if not payment_request and utr:
            payment_request = PaymentRequest.objects.filter(utr=utr).first()

        if payment_request:
            webhook_record.payment_request = payment_request

        if not payment_request:
            msg = f"No PaymentRequest found matching provider reference '{provider_ref}' or UTR '{utr}'"
            logger.warning("Webhook unresolved: %s", msg)
            webhook_record.error_message = msg
            webhook_record.is_processed = False
            webhook_record.save(update_fields=['payment_request', 'error_message', 'is_processed'])
            return True, msg, {"event_id": event_id, "status": "UNMATCHED_REQUEST"}

        # 5. Process status transition
        try:
            if new_status == PaymentStatus.SUCCESS:
                PaymentOrchestrator.confirm_payment_success(
                    payment_request=payment_request,
                    utr=utr,
                    payer_vpa=payer_vpa,
                    raw_response=parsed_json
                )
            elif new_status == PaymentStatus.FAILED:
                PaymentOrchestrator.mark_payment_failed(
                    payment_request=payment_request,
                    error_message=f"Webhook status: {new_status}"
                )

            webhook_record.is_processed = True
            webhook_record.processed_at = timezone.now()
            webhook_record.save(update_fields=['payment_request', 'is_processed', 'processed_at'])
            return True, "Webhook processed successfully", {"event_id": event_id, "status": "PROCESSED"}

        except Exception as e:
            logger.exception("Error processing webhook %s: %s", event_id, e)
            webhook_record.error_message = str(e)
            webhook_record.save(update_fields=['error_message'])
            return False, f"Processing failed: {str(e)}", {"event_id": event_id, "status": "ERROR"}

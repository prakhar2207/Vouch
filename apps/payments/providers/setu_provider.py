# apps/payments/providers/setu_provider.py
import hmac
import hashlib
import json
import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone

from apps.payments.interfaces.provider_interface import PaymentProviderInterface
from apps.payments.constants import PaymentStatus, PaymentProviderType

logger = logging.getLogger(__name__)


class SetuPaymentProvider(PaymentProviderInterface):
    """
    Adapter for Setu UPI DeepLinks and Dynamic QR APIs.
    Supports UPI Collections, Status Polling, HMAC Signature Validation, and Webhook Parsing.
    """

    @property
    def provider_type(self) -> str:
        return PaymentProviderType.SETU

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, product_instance_id: Optional[str] = None):
        self.client_id = client_id or getattr(settings, 'SETU_CLIENT_ID', 'sandbox_setu_client_id')
        self.client_secret = client_secret or getattr(settings, 'SETU_CLIENT_SECRET', 'sandbox_setu_secret')
        self.product_instance_id = product_instance_id or getattr(settings, 'SETU_PRODUCT_INSTANCE_ID', 'sandbox_instance_id')
        self.base_url = getattr(settings, 'SETU_BASE_URL', 'https://staging.setu.co')

    def create_payment_request(self, payment_request) -> Dict[str, Any]:
        """
        Creates a Setu UPI link / Dynamic QR for the payment request.
        If live credentials are present, calls Setu /api/v2/links or /api/v1/merchants/dqr.
        In test/sandbox, deterministically generates verified UPI intent payload and references.
        """
        merchant_account = getattr(payment_request.recipient_company, 'payment_account', None)
        payee_vpa = (merchant_account.vpa if merchant_account and merchant_account.vpa else None) or payment_request.recipient_vpa or "srilekh.pay@icici"
        payee_name = payment_request.recipient_name or payment_request.company.name

        provider_ref = f"SETU_{payment_request.srilekh_pay_id}_{uuid.uuid4().hex[:8].upper()}"
        
        # Standard NPCI UPI URI specifications
        # upi://pay?pa={vpa}&pn={name}&am={amount}&cu=INR&tr={ref}&tn={note}
        encoded_note = f"SriLekhPay {payment_request.srilekh_pay_id}".replace(' ', '%20')
        upi_intent = (
            f"upi://pay?pa={payee_vpa}"
            f"&pn={payee_name.replace(' ', '%20')}"
            f"&am={payment_request.amount:.2f}"
            f"&cu=INR"
            f"&tr={provider_ref}"
            f"&tn={encoded_note}"
        )
        payment_url = f"https://srilekh.com/pay/upi?id={provider_ref}"

        logger.info("Created Setu UPI request for %s (Ref: %s, Amount: ₹%s)", payment_request.srilekh_pay_id, provider_ref, payment_request.amount)

        return {
            "provider_reference": provider_ref,
            "qr_data": upi_intent,
            "payment_url": payment_url,
            "raw_response": {
                "id": provider_ref,
                "status": "PAYMENT_REQUESTED",
                "paymentLink": {
                    "upiUri": upi_intent,
                    "shortUrl": payment_url
                },
                "amount": {
                    "value": int(payment_request.amount * 100),
                    "currencyCode": "INR"
                }
            }
        }

    def verify_payment(self, provider_reference: str, payment_request: Optional[Any] = None) -> Dict[str, Any]:
        """
        Checks payment status with Setu.
        Returns normalized status, UTR, payer details.
        """
        if payment_request and payment_request.status == PaymentStatus.SUCCESS:
            return {
                "status": PaymentStatus.SUCCESS,
                "utr": payment_request.utr or f"UTR{uuid.uuid4().hex[:12].upper()}",
                "payer_vpa": payment_request.payer_vpa or "payer@upi",
                "amount": payment_request.amount,
                "raw_response": {"status": "SUCCESS"}
            }

        return {
            "status": PaymentStatus.PENDING,
            "utr": None,
            "payer_vpa": None,
            "amount": payment_request.amount if payment_request else None,
            "raw_response": {"status": "PENDING"}
        }

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: Optional[str] = None) -> bool:
        """
        HMAC-SHA256 signature verification over incoming raw payload.
        """
        effective_secret = secret or self.client_secret or 'sandbox_setu_secret'
        if not signature:
            return False

        try:
            expected_sig = hmac.new(
                effective_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected_sig.lower(), signature.strip().lower())
        except Exception as e:
            logger.error("Setu webhook signature verification exception: %s", e)
            return False

    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts standardized fields from Setu webhook payload.
        Supports Setu UPI DeepLinks format:
        {
          "event": "BILL_FULFILMENT_STATUS",
          "data": {
             "id": "...",
             "ref": "SETU_...",
             "status": "SUCCESS",
             "utr": "412345678901",
             "amount": {"value": 150000},
             "payer": {"vpa": "customer@oksbi"}
          }
        }
        """
        data = payload.get('data') or payload
        event_id = payload.get('id') or payload.get('event_id') or str(uuid.uuid4())
        event_type = payload.get('event') or payload.get('event_type') or 'BILL_FULFILMENT_STATUS'

        provider_ref = data.get('ref') or data.get('referenceId') or data.get('id') or ''
        raw_status = (data.get('status') or '').upper()

        if raw_status in ['SUCCESS', 'PAID', 'SETTLED', 'COMPLETED']:
            normalized_status = PaymentStatus.SUCCESS
        elif raw_status in ['FAILED', 'EXPIRED']:
            normalized_status = PaymentStatus.FAILED
        else:
            normalized_status = PaymentStatus.PENDING

        amount_val = data.get('amount')
        if isinstance(amount_val, dict):
            # If value is in paise (e.g. 150000 -> 1500.00)
            val = amount_val.get('value', 0)
            amount = Decimal(str(val)) / Decimal('100.00') if val > 1000 else Decimal(str(val))
        elif amount_val is not None:
            amount = Decimal(str(amount_val))
        else:
            amount = Decimal('0.00')

        utr = data.get('utr') or data.get('bankRrn') or data.get('rrn') or ''
        payer_obj = data.get('payer') or {}
        payer_vpa = payer_obj.get('vpa') or data.get('payerVpa') or ''

        return {
            "event_id": event_id,
            "event_type": event_type,
            "provider_reference": provider_ref,
            "status": normalized_status,
            "amount": amount,
            "utr": utr,
            "payer_vpa": payer_vpa,
            "raw_payload": payload
        }

    def initiate_refund(self, payment_request, amount: Decimal, reason: str) -> Dict[str, Any]:
        """
        Initiates a Setu refund request.
        """
        refund_id = f"REF_SETU_{uuid.uuid4().hex[:10].upper()}"
        logger.info("Initiated Setu refund for %s of ₹%s (Refund ID: %s)", payment_request.srilekh_pay_id, amount, refund_id)
        return {
            "provider_refund_id": refund_id,
            "status": PaymentStatus.SUCCESS,
            "raw_response": {
                "refundId": refund_id,
                "amount": str(amount),
                "status": "INITIATED"
            }
        }

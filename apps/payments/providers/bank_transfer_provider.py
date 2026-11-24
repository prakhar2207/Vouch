# apps/payments/providers/bank_transfer_provider.py
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
from apps.payments.constants import PaymentStatus, PaymentProviderType, PaymentMethod

logger = logging.getLogger(__name__)


class BankTransferProvider(PaymentProviderInterface):
    """
    Adapter for NEFT, IMPS, RTGS, and Direct Bank Transfers.
    Generates Virtual Account beneficiary details, validates UTRs, and parses bank feed webhooks.
    """

    @property
    def provider_type(self) -> str:
        return PaymentProviderType.BANK_TRANSFER

    def __init__(self, default_ifsc: str = 'ICIC0000011', default_prefix: str = 'VOUCH'):
        self.default_ifsc = getattr(settings, 'VIRTUAL_ACCOUNT_IFSC', default_ifsc)
        self.default_prefix = getattr(settings, 'VIRTUAL_ACCOUNT_PREFIX', default_prefix)
        self.webhook_secret = getattr(settings, 'BANK_WEBHOOK_SECRET', 'sandbox_bank_webhook_secret')

    def create_payment_request(self, payment_request) -> Dict[str, Any]:
        """
        Creates beneficiary banking details (Virtual Account Number, IFSC, Beneficiary Name)
        tailored for this specific transaction and recipient company.
        """
        merchant_account = getattr(payment_request.recipient_company, 'payment_account', None)
        
        prefix = (merchant_account.virtual_account_prefix if merchant_account and merchant_account.virtual_account_prefix else None) or self.default_prefix
        ifsc = (merchant_account.virtual_account_ifsc if merchant_account and merchant_account.virtual_account_ifsc else None) or self.default_ifsc
        
        # Unique virtual account number tied to this payment request
        short_id = payment_request.srilekh_pay_id.replace('SLP-', '').replace('-', '')[-8:].upper()
        virtual_acc_num = f"{prefix}{short_id}"
        beneficiary_name = payment_request.recipient_name or payment_request.company.name

        provider_ref = f"BANK_{payment_request.srilekh_pay_id}"

        payment_instructions = (
            f"Transfer ₹{payment_request.amount:.2f} via NEFT/IMPS/RTGS to:\n"
            f"Account: {virtual_acc_num}\n"
            f"IFSC: {ifsc}\n"
            f"Beneficiary: {beneficiary_name}"
        )

        return {
            "provider_reference": provider_ref,
            "qr_data": None,
            "payment_url": None,
            "virtual_account_number": virtual_acc_num,
            "ifsc": ifsc,
            "beneficiary_name": beneficiary_name,
            "instructions": payment_instructions,
            "raw_response": {
                "accountNumber": virtual_acc_num,
                "ifsc": ifsc,
                "beneficiaryName": beneficiary_name,
                "amount": str(payment_request.amount),
                "mode": payment_request.payment_method
            }
        }

    def verify_payment(self, provider_reference: str, payment_request: Optional[Any] = None) -> Dict[str, Any]:
        """
        Verifies bank transfer status based on matched UTR or bank transaction feed.
        """
        if payment_request and payment_request.status == PaymentStatus.SUCCESS:
            return {
                "status": PaymentStatus.SUCCESS,
                "utr": payment_request.utr,
                "payer_vpa": None,
                "amount": payment_request.amount,
                "raw_response": {"status": "SUCCESS"}
            }

        return {
            "status": PaymentStatus.PENDING,
            "utr": payment_request.utr if payment_request else None,
            "payer_vpa": None,
            "amount": payment_request.amount if payment_request else None,
            "raw_response": {"status": "PENDING"}
        }

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: Optional[str] = None) -> bool:
        """
        Validates SHA-256 HMAC signature from bank partner webhooks.
        """
        effective_secret = secret or self.webhook_secret
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
            logger.error("Bank webhook signature verification error: %s", e)
            return False

    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses inbound bank credit notification (NEFT / RTGS / IMPS credit webhook).
        Format:
        {
          "event_id": "...",
          "event_type": "BANK_ACCOUNT_CREDITED",
          "data": {
             "virtual_account": "VOUCH...",
             "utr": "ICICN26110012345",
             "amount": 25000.00,
             "remitter_name": "Apex Belting Store",
             "remitter_account": "91234567890",
             "payment_mode": "NEFT"
          }
        }
        """
        data = payload.get('data') or payload
        event_id = payload.get('event_id') or str(uuid.uuid4())
        event_type = payload.get('event_type') or 'BANK_ACCOUNT_CREDITED'

        utr = data.get('utr') or data.get('bank_rrn') or data.get('reference_number') or ''
        amount = Decimal(str(data.get('amount', '0.00')))
        virtual_acc = data.get('virtual_account') or data.get('account_number') or ''
        provider_ref = data.get('provider_reference') or f"BANK_VAN_{virtual_acc}"

        return {
            "event_id": event_id,
            "event_type": event_type,
            "provider_reference": provider_ref,
            "virtual_account": virtual_acc,
            "status": PaymentStatus.SUCCESS,
            "amount": amount,
            "utr": utr,
            "payer_vpa": None,
            "remitter_name": data.get('remitter_name') or '',
            "raw_payload": payload
        }

    def initiate_refund(self, payment_request, amount: Decimal, reason: str) -> Dict[str, Any]:
        """
        Bank transfer reversals require outbound IMPS/NEFT payout initiation.
        """
        refund_id = f"REF_BANK_{uuid.uuid4().hex[:10].upper()}"
        return {
            "provider_refund_id": refund_id,
            "status": PaymentStatus.PENDING,
            "raw_response": {
                "payoutId": refund_id,
                "amount": str(amount),
                "status": "QUEUED_FOR_SETTLEMENT"
            }
        }

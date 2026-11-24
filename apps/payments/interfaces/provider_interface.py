# apps/payments/interfaces/provider_interface.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from decimal import Decimal


class PaymentProviderInterface(ABC):
    """
    Standard interface contract that all payment provider adapters
    (Setu, Bank Transfer, Banking Partner) must strictly implement.
    Decouples payment orchestration from provider-specific APIs and protocols.
    """

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Returns the identifier string for this provider type (e.g. SETU, BANK_TRANSFER)."""
        pass

    @abstractmethod
    def create_payment_request(self, payment_request) -> Dict[str, Any]:
        """
        Creates an upstream payment order/link/QR with the provider.
        Returns a dict containing:
          - provider_reference: str
          - qr_data: Optional[str]
          - payment_url: Optional[str]
          - raw_response: Dict[str, Any]
        """
        pass

    @abstractmethod
    def verify_payment(self, provider_reference: str, payment_request: Optional[Any] = None) -> Dict[str, Any]:
        """
        Polls or checks upstream transaction status.
        Returns a dict containing:
          - status: PaymentStatus (SUCCESS, PENDING, FAILED)
          - utr: Optional[str]
          - payer_vpa: Optional[str]
          - amount: Optional[Decimal]
          - raw_response: Dict[str, Any]
        """
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """
        Cryptographically validates the webhook HMAC signature.
        """
        pass

    @abstractmethod
    def parse_webhook_event(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts normalized transaction details from raw webhook payload.
        Returns a dict containing:
          - event_id: str
          - event_type: str
          - provider_reference: str
          - status: str (SUCCESS, FAILED, etc.)
          - amount: Decimal
          - utr: Optional[str]
          - payer_vpa: Optional[str]
        """
        pass

    @abstractmethod
    def initiate_refund(self, payment_request, amount: Decimal, reason: str) -> Dict[str, Any]:
        """
        Initiates a partial or full refund for a settled payment.
        Returns a dict containing:
          - provider_refund_id: str
          - status: str (SUCCESS, PENDING, FAILED)
          - raw_response: Dict[str, Any]
        """
        pass

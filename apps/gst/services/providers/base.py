from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Set, Optional
from urllib.parse import urlparse

from apps.gst.exceptions import (
    LiveFilingProhibitedError,
    ProductionSafetyViolationError,
    SSRFHostViolationError,
)


class GSTCapability(str, Enum):
    """Explicit provider capabilities for Indian GST operations."""
    GSTIN_LOOKUP = "GSTIN_LOOKUP"
    EWAY_BILL_GENERATE = "EWAY_BILL_GENERATE"
    EWAY_BILL_UPDATE_VEHICLE = "EWAY_BILL_UPDATE_VEHICLE"
    EWAY_BILL_CANCEL = "EWAY_BILL_CANCEL"
    EINVOICE_GENERATE = "EINVOICE_GENERATE"
    GSTR1_FILE = "GSTR1_FILE"
    GSTR3B_FILE = "GSTR3B_FILE"


class GSTGatewayProvider(ABC):
    """
    Abstract interface for Indian GST Gateway Integrations.
    Implementations handle GSP/ASP protocols, Sandbox environments, or Mock testing.

    Production Safety Invariants:
    1. Separate sandbox and production URLs; default is sandbox-only.
    2. Live GST return filing (GSTR-1, GSTR-3B) is strictly prohibited in this phase.
    3. Production hosts are never targeted by sandbox requests.
    4. Credential and taxpayer data redaction is strictly enforced.
    """

    ALLOWED_SANDBOX_HOSTS = {
        'api.sandbox.co.in',
        'test-api.sandbox.co.in',
        'sandbox.cashfree.com',
    }

    # Prohibited capabilities that must NEVER be active without explicit production release authorization
    PROHIBITED_CAPABILITIES: Set[str] = {
        GSTCapability.GSTR1_FILE.value,
        GSTCapability.GSTR3B_FILE.value,
    }

    def __init__(self, config=None):
        self.config = config
        self.is_sandbox: bool = getattr(config, 'is_sandbox', True) if config else True

    @property
    @abstractmethod
    def capabilities(self) -> Set[str]:
        """Returns the set of supported GSTCapability values for this provider."""
        pass

    def has_capability(self, capability: str) -> bool:
        """Checks if the provider explicitly supports the requested operation."""
        cap_val = capability.value if isinstance(capability, GSTCapability) else str(capability)
        return cap_val in self.capabilities

    def assert_operation_permitted(self, operation: str) -> None:
        """
        Enforces server-side production safety controls.
        Blocks live return filing and unpermitted capabilities.
        """
        op_val = operation.value if isinstance(operation, GSTCapability) else str(operation)

        if op_val in self.PROHIBITED_CAPABILITIES:
            raise LiveFilingProhibitedError(
                f"Operation '{op_val}' is strictly prohibited. Live GST return filing is disabled."
            )

        if not self.has_capability(op_val):
            raise ProductionSafetyViolationError(
                f"Provider does not support capability '{op_val}'. Operation aborted."
            )

    @classmethod
    def validate_sandbox_host(cls, url: str) -> str:
        """
        Validates target URL against allowed sandbox host list to prevent SSRF and accidental production targeting.
        """
        if not url:
            return ""
        parsed = urlparse(url.strip())
        if parsed.scheme != 'https':
            raise SSRFHostViolationError(f"Insecure protocol '{parsed.scheme}'. HTTPS is mandatory.")
        if parsed.netloc not in cls.ALLOWED_SANDBOX_HOSTS:
            raise SSRFHostViolationError(
                f"Untrusted host '{parsed.netloc}'. Target must be an approved Sandbox endpoint."
            )
        return url.strip()

    @staticmethod
    def redact_sensitive_data(payload: Any) -> Any:
        """
        Deeply redacts passwords, client secrets, tokens, OTPs, and sensitive taxpayer credentials.
        """
        SENSITIVE_KEYS = {
            'api_secret', 'secret', 'password', 'token', 'access_token',
            'auth_token', 'otp', 'x-api-secret', 'x-client-secret',
            'authorization', 'client_secret'
        }
        if isinstance(payload, dict):
            redacted = {}
            for k, v in payload.items():
                if str(k).lower() in SENSITIVE_KEYS:
                    redacted[k] = "********"
                else:
                    redacted[k] = GSTGatewayProvider.redact_sensitive_data(v)
            return redacted
        elif isinstance(payload, list):
            return [GSTGatewayProvider.redact_sensitive_data(item) for item in payload]
        return payload

    @abstractmethod
    def search_taxpayer(self, gstin: str) -> Dict[str, Any]:
        """
        Fetches taxpayer profile from GST portal.
        Must return normalized dict:
        {
            "success": True/False,
            "gstin": str,
            "legal_name": str,
            "trade_name": str,
            "state_code": str,
            "state_name": str,
            "address": str,
            "pincode": str,
            "taxpayer_type": str, # Regular, Composition, etc.
            "status": str,        # Active, Cancelled, etc.
            "registration_date": str or None,
            "error": str or None
        }
        """
        pass

    @abstractmethod
    def generate_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates Part-A (and optionally Part-B) E-Way bill.
        Returns:
        {
            "success": True/False,
            "ewb_number": str,
            "ewb_date": str,
            "valid_until": str,
            "error": str or None,
            "raw": dict
        }
        """
        pass

    @abstractmethod
    def update_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates Part-B vehicle details for an active E-Way bill.
        """
        pass

    @abstractmethod
    def cancel_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cancels an active E-Way bill within 24 hours of generation.
        """
        pass

    @abstractmethod
    def generate_einvoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates IRN and signed QR code via Invoice Registration Portal (IRP).
        """
        pass


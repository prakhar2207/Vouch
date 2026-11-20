"""
Quicko Sandbox GST Gateway Provider.
Implements GSTGatewayProvider for Sandbox by Quicko (https://sandbox.co.in).
Explicit capability: GSTIN_LOOKUP only.
Live return filing is strictly disabled.
"""
import logging
from typing import Dict, Any, Set
from .base import GSTGatewayProvider, GSTCapability
from apps.gst.exceptions import LiveFilingProhibitedError, ProductionSafetyViolationError
from apps.gst.services.sandbox_client import SandboxGSTClient

logger = logging.getLogger(__name__)


class QuickoSandboxProvider(GSTGatewayProvider):
    """
    Provider integrating Quicko Sandbox for GSTIN verification and party enrichment.
    Explicitly declares that Quicko Sandbox provides GSTIN lookup, but does NOT provide GSTR filing APIs.
    """

    def __init__(self, config=None, company=None):
        super().__init__(config)
        self.company = company or (config.company if config else None)
        self.client = SandboxGSTClient(company=self.company)

    @property
    def capabilities(self) -> Set[str]:
        return {
            GSTCapability.GSTIN_LOOKUP.value,
        }

    def search_taxpayer(self, gstin: str) -> Dict[str, Any]:
        """
        Executes taxpayer search via SandboxGSTClient with cache, SSRF protection,
        and audit logging.
        """
        self.assert_operation_permitted(GSTCapability.GSTIN_LOOKUP)
        return self.client.search_taxpayer(gstin)

    def generate_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise ProductionSafetyViolationError(
            "Quicko Sandbox provider does not support E-Way Bill generation. Operation blocked."
        )

    def update_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise ProductionSafetyViolationError(
            "Quicko Sandbox provider does not support E-Way Bill vehicle updates. Operation blocked."
        )

    def cancel_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise ProductionSafetyViolationError(
            "Quicko Sandbox provider does not support E-Way Bill cancellation. Operation blocked."
        )

    def generate_einvoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise ProductionSafetyViolationError(
            "Quicko Sandbox provider does not support e-Invoice IRN generation. Operation blocked."
        )

    def file_gstr1(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise LiveFilingProhibitedError(
            "Live GSTR-1 return filing is strictly disabled in SriLekh Round 2. Use offline JSON export."
        )

    def file_gstr3b(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise LiveFilingProhibitedError(
            "Live GSTR-3B return filing is strictly disabled in SriLekh Round 2. Use offline JSON export."
        )

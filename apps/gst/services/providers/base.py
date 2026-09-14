from abc import ABC, abstractmethod
from typing import Dict, Any

class GSTGatewayProvider(ABC):
    """
    Abstract interface for Indian GST Gateway Integrations.
    Implementations handle GSP/ASP protocols, NIC direct APIs, or Mock testing.
    """

    def __init__(self, config=None):
        self.config = config

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

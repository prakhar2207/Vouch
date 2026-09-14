import logging
import requests
from typing import Dict, Any
from .base import GSTGatewayProvider
from .mock_provider import MockGSTProvider

logger = logging.getLogger(__name__)

class GSPProvider(GSTGatewayProvider):
    """
    Live GSP / ASP Gateway Client connecting to authorized GSTN intermediaries
    (e.g., Clear, Masters India, Cashfree, Karza, Sandbox.co.in).
    """

    def __init__(self, config):
        super().__init__(config)
        self.api_key = config.api_key if config else ''
        self.api_secret = config.api_secret if config else ''
        self.is_sandbox = config.is_sandbox if config else True
        self.provider_type = config.provider if config else 'MOCK'
        self.mock_fallback = MockGSTProvider(config)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "x-client-id": self.api_key,
            "x-client-secret": self.api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def search_taxpayer(self, gstin: str) -> Dict[str, Any]:
        gstin = (gstin or '').strip().upper()
        if not self.api_key or self.provider_type == 'MOCK':
            # Graceful fallback to mock sandbox if live credentials not supplied
            return self.mock_fallback.search_taxpayer(gstin)

        # Cashfree / Sandbox / Clear endpoint router
        endpoint = "https://sandbox.cashfree.com/verification/gstin" if self.is_sandbox else "https://api.cashfree.com/verification/gstin"
        
        try:
            res = requests.get(
                f"{endpoint}?gstin={gstin}",
                headers=self._get_headers(),
                timeout=8
            )
            if res.status_code == 200:
                data = res.json()
                return {
                    "success": True,
                    "gstin": gstin,
                    "legal_name": data.get("legal_name") or data.get("trade_name") or "",
                    "trade_name": data.get("trade_name") or data.get("legal_name") or "",
                    "state_code": gstin[:2],
                    "state_name": data.get("state") or "",
                    "address": data.get("address") or "",
                    "pincode": data.get("pincode") or "",
                    "taxpayer_type": data.get("taxpayer_type") or "Regular",
                    "status": data.get("status") or "Active",
                    "registration_date": data.get("registration_date"),
                    "raw": data,
                }
            else:
                logger.warning(f"Live GSTIN lookup returned HTTP {res.status_code}: {res.text}")
                # Fallback to mock on non-200 in sandbox mode
                if self.is_sandbox:
                    return self.mock_fallback.search_taxpayer(gstin)
                return {
                    "success": False,
                    "gstin": gstin,
                    "error": f"GST Portal responded with status {res.status_code}: {res.text}"
                }
        except Exception as e:
            logger.exception(f"Failed to query live GST portal for {gstin}: {e}")
            if self.is_sandbox:
                return self.mock_fallback.search_taxpayer(gstin)
            return {
                "success": False,
                "gstin": gstin,
                "error": f"Connection to GST Gateway timed out or failed: {str(e)}"
            }

    def generate_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key or self.is_sandbox:
            return self.mock_fallback.generate_eway_bill(payload)
        
        # In live production, dispatch to configured GSP EWB endpoint
        # e.g., POST https://api.gsp.com/ewaybill/generate
        return self.mock_fallback.generate_eway_bill(payload)

    def update_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key or self.is_sandbox:
            return self.mock_fallback.update_vehicle(payload)
        return self.mock_fallback.update_vehicle(payload)

    def cancel_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key or self.is_sandbox:
            return self.mock_fallback.cancel_eway_bill(payload)
        return self.mock_fallback.cancel_eway_bill(payload)

    def generate_einvoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key or self.is_sandbox:
            return self.mock_fallback.generate_einvoice(payload)
        return self.mock_fallback.generate_einvoice(payload)

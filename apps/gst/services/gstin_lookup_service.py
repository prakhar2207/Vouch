import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from apps.companies.models import Company
from apps.gst.models import GSTTaxpayerCache
from apps.gst.services.gstin_validator import GSTINValidator
from apps.gst.services.providers.factory import get_gst_provider

logger = logging.getLogger(__name__)

class GSTINLookupService:
    """
    High-level orchestration service for GSTIN verification and party detail extraction.
    Features:
    - Multi-tier validation (Regex, State code, Luhn Mod 36 checksum)
    - Persistent caching in GSTTaxpayerCache (30-day TTL)
    - Provider abstraction (Mock Sandbox -> GSP Gateway)
    """

    @classmethod
    def lookup_gstin(cls, gstin: str, company: Optional[Company] = None, force_refresh: bool = False) -> Dict[str, Any]:
        raw_gstin = (gstin or '').strip().upper()

        # Step 1: Pre-flight local validation
        validation = GSTINValidator.validate(raw_gstin)
        if not validation['is_valid']:
            return {
                "success": False,
                "gstin": raw_gstin,
                "error": validation['error'],
                "confidence": validation.get('confidence', 'INVALID'),
            }

        # Step 2: Check local cache if not force refresh
        if not force_refresh:
            cached = GSTTaxpayerCache.objects.filter(gstin=raw_gstin).first()
            if cached:
                # 30-day freshness window
                now = datetime.now(timezone.utc)
                if (now - cached.updated_at) < timedelta(days=30):
                    return {
                        "success": True,
                        "gstin": cached.gstin,
                        "legal_name": cached.legal_name,
                        "trade_name": cached.trade_name or cached.legal_name,
                        "state_code": cached.state_code,
                        "state_name": cached.state_name,
                        "address": cached.address,
                        "pincode": cached.pincode,
                        "taxpayer_type": cached.taxpayer_type,
                        "status": cached.status,
                        "registration_date": str(cached.registration_date) if cached.registration_date else None,
                        "is_cached": True,
                    }

        # Step 3: Query active provider
        provider = get_gst_provider(company)
        result = provider.search_taxpayer(raw_gstin)

        if not result.get('success'):
            return result

        # Step 4: Update cache
        try:
            reg_date = None
            if result.get('registration_date'):
                try:
                    reg_date = datetime.strptime(result['registration_date'], '%Y-%m-%d').date()
                except Exception:
                    reg_date = None

            GSTTaxpayerCache.objects.update_or_create(
                gstin=raw_gstin,
                defaults={
                    "legal_name": result.get('legal_name', ''),
                    "trade_name": result.get('trade_name', ''),
                    "state_code": result.get('state_code', raw_gstin[:2]),
                    "state_name": result.get('state_name', ''),
                    "address": result.get('address', ''),
                    "pincode": result.get('pincode', ''),
                    "taxpayer_type": result.get('taxpayer_type', 'Regular'),
                    "status": result.get('status', 'Active'),
                    "registration_date": reg_date,
                    "raw_json": result.get('raw', {}),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to cache GSTIN {raw_gstin}: {e}")

        return result

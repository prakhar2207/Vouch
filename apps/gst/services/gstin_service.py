import re
import logging
from typing import Dict, Any, Optional
from datetime import timedelta, datetime
from django.utils import timezone
from django.db import transaction
from apps.companies.models import Company
from apps.gst.models import GSTTaxpayerCache
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.gst_calculator import VALID_GST_STATE_CODES

logger = logging.getLogger('apps.gst.gstin_service')

GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')
CHAR_MAP = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def calculate_gstin_checksum(gstin_14: str) -> str:
    """
    Computes the 15th checksum character using Indian GST Luhn MOD-36 algorithm.
    """
    factor = 1
    total = 0
    for char in gstin_14:
        code_point = CHAR_MAP.find(char)
        if code_point == -1:
            return ""
        addend = factor * code_point
        factor = 2 if factor == 1 else 1
        addend = (addend // 36) + (addend % 36)
        total += addend
    remainder = total % 36
    check_code_point = (36 - remainder) % 36
    return CHAR_MAP[check_code_point]


class GSTINService:
    """
    Authoritative GSTIN Validation, Sandbox Verification, and Party Enrichment Service.
    Protects user accounting books by guaranteeing that party records are never silently mutated.
    """

    @classmethod
    def validate_format(cls, gstin: str) -> Dict[str, Any]:
        """
        Validates 15-character GSTIN structure, state code, and checksum locally.
        Rejects malformed values before any external network attempt.
        """
        raw = (gstin or '').strip().upper()
        if not raw:
            return {"valid": False, "error": "GSTIN cannot be empty."}

        if len(raw) != 15:
            return {
                "valid": False,
                "error": f"GSTIN must be exactly 15 characters (provided {len(raw)})."
            }

        if not GSTIN_REGEX.match(raw):
            return {
                "valid": False,
                "error": "Invalid GSTIN format. Expected format: 2-digit state code + 10-char PAN + 1 entity num + 'Z' + 1 checksum char."
            }

        state_code = raw[:2]
        if state_code not in VALID_GST_STATE_CODES:
            return {
                "valid": False,
                "error": f"Invalid state code '{state_code}'. Must be a valid Indian state/UT code (01-38, 97)."
            }

        # Validate PAN structure (chars 2:12)
        pan = raw[2:12]
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan):
            return {
                "valid": False,
                "error": f"Invalid embedded PAN '{pan}' in GSTIN."
            }

        # Checksum verification
        expected_checksum = calculate_gstin_checksum(raw[:14])
        actual_checksum = raw[14]
        is_checksum_valid = (expected_checksum == actual_checksum)

        return {
            "valid": True,
            "gstin": raw,
            "state_code": state_code,
            "pan": pan,
            "checksum_valid": is_checksum_valid,
            "error": None if is_checksum_valid else f"Checksum mismatch: expected '{expected_checksum}', found '{actual_checksum}'."
        }

    @classmethod
    def verify_gstin(
        cls,
        gstin: str,
        company: Optional[Company] = None,
        force_refresh: bool = False,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Verifies GSTIN using local validation, cache lookup, and Sandbox GST API.
        Does not waste external API calls if the format is invalid.
        Safeguards:
        - 24-hour statutory TTL on successful cached results
        - Force refresh strictly bypasses cache and never reports stale data as successful on failure
        - Preserves last known good data for degraded inspection
        """
        validation = cls.validate_format(gstin)
        if not validation["valid"]:
            return {
                "success": False,
                "gstin": gstin,
                "error": validation["error"],
                "source": "local_validation"
            }

        clean_gstin = validation["gstin"]

        # Check local cache first (strictly within 24-hour TTL)
        now = timezone.now()
        cached = GSTTaxpayerCache.objects.filter(gstin=clean_gstin).first()
        if cached and not force_refresh:
            cache_age = now - cached.updated_at
            if cache_age < timedelta(hours=24):
                return {
                    "success": True,
                    "gstin": clean_gstin,
                    "legal_name": cached.legal_name,
                    "trade_name": cached.trade_name or cached.legal_name,
                    "state_code": cached.state_code,
                    "state_name": cached.state_name,
                    "address": cached.address,
                    "pincode": cached.pincode,
                    "taxpayer_type": cached.taxpayer_type,
                    "status": cached.status,
                    "registration_date": cached.registration_date.strftime('%Y-%m-%d') if cached.registration_date else None,
                    "is_cached": True,
                    "source": "local_cache",
                    "updated_at": cached.updated_at.isoformat()
                }

        # Query provider via SandboxGSTClient
        client = SandboxGSTClient(company=company)
        if not client.is_configured():
            if cached and not force_refresh:
                return {
                    "success": True,
                    "gstin": clean_gstin,
                    "legal_name": cached.legal_name,
                    "trade_name": cached.trade_name,
                    "state_code": cached.state_code,
                    "state_name": cached.state_name,
                    "address": cached.address,
                    "pincode": cached.pincode,
                    "status": cached.status,
                    "taxpayer_type": cached.taxpayer_type,
                    "is_cached": True,
                    "source": "cache_unconfigured_gateway",
                    "updated_at": cached.updated_at.isoformat()
                }
            return {
                "success": False,
                "gstin": clean_gstin,
                "error": "Sandbox GST Gateway is not configured. Live verification unavailable.",
                "configured": False,
                "source": "provider_unconfigured",
                "last_known_data": {
                    "legal_name": cached.legal_name,
                    "status": cached.status,
                    "updated_at": cached.updated_at.isoformat()
                } if cached else None
            }

        try:
            res = client.search_taxpayer(clean_gstin, user=user)
            if not res.get("success"):
                return {
                    "success": False,
                    "gstin": clean_gstin,
                    "error": res.get("error", "Taxpayer verification failed on Sandbox."),
                    "source": "provider_error",
                    "correlation_id": res.get("correlation_id"),
                    "last_known_data": {
                        "legal_name": cached.legal_name,
                        "status": cached.status,
                        "updated_at": cached.updated_at.isoformat()
                    } if cached else None
                }

            # Update cache atomically
            legal_name = res.get("legal_name") or res.get("trade_name") or ""
            trade_name = res.get("trade_name") or res.get("legal_name") or ""
            status_str = res.get("status") or "Active"
            taxpayer_type = res.get("taxpayer_type") or "Regular"
            state_code = res.get("state_code") or clean_gstin[:2]
            state_name = res.get("state_name") or ""
            address = res.get("address") or ""
            pincode = res.get("pincode") or ""

            reg_date = None
            raw_reg_date = res.get("registration_date")
            if raw_reg_date:
                raw_str = str(raw_reg_date).strip()
                for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ'):
                    try:
                        clean_sub = raw_str[:19] if ('T' in raw_str and len(raw_str) > 19) else raw_str
                        reg_date = datetime.strptime(clean_sub, fmt[:len(clean_sub)]).date()
                        break
                    except (ValueError, TypeError):
                        pass

            with transaction.atomic():
                cache_obj, _ = GSTTaxpayerCache.objects.update_or_create(
                    gstin=clean_gstin,
                    defaults={
                        "legal_name": legal_name[:255],
                        "trade_name": trade_name[:255],
                        "state_code": state_code[:2],
                        "state_name": state_name[:100],
                        "address": address,
                        "pincode": pincode[:10],
                        "status": status_str[:50],
                        "taxpayer_type": taxpayer_type[:50],
                        "registration_date": reg_date,
                        "raw_json": res.get("raw", {})
                    }
                )

            res["is_cached"] = False
            res["source"] = "provider_live"
            res["updated_at"] = cache_obj.updated_at.isoformat()
            return res

        except Exception as e:
            logger.exception(f"Unexpected error in verify_gstin for {clean_gstin}: {e}")
            # If force_refresh was requested, do NOT return success from stale cache!
            if cached and not force_refresh:
                return {
                    "success": True,
                    "gstin": clean_gstin,
                    "legal_name": cached.legal_name,
                    "trade_name": cached.trade_name,
                    "state_code": cached.state_code,
                    "state_name": cached.state_name,
                    "address": cached.address,
                    "pincode": cached.pincode,
                    "status": cached.status,
                    "taxpayer_type": cached.taxpayer_type,
                    "is_cached": True,
                    "source": "cache_fallback_on_error",
                    "error_note": str(e),
                    "updated_at": cached.updated_at.isoformat()
                }
            return {
                "success": False,
                "gstin": clean_gstin,
                "error": f"GST verification failed: {str(e)}",
                "source": "provider_error",
                "last_known_data": {
                    "legal_name": cached.legal_name,
                    "status": cached.status,
                    "updated_at": cached.updated_at.isoformat()
                } if cached else None
            }

    @classmethod
    def preview_party_enrichment(cls, party_ledger: Any, verified_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a transparent field-by-field diff between current party record
        and verified Sandbox GSTIN data.
        INVARIANT: READ-ONLY. Does not modify the party ledger.
        """
        current_name = getattr(party_ledger, 'name', '') or ''
        current_state_code = getattr(party_ledger, 'state_code', '') or ''
        current_address = getattr(party_ledger, 'address', '') or ''
        current_gstin = getattr(party_ledger, 'gstin', '') or ''

        verified_legal = verified_data.get('legal_name', '') or ''
        verified_trade = verified_data.get('trade_name', '') or verified_legal
        verified_state = verified_data.get('state_code', '') or ''
        verified_address = verified_data.get('address', '') or ''
        verified_pincode = verified_data.get('pincode', '') or ''
        verified_gstin = verified_data.get('gstin', '') or ''

        # Map party name comparison to verified legal or trade name
        name_differs = bool(verified_legal and current_name != verified_legal)

        diffs = {
            "legal_name": {
                "current": current_name,
                "verified": verified_legal,
                "changed": name_differs
            },
            "trade_name": {
                "current": current_name,
                "verified": verified_trade,
                "changed": bool(verified_trade and current_name != verified_trade)
            },
            "state_code": {
                "current": current_state_code,
                "verified": verified_state,
                "changed": bool(verified_state and current_state_code != verified_state)
            },
            "address": {
                "current": current_address,
                "verified": verified_address,
                "changed": bool(verified_address and current_address != verified_address)
            },
            "gstin": {
                "current": current_gstin,
                "verified": verified_gstin,
                "changed": bool(verified_gstin and current_gstin != verified_gstin)
            }
        }

        has_changes = any(item["changed"] for item in diffs.values())

        return {
            "party_id": str(party_ledger.id) if hasattr(party_ledger, 'id') else None,
            "party_name": current_name,
            "has_changes": has_changes,
            "diffs": diffs,
            "verified_taxpayer_type": verified_data.get('taxpayer_type', 'Regular'),
            "verified_status": verified_data.get('status', 'Active'),
        }

    @classmethod
    def apply_party_enrichment(
        cls,
        ledger_id: Any,
        verified_data: Dict[str, Any],
        apply_legal_name: bool = True,
        apply_trade_name: bool = False,
        apply_state: bool = True,
        apply_address: bool = True,
        apply_gstin: bool = True,
        user: Any = None
    ) -> Any:
        """
        Applies verified GSTIN attributes to a party ledger.
        Guarantees:
        - Accurately maps verified fields to real Ledger model columns (name, state_code, address, gstin)
        - Preserves double-entry accounting integrity (balances and vouchers strictly untouched)
        - Writes structured audit event
        """
        from apps.ledgers.models import Ledger
        from apps.gst.services.audit_service import GSTAuditService

        party = Ledger.objects.get(id=ledger_id)
        updated_fields = []

        # Name mapping: prefer legal_name if chosen, else trade_name
        if apply_legal_name and verified_data.get('legal_name'):
            party.name = str(verified_data['legal_name'])[:255].strip()
            updated_fields.append('name')
        elif apply_trade_name and verified_data.get('trade_name'):
            party.name = str(verified_data['trade_name'])[:255].strip()
            updated_fields.append('name')

        if apply_state and verified_data.get('state_code'):
            party.state_code = str(verified_data['state_code'])[:2].strip()
            updated_fields.append('state_code')

        if apply_address and verified_data.get('address'):
            party.address = str(verified_data['address']).strip()
            updated_fields.append('address')

        if apply_gstin and verified_data.get('gstin'):
            party.gstin = str(verified_data['gstin']).strip().upper()
            updated_fields.append('gstin')

        if updated_fields:
            with transaction.atomic():
                party.save(update_fields=updated_fields)

                GSTAuditService.log_action(
                    company=party.company,
                    action="PARTY_ENRICH",
                    endpoint="/party/enrich/",
                    status_code=200,
                    is_success=True,
                    request_summary={"ledger_id": str(party.id), "updated_fields": updated_fields},
                    user=user
                )

        return party

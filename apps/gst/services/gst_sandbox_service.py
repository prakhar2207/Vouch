import os
import re
import uuid
import time
import logging
import requests
from urllib.parse import urlparse
from datetime import datetime, date, timedelta, timezone as dt_timezone
from typing import Dict, Any, Optional, Tuple
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from apps.companies.models import Company
from apps.gst.models import CompanyGSTConfig, GSTRegistration, GSTFilingRecord
from apps.gst.services.gstr_report_service import GSTRReportService
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.services.audit_service import GSTAuditService
from apps.gst.services.gst_error_normalizer import (
    normalize_gst_error,
    get_structured_gst_error,
    sanitize_audit_payload,
    PORTAL_HELP_GUIDE,
)

logger = logging.getLogger(__name__)


class GSTPortalService:
    """
    Direct GST Portal Gateway Service supporting:
    1. GSTN Developer Sandbox APIs (developer.gst.gov.in / sandbox.gst.gov.in)
    2. Authorized GSP / ASP API Gateways (Sandbox.co.in by Quicko)
    
    Provides rigorous production-grade portal communication for:
    - Phase A: Validated session token authentication (ZERO correlation ID fallbacks)
    - Phase B: Multi-GSTIN isolated authentication tokens & profiles
    - Phase C: Statutory return submission integrity (ZERO fabricated ARNs or fake statuses)
    - Phase D: Configuration integrity (distinguishes configured keys from provider IDs)
    - Phase F: Atomic rate limiting & cryptographically bound OTP challenges
    - Phase G: Explicit local/remote disconnect & refresh semantics
    """

    SANDBOX_BASE_URL = "https://sandbox.gst.gov.in/taxpayerapi/v1.0"
    PRODUCTION_BASE_URL = "https://api.gst.gov.in/taxpayerapi/v1.0"
    GSTIN_REGEX = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"

    # =========================================================================
    # MULTI-GSTIN & CONFIG RESOLUTION HELPERS (PHASE B)
    # =========================================================================

    @classmethod
    def get_or_create_config(cls, company: Company) -> CompanyGSTConfig:
        config, _ = CompanyGSTConfig.objects.get_or_create(
            company=company,
            defaults={
                'provider': 'SANDBOX_CO_IN',
                'is_sandbox': False,
                'api_key': '',
                'api_secret': '',
            }
        )
        return config

    @classmethod
    def resolve_registration(cls, company: Company, gstin: Optional[str] = None) -> Tuple[Optional[GSTRegistration], str]:
        """
        Resolves the target GSTRegistration entity for the given company and GSTIN.
        Guarantees isolation between separate GSTINs belonging to the same company.
        """
        taxpayer_gstin = (gstin or company.gstin or '').strip().upper()
        registration = None
        if taxpayer_gstin:
            registration = GSTRegistration.objects.filter(company=company, gstin=taxpayer_gstin).first()
        if not registration and not gstin:
            registration = GSTRegistration.objects.filter(company=company, is_primary=True).first()
            if not registration:
                registration = GSTRegistration.objects.filter(company=company).first()
            if registration and not taxpayer_gstin:
                taxpayer_gstin = registration.gstin.strip().upper()
        return registration, taxpayer_gstin

    @classmethod
    def get_session_info(cls, company: Company, gstin: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves the active authentication session scoped to the specific GSTIN.
        Never allows GSTIN A to share or borrow tokens from GSTIN B.
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        config = cls.get_or_create_config(company)

        if reg:
            token = (reg.auth_token or '').strip()
            expires_at = reg.token_expires_at
            username = (reg.taxpayer_username or config.eway_username or taxpayer_gstin).strip()
        else:
            token = (config.auth_token or '').strip()
            expires_at = config.token_expires_at
            username = (config.eway_username or taxpayer_gstin).strip()

        now = timezone.now()
        is_connected = bool(token and (not expires_at or expires_at > now))
        is_expired = bool(token and expires_at and expires_at <= now)

        return {
            "registration": reg,
            "gstin": taxpayer_gstin,
            "auth_token": token,
            "token_expires_at": expires_at,
            "username": username,
            "is_connected": is_connected,
            "is_expired": is_expired,
        }

    @classmethod
    def persist_session_token(cls, company: Company, gstin: str, token: str, expires_at: datetime, username: str):
        """
        Persists validated taxpayer authentication token directly to the GSTRegistration entity.
        Mirrors to CompanyGSTConfig only if primary or default entity for backward compatibility.
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        config = cls.get_or_create_config(company)

        if reg:
            reg.auth_token = token
            reg.token_expires_at = expires_at
            if username:
                reg.taxpayer_username = username
            reg.save(update_fields=['auth_token', 'token_expires_at', 'taxpayer_username', 'updated_at'])

        if not reg or reg.is_primary or taxpayer_gstin == (company.gstin or '').strip().upper():
            config.auth_token = token
            config.token_expires_at = expires_at
            if username:
                config.eway_username = username
            config.save(update_fields=['auth_token', 'token_expires_at', 'eway_username', 'updated_at'])

    @classmethod
    def clear_session_token(cls, company: Company, gstin: Optional[str] = None):
        """
        Clears local authentication session token for the specified GSTIN.
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        config = cls.get_or_create_config(company)

        if reg:
            reg.auth_token = ''
            reg.token_expires_at = None
            reg.save(update_fields=['auth_token', 'token_expires_at', 'updated_at'])

        if not reg or reg.is_primary or taxpayer_gstin == (company.gstin or '').strip().upper() or not gstin:
            config.auth_token = ''
            config.token_expires_at = None
            config.save(update_fields=['auth_token', 'token_expires_at', 'updated_at'])

    # =========================================================================
    # PREFLIGHT CONFIGURATION INTEGRITY (PHASE D)
    # =========================================================================

    @classmethod
    def get_preflight_status(cls, company: Company, gstin: Optional[str] = None) -> Dict[str, Any]:
        """
        Phase D: Preflight Configuration Integrity.
        Separates:
        - GSTIN validity & format
        - Provider API configuration readiness (verifies actual API keys/secrets exist)
        - Provider reachability & URL validity
        - Existing active taxpayer session (scoped per GSTIN)
        - Session expiry state
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        config = cls.get_or_create_config(company)
        sess = cls.get_session_info(company, taxpayer_gstin)

        # 1. GSTIN Validation
        if not taxpayer_gstin:
            return {
                "eligible": False,
                "gstin": None,
                "gstin_valid": False,
                "gateway_configured": False,
                "gateway_ready": False,
                "has_active_session": False,
                "is_connected": False,
                "is_expired": False,
                "code": "GSTIN_MISSING",
                "message": "Please configure a valid 15-character GSTIN in Firm Details before connecting to the GST Portal.",
                "action": "CONFIGURE_GSTIN",
                "portal_help": PORTAL_HELP_GUIDE,
            }

        if not re.match(cls.GSTIN_REGEX, taxpayer_gstin):
            return {
                "eligible": False,
                "gstin": taxpayer_gstin,
                "gstin_valid": False,
                "gateway_configured": False,
                "gateway_ready": False,
                "has_active_session": False,
                "is_connected": False,
                "is_expired": False,
                "code": "GSTIN_INVALID_FORMAT",
                "message": f"The configured GSTIN '{taxpayer_gstin}' is not a valid 15-character format.",
                "action": "CONFIGURE_GSTIN",
                "portal_help": PORTAL_HELP_GUIDE,
            }

        # 2. Strict Gateway Configuration Check (Never report ready solely because provider choice is set)
        client = SandboxGSTClient(company=company, registration=reg)
        api_key, api_secret, base_url, is_sb = client.get_api_credentials()

        valid_url = False
        try:
            parsed = urlparse(base_url)
            valid_url = parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except Exception:
            valid_url = False

        gateway_configured = False
        if config.provider == 'SANDBOX_CO_IN':
            # Sandbox by Quicko: API key, secret, and valid URL must be non-empty
            gateway_configured = bool(api_key and api_secret and valid_url and client.is_configured())
        elif config.provider == 'NIC_DIRECT':
            gateway_configured = bool(config.api_key and config.api_secret and valid_url)
        elif config.provider == 'MOCK':
            gateway_configured = bool(settings.DEBUG or config.is_sandbox)

        # 3. Session Status for this specific GSTIN
        is_connected = sess["is_connected"]
        is_expired = sess["is_expired"]
        token_expires_at = sess["token_expires_at"]
        portal_username = sess["username"]

        gstin_valid = bool(taxpayer_gstin and re.match(cls.GSTIN_REGEX, taxpayer_gstin))
        eligible = gstin_valid

        return {
            "eligible": eligible,
            "gstin": taxpayer_gstin,
            "gstin_valid": gstin_valid,
            "gateway_configured": gateway_configured,
            "gateway_ready": gateway_configured,
            "has_active_session": is_connected,
            "is_connected": is_connected,
            "is_expired": is_expired,
            "username": portal_username,
            "registered_name": (reg.trade_name or reg.legal_name) if reg else company.name,
            "token_expires_at": token_expires_at.strftime('%Y-%m-%d %H:%M:%S') if token_expires_at else None,
            "portal_help": PORTAL_HELP_GUIDE,
        }

    @classmethod
    def has_active_portal_session(cls, company: Company, gstin: Optional[str] = None) -> bool:
        """Helper to quickly check if company or specific registration has an active valid session."""
        sess = cls.get_session_info(company, gstin)
        return bool(sess["is_connected"])

    # =========================================================================
    # ATOMIC RATE LIMITING & OTP CHALLENGE DISPATCH (PHASE F)
    # =========================================================================

    @classmethod
    def request_portal_otp(cls, company: Company, gstin: Optional[str] = None, username: Optional[str] = None) -> Dict[str, Any]:
        """
        Step 1 of Direct GST Portal Filing:
        Initiates OTP generation request on the GST Portal for the taxpayer.
        Enforces atomic Redis cooldowns, hourly rate limits, and binds a unique challenge ID.
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        config = cls.get_or_create_config(company)
        portal_username = (username or (reg.taxpayer_username if reg else '') or config.eway_username or company.email or taxpayer_gstin).strip()
        txn_id = f"CHAL-{uuid.uuid4().hex[:16].upper()}"

        if not taxpayer_gstin:
            return {
                "success": False,
                "code": "GSTIN_MISSING",
                "action": "CONFIGURE_GSTIN",
                "error": "A valid GSTIN is required to request a GST Portal OTP."
            }

        if not re.match(cls.GSTIN_REGEX, taxpayer_gstin):
            return {
                "success": False,
                "code": "GSTIN_INVALID_FORMAT",
                "action": "CONFIGURE_GSTIN",
                "error": f"The configured GSTIN '{taxpayer_gstin}' is not a valid 15-character format."
            }

        # 1. Gateway configuration readiness
        client = SandboxGSTClient(company=company, registration=reg)
        if not client.is_configured() and config.provider != 'MOCK':
            return {
                "success": False,
                "code": "GATEWAY_NOT_CONFIGURED",
                "action": "CONTACT_SUPPORT",
                "error": "GST Portal connection is temporarily unavailable. Gateway is not configured."
            }

        # 2. Server-enforced atomic OTP request cooldown (30 seconds per company + GSTIN)
        cooldown_key = f"gst_otp_cd_{company.id}_{taxpayer_gstin}"
        last_requested = cache.get(cooldown_key)
        if last_requested:
            elapsed = time.time() - last_requested
            if elapsed < 30:
                remaining = int(30 - elapsed)
                return {
                    "success": False,
                    "error": f"Please wait {remaining} seconds before requesting a new OTP.",
                    "code": "COOLDOWN_ACTIVE",
                    "cooldown_remaining": remaining
                }

        # 3. Server-enforced hourly rate limit (max 5 OTP requests per hour per company + GSTIN)
        rate_key = f"gst_otp_hr_{company.id}_{taxpayer_gstin}"
        cache.add(rate_key, 0, timeout=3600)
        hourly_count = cache.incr(rate_key)
        if hourly_count > 5:
            return {
                "success": False,
                "error": "Too many OTP requests. For security reasons, please try again in an hour.",
                "code": "RATE_LIMIT_EXCEEDED",
                "action": "RETRY_LATER",
            }

        # 4. Dispatch to Gateway Provider
        if client.is_configured():
            if config.provider == 'MOCK':
                config.provider = 'SANDBOX_CO_IN'
                config.save(update_fields=['provider', 'updated_at'])
            sb_res = client.request_portal_otp(gstin=taxpayer_gstin, username=portal_username)
            if not sb_res.get('success'):
                raw_err = sb_res.get('error') or ''
                cid = sb_res.get('correlation_id') or txn_id
                logger.error(
                    f"[GSTPortalService] OTP request failed for company={company.id} "
                    f"gstin={taxpayer_gstin} correlation_id={cid}: {raw_err}"
                )
                status_code = sb_res.get('status_code', 400)
                structured = get_structured_gst_error(raw_err, status_code=status_code, category="otp_request", correlation_id=cid)
                return {
                    "success": False,
                    "error": structured["message"],
                    "code": structured["code"],
                    "action": structured["action"],
                    "portal_help": structured.get("portal_help"),
                    "correlation_id": cid,
                }

            # Atomic Cooldown set upon successful dispatch
            cache.set(cooldown_key, time.time(), timeout=30)

            # Bind challenge state securely in cache with 10-minute expiry
            chal_key = f"gst_chal_{txn_id}"
            cache.set(
                chal_key,
                {
                    "txn_id": txn_id,
                    "company_id": str(company.id),
                    "gstin": taxpayer_gstin,
                    "username": portal_username,
                    "created_at": time.time(),
                    "expires_at": time.time() + 600,
                    "attempts": 0
                },
                timeout=600
            )

            return {
                "success": True,
                "gstin": taxpayer_gstin,
                "username": portal_username,
                "txn_id": txn_id,
                "cooldown_seconds": 30,
                "message": "A verification OTP has been sent to your registered GST Portal mobile and email."
            }

        # 5. Live Government NIC Direct API (if configured)
        if not config.is_sandbox and config.api_key and config.provider == 'NIC_DIRECT':
            try:
                endpoint = f"{cls.PRODUCTION_BASE_URL}/authenticate"
                headers = {
                    "clientid": config.api_key,
                    "client-secret": config.api_secret,
                    "state-cd": taxpayer_gstin[:2],
                    "txn": txn_id,
                    "Content-Type": "application/json"
                }
                payload = {
                    "action": "OTPREQUEST",
                    "app_key": uuid.uuid4().hex[:32],
                    "username": portal_username,
                }
                res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    cache.set(cooldown_key, time.time(), timeout=30)
                    chal_key = f"gst_chal_{txn_id}"
                    cache.set(
                        chal_key,
                        {
                            "txn_id": txn_id,
                            "company_id": str(company.id),
                            "gstin": taxpayer_gstin,
                            "username": portal_username,
                            "created_at": time.time(),
                            "expires_at": time.time() + 600,
                            "attempts": 0
                        },
                        timeout=600
                    )
                    return {
                        "success": True,
                        "gstin": taxpayer_gstin,
                        "username": portal_username,
                        "txn_id": txn_id,
                        "cooldown_seconds": 30,
                        "message": "A verification OTP has been sent to your registered GST Portal mobile."
                    }
                else:
                    logger.warning(f"GST Portal OTP request returned {res.status_code}: {res.text}")
                    structured = get_structured_gst_error(res.text, status_code=res.status_code, category="otp_request", correlation_id=txn_id)
                    return {
                        "success": False,
                        "error": structured["message"],
                        "code": structured["code"],
                        "action": structured["action"],
                        "portal_help": structured.get("portal_help"),
                        "correlation_id": txn_id,
                    }
            except Exception as e:
                logger.exception(f"Error calling live GST Portal OTP: {e}")
                structured = get_structured_gst_error(str(e), status_code=500, category="otp_request", correlation_id=txn_id)
                return {
                    "success": False,
                    "error": structured["message"],
                    "code": structured["code"],
                    "action": structured["action"],
                    "correlation_id": txn_id,
                }

        # 6. Fallback when credentials unconfigured
        return {
            "success": False,
            "error": "GST Portal connection is temporarily unavailable. Please contact support if the problem continues.",
            "code": "CONFIGURATION_ERROR",
            "action": "CONTACT_SUPPORT",
        }

    # =========================================================================
    # STRICT TOKEN VALIDATION & AUTHENTICATION INTEGRITY (PHASE A)
    # =========================================================================

    @classmethod
    def verify_portal_otp(
        cls,
        company: Company,
        otp: str,
        txn_id: Optional[str] = None,
        gstin: Optional[str] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Step 2 of Direct GST Portal Filing:
        Submits taxpayer OTP to establish an authenticated session.
        Enforces strict contract validation:
        - NEVER uses correlation_id or fallback IDs as auth tokens
        - Validates successful status_cd
        - Validates future token expiry
        - Verifies returned GSTIN matches requested GSTIN
        - Persists token to GSTRegistration entity
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        config = cls.get_or_create_config(company)
        clean_otp = (otp or '').strip()

        if len(clean_otp) != 6 or not clean_otp.isdigit():
            return {
                "success": False,
                "code": "INCORRECT_OTP",
                "action": "REENTER_OTP",
                "error": "Please enter a valid 6-digit numeric OTP."
            }

        # 1. Challenge Binding & Brute-Force Shield (Atomic attempt tracking)
        chal_key = None
        challenge = None
        if txn_id:
            chal_key = f"gst_chal_{txn_id}"
            challenge = cache.get(chal_key)
            if not challenge:
                return {
                    "success": False,
                    "code": "CHALLENGE_EXPIRED",
                    "action": "REQUEST_NEW_OTP",
                    "error": "The OTP challenge has expired. Please request a new OTP to continue."
                }
            if challenge.get("company_id") != str(company.id) or challenge.get("gstin") != taxpayer_gstin:
                return {
                    "success": False,
                    "code": "INVALID_CHALLENGE",
                    "action": "REQUEST_NEW_OTP",
                    "error": "OTP challenge ownership mismatch. Please request a new OTP."
                }
            attempts = challenge.get("attempts", 0) + 1
            challenge["attempts"] = attempts
            if attempts > 5:
                cache.delete(chal_key)
                return {
                    "success": False,
                    "code": "MAX_ATTEMPTS_EXCEEDED",
                    "action": "REQUEST_NEW_OTP",
                    "error": "Too many incorrect OTP attempts. Please request a new OTP to continue."
                }
            cache.set(chal_key, challenge, timeout=600)
        else:
            attempts_key = f"gst_att_{company.id}_{taxpayer_gstin}"
            cache.add(attempts_key, 0, timeout=600)
            attempts = cache.incr(attempts_key)
            if attempts > 5:
                return {
                    "success": False,
                    "code": "MAX_ATTEMPTS_EXCEEDED",
                    "action": "REQUEST_NEW_OTP",
                    "error": "Too many incorrect OTP attempts. Please request a new OTP to continue."
                }

        # 2. Gateway Client Execution
        client = SandboxGSTClient(company=company, registration=reg)
        if not client.is_configured() and config.provider != 'MOCK':
            return {
                "success": False,
                "code": "GATEWAY_NOT_CONFIGURED",
                "action": "CONTACT_SUPPORT",
                "error": "GST Portal connection is temporarily unavailable. Gateway is not configured."
            }

        if client.is_configured():
            if config.provider == 'MOCK':
                config.provider = 'SANDBOX_CO_IN'
                config.save(update_fields=['provider', 'updated_at'])
            portal_user = (username or (reg.taxpayer_username if reg else '') or config.eway_username or company.email or taxpayer_gstin).strip()
            sb_res = client.verify_portal_otp(
                gstin=taxpayer_gstin,
                username=portal_user,
                otp=clean_otp
            )
            cid = sb_res.get('correlation_id') or txn_id or f"VERIFY-{uuid.uuid4().hex[:10].upper()}"

            if not sb_res.get('success'):
                raw_err = sb_res.get('error') or ''
                logger.error(
                    f"[GSTPortalService] OTP verify failed for company={company.id} "
                    f"gstin={taxpayer_gstin} correlation_id={cid}: {raw_err}"
                )
                status_code = sb_res.get('status_code', 400)
                structured = get_structured_gst_error(raw_err, status_code=status_code, category="otp_verify", correlation_id=cid)
                return {
                    "success": False,
                    "error": structured["message"],
                    "code": structured["code"],
                    "action": structured["action"],
                    "portal_help": structured.get("portal_help"),
                    "correlation_id": cid,
                }

            # 3. Strict Contract Validation on Successful HTTP Response
            sb_data = sb_res.get('data')
            if not isinstance(sb_data, dict):
                GSTAuditService.log_action(
                    company=company,
                    gst_registration=reg,
                    action='PORTAL_OTP_VERIFY',
                    correlation_id=cid,
                    endpoint='/gst/compliance/tax-payer/otp/verify',
                    http_method='POST',
                    status_code=400,
                    is_success=False,
                    error_message="Authentication rejected: Provider response missing dictionary payload data."
                )
                return {
                    "success": False,
                    "code": "INVALID_SESSION_TOKEN",
                    "action": "REQUEST_NEW_OTP",
                    "correlation_id": cid,
                    "error": "Authentication failed: Unexpected response format from provider."
                }

            # Check status_cd
            if sb_data.get('status_cd') == '0' or 'error' in sb_data:
                err_detail = sb_data.get('error')
                err_msg = err_detail.get('message') if isinstance(err_detail, dict) else (err_detail or "OTP verification rejected by GSTN.")
                structured = get_structured_gst_error(str(err_msg), status_code=400, category="otp_verify", correlation_id=cid)
                return {
                    "success": False,
                    "error": structured["message"],
                    "code": structured["code"],
                    "action": structured["action"],
                    "portal_help": structured.get("portal_help"),
                    "correlation_id": cid,
                }

            # Strict extraction of session token (ZERO fallback to correlation_id or dummy tokens)
            auth_token = sb_data.get('auth_token') or sb_data.get('access_token')
            if not auth_token or not isinstance(auth_token, str):
                GSTAuditService.log_action(
                    company=company,
                    gst_registration=reg,
                    action='PORTAL_OTP_VERIFY',
                    correlation_id=cid,
                    endpoint='/gst/compliance/tax-payer/otp/verify',
                    http_method='POST',
                    status_code=400,
                    is_success=False,
                    error_message="Authentication rejected: Provider response did not contain an auth_token or access_token."
                )
                return {
                    "success": False,
                    "code": "INVALID_SESSION_TOKEN",
                    "action": "REQUEST_NEW_OTP",
                    "correlation_id": cid,
                    "error": "Authentication failed: No valid taxpayer session token returned by provider."
                }

            auth_token = auth_token.strip()
            # Reject correlation IDs, placeholder tokens, or malformed strings
            if (
                len(auth_token) < 10
                or auth_token == cid
                or auth_token == txn_id
                or auth_token.startswith('CORR-')
                or auth_token.startswith('GST-')
                or auth_token.startswith('TXN-')
                or auth_token.startswith('CHAL-')
            ):
                GSTAuditService.log_action(
                    company=company,
                    gst_registration=reg,
                    action='PORTAL_OTP_VERIFY',
                    correlation_id=cid,
                    endpoint='/gst/compliance/tax-payer/otp/verify',
                    http_method='POST',
                    status_code=400,
                    is_success=False,
                    error_message="Authentication rejected: Session token is malformed or matches request correlation ID."
                )
                return {
                    "success": False,
                    "code": "INVALID_SESSION_TOKEN",
                    "action": "REQUEST_NEW_OTP",
                    "correlation_id": cid,
                    "error": "Authentication failed: Malformed taxpayer session token rejected."
                }

            # Expiry validation
            token_expiry_raw = (
                sb_data.get('session_expiry')
                or sb_data.get('token_expiry')
                or sb_data.get('expiry')
                or sb_data.get('expires_at')
            )
            if not token_expiry_raw:
                GSTAuditService.log_action(
                    company=company,
                    gst_registration=reg,
                    action='PORTAL_OTP_VERIFY',
                    correlation_id=cid,
                    endpoint='/gst/compliance/tax-payer/otp/verify',
                    http_method='POST',
                    status_code=400,
                    is_success=False,
                    error_message="Authentication rejected: Missing session expiry timestamp in provider response."
                )
                return {
                    "success": False,
                    "code": "INVALID_EXPIRY",
                    "action": "REQUEST_NEW_OTP",
                    "correlation_id": cid,
                    "error": "Authentication failed: Session expiry timestamp missing from provider."
                }

            try:
                expires_at = None
                raw_str = str(token_expiry_raw).strip()
                if raw_str.isdigit():
                    exp_val = int(raw_str)
                    if exp_val > 1e11:  # ms
                        expires_at = datetime.fromtimestamp(exp_val / 1000.0, tz=dt_timezone.utc)
                    elif exp_val > 1e8:  # seconds
                        expires_at = datetime.fromtimestamp(exp_val, tz=dt_timezone.utc)
                    else:
                        expires_at = timezone.now() + timedelta(seconds=exp_val)
                else:
                    from django.utils.dateparse import parse_datetime
                    dt = parse_datetime(raw_str)
                    if not dt:
                        from dateutil import parser
                        dt = parser.parse(raw_str)
                    expires_at = dt

                if expires_at and timezone.is_naive(expires_at):
                    expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

                if not expires_at or expires_at <= timezone.now():
                    GSTAuditService.log_action(
                        company=company,
                        gst_registration=reg,
                        action='PORTAL_OTP_VERIFY',
                        correlation_id=cid,
                        endpoint='/gst/compliance/tax-payer/otp/verify',
                        http_method='POST',
                        status_code=400,
                        is_success=False,
                        error_message="Authentication rejected: Session expiry timestamp is in the past."
                    )
                    return {
                        "success": False,
                        "code": "INVALID_EXPIRY",
                        "action": "REQUEST_NEW_OTP",
                        "correlation_id": cid,
                        "error": "Authentication failed: Session expiry timestamp is in the past."
                    }
            except Exception:
                GSTAuditService.log_action(
                    company=company,
                    gst_registration=reg,
                    action='PORTAL_OTP_VERIFY',
                    correlation_id=cid,
                    endpoint='/gst/compliance/tax-payer/otp/verify',
                    http_method='POST',
                    status_code=400,
                    is_success=False,
                    error_message="Authentication rejected: Session expiry timestamp could not be parsed."
                )
                return {
                    "success": False,
                    "code": "INVALID_EXPIRY",
                    "action": "REQUEST_NEW_OTP",
                    "correlation_id": cid,
                    "error": "Authentication failed: Session expiry timestamp format is invalid."
                }

            # GSTIN mismatch check
            resp_gstin = (sb_data.get('gstin') or '').strip().upper()
            if resp_gstin and resp_gstin != taxpayer_gstin:
                GSTAuditService.log_action(
                    company=company,
                    gst_registration=reg,
                    action='PORTAL_OTP_VERIFY',
                    correlation_id=cid,
                    endpoint='/gst/compliance/tax-payer/otp/verify',
                    http_method='POST',
                    status_code=400,
                    is_success=False,
                    error_message=f"Authentication rejected: GSTIN mismatch ({resp_gstin} != {taxpayer_gstin})."
                )
                return {
                    "success": False,
                    "code": "GSTIN_MISMATCH",
                    "action": "VERIFY_GSTIN",
                    "correlation_id": cid,
                    "error": f"Authentication failed: GSTIN in session ({resp_gstin}) does not match registration ({taxpayer_gstin})."
                }

            # All validations passed: Persist encrypted token to GSTRegistration
            cls.persist_session_token(company, taxpayer_gstin, auth_token, expires_at, portal_user)

            # Invalidate challenge after successful verification
            if chal_key:
                cache.delete(chal_key)

            return {
                "success": True,
                "is_connected": True,
                "token_expires_at": expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                "message": "Your GST Portal account has been connected successfully."
            }

        # 3. Live Government NIC Direct API
        if not config.is_sandbox and config.api_key and config.provider == 'NIC_DIRECT':
            try:
                endpoint = f"{cls.PRODUCTION_BASE_URL}/authenticate"
                headers = {
                    "clientid": config.api_key,
                    "client-secret": config.api_secret,
                    "state-cd": taxpayer_gstin[:2],
                    "txn": txn_id or f"TXN-{uuid.uuid4().hex[:12].upper()}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "action": "AUTHTOKEN",
                    "username": username or config.eway_username or 'taxpayer',
                    "otp": clean_otp,
                }
                res = requests.post(endpoint, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    auth_token = data.get("auth_token")
                    if not auth_token or len(auth_token) < 10:
                        return {"success": False, "code": "INVALID_SESSION_TOKEN", "error": "Invalid token from NIC portal."}
                    expires_at = timezone.now() + timedelta(hours=6)
                    cls.persist_session_token(company, taxpayer_gstin, auth_token, expires_at, payload["username"])
                    return {
                        "success": True,
                        "token_expires_at": expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        "message": "GST Portal session authenticated successfully."
                    }
                else:
                    return {
                        "success": False,
                        "error": f"GST Portal rejected OTP (HTTP {res.status_code}): {res.text[:300]}"
                    }
            except Exception as e:
                logger.exception(f"Error validating live GST OTP: {e}")
                return {
                    "success": False,
                    "error": f"Error contacting live GST Portal: {str(e)}"
                }

        return {
            "success": False,
            "error": "GST Portal connection is temporarily unavailable. Please contact support if the problem continues.",
            "code": "CONFIGURATION_ERROR",
            "action": "CONTACT_SUPPORT"
        }

    # =========================================================================
    # SESSION REFRESH & DISCONNECT SEMANTICS (PHASE G)
    # =========================================================================

    @classmethod
    def refresh_portal_session(cls, company: Company, gstin: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Phase G: Extends an active taxpayer compliance session token with Sandbox.
        Validates refreshed token format and expiry; marks session expired if rejected.
        """
        sess = cls.get_session_info(company, gstin)
        taxpayer_gstin = sess["gstin"]
        active_token = sess["auth_token"]
        reg = sess["registration"]

        if not active_token:
            return {
                "success": False,
                "code": "NO_ACTIVE_SESSION",
                "action": "CONNECT_PORTAL",
                "error": "No active GST Portal session found to refresh. Please connect using OTP."
            }

        client = SandboxGSTClient(company=company, registration=reg)
        if client.is_configured():
            sb_res = client.refresh_portal_session(session_token=active_token)
            if not sb_res.get('success'):
                raw_err = sb_res.get('error') or ''
                # Session expired on provider side; revoke locally to prevent silent failures
                cls.clear_session_token(company, taxpayer_gstin)
                status_code = sb_res.get('status_code', 400)
                structured = get_structured_gst_error(raw_err, status_code=status_code, category="otp_verify")
                return {
                    "success": False,
                    "code": "EXPIRED_SESSION",
                    "action": "RECONNECT",
                    "error": structured["message"]
                }

            sb_data = sb_res.get('data') or {}
            new_token = sb_data.get('access_token') or sb_data.get('auth_token')
            if not new_token or not isinstance(new_token, str) or len(new_token.strip()) < 10:
                cls.clear_session_token(company, taxpayer_gstin)
                return {
                    "success": False,
                    "code": "INVALID_SESSION_TOKEN",
                    "action": "RECONNECT",
                    "error": "Provider response did not contain a valid refreshed session token."
                }

            expiry_raw = (
                sb_data.get('session_expiry')
                or sb_data.get('token_expiry')
                or sb_data.get('expiry')
                or sb_data.get('expires_at')
            )
            if not expiry_raw:
                cls.clear_session_token(company, taxpayer_gstin)
                return {
                    "success": False,
                    "code": "INVALID_EXPIRY",
                    "action": "RECONNECT",
                    "error": "Refreshed session missing expiry timestamp."
                }

            try:
                expires_at = None
                raw_str = str(expiry_raw).strip()
                if raw_str.isdigit():
                    exp_val = int(raw_str)
                    if exp_val > 1e11:
                        expires_at = datetime.fromtimestamp(exp_val / 1000.0, tz=dt_timezone.utc)
                    elif exp_val > 1e8:
                        expires_at = datetime.fromtimestamp(exp_val, tz=dt_timezone.utc)
                    else:
                        expires_at = timezone.now() + timedelta(seconds=exp_val)
                else:
                    from django.utils.dateparse import parse_datetime
                    dt = parse_datetime(raw_str)
                    if not dt:
                        from dateutil import parser
                        dt = parser.parse(raw_str)
                    expires_at = dt

                if expires_at and timezone.is_naive(expires_at):
                    expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

                if not expires_at or expires_at <= timezone.now():
                    cls.clear_session_token(company, taxpayer_gstin)
                    return {
                        "success": False,
                        "code": "INVALID_EXPIRY",
                        "action": "RECONNECT",
                        "error": "Refreshed session expiry timestamp is in the past."
                    }
            except Exception:
                cls.clear_session_token(company, taxpayer_gstin)
                return {
                    "success": False,
                    "code": "INVALID_EXPIRY",
                    "action": "RECONNECT",
                    "error": "Refreshed session expiry timestamp could not be parsed."
                }

            cls.persist_session_token(company, taxpayer_gstin, new_token.strip(), expires_at, sess["username"])

            return {
                "success": True,
                "is_connected": True,
                "token": new_token.strip(),
                "token_expires_at": expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                "message": "GST Portal session refreshed successfully."
            }

        return {
            "success": False,
            "code": "GATEWAY_NOT_CONFIGURED",
            "action": "CONTACT_SUPPORT",
            "error": "GST Portal connection is temporarily unavailable. Gateway is not configured."
        }

    @classmethod
    def disconnect_portal_session(cls, company: Company, gstin: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Phase G: Disconnect and Remote Logout.
        Distinguishes local revocation from confirmed remote revocation.
        """
        sess = cls.get_session_info(company, gstin)
        taxpayer_gstin = sess["gstin"]
        old_token = sess["auth_token"]
        reg = sess["registration"]

        remote_confirmed = False
        if old_token:
            client = SandboxGSTClient(company=company, registration=reg)
            if client.is_configured():
                try:
                    res = client.logout_portal_session(session_token=old_token)
                    remote_confirmed = bool(res.get('success'))
                except Exception as e:
                    logger.warning(f"[GSTPortalService] Remote session logout exception: {e}")
                    remote_confirmed = False

        cls.clear_session_token(company, taxpayer_gstin)

        return {
            "success": True,
            "is_connected": False,
            "local_revoked": True,
            "remote_logout_confirmed": remote_confirmed,
            "remote_status": "CONFIRMED" if remote_confirmed else "NOT_CONFIRMED",
            "message": "GST Portal session disconnected successfully." if remote_confirmed else "GST Portal session disconnected locally. Remote session invalidation could not be confirmed with provider."
        }

    # =========================================================================
    # GSTR-1 DIRECT FILING INTEGRITY (PHASE C)
    # =========================================================================

    @classmethod
    def upload_gstr1_direct(
        cls,
        company: Company,
        start_date: str,
        end_date: str,
        gstin: Optional[str] = None,
        auth_token: Optional[str] = None,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Phase C: Statutory Return Filing Integrity.
        STRICT RULES:
        - ZERO mock/hardcoded OTP authentication fallback (e.g. "575757" permanently eliminated).
        - Requires an active, non-expired taxpayer session token.
        - ZERO fabricated ARNs (e.g. "REF-G1-..." or random UUID ARNs permanently eliminated).
        - Persists official ARN ONLY when returned by authenticated GSTN/provider response.
        - Idempotent submission state machine: DRAFT -> SUBMITTING -> SUBMITTED -> FILED / FAILED / RECONCILIATION_REQUIRED.
        """
        sess = cls.get_session_info(company, gstin)
        taxpayer_gstin = sess["gstin"]
        reg = sess["registration"]
        active_token = auth_token or sess["auth_token"]

        # 1. Strict Authentication Check: NO hardcoded OTP fallback
        if not active_token or sess["is_expired"]:
            return {
                "success": False,
                "code": "AUTHENTICATION_REQUIRED",
                "action": "CONNECT_PORTAL",
                "error": "No active GST Portal session found for this GSTIN. Please authenticate via OTP before submitting returns."
            }

        # 2. Gateway Client Verification
        client = SandboxGSTClient(company=company, registration=reg)
        if not client.is_configured():
            return {
                "success": False,
                "code": "GATEWAY_NOT_CONFIGURED",
                "action": "CONTACT_SUPPORT",
                "error": "GST Gateway API is not configured. Please supply API credentials."
            }

        # 3. Compile official GSTR-1 payload from vouchers
        gstr1_data = GSTRReportService.generate_gstr1(company, start_date, end_date)
        period_val = gstr1_data.get("fp", "") or datetime.now().strftime("%m%Y")
        corr_id = f"TXN-G1-{uuid.uuid4().hex[:12].upper()}"

        b2b_list = gstr1_data.get('b2b', [])
        b2cs_list = gstr1_data.get('b2cs', [])
        cdnr_list = gstr1_data.get('cdnr', [])
        hsn_list = gstr1_data.get('hsn', {}).get('data', [])

        total_b2b_invs = sum(len(party.get('inv', [])) for party in b2b_list)
        total_cdnr_notes = sum(len(party.get('nt', [])) for party in cdnr_list)
        total_taxable = sum(float(item.get('txval', 0.0)) for item in hsn_list)
        total_tax = sum(float(item.get('iamt', 0.0)) + float(item.get('camt', 0.0)) + float(item.get('samt', 0.0)) for item in hsn_list)

        # 4. Check for existing filings in the same period
        existing_filing = GSTFilingRecord.objects.filter(
            company=company,
            return_type='GSTR1',
            return_period=period_val,
            gst_registration=reg
        ).first()

        if existing_filing:
            if existing_filing.status == 'FILED' and existing_filing.arn:
                return {
                    "success": False,
                    "code": "ALREADY_FILED",
                    "action": "VIEW_FILED_RETURN",
                    "arn": existing_filing.arn,
                    "filing_id": str(existing_filing.id),
                    "error": f"GSTR-1 for period {period_val} is already confirmed FILED with government ARN: {existing_filing.arn}."
                }
            if existing_filing.status == 'SUBMITTED' and not existing_filing.arn:
                return {
                    "success": False,
                    "code": "SUBMISSION_PENDING",
                    "action": "CHECK_STATUS",
                    "provider_reference": existing_filing.provider_reference,
                    "filing_id": str(existing_filing.id),
                    "error": f"A previous submission for period {period_val} is currently pending processing on GST Portal (Reference: {existing_filing.provider_reference}). Please check status instead of re-submitting."
                }

        # 5. Record SUBMITTING state before network call
        filing_rec, _ = GSTFilingRecord.objects.update_or_create(
            company=company,
            return_type='GSTR1',
            return_period=period_val,
            defaults={
                "gst_registration": reg,
                "status": "SUBMITTING",
                "arn": "",  # Strictly empty string! NEVER fabricate an ARN!
                "provider_reference": corr_id,
                "filing_mode": "DIRECT_PORTAL",
                "total_taxable_value": round(total_taxable, 2),
                "total_tax_amount": round(total_tax, 2),
                "invoices_count": total_b2b_invs + len(b2cs_list),
                "submitted_by": user if getattr(user, 'is_authenticated', False) else None
            }
        )

        # 6. Dispatch Payload to Sandbox / GST Portal
        try:
            res = client.save_gstr1(payload=gstr1_data, session_token=active_token, user=user)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            logger.exception(f"GSTR-1 submission network failure/timeout: {exc}")
            filing_rec.status = 'RECONCILIATION_REQUIRED'
            filing_rec.error_message = f"Network timeout during submission. Outcome pending reconciliation. ({exc})"
            filing_rec.save(update_fields=['status', 'error_message', 'updated_at'])
            return {
                "success": False,
                "code": "RECONCILIATION_REQUIRED",
                "status": "RECONCILIATION_REQUIRED",
                "filing_id": str(filing_rec.id),
                "provider_reference": corr_id,
                "action": "CHECK_STATUS",
                "error": "The connection timed out during submission. The return status is pending reconciliation with the GST Portal."
            }

        # 7. Evaluate Provider Response
        if not res.get("success"):
            raw_err = res.get("error", "GST Portal rejected return submission.")
            status_code = res.get("status_code", 400)
            if status_code in (502, 503, 504) or 'timeout' in str(raw_err).lower():
                filing_rec.status = 'RECONCILIATION_REQUIRED'
                filing_rec.error_message = f"Gateway timeout ({status_code}). Outcome pending reconciliation. ({raw_err})"
                filing_rec.save(update_fields=['status', 'error_message', 'updated_at'])
                return {
                    "success": False,
                    "code": "RECONCILIATION_REQUIRED",
                    "status": "RECONCILIATION_REQUIRED",
                    "filing_id": str(filing_rec.id),
                    "provider_reference": corr_id,
                    "action": "CHECK_STATUS",
                    "error": "The connection timed out during submission. The return status is pending reconciliation with the GST Portal."
                }
            filing_rec.status = 'FAILED'
            filing_rec.error_message = raw_err
            filing_rec.response_snapshot = res.get("data") or res.get("raw") or {}
            filing_rec.save(update_fields=['status', 'error_message', 'response_snapshot', 'updated_at'])
            return {
                "success": False,
                "code": "SUBMISSION_REJECTED",
                "status": "FAILED",
                "filing_id": str(filing_rec.id),
                "error": raw_err
            }

        # 8. Success: Provider accepted submission
        resp_data = res.get("data") or {}
        provider_ref = resp_data.get("reference_id") or resp_data.get("ref_id") or corr_id
        gov_arn = resp_data.get("arn") or ""  # Only authentic government ARN

        final_status = 'FILED' if gov_arn else 'SUBMITTED'
        filing_rec.status = final_status
        filing_rec.arn = gov_arn
        filing_rec.provider_reference = provider_ref
        filing_rec.response_snapshot = resp_data
        filing_rec.save(update_fields=['status', 'arn', 'provider_reference', 'response_snapshot', 'updated_at'])

        return {
            "success": True,
            "status": final_status,
            "filing_id": str(filing_rec.id),
            "provider_reference": provider_ref,
            "ref_id": provider_ref,
            "arn": gov_arn or "",
            "period": period_val,
            "gstin": taxpayer_gstin,
            "b2b_invoices_uploaded": total_b2b_invs,
            "b2cs_entries_uploaded": len(b2cs_list),
            "cdnr_notes_uploaded": total_cdnr_notes,
            "hsn_entries_uploaded": len(hsn_list),
            "total_taxable_value": round(total_taxable, 2),
            "total_tax_amount": round(total_tax, 2),
            "message": f"GSTR-1 return successfully submitted to GST Portal. Reference ID: {provider_ref}" if not gov_arn else f"GSTR-1 return filed. Government ARN: {gov_arn}"
        }

    @classmethod
    def get_portal_status(cls, company: Company, ref_id: str, gstin: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Reconciles processing status of a previously submitted GSTR-1 batch.
        Updates GSTFilingRecord idempotently upon receiving government processing confirmation.
        """
        reg, taxpayer_gstin = cls.resolve_registration(company, gstin)
        filing = GSTFilingRecord.objects.filter(company=company, provider_reference=ref_id).first()
        if not filing:
            filing = GSTFilingRecord.objects.filter(company=company, arn=ref_id).first()

        # If already confirmed FILED with real ARN, return immediately
        if filing and filing.status == 'FILED' and filing.arn:
            return {
                "success": True,
                "reference_id": ref_id,
                "arn": filing.arn,
                "status": "FILED",
                "filing_id": str(filing.id),
                "message": f"Return is confirmed FILED with government ARN: {filing.arn}"
            }

        client = SandboxGSTClient(company=company, registration=reg)
        sess = cls.get_session_info(company, taxpayer_gstin)
        active_token = sess["auth_token"]

        if not client.is_configured() or not active_token:
            current_status = filing.status if filing else "UNKNOWN"
            return {
                "success": False,
                "reference_id": ref_id,
                "status": current_status,
                "reconciliation_required": True,
                "error": "Cannot contact GST Portal to query status: Session or credentials unavailable."
            }

        period = filing.return_period if filing else datetime.now().strftime("%m%Y")
        year = period[-4:] if len(period) >= 4 else datetime.now().strftime("%Y")
        month = period[:2] if len(period) >= 6 else datetime.now().strftime("%m")

        status_res = client.get_gstr_status(year=year, month=month, ref_id=ref_id, session_token=active_token, user=user)
        if not status_res.get("success"):
            return {
                "success": False,
                "reference_id": ref_id,
                "status": filing.status if filing else "UNKNOWN",
                "reconciliation_required": True,
                "error": status_res.get("error", "Error checking status on GST Portal.")
            }

        data = status_res.get("data") or {}
        gov_status = (data.get("status") or data.get("status_cd") or "").upper()
        gov_arn = data.get("arn") or ""

        if gov_arn or gov_status in ('PROCESSED', 'FILED', '1'):
            if filing:
                filing.status = 'FILED'
                if gov_arn:
                    filing.arn = gov_arn
                filing.response_snapshot = data
                filing.save(update_fields=['status', 'arn', 'response_snapshot', 'updated_at'])
            return {
                "success": True,
                "reference_id": ref_id,
                "arn": gov_arn or None,
                "status": "FILED",
                "message": "Return processing complete. Confirmed on GST Portal."
            }
        elif gov_status in ('ERROR', 'REJECTED', 'FAILED', '0'):
            err_msg = data.get("error_report") or data.get("error") or "GSTN reported validation errors."
            if filing:
                filing.status = 'FAILED'
                filing.error_message = str(err_msg)
                filing.save(update_fields=['status', 'error_message', 'updated_at'])
            return {
                "success": False,
                "reference_id": ref_id,
                "status": "FAILED",
                "error": str(err_msg)
            }

        return {
            "success": True,
            "reference_id": ref_id,
            "status": "SUBMITTED",
            "message": "Return is currently being processed by the GST Common Portal."
        }

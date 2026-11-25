import os
import uuid
import time
import random
import logging
import requests
from urllib.parse import urlparse
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from apps.companies.models import Company
from apps.gst.models import CompanyGSTConfig, GSTRegistration
from apps.gst.exceptions import (
    GSTIntegrationError,
    GSTConfigurationMissingError,
    GSTAuthenticationError,
    GSTRateLimitExceededError,
)
from apps.gst.services.audit_service import GSTAuditService
from apps.gst.services.gst_error_normalizer import sanitize_audit_payload

logger = logging.getLogger('apps.gst.sandbox_client')


class SandboxGSTClient:
    """
    Authoritative Provider Client for Sandbox by Quicko (https://sandbox.co.in).
    Handles:
    - Base URL & host allowlist validation (SSRF protection)
    - /authenticate token exchange & dual caching (DB + Django cache)
    - Token stampede prevention under high concurrency
    - Header management (x-api-key, authorization, x-api-version)
    - Connection timeouts, bounded exponential backoff with jitter for idempotent calls
    - Error normalization and credential redaction
    - Structured audit logging via GSTAuditService
    """

    DEFAULT_BASE_URL = "https://api.sandbox.co.in"
    DEFAULT_TEST_URL = "https://test-api.sandbox.co.in"
    API_VERSION = "1.0.0"

    ALLOWED_SANDBOX_HOSTS = {
        'api.sandbox.co.in',
        'test-api.sandbox.co.in',
    }

    def __init__(self, company: Optional[Company] = None, registration: Optional[GSTRegistration] = None):
        self.company = company
        self.registration = registration
        self.config = self._load_config()

    def _load_config(self) -> Optional[CompanyGSTConfig]:
        if not self.company:
            return None
        return CompanyGSTConfig.objects.filter(company=self.company).first()

    def get_api_credentials(self) -> tuple[str, str, str, bool]:
        """
        Resolves API Key, Secret, Base URL, and Sandbox mode.
        Enforces SSRF host allowlist checks.
        Checks CompanyGSTConfig first, then falls back to Django settings / Render environment.
        """
        api_key = ''
        api_secret = ''
        base_url = (
            getattr(settings, 'SANDBOX_BASE_URL', '')
            or getattr(settings, 'GST_SANDBOX_BASE_URL', '')
            or os.environ.get('SANDBOX_BASE_URL', '')
            or os.environ.get('GST_SANDBOX_BASE_URL', '')
            or self.DEFAULT_BASE_URL
        )
        is_sandbox = False

        if self.config:
            k = (self.config.sandbox_api_key or self.config.api_key or '').strip()
            s = (self.config.sandbox_api_secret or self.config.api_secret or '').strip()
            # Ignore placeholder mock values
            if k and not k.startswith('sandbox_api_key_vouch'):
                api_key = k
            if s and not s.startswith('sandbox_api_secret_vouch'):
                api_secret = s
            if self.config.sandbox_base_url:
                base_url = self.config.sandbox_base_url
            is_sandbox = self.config.is_sandbox

        if not api_key:
            api_key = (
                getattr(settings, 'SANDBOX_API_KEY', '')
                or getattr(settings, 'GST_SANDBOX_API_KEY', '')
                or getattr(settings, 'QUICKO_API_KEY', '')
                or os.environ.get('SANDBOX_API_KEY', '')
                or os.environ.get('GST_SANDBOX_API_KEY', '')
                or os.environ.get('QUICKO_API_KEY', '')
                or os.environ.get('SANDBOX_KEY', '')
                or os.environ.get('GST_API_KEY', '')
                or os.environ.get('SANDBOX_CO_IN_API_KEY', '')
                or os.environ.get('SANDBOX_CO_IN_KEY', '')
                or os.environ.get('GST_CLIENT_ID', '')
                or os.environ.get('API_KEY', '')
            )
        if not api_secret:
            api_secret = (
                getattr(settings, 'SANDBOX_API_SECRET', '')
                or getattr(settings, 'GST_SANDBOX_API_SECRET', '')
                or getattr(settings, 'QUICKO_API_SECRET', '')
                or os.environ.get('SANDBOX_API_SECRET', '')
                or os.environ.get('GST_SANDBOX_API_SECRET', '')
                or os.environ.get('QUICKO_API_SECRET', '')
                or os.environ.get('SANDBOX_SECRET', '')
                or os.environ.get('GST_API_SECRET', '')
                or os.environ.get('SANDBOX_CO_IN_API_SECRET', '')
                or os.environ.get('SANDBOX_CO_IN_SECRET', '')
                or os.environ.get('GST_CLIENT_SECRET', '')
                or os.environ.get('API_SECRET', '')
            )

        if api_key:
            api_key = str(api_key).strip().strip('"').strip("'")
        if api_secret:
            api_secret = str(api_secret).strip().strip('"').strip("'")

        # Adjust base URL for explicit sandbox environment if configured
        env_mode = getattr(settings, 'GST_SANDBOX_ENV', '') or os.environ.get('GST_SANDBOX_ENV', 'staging')
        if is_sandbox and 'test-api' in env_mode:
            base_url = self.DEFAULT_TEST_URL

        # SSRF Protection: Validate base_url against explicit allowlist of HTTPS hosts
        clean_url = str(base_url).strip()
        parsed = urlparse(clean_url)
        if parsed.scheme != 'https' or parsed.netloc not in self.ALLOWED_SANDBOX_HOSTS:
            logger.warning(
                f"Untrusted, insecure, or invalid Sandbox base URL '{clean_url}'. "
                f"Resetting to authoritative DEFAULT_BASE_URL for security."
            )
            clean_url = self.DEFAULT_TEST_URL if (is_sandbox and 'test-api' in env_mode) else self.DEFAULT_BASE_URL

        return api_key, api_secret, clean_url, is_sandbox

    def is_configured(self) -> bool:
        api_key, api_secret, base_url, _ = self.get_api_credentials()
        return bool(api_key and api_secret and base_url)

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Retrieves valid JWT access token from Quicko Sandbox.
        Reuses cached token if valid; otherwise executes POST /authenticate.
        Dual caching:
        1. Database cache via CompanyGSTConfig.sandbox_access_token
        2. Django memory/distributed cache (prevents token stampedes when config row is absent)
        """
        api_key, api_secret, base_url, _ = self.get_api_credentials()

        if not api_key or not api_secret:
            raise GSTConfigurationMissingError(
                "Sandbox GST API credentials (API Key and Secret) are missing. "
                "Please configure GST Sandbox settings."
            )

        now = timezone.now()
        cache_key = f"gst_sandbox_token_{str(self.company.id) if self.company else 'global'}"

        # 1. Check existing cached token if not force_refresh
        if not force_refresh:
            if self.config and self.config.sandbox_access_token:
                if self.config.sandbox_token_expires_at and self.config.sandbox_token_expires_at > (now + timedelta(minutes=5)):
                    return self.config.sandbox_access_token

            cached_token = cache.get(cache_key)
            if cached_token:
                return cached_token

        # 2. Exchange API Key & Secret for JWT token via POST /authenticate
        endpoint = f"{base_url}/authenticate"
        correlation_id = f"AUTH-{uuid.uuid4().hex[:12].upper()}"
        headers = {
            "x-api-key": api_key,
            "x-api-secret": api_secret,
            "x-api-version": self.API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-transaction-id": correlation_id,
        }

        try:
            res = requests.request('POST', endpoint, headers=headers, timeout=12)
            status_code = res.status_code

            if status_code == 200:
                data = res.json()
                payload_data = data.get('data') if isinstance(data.get('data'), dict) else {}
                
                # Robust token extraction (top-level or nested under 'data')
                token = (
                    data.get('access_token')
                    or payload_data.get('access_token')
                    or (data.get('data') if isinstance(data.get('data'), str) else '')
                    or ''
                )

                # Robust expiry extraction (top-level or nested under 'data')
                raw_exp = data.get('expires_in') or payload_data.get('expires_in')
                try:
                    expires_in = int(raw_exp) if raw_exp is not None else 86400
                except (ValueError, TypeError):
                    expires_in = 86400

                if not token:
                    raise GSTAuthenticationError(f"Sandbox /authenticate returned 200 but missing access_token.")

                # Cache in Django cache to prevent stampede (5-minute buffer)
                cache_ttl = max(60, expires_in - 300)
                cache.set(cache_key, token, timeout=cache_ttl)

                # Cache in CompanyGSTConfig if available
                if self.config:
                    self.config.sandbox_access_token = token
                    self.config.sandbox_token_expires_at = now + timedelta(seconds=expires_in)
                    self.config.save(update_fields=['sandbox_access_token', 'sandbox_token_expires_at'])

                GSTAuditService.log_action(
                    company=self.company,
                    gst_registration=self.registration,
                    action='AUTH_TOKEN',
                    correlation_id=correlation_id,
                    endpoint='/authenticate',
                    http_method='POST',
                    status_code=200,
                    is_success=True,
                    request_summary={"endpoint": "/authenticate", "key_prefix": api_key[:4] + "***"},
                    response_summary={"status": "authenticated", "expires_in": expires_in}
                )
                return token
            elif status_code == 401 or status_code == 403:
                # Sanitize error message to prevent credential echo
                sanitized_text = res.text[:500].replace(api_key, "***").replace(api_secret, "***")
                raise GSTAuthenticationError(
                    f"Authentication failed with Sandbox (HTTP {status_code}): {sanitized_text}"
                )
            elif status_code == 429:
                raise GSTRateLimitExceededError("Rate limit exceeded while authenticating with Sandbox.")
            else:
                sanitized_text = res.text[:500].replace(api_key, "***").replace(api_secret, "***")
                raise GSTIntegrationError(
                    f"Sandbox /authenticate responded with HTTP {status_code}: {sanitized_text}",
                    status_code=status_code
                )
        except requests.exceptions.Timeout as e:
            raise GSTIntegrationError("Connection timed out contacting Sandbox /authenticate.", status_code=504)
        except requests.exceptions.RequestException as e:
            raise GSTIntegrationError("Network error communicating with Sandbox /authenticate.", status_code=502)

    def _get_authorized_headers(
        self,
        custom_session_token: Optional[str] = None,
        source: str = "primary",
        omit_source: bool = False
    ) -> tuple[Dict[str, str], str]:
        """
        Builds standard authorized headers for Sandbox GST endpoints.
        """
        api_key, _, _, _ = self.get_api_credentials()
        token = custom_session_token or self.get_access_token()
        correlation_id = f"GST-{uuid.uuid4().hex[:12].upper()}"

        headers = {
            "authorization": token,
            "x-api-key": api_key,
            "x-api-version": self.API_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-transaction-id": correlation_id,
        }
        if not omit_source:
            headers["x-source"] = source or "primary"
        return headers, correlation_id

    def execute_request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        custom_session_token: Optional[str] = None,
        source: str = "primary",
        omit_source: bool = False,
        headers_override: Optional[Dict[str, str]] = None,
        action: str = 'GST_API_CALL',
        user: Any = None,
        allow_retries: bool = False
    ) -> Dict[str, Any]:
        """
        Central request dispatcher with:
        - Header injection
        - Timeout handling
        - Safe retry logic with bounded jittered exponential backoff for idempotent calls
        - Strict fail-closed semantics for non-idempotent operations
        - Audit logging with credential redaction
        """
        _, _, base_url, _ = self.get_api_credentials()
        endpoint = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        headers, correlation_id = self._get_authorized_headers(
            custom_session_token=custom_session_token,
            source=source,
            omit_source=omit_source
        )
        if headers_override:
            headers.update(headers_override)

        max_attempts = 3 if allow_retries else 1
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            t0 = time.time()
            try:
                res = requests.request(
                    method=method.upper(),
                    url=endpoint,
                    json=payload if payload and method.upper() in ['POST', 'PUT', 'PATCH'] else None,
                    params=params,
                    headers=headers,
                    timeout=15
                )
                duration = time.time() - t0
                status_code = res.status_code

                # Handle 401 token expiry retry (once)
                if status_code == 401 and attempt == 1 and not custom_session_token:
                    logger.info("Sandbox access token expired; refreshing token and retrying request.")
                    new_token = self.get_access_token(force_refresh=True)
                    headers["authorization"] = new_token
                    continue

                # Rate limiting (HTTP 429) - exponential backoff with jitter
                if status_code == 429:
                    if allow_retries and attempt < max_attempts:
                        backoff = (1.5 * attempt) + random.uniform(0.1, 0.4)
                        time.sleep(backoff)
                        continue
                    raise GSTRateLimitExceededError("Sandbox rate limit reached for this endpoint.")

                # Try JSON parse
                try:
                    response_json = res.json()
                except Exception:
                    response_json = {"raw_text": res.text[:2000]}

                is_success = 200 <= status_code < 300
                data_payload = response_json.get('data') if isinstance(response_json, dict) else {}
                if is_success and isinstance(data_payload, dict):
                    if data_payload.get('status_cd') == '0' or 'error' in data_payload:
                        is_success = False

                # Audit log with sensitive credential redaction
                if self.company:
                    clean_req = sanitize_audit_payload({"path": path, "payload": payload, "params": params})
                    clean_res = sanitize_audit_payload(response_json if isinstance(response_json, dict) else {"status": status_code})
                    GSTAuditService.log_action(
                        company=self.company,
                        gst_registration=self.registration,
                        action=action,
                        correlation_id=correlation_id,
                        endpoint=path,
                        http_method=method.upper(),
                        status_code=status_code,
                        is_success=is_success,
                        request_summary=clean_req,
                        response_summary=clean_res,
                        error_message="" if is_success else str(clean_res)[:1000],
                        user=user
                    )

                if is_success:
                    return {
                        "success": True,
                        "status_code": status_code,
                        "data": response_json.get('data', response_json),
                        "raw": response_json,
                        "correlation_id": correlation_id,
                    }
                else:
                    err_detail = data_payload.get('error') if isinstance(data_payload, dict) else None
                    if err_detail and isinstance(err_detail, dict):
                        err_msg = err_detail.get('message') or str(err_detail)
                    elif err_detail:
                        err_msg = str(err_detail)
                    else:
                        err_msg = (
                            response_json.get('message')
                            or response_json.get('error')
                            or f"Sandbox responded with HTTP {status_code}"
                        )
                    return {
                        "success": False,
                        "status_code": status_code,
                        "error": str(err_msg),
                        "data": response_json.get('data', {}),
                        "raw": response_json,
                        "correlation_id": correlation_id,
                    }

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exception = e
                if allow_retries and attempt < max_attempts:
                    backoff = (1.0 * attempt) + random.uniform(0.1, 0.3)
                    time.sleep(backoff)
                    continue
                break

        # If loop exited on network failure
        err_text = f"Connection to Sandbox failed after {attempt} attempt(s): {type(last_exception).__name__}"
        if self.company:
            GSTAuditService.log_action(
                company=self.company,
                gst_registration=self.registration,
                action=action,
                correlation_id=correlation_id,
                endpoint=path,
                http_method=method.upper(),
                status_code=504,
                is_success=False,
                request_summary={"path": path, "payload": payload},
                error_message=err_text,
                user=user
            )
        return {
            "success": False,
            "status_code": 504,
            "error": err_text,
            "correlation_id": correlation_id,
        }

    # ==========================================
    # 1. PUBLIC GSTIN VERIFICATION & SEARCH
    # ==========================================
    def search_taxpayer(self, gstin: str, user: Any = None) -> Dict[str, Any]:
        """
        Calls Sandbox Public Compliance GSTIN search endpoint:
        POST /gst/compliance/public/gstin/search
        """
        gstin = (gstin or '').strip().upper()
        res = self.execute_request(
            method='POST',
            path='/gst/compliance/public/gstin/search',
            payload={"gstin": gstin},
            action='GSTIN_VERIFY',
            user=user,
            allow_retries=True
        )

        if not res.get('success'):
            return res

        data = res.get('data') or {}
        if isinstance(data.get('data'), dict):
            data = data['data']

        # Normalize fields returned by Sandbox
        pradr = data.get('pradr', {}) or {}
        addr_obj = pradr.get('addr', {}) if isinstance(pradr, dict) else {}
        
        # Build address string
        flno = addr_obj.get('flno', '')
        bno = addr_obj.get('bno', '')
        bnm = addr_obj.get('bnm', '')
        st = addr_obj.get('st', '')
        loc = addr_obj.get('loc', '')
        dst = addr_obj.get('dst', '')
        pncd = addr_obj.get('pncd', '')
        # In Indian GST, state code is strictly the 2-digit numeric prefix of GSTIN
        state_code = gstin[:2] if len(gstin) >= 2 and gstin[:2].isdigit() else (addr_obj.get('stcd', '')[:2])
        # Quicko returns the state name in addr_obj['stcd'] (e.g. "Maharashtra")
        state_name = addr_obj.get('stcd', '') or data.get('state_name', '')
        full_address = ", ".join(part for part in [flno, bno, bnm, st, loc, dst] if part)

        normalized = {
            "success": True,
            "gstin": gstin,
            "legal_name": data.get('lgnm') or data.get('legal_name') or '',
            "trade_name": data.get('tradeNam') or data.get('trade_name') or data.get('lgnm') or '',
            "status": data.get('sts') or data.get('status') or 'Active',
            "taxpayer_type": data.get('ctb') or data.get('taxpayer_type') or 'Regular',
            "registration_date": data.get('rgdt') or data.get('registration_date') or None,
            "state_code": state_code,
            "state_name": state_name,
            "address": full_address or data.get('address') or '',
            "pincode": pncd or data.get('pincode') or '',
            "raw": data,
            "correlation_id": res.get('correlation_id'),
        }
        return normalized

    # ==========================================
    # 2. TAXPAYER PORTAL OTP COMPLIANCE
    # ==========================================
    def request_portal_otp(
        self,
        gstin: str,
        username: str,
        source: str = "primary",
        user: Any = None,
        omit_source: bool = False
    ) -> Dict[str, Any]:
        """
        Requests OTP for taxpayer filing session:
        POST /gst/compliance/tax-payer/otp
        Payload: {"username": username, "gstin": gstin}
        """
        payload = {"username": username.strip(), "gstin": gstin.strip().upper()}
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/otp',
            payload=payload,
            source=source,
            omit_source=omit_source,
            action='PORTAL_OTP_REQUEST',
            user=user,
            allow_retries=False
        )

    def verify_portal_otp(
        self,
        gstin: str,
        username: str,
        otp: str,
        source: str = "primary",
        user: Any = None,
        omit_source: bool = False
    ) -> Dict[str, Any]:
        """
        Verifies OTP and establishes taxpayer compliance session token:
        POST /gst/compliance/tax-payer/otp/verify?otp=<otp>
        Payload: {"username": username, "gstin": gstin}
        """
        payload = {
            "username": username.strip(),
            "gstin": gstin.strip().upper()
        }
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/otp/verify',
            payload=payload,
            params={"otp": str(otp).strip()},
            source=source,
            omit_source=omit_source,
            action='PORTAL_OTP_VERIFY',
            user=user,
            allow_retries=False
        )

    def refresh_portal_session(
        self,
        session_token: str,
        source: str = "primary",
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Refreshes active taxpayer compliance session token:
        POST /gst/compliance/tax-payer/session/refresh
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/session/refresh',
            custom_session_token=session_token,
            source=source,
            action='PORTAL_SESSION_REFRESH',
            user=user,
            allow_retries=False
        )

    def logout_portal_session(
        self,
        session_token: str,
        source: str = "primary",
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Terminates active taxpayer compliance session token on Sandbox:
        POST /gst/compliance/tax-payer/logout
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/logout',
            custom_session_token=session_token,
            source=source,
            action='PORTAL_SESSION_LOGOUT',
            user=user,
            allow_retries=False
        )

    # ==========================================
    # 3. E-INVOICE (IRN) INTEGRATION
    # ==========================================
    def authenticate_einvoice(self, gstin: str, username: str, password: str, user: Any = None) -> Dict[str, Any]:
        """
        Taxpayer IRP authentication to obtain E-Invoice session token:
        POST /gst/compliance/e-invoice/tax-payer/authenticate
        """
        payload = {
            "gstin": gstin.strip().upper(),
            "username": username.strip(),
            "password": password
        }
        return self.execute_request(
            method='POST',
            path='/gst/compliance/e-invoice/tax-payer/authenticate',
            payload=payload,
            action='EINVOICE_AUTH',
            user=user,
            allow_retries=False
        )

    def generate_einvoice(self, invoice_payload: Dict[str, Any], session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Generates official IRN and Signed QR Code via Sandbox e-invoice endpoint:
        POST /gst/compliance/e-invoice/tax-payer/invoice
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/e-invoice/tax-payer/invoice',
            payload=invoice_payload,
            custom_session_token=session_token,
            action='EINVOICE_GENERATE',
            user=user,
            allow_retries=False  # Strictly fail-closed: NO blind retries on IRN generation
        )

    def cancel_einvoice(self, irn: str, cancel_reason: str, remarks: str = '', session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Cancels an active IRN within the statutory 24-hour window:
        POST /gst/compliance/e-invoice/tax-payer/invoice/cancel
        """
        payload = {
            "Irn": irn.strip(),
            "CnlRsn": str(cancel_reason),
            "CnlRem": remarks.strip()
        }
        return self.execute_request(
            method='POST',
            path='/gst/compliance/e-invoice/tax-payer/invoice/cancel',
            payload=payload,
            custom_session_token=session_token,
            action='EINVOICE_CANCEL',
            user=user,
            allow_retries=False
        )

    # ==========================================
    # 4. E-WAY BILL INTEGRATION
    # ==========================================
    def generate_ewaybill_for_irn(self, irn: str, payload: Dict[str, Any], session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Generates E-Way Bill tied to an existing IRN:
        POST /gst/compliance/e-invoice/tax-payer/invoice/{irn}/e-way-bill
        """
        return self.execute_request(
            method='POST',
            path=f"/gst/compliance/e-invoice/tax-payer/invoice/{irn}/e-way-bill",
            payload=payload,
            custom_session_token=session_token,
            action='EWAYBILL_GENERATE',
            user=user,
            allow_retries=False
        )

    def generate_standalone_ewaybill(self, payload: Dict[str, Any], session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Generates standalone E-Way Bill:
        POST /gst/compliance/e-way-bill/consignor/bill
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/e-way-bill/consignor/bill',
            payload=payload,
            custom_session_token=session_token,
            action='EWAYBILL_GENERATE',
            user=user,
            allow_retries=False
        )

    def update_ewaybill_vehicle(self, payload: Dict[str, Any], session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Updates Part-B vehicle details on an active E-Way bill:
        POST /gst/compliance/e-way-bill/vehicle/update
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/e-way-bill/vehicle/update',
            payload=payload,
            custom_session_token=session_token,
            action='EWAYBILL_UPDATE_VEHICLE',
            user=user,
            allow_retries=False
        )

    def cancel_ewaybill(self, payload: Dict[str, Any], session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Cancels an active E-Way bill:
        POST /gst/compliance/e-way-bill/bill/cancel
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/e-way-bill/bill/cancel',
            payload=payload,
            custom_session_token=session_token,
            action='EWAYBILL_CANCEL',
            user=user,
            allow_retries=False
        )

    # ==========================================
    # 5. GSTR-1 & RETURNS
    # ==========================================
    def save_gstr1(self, payload: Dict[str, Any], session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Uploads GSTR-1 outward supply payload to the GST portal via Sandbox:
        POST /gst/compliance/tax-payer/gstrs/gstr-1
        """
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/gstrs/gstr-1',
            payload=payload,
            custom_session_token=session_token,
            action='GSTR1_SUBMIT',
            user=user,
            allow_retries=False
        )

    def get_gstr_status(self, year: str, month: str, ref_id: str, session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Checks processing status of a previously submitted return:
        GET /gst/compliance/tax-payer/gstrs/{year}/{month}/status
        """
        return self.execute_request(
            method='GET',
            path=f"/gst/compliance/tax-payer/gstrs/{year}/{month}/status",
            params={"ref_id": ref_id},
            custom_session_token=session_token,
            action='GSTR1_STATUS',
            user=user,
            allow_retries=True
        )

    # ==========================================
    # 6. GSTR-2B STATEMENT RETRIEVAL
    # ==========================================
    def fetch_gstr2b(self, year: str, month: str, session_token: Optional[str] = None, user: Any = None) -> Dict[str, Any]:
        """
        Retrieves purchase-side GSTR-2B statement data for reconciliation:
        GET /gst/compliance/tax-payer/gstrs/gstr-2b/{year}/{month}
        """
        return self.execute_request(
            method='GET',
            path=f"/gst/compliance/tax-payer/gstrs/gstr-2b/{year}/{month}",
            custom_session_token=session_token,
            action='GSTR2B_FETCH',
            user=user,
            allow_retries=True
        )

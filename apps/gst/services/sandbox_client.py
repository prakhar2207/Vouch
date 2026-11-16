import os
import uuid
import time
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from apps.companies.models import Company
from apps.gst.models import CompanyGSTConfig, GSTRegistration
from apps.gst.exceptions import (
    GSTIntegrationError,
    GSTConfigurationMissingError,
    GSTAuthenticationError,
    GSTRateLimitExceededError,
)
from apps.gst.services.audit_service import GSTAuditService

logger = logging.getLogger('apps.gst.sandbox_client')


class SandboxGSTClient:
    """
    Authoritative Provider Client for Sandbox by Quicko (https://sandbox.co.in).
    Handles:
    - Base URL & environment selection (test vs live)
    - /authenticate token exchange & auto-refresh
    - Header management (x-api-key, authorization, x-api-version)
    - Connection timeouts, exponential backoff for idempotent calls
    - Error normalization
    - Structured audit logging via GSTAuditService
    """

    DEFAULT_BASE_URL = "https://api.sandbox.co.in"
    DEFAULT_TEST_URL = "https://test-api.sandbox.co.in"
    API_VERSION = "1.0.0"

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
        Checks CompanyGSTConfig first, then falls back to Django settings / environment.
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
        is_sandbox = True

        if self.config:
            api_key = self.config.sandbox_api_key or self.config.api_key or ''
            api_secret = self.config.sandbox_api_secret or self.config.api_secret or ''
            if self.config.sandbox_base_url:
                base_url = self.config.sandbox_base_url
            is_sandbox = self.config.is_sandbox

        if not api_key:
            api_key = (
                getattr(settings, 'SANDBOX_API_KEY', '')
                or getattr(settings, 'GST_SANDBOX_API_KEY', '')
                or os.environ.get('SANDBOX_API_KEY', '')
                or os.environ.get('GST_SANDBOX_API_KEY', '')
            )
        if not api_secret:
            api_secret = (
                getattr(settings, 'SANDBOX_API_SECRET', '')
                or getattr(settings, 'GST_SANDBOX_API_SECRET', '')
                or os.environ.get('SANDBOX_API_SECRET', '')
                or os.environ.get('GST_SANDBOX_API_SECRET', '')
            )

        # Adjust base URL for explicit sandbox environment if configured
        env_mode = getattr(settings, 'GST_SANDBOX_ENV', '') or os.environ.get('GST_SANDBOX_ENV', 'staging')
        if is_sandbox and 'test-api' in env_mode:
            base_url = self.DEFAULT_TEST_URL

        return api_key.strip(), api_secret.strip(), base_url.strip(), is_sandbox

    def is_configured(self) -> bool:
        api_key, api_secret, _, _ = self.get_api_credentials()
        return bool(api_key and api_secret)

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Retrieves valid JWT access token from Quicko Sandbox.
        Reuses cached token if valid; otherwise executes POST /authenticate.
        """
        api_key, api_secret, base_url, _ = self.get_api_credentials()

        if not api_key or not api_secret:
            raise GSTConfigurationMissingError(
                "Sandbox GST API credentials (API Key and Secret) are missing. "
                "Please configure GST Sandbox settings."
            )

        # Check existing cached token
        now = timezone.now()
        if not force_refresh and self.config and self.config.sandbox_access_token:
            if self.config.sandbox_token_expires_at and self.config.sandbox_token_expires_at > (now + timedelta(minutes=5)):
                return self.config.sandbox_access_token

        # Exchange API Key & Secret for JWT token via POST /authenticate
        endpoint = f"{base_url}/authenticate"
        correlation_id = f"AUTH-{uuid.uuid4().hex[:12].upper()}"
        headers = {
            "x-api-key": api_key,
            "x-api-secret": api_secret,
            "x-api-version": self.API_VERSION,
            "Content-Type": "application/json",
            "x-transaction-id": correlation_id,
        }

        try:
            res = requests.request('POST', endpoint, headers=headers, timeout=12)
            status_code = res.status_code

            if status_code == 200:
                data = res.json()
                # Access token may be at top level or nested under 'data'
                token = data.get('access_token') or (data.get('data', {}).get('access_token') if isinstance(data.get('data'), dict) else '')
                expires_in = data.get('expires_in', 86400)

                if not token:
                    raise GSTAuthenticationError(f"Sandbox /authenticate returned 200 but missing access_token: {data}")

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
                raise GSTAuthenticationError(
                    f"Authentication failed with Sandbox (HTTP {status_code}): {res.text}"
                )
            elif status_code == 429:
                raise GSTRateLimitExceededError("Rate limit exceeded while authenticating with Sandbox.")
            else:
                raise GSTIntegrationError(
                    f"Sandbox /authenticate responded with HTTP {status_code}: {res.text}",
                    status_code=status_code
                )
        except requests.exceptions.Timeout as e:
            raise GSTIntegrationError(f"Connection timed out contacting Sandbox /authenticate: {e}", status_code=504)
        except requests.exceptions.RequestException as e:
            raise GSTIntegrationError(f"Network error communicating with Sandbox /authenticate: {e}", status_code=502)

    def _get_authorized_headers(self, custom_session_token: Optional[str] = None) -> tuple[Dict[str, str], str]:
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
        return headers, correlation_id

    def execute_request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        custom_session_token: Optional[str] = None,
        action: str = 'GST_API_CALL',
        user: Any = None,
        allow_retries: bool = False
    ) -> Dict[str, Any]:
        """
        Central request dispatcher with:
        - Header injection
        - Timeout handling
        - Safe retry logic for idempotent calls
        - Audit logging
        """
        _, _, base_url, _ = self.get_api_credentials()
        endpoint = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        headers, correlation_id = self._get_authorized_headers(custom_session_token)

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
                    logger.info("Sandbox access token may be expired; refreshing token and retrying request.")
                    new_token = self.get_access_token(force_refresh=True)
                    headers["authorization"] = new_token
                    continue

                # Rate limiting
                if status_code == 429:
                    if allow_retries and attempt < max_attempts:
                        time.sleep(1.5 * attempt)
                        continue
                    raise GSTRateLimitExceededError("Sandbox rate limit reached for this endpoint.")

                # Try JSON parse
                try:
                    response_json = res.json()
                except Exception:
                    response_json = {"raw_text": res.text[:2000]}

                is_success = 200 <= status_code < 300

                # Audit log
                if self.company:
                    GSTAuditService.log_action(
                        company=self.company,
                        gst_registration=self.registration,
                        action=action,
                        correlation_id=correlation_id,
                        endpoint=path,
                        http_method=method.upper(),
                        status_code=status_code,
                        is_success=is_success,
                        request_summary={"path": path, "payload": payload, "params": params},
                        response_summary=response_json if isinstance(response_json, dict) else {"status": status_code},
                        error_message="" if is_success else str(response_json)[:1000],
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
                    time.sleep(1.0 * attempt)
                    continue
                break

        # If loop exited on network failure
        err_text = f"Connection to Sandbox failed after {attempt} attempt(s): {last_exception}"
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
        # Normalize fields returned by Sandbox
        # Schema typically has: gstin, lgnm, tradeNam, sts, ctb, rgdt, pradr, nba
        pradr = data.get('pradr', {}) or {}
        addr_obj = pradr.get('addr', {}) if isinstance(pradr, dict) else {}
        
        # Build address string
        bno = addr_obj.get('bno', '')
        st = addr_obj.get('st', '')
        loc = addr_obj.get('loc', '')
        pncd = addr_obj.get('pncd', '')
        stcd = addr_obj.get('stcd', '') or gstin[:2]
        full_address = ", ".join(part for part in [bno, st, loc] if part)

        normalized = {
            "success": True,
            "gstin": gstin,
            "legal_name": data.get('lgnm') or data.get('legal_name') or '',
            "trade_name": data.get('tradeNam') or data.get('trade_name') or data.get('lgnm') or '',
            "status": data.get('sts') or data.get('status') or 'Active',
            "taxpayer_type": data.get('ctb') or data.get('taxpayer_type') or 'Regular',
            "registration_date": data.get('rgdt') or data.get('registration_date') or None,
            "state_code": stcd,
            "state_name": data.get('state_name') or '',
            "address": full_address or data.get('address') or '',
            "pincode": pncd or data.get('pincode') or '',
            "raw": data,
            "correlation_id": res.get('correlation_id'),
        }
        return normalized

    # ==========================================
    # 2. TAXPAYER PORTAL OTP COMPLIANCE
    # ==========================================
    def request_portal_otp(self, gstin: str, username: str, user: Any = None) -> Dict[str, Any]:
        """
        Requests OTP for taxpayer filing session:
        POST /gst/compliance/tax-payer/otp
        """
        payload = {"gstin": gstin.strip().upper(), "username": username.strip()}
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/otp',
            payload=payload,
            action='PORTAL_OTP_REQUEST',
            user=user,
            allow_retries=False
        )

    def verify_portal_otp(self, gstin: str, username: str, otp: str, user: Any = None) -> Dict[str, Any]:
        """
        Verifies OTP and establishes taxpayer compliance session token:
        POST /gst/compliance/tax-payer/otp/verify
        """
        payload = {
            "gstin": gstin.strip().upper(),
            "username": username.strip(),
            "otp": str(otp).strip()
        }
        return self.execute_request(
            method='POST',
            path='/gst/compliance/tax-payer/otp/verify',
            payload=payload,
            action='PORTAL_OTP_VERIFY',
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

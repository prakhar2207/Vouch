import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from apps.companies.models import Company
from apps.gst.models import GSTRegistration, GSTAuditLog

logger = logging.getLogger('apps.gst.audit')

SENSITIVE_KEYS = {
    'api_key', 'api_secret', 'secret', 'password', 'eway_password',
    'einvoice_password', 'auth_token', 'token', 'access_token',
    'otp', 'sandbox_api_key', 'sandbox_api_secret', 'authorization',
    'x-api-key', 'x-api-secret', 'client_secret', 'clientid'
}


def redact_sensitive_payload(data: Any) -> Any:
    """
    Recursively redacts sensitive credentials, tokens, passwords, and OTPs
    from payloads before logging or persisting to GSTAuditLog.
    """
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                redacted[k] = "REDACTED"
            elif isinstance(v, (dict, list)):
                redacted[k] = redact_sensitive_payload(v)
            else:
                redacted[k] = v
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_payload(item) for item in data]
    return data


class GSTAuditService:
    """
    Authoritative audit logger for all outbound GST Sandbox API interactions.
    Guarantees zero leakage of secrets, API keys, or taxpayer OTPs.
    """

    @classmethod
    def log_action(
        cls,
        company: Company,
        action: str,
        correlation_id: str,
        endpoint: str,
        http_method: str = 'POST',
        gst_registration: Optional[GSTRegistration] = None,
        status_code: Optional[int] = None,
        is_success: bool = True,
        request_summary: Optional[Dict[str, Any]] = None,
        response_summary: Optional[Dict[str, Any]] = None,
        error_message: str = '',
        user: Any = None,
        ip_address: Optional[str] = None
    ) -> GSTAuditLog:
        cleaned_req = redact_sensitive_payload(request_summary or {})
        cleaned_res = redact_sensitive_payload(response_summary or {})

        try:
            audit_entry = GSTAuditLog.objects.create(
                company=company,
                gst_registration=gst_registration,
                action=action,
                correlation_id=correlation_id,
                endpoint=endpoint,
                http_method=http_method,
                status_code=status_code,
                is_success=is_success,
                request_summary=cleaned_req,
                response_summary=cleaned_res,
                error_message=error_message[:2000] if error_message else '',
                performed_by=user if getattr(user, 'is_authenticated', False) else None,
                ip_address=ip_address
            )
            return audit_entry
        except Exception as e:
            logger.warning(f"Failed to persist GSTAuditLog: {e}")
            return None

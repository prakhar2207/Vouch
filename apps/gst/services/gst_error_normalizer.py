"""
GST Error Normalizer Service
Provides centralized error message normalization, data sanitization,
and structured error classification for GST compliance integrations.
Ensures zero leaks of credentials, raw HTTP stack traces, correlation IDs,
or unhandled vendor errors to customers.
"""

import re
import uuid
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

PORTAL_HELP_GUIDE = {
    "url": "https://services.gst.gov.in",
    "gsp_name": "Quicko Infosoft Private Limited",
    "steps": [
        "Log in to the official GST Portal at services.gst.gov.in",
        "Click on your profile name at the top right and select My Profile",
        "Under Quick Links, click on Manage API Access",
        "Set 'Enable API Request' to Yes and choose Duration (30 days recommended)",
        "If a GSP selection is shown, choose 'Quicko Infosoft Private Limited'",
        "Click Confirm to save your authorization on the GST Portal",
        "Return to SriLekh and click 'Connect GST Portal'"
    ]
}

# Sensitive keys that must be redacted before logging or auditing
SENSITIVE_KEYS = {
    'password', 'otp', 'api_secret', 'client-secret', 'client_secret',
    'auth_token', 'access_token', 'app_key', 'token', 'secret',
    'eway_password', 'einvoice_password', 'sandbox_api_secret'
}

REDACTION_PATTERN = re.compile(
    r'(password|otp|secret|token|bearer|key)\s*[:=]\s*["\']?([^"\'\s,;&]+)["\']?',
    re.IGNORECASE
)


def redact_sensitive_str(text: Optional[str]) -> str:
    """Masks secrets, passwords, OTPs, and tokens in raw strings."""
    if not text:
        return ""
    return REDACTION_PATTERN.sub(r'\1=***REDACTED***', str(text))


def sanitize_audit_payload(data: Any) -> Any:
    """
    Recursively redacts sensitive credentials (OTPs, passwords, tokens, secrets)
    from dictionary or list structures before persisting to GSTAuditLog or server logs.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_audit_payload(v)
            elif isinstance(v, str) and str(k).lower() == 'otp':
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(data, list):
        return [sanitize_audit_payload(item) for item in data]
    elif isinstance(data, str):
        return redact_sensitive_str(data)
    return data


def get_structured_gst_error(
    raw_error: Optional[str],
    status_code: int = 400,
    category: str = "general",
    correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes raw external provider responses, HTTP status codes, and exceptions,
    returning structured, customer-safe error classification with actionable guidance.
    Never exposes raw exceptions, credentials, or internal provider names.
    """
    cid = correlation_id or f"GST-ERR-{uuid.uuid4().hex[:10].upper()}"

    if not raw_error:
        if category == "otp_request":
            return {
                "code": "OTP_DELIVERY_FAILURE",
                "message": "We couldn't send your OTP. Please verify your GST Portal username and try again.",
                "action": "RECHECK_USERNAME",
                "correlation_id": cid,
            }
        elif category == "otp_verify":
            return {
                "code": "INCORRECT_OTP",
                "message": "The OTP entered is incorrect or has expired. Please check and try again.",
                "action": "REENTER_OTP",
                "correlation_id": cid,
            }
        elif category == "filing":
            return {
                "code": "SUBMISSION_REJECTED",
                "message": "Return submission was rejected by the GST Portal. Please check return contents.",
                "action": "REVIEW_RETURN",
                "correlation_id": cid,
            }
        return {
            "code": "PROVIDER_OUTAGE",
            "message": "We couldn't connect to the GST Portal right now. Please try again.",
            "action": "RETRY_LATER",
            "correlation_id": cid,
        }

    raw_str = str(raw_error).strip()
    raw_lower = raw_str.lower()

    # 1. Rate Limiting (HTTP 429)
    if status_code == 429 or "rate limit" in raw_lower or "too many requests" in raw_lower:
        return {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests to the GST Portal. Please wait a few moments before trying again.",
            "action": "RETRY_LATER",
            "correlation_id": cid,
        }

    # 2. Network connectivity, timeout, or external gateway 5xx outage / Scheduled Downtime
    if any(phrase in raw_lower for phrase in ["scheduled downtime", "downtime", "maintenance", "enhancing the services"]):
        return {
            "code": "SCHEDULED_DOWNTIME",
            "message": "The official GST Portal (services.gst.gov.in) is currently undergoing scheduled maintenance/downtime. Services will resume once the government maintenance window ends.",
            "action": "RETRY_LATER",
            "correlation_id": cid,
        }

    if (
        status_code in (502, 503, 504)
        or "timeout" in raw_lower
        or "timed out" in raw_lower
        or "connection error" in raw_lower
        or "network error" in raw_lower
        or "service unavailable" in raw_lower
        or "bad gateway" in raw_lower
    ):
        return {
            "code": "PROVIDER_OUTAGE",
            "message": "The GST Portal is temporarily unavailable. Please try again shortly.",
            "action": "RETRY_LATER",
            "correlation_id": cid,
        }

    # 3. GSP/ASP Consent or Mapping Missing
    if any(phrase in raw_lower for phrase in ["gsp not mapped", "gsp authorization missing", "asp authorization", "unauthorized gsp", "invalid gsp"]):
        return {
            "code": "GSP_AUTH_MISSING",
            "message": "GST Portal authorization for SriLekh's integration partner is missing. Please select Quicko Infosoft Private Limited under Manage API Access on the GST Portal.",
            "action": "ENABLE_PORTAL_API_ACCESS",
            "portal_help": PORTAL_HELP_GUIDE,
            "correlation_id": cid,
        }

    # 4. API Access disabled on government portal or insufficient privileges
    if any(phrase in raw_lower for phrase in [
        "api access", "enable api", "manage api access", "duration",
        "api_access_disabled", "access is disabled", "access not enabled", "gsp access",
        "api access is disabled", "api access is not enabled", "api access disabled",
        "insufficient privilege", "insufficient privileges", "privilege", "unauthorized access"
    ]):
        return {
            "code": "API_ACCESS_DISABLED",
            "message": "GST API access is disabled or has insufficient privileges on the GST Portal. Please log in to services.gst.gov.in > My Profile > Manage API Access, set Enable API Request to 'Yes' (30 days), select Quicko as GSP, and reconnect.",
            "action": "ENABLE_PORTAL_API_ACCESS",
            "portal_help": PORTAL_HELP_GUIDE,
            "correlation_id": cid,
        }

    # 5. Invalid or Expired OTP
    if "otp" in raw_lower and any(
        term in raw_lower for term in ["expired", "timeout", "timed out"]
    ):
        return {
            "code": "EXPIRED_OTP",
            "message": "The OTP entered has expired. Please request a new OTP to continue.",
            "action": "REQUEST_NEW_OTP",
            "correlation_id": cid,
        }
    if "otp" in raw_lower and any(
        term in raw_lower for term in ["invalid", "incorrect", "mismatch", "failed", "wrong"]
    ):
        return {
            "code": "INCORRECT_OTP",
            "message": "The OTP entered is incorrect or has expired. Please check and try again.",
            "action": "REENTER_OTP",
            "correlation_id": cid,
        }

    # 6. Taxpayer / Username not found
    if any(term in raw_lower for term in ["taxpayer not found", "invalid taxpayer", "user not found", "user does not exist", "invalid username"]):
        return {
            "code": "INVALID_USERNAME",
            "message": "The GST Portal username entered does not match your GST registration. Please verify your username.",
            "action": "RECHECK_USERNAME",
            "correlation_id": cid,
        }
    if "username" in raw_lower and any(term in raw_lower for term in ["invalid", "not found", "incorrect", "unknown"]):
        return {
            "code": "INVALID_USERNAME",
            "message": "Please check your GST Portal username and try again.",
            "action": "RECHECK_USERNAME",
            "correlation_id": cid,
        }

    # 7. Session Expired or Token Invalid
    if any(phrase in raw_lower for phrase in ["session expired", "token expired", "unauthorized session", "auth token"]):
        return {
            "code": "EXPIRED_SESSION",
            "message": "Your GST Portal connection session has expired. Please reconnect to continue.",
            "action": "RECONNECT",
            "correlation_id": cid,
        }

    # 8. Token integrity & validation failures
    if "session token" in raw_lower or "malformed token" in raw_lower or "invalid token" in raw_lower:
        return {
            "code": "INVALID_SESSION_TOKEN",
            "message": "Authentication token verification failed. Please reconnect with a fresh OTP.",
            "action": "REQUEST_NEW_OTP",
            "correlation_id": cid,
        }

    # 9. GSTIN Mismatch
    if "gstin mismatch" in raw_lower or "mismatch" in raw_lower and "gstin" in raw_lower:
        return {
            "code": "GSTIN_MISMATCH",
            "message": "The GSTIN in the portal session does not match your company registration.",
            "action": "VERIFY_GSTIN",
            "correlation_id": cid,
        }

    # 10. Filing and statutory errors
    if any(phrase in raw_lower for phrase in ["already filed", "return already filed", "duplicate filing"]):
        return {
            "code": "ALREADY_FILED",
            "message": "This GST return has already been filed on the GST Common Portal.",
            "action": "VIEW_FILED_RETURN",
            "correlation_id": cid,
        }

    # 11. Internal parameter, credential, or signature issues (e.g. x-source, client credentials)
    # Mask completely from customer view
    if any(term in raw_lower for term in ["x-source", "parameter", "header", "credential", "clientid", "secret", "401", "403"]):
        return {
            "code": "CONFIGURATION_ERROR",
            "message": "GST Portal connection is temporarily unavailable. Please try again shortly or contact support if the issue persists.",
            "action": "CONTACT_SUPPORT",
            "correlation_id": cid,
        }

    # 12. Category-specific fallbacks
    if category == "otp_request":
        return {
            "code": "OTP_DELIVERY_FAILURE",
            "message": "We couldn't send your OTP. Please verify your GST Portal username and try again.",
            "action": "RECHECK_USERNAME",
            "correlation_id": cid,
        }
    elif category == "otp_verify":
        return {
            "code": "INCORRECT_OTP",
            "message": "The OTP entered could not be verified. Please check the code and try again.",
            "action": "REENTER_OTP",
            "correlation_id": cid,
        }
    elif category == "filing":
        return {
            "code": "SUBMISSION_REJECTED",
            "message": "The GST Portal rejected the return submission. Please verify the return details.",
            "action": "REVIEW_RETURN",
            "correlation_id": cid,
        }

    return {
        "code": "PROVIDER_OUTAGE",
        "message": "We couldn't connect to the GST Portal right now. Please try again.",
        "action": "RETRY_LATER",
        "correlation_id": cid,
    }


def normalize_gst_error(raw_error: Optional[str], status_code: int = 400, category: str = "general") -> str:
    """
    Translates raw external provider errors, HTTP status codes, and exceptions
    into clean, business-friendly error explanations string.
    """
    structured = get_structured_gst_error(raw_error, status_code=status_code, category=category)
    return structured["message"]

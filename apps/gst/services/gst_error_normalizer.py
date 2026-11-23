"""
GST Error Normalizer Service
Provides centralized error message normalization and structured error classification
for GST compliance integrations. Ensures no raw provider responses, HTTP status traces,
parameter names, or vendor/infrastructure details leak to customer-facing interfaces.
"""

import re
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


def get_structured_gst_error(raw_error: Optional[str], status_code: int = 400, category: str = "general") -> Dict[str, Any]:
    """
    Analyzes raw external provider responses, HTTP status codes, and exceptions,
    returning structured, customer-safe error classification with actionable guidance.
    """
    if not raw_error:
        if category == "otp_request":
            return {
                "code": "OTP_DELIVERY_FAILURE",
                "message": "We couldn't send your OTP. Please verify your GST Portal username and try again.",
                "action": "RECHECK_USERNAME",
            }
        elif category == "otp_verify":
            return {
                "code": "INCORRECT_OTP",
                "message": "The OTP entered is incorrect or has expired. Please check and try again.",
                "action": "REENTER_OTP",
            }
        return {
            "code": "PROVIDER_OUTAGE",
            "message": "We couldn't connect to the GST Portal right now. Please try again.",
            "action": "RETRY_LATER",
        }

    raw_str = str(raw_error).strip()
    raw_lower = raw_str.lower()

    # 1. Rate Limiting (HTTP 429)
    if status_code == 429 or "rate limit" in raw_lower or "too many requests" in raw_lower:
        return {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests to the GST Portal. Please wait a few moments before trying again.",
            "action": "RETRY_LATER",
        }

    # 2. Network connectivity, timeout, or external gateway 5xx outage
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
        }

    # 3. GSP/ASP Consent or Mapping Missing
    if any(phrase in raw_lower for phrase in ["gsp not mapped", "gsp authorization missing", "asp authorization", "unauthorized gsp", "invalid gsp"]):
        return {
            "code": "GSP_AUTH_MISSING",
            "message": "GST Portal authorization for SriLekh's integration partner is missing. Please select Quicko Infosoft Private Limited under Manage API Access on the GST Portal.",
            "action": "ENABLE_PORTAL_API_ACCESS",
            "portal_help": PORTAL_HELP_GUIDE,
        }

    # 4. API Access disabled on government portal
    if any(phrase in raw_lower for phrase in [
        "api access", "enable api", "manage api access", "duration",
        "api_access_disabled", "access is disabled", "access not enabled", "gsp access",
        "api access is disabled", "api access is not enabled", "api access disabled"
    ]):
        return {
            "code": "API_ACCESS_DISABLED",
            "message": "GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again.",
            "action": "ENABLE_PORTAL_API_ACCESS",
            "portal_help": PORTAL_HELP_GUIDE,
        }

    # 5. Invalid or Expired OTP
    if "otp" in raw_lower and any(
        term in raw_lower for term in ["expired", "timeout", "timed out"]
    ):
        return {
            "code": "EXPIRED_OTP",
            "message": "The OTP entered has expired. Please request a new OTP to continue.",
            "action": "REQUEST_NEW_OTP",
        }
    if "otp" in raw_lower and any(
        term in raw_lower for term in ["invalid", "incorrect", "mismatch", "failed", "wrong"]
    ):
        return {
            "code": "INCORRECT_OTP",
            "message": "The OTP entered is incorrect or has expired. Please check and try again.",
            "action": "REENTER_OTP",
        }

    # 6. Taxpayer / Username not found
    if any(term in raw_lower for term in ["taxpayer not found", "invalid taxpayer", "user not found", "user does not exist", "invalid username"]):
        return {
            "code": "INVALID_USERNAME",
            "message": "The GST Portal username entered does not match your GST registration. Please verify your username.",
            "action": "RECHECK_USERNAME",
        }
    if "username" in raw_lower and any(term in raw_lower for term in ["invalid", "not found", "incorrect", "unknown"]):
        return {
            "code": "INVALID_USERNAME",
            "message": "Please check your GST Portal username and try again.",
            "action": "RECHECK_USERNAME",
        }

    # 7. Session Expired or Token Invalid
    if any(phrase in raw_lower for phrase in ["session expired", "token expired", "unauthorized session", "auth token"]):
        return {
            "code": "EXPIRED_SESSION",
            "message": "Your GST Portal connection session has expired. Please reconnect to continue.",
            "action": "RECONNECT",
        }

    # 8. Internal parameter, credential, or signature issues (e.g. x-source, client credentials)
    # Mask completely from customer view
    if any(term in raw_lower for term in ["x-source", "parameter", "header", "credential", "clientid", "secret", "401", "403"]):
        return {
            "code": "CONFIGURATION_ERROR",
            "message": "GST Portal connection is temporarily unavailable. Please try again shortly or contact support if the issue persists.",
            "action": "CONTACT_SUPPORT",
        }

    # 9. Category-specific fallbacks
    if category == "otp_request":
        return {
            "code": "OTP_DELIVERY_FAILURE",
            "message": "We couldn't send your OTP. Please verify your GST Portal username and try again.",
            "action": "RECHECK_USERNAME",
        }
    elif category == "otp_verify":
        return {
            "code": "INCORRECT_OTP",
            "message": "The OTP entered could not be verified. Please check the code and try again.",
            "action": "REENTER_OTP",
        }

    return {
        "code": "PROVIDER_OUTAGE",
        "message": "We couldn't connect to the GST Portal right now. Please try again.",
        "action": "RETRY_LATER",
    }


def normalize_gst_error(raw_error: Optional[str], status_code: int = 400, category: str = "general") -> str:
    """
    Translates raw external provider errors, HTTP status codes, and exceptions
    into clean, business-friendly error explanations string.
    """
    structured = get_structured_gst_error(raw_error, status_code=status_code, category=category)
    return structured["message"]

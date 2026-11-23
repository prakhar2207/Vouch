"""
GST Error Normalizer Service
Provides centralized error message normalization for GST compliance integrations.
Ensures no raw provider responses, HTTP status traces, parameter names, or vendor/infrastructure
details leak to customer-facing interfaces.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_gst_error(raw_error: Optional[str], status_code: int = 400, category: str = "general") -> str:
    """
    Translates raw external provider errors, HTTP status codes, and exceptions
    into clean, business-friendly error explanations.

    Categories:
    - "otp_request": Error occurred while requesting an OTP
    - "otp_verify": Error occurred while verifying an OTP
    - "portal_status": Error checking portal filing status
    - "general": General portal interaction
    """
    if not raw_error:
        if category == "otp_request":
            return "We couldn't send your OTP right now. Please verify your GST Portal username and try again."
        elif category == "otp_verify":
            return "The OTP entered is incorrect or has expired. Please try again."
        return "We couldn't connect to the GST Portal right now. Please try again."

    raw_str = str(raw_error).strip()
    raw_lower = raw_str.lower()

    # 1. Rate Limiting (HTTP 429)
    if status_code == 429 or "rate limit" in raw_lower or "too many requests" in raw_lower:
        return "Too many requests to the GST Portal. Please wait a few moments before trying again."

    # 2. Network connectivity, timeout, or external gateway 5xx outage
    if (
        status_code in (502, 503, 504)
        or "timeout" in raw_lower
        or "timed out" in raw_lower
        or "connection error" in raw_lower
        or "network error" in raw_lower
        or "service unavailable" in raw_lower
    ):
        return "The GST Portal is temporarily unavailable. Please try again shortly."

    # 3. Invalid or Expired OTP
    if "otp" in raw_lower and any(
        term in raw_lower for term in ["invalid", "expired", "incorrect", "mismatch", "failed", "wrong"]
    ):
        return "The OTP entered is incorrect or has expired. Please check and try again."

    # 4. Taxpayer / Username not found
    if any(term in raw_lower for term in ["taxpayer not found", "invalid taxpayer", "user not found", "user does not exist"]):
        return "We couldn't find a matching GST Portal account for this username. Please verify your registered username."
    if "username" in raw_lower and any(term in raw_lower for term in ["invalid", "not found", "incorrect", "unknown"]):
        return "Please check your GST Portal username and try again."

    # 5. API Access disabled on government portal
    if any(phrase in raw_lower for phrase in [
        "api access", "enable api", "manage api access", "duration",
        "api_access_disabled", "access is disabled", "access not enabled", "gsp access",
        "api access is disabled", "api access is not enabled", "api access disabled"
    ]):
        return "GST API access is currently disabled for this GST registration. Please enable API access in your GST Portal account and try again."

    # 6. Session Expired or Token Invalid
    if any(phrase in raw_lower for phrase in ["session expired", "token expired", "unauthorized session", "auth token"]):
        return "Your GST Portal session has expired. Please reconnect with a new OTP."

    # 7. Internal parameter, credential, or signature issues (e.g. x-source, client credentials)
    # Mask completely from customer view
    if any(term in raw_lower for term in ["x-source", "parameter", "header", "credential", "clientid", "secret", "401", "403"]):
        return "GST Portal connection is temporarily unavailable. Please try again shortly or contact support if the issue persists."

    # 8. Category-specific fallbacks
    if category == "otp_request":
        return "We couldn't send your OTP. Please verify your GST Portal username and try again."
    elif category == "otp_verify":
        return "The OTP entered could not be verified. Please check the code and try again."

    return "We couldn't connect to the GST Portal right now. Please try again."

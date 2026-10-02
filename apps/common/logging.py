import re
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Dict, Any, Optional
from django.utils.deprecation import MiddlewareMixin

# ContextVar for thread/async-safe request correlation tracking
_correlation_ctx: ContextVar[Dict[str, Any]] = ContextVar('correlation_ctx', default={})

def get_correlation_context() -> Dict[str, Any]:
    """Retrieve current request / worker correlation context."""
    return dict(_correlation_ctx.get())

def set_correlation_context(**kwargs) -> None:
    """Update or merge fields into the current correlation context."""
    ctx = dict(_correlation_ctx.get())
    for k, v in kwargs.items():
        if v is not None:
            ctx[k] = str(v)
    _correlation_ctx.set(ctx)

def clear_correlation_context() -> None:
    """Clear correlation context (e.g. at request end)."""
    _correlation_ctx.set({})


# -------------------------------------------------------------------------
# PII & Sensitive Credential Masking Engine
# -------------------------------------------------------------------------
# Masks sensitive accounting and client information before emission:
# - GSTIN
# - Bank Account numbers
# - Indian PAN numbers
# - JWT / Bearer tokens
# - Cryptographic private keys & seeds
# - Passwords & API secrets

GSTIN_REGEX = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b')
PAN_REGEX = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b')
BANK_ACC_REGEX = re.compile(r'(?i)\b(?:account|acct|a/c|acc|bank_account)[\s:=_-]*(\d{9,18})\b')
STANDALONE_BANK_REGEX = re.compile(r'\b\d{11,18}\b')  # 11-18 digit standalone numbers (standard Indian bank acc range)
JWT_REGEX = re.compile(r'Bearer\s+[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+')
PRIVATE_KEY_REGEX = re.compile(r'-----BEGIN[ A-Z0-9_-]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z0-9_-]*PRIVATE KEY-----')
JSON_SECRET_KEY_REGEX = re.compile(
    r'(?i)"(password|secret|token|api_key|private_key|seed|vapid_private_key|pin|cvv)"\s*:\s*"([^"]+)"'
)

def mask_sensitive_data(text: str) -> str:
    """
    Sanitizes string against sensitive financial PII and security tokens.
    """
    if not isinstance(text, str) or not text:
        return text

    # 1. Private keys
    if "BEGIN" in text and "PRIVATE KEY" in text:
        text = PRIVATE_KEY_REGEX.sub("[MASKED_PRIVATE_KEY]", text)

    # 2. JWT & Bearer tokens
    if "Bearer " in text:
        text = JWT_REGEX.sub("Bearer [MASKED_JWT]", text)

    # 3. JSON secret fields
    text = JSON_SECRET_KEY_REGEX.sub(r'"\1": "[MASKED_SECRET]"', text)

    # 4. Bank account patterns
    text = BANK_ACC_REGEX.sub(r'account: [MASKED_BANK_ACC]', text)

    # 5. GSTIN
    text = GSTIN_REGEX.sub("[MASKED_GSTIN]", text)

    # 6. PAN
    text = PAN_REGEX.sub("[MASKED_PAN]", text)

    return text


class PIIMaskingFilter(logging.Filter):
    """
    Logging filter that intercepts log records and scrubs sensitive PII
    from log messages and formatted representations.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = mask_sensitive_data(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: mask_sensitive_data(str(v)) for k, v in record.args.items()}
                elif isinstance(record.args, (list, tuple)):
                    record.args = tuple(mask_sensitive_data(str(a)) for a in record.args)
        except Exception:
            pass  # Ensure logging never crashes application
        return True


# -------------------------------------------------------------------------
# Production JSON Formatter
# -------------------------------------------------------------------------
class StructuredJSONFormatter(logging.Formatter):
    """
    Outputs structured single-line JSON records formatted with:
    - timestamp (ISO-8601 UTC)
    - level
    - logger
    - correlation IDs (request_id, company_id, transaction_id, operation_id, replica_id)
    - latency_ms (if supplied)
    - masked message & sanitized exception details
    """
    def format(self, record: logging.LogRecord) -> str:
        ctx = get_correlation_context()

        # Merge context from extra if provided on log call
        request_id = getattr(record, 'request_id', None) or ctx.get('request_id', '-')
        company_id = getattr(record, 'company_id', None) or ctx.get('company_id', '-')
        transaction_id = getattr(record, 'transaction_id', None) or ctx.get('transaction_id', '-')
        operation_id = getattr(record, 'operation_id', None) or ctx.get('operation_id', '-')
        replica_id = getattr(record, 'replica_id', None) or ctx.get('replica_id', '-')

        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask_sensitive_data(record.getMessage()),
            "correlation": {
                "request_id": request_id,
                "company_id": company_id,
                "transaction_id": transaction_id,
                "operation_id": operation_id,
                "replica_id": replica_id,
            }
        }

        # Optional metrics
        if hasattr(record, 'latency_ms'):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, 'status_code'):
            log_data["status_code"] = record.status_code
        if hasattr(record, 'event_type'):
            log_data["event_type"] = record.event_type

        # Sanitized Exception info
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            log_data["exception"] = mask_sensitive_data(exc_text)

        return json.dumps(log_data)


# -------------------------------------------------------------------------
# Request Correlation & Latency Middleware
# -------------------------------------------------------------------------
class RequestCorrelationMiddleware(MiddlewareMixin):
    """
    Middleware that establishes correlation IDs and logs incoming/outgoing
    HTTP requests with latency metrics and correlation context.
    """
    def process_request(self, request):
        request.start_time = time.perf_counter()

        # Extract or generate correlation IDs
        req_id = (
            request.META.get('HTTP_X_REQUEST_ID') or
            request.META.get('HTTP_REQUEST_ID') or
            str(uuid.uuid4())
        )
        company_id = (
            request.META.get('HTTP_X_COMPANY_ID') or
            request.META.get('HTTP_COMPANY_ID') or
            '-'
        )
        replica_id = (
            request.META.get('HTTP_X_REPLICA_ID') or
            request.META.get('HTTP_X_DEVICE_ID') or
            '-'
        )

        request.request_id = req_id
        set_correlation_context(
            request_id=req_id,
            company_id=company_id,
            replica_id=replica_id
        )

    def process_response(self, request, response):
        try:
            latency_ms = None
            if hasattr(request, 'start_time'):
                duration = time.perf_counter() - request.start_time
                latency_ms = round(duration * 1000, 2)

            req_id = getattr(request, 'request_id', '-')
            response['X-Request-ID'] = req_id

            # Skip logging health checks to avoid noise
            if request.path not in ('/api/health/', '/', '/healthz'):
                access_logger = logging.getLogger('vouch.access')
                extra = {
                    'latency_ms': latency_ms,
                    'status_code': response.status_code,
                    'request_id': req_id,
                }
                access_logger.info(
                    "HTTP %s %s %s in %sms",
                    request.method,
                    request.path,
                    response.status_code,
                    latency_ms if latency_ms is not None else 0.0,
                    extra=extra
                )
        finally:
            clear_correlation_context()

        return response

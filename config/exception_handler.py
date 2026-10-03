import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import Throttled, ValidationError

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler.
    Ensures that ALL exceptions, including unhandled Python/Django exceptions,
    ValidationError, and 429 Throttled exceptions, return a structured DRF Response
    with a consistent JSON format: {"error": "...", "detail": "..."}.
    """
    response = exception_handler(exc, context)

    if response is not None:
        if isinstance(exc, Throttled):
            wait = getattr(exc, 'wait', None)
            retry_seconds = max(1, int(wait)) if wait is not None else 60
            response.data = {
                "error": "Rate limit exceeded. Please slow down your requests.",
                "detail": response.data.get('detail', 'Request was throttled.'),
                "retry_after_seconds": retry_seconds,
            }
            response['Retry-After'] = str(retry_seconds)
        elif isinstance(exc, ValidationError):
            # Normalize ValidationError to a consistent flat string format.
            # DRF ValidationError.detail can be a list, dict, or string.
            detail = exc.detail
            if isinstance(detail, list):
                # Flatten list of ErrorDetail objects to a single string
                flat = '; '.join(str(item) for item in detail)
            elif isinstance(detail, dict):
                # Flatten field-keyed errors: {"field": ["error1", "error2"]}
                parts = []
                for field, errors in detail.items():
                    if isinstance(errors, list):
                        field_errors = ', '.join(str(e) for e in errors)
                    else:
                        field_errors = str(errors)
                    if field == 'non_field_errors':
                        parts.append(field_errors)
                    else:
                        parts.append(f"{field}: {field_errors}")
                flat = '; '.join(parts)
            else:
                flat = str(detail)
            response.data = {
                "success": False,
                "error": flat,
            }
        return response

    view = context.get('view')
    view_name = view.__class__.__name__ if view else 'UnknownView'
    logger.exception("Unhandled server error in %s: %s", view_name, exc)
    return Response(
        {
            "error": "An internal server error occurred.",
            "detail": str(exc),
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


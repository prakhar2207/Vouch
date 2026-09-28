import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

from rest_framework.exceptions import Throttled

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler.
    Ensures that ALL exceptions, including unhandled Python/Django exceptions
    and 429 Throttled exceptions, return a structured DRF Response.
    Attaches Access-Control-Allow-Origin headers and standard Retry-After headers.
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


import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler.
    Ensures that ALL exceptions, including unhandled Python/Django exceptions,
    return a DRF Response. This guarantees that Django's response middleware
    (specifically corsheaders.middleware.CorsMiddleware) runs and attaches
    Access-Control-Allow-Origin headers, preventing CORS policy blocks on 500 errors.
    """
    response = exception_handler(exc, context)

    if response is None:
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

    return response

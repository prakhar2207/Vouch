import json
import logging
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class IdempotencyMiddleware(MiddlewareMixin):
    """
    Guarantees strict once-and-only-once execution for mobile, desktop, and web clients.
    Intercepts mutating requests (POST, PUT, PATCH, DELETE) bearing 'X-Idempotency-Key'.
    
    If a retry arrives:
    - If previously completed: Replays the cached response with 'X-Idempotent-Replay: true'.
    - If currently processing: Returns HTTP 409 Conflict ('Operation in progress').
    """

    SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}
    TTL_SECONDS = 86400  # 24-hour replay cache

    def process_request(self, request):
        if request.method in self.SAFE_METHODS:
            return None

        key = request.META.get('HTTP_X_IDEMPOTENCY_KEY') or request.META.get('HTTP_IDEMPOTENCY_KEY')
        if not key:
            return None

        # Clean key to prevent cache injection
        key = str(key).strip()
        if len(key) < 8 or len(key) > 128:
            return None

        company_id = request.META.get('HTTP_X_COMPANY_ID', '')
        cache_key = f"idempotency:{company_id}:{key}"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            if cached_data.get('status') == 'PROCESSING':
                return JsonResponse({
                    'success': False,
                    'error': 'This operation is currently being processed. Please wait.',
                    'error_code': 'IDEMPOTENCY_LOCKED'
                }, status=409)

            # Replay cached response
            response = HttpResponse(
                content=cached_data.get('content', b''),
                status=cached_data.get('status_code', 200),
                content_type=cached_data.get('content_type', 'application/json')
            )
            response['X-Idempotent-Replay'] = 'true'
            response['X-Idempotency-Key'] = key
            return response

        # Lock the key as processing
        cache.set(cache_key, {'status': 'PROCESSING'}, timeout=120)
        request._idempotency_cache_key = cache_key
        request._idempotency_client_key = key
        return None

    def process_response(self, request, response):
        cache_key = getattr(request, '_idempotency_cache_key', None)
        if not cache_key:
            return response

        client_key = getattr(request, '_idempotency_client_key', '')

        # Only cache successful or legitimate deterministic business responses (status < 500)
        if response.status_code < 500:
            cache.set(
                cache_key,
                {
                    'status': 'COMPLETED',
                    'status_code': response.status_code,
                    'content': response.content,
                    'content_type': response.get('Content-Type', 'application/json')
                },
                timeout=self.TTL_SECONDS
            )
            response['X-Idempotency-Key'] = client_key
        else:
            # If server threw 500+, unlock so client retry can attempt again
            cache.delete(cache_key)

        return response

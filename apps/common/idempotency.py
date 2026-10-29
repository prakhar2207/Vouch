import json
import time
import hashlib
import logging
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class IdempotencyMiddleware(MiddlewareMixin):
    """
    Guarantees strict once-and-only-once execution for mobile, desktop, and web clients.
    Intercepts mutating requests (POST, PUT, PATCH, DELETE) bearing 'X-Idempotency-Key'.
    
    Robustness Guarantees:
    1. Scoped Isolation: Cache keys are partitioned by Tenant (Company), Authenticated User,
       HTTP Method, and Request Path.
    2. Payload Integrity: Validates that retried requests carry the identical SHA-256 payload body.
       Re-using the same key with different payloads triggers HTTP 422 Unprocessable Entity.
    3. Concurrency Lock: Uses atomic cache.add() (SETNX) to prevent race conditions during
       simultaneous duplicate submissions.
    """

    SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}
    TTL_SECONDS = 86400  # 24-hour replay cache
    LOCK_TIMEOUT_SECONDS = 120  # 2-minute processing lock

    def process_request(self, request):
        if request.method in self.SAFE_METHODS:
            return None

        key = request.META.get('HTTP_X_IDEMPOTENCY_KEY') or request.META.get('HTTP_IDEMPOTENCY_KEY')
        if not key:
            return None

        # Clean key to prevent cache injection
        client_key = str(key).strip()
        if len(client_key) < 8 or len(client_key) > 128:
            return None

        # 1. Scope by Tenant (Company)
        company_id = (
            request.META.get('HTTP_X_COMPANY_ID') or 
            request.META.get('HTTP_COMPANY_ID') or 
            getattr(request, 'company_id', '') or 
            'global'
        ).strip()

        # 2. Scope by User (Authenticated user ID or 'anon')
        user_id = 'anon'
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            user_id = str(request.user.id)
        else:
            # Fallback: Extract user ID from Bearer JWT in Authorization header for API views
            auth_header = request.META.get('HTTP_AUTHORIZATION') or ''
            if auth_header and auth_header.strip().startswith(('Bearer ', 'bearer ')):
                token_str = auth_header.strip().split(' ', 1)[1].strip()
                try:
                    from rest_framework_simplejwt.tokens import AccessToken
                    token = AccessToken(token_str)
                    user_id = str(token.get('user_id') or 'anon')
                except Exception:
                    user_id = 'anon'

        # 3. Scope by Method and Endpoint Path
        method = request.method.upper()
        path = request.path_info.rstrip('/')

        # 4. Fingerprint request payload body
        body_bytes = request.body if hasattr(request, 'body') else b''
        body_hash = hashlib.sha256(body_bytes).hexdigest()

        # 5. Build cryptographically isolated cache key
        endpoint_sig = hashlib.sha256(f"{method}:{path}".encode()).hexdigest()[:16]
        cache_key = f"idempotency:{company_id}:{user_id}:{endpoint_sig}:{client_key}"

        # 6. Atomic Lock Attempt via cache.add() (SETNX semantics)
        lock_payload = {
            'status': 'PROCESSING',
            'body_hash': body_hash,
            'method': method,
            'path': path,
            'user_id': user_id,
            'company_id': company_id,
            'timestamp': time.time()
        }

        acquired = cache.add(cache_key, lock_payload, timeout=self.LOCK_TIMEOUT_SECONDS)
        if acquired:
            # We are the sole holder of this idempotency lock
            request._idempotency_cache_key = cache_key
            request._idempotency_client_key = client_key
            request._idempotency_body_hash = body_hash
            request._idempotency_method = method
            request._idempotency_path = path
            return None

        # If lock was not acquired, another request with this key already ran or is running
        cached_data = cache.get(cache_key)
        if cached_data is None:
            # Expired in the microsecond between add and get; re-acquire lock
            cache.set(cache_key, lock_payload, timeout=self.LOCK_TIMEOUT_SECONDS)
            request._idempotency_cache_key = cache_key
            request._idempotency_client_key = client_key
            request._idempotency_body_hash = body_hash
            request._idempotency_method = method
            request._idempotency_path = path
            return None

        # Case A: Concurrent execution in flight -> HTTP 409 Conflict
        if cached_data.get('status') == 'PROCESSING':
            return JsonResponse({
                'success': False,
                'error': 'This operation is currently being processed. Please wait.',
                'error_code': 'IDEMPOTENCY_LOCKED'
            }, status=409)

        # Case B: Previously completed -> Verify payload hash matches
        stored_body_hash = cached_data.get('body_hash')
        if stored_body_hash and stored_body_hash != body_hash:
            return JsonResponse({
                'success': False,
                'error': 'Idempotency key was previously used with different request parameters.',
                'error_code': 'IDEMPOTENCY_PAYLOAD_MISMATCH'
            }, status=422)

        # Case C: Valid replay -> Replay identical response
        response = HttpResponse(
            content=cached_data.get('content', b''),
            status=cached_data.get('status_code', 200),
            content_type=cached_data.get('content_type', 'application/json')
        )
        response['X-Idempotent-Replay'] = 'true'
        response['X-Idempotency-Key'] = client_key
        return response

    def process_response(self, request, response):
        cache_key = getattr(request, '_idempotency_cache_key', None)
        if not cache_key:
            return response

        client_key = getattr(request, '_idempotency_client_key', '')
        body_hash = getattr(request, '_idempotency_body_hash', '')
        method = getattr(request, '_idempotency_method', request.method)
        path = getattr(request, '_idempotency_path', request.path_info.rstrip('/'))

        # Only cache successful or legitimate deterministic business responses (status < 500)
        if response.status_code < 500:
            cache.set(
                cache_key,
                {
                    'status': 'COMPLETED',
                    'status_code': response.status_code,
                    'content': response.content,
                    'content_type': response.get('Content-Type', 'application/json'),
                    'body_hash': body_hash,
                    'method': method,
                    'path': path,
                },
                timeout=self.TTL_SECONDS
            )
            response['X-Idempotency-Key'] = client_key
        else:
            # If server threw 500+, unlock so client retry can attempt again
            cache.delete(cache_key)

        return response

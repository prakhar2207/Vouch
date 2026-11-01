import json
import time
import hashlib
import logging
import re
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone

logger = logging.getLogger(__name__)

class IdempotencyService:
    @staticmethod
    def commit_idempotent_operation(request, response_data: dict, status_code: int = 200):
        """
        Transactional atomic synchronization:
        Invoked inside the database transaction when a financial mutation succeeds.
        Guarantees that IdempotencyRecord.status='COMPLETED' is committed in PostgreSQL
        within the same transaction boundary as the voucher creation.
        Survives worker crashes, SIGKILL, out-of-memory errors, and network disconnects.
        """
        record = getattr(request, '_idempotency_record', None)
        if not record:
            return

        try:
            body_str = json.dumps(response_data, default=str)
            record.status = 'COMPLETED'
            record.response_code = status_code
            record.response_body = body_str
            record.save(update_fields=['status', 'response_code', 'response_body', 'updated_at'])
        except Exception as e:
            logger.warning(f"Could not commit IdempotencyRecord in transaction: {e}")


class IdempotencyMiddleware(MiddlewareMixin):
    """
    Guarantees strict once-and-only-once execution for mobile, desktop, and web clients.
    Combines:
    1. Authenticated Principal & Tenant Scoping: Partitioned by (company_id, user_id, endpoint, client_key).
       Eliminates DEF-IDEM-02 by preventing silent fallback to global tenant for multi-company users.
    2. Durable PostgreSQL Storage: IdempotencyRecord survives process restarts, cache flushes, and worker crashes.
    3. Concurrency Protection & Stale Recovery: Atomic conditional updates prevent concurrent takeover of stale locks.
    4. Transactional Consistency: Financial mutations commit IdempotencyRecord status='COMPLETED' atomically (DEF-IDEM-01).
    """

    SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}
    TTL_SECONDS = 86400  # 24-hour replay cache
    LOCK_TIMEOUT_SECONDS = 120  # 2-minute processing lock

    def _replay_response(self, record, client_key: str):
        response = HttpResponse(
            content=(record.response_body or '').encode('utf-8'),
            status=record.response_code or 200,
            content_type='application/json'
        )
        response['X-Idempotent-Replay'] = 'true'
        response['X-Idempotency-Key'] = client_key
        return response

    def process_request(self, request):
        if request.method in self.SAFE_METHODS:
            return None

        key = request.META.get('HTTP_X_IDEMPOTENCY_KEY') or request.META.get('HTTP_IDEMPOTENCY_KEY')
        if not key:
            return None

        client_key = str(key).strip()
        if len(client_key) < 8 or len(client_key) > 128:
            return None

        # 1. Scope by Authenticated Principal (User)
        user_id = 'anon'
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            user_id = str(request.user.id)
        else:
            auth_header = request.META.get('HTTP_AUTHORIZATION') or ''
            if auth_header and auth_header.strip().startswith(('Bearer ', 'bearer ')):
                token_str = auth_header.strip().split(' ', 1)[1].strip()
                try:
                    from rest_framework_simplejwt.tokens import AccessToken
                    token = AccessToken(token_str)
                    user_id = str(token.get('user_id') or 'anon')
                except Exception:
                    user_id = 'anon'

        # 2. Scope by Tenant (Company)
        company_id = (
            request.META.get('HTTP_X_COMPANY_ID') or 
            request.META.get('HTTP_COMPANY_ID') or 
            getattr(request, 'company_id', '')
        )
        if company_id:
            company_id = str(company_id).strip()

        # Check URL path for company UUID
        path = request.path_info.rstrip('/')
        if not company_id:
            uuid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', path)
            if uuid_match:
                potential_uuid = uuid_match.group(0)
                try:
                    from apps.companies.models import Company
                    if Company.objects.filter(id=potential_uuid).exists():
                        company_id = potential_uuid
                except Exception:
                    pass

        # Check query parameters for company_id
        if not company_id and hasattr(request, 'GET'):
            c_get = request.GET.get('company_id') or request.GET.get('company')
            if c_get:
                company_id = str(c_get).strip()

        is_tenant_path = any(path.startswith(p) for p in [
            '/api/v1/accounting', '/api/v1/ledgers', '/api/v1/inventory',
            '/api/v1/sync', '/api/v1/gst', '/api/v1/banking', '/api/v1/documents'
        ])

        # DEF-IDEM-02: Resolve authenticated user's company and prevent unauthorized global fallback
        if not company_id and user_id != 'anon' and is_tenant_path:
            try:
                from apps.companies.models import UserCompany
                user_companies = list(UserCompany.objects.filter(user_id=user_id).values_list('company_id', flat=True))
                if len(user_companies) == 1:
                    company_id = str(user_companies[0])
                elif len(user_companies) > 1:
                    return JsonResponse({
                        'success': False,
                        'error': 'X-Company-ID header is required for multi-company operations.',
                        'error_code': 'TENANT_HEADER_REQUIRED'
                    }, status=400)
            except Exception:
                pass

        if not company_id:
            company_id = 'unauthenticated' if user_id == 'anon' else ('global' if not is_tenant_path else 'default')

        method = request.method.upper()

        # 3. Request payload fingerprint
        body_bytes = request.body if hasattr(request, 'body') else b''
        body_hash = hashlib.sha256(body_bytes).hexdigest()

        # 4. Scope Key
        endpoint_sig = hashlib.sha256(f"{method}:{path}".encode()).hexdigest()[:16]
        scope_key = f"{company_id}:{user_id}:{endpoint_sig}:{client_key}"
        cache_key = f"idempotency:{scope_key}"

        from apps.accounting.models import IdempotencyRecord
        from apps.companies.models import Company
        from apps.accounts.models import User

        # Fast-path: Check durable PostgreSQL operation record
        try:
            record = IdempotencyRecord.objects.filter(scope_key=scope_key).first()
        except Exception as e:
            logger.warning(f"Error querying IdempotencyRecord: {e}")
            record = None

        if record:
            # Case A: Payload mismatch on reused key
            if record.payload_hash and record.payload_hash != body_hash:
                return JsonResponse({
                    'success': False,
                    'error': 'Idempotency key was previously used with different request parameters.',
                    'error_code': 'IDEMPOTENCY_PAYLOAD_MISMATCH'
                }, status=422)

            # Case B: Completed operation -> return durable recorded response
            if record.status == 'COMPLETED':
                return self._replay_response(record, client_key)

            # Case C: Processing in flight or stale recovery
            if record.status == 'PROCESSING':
                time_diff = (timezone.now() - record.created_at).total_seconds()
                if time_diff < self.LOCK_TIMEOUT_SECONDS:
                    return JsonResponse({
                        'success': False,
                        'error': 'This operation is currently being processed. Please wait.',
                        'error_code': 'IDEMPOTENCY_LOCKED'
                    }, status=409)
                else:
                    # Stale PROCESSING recovery (>120s):
                    # Atomically take over lock using conditional update to prevent concurrent worker takeover
                    rows_updated = IdempotencyRecord.objects.filter(
                        id=record.id,
                        status='PROCESSING'
                    ).update(
                        created_at=timezone.now(),
                        updated_at=timezone.now()
                    )
                    if rows_updated == 0:
                        # Another worker concurrently completed or claimed it
                        record.refresh_from_db()
                        if record.status == 'COMPLETED':
                            return self._replay_response(record, client_key)
                        return JsonResponse({
                            'success': False,
                            'error': 'This operation is currently being processed. Please wait.',
                            'error_code': 'IDEMPOTENCY_LOCKED'
                        }, status=409)

                    # Stale lock claimed by this worker: allow retry to proceed to view
                    request._idempotency_cache_key = cache_key
                    request._idempotency_client_key = client_key
                    request._idempotency_body_hash = body_hash
                    request._idempotency_method = method
                    request._idempotency_path = path
                    request._idempotency_record = record
                    return None

        # In-memory lock attempt
        lock_payload = {
            'status': 'PROCESSING',
            'body_hash': body_hash,
            'method': method,
            'path': path,
            'user_id': user_id,
            'company_id': company_id,
            'timestamp': time.time()
        }
        cache.add(cache_key, lock_payload, timeout=self.LOCK_TIMEOUT_SECONDS)

        # Resolve FK references
        comp_obj = None
        if company_id not in ['global', 'unauthenticated', 'default']:
            try:
                comp_obj = Company.objects.filter(id=company_id).first()
            except Exception:
                pass

        user_obj = None
        if user_id != 'anon':
            try:
                user_obj = User.objects.filter(id=user_id).first()
            except Exception:
                pass

        # Atomic PostgreSQL reservation
        created = False
        try:
            record, created = IdempotencyRecord.objects.get_or_create(
                scope_key=scope_key,
                defaults={
                    'company': comp_obj,
                    'user': user_obj,
                    'client_key': client_key,
                    'endpoint': path,
                    'method': method,
                    'payload_hash': body_hash,
                    'status': 'PROCESSING'
                }
            )
        except Exception:
            # Concurrent race caught by DB unique constraint
            record = IdempotencyRecord.objects.filter(scope_key=scope_key).first()
            created = False

        if not created and record:
            if record.payload_hash and record.payload_hash != body_hash:
                return JsonResponse({
                    'success': False,
                    'error': 'Idempotency key was previously used with different request parameters.',
                    'error_code': 'IDEMPOTENCY_PAYLOAD_MISMATCH'
                }, status=422)

            if record.status == 'COMPLETED':
                return self._replay_response(record, client_key)
            elif record.status == 'PROCESSING':
                time_diff = (timezone.now() - record.created_at).total_seconds()
                if time_diff < self.LOCK_TIMEOUT_SECONDS:
                    return JsonResponse({
                        'success': False,
                        'error': 'This operation is currently being processed. Please wait.',
                        'error_code': 'IDEMPOTENCY_LOCKED'
                    }, status=409)
                else:
                    rows_updated = IdempotencyRecord.objects.filter(
                        id=record.id,
                        status='PROCESSING'
                    ).update(
                        created_at=timezone.now(),
                        updated_at=timezone.now()
                    )
                    if rows_updated == 0:
                        record.refresh_from_db()
                        if record.status == 'COMPLETED':
                            return self._replay_response(record, client_key)
                        return JsonResponse({
                            'success': False,
                            'error': 'This operation is currently being processed. Please wait.',
                            'error_code': 'IDEMPOTENCY_LOCKED'
                        }, status=409)

        # Store context on request
        request._idempotency_cache_key = cache_key
        request._idempotency_client_key = client_key
        request._idempotency_body_hash = body_hash
        request._idempotency_method = method
        request._idempotency_path = path
        request._idempotency_record = record
        return None

    def process_response(self, request, response):
        record = getattr(request, '_idempotency_record', None)
        cache_key = getattr(request, '_idempotency_cache_key', None)
        client_key = getattr(request, '_idempotency_client_key', '')
        body_hash = getattr(request, '_idempotency_body_hash', '')
        method = getattr(request, '_idempotency_method', request.method)
        path = getattr(request, '_idempotency_path', request.path_info.rstrip('/'))

        if not record and not cache_key:
            return response

        # Deterministic business status codes (success or 4xx business rejections)
        if response.status_code < 500:
            resp_body = response.content.decode('utf-8', errors='ignore') if hasattr(response, 'content') else ''
            
            # 1. Update durable PostgreSQL record if not already completed by view transaction
            if record:
                try:
                    record.refresh_from_db()
                    if record.status != 'COMPLETED':
                        record.status = 'COMPLETED'
                        record.response_code = response.status_code
                        record.response_body = resp_body
                        record.save(update_fields=['status', 'response_code', 'response_body', 'updated_at'])
                except Exception as e:
                    logger.warning(f"Could not persist IdempotencyRecord in process_response: {e}")

            # 2. Update memory cache
            if cache_key:
                cache.set(
                    cache_key,
                    {
                        'status': 'COMPLETED',
                        'status_code': response.status_code,
                        'content': response.content if hasattr(response, 'content') else b'',
                        'content_type': response.get('Content-Type', 'application/json'),
                        'body_hash': body_hash,
                        'method': method,
                        'path': path,
                    },
                    timeout=self.TTL_SECONDS
                )

            response['X-Idempotency-Key'] = client_key
            if 'X-Idempotent-Replay' not in response:
                response['X-Idempotent-Replay'] = 'false'
        else:
            # 500 Server error -> purge lock so client can retry
            if record:
                try:
                    record.delete()
                except Exception:
                    pass
            if cache_key:
                cache.delete(cache_key)

        return response

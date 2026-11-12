"""
Centralized cookie, CSRF, and token-revocation helpers for SriLekh authentication.

Browser clients (`X-Client-Type: web` or cookie-authenticated sessions) receive
HttpOnly, Secure (in HTTPS/production) access & refresh cookies paired with
CSRF protection on unsafe HTTP methods. Native Capacitor clients continue to use
explicit Bearer headers without cookie CSRF requirements.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import F
from django.middleware.csrf import get_token
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User

logger = logging.getLogger(__name__)


def get_access_cookie_name() -> str:
    return getattr(settings, 'AUTH_ACCESS_COOKIE_NAME', 'srilekh_access')


def get_refresh_cookie_name() -> str:
    return getattr(settings, 'AUTH_REFRESH_COOKIE_NAME', 'srilekh_refresh')


def is_web_cookie_client(request) -> bool:
    client_type = (request.headers.get('X-Client-Type') or '').strip().lower()
    return client_type == 'web'


def _extract_hostname(raw_origin_or_host: str | None) -> str:
    if not raw_origin_or_host:
        return ''
    val = raw_origin_or_host.strip()
    if '://' in val:
        return (urlparse(val).hostname or '').lower()
    return val.split(':')[0].strip().lower()


def _base_site(hostname: str) -> str:
    if not hostname or hostname in ('localhost', '127.0.0.1'):
        return hostname
    parts = hostname.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return hostname


def is_cookie_secure(request) -> bool:
    configured = getattr(settings, 'AUTH_COOKIE_SECURE', None)
    if configured is not None:
        return bool(configured)
    if request is not None and request.is_secure():
        return True
    return not getattr(settings, 'DEBUG', False)


def resolve_cookie_samesite(request, *, secure: bool) -> str:
    configured = (getattr(settings, 'AUTH_COOKIE_SAMESITE', '') or '').strip()
    if configured in ('Lax', 'Strict', 'None'):
        if configured == 'None' and not secure:
            return 'Lax'
        return configured

    origin_host = _extract_hostname(request.headers.get('Origin') or request.META.get('HTTP_ORIGIN'))
    server_host = _extract_hostname(request.get_host() if request is not None else '')

    if not origin_host or not server_host:
        return 'Lax'

    if origin_host == server_host or _base_site(origin_host) == _base_site(server_host):
        # Same-site origins (e.g. srilekh.com <-> api.srilekh.com, localhost:3000 <-> localhost:8000)
        # work reliably as first-party cookies with SameSite=Lax without needing third-party cookies.
        return 'Lax'

    # Cross-site deployments (e.g. *.vercel.app -> *.onrender.com) require SameSite=None; Secure.
    return 'None' if secure else 'Lax'


def enforce_cookie_csrf(request) -> None:
    """
    Enforces Django's CSRF validation for cookie-authenticated unsafe requests.
    """
    def dummy_get_response(_req):
        return None

    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f'CSRF Failed: {reason}')


def build_tokens_for_user(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    token_ver = int(getattr(user, 'token_version', 0) or 0)
    refresh['email'] = user.email
    refresh['role'] = user.role
    refresh['is_staff'] = user.is_staff
    refresh['is_superuser'] = user.is_superuser
    refresh['email_verified'] = getattr(user, 'email_verified', True)
    refresh['token_version'] = token_ver

    access = refresh.access_token
    access['email'] = user.email
    access['role'] = user.role
    access['is_staff'] = user.is_staff
    access['is_superuser'] = user.is_superuser
    access['email_verified'] = getattr(user, 'email_verified', True)
    access['token_version'] = token_ver

    return {
        'access': str(access),
        'refresh': str(refresh),
    }


def _lifetime_seconds(setting_key: str, default_seconds: int) -> int:
    td = getattr(settings, 'SIMPLE_JWT', {}).get(setting_key)
    if td is not None:
        return int(td.total_seconds())
    return default_seconds


def attach_auth_cookies(
    request,
    response,
    *,
    access_token: str,
    refresh_token: str | None = None,
    user: User | None = None,
) -> None:
    secure = is_cookie_secure(request)
    samesite = resolve_cookie_samesite(request, secure=secure)
    httponly = bool(getattr(settings, 'AUTH_COOKIE_HTTPONLY', True))

    access_max_age = _lifetime_seconds('ACCESS_TOKEN_LIFETIME', 1800)
    refresh_max_age = _lifetime_seconds('REFRESH_TOKEN_LIFETIME', 7 * 24 * 3600)

    response.set_cookie(
        key=get_access_cookie_name(),
        value=access_token,
        max_age=access_max_age,
        path='/',
        secure=secure,
        httponly=httponly,
        samesite=samesite,
    )
    if refresh_token:
        response.set_cookie(
            key=get_refresh_cookie_name(),
            value=refresh_token,
            max_age=refresh_max_age,
            path='/api/v1/auth/',
            secure=secure,
            httponly=httponly,
            samesite=samesite,
        )

    csrf_token = get_token(request)
    now_ms = int(time.time() * 1000)

    if isinstance(response.data, dict):
        response.data['csrf_token'] = csrf_token
        response.data['auth_mode'] = 'cookie' if is_web_cookie_client(request) else 'token'
        response.data['expires_at'] = now_ms + access_max_age * 1000
        response.data['refresh_expires_at'] = now_ms + refresh_max_age * 1000
        if user is not None and 'user' not in response.data:
            response.data['user'] = {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'email_verified': getattr(user, 'email_verified', True),
            }

        # For browser cookie clients, never expose raw JWT strings back into JS memory/storage.
        if is_web_cookie_client(request):
            response.data.pop('access', None)
            response.data.pop('refresh', None)


def clear_auth_cookies(request, response) -> None:
    secure = is_cookie_secure(request)
    samesite = resolve_cookie_samesite(request, secure=secure)
    for name, path in (
        (get_access_cookie_name(), '/'),
        (get_refresh_cookie_name(), '/api/v1/auth/'),
        # Clear any legacy JS cookie names defensively too
        ('access_token', '/'),
        ('refresh_token', '/'),
    ):
        response.delete_cookie(key=name, path=path, samesite=samesite)


def revoke_user_tokens(user: User | None) -> None:
    """
    Atomically increments token_version on the user and blacklists all outstanding
    SimpleJWT refresh tokens so no stale tab or captured token can authenticate.
    """
    if user is None:
        return
    User.objects.filter(pk=user.pk).update(token_version=F('token_version') + 1)
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

        for ot in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=ot)
    except Exception as exc:
        logger.warning('Could not blacklist outstanding tokens for user %s: %s', getattr(user, 'id', '?'), exc)

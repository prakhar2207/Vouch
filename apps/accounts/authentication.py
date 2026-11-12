"""
DRF JWT Authentication supporting HttpOnly browser cookies + CSRF validation,
while preserving Authorization: Bearer authentication for Capacitor native and
API service clients and enforcing User.token_version revocation.
"""

from __future__ import annotations

from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .cookies import enforce_cookie_csrf, get_access_cookie_name

SAFE_HTTP_METHODS = ('GET', 'HEAD', 'OPTIONS', 'TRACE')


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                # Guard against accidental "Bearer undefined" / "Bearer null" from unmigrated JS callers
                decoded_str = raw_token.decode('utf-8', errors='ignore').strip()
                if decoded_str and decoded_str.lower() not in ('undefined', 'null'):
                    validated_token = self.get_validated_token(raw_token)
                    user = self.get_user(validated_token)
                    self._verify_token_version(user, validated_token)
                    return user, validated_token

        cookie_token = request.COOKIES.get(get_access_cookie_name())
        if not cookie_token:
            return None

        validated_token = self.get_validated_token(cookie_token)
        user = self.get_user(validated_token)
        self._verify_token_version(user, validated_token)

        if request.method not in SAFE_HTTP_METHODS:
            enforce_cookie_csrf(request)

        return user, validated_token

    @staticmethod
    def _verify_token_version(user, validated_token) -> None:
        current_version = int(getattr(user, 'token_version', 0) or 0)
        token_version = validated_token.get('token_version', None)
        if token_version is None:
            # Reject pre-migration legacy tokens if user has explicitly revoked sessions (version > 0)
            if current_version > 0:
                raise InvalidToken('Session revoked. Please sign in again.')
            return
        try:
            if int(token_version) != current_version:
                raise InvalidToken('Session revoked. Please sign in again.')
        except (TypeError, ValueError):
            raise exceptions.AuthenticationFailed('Invalid session version.')

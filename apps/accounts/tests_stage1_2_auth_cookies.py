"""
Stage 1.2 Targeted Regression Suite: HttpOnly Cookie Auth, SameSite, CSRF,
Refresh Rotation, Immediate Session/Stale-Tab Revocation, and Native Mode.
"""

from types import SimpleNamespace

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.cookies import resolve_cookie_samesite
from apps.accounts.models import User


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    AUTH_COOKIE_SECURE=False,
)
class Stage12AuthCookiesAndCsrfTests(TestCase):
    def setUp(self):
        self.email = 'stage12.merchant@srilekh-sandbox.local'
        self.password = 'SecureStage12Pass!@#'
        self.user = User.objects.create_user(
            email=self.email,
            password=self.password,
            role='OWNER',
            email_verified=True,
        )

    def test_web_login_sets_httponly_cookies_and_strips_json_jwts(self):
        client = APIClient(enforce_csrf_checks=True)
        res = client.post(
            '/api/v1/auth/login/',
            {'email': self.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get('auth_mode'), 'cookie')
        self.assertNotIn('access', res.data)
        self.assertNotIn('refresh', res.data)
        self.assertTrue(res.data.get('csrf_token'))

        access_cookie = res.cookies.get('srilekh_access')
        refresh_cookie = res.cookies.get('srilekh_refresh')
        self.assertIsNotNone(access_cookie)
        self.assertIsNotNone(refresh_cookie)
        self.assertTrue(bool(access_cookie['httponly']))
        self.assertTrue(bool(refresh_cookie['httponly']))
        self.assertEqual(refresh_cookie['path'], '/api/v1/auth/')
        self.assertEqual(access_cookie['path'], '/')

    def test_cookie_authenticated_read_and_csrf_enforced_write(self):
        client = APIClient(enforce_csrf_checks=True)
        login_res = client.post(
            '/api/v1/auth/login/',
            {'email': self.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        csrf_token = login_res.data['csrf_token']

        # GET /me/ via HttpOnly cookie succeeds without Authorization header
        me_res = client.get('/api/v1/auth/me/')
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.data['data']['email'], self.email)

        # State-changing PATCH without X-CSRFToken MUST fail (403 Forbidden)
        no_csrf_res = client.patch(
            '/api/v1/auth/me/',
            {'first_name': 'Blocked'},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        self.assertEqual(no_csrf_res.status_code, status.HTTP_403_FORBIDDEN)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')

        # State-changing PATCH with valid X-CSRFToken MUST succeed
        with_csrf_res = client.patch(
            '/api/v1/auth/me/',
            {'first_name': 'Aarav'},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(with_csrf_res.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Aarav')

    def test_cookie_refresh_rotation_and_replay_rejection(self):
        client = APIClient(enforce_csrf_checks=True)
        login_res = client.post(
            '/api/v1/auth/login/',
            {'email': self.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        csrf_token = login_res.data['csrf_token']
        first_refresh_val = login_res.cookies['srilekh_refresh'].value

        # Refresh without CSRF fails
        bad_refresh = client.post(
            '/api/v1/auth/refresh/',
            {},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        self.assertEqual(bad_refresh.status_code, status.HTTP_403_FORBIDDEN)

        # Refresh with CSRF succeeds & rotates cookie
        rot_res = client.post(
            '/api/v1/auth/refresh/',
            {},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(rot_res.status_code, status.HTTP_200_OK)
        self.assertNotIn('access', rot_res.data)
        self.assertNotIn('refresh', rot_res.data)
        second_refresh_val = rot_res.cookies['srilekh_refresh'].value
        self.assertNotEqual(first_refresh_val, second_refresh_val)

        # Replaying old rotated refresh token is rejected
        replay_client = APIClient()
        replay_res = replay_client.post(
            '/api/v1/auth/refresh/',
            {'refresh': first_refresh_val},
            format='json',
        )
        self.assertEqual(replay_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_revokes_cookies_refresh_and_stale_tab_access_token(self):
        # 1. Capture native/stale-tab Bearer access token BEFORE logout
        native_client = APIClient()
        cap_login = native_client.post(
            '/api/v1/auth/login/',
            {'email': self.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        )
        self.assertEqual(cap_login.status_code, status.HTTP_200_OK)
        stale_access = cap_login.data['access']
        stale_refresh = cap_login.data['refresh']

        # 2. Browser client logs in & logs out
        web_client = APIClient(enforce_csrf_checks=True)
        web_login = web_client.post(
            '/api/v1/auth/login/',
            {'email': self.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        csrf_token = web_login.data['csrf_token']
        captured_cookie_access = web_login.cookies['srilekh_access'].value

        # CSRF enforced on cookie logout
        bad_logout = web_client.post('/api/v1/auth/logout/', {}, format='json')
        self.assertEqual(bad_logout.status_code, status.HTTP_403_FORBIDDEN)

        logout_res = web_client.post(
            '/api/v1/auth/logout/',
            {},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)
        self.assertEqual(logout_res.cookies['srilekh_access'].value, '')
        self.assertEqual(logout_res.cookies['srilekh_refresh'].value, '')

        # 3. Stale tab trying to write with old Bearer access token or captured cookie is REJECTED (401)
        stale_bearer_client = APIClient()
        stale_bearer_client.credentials(HTTP_AUTHORIZATION=f'Bearer {stale_access}')
        stale_write = stale_bearer_client.patch(
            '/api/v1/auth/me/',
            {'first_name': 'StaleWrite'},
            format='json',
        )
        self.assertEqual(stale_write.status_code, status.HTTP_401_UNAUTHORIZED)

        stale_cookie_client = APIClient()
        stale_cookie_client.cookies['srilekh_access'] = captured_cookie_access
        self.assertEqual(stale_cookie_client.get('/api/v1/auth/me/').status_code, status.HTTP_401_UNAUTHORIZED)

        # Stale refresh token also rejected
        self.assertEqual(
            APIClient().post('/api/v1/auth/refresh/', {'refresh': stale_refresh}, format='json').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_capacitor_native_bearer_auth_compatible(self):
        client = APIClient(enforce_csrf_checks=True)
        res = client.post(
            '/api/v1/auth/login/',
            {'email': self.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get('auth_mode'), 'token')
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)

        # Clear cookies to prove native client relies purely on Bearer without cookies or CSRF
        client.cookies.clear()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        patch_res = client.patch('/api/v1/auth/me/', {'last_name': 'MobileUser'}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, 'MobileUser')

    def test_origin_aware_samesite_policy(self):
        rf = APIRequestFactory()
        same_site_req = rf.post('/api/v1/auth/login/', HTTP_ORIGIN='https://srilekh.com', HTTP_HOST='api.srilekh.com')
        self.assertEqual(resolve_cookie_samesite(same_site_req, secure=True), 'Lax')

        local_req = rf.post('/api/v1/auth/login/', HTTP_ORIGIN='http://localhost:3000', HTTP_HOST='localhost:8000')
        self.assertEqual(resolve_cookie_samesite(local_req, secure=False), 'Lax')

        cross_site_req = rf.post(
            '/api/v1/auth/login/',
            HTTP_ORIGIN='https://vouch-pi-one.vercel.app',
            HTTP_HOST='vouch-api-752s.onrender.com',
        )
        self.assertEqual(resolve_cookie_samesite(cross_site_req, secure=True), 'None')

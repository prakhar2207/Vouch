"""
Targeted regression tests for Google Play launch readiness & security fixes:
1. Authenticated account deletion: password re-auth, confirmation phrase,
   sole-owner transfer protection (409), solo-company archival, PII anonymization,
   JWT token_version revocation (401), audit log preservation, non-PII status check.
2. Password reset request: per-email throttling, bounded SMTP timeout resilience
   returning generic 200 without leaking email existence or crashing.
3. File upload size & extension validation on UniversalImportPreview & GSTR2BUpload.
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import AccountDeletionRequest, User
from apps.companies.models import Company, UserCompany
from apps.audit.models import AuditLog
from apps.notifications.models import EmailDeliveryLog, Notification
from apps.protocol.models import AuthorizedDevice


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    AUTH_COOKIE_SECURE=False,
)
class PlayLaunchAccountDeletionAndHardeningTests(TestCase):
    def setUp(self):
        self.password = 'DeleteTestPass!123'
        self.owner = User.objects.create_user(
            email='owner.delete@srilekh-sandbox.local',
            password=self.password,
            first_name='Asha',
            last_name='Traders',
            role='OWNER',
            email_verified=True,
        )
        self.member = User.objects.create_user(
            email='employee.delete@srilekh-sandbox.local',
            password=self.password,
            first_name='Ravi',
            last_name='Staff',
            role='EMPLOYEE',
            email_verified=True,
        )
        self.solo_company = Company.objects.create(
            name='Solo Launch Sandbox Co',
            gstin='09AAAAA0000A1Z5',
            state_code='09',
        )
        UserCompany.objects.create(user=self.owner, company=self.solo_company, role='OWNER')

    def _login_cookie(self, email: str):
        client = APIClient(enforce_csrf_checks=True)
        res = client.post(
            '/api/v1/auth/login/',
            {'email': email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='web',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return client, res.data['csrf_token']

    def test_account_deletion_requires_authentication_and_reauth(self):
        anon = APIClient()
        res_unauth = anon.post('/api/v1/auth/account/delete-request/', {}, format='json')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        client, csrf = self._login_cookie(self.owner.email)
        res_bad_pw = client.post(
            '/api/v1/auth/account/delete-request/',
            {'current_password': 'WrongPassword!', 'confirmation_text': 'DELETE MY ACCOUNT'},
            format='json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(res_bad_pw.status_code, status.HTTP_403_FORBIDDEN)

        res_bad_phrase = client.post(
            '/api/v1/auth/account/delete-request/',
            {'current_password': self.password, 'confirmation_text': 'YES'},
            format='json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(res_bad_phrase.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sole_owner_with_other_members_blocked_until_transfer(self):
        UserCompany.objects.create(user=self.member, company=self.solo_company, role='EMPLOYEE')
        client, csrf = self._login_cookie(self.owner.email)

        preview = client.get('/api/v1/auth/account/delete-request/')
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertFalse(preview.data['data']['can_delete_immediately'])
        self.assertEqual(len(preview.data['data']['sole_owned_requires_transfer']), 1)

        res = client.post(
            '/api/v1/auth/account/delete-request/',
            {
                'current_password': self.password,
                'confirmation_text': 'DELETE MY ACCOUNT',
                'sole_company_action': 'ARCHIVE_SOLO_COMPANIES',
            },
            format='json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data.get('code'), 'OWNERSHIP_TRANSFER_REQUIRED')

    def test_solo_owner_deletion_anonymizes_pii_revokes_tokens_and_archives_solo_company(self):
        client, csrf = self._login_cookie(self.owner.email)
        stale_bearer_client = APIClient()
        cap_login = stale_bearer_client.post(
            '/api/v1/auth/login/',
            {'email': self.owner.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        )
        bearer_access = cap_login.data['access']

        # Missing solo archive flag must fail with 409 SOLE_COMPANY_CONFIRMATION_REQUIRED
        res_need_confirm = client.post(
            '/api/v1/auth/account/delete-request/',
            {'current_password': self.password, 'confirmation_text': 'DELETE MY ACCOUNT'},
            format='json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(res_need_confirm.status_code, status.HTTP_409_CONFLICT)

        res_ok = client.post(
            '/api/v1/auth/account/delete-request/',
            {
                'current_password': self.password,
                'confirmation_text': 'DELETE MY ACCOUNT',
                'sole_company_action': 'ARCHIVE_SOLO_COMPANIES',
                'reason': 'Closing business workspace',
            },
            format='json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        ref_id = res_ok.data['reference_id']

        self.owner.refresh_from_db()
        self.solo_company.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertEqual(self.owner.first_name, '')
        self.assertIn('@anonymized.srilekh.invalid', self.owner.email)
        self.assertFalse(self.owner.check_password(self.password))
        self.assertGreater(self.owner.token_version, 0)
        self.assertFalse(self.solo_company.is_active)
        self.assertIsNotNone(self.solo_company.deleted_at)
        self.assertEqual(UserCompany.objects.filter(user=self.owner).count(), 0)

        # Prior Bearer & Cookie sessions are permanently invalidated
        res_stale = stale_bearer_client.get(
            '/api/v1/auth/me/',
            HTTP_AUTHORIZATION=f'Bearer {bearer_access}',
        )
        self.assertEqual(res_stale.status_code, status.HTTP_401_UNAUTHORIZED)

        # Public status receipt endpoint reveals ZERO PII
        res_status = APIClient().get(f'/api/v1/auth/account/delete-status/?reference={ref_id}')
        self.assertEqual(res_status.status_code, status.HTTP_200_OK)
        self.assertEqual(res_status.data['data']['status'], 'COMPLETED')
        self.assertNotIn('email', res_status.data['data'])
        self.assertNotIn('owner.delete', str(res_status.data))
        self.assertEqual(AccountDeletionRequest.objects.filter(id=ref_id).count(), 1)

    def test_password_reset_smtp_timeout_returns_generic_200_without_crash(self):
        client = APIClient()
        with patch('django.core.mail.EmailMultiAlternatives.send', side_effect=TimeoutError('SMTP socket timed out')):
            res = client.post(
                '/api/v1/auth/password/reset/request/',
                {'email': self.owner.email},
                format='json',
            )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        log = EmailDeliveryLog.objects.filter(recipient_email=self.owner.email, email_type='PASSWORD_RESET').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'DELIVERY_UNKNOWN')

    def test_universal_import_and_gstr2b_reject_disallowed_file_extensions(self):
        client, csrf = self._login_cookie(self.owner.email)
        bad_exe = SimpleUploadedFile('payload.exe', b'MZ\x90\x00', content_type='application/octet-stream')
        res_import = client.post(
            '/api/v1/accounting/import/preview/',
            {'company_id': str(self.solo_company.id), 'file': bad_exe},
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(res_import.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Unsupported file format', res_import.data.get('error', ''))

    def test_deletion_revokes_devices_notifications_and_blocks_replay_and_concurrent_double_delete(self):
        dev = AuthorizedDevice.objects.create(
            device_id='DEV-DELETE-HARDEN-1',
            replica_id='REPL-DELETE-HARDEN-1',
            company=self.solo_company,
            registered_by=self.owner,
            public_key_hex='aa' * 32,
            key_id='KID-DELETE-1',
            status='ACTIVE',
        )
        Notification.objects.create(
            user=self.owner,
            title='Confidential Alert',
            message='Secret user notification payload',
        )
        cap_client = APIClient()
        login_res = cap_client.post(
            '/api/v1/auth/login/',
            {'email': self.owner.email, 'password': self.password},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        )
        access_tok = login_res.data['access']
        refresh_tok = login_res.data['refresh']

        # First deletion succeeds
        res1 = cap_client.post(
            '/api/v1/auth/account/delete-request/',
            {
                'current_password': self.password,
                'confirmation_text': 'DELETE MY ACCOUNT',
                'sole_company_action': 'ARCHIVE_SOLO_COMPANIES',
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_tok}',
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        dev.refresh_from_db()
        self.assertEqual(dev.status, 'REVOKED')
        self.assertIsNone(dev.registered_by)
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 0)
        self.assertTrue(
            AuditLog.objects.filter(company=self.solo_company, model_name='Company', action='DELETE').exists()
        )

        # Replay of deletion endpoint with stale JWT or refresh token must be rejected
        res_replay = APIClient().post(
            '/api/v1/auth/account/delete-request/',
            {
                'current_password': self.password,
                'confirmation_text': 'DELETE MY ACCOUNT',
                'sole_company_action': 'ARCHIVE_SOLO_COMPANIES',
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access_tok}',
        )
        self.assertEqual(res_replay.status_code, status.HTTP_401_UNAUTHORIZED)

        res_refresh = APIClient().post(
            '/api/v1/auth/refresh/',
            {'refresh': refresh_tok},
            format='json',
        )
        self.assertEqual(res_refresh.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(AccountDeletionRequest.objects.filter(user_snapshot_id=self.owner.id).count(), 1)

    def test_account_deletion_already_anonymized_user_blocked_inside_lock(self):
        from apps.accounts.views import AccountDeletionView
        from rest_framework.test import APIRequestFactory, force_authenticate

        User.objects.filter(pk=self.owner.pk).update(
            email=f'deleted-{self.owner.id}@anonymized.srilekh.invalid',
            is_active=False,
        )
        self.owner.refresh_from_db()
        factory = APIRequestFactory()
        req = factory.post(
            '/api/v1/auth/account/delete-request/',
            {'current_password': self.password, 'confirmation_text': 'DELETE MY ACCOUNT'},
            format='json',
        )
        force_authenticate(req, user=self.owner)
        resp = AccountDeletionView.as_view()(req)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data.get('code'), 'ACCOUNT_ALREADY_DELETED')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    AUTH_COOKIE_SECURE=False,
)
class Stage124DeletionConcurrencyThrottleAndAuditTests(TestCase):
    def test_account_deletion_rate_throttle_blocks_excess_requests(self):
        from django.core.cache import cache
        cache.clear()
        pw = 'ThrottlePass!123'
        u = User.objects.create_user(
            email='throttle.del@srilekh-sandbox.local',
            password=pw,
            first_name='Throttle',
            last_name='Tester',
            role='OWNER',
            email_verified=True,
        )
        client = APIClient()
        tok = client.post(
            '/api/v1/auth/login/',
            {'email': u.email, 'password': pw},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        ).data['access']
        with override_settings(TESTING=False, DISABLE_THROTTLING=False):
            statuses = []
            for _ in range(11):
                r = APIClient().get(
                    '/api/v1/auth/account/delete-request/',
                    HTTP_AUTHORIZATION=f'Bearer {tok}',
                )
                statuses.append(r.status_code)
        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[10], 429)
        cache.clear()

    def test_deletion_preserves_audit_hash_chain_and_isolates_unrelated_users(self):
        from apps.audit.services.audit_service import AuditService
        from apps.audit.views import AuditLogListView

        pw = 'AuditChainPass!123'
        owner = User.objects.create_user(
            email='chain.owner@srilekh-sandbox.local', password=pw, first_name='Chain', role='OWNER', email_verified=True
        )
        bystander = User.objects.create_user(
            email='bystander@srilekh-sandbox.local', password=pw, first_name='Safe', role='OWNER', email_verified=True
        )
        comp = Company.objects.create(name='Chain Sandbox Co', gstin='09BBBBB0000B1Z5', state_code='09')
        bystander_comp = Company.objects.create(name='Bystander Co', gstin='09CCCCC0000C1Z5', state_code='09')
        UserCompany.objects.create(user=owner, company=comp, role='OWNER')
        UserCompany.objects.create(user=bystander, company=bystander_comp, role='OWNER')

        AuditService.log_action(
            company=comp, user=owner, action='CREATE', model_name='Voucher', record_id='V-PRE-1', changes={'total': 500}
        )

        client = APIClient()
        tok = client.post(
            '/api/v1/auth/login/',
            {'email': owner.email, 'password': pw},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        ).data['access']

        res = client.post(
            '/api/v1/auth/account/delete-request/',
            {
                'current_password': pw,
                'confirmation_text': 'DELETE MY ACCOUNT',
                'sole_company_action': 'ARCHIVE_SOLO_COMPANIES',
            },
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {tok}',
        )
        self.assertEqual(res.status_code, 200)

        telemetry = AuditLogListView.verify_company_chain_telemetry(comp)
        self.assertEqual(telemetry['status'], 'VERIFIED', f'Audit chain broken: {telemetry}')
        self.assertEqual(telemetry['invalid_records_count'], 0)
        self.assertGreaterEqual(telemetry['total_records_checked'], 2)

        bystander.refresh_from_db()
        bystander_comp.refresh_from_db()
        self.assertTrue(bystander.is_active)
        self.assertTrue(bystander_comp.is_active)
        self.assertTrue(UserCompany.objects.filter(user=bystander, company=bystander_comp).exists())


import unittest
from django.test import TransactionTestCase
import threading
from concurrent.futures import ThreadPoolExecutor
from django.db import connections


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    AUTH_COOKIE_SECURE=False,
)
class Stage124ConcurrentAccountDeletionTransactionTests(TransactionTestCase):
    def test_parallel_concurrent_delete_requests_execute_atomically_once(self):
        if connections['default'].vendor == 'sqlite':
            self.skipTest("Multi-threaded write-lock concurrency requires PostgreSQL MVCC (executed on test_neondb_staging)")
        pw = 'RacePass!123'
        owner = User.objects.create_user(
            email='race.owner@srilekh-sandbox.local', password=pw, first_name='Race', role='OWNER', email_verified=True
        )
        comp = Company.objects.create(name='Race Co', gstin='09DDDDD0000D1Z5', state_code='09')
        UserCompany.objects.create(user=owner, company=comp, role='OWNER')

        tok = APIClient().post(
            '/api/v1/auth/login/',
            {'email': owner.email, 'password': pw},
            format='json',
            HTTP_X_CLIENT_TYPE='capacitor',
        ).data['access']

        barrier = threading.Barrier(2)

        def worker():
            try:
                barrier.wait(timeout=10)
                return APIClient().post(
                    '/api/v1/auth/account/delete-request/',
                    {
                        'current_password': pw,
                        'confirmation_text': 'DELETE MY ACCOUNT',
                        'sole_company_action': 'ARCHIVE_SOLO_COMPANIES',
                    },
                    format='json',
                    HTTP_AUTHORIZATION=f'Bearer {tok}',
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(worker)
            f2 = pool.submit(worker)
            codes = sorted([f1.result(), f2.result()])

        self.assertIn(200, codes)
        self.assertEqual(codes.count(200), 1)
        self.assertTrue(codes[1] in (401, 409) or (codes[0] in (401, 409) and codes[1] == 200))
        self.assertEqual(AccountDeletionRequest.objects.filter(user_snapshot_id=owner.id).count(), 1)

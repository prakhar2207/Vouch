import uuid
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.notifications.models import EmailDeliveryLog


class Stage415NotificationAuthorizationTests(TestCase):
    """Strict tenant authorization regression tests for EmailDeliveryLog and Preferences endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.comp_a = Company.objects.create(name="Notif Auth Tenant A", state_code="27")
        self.comp_b = Company.objects.create(name="Notif Auth Tenant B", state_code="27")

        self.owner_a = User.objects.create_user(email="owner_a@n415.test", password="Password123!", role="OWNER", email_verified=True)
        self.admin_a = User.objects.create_user(email="admin_a@n415.test", password="Password123!", role="ADMIN", email_verified=True)
        self.emp_a = User.objects.create_user(email="emp_a@n415.test", password="Password123!", role="EMPLOYEE", email_verified=True)
        self.viewer_a = User.objects.create_user(email="viewer_a@n415.test", password="Password123!", role="VIEWER", email_verified=True)
        self.ca_a = User.objects.create_user(email="ca_a@n415.test", password="Password123!", role="CA", email_verified=True)
        self.multi_user = User.objects.create_user(email="multi@n415.test", password="Password123!", role="OWNER", email_verified=True)
        self.no_company_user = User.objects.create_user(email="orphan@n415.test", password="Password123!", role="OWNER", email_verified=True)

        UserCompany.objects.create(user=self.owner_a, company=self.comp_a, role="OWNER")
        UserCompany.objects.create(user=self.admin_a, company=self.comp_a, role="ADMIN")
        UserCompany.objects.create(user=self.emp_a, company=self.comp_a, role="EMPLOYEE")
        UserCompany.objects.create(user=self.viewer_a, company=self.comp_a, role="VIEWER")
        UserCompany.objects.create(user=self.ca_a, company=self.comp_a, role="CA")

        UserCompany.objects.create(user=self.multi_user, company=self.comp_a, role="OWNER")
        UserCompany.objects.create(user=self.multi_user, company=self.comp_b, role="OWNER")

        self.log_a = EmailDeliveryLog.objects.create(
            company=self.comp_a, recipient_email="cust_a@n415.test", subject="Inv A",
            email_type="INVOICE_POSTED", status="FAILED", idempotency_key=f"k_a_{uuid.uuid4()}",
        )
        self.log_b = EmailDeliveryLog.objects.create(
            company=self.comp_b, recipient_email="cust_b@n415.test", subject="Inv B",
            email_type="INVOICE_POSTED", status="FAILED", idempotency_key=f"k_b_{uuid.uuid4()}",
        )

    def test_unauthenticated_rejected_401(self):
        res = self.client.get(f"/api/v1/notifications/logs/?company_id={self.comp_a.id}")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_same_tenant_owner_and_admin_200_and_roles_blocked_403(self):
        for u in (self.owner_a, self.admin_a):
            self.client.force_authenticate(user=u)
            res = self.client.get(f"/api/v1/notifications/logs/?company_id={self.comp_a.id}")
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(len(res.data["data"]), 1)
            self.assertEqual(res.data["data"][0]["recipient_email"], "cust_a@n415.test")

        for u in (self.emp_a, self.viewer_a, self.ca_a):
            self.client.force_authenticate(user=u)
            res = self.client.get(f"/api/v1/notifications/logs/?company_id={self.comp_a.id}")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_explicit_unauthorized_company_returns_403_no_silent_fallback(self):
        self.client.force_authenticate(user=self.owner_a)
        res_q = self.client.get(f"/api/v1/notifications/logs/?company_id={self.comp_b.id}")
        self.assertEqual(res_q.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("cust_a@n415.test", str(res_q.data))
        self.assertNotIn("cust_b@n415.test", str(res_q.data))

        res_h = self.client.get("/api/v1/notifications/logs/", HTTP_X_COMPANY_ID=str(self.comp_b.id))
        self.assertEqual(res_h.status_code, status.HTTP_403_FORBIDDEN)

        # Preferences endpoint also rejects cross-tenant company_id cleanly
        res_p = self.client.get(f"/api/v1/notifications/preferences/?company_id={self.comp_b.id}")
        self.assertEqual(res_p.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_invalid_and_conflicting_company_ids_rejected_cleanly(self):
        self.client.force_authenticate(user=self.owner_a)
        res_unknown = self.client.get(f"/api/v1/notifications/logs/?company_id={uuid.uuid4()}")
        self.assertEqual(res_unknown.status_code, status.HTTP_404_NOT_FOUND)

        res_bad = self.client.get("/api/v1/notifications/logs/?company_id=not-a-uuid")
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)

        res_conflict = self.client.get(
            f"/api/v1/notifications/logs/?company_id={self.comp_a.id}",
            HTTP_X_COMPANY_ID=str(self.comp_b.id),
        )
        self.assertEqual(res_conflict.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_company_param_single_multi_and_orphan_user(self):
        self.client.force_authenticate(user=self.owner_a)
        res_single = self.client.get("/api/v1/notifications/logs/")
        self.assertEqual(res_single.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_single.data["data"]), 1)

        self.client.force_authenticate(user=self.multi_user)
        res_b = self.client.get(f"/api/v1/notifications/logs/?company_id={self.comp_b.id}")
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        self.assertEqual(res_b.data["data"][0]["recipient_email"], "cust_b@n415.test")

        self.client.force_authenticate(user=self.no_company_user)
        res_none = self.client.get("/api/v1/notifications/logs/")
        self.assertEqual(res_none.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retry_cross_tenant_and_rbac_authorization(self):
        self.client.force_authenticate(user=self.owner_a)
        # Explicit unauthorized company_id -> 403
        res_explicit = self.client.post(f"/api/v1/notifications/logs/{self.log_b.id}/retry/?company_id={self.comp_b.id}")
        self.assertEqual(res_explicit.status_code, status.HTTP_403_FORBIDDEN)

        # Without explicit company_id (resolved to comp_a) -> 404 (no cross-tenant leakage)
        res_implicit = self.client.post(f"/api/v1/notifications/logs/{self.log_b.id}/retry/")
        self.assertEqual(res_implicit.status_code, status.HTTP_404_NOT_FOUND)

        # EMPLOYEE / CA / VIEWER denied 403 on same-tenant log retry
        for u in (self.emp_a, self.viewer_a, self.ca_a):
            self.client.force_authenticate(user=u)
            res_role = self.client.post(f"/api/v1/notifications/logs/{self.log_a.id}/retry/?company_id={self.comp_a.id}")
            self.assertEqual(res_role.status_code, status.HTTP_403_FORBIDDEN)

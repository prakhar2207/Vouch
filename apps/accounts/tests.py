from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.companies.models import Company, UserCompany

class RegisterViewTests(TestCase):
    """
    P0 Verification: Proves that the legacy direct registration endpoint
    (/api/v1/auth/register/) is permanently closed (HTTP 410 GONE) and cannot
    provision users, companies, or ledgers without verified email ownership.
    """
    def setUp(self):
        self.client = APIClient()

    def test_legacy_direct_registration_rejected_410(self):
        """P0 Invariant: Direct registration without email OTP verification returns 410 GONE."""
        payload = {
            "email": "ranjana@example.com",
            "password": "SecurePass123!@#",
            "name": "Shukla Enterprises",
            "gstin": "09ACHFS9225Q1Z7",
            "phone": "6386623787",
            "state_code": "09",
            "address": "123 Civil Lines, Lucknow",
            "proprietor_name": "Ranjana Shukla",
            "proprietor_phone": "6386623787"
        }
        response = self.client.post("/api/v1/auth/register/", data=payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["code"], "LEGACY_REGISTRATION_DEPRECATED")
        self.assertIn("/api/v1/auth/register/initiate/", response.data["redirect_to"])

        # Crucial Invariant: Proves zero database side-effects
        self.assertFalse(User.objects.filter(email="ranjana@example.com").exists())
        self.assertFalse(Company.objects.filter(name="Shukla Enterprises").exists())

    def test_forged_verification_flag_rejected(self):
        """P0 Security: An attacker providing forged email_verified=True is still rejected with 410 GONE."""
        payload = {
            "email": "attacker@exploit.local",
            "password": "AttackerPass123!@#",
            "name": "Attacker Corp",
            "email_verified": True,
            "is_verified": True,
        }
        response = self.client.post("/api/v1/auth/register/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertFalse(response.data["success"])
        self.assertFalse(User.objects.filter(email="attacker@exploit.local").exists())

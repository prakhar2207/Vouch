from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.companies.models import Company, UserCompany

class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_successful_registration(self):
        payload = {
            "email": "ranjana@example.com",
            "password": "password123",
            "name": "Shukla Enterprises",
            "gstin": "09ACHFS9225Q1Z7",
            "phone": "6386623787",
            "state_code": "09",
            "address": "123 Civil Lines, Lucknow",
            "proprietor_name": "Ranjana Shukla",
            "proprietor_phone": "6386623787"
        }
        response = self.client.post("/api/v1/auth/register/", data=payload, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        self.assertIn("access", response.data)

        # Verify DB records
        user = User.objects.get(email="ranjana@example.com")
        self.assertIsNotNone(user)
        user_company = UserCompany.objects.get(user=user)
        self.assertEqual(user_company.company.name, "Shukla Enterprises")
        self.assertEqual(user_company.company.pan, "ACHFS9225Q")
        self.assertEqual(user_company.company.proprietor_name, "Ranjana Shukla")

    def test_duplicate_email_registration(self):
        User.objects.create_user(email="ranjana@example.com", password="password123")
        payload = {
            "email": "ranjana@example.com",
            "password": "password456",
            "name": "Another Company",
        }
        response = self.client.post("/api/v1/auth/register/", data=payload, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertIn("already exists", response.data["error"])

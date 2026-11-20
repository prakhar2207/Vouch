import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, FinancialYear, VoucherSequence

User = get_user_model()

class SuperadminCompanyDeletionTestCase(TestCase):
    def setUp(self):
        # 1. Superadmin User
        self.superadmin = User.objects.create_user(
            email="superadmin@example.com",
            password="StrongPassword@123",
            is_staff=True,
            is_superuser=True,
            role="ADMIN"
        )
        # 2. Regular User
        self.regular_user = User.objects.create_user(
            email="regular@example.com",
            password="StrongPassword@123",
            is_staff=False,
            is_superuser=False,
            role="OWNER"
        )
        self.client = APIClient()

    def test_regular_user_cannot_delete_companies(self):
        self.client.force_authenticate(user=self.regular_user)
        company = Company.objects.create(name="Tenant X", gstin="09ABCDE1234F1Z1")
        
        # Single delete attempt
        res = self.client.delete(f"/api/v1/superadmin/companies/{company.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Bulk delete attempt
        res_bulk = self.client.post("/api/v1/superadmin/companies/bulk-delete/", {"company_ids": [str(company.id)]}, format="json")
        self.assertEqual(res_bulk.status_code, status.HTTP_403_FORBIDDEN)

    def test_single_company_cascade_delete(self):
        self.client.force_authenticate(user=self.superadmin)
        company = Company.objects.create(name="Delete Me Ltd", gstin="09DELME1234F1Z2")
        UserCompany.objects.create(user=self.regular_user, company=company, role="OWNER")
        
        # Add dependent items
        group = LedgerGroup.objects.create(company=company, name="Sales Accounts", nature="INCOME")
        ledger = Ledger.objects.create(company=company, group=group, name="Sales", ledger_type="SALES")
        cat = ProductCategory.objects.create(company=company, name="Bearings")
        prod = Product.objects.create(company=company, name="Ball Bearing 6204", category=cat)

        res = self.client.delete(f"/api/v1/superadmin/companies/{company.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])

        # Verify company and cascading models are deleted
        self.assertFalse(Company.objects.filter(id=company.id).exists())
        self.assertFalse(Ledger.objects.filter(id=ledger.id).exists())
        self.assertFalse(Product.objects.filter(id=prod.id).exists())
        self.assertFalse(UserCompany.objects.filter(company_id=company.id).exists())

    def test_bulk_company_cascade_delete(self):
        self.client.force_authenticate(user=self.superadmin)
        
        c1 = Company.objects.create(name="Bulk Tenant 1", gstin="09BULK11234F1Z1")
        c2 = Company.objects.create(name="Bulk Tenant 2", gstin="09BULK21234F1Z2")
        c3 = Company.objects.create(name="Bulk Tenant 3", gstin="09BULK31234F1Z3")

        # Attach dependencies to c1 and c2
        g1 = LedgerGroup.objects.create(company=c1, name="Bank Accounts", nature="ASSET")
        Ledger.objects.create(company=c1, group=g1, name="HDFC", ledger_type="BANK")
        
        g2 = LedgerGroup.objects.create(company=c2, name="Sundry Debtors", nature="ASSET")
        Ledger.objects.create(company=c2, group=g2, name="Customer A", ledger_type="CUSTOMER")

        payload = {
            "company_ids": [str(c1.id), str(c2.id)]
        }
        res = self.client.post("/api/v1/superadmin/companies/bulk-delete/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])
        self.assertEqual(res.data["deleted_count"], 2)

        # c1 and c2 must be gone
        self.assertFalse(Company.objects.filter(id=c1.id).exists())
        self.assertFalse(Company.objects.filter(id=c2.id).exists())
        self.assertFalse(Ledger.objects.filter(company_id=c1.id).exists())
        self.assertFalse(Ledger.objects.filter(company_id=c2.id).exists())

        # c3 was NOT in the list and must remain untouched
        self.assertTrue(Company.objects.filter(id=c3.id).exists())

    def test_protected_tenants_cannot_be_deleted(self):
        self.client.force_authenticate(user=self.superadmin)
        
        # Test Maa Annapurna Belting Store protection
        protected_id_1 = "5d2e5dea-ff86-4871-b2af-fe1c5a05c03c"
        protected_id_2 = "4e62863a-08f9-4e99-b0bd-64873acfdd33"

        # Bulk delete attempt on protected IDs
        payload = {
            "company_ids": [protected_id_1, protected_id_2]
        }
        res = self.client.post("/api/v1/superadmin/companies/bulk-delete/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["deleted_count"], 0)
        self.assertEqual(len(res.data["skipped"]), 2)

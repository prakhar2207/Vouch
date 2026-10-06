from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.companies.models import Company, UserCompany
from apps.companies.services import CompanyBankService
from apps.companies.views import provision_company_defaults
from apps.ledgers.models import Ledger, LedgerGroup

User = get_user_model()

class AutoBankLedgerSyncTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="testowner@example.com",
            password="StrongPassword@123",
            role="OWNER"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_company_creation_auto_creates_bank_ledger(self):
        """
        When a company is provisioned with bank details, a corresponding Bank Ledger
        is automatically created under 'Bank Accounts' group.
        """
        company = Company.objects.create(
            name="Apex Engineering Ltd",
            gstin="27ABCDE1234F1Z5",
            bank_name="HDFC Bank",
            bank_account_number="50200098765432",
            bank_ifsc="HDFC0001234",
            upi_id="apex@okhdfcbank"
        )
        UserCompany.objects.create(user=self.user, company=company, role="OWNER")

        # Provision defaults
        provision_company_defaults(company)

        # Verify Bank Ledger was automatically created
        bank_ledgers = Ledger.objects.filter(company=company, ledger_type="BANK")
        self.assertEqual(bank_ledgers.count(), 1)

        ledger = bank_ledgers.first()
        self.assertEqual(ledger.name, "HDFC Bank (A/c ...5432)")
        self.assertEqual(ledger.bank_account_number, "50200098765432")
        self.assertEqual(ledger.bank_ifsc, "HDFC0001234")
        self.assertEqual(ledger.upi_id, "apex@okhdfcbank")
        self.assertEqual(ledger.group.name, "Bank Accounts")
        self.assertEqual(ledger.group.nature, "ASSET")

    def test_company_update_syncs_bank_ledger(self):
        """
        When a company without bank details later configures bank details in settings,
        the bank ledger is automatically generated and kept in sync.
        """
        company = Company.objects.create(
            name="Modern Traders",
            gstin="07AAAAA0000A1Z5"
        )
        UserCompany.objects.create(user=self.user, company=company, role="OWNER")
        provision_company_defaults(company)

        # Initially 0 bank ledgers
        self.assertEqual(Ledger.objects.filter(company=company, ledger_type="BANK").count(), 0)

        # Now company configures bank details in settings
        company.bank_name = "ICICI Bank"
        company.bank_account_number = "112233445566"
        company.bank_ifsc = "ICIC0009999"
        company.upi_id = "moderntraders@icici"
        company.save()

        # Signal / service runs and auto-creates the ledger
        CompanyBankService.sync_company_bank_ledger(company)

        bank_ledgers = Ledger.objects.filter(company=company, ledger_type="BANK")
        self.assertEqual(bank_ledgers.count(), 1)
        ledger = bank_ledgers.first()
        self.assertEqual(ledger.name, "ICICI Bank (A/c ...5566)")
        self.assertEqual(ledger.bank_account_number, "112233445566")
        self.assertEqual(ledger.bank_ifsc, "ICIC0009999")

        # Update IFSC and UPI
        company.bank_ifsc = "ICIC0008888"
        company.upi_id = "modern@icici"
        company.save()
        CompanyBankService.sync_company_bank_ledger(company)

        # Still exactly 1 bank ledger, updated in-place without duplicates
        self.assertEqual(Ledger.objects.filter(company=company, ledger_type="BANK").count(), 1)
        ledger.refresh_from_db()
        self.assertEqual(ledger.bank_ifsc, "ICIC0008888")
        self.assertEqual(ledger.upi_id, "modern@icici")

    def test_ledger_creation_with_company_default_sync(self):
        """
        When creating a bank ledger via Ledgers API, setting set_as_company_default
        syncs bank details to Company for invoice printing.
        """
        company = Company.objects.create(
            name="Sunrise Solar",
            gstin="09ABCDE5678F1Z2"
        )
        UserCompany.objects.create(user=self.user, company=company, role="OWNER")
        provision_company_defaults(company)

        res = self.client.post(
            f"/api/v1/ledgers/{company.id}/",
            data={
                "name": "State Bank of India (A/c ...7890)",
                "bank_name": "State Bank of India",
                "bank_account_number": "409988776655",
                "bank_ifsc": "SBIN0004321",
                "upi_id": "sunrise@sbi",
                "ledger_type": "BANK",
                "group_name": "Bank Accounts",
                "set_as_company_default": True
            },
            format="json"
        )
        self.assertEqual(res.status_code, 201)

        company.refresh_from_db()
        self.assertEqual(company.bank_name, "State Bank of India")
        self.assertEqual(company.bank_account_number, "409988776655")
        self.assertEqual(company.bank_ifsc, "SBIN0004321")
        self.assertEqual(company.upi_id, "sunrise@sbi")

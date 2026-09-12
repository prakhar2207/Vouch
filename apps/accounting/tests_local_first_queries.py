import uuid
import datetime
from decimal import Decimal
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APITestCase
from rest_framework import status

from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import (
    FinancialYear, Voucher, VoucherItem, LedgerEntry, PaymentAllocation, BankTransaction
)
from apps.inventory.models import Product

class LocalFirstQueriesAndTransferReductionTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Local First Test Enterprise",
            gstin="27AABCT9999F1Z1",
            state_code="27"
        )
        self.user = User.objects.create_user(
            email="localfirst_test@vouch.com",
            password="securepassword123"
        )
        self.company.users.create(user=self.user, role="OWNER")
        self.client.force_authenticate(user=self.user)

        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31)
        )

        self.debtor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.income_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")
        self.bank_grp = LedgerGroup.objects.create(company=self.company, name="Bank Accounts", nature="ASSET")

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.bank_grp,
            name="HDFC Current A/c",
            ledger_type="BANK",
            opening_balance_type="DEBIT",
            current_balance=Decimal("250000.00")
        )

        self.party_customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Alpha Corp",
            ledger_type="CUSTOMER",
            opening_balance=Decimal("0.00"),
            opening_balance_type="DEBIT",
            current_balance=Decimal("15000.00")
        )

        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.income_grp,
            name="General Sales",
            ledger_type="SALES",
            opening_balance_type="CREDIT",
            current_balance=Decimal("0.00")
        )

        self.product = Product.objects.create(
            company=self.company,
            name="Precision Widget A",
            sku="WGT-001",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("700.00"),
            stock_quantity=Decimal("100.00")
        )

        # Create 5 test vouchers with line items, ledger entries, and attachments
        self.vouchers = []
        for i in range(5):
            v = Voucher.objects.create(
                company=self.company,
                financial_year=self.fy,
                created_by=self.user,
                party_ledger=self.party_customer,
                voucher_type="SALES",
                voucher_number=f"INV-LF-{i+1:03d}",
                voucher_date=datetime.date(2026, 5, 10 + i),
                status="POSTED",
                total_amount=Decimal("1180.00"),
                attachment_data="data:application/pdf;base64,JVBERi0xLjQKJcTl8uXr..." * 50,
                attachment_mime="application/pdf"
            )
            VoucherItem.objects.create(
                voucher=v,
                product=self.product,
                quantity=Decimal("1.00"),
                rate=Decimal("1000.00"),
                taxable_amount=Decimal("1000.00"),
                gst_rate=Decimal("18.00"),
                total_amount=Decimal("1180.00")
            )
            LedgerEntry.objects.create(
                voucher=v,
                company=self.company,
                ledger=self.party_customer,
                debit_amount=Decimal("1180.00"),
                credit_amount=Decimal("0.00")
            )
            LedgerEntry.objects.create(
                voucher=v,
                company=self.company,
                ledger=self.sales_ledger,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("1180.00")
            )
            self.vouchers.append(v)

    def test_sync_pull_omits_items_and_entries_by_default(self):
        """
        P0 Test: Normal sync pull must omit voucher_items and ledger_entries
        to eliminate discarded wire transfer.
        """
        payload = {
            "company_id": str(self.company.id),
            "limit": 10
        }
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.post("/api/v1/sync/pull/", payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        changes = resp.data["changes"]
        # Voucher headers MUST be returned
        self.assertEqual(len(changes["vouchers"]["created"]), 5)
        # Line items and entries MUST be empty
        self.assertEqual(len(changes["voucher_items"]["created"]), 0)
        self.assertEqual(len(changes["ledger_entries"]["created"]), 0)

        # Ensure NO SQL queries hit VoucherItem or LedgerEntry
        queries = [q["sql"].lower() for q in ctx.captured_queries]
        for q in queries:
            self.assertNotIn("accounting_voucheritem", q)
            self.assertNotIn("accounting_ledgerentry", q)

    def test_sync_pull_includes_items_when_requested(self):
        """
        Sync pull includes line items only when include_details=True is explicitly requested.
        """
        payload = {
            "company_id": str(self.company.id),
            "limit": 10,
            "include_details": True
        }
        resp = self.client.post("/api/v1/sync/pull/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        changes = resp.data["changes"]
        self.assertEqual(len(changes["vouchers"]["created"]), 5)
        self.assertEqual(len(changes["voucher_items"]["created"]), 5)
        self.assertEqual(len(changes["ledger_entries"]["created"]), 10)

    def test_bank_transaction_list_excludes_voucher_attachment(self):
        """
        P0 Test: BankTransactionListAPIView must use narrowed projection (.only)
        and NEVER query matched_voucher.attachment_data.
        """
        # Create bank transaction matched to voucher with attachment
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            description="NEFT INWARD FROM ALPHA CORP",
            normalized_narration="NEFT INWARD FROM ALPHA CORP",
            credit_amount=Decimal("1180.00"),
            debit_amount=Decimal("0.00"),
            balance=Decimal("251180.00"),
            status="MATCHED_AUTO",
            matched_party=self.party_customer,
            matched_voucher=self.vouchers[0],
            match_confidence=98
        )

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                f"/api/v1/accounting/banking/transactions/?company_id={self.company.id}&status=MATCHED"
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["matched_voucher"]["id"], str(self.vouchers[0].id))
        self.assertEqual(results[0]["matched_voucher"]["voucher_number"], self.vouchers[0].voucher_number)

        # Crucial: verify SQL query did NOT include attachment_data
        for q in ctx.captured_queries:
            sql_lower = q["sql"].lower()
            self.assertNotIn("attachment_data", sql_lower)

    def test_voucher_detail_payment_allocation_excludes_attachment(self):
        """
        P0 Test: PaymentAllocation in VoucherDetailAPIView must not pull
        heavy attachment_data columns from joined vouchers.
        """
        # Create receipt voucher with attachment
        receipt = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            created_by=self.user,
            party_ledger=self.party_customer,
            voucher_type="RECEIPT",
            voucher_number="REC-LF-001",
            voucher_date=datetime.date(2026, 5, 12),
            status="POSTED",
            total_amount=Decimal("1180.00"),
            attachment_data="data:application/pdf;base64,JVBERi0xLjQKJcTl8uXr..." * 50,
            attachment_mime="application/pdf"
        )
        # Allocate against invoice
        PaymentAllocation.objects.create(
            company=self.company,
            payment_voucher=receipt,
            invoice_voucher=self.vouchers[0],
            allocated_amount=Decimal("1180.00")
        )

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/v1/accounting/vouchers/detail/{self.vouchers[0].id}/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        allocations = resp.data["data"]["allocations"]
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0]["voucher_number"], "REC-LF-001")

        # Crucial: verify SQL query did NOT fetch receipt attachment_data
        queries = [q["sql"].lower() for q in ctx.captured_queries]
        for q in queries:
            if "accounting_paymentallocation" in q:
                self.assertNotIn("attachment_data", q)

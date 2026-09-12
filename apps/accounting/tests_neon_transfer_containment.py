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
    FinancialYear, Voucher, VoucherItem, LedgerEntry, PaymentAllocation
)
from apps.inventory.models import Product
from apps.accounting.services.integrity_engine import AccountingIntegrityEngine

class NeonTransferContainmentTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Neon Containment Test Corp",
            gstin="27AABCT1234F1Z9",
            state_code="27"
        )
        self.user = User.objects.create_user(
            email="containment_test@vouch.com",
            password="testpassword123"
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
            name="Test Bank A/c",
            ledger_type="BANK",
            opening_balance_type="DEBIT",
            current_balance=Decimal("50000.00")
        )

        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.income_grp,
            name="Domestic Sales",
            ledger_type="SALES",
            opening_balance_type="CREDIT",
            current_balance=Decimal("0.00")
        )

        # Create 20 Customer Parties
        self.parties = []
        for i in range(20):
            p = Ledger.objects.create(
                company=self.company,
                group=self.debtor_grp,
                name=f"Customer Party {i+1}",
                ledger_type="CUSTOMER",
                opening_balance=Decimal("1000.00"),
                opening_balance_type="DEBIT",
                current_balance=Decimal("1000.00")
            )
            self.parties.append(p)

        # Create 20 Posted Sales Invoices
        self.invoices = []
        for i, party in enumerate(self.parties):
            v = Voucher.objects.create(
                company=self.company,
                financial_year=self.fy,
                created_by=self.user,
                party_ledger=party,
                voucher_type="SALES",
                voucher_number=f"INV-TEST-{i+1:03d}",
                voucher_date=datetime.date(2026, 5, 1),
                status="POSTED",
                total_amount=Decimal("5000.00"),
                attachment_data="data:application/pdf;base64,JVBERi0xLjQKJcTl8uXr..." if i % 2 == 0 else None,
                attachment_mime="application/pdf" if i % 2 == 0 else None
            )
            LedgerEntry.objects.create(
                voucher=v,
                company=self.company,
                ledger=party,
                debit_amount=Decimal("5000.00"),
                credit_amount=Decimal("0.00")
            )
            LedgerEntry.objects.create(
                voucher=v,
                company=self.company,
                ledger=self.sales_ledger,
                debit_amount=Decimal("0.00"),
                credit_amount=Decimal("5000.00")
            )
            self.invoices.append(v)

        # Create Payment Allocations
        for i in range(10):
            inv = self.invoices[i]
            pmt = Voucher.objects.create(
                company=self.company,
                financial_year=self.fy,
                created_by=self.user,
                party_ledger=inv.party_ledger,
                voucher_type="RECEIPT",
                voucher_number=f"REC-TEST-{i+1:03d}",
                voucher_date=datetime.date(2026, 5, 2),
                status="POSTED",
                total_amount=Decimal("5000.00")
            )
            PaymentAllocation.objects.create(
                company=self.company,
                payment_voucher=pmt,
                invoice_voucher=inv,
                allocated_amount=Decimal("5000.00")
            )

        # Update customer current balances so the ledger balances match the transactions (1000 op + 5000 inv = 6000)
        # Except the last party, which intentionally has an imbalance to verify finding generation
        for p in self.parties[:-1]:
            p.current_balance = Decimal("6000.00")
            p.save()

    def test_party_balances_grouped_query_efficiency(self):
        """
        Verifies check_party_balances runs in <= 5 queries regardless of party count.
        Previously executed 2 queries per party (40+ queries for 20 parties).
        """
        with CaptureQueriesContext(connection) as ctx:
            findings = AccountingIntegrityEngine.check_party_balances(self.company)

        # 1 query for parties, 1 for opening vouchers, 1 for grouped debit/credit sums,
        # 1 for prefetching findings, and 1 to persist the single imbalanced finding = 5 queries max
        self.assertLessEqual(len(ctx.captured_queries), 5)

    def test_payment_allocations_grouped_query_efficiency(self):
        """
        Verifies check_payment_allocations runs in <= 4 queries regardless of invoice count.
        Previously executed 1 aggregate query per invoice (20+ queries).
        """
        with CaptureQueriesContext(connection) as ctx:
            findings = AccountingIntegrityEngine.check_payment_allocations(self.company)

        # 1 query for allocations cross-check, 1 for allocation totals group by invoice, 1 for invoices
        self.assertLessEqual(len(ctx.captured_queries), 4)

    def test_accounting_integrity_engine_run_all_checks_bounded(self):
        """
        Verifies full AccountingIntegrityEngine.run_all_checks runs in <= 25 queries across all 11 dimensions.
        Previously executed 270+ individual N+1 queries.
        """
        with CaptureQueriesContext(connection) as ctx:
            report = AccountingIntegrityEngine.run_all_checks(self.company)

        self.assertIn("health_score", report)
        self.assertIn("checks_summary", report)
        # Bounded query count (21 queries for all 11 accounting checks combined, vs 270+ before)
        self.assertLessEqual(len(ctx.captured_queries), 25)

    def test_sync_pull_defers_attachment_data_and_omits_duplicate_master_data(self):
        """
        Verifies SyncPullAPIView:
        1. Does not select attachment_data in SQL.
        2. Omits ledgers and products on subsequent cursor batches.
        """
        # Batch 1: Initial pull without cursor
        payload_initial = {
            "company_id": str(self.company.id),
            "limit": 5
        }
        with CaptureQueriesContext(connection) as ctx_initial:
            resp_initial = self.client.post("/api/v1/sync/pull/", payload_initial, format="json")

        self.assertEqual(resp_initial.status_code, status.HTTP_200_OK)
        data_initial = resp_initial.data
        self.assertTrue(len(data_initial["changes"]["ledgers"]["created"]) > 0)
        self.assertTrue(data_initial["has_more"])
        next_cursor = data_initial["next_cursor"]

        # Ensure attachment_data was NOT fetched
        voucher_queries = [q["sql"] for q in ctx_initial.captured_queries if "accounting_voucher" in q["sql"]]
        for q in voucher_queries:
            self.assertNotIn("attachment_data", q.lower())

        # Batch 2: Subsequent cursor pull
        payload_paged = {
            "company_id": str(self.company.id),
            "cursor": next_cursor,
            "limit": 5
        }
        resp_paged = self.client.post("/api/v1/sync/pull/", payload_paged, format="json")
        self.assertEqual(resp_paged.status_code, status.HTTP_200_OK)
        data_paged = resp_paged.data

        # Master data MUST be empty on batch 2 to prevent redundant transfer
        self.assertEqual(len(data_paged["changes"]["ledgers"]["created"]), 0)
        self.assertEqual(len(data_paged["changes"]["products"]["created"]), 0)
        # But vouchers continue to be returned
        self.assertTrue(len(data_paged["changes"]["vouchers"]["created"]) > 0)

    def test_voucher_detail_attachment_deferral(self):
        """
        Verifies VoucherDetailAPIView defers attachment_data unless include_attachment=true.
        """
        voucher_with_att = self.invoices[0]  # has attachment_data
        url = f"/api/v1/accounting/vouchers/detail/{voucher_with_att.id}/"

        # Default GET: attachment_data should be None, has_attachment should be True
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["has_attachment"])
        self.assertIsNone(resp.data["data"]["attachment_data"])

        # GET with include_attachment=true: attachment_data should be returned
        resp_with_att = self.client.get(f"{url}?include_attachment=true")
        self.assertEqual(resp_with_att.status_code, status.HTTP_200_OK)
        self.assertTrue(resp_with_att.data["data"]["has_attachment"])
        self.assertIsNotNone(resp_with_att.data["data"]["attachment_data"])

    def test_dedicated_voucher_attachment_api(self):
        """
        Verifies GET /api/v1/accounting/vouchers/<id>/attachment/ returns attachment on demand.
        """
        voucher_with_att = self.invoices[0]
        url = f"/api/v1/accounting/vouchers/{voucher_with_att.id}/attachment/"

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["has_attachment"])
        self.assertIn("JVBERi0xLjQKJcTl8uXr", resp.data["attachment_data"])
        self.assertEqual(resp.data["attachment_mime"], "application/pdf")

    def test_universal_voucher_list_does_not_inspect_attachment_data(self):
        """
        Verifies UniversalVoucherAPIView uses attachment_mime instead of evaluating attachment_data.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f"/api/v1/accounting/vouchers/{self.company.id}/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for q in ctx.captured_queries:
            sql_lower = q["sql"].lower()
            if "accounting_voucher" in sql_lower:
                self.assertNotIn("attachment_data", sql_lower)

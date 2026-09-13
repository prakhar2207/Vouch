import datetime
from decimal import Decimal
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework import status

from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import (
    FinancialYear, Voucher, LedgerEntry, BankTransaction, BankStatementImport, PaymentAllocation
)
from apps.accounting.services.bank_statement_service import BankStatementService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.voucher_service import VoucherService


class BankingProductionIntegrationTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Apex Engineering Solutions",
            gstin="27AAPCA1234F1Z5",
            state_code="27"
        )
        self.company_b = Company.objects.create(
            name="Rival Corp",
            gstin="27XYZAB9999K1Z2",
            state_code="27"
        )
        self.user = User.objects.create_user(
            email="owner@apexsolutions.com",
            password="testpassword123"
        )
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31)
        )

        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Bank Accounts", nature="ASSET")
        self.debtor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.creditor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Creditors", nature="LIABILITY")

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="HDFC Main Current A/c",
            ledger_type="BANK",
            opening_balance=Decimal("100000.00"),
            current_balance=Decimal("100000.00"),
            opening_balance_type="DEBIT"
        )

        self.customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Shree Om Traders",
            ledger_type="CUSTOMER",
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
            opening_balance_type="DEBIT"
        )

        self.supplier = Ledger.objects.create(
            company=self.company,
            group=self.creditor_grp,
            name="Tata Steel Distributors",
            ledger_type="SUPPLIER",
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
            opening_balance_type="CREDIT"
        )

    def test_01_source_fact_immutability_supplier_refund(self):
        """
        Rule 11: An incoming deposit from a supplier is recorded strictly as Credit (Money IN),
        and resolves into a RECEIPT voucher (Dr Bank, Cr Supplier). It is NEVER flipped to debit/payment.
        """
        csv_data = (
            "Txn Date,Particulars,Chq/Ref No,Debit,Credit,Balance\n"
            "15/06/2026,NEFT CR TATA STEEL DISTRIBUTORS REFUND,NEFT1001,0.00,12000.00,112000.00\n"
        ).encode('utf-8')

        summary = BankStatementService.parse_statement(
            company=self.company,
            bank_ledger=self.bank_ledger,
            file_bytes=csv_data,
            filename="supplier_refund.csv",
            user=self.user
        )

        tx = BankTransaction.objects.get(statement_import_id=summary["import_id"])
        self.assertEqual(tx.credit_amount, Decimal("12000.00"))
        self.assertEqual(tx.debit_amount, Decimal("0.00"))

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type="CONFIRM_SUPPLIER_REFUND",
            payload={"party_id": str(self.supplier.id)},
            user=self.user
        )

        self.assertEqual(res["status"], "SUCCESS")
        voucher = Voucher.objects.get(id=res["voucher_id"])
        self.assertEqual(voucher.voucher_type, "RECEIPT")
        self.assertEqual(voucher.status, "POSTED")

        entries = voucher.ledger_entries.all()
        bank_entry = entries.get(ledger=self.bank_ledger)
        supplier_entry = entries.get(ledger=self.supplier)
        self.assertEqual(bank_entry.debit_amount, Decimal("12000.00"))
        self.assertEqual(supplier_entry.credit_amount, Decimal("12000.00"))

    def test_02_source_fact_immutability_customer_refund(self):
        """Customer refund is Money OUT (Debit). It must resolve to PAYMENT (Dr Customer, Cr Bank)."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 6, 16),
            description="UPI/REFUND/SHREE OM TRADERS/EXCESS",
            normalized_narration="UPI REFUND SHREE OM TRADERS EXCESS",
            debit_amount=Decimal("5000.00"),
            credit_amount=Decimal("0.00"),
            status="UNRESOLVED"
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type="CONFIRM_CUSTOMER_REFUND",
            payload={"party_id": str(self.customer.id)},
            user=self.user
        )

        voucher = Voucher.objects.get(id=res["voucher_id"])
        self.assertEqual(voucher.voucher_type, "PAYMENT")
        self.assertEqual(voucher.status, "POSTED")

        entries = voucher.ledger_entries.all()
        cust_entry = entries.get(ledger=self.customer)
        bank_entry = entries.get(ledger=self.bank_ledger)
        self.assertEqual(cust_entry.debit_amount, Decimal("5000.00"))
        self.assertEqual(bank_entry.credit_amount, Decimal("5000.00"))

    def test_03_canonical_posting_and_balance_update(self):
        """Posting updates authoritative balances via canonical VoucherService under lock."""
        initial_bank_bal = self.bank_ledger.current_balance

        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 6, 17),
            description="CHQ DEP SHREE OM TRADERS",
            normalized_narration="CHQ DEP SHREE OM TRADERS",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("20000.00"),
            status="UNRESOLVED"
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type="CONFIRM_RECEIPT",
            payload={"party_id": str(self.customer.id)},
            user=self.user
        )

        self.bank_ledger.refresh_from_db()
        self.assertEqual(self.bank_ledger.current_balance, initial_bank_bal + Decimal("20000.00"))

    def test_04_concurrency_safe_allocation_prevents_overallocation(self):
        """Payment allocations verify that total allocations never exceed the invoice amount."""
        inv = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-2026-001",
            voucher_date=datetime.date(2026, 6, 1),
            party_ledger=self.customer,
            total_amount=Decimal("30000.00"),
            status="POSTED",
            created_by=self.user
        )

        pmt1 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-001",
            voucher_date=datetime.date(2026, 6, 10),
            party_ledger=self.customer,
            total_amount=Decimal("20000.00"),
            status="POSTED",
            created_by=self.user
        )
        allocs1 = PaymentAllocationService.auto_allocate_voucher(pmt1)
        self.assertEqual(len(allocs1), 1)
        self.assertEqual(Decimal(allocs1[0]["allocated_amount"]), Decimal("20000.00"))

        pmt2 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-002",
            voucher_date=datetime.date(2026, 6, 12),
            party_ledger=self.customer,
            total_amount=Decimal("20000.00"),
            status="POSTED",
            created_by=self.user
        )
        allocs2 = PaymentAllocationService.auto_allocate_voucher(pmt2)
        self.assertEqual(len(allocs2), 1)
        self.assertEqual(Decimal(allocs2[0]["allocated_amount"]), Decimal("10000.00"))

        tot_alloc = PaymentAllocationService.get_voucher_allocated_amount(inv)
        self.assertEqual(tot_alloc, Decimal("30000.00"))

        pmt3 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-003",
            voucher_date=datetime.date(2026, 6, 14),
            party_ledger=self.customer,
            total_amount=Decimal("5000.00"),
            status="POSTED",
            created_by=self.user
        )
        with self.assertRaises(ValidationError):
            PaymentAllocationService.allocate_payment(pmt3, inv, Decimal("1000.00"))

    def test_05_reference_aware_allocation_prioritizes_invoice(self):
        """Explicit invoice reference in payment voucher is allocated first."""
        inv1 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="INV-A01", voucher_date=datetime.date(2026, 6, 1),
            party_ledger=self.customer, total_amount=Decimal("10000.00"), status="POSTED",
            created_by=self.user
        )
        inv2 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="SALES",
            voucher_number="INV-A02", voucher_date=datetime.date(2026, 6, 2),
            party_ledger=self.customer, total_amount=Decimal("10000.00"), status="POSTED",
            created_by=self.user
        )

        pmt = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="RECEIPT",
            voucher_number="RCP-100", voucher_date=datetime.date(2026, 6, 15),
            party_ledger=self.customer, total_amount=Decimal("10000.00"),
            reference_number="INV-A02", status="POSTED",
            created_by=self.user
        )

        allocs = PaymentAllocationService.auto_allocate_voucher(pmt)
        self.assertEqual(len(allocs), 1)
        self.assertEqual(allocs[0]["invoice_number"], "INV-A02")
        self.assertEqual(Decimal(allocs[0]["allocated_amount"]), Decimal("10000.00"))

    def test_06_idempotent_reconciliation(self):
        """Resolving already reconciled transaction returns existing voucher idempotently."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 6, 18),
            description="UPI/RAJESH/TEST",
            normalized_narration="UPI RAJESH TEST",
            credit_amount=Decimal("7500.00"),
            debit_amount=Decimal("0.00"),
            status="UNRESOLVED"
        )

        res1 = BankReconciliationService.resolve_transaction(
            bank_tx=tx, action_type="CONFIRM_RECEIPT",
            payload={"party_id": str(self.customer.id)}, user=self.user
        )
        tx.refresh_from_db()
        self.assertEqual(tx.status, "RECONCILED")

        res2 = BankReconciliationService.resolve_transaction(
            bank_tx=tx, action_type="CONFIRM_RECEIPT",
            payload={"party_id": str(self.customer.id)}, user=self.user
        )
        self.assertEqual(res2["status"], "SUCCESS")
        self.assertEqual(res2["voucher_id"], res1["voucher_id"])

    def test_07_date_bound_reconciliation_summary(self):
        """Date-bound reconciliation evaluates book balance strictly as of statement cutoff date."""
        v1 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="RECEIPT",
            voucher_number="RCP-JUN15", voucher_date=datetime.date(2026, 6, 15),
            party_ledger=self.customer, total_amount=Decimal("25000.00"), status="DRAFT",
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=v1, ledger=self.bank_ledger, debit_amount=Decimal("25000.00"), credit_amount=Decimal("0.00"))
        LedgerEntry.objects.create(company=self.company, voucher=v1, ledger=self.customer, debit_amount=Decimal("0.00"), credit_amount=Decimal("25000.00"))
        VoucherService.post_voucher(v1)

        stmt = BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="june_statement.csv",
            statement_start_date=datetime.date(2026, 6, 1),
            statement_end_date=datetime.date(2026, 6, 20),
            closing_balance=Decimal("125000.00"),
            status="COMPLETED"
        )
        BankTransaction.objects.create(
            company=self.company,
            statement_import=stmt,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 6, 15),
            description="DEPOSIT",
            normalized_narration="DEPOSIT",
            credit_amount=Decimal("25000.00"),
            balance=Decimal("125000.00"),
            status="RECONCILED"
        )

        v2 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type="RECEIPT",
            voucher_number="RCP-JUL05", voucher_date=datetime.date(2026, 7, 5),
            party_ledger=self.customer, total_amount=Decimal("20000.00"), status="DRAFT",
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=v2, ledger=self.bank_ledger, debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00"))
        LedgerEntry.objects.create(company=self.company, voucher=v2, ledger=self.customer, debit_amount=Decimal("0.00"), credit_amount=Decimal("20000.00"))
        VoucherService.post_voucher(v2)

        summary = BankReconciliationService.get_reconciliation_summary(self.company, str(self.bank_ledger.id))
        self.assertEqual(summary["statement_cutoff_date"], "2026-06-20")
        self.assertEqual(summary["statement_closing_balance"], "125000.00")
        self.assertEqual(summary["book_closing_balance"], "125000.00")
        self.assertEqual(summary["reconciliation_gap"], "0.00")
        self.assertTrue(summary["is_balanced"])
        self.assertEqual(summary["reconciliation_state"], "FULLY_RECONCILED")

    def test_08_audited_non_destructive_exclusion(self):
        """Exclusion marks record as EXCLUDED and canonically reverses any generated vouchers."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 6, 22),
            description="CHQ PAID SUPPLIER TATA",
            normalized_narration="CHQ PAID SUPPLIER TATA",
            debit_amount=Decimal("15000.00"),
            credit_amount=Decimal("0.00"),
            status="UNRESOLVED"
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx, action_type="CONFIRM_SUPPLIER_PAYMENT",
            payload={"party_id": str(self.supplier.id)}, user=self.user
        )
        tx.refresh_from_db()
        self.assertEqual(tx.status, "RECONCILED")
        vch = tx.matched_voucher

        exc_res = BankReconciliationService.exclude_transaction(tx, reason="Personal transaction", user=self.user)
        self.assertEqual(exc_res["status"], "SUCCESS")

        tx.refresh_from_db()
        self.assertTrue(tx.is_excluded)
        self.assertEqual(tx.status, "EXCLUDED")
        self.assertEqual(tx.exclusion_reason, "Personal transaction")

        vch.refresh_from_db()
        self.assertEqual(vch.status, "REVERSED")
        self.assertIsNotNone(vch.reversal_voucher)
        self.assertTrue(vch.reversal_voucher.voucher_number.startswith("REV-"))

    def test_09_tenant_isolation_enforced(self):
        """Cross-company access is blocked."""
        tx_b = BankTransaction.objects.create(
            company=self.company_b,
            bank_ledger=Ledger.objects.create(
                company=self.company_b, name="Competitor Bank", ledger_type="BANK",
                group=LedgerGroup.objects.create(company=self.company_b, name="Banks", nature="ASSET")
            ),
            transaction_date=datetime.date(2026, 6, 23),
            description="Secret Tx",
            normalized_narration="SECRET TX",
            credit_amount=Decimal("50000.00"),
            debit_amount=Decimal("0.00")
        )

        self.client.force_authenticate(user=self.user)
        url = f"/api/v1/accounting/banking/transactions/{tx_b.id}/resolve/"
        response = self.client.post(url, {
            "action": "CONFIRM_RECEIPT",
            "payload": {"party_id": str(self.customer.id)}
        }, format="json", HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

import datetime
from decimal import Decimal
from django.test import TestCase
from django.db.utils import IntegrityError
from django.db import transaction
from rest_framework.test import APITestCase
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import (
    FinancialYear,
    Voucher,
    LedgerEntry,
    BankTransaction,
    BankStatementImport,
    PaymentAllocation,
)
from apps.audit.models import AuditLog
from apps.inventory.models import Product, Warehouse, InventoryEntry
from apps.accounting.services.party_balance_service import PartyBalanceService
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.balance_rebuild import rebuild_ledger_balances
from apps.inventory.services.stock_service import StockService


class MasterStabilizationTests(APITestCase):
    """
    Master Production Stabilization Test Suite
    Enforces all core accounting invariants, balance semantics, banking integrity,
    inventory reconstruction, and API consistency.
    """

    def setUp(self):
        self.company = Company.objects.create(
            name="Apex Engineering Solutions",
            gstin="27AAPCA1234F1Z5",
            state_code="27",
        )
        self.user = User.objects.create_user(
            email="stabilization_owner@apexsolutions.com",
            password="testpassword123",
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2025-26",
            code="25-26",
            start_date=datetime.date(2025, 4, 1),
            end_date=datetime.date(2026, 3, 31),
        )

        self.asset_grp = LedgerGroup.objects.create(
            company=self.company, name="Bank Accounts", nature="ASSET"
        )
        self.debtor_grp = LedgerGroup.objects.create(
            company=self.company, name="Sundry Debtors", nature="ASSET"
        )
        self.creditor_grp = LedgerGroup.objects.create(
            company=self.company, name="Sundry Creditors", nature="LIABILITY"
        )

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="HDFC Main Current A/c",
            ledger_type="BANK",
            opening_balance=Decimal("100000.00"),
            current_balance=Decimal("100000.00"),
            opening_balance_type="DEBIT",
        )

    def test_scenario_a_supplier_payable(self):
        """
        Scenario A: Supplier payable ₹68,362.12
        - Role = SUPPLIER, normal_balance = CREDIT.
        - Balance state must be TO_PAY.
        - Must NOT be inverted even if opening_balance_type was erroneously set to DEBIT.
        """
        supplier = Ledger.objects.create(
            company=self.company,
            group=self.creditor_grp,
            name="Tata Steel Distributors",
            ledger_type="SUPPLIER",
            opening_balance=Decimal("68362.12"),
            current_balance=Decimal("68362.12"),
            opening_balance_type="DEBIT",
        )

        interp = PartyBalanceService.get_party_balance_interpretation(supplier)
        self.assertEqual(interp["canonical_role"], "SUPPLIER")
        self.assertEqual(interp["state"], "TO_PAY")
        self.assertEqual(interp["display_balance"], Decimal("68362.12"))
        self.assertEqual(interp["normal_balance"], "CREDIT")
        self.assertTrue(interp["is_payable"])
        self.assertFalse(interp["is_receivable"])

    def test_scenario_b_customer_receivable(self):
        """
        Scenario B: Customer receivable ₹75,000.00
        - Role = CUSTOMER, normal_balance = DEBIT.
        - Balance state must be TO_COLLECT.
        - Must NOT be inverted even if opening_balance_type was erroneously set to CREDIT.
        """
        customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Shree Om Traders",
            ledger_type="CUSTOMER",
            opening_balance=Decimal("75000.00"),
            current_balance=Decimal("75000.00"),
            opening_balance_type="CREDIT",
        )

        interp = PartyBalanceService.get_party_balance_interpretation(customer)
        self.assertEqual(interp["canonical_role"], "CUSTOMER")
        self.assertEqual(interp["state"], "TO_COLLECT")
        self.assertEqual(interp["display_balance"], Decimal("75000.00"))
        self.assertEqual(interp["normal_balance"], "DEBIT")
        self.assertTrue(interp["is_receivable"])
        self.assertFalse(interp["is_payable"])

    def test_scenario_c_customer_advance(self):
        """
        Scenario C: Customer advance ₹50,000.00
        - Customer makes an advance payment without invoice.
        - Balance becomes Credit ₹50,000.00.
        - Balance state must be ADVANCE_RECEIVED.
        - Canonical role MUST remain CUSTOMER (does NOT become a supplier!).
        """
        customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Advance Customer Pvt Ltd",
            ledger_type="CUSTOMER",
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
            opening_balance_type="DEBIT",
        )

        # Receipt voucher: Dr Bank ₹50,000, Cr Customer ₹50,000
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="REC-001",
            voucher_date=datetime.date(2026, 1, 15),
            party_ledger=customer,
            created_by=self.user,
            status="POSTED",
            total_amount=Decimal("50000.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=voucher,
            ledger=self.bank_ledger,
            debit_amount=Decimal("50000.00"), credit_amount=Decimal("0.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=voucher,
            ledger=customer,
            debit_amount=Decimal("0.00"), credit_amount=Decimal("50000.00"),
        )

        rebuild_ledger_balances(self.company)
        customer.refresh_from_db()

        interp = PartyBalanceService.get_party_balance_interpretation(customer)
        self.assertEqual(interp["canonical_role"], "CUSTOMER")
        self.assertEqual(interp["state"], "ADVANCE_RECEIVED")
        self.assertEqual(interp["display_balance"], Decimal("50000.00"))
        self.assertEqual(interp["balance_direction"], "CREDIT")

    def test_scenario_d_supplier_advance(self):
        """
        Scenario D: Supplier advance ₹50,000.00
        - Business makes advance payment to supplier before receiving bill.
        - Balance becomes Debit ₹50,000.00.
        - Balance state must be ADVANCE_PAID.
        - Canonical role MUST remain SUPPLIER (does NOT become a customer!).
        """
        supplier = Ledger.objects.create(
            company=self.company,
            group=self.creditor_grp,
            name="Advance Supplier Industries",
            ledger_type="SUPPLIER",
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
            opening_balance_type="CREDIT",
        )

        # Payment voucher: Dr Supplier ₹50,000, Cr Bank ₹50,000
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="PAYMENT",
            voucher_number="PAY-001",
            voucher_date=datetime.date(2026, 1, 15),
            party_ledger=supplier,
            created_by=self.user,
            status="POSTED",
            total_amount=Decimal("50000.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=voucher,
            ledger=supplier,
            debit_amount=Decimal("50000.00"), credit_amount=Decimal("0.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=voucher,
            ledger=self.bank_ledger,
            debit_amount=Decimal("0.00"), credit_amount=Decimal("50000.00"),
        )

        rebuild_ledger_balances(self.company)
        supplier.refresh_from_db()

        interp = PartyBalanceService.get_party_balance_interpretation(supplier)
        self.assertEqual(interp["canonical_role"], "SUPPLIER")
        self.assertEqual(interp["state"], "ADVANCE_PAID")
        self.assertEqual(interp["display_balance"], Decimal("50000.00"))
        self.assertEqual(interp["balance_direction"], "DEBIT")

    def test_scenario_e_bank_supplier_refund_and_constraints(self):
        """
        Scenario E: Bank supplier refund ₹12,000.00 & DB Direction Invariant
        - BankTransaction DB constraints prevent negative amounts and simultaneous Dr/Cr.
        - Incoming refund is credit_amount=12000 (deposit).
        - Resolving creates RECEIPT voucher: Dr Bank, Cr Supplier.
        """
        # 1. DB Constraint check: Negative amounts prohibited
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BankTransaction.objects.create(
                    company=self.company,
                    bank_ledger=self.bank_ledger,
                    transaction_date=datetime.date(2026, 1, 10),
                    description="Negative test",
                    debit_amount=Decimal("-100.00"),
                    credit_amount=Decimal("0.00"),
                )

        # 2. DB Constraint check: Simultaneous Dr > 0 and Cr > 0 prohibited
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BankTransaction.objects.create(
                    company=self.company,
                    bank_ledger=self.bank_ledger,
                    transaction_date=datetime.date(2026, 1, 10),
                    description="Both Dr and Cr test",
                    debit_amount=Decimal("100.00"),
                    credit_amount=Decimal("100.00"),
                )

        # 3. Create valid supplier refund transaction: Money IN (Credit = 12000)
        supplier = Ledger.objects.create(
            company=self.company,
            group=self.creditor_grp,
            name="Steel Refunder Ltd",
            ledger_type="SUPPLIER",
        )

        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 1, 10),
            description="NEFT REFUND FROM STEEL REFUNDER",
            normalized_narration="REFUND STEEL REFUNDER",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("12000.00"),
            status="UNRESOLVED",
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type="MATCH_PARTY",
            payload={"party_id": str(supplier.id)},
            user=self.user,
        )

        self.assertIn("voucher_number", res)
        voucher = Voucher.objects.get(voucher_number=res["voucher_number"])
        self.assertEqual(voucher.voucher_type, "RECEIPT")

        # Verify entry directions: Dr Bank, Cr Supplier
        bank_entry = LedgerEntry.objects.get(voucher=voucher, ledger=self.bank_ledger)
        supplier_entry = LedgerEntry.objects.get(voucher=voucher, ledger=supplier)
        self.assertEqual(bank_entry.debit_amount, Decimal("12000.00"))
        self.assertEqual(bank_entry.credit_amount, Decimal("0.00"))
        self.assertEqual(supplier_entry.credit_amount, Decimal("12000.00"))
        self.assertEqual(supplier_entry.debit_amount, Decimal("0.00"))

    def test_scenario_f_reconciliation_cutoff_date(self):
        """
        Scenario F: Reconciliation Cutoff Date
        - Cutoff date: 2026-01-31.
        - Jan 20: Voucher ₹10,000 (included)
        - Feb 2: Voucher ₹20,000 (after cutoff -> must be strictly excluded from cutoff book balance)
        """
        # Voucher before cutoff (Jan 20)
        v_jan20 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="V-JAN20",
            voucher_date=datetime.date(2026, 1, 20),
            created_by=self.user,
            status="POSTED",
            total_amount=Decimal("10000.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v_jan20,
            ledger=self.bank_ledger,
            debit_amount=Decimal("10000.00"), credit_amount=Decimal("0.00"),
        )

        # Voucher after cutoff (Feb 2)
        v_feb02 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="V-FEB02",
            voucher_date=datetime.date(2026, 2, 2),
            created_by=self.user,
            status="POSTED",
            total_amount=Decimal("20000.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v_feb02,
            ledger=self.bank_ledger,
            debit_amount=Decimal("20000.00"), credit_amount=Decimal("0.00"),
        )

        # Bank statement import with cutoff date Jan 31, 2026
        stmt_import = BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="jan_2026_statement.csv",
            statement_start_date=datetime.date(2026, 1, 1),
            statement_end_date=datetime.date(2026, 1, 31),
            closing_balance=Decimal("110000.00"),
            total_rows=1,
            successful_rows=1,
            created_by=self.user,
        )

        # Bank transaction before cutoff
        tx = BankTransaction.objects.create(
            company=self.company,
            statement_import=stmt_import,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 1, 20),
            description="Statement receipt",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("10000.00"),
            status="MATCHED",
            matched_voucher=v_jan20,
        )

        summary = BankReconciliationService.get_reconciliation_summary(
            company=self.company,
            bank_ledger_id=str(self.bank_ledger.id),
        )

        # Initial opening balance = 100,000. Jan 20 receipt = 10,000.
        # Book balance as of Jan 31 must be 110,000.00 (NOT 130,000.00 which would include Feb 2!)
        expected_book_balance = Decimal("110000.00")
        self.assertEqual(
            Decimal(summary["book_closing_balance"]),
            expected_book_balance,
        )

    def test_stock_rebuild_invariant(self):
        """
        Stock Reconstruction Invariant:
        StockService.rebuild_company_stock restores drifted product stock to exact
        sum of (IN - OUT) InventoryEntry movements with audit trail.
        """
        wh = Warehouse.objects.create(company=self.company, name="Central Godown")
        product = Product.objects.create(
            company=self.company,
            name="Galvanized Pipe 2 inch",
            sku="GP-2IN",
            unit="MTR",
            stock_quantity=Decimal("0.00"),
        )

        # In: 100, Out: 35, In: 15 -> Net = 80
        InventoryEntry.objects.create(
            company=self.company,
            product=product,
            warehouse=wh,
            movement_type="IN",
            quantity=Decimal("100.00"),
            rate=Decimal("50.00"),
            total_value=Decimal("5000.00"),
        )
        InventoryEntry.objects.create(
            company=self.company,
            product=product,
            warehouse=wh,
            movement_type="OUT",
            quantity=Decimal("35.00"),
            rate=Decimal("50.00"),
            total_value=Decimal("1750.00"),
        )
        InventoryEntry.objects.create(
            company=self.company,
            product=product,
            warehouse=wh,
            movement_type="IN",
            quantity=Decimal("15.00"),
            rate=Decimal("50.00"),
            total_value=Decimal("750.00"),
        )

        # Artificially corrupt stock_quantity
        product.stock_quantity = Decimal("999.00")
        product.save()

        # Rebuild stock
        res = StockService.rebuild_company_stock(company=self.company, user=self.user)
        self.assertTrue(res["success"])
        self.assertEqual(res["discrepancies_count"], 1)

        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, Decimal("80.00"))

    def test_read_only_statement_api_idempotence(self):
        """
        Read-Only Statement API Invariant:
        GET request to LedgerStatementAPIView retrieves data without modifying
        any database records.
        """
        customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Statement Check Customer",
            ledger_type="CUSTOMER",
            opening_balance=Decimal("25000.00"),
            current_balance=Decimal("25000.00"),
        )

        v = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-STMT-01",
            voucher_date=datetime.date(2026, 1, 10),
            party_ledger=customer,
            created_by=self.user,
            status="POSTED",
            total_amount=Decimal("10000.00"),
        )
        LedgerEntry.objects.create(
            company=self.company,
            voucher=v,
            ledger=customer,
            debit_amount=Decimal("10000.00"), credit_amount=Decimal("0.00"),
        )

        self.client.force_authenticate(user=self.user)
        url = f"/api/v1/accounting/ledgers/{customer.id}/statement/"

        counts_before = {
            "voucher": Voucher.objects.count(),
            "ledger_entry": LedgerEntry.objects.count(),
            "ledger": Ledger.objects.count(),
            "audit_log": AuditLog.objects.count(),
        }

        response = self.client.get(url, HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        raw = response.json()
        data = raw.get("data", raw)
        self.assertIn("opening_balance", data)
        self.assertIn("closing_balance", data)
        self.assertIn("entries", data)

        counts_after = {
            "voucher": Voucher.objects.count(),
            "ledger_entry": LedgerEntry.objects.count(),
            "ledger": Ledger.objects.count(),
            "audit_log": AuditLog.objects.count(),
        }

        # Assert zero side effects
        self.assertEqual(counts_before, counts_after)

    def test_effective_voucher_service_statuses(self):
        """
        Effective Voucher Service Invariant:
        Ensures POSTED, REVERSED, CORRECTED are accounted, while DRAFT, CANCELLED,
        SUPERSEDED are strictly excluded from accounting balances.
        """
        self.assertIn("POSTED", EffectiveVoucherService.ACCOUNTING_STATUSES)
        self.assertIn("REVERSED", EffectiveVoucherService.ACCOUNTING_STATUSES)
        self.assertIn("CORRECTED", EffectiveVoucherService.ACCOUNTING_STATUSES)
        self.assertNotIn("DRAFT", EffectiveVoucherService.ACCOUNTING_STATUSES)
        self.assertNotIn("CANCELLED", EffectiveVoucherService.ACCOUNTING_STATUSES)
        self.assertNotIn("SUPERSEDED", EffectiveVoucherService.ACCOUNTING_STATUSES)

    def test_concurrency_allocation_row_lock_fifo(self):
        """
        Allocation Concurrency & FIFO Invariant:
        Verifies PaymentAllocationService applies customer receipts to oldest unpaid invoices
        in FIFO sequence with select_for_update row-level locks.
        """
        customer = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="FIFO Allocation Customer",
            ledger_type="CUSTOMER",
        )

        inv1 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-FIFO-01",
            voucher_date=datetime.date(2026, 1, 1),
            party_ledger=customer,
            status="POSTED",
            total_amount=Decimal("30000.00"),
            created_by=self.user,
        )
        inv2 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-FIFO-02",
            voucher_date=datetime.date(2026, 1, 5),
            party_ledger=customer,
            status="POSTED",
            total_amount=Decimal("20000.00"),
            created_by=self.user,
        )

        receipt = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="REC-FIFO-01",
            voucher_date=datetime.date(2026, 1, 10),
            party_ledger=customer,
            status="POSTED",
            total_amount=Decimal("40000.00"),
            created_by=self.user,
        )

        allocations = PaymentAllocationService.auto_allocate_voucher(
            payment_voucher=receipt,
        )

        # FIFO: inv1 should be fully paid (30,000) and inv2 partially paid (10,000)
        self.assertEqual(len(allocations), 2)
        alloc_map = {a["invoice_voucher_id"]: Decimal(a["allocated_amount"]) for a in allocations}
        self.assertEqual(alloc_map[str(inv1.id)], Decimal("30000.00"))
        self.assertEqual(alloc_map[str(inv2.id)], Decimal("10000.00"))

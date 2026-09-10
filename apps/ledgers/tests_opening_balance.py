import datetime
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.companies.models import Company, CompanySettings
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear, PaymentAllocation
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.report_service import ReportService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.balance_rebuild import BalanceRebuildService
from apps.accounting.services.year_end_service import YearEndClosingService
from apps.ledgers.services.opening_balance_service import OpeningBalanceService
from apps.ledgers.services.party_merge_service import PartyMergeService
from apps.audit.models import AuditLog


class OpeningBalanceAndPartyAccountingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="owner@test.com", password="password123")
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name="Apex Supermart Pvt Ltd",
            gstin="27ABCDE1234F1Z5",
            state_code="27"
        )
        self.company.users.create(user=self.user, role="OWNER")
        self.settings, _ = CompanySettings.objects.get_or_create(company=self.company)

        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31)
        )

        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.liab_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Creditors", nature="LIABILITY")
        self.equity_grp = LedgerGroup.objects.create(company=self.company, name="Equity", nature="EQUITY")
        self.income_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")
        self.cash_grp = LedgerGroup.objects.create(company=self.company, name="Cash-in-hand", nature="ASSET")

        self.cash_ledger = Ledger.objects.create(
            company=self.company,
            group=self.cash_grp,
            name="Cash",
            ledger_type="CASH"
        )
        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.income_grp,
            name="Sales Account",
            ledger_type="SALES"
        )

    def test_01_customer_onboarding_opening_balance_and_trial_balance(self):
        """Scenario 1: Customer onboarding with opening balance ₹50,000 creates double entry and balances Trial Balance."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="ABC Traders",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('50000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )

        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('50000.00'),
            balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1),
            user=self.user
        )

        customer.refresh_from_db()
        self.assertEqual(customer.current_balance, Decimal('50000.00'))

        # Verify Opening Balance Adjustment account
        adj_ledger = OpeningBalanceService.get_or_create_opening_adjustment_ledger(self.company)
        adj_ledger.refresh_from_db()
        self.assertEqual(adj_ledger.current_balance, Decimal('50000.00'))

        # Verify Trial Balance equilibrium
        tb = ReportService.generate_trial_balance(self.company)
        self.assertTrue(tb["totals"]["is_balanced"])
        self.assertEqual(tb["totals"]["total_debit"], Decimal('50000.00'))
        self.assertEqual(tb["totals"]["total_credit"], Decimal('50000.00'))

    def test_02_supplier_onboarding_opening_balance(self):
        """Scenario 2: Supplier onboarding with opening balance ₹30,000 payable."""
        supplier = Ledger.objects.create(
            company=self.company,
            group=self.liab_grp,
            name="XYZ Suppliers",
            ledger_type="SUPPLIER",
            opening_balance=Decimal('30000.00'),
            opening_balance_type="CREDIT",
            opening_date=datetime.date(2026, 4, 1)
        )

        OpeningBalanceService.record_opening_balance(
            ledger=supplier,
            amount=Decimal('30000.00'),
            balance_type="CREDIT",
            opening_date=datetime.date(2026, 4, 1),
            user=self.user
        )

        supplier.refresh_from_db()
        self.assertEqual(supplier.current_balance, Decimal('30000.00'))

        tb = ReportService.generate_trial_balance(self.company)
        self.assertTrue(tb["totals"]["is_balanced"])
        self.assertEqual(tb["totals"]["total_debit"], Decimal('30000.00'))
        self.assertEqual(tb["totals"]["total_credit"], Decimal('30000.00'))

    def test_03_pending_invoices_onboarding_and_aging(self):
        """Scenario 3: Opening balance with pending invoices and aging buckets."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Kisan Store",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('50000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )

        pending = [
            {
                "invoice_number": "INV-OLD-01",
                "voucher_date": "2026-03-01",
                "due_date": "2026-03-20",  # Overdue
                "amount": "30000.00"
            },
            {
                "invoice_number": "INV-OLD-02",
                "voucher_date": "2026-03-25",
                "due_date": "2026-04-15",  # Future
                "amount": "20000.00"
            }
        ]

        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('50000.00'),
            balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1),
            pending_invoices=pending,
            user=self.user
        )

        customer.refresh_from_db()
        self.assertEqual(customer.current_balance, Decimal('50000.00'))

        # Verify vouchers exist
        self.assertTrue(Voucher.objects.filter(voucher_number="INV-OLD-01", voucher_type="OPENING_INVOICE").exists())
        self.assertTrue(Voucher.objects.filter(voucher_number="INV-OLD-02", voucher_type="OPENING_INVOICE").exists())

        # Test Khata view endpoint
        res = self.client.get(f"/api/v1/ledgers/{self.company.id}/{customer.id}/khata/")
        self.assertEqual(res.status_code, 200)
        data = res.data["data"]
        self.assertEqual(data["balance_label"], "To Collect")
        self.assertEqual(data["aging"]["unpaid_invoices"][0]["voucher_number"], "INV-OLD-01")

    def test_04_incorrect_pending_invoices_rejected(self):
        """Scenario 4: Sum of pending invoices mismatching opening balance is rejected."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Faulty Store",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('50000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )

        pending = [
            {"invoice_number": "INV-01", "amount": "45000.00"}
        ]

        with self.assertRaises(ValidationError) as ctx:
            OpeningBalanceService.record_opening_balance(
                ledger=customer,
                amount=Decimal('50000.00'),
                balance_type="DEBIT",
                pending_invoices=pending,
                user=self.user
            )
        self.assertIn("Difference", str(ctx.exception))

    def test_05_opening_balance_correction_with_existing_transactions(self):
        """Scenario 5: Changing opening balance after transactions exist posts differential journal."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Sharma Trading",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('50000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )
        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('50000.00'),
            balance_type="DEBIT",
            user=self.user
        )

        # Subsequent transaction: Sales of ₹10,000
        sale_vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="SAL-001",
            voucher_date=datetime.date(2026, 5, 1),
            party_ledger=customer,
            status="POSTED",
            total_amount=Decimal('10000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=sale_vch, ledger=customer, debit_amount=Decimal('10000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=sale_vch, ledger=self.sales_ledger, credit_amount=Decimal('10000.00'))
        VoucherService.recalculate_ledger_balance(customer)
        customer.refresh_from_db()
        self.assertEqual(customer.current_balance, Decimal('60000.00'))

        # Now edit opening balance: ₹50,000 -> ₹80,000
        OpeningBalanceService.adjust_opening_balance(
            ledger=customer,
            new_amount=Decimal('80000.00'),
            new_balance_type="DEBIT",
            user=self.user,
            reason="Auditor corrected initial ledger"
        )

        customer.refresh_from_db()
        self.assertEqual(customer.opening_balance, Decimal('80000.00'))
        self.assertEqual(customer.current_balance, Decimal('90000.00'))  # 80k + 10k sale

        # Verify differential voucher
        diff_vch = Voucher.objects.filter(party_ledger=customer, voucher_type="JOURNAL", correction_reason="Auditor corrected initial ledger").first()
        self.assertIsNotNone(diff_vch)
        self.assertEqual(diff_vch.total_amount, Decimal('30000.00'))

        # Verify audit log
        self.assertTrue(AuditLog.objects.filter(company=self.company, model_name="LedgerOpeningBalance", action="UPDATE").exists())

    def test_06_customer_and_supplier_same_gstin(self):
        """Scenario 6: Business as Customer and Supplier on same GSTIN without accidental merge."""
        gstin = "27AAACB1234C1Z1"
        
        # 1. Create Supplier
        res1 = self.client.post(f"/api/v1/ledgers/{self.company.id}/", {
            "name": "Reliance Distributor",
            "gstin": gstin,
            "group_name": "Sundry Creditors",
            "ledger_type": "SUPPLIER"
        })
        self.assertEqual(res1.status_code, 201)
        supplier_id = res1.data["data"]["id"]

        # 2. Attempt to create Customer with same GSTIN without role_action: should return conflict
        res2 = self.client.post(f"/api/v1/ledgers/{self.company.id}/", {
            "name": "Reliance Retail",
            "gstin": gstin,
            "group_name": "Sundry Debtors",
            "ledger_type": "CUSTOMER"
        })
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.data["conflict_type"], "ROLE_DIFFERENCE")

        # 3. Create with explicit separate role
        res3 = self.client.post(f"/api/v1/ledgers/{self.company.id}/", {
            "name": "Reliance Retail",
            "gstin": gstin,
            "group_name": "Sundry Debtors",
            "ledger_type": "CUSTOMER",
            "role_action": "CREATE_SEPARATE"
        })
        self.assertEqual(res3.status_code, 201)
        customer_id = res3.data["data"]["id"]

        self.assertNotEqual(supplier_id, customer_id)
        self.assertEqual(Ledger.objects.filter(company=self.company, gstin=gstin).count(), 2)

    def test_07_payment_against_opening_balance(self):
        """Scenario 7: Receive ₹20,000 against ₹50,000 opening balance."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Gupta Bros",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('50000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )
        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('50000.00'),
            balance_type="DEBIT",
            user=self.user
        )

        # Receive payment ₹20,000
        rcpt = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCPT-001",
            voucher_date=datetime.date(2026, 4, 10),
            party_ledger=customer,
            status="POSTED",
            total_amount=Decimal('20000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=rcpt, ledger=self.cash_ledger, debit_amount=Decimal('20000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=rcpt, ledger=customer, credit_amount=Decimal('20000.00'))
        
        VoucherService.recalculate_ledger_balance(customer)
        customer.refresh_from_db()
        self.assertEqual(customer.current_balance, Decimal('30000.00'))

    def test_08_payment_allocation_against_pending_invoices(self):
        """Scenario 8: Auto-allocate payment against pending opening invoices."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Modern Electronics",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('50000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )
        pending = [
            {"invoice_number": "INV-P-01", "voucher_date": "2026-03-01", "due_date": "2026-03-15", "amount": "30000.00"},
            {"invoice_number": "INV-P-02", "voucher_date": "2026-03-10", "due_date": "2026-03-25", "amount": "20000.00"}
        ]
        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('50000.00'),
            balance_type="DEBIT",
            pending_invoices=pending,
            user=self.user
        )

        rcpt = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCPT-002",
            voucher_date=datetime.date(2026, 4, 5),
            party_ledger=customer,
            status="POSTED",
            total_amount=Decimal('35000.00'),
            created_by=self.user
        )
        
        allocations = PaymentAllocationService.auto_allocate_voucher(rcpt)
        self.assertEqual(len(allocations), 2)
        self.assertEqual(Decimal(allocations[0]['allocated_amount']), Decimal('30000.00'))
        self.assertEqual(Decimal(allocations[1]['allocated_amount']), Decimal('5000.00'))

    def test_09_year_end_closing_opening_balance_carryforward(self):
        """Scenario 9: FY closing balance carries forward into next FY opening balance."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Anand Sweets",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('25000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )
        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('25000.00'),
            balance_type="DEBIT",
            user=self.user
        )

        result = YearEndClosingService.close_and_roll_forward(str(self.company.id), str(self.fy.id))
        self.assertTrue(result["success"])

        # Check next FY
        next_fy = FinancialYear.objects.get(code="27-28", company=self.company)
        from apps.accounting.models import LedgerBalance
        next_lb = LedgerBalance.objects.get(ledger=customer, financial_year=next_fy)
        self.assertEqual(next_lb.opening_balance, Decimal('25000.00'))
        self.assertEqual(next_lb.opening_type, "DR")

    def test_10_credit_terms_and_due_date_calculation(self):
        """Scenario 10: Invoice due date auto-calculated from credit_period_days."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Credit Client",
            ledger_type="CUSTOMER",
            credit_period_days=30
        )

        vch = SalesInvoiceService.generate_sales_invoice(
            company=self.company,
            user=self.user,
            party_ledger=customer,
            items_data=[{"item_name": "Item A", "quantity": 1, "rate": 1000}],
            manual_voucher_date=datetime.date(2026, 5, 1)
        )

        self.assertEqual(vch.due_date, datetime.date(2026, 5, 31))

    def test_11_credit_limit_warning_and_enforcement(self):
        """Scenario 11: Credit limit warning and blocking on sales invoice."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Limited Client",
            ledger_type="CUSTOMER",
            credit_limit=Decimal('10000.00')
        )

        # 1. When enforce_credit_limit is False: allows with warning
        self.settings.enforce_credit_limit = False
        self.settings.save()

        vch = SalesInvoiceService.generate_sales_invoice(
            company=self.company,
            user=self.user,
            party_ledger=customer,
            items_data=[{"item_name": "Item Huge", "quantity": 1, "rate": 15000}],
            manual_voucher_date=datetime.date(2026, 5, 1)
        )
        self.assertTrue(hasattr(vch, 'credit_limit_warning'))

        # 2. When enforce_credit_limit is True: blocks with ValidationError
        self.settings.enforce_credit_limit = True
        self.settings.save()

        with self.assertRaises(Exception) as ctx:
            SalesInvoiceService.generate_sales_invoice(
                company=self.company,
                user=self.user,
                party_ledger=customer,
                items_data=[{"item_name": "Item Huge 2", "quantity": 1, "rate": 15000}],
                manual_voucher_date=datetime.date(2026, 5, 2)
            )
        self.assertIn("Credit limit exceeded", str(ctx.exception))

    def test_12_balance_rebuild_reconciliation(self):
        """Scenario 12: BalanceRebuildService accurately reconstructs balances."""
        customer = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="Rebuild Client",
            ledger_type="CUSTOMER",
            opening_balance=Decimal('40000.00'),
            opening_balance_type="DEBIT",
            opening_date=datetime.date(2026, 4, 1)
        )
        OpeningBalanceService.record_opening_balance(
            ledger=customer,
            amount=Decimal('40000.00'),
            balance_type="DEBIT",
            user=self.user
        )

        # Mutate cached current_balance artificially to simulate drift
        customer.current_balance = Decimal('99999.00')
        customer.save(update_fields=['current_balance'])

        # Run balance rebuild
        rebuild_res = BalanceRebuildService.rebuild_company_ledger_balances(self.company)
        self.assertTrue(rebuild_res["success"])

        customer.refresh_from_db()
        self.assertEqual(customer.current_balance, Decimal('40000.00'))

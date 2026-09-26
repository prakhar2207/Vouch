import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
User = get_user_model()

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, PaymentAllocation, BankTransaction, AccountingFinding
from apps.inventory.models import Product, ProductCategory, Warehouse
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.deduplication_engine import TransactionDeduplicationEngine
from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
from apps.accounting.services.finding_fix_service import FindingFixService
from apps.accounting.services.sequence_service import InvoiceSequenceService


class TransactionDeduplicationEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="testaccountant@vouch.internal", password="password123")
        self.company = Company.objects.create(name="Deduplication Test Store", gstin="29AAAAA0000A1Z5")
        self.fy = InvoiceSequenceService.get_or_create_active_fy(self.company, datetime.date.today())

        self.sundry_debtors, _ = LedgerGroup.objects.get_or_create(
            company=self.company, name="Sundry Debtors", defaults={"nature": "ASSET"}
        )
        self.bank_group, _ = LedgerGroup.objects.get_or_create(
            company=self.company, name="Bank Accounts", defaults={"nature": "ASSET"}
        )

        self.customer = Ledger.objects.create(
            company=self.company,
            group=self.sundry_debtors,
            name="Classic Pipe Enterprises",
            ledger_type="CUSTOMER",
            current_balance=Decimal("10000.00")
        )

        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.bank_group,
            name="HDFC Bank",
            ledger_type="BANK",
            current_balance=Decimal("50000.00")
        )

    def test_check_duplicate_candidate_exact_and_rapid(self):
        # 1. Post a first receipt voucher
        v1 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-001",
            voucher_date=datetime.date.today(),
            party_ledger=self.customer,
            total_amount=Decimal("3029.00"),
            status="POSTED",
            created_by=self.user
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v1, ledger=self.bank_ledger, debit_amount=Decimal("3029.00"), credit_amount=Decimal("0.00")
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v1, ledger=self.customer, debit_amount=Decimal("0.00"), credit_amount=Decimal("3029.00")
        )

        # 2. Check candidate for identical entry
        res = TransactionDeduplicationEngine.check_duplicate_candidate(
            company=self.company,
            voucher_type="RECEIPT",
            party_ledger=self.customer,
            total_amount=Decimal("3029.00"),
            voucher_date=datetime.date.today()
        )
        self.assertTrue(res["is_duplicate"])
        self.assertEqual(res["matching_voucher"]["voucher_number"], "RCP-001")

    def test_bank_recon_auto_matches_existing_voucher(self):
        # 1. User records a manual receipt
        v1 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-MANUAL-01",
            voucher_date=datetime.date.today(),
            party_ledger=self.customer,
            total_amount=Decimal("3029.00"),
            status="DRAFT",
            created_by=self.user
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v1, ledger=self.bank_ledger, debit_amount=Decimal("3029.00"), credit_amount=Decimal("0.00")
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v1, ledger=self.customer, debit_amount=Decimal("0.00"), credit_amount=Decimal("3029.00")
        )
        VoucherService.post_voucher(v1)

        # 2. Bank statement transaction arrives for the same amount and date
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date.today(),
            description="UPI/CLASSIC PIPE/REF123",
            credit_amount=Decimal("3029.00"),
            debit_amount=Decimal("0.00"),
            status="UNRESOLVED"
        )

        # 3. Resolve bank transaction without force_new_voucher
        res = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type="CONFIRM_RECEIPT",
            payload={"party_id": str(self.customer.id)},
            user=self.user
        )

        # 4. Verify that it AUTO-MATCHED existing voucher rather than creating a duplicate
        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, "RECONCILED")
        self.assertEqual(bank_tx.matched_voucher.id, v1.id)
        # Verify no duplicate voucher was created
        receipt_count = Voucher.objects.filter(company=self.company, voucher_type="RECEIPT").count()
        self.assertEqual(receipt_count, 1)

    def test_integrity_engine_scans_and_fixes_duplicate_voucher(self):
        # 1. Create two identical vouchers (simulating a double entry)
        v1 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-001",
            voucher_date=datetime.date.today(),
            party_ledger=self.customer,
            total_amount=Decimal("1500.00"),
            status="POSTED",
            created_by=self.user
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v1, ledger=self.bank_ledger, debit_amount=Decimal("1500.00"), credit_amount=Decimal("0.00")
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v1, ledger=self.customer, debit_amount=Decimal("0.00"), credit_amount=Decimal("1500.00")
        )

        v2 = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type="RECEIPT",
            voucher_number="RCP-002",
            voucher_date=datetime.date.today(),
            party_ledger=self.customer,
            total_amount=Decimal("1500.00"),
            status="POSTED",
            created_by=self.user
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v2, ledger=self.bank_ledger, debit_amount=Decimal("1500.00"), credit_amount=Decimal("0.00")
        )
        LedgerEntry.objects.create(
            company=self.company, voucher=v2, ledger=self.customer, debit_amount=Decimal("0.00"), credit_amount=Decimal("1500.00")
        )

        VoucherService.recalculate_ledger_balance(self.customer)
        VoucherService.recalculate_ledger_balance(self.bank_ledger)

        # 2. Run integrity audit
        report = AccountingIntegrityEngine.run_all_checks(self.company)
        dup_findings = [f for f in report["findings"] if f["category"] == "DUPLICATE" and f["fix_action"] == "VOID_DUPLICATE_VOUCHER"]
        self.assertTrue(len(dup_findings) >= 1)

        # 3. Test Preview
        finding_obj = AccountingFinding.objects.get(id=dup_findings[0]["id"])
        preview = FindingFixService.generate_fix_preview(finding_obj)
        self.assertTrue(preview["supported"])
        self.assertEqual(preview["action"], "VOID_DUPLICATE_VOUCHER")

        # 4. Test Execute Fix
        result = FindingFixService.execute_fix(finding_obj, user=self.user)
        self.assertEqual(result["status"], "SUCCESS")

        v2.refresh_from_db()
        self.assertEqual(v2.status, "CANCELLED")
        finding_obj.refresh_from_db()
        self.assertTrue(finding_obj.is_resolved)

    def test_merge_inventory_items(self):
        cat = ProductCategory.objects.create(company=self.company, name="Belts")
        p1 = Product.objects.create(
            company=self.company, category=cat, name="B 42", brand="PIX", sku="B42-01", stock_quantity=Decimal("5.00")
        )
        p2 = Product.objects.create(
            company=self.company, category=cat, name="B 42", brand="PIX", sku="B42-02", stock_quantity=Decimal("3.00")
        )

        # 1. Scan duplicate inventory
        report = AccountingIntegrityEngine.run_all_checks(self.company)
        inv_findings = [f for f in report["findings"] if f["category"] == "DUPLICATE_INVENTORY"]
        self.assertTrue(len(inv_findings) >= 1)

        # 2. Fix finding
        finding_obj = AccountingFinding.objects.get(id=inv_findings[0]["id"])
        preview = FindingFixService.generate_fix_preview(finding_obj)
        self.assertTrue(preview["supported"])

        result = FindingFixService.execute_fix(finding_obj, user=self.user)
        self.assertEqual(result["status"], "SUCCESS")

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.stock_quantity, Decimal("8.00"))
        self.assertFalse(p2.is_active)

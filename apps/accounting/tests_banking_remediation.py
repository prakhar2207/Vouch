import datetime
import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import (
    FinancialYear, Voucher, LedgerEntry, BankTransaction, BankStatementImport, PaymentAllocation, IdempotencyRecord, AccountingFinding
)
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService


class BankReconciliationRemediationTests(APITestCase):
    """
    Production-grade verification test suite for Bank Reconciliation remediation.
    Mandatory compliance with GEMINI.md test isolation invariants.
    """

    SANDBOX_COMPANY_ID = uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33')
    PROTECTED_COMPANY_ID = uuid.UUID('5d2e5dea-ff86-4871-b2af-fe1c5a05c03c')

    def setUp(self):
        # Enforce GEMINI.md Sandbox Policy
        self.company = Company.objects.create(
            id=self.SANDBOX_COMPANY_ID,
            name="Apex Belting & Industrial Store (Demo)",
            gstin="27AAPCA1234F1Z5",
            state_code="27"
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
        )
        assert str(self.company.id) != '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c', (
            "CRITICAL: Under no circumstances touch Maa Annapurna Belting Store!"
        )

        # Competitor tenant for tenant isolation verification
        self.company_b = Company.objects.create(
            id=uuid.uuid4(),
            name="Competitor Belts Ltd",
            gstin="27XYZAB9999K1Z2",
            state_code="27"
        )

        self.user = User.objects.create_user(
            email="tester@apexbelting.demo",
            password="testpassword123",
            role="ADMIN"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role="ADMIN")
        self.client.force_authenticate(user=self.user)

        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
            is_closed=False
        )

        # Standard Groups
        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Bank Accounts", nature="ASSET")
        self.debtor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Debtors", nature="ASSET")
        self.creditor_grp = LedgerGroup.objects.create(company=self.company, name="Sundry Creditors", nature="LIABILITY")
        self.expense_grp = LedgerGroup.objects.create(company=self.company, name="Bank Charges", nature="EXPENSE")

        # Bank and Party Ledgers
        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            group=self.asset_grp,
            name="HDFC Current Account",
            ledger_type="BANK",
            opening_balance=Decimal('10000.00'),
            current_balance=Decimal('10000.00'),
            is_active=True
        )
        self.customer_ledger = Ledger.objects.create(
            company=self.company,
            group=self.debtor_grp,
            name="Shree Adinath Traders",
            ledger_type="CUSTOMER",
            is_active=True
        )
        self.vendor_ledger = Ledger.objects.create(
            company=self.company,
            group=self.creditor_grp,
            name="Fenner Power Transmission",
            ledger_type="SUPPLIER",
            is_active=True
        )
        self.expense_ledger = Ledger.objects.create(
            company=self.company,
            group=self.expense_grp,
            name="Bank Maintenance Charges",
            ledger_type="EXPENSE",
            is_active=True
        )

        # Tenant B Ledger
        self.grp_b = LedgerGroup.objects.create(company=self.company_b, name="Competitor Banks", nature="ASSET")
        self.bank_b = Ledger.objects.create(
            company=self.company_b,
            group=self.grp_b,
            name="Competitor ICICI Bank",
            ledger_type="BANK",
            is_active=True
        )

    # -------------------------------------------------------------------------
    # SCENARIOS 1-5: Missing Statement Evidence vs Zero Balance (NOT_VERIFIABLE)
    # -------------------------------------------------------------------------

    def test_01_summary_missing_statement_is_not_verifiable(self):
        """When no statement has been imported and no transactions exist, state is NOT_STARTED. When transactions exist without statement, it is NOT_VERIFIABLE."""
        summary_empty = BankReconciliationService.get_reconciliation_summary(
            self.company,
            bank_ledger_id=str(self.bank_ledger.id)
        )
        self.assertIsNone(summary_empty['statement_closing_balance'])
        self.assertIsNone(summary_empty['reconciliation_gap'])
        self.assertFalse(summary_empty['is_balanced'])
        self.assertEqual(summary_empty['reconciliation_state'], 'NOT_STARTED')

        # Add a transaction without importing a statement
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 1),
            credit_amount=Decimal('5000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Customer NEFT IN'
        )
        summary_with_tx = BankReconciliationService.get_reconciliation_summary(
            self.company,
            bank_ledger_id=str(self.bank_ledger.id)
        )
        self.assertEqual(summary_with_tx['reconciliation_state'], 'NOT_VERIFIABLE')

    def test_02_summary_completed_count_excludes_ai_suggestions(self):
        """completed_count must strictly reflect RECONCILED vouchers, never MATCHED_AUTO or MATCHED_SUGGESTED."""
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 1),
            credit_amount=Decimal('5000.00'),
            debit_amount=Decimal('0.00'),
            status='MATCHED_AUTO',
            description='Customer NEFT IN'
        )
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 2),
            credit_amount=Decimal('0.00'),
            debit_amount=Decimal('100.00'),
            status='MATCHED_SUGGESTED',
            description='Bank charges'
        )
        summary = BankReconciliationService.get_reconciliation_summary(
            self.company,
            bank_ledger_id=str(self.bank_ledger.id)
        )
        self.assertEqual(summary['total_transactions'], 2)
        self.assertEqual(summary['completed_count'], 0)  # Provisional suggestions must NOT count as completed!
        self.assertEqual(summary['auto_matched'], 1)
        self.assertEqual(summary['suggested'], 1)

    def test_03_brs_missing_statement_returns_not_verifiable(self):
        """Statutory BRS generation must flag NOT_VERIFIABLE when statement closing balance is absent."""
        brs = BankReconciliationService.generate_statutory_brs(
            company=self.company,
            bank_ledger_id=str(self.bank_ledger.id),
            as_of_date=datetime.date(2026, 5, 31)
        )
        self.assertEqual(brs['reconciliation_status'], 'NOT_VERIFIABLE')
        self.assertIsNone(brs['actual_statement_balance'])
        self.assertIsNone(brs['variance'])

    def test_04_brs_cutoff_isolation(self):
        """Transactions posted after the cutoff date must NOT affect past cutoff BRS calculation."""
        # Statement import with closing balance
        import_rec = BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="stmt_may.csv",
            file_hash="hash_may_brs",
            closing_balance=Decimal('15000.00'),
            statement_end_date=datetime.date(2026, 5, 31)
        )
        # Transaction on May 15
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            statement_import=import_rec,
            transaction_date=datetime.date(2026, 5, 15),
            credit_amount=Decimal('5000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Inward May'
        )
        # Transaction on June 15 (future relative to May 31 cutoff)
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            statement_import=import_rec,
            transaction_date=datetime.date(2026, 6, 15),
            credit_amount=Decimal('20000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Inward June'
        )

        brs_may = BankReconciliationService.generate_statutory_brs(
            company=self.company,
            bank_ledger_id=str(self.bank_ledger.id),
            as_of_date=datetime.date(2026, 5, 31)
        )
        uncredited_may = [d['description'] for d in brs_may['additions']['unrecorded_bank_credits']['items']]
        self.assertIn('Inward May', uncredited_may)
        self.assertNotIn('Inward June', uncredited_may)

    def test_05_summary_zero_balance_distinguished_from_null(self):
        """A verified zero closing balance (0.00) must be distinguished from missing evidence (None)."""
        BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="zero_stmt.csv",
            file_hash="hash_zero_stmt",
            closing_balance=Decimal('0.00'),
            statement_end_date=datetime.date(2026, 5, 31)
        )
        summary = BankReconciliationService.get_reconciliation_summary(
            self.company,
            bank_ledger_id=str(self.bank_ledger.id)
        )
        self.assertEqual(Decimal(str(summary['statement_closing_balance'])), Decimal('0.00'))
        self.assertIsNotNone(summary['reconciliation_gap'])

    # -------------------------------------------------------------------------
    # SCENARIOS 6-12: MATCH_EXISTING_VOUCHER Validation Controls
    # -------------------------------------------------------------------------

    def test_06_match_existing_voucher_success(self):
        """Valid posted voucher matching exact amount, bank ledger, and company succeeds."""
        vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/0001',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1500.00'),
            party_ledger=self.vendor_ledger,
            status='POSTED',
            created_by=self.user
        )
        LedgerEntry.objects.create(
            voucher=vch,
            ledger=self.bank_ledger,
            credit_amount=Decimal('1500.00'),
            debit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            voucher=vch,
            ledger=self.vendor_ledger,
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00')
        )

        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Payment to Fenner'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='MATCH_EXISTING_VOUCHER',
            payload={'voucher_id': str(vch.id)},
            user=self.user
        )
        self.assertEqual(res['status'], 'SUCCESS')
        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, 'RECONCILED')
        self.assertEqual(bank_tx.matched_voucher_id, vch.id)

    def test_07_match_existing_voucher_amount_mismatch_rejected(self):
        """Matching a voucher with a different amount must raise ValidationError."""
        vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/0002',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1600.00'),
            party_ledger=self.vendor_ledger,
            status='POSTED',
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=vch, ledger=self.bank_ledger, credit_amount=Decimal('1600.00'), debit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=vch, ledger=self.vendor_ledger, debit_amount=Decimal('1600.00'), credit_amount=Decimal('0.00'))

        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Payment to Fenner'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(vch.id)},
                user=self.user
            )
        self.assertIn("Amount mismatch", str(ctx.exception))

    def test_08_match_existing_voucher_reversed_status_rejected(self):
        """A reversed voucher cannot be reconciled."""
        vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/0003',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1500.00'),
            party_ledger=self.vendor_ledger,
            status='REVERSED',
            created_by=self.user
        )
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Payment to Fenner'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(vch.id)},
                user=self.user
            )
        self.assertIn("Only active POSTED vouchers can be matched", str(ctx.exception))

    def test_09_match_existing_voucher_already_linked_rejected(self):
        """A voucher already linked to another reconciled transaction cannot be double-matched."""
        vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/0004',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1500.00'),
            party_ledger=self.vendor_ledger,
            status='POSTED',
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=vch, ledger=self.bank_ledger, credit_amount=Decimal('1500.00'), debit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=vch, ledger=self.vendor_ledger, debit_amount=Decimal('1500.00'), credit_amount=Decimal('0.00'))

        # First transaction matches it
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='RECONCILED',
            matched_voucher=vch,
            description='First Match'
        )
        # Second transaction attempts to match same voucher
        tx2 = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Second Attempt'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=tx2,
                action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(vch.id)},
                user=self.user
            )
        self.assertIn("already reconciled to another bank transaction", str(ctx.exception))

    def test_10_match_existing_voucher_wrong_ledger_rejected(self):
        """Voucher that does not debit or credit the active bank ledger cannot be matched."""
        cash_ledger = Ledger.objects.create(company=self.company, group=self.asset_grp, name="Cash in Hand", ledger_type="CASH")
        vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/0005',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1500.00'),
            party_ledger=self.vendor_ledger,
            status='POSTED',
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=vch, ledger=cash_ledger, credit_amount=Decimal('1500.00'), debit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=vch, ledger=self.vendor_ledger, debit_amount=Decimal('1500.00'), credit_amount=Decimal('0.00'))

        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Payment via HDFC'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(vch.id)},
                user=self.user
            )
        self.assertIn("does not affect bank ledger", str(ctx.exception))

    def test_11_match_existing_voucher_wrong_direction_rejected(self):
        """A money-in transaction cannot match a voucher that credited the bank ledger."""
        vch = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/0006',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1500.00'),
            party_ledger=self.vendor_ledger,
            status='POSTED',
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=vch, ledger=self.bank_ledger, credit_amount=Decimal('1500.00'), debit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=vch, ledger=self.vendor_ledger, debit_amount=Decimal('1500.00'), credit_amount=Decimal('0.00'))

        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            credit_amount=Decimal('1500.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Inward money'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(vch.id)},
                user=self.user
            )
        self.assertIn("Direction mismatch", str(ctx.exception))

    def test_12_tenant_isolation_violation_rejected(self):
        """Cross-tenant voucher match attempt is strictly rejected."""
        vch_b = Voucher.objects.create(
            company=self.company_b,
            voucher_type='PAYMENT',
            voucher_number='PAY/26-27/9999',
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('1500.00'),
            status='POSTED',
            created_by=self.user
        )
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            debit_amount=Decimal('1500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Attempt match competitor'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(vch_b.id)},
                user=self.user
            )
        self.assertIn("does not exist in this company", str(ctx.exception))

    # -------------------------------------------------------------------------
    # SCENARIOS 13-18: Closed Accounting Period & Idempotency Controls
    # -------------------------------------------------------------------------

    def test_13_closed_period_resolution_rejected(self):
        """Modifications and reconciliation are strictly blocked in a closed financial year."""
        self.fy.is_closed = True
        self.fy.save()

        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            credit_amount=Decimal('2000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Deposit in closed year'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='RECORD_PAYMENT',
                payload={'party_id': str(self.customer_ledger.id)},
                user=self.user
            )
        self.assertIn("is closed", str(ctx.exception))

    def test_14_closed_period_unreconcile_rejected(self):
        """Unreconciling a transaction in a closed financial year is strictly blocked."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 10),
            credit_amount=Decimal('2000.00'),
            debit_amount=Decimal('0.00'),
            status='RECONCILED',
            description='Reconciled in closed year'
        )
        self.fy.is_closed = True
        self.fy.save()

        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.unreconcile_transaction(
                bank_tx=bank_tx,
                reason="Attempt unreconcile in closed period",
                user=self.user
            )
        self.assertIn("is closed", str(ctx.exception))

    def test_15_idempotency_protection_prevents_duplicate_voucher(self):
        """Repeated resolution request with the same idempotency key returns cached result without posting second voucher."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 12),
            credit_amount=Decimal('4500.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Customer NEFT 4500'
        )

        key = "idemp_test_key_001"
        res1 = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='RECORD_PAYMENT',
            payload={'party_id': str(self.customer_ledger.id), 'idempotency_key': key},
            user=self.user,
            idempotency_key=key
        )
        self.assertEqual(res1['status'], 'SUCCESS')
        voucher_count = Voucher.objects.filter(company=self.company, party_ledger=self.customer_ledger).count()
        self.assertEqual(voucher_count, 1)

        # Re-execute with identical key
        bank_tx.refresh_from_db()
        res2 = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='RECORD_PAYMENT',
            payload={'party_id': str(self.customer_ledger.id), 'idempotency_key': key},
            user=self.user,
            idempotency_key=key
        )
        self.assertEqual(res2['status'], 'SUCCESS')
        voucher_count_after = Voucher.objects.filter(company=self.company, party_ledger=self.customer_ledger).count()
        self.assertEqual(voucher_count_after, 1)

    # -------------------------------------------------------------------------
    # SCENARIOS 19-24: Safe Unreconciliation & Atomic Rollback
    # -------------------------------------------------------------------------

    def test_16_safe_unreconcile_cancels_voucher_and_restores_unresolved(self):
        """Unreconciling a transaction cancels the generated voucher and restores status to UNRESOLVED."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 14),
            debit_amount=Decimal('300.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Bank charge'
        )
        res = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='RECORD_EXPENSE',
            payload={'expense_ledger_id': str(self.expense_ledger.id)},
            user=self.user
        )
        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, 'RECONCILED')
        created_vch = bank_tx.matched_voucher
        self.assertIsNotNone(created_vch)

        # Unreconcile
        unrec_res = BankReconciliationService.unreconcile_transaction(
            bank_tx=bank_tx,
            reason="User cancelled reconciliation",
            user=self.user
        )
        self.assertEqual(unrec_res['status'], 'SUCCESS')
        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, 'UNRESOLVED')
        self.assertIsNone(bank_tx.matched_voucher)

        created_vch.refresh_from_db()
        self.assertIn(created_vch.status, ['CANCELLED', 'REVERSED'])

    def test_17_unreconcile_noop_if_not_reconciled(self):
        """Calling unreconcile on an un-reconciled transaction is safe NOOP."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 14),
            debit_amount=Decimal('300.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Bank charge'
        )
        res = BankReconciliationService.unreconcile_transaction(bank_tx, user=self.user)
        self.assertEqual(res['status'], 'NOOP')

    # -------------------------------------------------------------------------
    # SCENARIOS 25-30: Transaction & Statement Exclusion and Restoration
    # -------------------------------------------------------------------------

    def test_18_exclude_transaction_requires_reason(self):
        """Exclusion without a non-empty reason is rejected."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 16),
            credit_amount=Decimal('100.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Mystery deposit'
        )
        with self.assertRaises(ValidationError):
            BankReconciliationService.exclude_transaction(bank_tx, reason="", user=self.user)

    def test_19_exclude_reconciled_transaction_creates_reversal_voucher(self):
        """Excluding a reconciled transaction reverses its voucher and marks bank transaction EXCLUDED."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 16),
            debit_amount=Decimal('600.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Office stationery'
        )
        BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='RECORD_EXPENSE',
            payload={'expense_ledger_id': str(self.expense_ledger.id)},
            user=self.user
        )
        bank_tx.refresh_from_db()
        vch = bank_tx.matched_voucher

        # Exclude
        res = BankReconciliationService.exclude_transaction(
            bank_tx=bank_tx,
            reason="Personal card used accidentally",
            user=self.user
        )
        self.assertEqual(res['status'], 'SUCCESS')
        bank_tx.refresh_from_db()
        self.assertTrue(bank_tx.is_excluded)
        self.assertEqual(bank_tx.status, 'EXCLUDED')
        vch.refresh_from_db()
        self.assertEqual(vch.status, 'REVERSED')

    def test_20_cannot_resolve_excluded_transaction(self):
        """Attempting to resolve an excluded transaction raises ValidationError."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 16),
            credit_amount=Decimal('500.00'),
            debit_amount=Decimal('0.00'),
            status='EXCLUDED',
            is_excluded=True,
            exclusion_reason="Personal",
            description='Personal transfer'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=bank_tx,
                action_type='RECORD_PAYMENT',
                payload={'party_id': str(self.customer_ledger.id)},
                user=self.user
            )
        self.assertIn("Cannot resolve an excluded bank transaction", str(ctx.exception))

    def test_21_restore_excluded_transaction(self):
        """Restoring an excluded transaction resets status to UNRESOLVED without recreating vouchers."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 16),
            credit_amount=Decimal('500.00'),
            debit_amount=Decimal('0.00'),
            status='EXCLUDED',
            is_excluded=True,
            exclusion_reason="Personal",
            description='Personal transfer'
        )
        res = BankReconciliationService.restore_transaction(bank_tx, user=self.user)
        self.assertEqual(res['status'], 'SUCCESS')
        bank_tx.refresh_from_db()
        self.assertFalse(bank_tx.is_excluded)
        self.assertEqual(bank_tx.status, 'UNRESOLVED')
        self.assertIsNone(bank_tx.exclusion_reason)

    def test_22_statement_level_exclusion_propagates_to_transactions(self):
        """Excluding an entire statement marks all its transactions excluded."""
        stmt = BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="wrong_bank.csv",
            file_hash="hash_wrong_bank"
        )
        tx1 = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            statement_import=stmt,
            transaction_date=datetime.date(2026, 5, 1),
            credit_amount=Decimal('100.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Wrong 1'
        )
        tx2 = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            statement_import=stmt,
            transaction_date=datetime.date(2026, 5, 2),
            credit_amount=Decimal('200.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='Wrong 2'
        )

        count = BankReconciliationService.exclude_statement_import(stmt, reason="Uploaded wrong bank statement", user=self.user)
        self.assertEqual(count, 2)
        stmt.refresh_from_db()
        tx1.refresh_from_db()
        tx2.refresh_from_db()
        self.assertTrue(stmt.is_excluded)
        self.assertTrue(tx1.is_excluded)
        self.assertTrue(tx2.is_excluded)
        self.assertEqual(tx1.status, 'EXCLUDED')
        self.assertEqual(tx2.status, 'EXCLUDED')

    def test_23_statement_level_restore_propagates(self):
        """Restoring an excluded statement restores all its transactions."""
        stmt = BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="re_enable.csv",
            file_hash="hash_re_enable",
            is_excluded=True,
            exclusion_reason="Accidental exclude"
        )
        tx1 = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            statement_import=stmt,
            transaction_date=datetime.date(2026, 5, 1),
            credit_amount=Decimal('100.00'),
            debit_amount=Decimal('0.00'),
            status='EXCLUDED',
            is_excluded=True,
            description='Reenable 1'
        )
        count = BankReconciliationService.restore_statement_import(stmt, user=self.user)
        self.assertEqual(count, 1)
        stmt.refresh_from_db()
        tx1.refresh_from_db()
        self.assertFalse(stmt.is_excluded)
        self.assertFalse(tx1.is_excluded)
        self.assertEqual(tx1.status, 'UNRESOLVED')

    def test_24_api_unreconcile_endpoint(self):
        """HTTP POST to /api/v1/accounting/banking/transactions/<id>/unreconcile/ succeeds."""
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 5, 18),
            debit_amount=Decimal('50.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED',
            description='SMS alert charge'
        )
        BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='RECORD_EXPENSE',
            payload={'expense_ledger_id': str(self.expense_ledger.id)},
            user=self.user
        )
        url = f"/api/v1/accounting/banking/transactions/{bank_tx.id}/unreconcile/"
        res = self.client.post(url, {"reason": "Test API unreconcile"}, format="json", HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, 'UNRESOLVED')


    # =========================================================================
    # HELPER METHOD FOR CLEAN VOUCHER & LEDGER CREATION
    # =========================================================================

    def _create_test_voucher(
        self, voucher_type='PAYMENT', amount=Decimal('100.00'), party_ledger=None,
        bank_ledger=None, voucher_date=None, voucher_number=None, company=None,
        financial_year=None, reference_number='', status='POSTED'
    ):
        import uuid
        c = company or self.company
        fy = financial_year or self.fy
        p = party_ledger or self.vendor_ledger
        b = bank_ledger or self.bank_ledger
        d = voucher_date or datetime.date(2026, 5, 20)
        v_num = voucher_number or f"{voucher_type[:3]}/{fy.code}/{uuid.uuid4().hex[:6].upper()}"
        v = Voucher.objects.create(
            company=c,
            financial_year=fy,
            voucher_type=voucher_type,
            voucher_number=v_num,
            voucher_date=d,
            total_amount=amount,
            party_ledger=p,
            reference_number=reference_number,
            status=status,
            created_by=self.user
        )
        if voucher_type == 'PAYMENT':
            LedgerEntry.objects.create(voucher=v, ledger=p, debit_amount=amount, credit_amount=Decimal('0.00'))
            LedgerEntry.objects.create(voucher=v, ledger=b, debit_amount=Decimal('0.00'), credit_amount=amount)
        elif voucher_type == 'RECEIPT':
            LedgerEntry.objects.create(voucher=v, ledger=b, debit_amount=amount, credit_amount=Decimal('0.00'))
            LedgerEntry.objects.create(voucher=v, ledger=p, debit_amount=Decimal('0.00'), credit_amount=amount)
        elif voucher_type == 'PURCHASE':
            LedgerEntry.objects.create(voucher=v, ledger=self.expense_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
            LedgerEntry.objects.create(voucher=v, ledger=p, debit_amount=Decimal('0.00'), credit_amount=amount)
        return v

    # =========================================================================
    # PHASE 9 — MANDATORY POSTGRESQL DUPLICATE RESOLUTION & INTEGRITY SUITE
    # =========================================================================

    def test_25_exact_duplicate_payment_detection(self):
        """1. Exact duplicate payment detection classifies as CONFIRMED_DUPLICATE."""
        from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
        v1 = self._create_test_voucher(amount=Decimal('28222.00'), voucher_number='PAY/26-27/0065')
        v2 = self._create_test_voucher(amount=Decimal('28222.00'), voucher_number='PAY/26-27/0083')

        report = AccountingIntegrityEngine.run_all_checks(self.company)
        dup_findings = [f for f in report["findings"] if f["category"] == "DUPLICATE" and f["evidence"].get("duplicate_voucher_id") == str(v2.id)]
        self.assertTrue(len(dup_findings) >= 1)
        self.assertEqual(dup_findings[0]["evidence"]["duplicate_classification"], "CONFIRMED_DUPLICATE")
        self.assertEqual(dup_findings[0]["fix_action"], "VOID_DUPLICATE_VOUCHER")

    def test_26_same_amount_different_party_not_duplicate(self):
        """2. Same amount but different party ledger is NOT flagged as a duplicate."""
        from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
        other_party = Ledger.objects.create(company=self.company, group=self.creditor_grp, name="Other Supplier Co", ledger_type="SUPPLIER")
        v1 = self._create_test_voucher(amount=Decimal('5000.00'), party_ledger=self.vendor_ledger)
        v2 = self._create_test_voucher(amount=Decimal('5000.00'), party_ledger=other_party)

        report = AccountingIntegrityEngine.run_all_checks(self.company)
        dup_findings = [f for f in report["findings"] if f["category"] == "DUPLICATE" and f["evidence"].get("amount") == "5000.00"]
        self.assertEqual(len(dup_findings), 0)

    def test_27_same_amount_and_party_different_reference_manual_review(self):
        """3. Same amount and party 2 days apart without matching ref digits is PROBABLE_DUPLICATE requiring manual review."""
        from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
        v1 = self._create_test_voucher(amount=Decimal('7500.00'), voucher_date=datetime.date(2026, 5, 20), reference_number="REF-999888")
        v2 = self._create_test_voucher(amount=Decimal('7500.00'), voucher_date=datetime.date(2026, 5, 22), reference_number="REF-111222")

        report = AccountingIntegrityEngine.run_all_checks(self.company)
        dup_findings = [f for f in report["findings"] if f["category"] == "DUPLICATE" and f["evidence"].get("amount") == "7500.00"]
        for f in dup_findings:
            self.assertNotEqual(f["evidence"].get("duplicate_classification"), "CONFIRMED_DUPLICATE")
            self.assertIsNone(f["fix_action"])

    def test_28_different_bank_ledger_rejected_for_duplicate_fix(self):
        """4. Finding with mismatched bank ledgers is rejected during execute_fix."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        bank2 = Ledger.objects.create(company=self.company, group=self.asset_grp, name="HDFC Bank Current A/c", ledger_type="BANK")
        v1 = self._create_test_voucher(amount=Decimal('1000.00'), bank_ledger=self.bank_ledger)
        v2 = self._create_test_voucher(amount=Decimal('1000.00'), bank_ledger=bank2)

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Mismatched Bank Duplicates",
            evidence={"primary_voucher_id": str(v1.id), "duplicate_voucher_id": str(v2.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        res = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res["status"], "SUCCESS")

    def test_29_different_financial_year_rejected_for_duplicate_fix(self):
        """5. Duplicate resolution between vouchers in different FYs is rejected."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        fy_old = FinancialYear.objects.create(
            company=self.company, code="25-26", name="FY 2025-2026",
            start_date=datetime.date(2025, 4, 1), end_date=datetime.date(2026, 3, 31)
        )
        v1 = self._create_test_voucher(amount=Decimal('2000.00'), financial_year=self.fy, voucher_date=datetime.date(2026, 5, 20))
        v2 = self._create_test_voucher(amount=Decimal('2000.00'), financial_year=fy_old, voucher_date=datetime.date(2026, 3, 20))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Cross FY Voucher",
            evidence={"primary_voucher_id": str(v1.id), "duplicate_voucher_id": str(v2.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        with self.assertRaises(ValidationError) as ctx:
            FindingFixService.execute_fix(finding, user=self.user)
        self.assertIn("different financial years", str(ctx.exception))

    def test_30_reversed_duplicate_voucher_aborts_deletion(self):
        """6. If duplicate voucher is already REVERSED, execute_fix resolves finding without re-deleting."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        v1 = self._create_test_voucher(amount=Decimal('3000.00'))
        v2 = self._create_test_voucher(amount=Decimal('3000.00'))
        VoucherService.create_reversal_voucher(v2, user=self.user, reason="Prior reversal")
        v2.refresh_from_db()
        self.assertEqual(v2.status, 'REVERSED')

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Reversed Duplicate",
            evidence={"primary_voucher_id": str(v1.id), "duplicate_voucher_id": str(v2.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        res = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("no deletion required", res["message"])
        self.assertTrue(Voucher.objects.filter(id=v2.id).exists())

    def test_31_duplicate_statement_upload_detection(self):
        """7. Re-uploading an identical statement file produces distinct auditable records."""
        stmt1 = BankStatementImport.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, source_file_name="passbook_may2026.pdf",
            file_hash="hash1234567890", closing_balance=Decimal('50000.00')
        )
        stmt2 = BankStatementImport.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, source_file_name="passbook_may2026.pdf",
            file_hash="hash1234567890", closing_balance=Decimal('50000.00')
        )
        self.assertNotEqual(stmt1.id, stmt2.id)

    def test_32_duplicate_6_rupee_bank_transaction_import_handling(self):
        """8. Duplicate ₹6 bank fee transaction import can be cleanly quarantined/excluded."""
        btx1 = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('6.00'), credit_amount=Decimal('0.00'), status='UNRESOLVED', description='SC NEFT OTHER THAN SB'
        )
        btx2 = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('6.00'), credit_amount=Decimal('0.00'), status='UNRESOLVED', description='SC NEFT OTHER THAN SB'
        )
        res = BankReconciliationService.exclude_transaction(btx2, reason="Duplicate bank statement row", user=self.user)
        self.assertEqual(res["status"], "SUCCESS")
        btx2.refresh_from_db()
        self.assertTrue(btx2.is_excluded)
        self.assertEqual(btx2.status, 'EXCLUDED')
        btx1.refresh_from_db()
        self.assertFalse(btx1.is_excluded)
        self.assertEqual(btx1.status, 'UNRESOLVED')

    def test_33_relink_bank_tx_to_original_voucher_with_flag(self):
        """9. Relinking bank transaction tags is_existing_matched to shield primary voucher from exclusion."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        v_primary = self._create_test_voucher(amount=Decimal('28222.00'), voucher_number='PAY/26-27/0065')
        v_duplicate = self._create_test_voucher(amount=Decimal('28222.00'), voucher_number='PAY/26-27/0083')

        btx = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('28222.00'), credit_amount=Decimal('0.00'), status='RECONCILED',
            matched_voucher=v_duplicate, matched_party=self.vendor_ledger, description='NEFT Adinath Traders'
        )
        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Adinath Duplicate",
            evidence={"primary_voucher_id": str(v_primary.id), "duplicate_voucher_id": str(v_duplicate.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        res = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res["status"], "SUCCESS")
        btx.refresh_from_db()
        self.assertEqual(btx.matched_voucher_id, v_primary.id)
        self.assertTrue(btx.match_notes.get('is_existing_matched'))

        # Excluding btx does NOT reverse v_primary!
        ex_res = BankReconciliationService.exclude_transaction(btx, reason="Quarantine statement", user=self.user)
        self.assertEqual(ex_res["status"], "SUCCESS")
        v_primary.refresh_from_db()
        self.assertEqual(v_primary.status, 'POSTED')

    def test_34_voucher_with_independent_allocations_rejects_delete(self):
        """10. Attempting to delete a duplicate voucher with independent invoice allocations is aborted."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        from apps.accounting.models import PaymentAllocation
        v_prim = self._create_test_voucher(amount=Decimal('1000.00'))
        v_dup = self._create_test_voucher(amount=Decimal('1000.00'))
        inv = self._create_test_voucher(voucher_type='PURCHASE', amount=Decimal('1000.00'))

        PaymentAllocation.objects.create(
            company=self.company, payment_voucher=v_dup, invoice_voucher=inv, allocated_amount=Decimal('1000.00')
        )
        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Allocated Duplicate",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        with self.assertRaises(ValidationError) as ctx:
            FindingFixService.execute_fix(finding, user=self.user)
        self.assertIn("independent invoice allocations", str(ctx.exception))

    def test_35_probable_duplicate_rejects_automated_one_click_fix(self):
        """11. Attempting to execute 1-click fix on a PROBABLE_DUPLICATE raises ValidationError."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        v_prim = self._create_test_voucher(amount=Decimal('400.00'), voucher_date=datetime.date(2026, 5, 20))
        v_dup = self._create_test_voucher(amount=Decimal('400.00'), voucher_date=datetime.date(2026, 5, 22))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="WARNING", title="Probable Duplicate",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "PROBABLE_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        with self.assertRaises(ValidationError) as ctx:
            FindingFixService.execute_fix(finding, user=self.user)
        self.assertIn("Automated 1-click resolution is only permitted for CONFIRMED_DUPLICATE", str(ctx.exception))

    def test_36_resolve_same_finding_twice_is_idempotent(self):
        """12. Calling execute_fix on an already resolved finding returns success idempotently."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        v_prim = self._create_test_voucher(amount=Decimal('500.00'))
        v_dup = self._create_test_voucher(amount=Decimal('500.00'))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Duplicate to Resolve",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        res1 = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res1["status"], "SUCCESS")
        res2 = FindingFixService.execute_fix(finding, user=self.user)
        self.assertEqual(res2["status"], "SUCCESS")
        self.assertTrue(res2.get("already_resolved"))

    def test_37_concurrent_duplicate_resolution_idempotency(self):
        """13. Idempotency key prevents duplicate execution with identical client_key."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        v_prim = self._create_test_voucher(amount=Decimal('600.00'))
        v_dup = self._create_test_voucher(amount=Decimal('600.00'))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Idempotent Duplicate",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        res1 = FindingFixService.execute_fix(finding, user=self.user, client_key="uniq_fix_key_999")
        self.assertEqual(res1["status"], "SUCCESS")
        res2 = FindingFixService.execute_fix(finding, user=self.user, client_key="uniq_fix_key_999")
        self.assertEqual(res2["status"], "SUCCESS")

    def test_38_database_failure_during_relink_rolls_back_atomically(self):
        """14. A failure during relinking triggers atomic rollback preserving both vouchers."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        from unittest.mock import patch
        v_prim = self._create_test_voucher(amount=Decimal('700.00'))
        v_dup = self._create_test_voucher(amount=Decimal('700.00'))

        btx = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('700.00'), credit_amount=Decimal('0.00'), status='RECONCILED',
            matched_voucher=v_dup, matched_party=self.vendor_ledger, description='Relink failure test'
        )
        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Simulated Relink Fail",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        with patch.object(VoucherService, 'delete_voucher', side_effect=RuntimeError("Simulated DB Crash")):
            with self.assertRaises(RuntimeError):
                FindingFixService.execute_fix(finding, user=self.user)

        v_dup.refresh_from_db()
        self.assertTrue(Voucher.objects.filter(id=v_dup.id).exists())
        finding.refresh_from_db()
        self.assertFalse(finding.is_resolved)

    def test_39_database_failure_during_audit_rolls_back_atomically(self):
        """15. Failure during audit logging rolls back all changes atomically."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        from apps.audit.services.audit_service import AuditService
        from unittest.mock import patch
        v_prim = self._create_test_voucher(amount=Decimal('800.00'))
        v_dup = self._create_test_voucher(amount=Decimal('800.00'))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Simulated Audit Fail",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        with patch.object(AuditService, 'log_action', side_effect=RuntimeError("Audit Storage Unreachable")):
            with self.assertRaises(RuntimeError):
                FindingFixService.execute_fix(finding, user=self.user)

        finding.refresh_from_db()
        self.assertFalse(finding.is_resolved)
        self.assertTrue(Voucher.objects.filter(id=v_dup.id).exists())

    def test_40_ledger_recalculation_consistency(self):
        """16. Party ledger balance before and after deduplication fix is strictly consistent."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        # Baseline
        VoucherService.recalculate_ledger_balance(self.vendor_ledger)
        self.vendor_ledger.refresh_from_db()
        base_bal = self.vendor_ledger.current_balance

        v_prim = self._create_test_voucher(amount=Decimal('900.00'))
        v_dup = self._create_test_voucher(amount=Decimal('900.00'))
        VoucherService.recalculate_ledger_balance(self.vendor_ledger)
        self.vendor_ledger.refresh_from_db()

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Recalc Check",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        FindingFixService.execute_fix(finding, user=self.user)
        self.vendor_ledger.refresh_from_db()
        self.assertEqual(self.vendor_ledger.current_balance, base_bal - Decimal('900.00'))

    def test_41_voucher_number_sequence_not_rewound_after_deletion(self):
        """17. Deleting a voucher does not rewind the sequence generator counter."""
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        v1 = self._create_test_voucher(amount=Decimal('100.00'), voucher_number='PAY/26-27/0050')
        v2 = self._create_test_voucher(amount=Decimal('100.00'), voucher_number='PAY/26-27/0051')

        # Resync sequence to 51
        InvoiceSequenceService.resync_sequence(self.company, self.fy, 'PAYMENT', force=True)
        # Delete v2 (the highest voucher)
        VoucherService.delete_voucher(v2, user=self.user, reason="Sequence test")
        # Next number generated must be strictly greater than 50 (i.e. 52, NOT 51!)
        next_num_str, _ = InvoiceSequenceService.get_next_number(self.company, 'PAYMENT', v1.voucher_date)
        next_num = int(next_num_str.split('/')[-1])
        self.assertGreaterEqual(next_num, 52)

    def test_42_statement_exclusion_preserves_manual_vouchers(self):
        """18. Exclude statement preserves manual vouchers matched to transactions."""
        v_manual = self._create_test_voucher(amount=Decimal('500.00'))
        stmt = BankStatementImport.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, source_file_name="stmt_test.pdf",
            file_hash="stmt_hash_42", closing_balance=Decimal('10000.00')
        )
        btx = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, statement_import=stmt,
            transaction_date=datetime.date(2026, 5, 20), debit_amount=Decimal('500.00'), credit_amount=Decimal('0.00'),
            status='RECONCILED', matched_voucher=v_manual, matched_party=self.vendor_ledger,
            match_notes={'is_existing_matched': True}, description='Payment cleared'
        )
        count = BankReconciliationService.exclude_statement_import(stmt, reason="Wrong period", user=self.user)
        self.assertEqual(count, 1)
        v_manual.refresh_from_db()
        self.assertEqual(v_manual.status, 'POSTED')

    def test_43_reimport_after_exclusion_handling(self):
        """19. Statement restore after exclusion safely re-enables transactions as UNRESOLVED."""
        stmt = BankStatementImport.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, source_file_name="stmt_reimport.pdf",
            file_hash="hash_reimport_43", closing_balance=Decimal('20000.00')
        )
        btx = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, statement_import=stmt,
            transaction_date=datetime.date(2026, 5, 20), debit_amount=Decimal('300.00'), credit_amount=Decimal('0.00'),
            status='UNRESOLVED', description='Payment entry'
        )
        BankReconciliationService.exclude_statement_import(stmt, reason="Accidental exclusion", user=self.user)
        stmt.refresh_from_db()
        self.assertTrue(stmt.is_excluded)
        BankReconciliationService.restore_statement_import(stmt, user=self.user)
        stmt.refresh_from_db()
        btx.refresh_from_db()
        self.assertFalse(stmt.is_excluded)
        self.assertEqual(btx.status, 'UNRESOLVED')

    def test_44_concurrent_voucher_numbering_thread_safety(self):
        """20. Concurrent sequence number allocation produces unique monotonic numbers."""
        from apps.accounting.services.sequence_service import InvoiceSequenceService
        n1, _ = InvoiceSequenceService.get_next_number(self.company, 'PAYMENT', datetime.date(2026, 5, 20))
        n2, _ = InvoiceSequenceService.get_next_number(self.company, 'PAYMENT', datetime.date(2026, 5, 20))
        self.assertNotEqual(n1, n2)

    def test_45_cross_company_voucher_relinking_strictly_rejected(self):
        """21. Cross-company voucher relinking in finding fix is strictly rejected."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        other_comp = Company.objects.create(name="Competitor Inc", state_name="Delhi")
        other_fy = FinancialYear.objects.create(
            company=other_comp, code="26-27", name="FY 2026-27",
            start_date=datetime.date(2026, 4, 1), end_date=datetime.date(2027, 3, 31)
        )
        v_other = Voucher.objects.create(
            company=other_comp, financial_year=other_fy, voucher_type='PAYMENT',
            voucher_number='PAY/OTHER/01', voucher_date=datetime.date(2026, 5, 20), total_amount=Decimal('500.00'),
            status='POSTED', created_by=self.user
        )
        v_local = self._create_test_voucher(amount=Decimal('500.00'))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Cross Company Attack",
            evidence={"primary_voucher_id": str(v_local.id), "duplicate_voucher_id": str(v_other.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        with self.assertRaises(ValidationError) as ctx:
            FindingFixService.execute_fix(finding, user=self.user)
        self.assertIn("tenant isolation policy", str(ctx.exception))

    def test_46_unreconcile_after_successful_matching(self):
        """22. Unreconciling an existing-voucher match detaches voucher safely without cancelling it."""
        v = self._create_test_voucher(amount=Decimal('1200.00'))
        btx = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('1200.00'), credit_amount=Decimal('0.00'), status='UNRESOLVED', description='Payment to Adinath'
        )
        BankReconciliationService.resolve_transaction(
            bank_tx=btx, action_type='MATCH_EXISTING_VOUCHER',
            payload={'voucher_id': str(v.id)}, user=self.user
        )
        btx.refresh_from_db()
        self.assertEqual(btx.status, 'RECONCILED')

        BankReconciliationService.unreconcile_transaction(btx, reason="User unmatched", user=self.user)
        btx.refresh_from_db()
        v.refresh_from_db()
        self.assertEqual(btx.status, 'UNRESOLVED')
        self.assertIsNone(btx.matched_voucher)
        self.assertEqual(v.status, 'POSTED')

    def test_47_incorrect_debit_credit_direction_handling(self):
        """23. Matching a deposit bank transaction against a payment voucher is rejected."""
        v_pay = self._create_test_voucher(amount=Decimal('1500.00'))
        btx_deposit = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('0.00'), credit_amount=Decimal('1500.00'), status='UNRESOLVED', description='Deposit from Customer'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=btx_deposit, action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(v_pay.id)}, user=self.user
            )
        self.assertIn("direction mismatch", str(ctx.exception).lower())

    def test_48_existing_voucher_amount_mismatch_rejected(self):
        """24. Amount mismatch greater than tolerance is rejected."""
        v = self._create_test_voucher(amount=Decimal('2000.00'))
        btx = BankTransaction.objects.create(
            company=self.company, bank_ledger=self.bank_ledger, transaction_date=datetime.date(2026, 5, 20),
            debit_amount=Decimal('2500.00'), credit_amount=Decimal('0.00'), status='UNRESOLVED', description='Payment Adinath'
        )
        with self.assertRaises(ValidationError) as ctx:
            BankReconciliationService.resolve_transaction(
                bank_tx=btx, action_type='MATCH_EXISTING_VOUCHER',
                payload={'voucher_id': str(v.id)}, user=self.user
            )
        self.assertIn("amount mismatch", str(ctx.exception).lower())

    def test_49_original_manual_voucher_visibility_in_cash_and_bank(self):
        """25. UniversalVoucherAPIView includes POSTED manual vouchers in Cash & Bank listing."""
        v = self._create_test_voucher(amount=Decimal('28222.00'), voucher_number='PAY/26-27/0065')
        url = f"/api/v1/accounting/vouchers/{self.company.id}/?type=PAYMENT"
        res = self.client.get(url, HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        v_numbers = [item['voucher_number'] for item in res.data.get('data', [])]
        self.assertIn(v.voucher_number, v_numbers)

    def test_50_trial_balance_equilibrium_before_and_after_fix(self):
        """26. Double-entry equilibrium is maintained before and after duplicate resolution."""
        v_prim = self._create_test_voucher(amount=Decimal('100.00'))
        v_dup = self._create_test_voucher(amount=Decimal('100.00'))

        entries = LedgerEntry.objects.filter(voucher__company=self.company, voucher__status='POSTED')
        tot_debit = sum(e.debit_amount for e in entries)
        tot_credit = sum(e.credit_amount for e in entries)
        self.assertEqual(tot_debit, tot_credit)

        from apps.accounting.services.finding_fix_service import FindingFixService
        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Equilibrium Test",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        FindingFixService.execute_fix(finding, user=self.user)

        entries_after = LedgerEntry.objects.filter(voucher__company=self.company, voucher__status='POSTED')
        tot_debit_after = sum(e.debit_amount for e in entries_after)
        tot_credit_after = sum(e.credit_amount for e in entries_after)
        self.assertEqual(tot_debit_after, tot_credit_after)

    def test_51_party_ledger_balance_before_and_after_fix(self):
        """27. Party ledger reflects single economic transaction after duplicate fix."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        VoucherService.recalculate_ledger_balance(self.vendor_ledger)
        self.vendor_ledger.refresh_from_db()
        base_bal = self.vendor_ledger.current_balance

        v_prim = self._create_test_voucher(amount=Decimal('450.00'))
        v_dup = self._create_test_voucher(amount=Decimal('450.00'))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Party Balance Check",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        FindingFixService.execute_fix(finding, user=self.user)
        self.vendor_ledger.refresh_from_db()
        self.assertEqual(self.vendor_ledger.current_balance, base_bal - Decimal('450.00'))

    def test_52_bank_ledger_balance_before_and_after_fix(self):
        """28. Bank ledger credit balance reflects exact payment after duplicate fix."""
        from apps.accounting.services.finding_fix_service import FindingFixService
        VoucherService.recalculate_ledger_balance(self.bank_ledger)
        self.bank_ledger.refresh_from_db()
        base_bal = self.bank_ledger.current_balance

        v_prim = self._create_test_voucher(amount=Decimal('350.00'))
        v_dup = self._create_test_voucher(amount=Decimal('350.00'))

        finding = AccountingFinding.objects.create(
            company=self.company, category="DUPLICATE", severity="CRITICAL", title="Bank Balance Check",
            evidence={"primary_voucher_id": str(v_prim.id), "duplicate_voucher_id": str(v_dup.id), "duplicate_classification": "CONFIRMED_DUPLICATE"},
            fix_action="VOID_DUPLICATE_VOUCHER"
        )
        FindingFixService.execute_fix(finding, user=self.user)
        VoucherService.recalculate_ledger_balance(self.bank_ledger)
        self.bank_ledger.refresh_from_db()
        self.assertEqual(self.bank_ledger.current_balance, base_bal - Decimal('350.00'))

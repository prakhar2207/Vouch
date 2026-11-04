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
    FinancialYear, Voucher, LedgerEntry, BankTransaction, BankStatementImport, PaymentAllocation, IdempotencyRecord
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

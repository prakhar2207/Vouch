import uuid
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import BankTransaction, Voucher, LedgerEntry
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService

class BankEvidencePreservationTests(TestCase):
    """
    Exhaustive regression test suite verifying DEFECT 1 remediation:
    Original bank evidence is preserved under all circumstances.
    Accounting interpretation is separated from imported source evidence.
    """
    def setUp(self):
        self.company_id = uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33')
        self.company, _ = Company.objects.get_or_create(
            id=self.company_id,
            defaults={'name': 'Apex Belting & Industrial Store (Demo)'}
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', "ABORT: Sandbox isolation invariant!"

        self.user, _ = User.objects.get_or_create(
            email='auditor@apexbelting.demo',
            defaults={'first_name': 'Audit', 'last_name': 'Tester'}
        )

        # Groups
        bank_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Bank Accounts', defaults={'nature': 'ASSET'})
        cust_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Sundry Debtors', defaults={'nature': 'ASSET'})
        supp_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Sundry Creditors', defaults={'nature': 'LIABILITY'})
        exp_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Indirect Expenses', defaults={'nature': 'EXPENSE'})

        # Ledgers
        self.bank_ledger, _ = Ledger.objects.get_or_create(
            company=self.company, name='Canara Bank OD',
            defaults={'group': bank_grp, 'ledger_type': 'BANK'}
        )
        self.customer, _ = Ledger.objects.get_or_create(
            company=self.company, name='Shiv Trading Co',
            defaults={'group': cust_grp, 'ledger_type': 'CUSTOMER'}
        )
        self.supplier, _ = Ledger.objects.get_or_create(
            company=self.company, name='Fenner India Ltd',
            defaults={'group': supp_grp, 'ledger_type': 'SUPPLIER'}
        )
        self.expense, _ = Ledger.objects.get_or_create(
            company=self.company, name='Bank Charges',
            defaults={'group': exp_grp, 'ledger_type': 'EXPENSE'}
        )

    def test_customer_payment_receipt_preserves_evidence(self):
        """Statement credit (Money IN) from customer -> Receipt voucher, original amounts intact."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=date(2026, 10, 20),
            description="UPI/CR/111032350168/Shiv Trading Co/RECEIPT",
            normalized_narration="SHIV TRADING CO",
            credit_amount=Decimal('15000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )
        # Check initial evidence preservation
        self.assertEqual(tx.raw_credit_amount, Decimal('15000.00'))
        self.assertEqual(tx.raw_debit_amount, Decimal('0.00'))

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_CUSTOMER_RECEIPT',
            payload={'party_id': str(self.customer.id)},
            user=self.user
        )
        self.assertEqual(res['status'], 'SUCCESS')

        tx.refresh_from_db()
        # Verify amounts WERE NOT MUTATED
        self.assertEqual(tx.credit_amount, Decimal('15000.00'))
        self.assertEqual(tx.debit_amount, Decimal('0.00'))
        self.assertEqual(tx.raw_credit_amount, Decimal('15000.00'))
        self.assertEqual(tx.raw_debit_amount, Decimal('0.00'))

        # Verify separate interpretation
        self.assertEqual(tx.status, 'RECONCILED')
        self.assertEqual(tx.user_classification, 'CUSTOMER_RECEIPT')
        self.assertFalse(tx.is_refund)
        self.assertEqual(tx.matched_voucher.voucher_type, 'RECEIPT')
        self.assertEqual(tx.matched_voucher.total_amount, Decimal('15000.00'))

    def test_customer_refund_preserves_evidence_without_flipping(self):
        """Statement debit (Money OUT) to customer -> Payment voucher (Refund), original amounts intact."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=date(2026, 10, 21),
            description="NEFT OUT/Shiv Trading Co/REFUND OVERPAYMENT",
            normalized_narration="SHIV TRADING CO REFUND",
            debit_amount=Decimal('4500.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_CUSTOMER_REFUND',
            payload={'party_id': str(self.customer.id)},
            user=self.user
        )
        self.assertEqual(res['status'], 'SUCCESS')

        tx.refresh_from_db()
        # ABSOLUTE INVARIANT: Debit amount must NOT be flipped or zeroed!
        self.assertEqual(tx.debit_amount, Decimal('4500.00'))
        self.assertEqual(tx.credit_amount, Decimal('0.00'))
        self.assertEqual(tx.raw_debit_amount, Decimal('4500.00'))

        # Verify separate interpretation
        self.assertEqual(tx.status, 'RECONCILED')
        self.assertEqual(tx.user_classification, 'CUSTOMER_REFUND')
        self.assertTrue(tx.is_refund)
        self.assertEqual(tx.matched_voucher.voucher_type, 'PAYMENT')
        self.assertEqual(tx.matched_voucher.total_amount, Decimal('4500.00'))

    def test_supplier_payment_preserves_evidence(self):
        """Statement debit (Money OUT) to supplier -> Payment voucher, original amounts intact."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=date(2026, 10, 22),
            description="RTGS DR/CNRBH00171484971/Fenner India Ltd",
            normalized_narration="FENNER INDIA LTD",
            debit_amount=Decimal('50000.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_SUPPLIER_PAYMENT',
            payload={'party_id': str(self.supplier.id)},
            user=self.user
        )
        self.assertEqual(res['status'], 'SUCCESS')

        tx.refresh_from_db()
        self.assertEqual(tx.debit_amount, Decimal('50000.00'))
        self.assertEqual(tx.credit_amount, Decimal('0.00'))
        self.assertEqual(tx.user_classification, 'SUPPLIER_PAYMENT')
        self.assertFalse(tx.is_refund)
        self.assertEqual(tx.matched_voucher.voucher_type, 'PAYMENT')

    def test_supplier_refund_preserves_evidence_without_flipping(self):
        """Statement credit (Money IN) from supplier -> Receipt voucher (Rebate/Recovery), original amounts intact."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=date(2026, 10, 23),
            description="NEFT CR/Fenner India Ltd/ANNUAL TURNOVER REBATE",
            normalized_narration="FENNER INDIA REBATE",
            credit_amount=Decimal('12000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_SUPPLIER_REFUND',
            payload={'party_id': str(self.supplier.id)},
            user=self.user
        )
        self.assertEqual(res['status'], 'SUCCESS')

        tx.refresh_from_db()
        # ABSOLUTE INVARIANT: Credit amount must NOT be zeroed or flipped to debit!
        self.assertEqual(tx.credit_amount, Decimal('12000.00'))
        self.assertEqual(tx.debit_amount, Decimal('0.00'))
        self.assertEqual(tx.user_classification, 'SUPPLIER_REFUND')
        self.assertTrue(tx.is_refund)
        self.assertEqual(tx.matched_voucher.voucher_type, 'RECEIPT')
        self.assertEqual(tx.matched_voucher.total_amount, Decimal('12000.00'))

    def test_unreconcile_transaction_workflow(self):
        """User can unreconcile a transaction; voucher is cancelled, evidence preserved, status reset."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=date(2026, 10, 24),
            description="CHQ 123456 PAYMENT TO SUPPLIER",
            debit_amount=Decimal('8000.00'),
            credit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )
        BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_SUPPLIER_PAYMENT',
            payload={'party_id': str(self.supplier.id)},
            user=self.user
        )
        tx.refresh_from_db()
        vch = tx.matched_voucher
        self.assertEqual(tx.status, 'RECONCILED')
        self.assertEqual(vch.status, 'POSTED')

        # Now unreconcile
        unrec_res = BankReconciliationService.unreconcile_transaction(
            bank_tx=tx,
            reason="Party was mistakenly matched",
            user=self.user
        )
        self.assertEqual(unrec_res['status'], 'SUCCESS')

        tx.refresh_from_db()
        vch.refresh_from_db()
        self.assertEqual(tx.status, 'UNRESOLVED')
        self.assertIsNone(tx.matched_voucher)
        self.assertEqual(vch.status, 'CANCELLED')
        # Original amounts must remain untouched!
        self.assertEqual(tx.debit_amount, Decimal('8000.00'))
        self.assertEqual(tx.credit_amount, Decimal('0.00'))
        self.assertEqual(tx.raw_debit_amount, Decimal('8000.00'))

        # Check interpretation history was recorded
        history = tx.match_notes.get('interpretation_history', [])
        self.assertTrue(any(h.get('action_type') == 'UNRECONCILE' for h in history))

    def test_repeated_reconciliation_idempotency(self):
        """Calling resolve on an already reconciled transaction returns existing outcome safely."""
        tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=date(2026, 10, 25),
            description="DEPOSIT FROM CUSTOMER",
            credit_amount=Decimal('5000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )
        res1 = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_CUSTOMER_RECEIPT',
            payload={'party_id': str(self.customer.id)},
            user=self.user
        )
        self.assertEqual(res1['status'], 'SUCCESS')

        # Second invocation
        res2 = BankReconciliationService.resolve_transaction(
            bank_tx=tx,
            action_type='CONFIRM_CUSTOMER_RECEIPT',
            payload={'party_id': str(self.customer.id)},
            user=self.user
        )
        self.assertEqual(res2['status'], 'SUCCESS')
        self.assertEqual(res1['voucher_id'], res2['voucher_id'])

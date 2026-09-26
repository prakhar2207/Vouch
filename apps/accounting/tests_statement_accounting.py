from decimal import Decimal
from django.test import TestCase
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.accounting.services.party_balance_service import PartyBalanceService
from apps.accounting.services.voucher_service import VoucherService

class StatementAccountingRegressionTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(email='satyam@example.com', password='password')
        self.company = Company.objects.create(name='Vouch Books')
        UserCompany.objects.create(company=self.company, user=self.user, role='OWNER')
        
        self.sundry_creditors = LedgerGroup.objects.create(
            name="Sundry Creditors", company=self.company, nature="LIABILITY"
        )
        self.sundry_debtors = LedgerGroup.objects.create(
            name="Sundry Debtors", company=self.company, nature="ASSET"
        )
        self.cash = LedgerGroup.objects.create(
            name="Cash-in-hand", company=self.company, nature="ASSET"
        )
        self.purchase_ac = LedgerGroup.objects.create(
            name="Purchase Accounts", company=self.company, nature="EXPENSE"
        )
        self.sales_ac = LedgerGroup.objects.create(
            name="Sales Accounts", company=self.company, nature="INCOME"
        )

        self.cash_ledger = Ledger.objects.create(
            name="Cash", group=self.cash, company=self.company, ledger_type="CASH"
        )
        self.purchase_ledger = Ledger.objects.create(
            name="Purchase", group=self.purchase_ac, company=self.company, ledger_type="PURCHASE"
        )
        self.sales_ledger = Ledger.objects.create(
            name="Sales", group=self.sales_ac, company=self.company, ledger_type="SALES"
        )

    def _post_voucher(self, v_type, party, amount):
        from datetime import date
        v = Voucher.objects.create(
            company=self.company,
            created_by=self.user,
            voucher_type=v_type,
            party_ledger=party,
            total_amount=amount,
            voucher_date=date.today(),
            status='DRAFT'
        )
        # Simplify entries directly for testing
        v.status = 'POSTED'
        v.save()
        
        if v_type == 'PURCHASE':
            # Purchase: Dr Purchase, Cr Supplier
            LedgerEntry.objects.create(voucher=v, ledger=self.purchase_ledger, debit_amount=amount)
            LedgerEntry.objects.create(voucher=v, ledger=party, credit_amount=amount)
        elif v_type == 'PAYMENT':
            # Payment: Dr Supplier, Cr Cash
            LedgerEntry.objects.create(voucher=v, ledger=party, debit_amount=amount)
            LedgerEntry.objects.create(voucher=v, ledger=self.cash_ledger, credit_amount=amount)
        elif v_type == 'SALES':
            # Sales: Dr Customer, Cr Sales
            LedgerEntry.objects.create(voucher=v, ledger=party, debit_amount=amount)
            LedgerEntry.objects.create(voucher=v, ledger=self.sales_ledger, credit_amount=amount)
        elif v_type == 'RECEIPT':
            # Receipt: Dr Cash, Cr Customer
            LedgerEntry.objects.create(voucher=v, ledger=self.cash_ledger, debit_amount=amount)
            LedgerEntry.objects.create(voucher=v, ledger=party, credit_amount=amount)
            
        VoucherService.recalculate_ledger_balance(party)

    def test_supplier_to_pay(self):
        supplier = Ledger.objects.create(
            name="Supplier To Pay", group=self.sundry_creditors, company=self.company, ledger_type="SUPPLIER"
        )
        self._post_voucher('PURCHASE', supplier, Decimal('173362.12'))
        self._post_voucher('PAYMENT', supplier, Decimal('105000.00'))
        
        supplier.refresh_from_db()
        bal_info = PartyBalanceService.get_party_balance(supplier)
        
        self.assertEqual(bal_info['signed_balance'], Decimal('68362.12'))
        self.assertEqual(bal_info['display_amount'], Decimal('68362.12'))
        self.assertEqual(bal_info['balance_state'], 'TO_PAY')

    def test_supplier_advance_paid(self):
        supplier = Ledger.objects.create(
            name="Supplier Advance", group=self.sundry_creditors, company=self.company, ledger_type="SUPPLIER"
        )
        self._post_voucher('PAYMENT', supplier, Decimal('50000.00'))
        
        supplier.refresh_from_db()
        bal_info = PartyBalanceService.get_party_balance(supplier)
        
        self.assertEqual(bal_info['signed_balance'], Decimal('-50000.00'))
        self.assertEqual(bal_info['balance_state'], 'ADVANCE_PAID')

    def test_customer_to_collect(self):
        customer = Ledger.objects.create(
            name="Customer To Collect", group=self.sundry_debtors, company=self.company, ledger_type="CUSTOMER"
        )
        self._post_voucher('SALES', customer, Decimal('100000.00'))
        self._post_voucher('RECEIPT', customer, Decimal('25000.00'))
        
        customer.refresh_from_db()
        bal_info = PartyBalanceService.get_party_balance(customer)
        
        self.assertEqual(bal_info['signed_balance'], Decimal('75000.00'))
        self.assertEqual(bal_info['balance_state'], 'TO_COLLECT')

    def test_customer_advance_received(self):
        customer = Ledger.objects.create(
            name="Customer Advance", group=self.sundry_debtors, company=self.company, ledger_type="CUSTOMER"
        )
        self._post_voucher('RECEIPT', customer, Decimal('50000.00'))
        
        customer.refresh_from_db()
        bal_info = PartyBalanceService.get_party_balance(customer)
        
        self.assertEqual(bal_info['signed_balance'], Decimal('-50000.00'))
        self.assertEqual(bal_info['balance_state'], 'ADVANCE_RECEIVED')

    def test_settled_balance(self):
        customer = Ledger.objects.create(
            name="Settled Customer", group=self.sundry_debtors, company=self.company, ledger_type="CUSTOMER"
        )
        self._post_voucher('SALES', customer, Decimal('10000.00'))
        self._post_voucher('RECEIPT', customer, Decimal('10000.00'))
        
        customer.refresh_from_db()
        bal_info = PartyBalanceService.get_party_balance(customer)
        
        self.assertEqual(bal_info['signed_balance'], Decimal('0.00'))
        self.assertEqual(bal_info['balance_state'], 'SETTLED')

    def test_statement_api_response_contract(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.user)
        
        supplier = Ledger.objects.create(
            name="Statement Supplier", group=self.sundry_creditors, company=self.company, ledger_type="SUPPLIER"
        )
        self._post_voucher('PURCHASE', supplier, Decimal('173362.12'))
        self._post_voucher('PAYMENT', supplier, Decimal('105000.00'))
        
        response = client.get(f'/api/v1/accounting/reports/ledger-statement/{self.company.id}/{supplier.id}/')
        self.assertEqual(response.status_code, 200)
        json_resp = response.json()
        self.assertTrue(json_resp['success'])
        data = json_resp['data']
        
        self.assertIn('closing_balance', data)
        self.assertEqual(data['closing_balance'], '68362.12')
        self.assertEqual(data['closing_balance_type'], 'CREDIT')
        self.assertEqual(data['semantic_state'], 'TO_PAY')
        self.assertEqual(data['display_amount'], '68362.12')
        self.assertEqual(data['period_debit'], '105000.00')
        self.assertEqual(data['period_credit'], '173362.12')

    def test_banking_refund_preservation(self):
        from apps.accounting.models import BankTransaction
        from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
        from datetime import date

        bank_group = LedgerGroup.objects.create(name="Bank Accounts", company=self.company, nature="ASSET")
        bank_ledger = Ledger.objects.create(name="HDFC Bank", group=bank_group, company=self.company, ledger_type="BANK")
        supplier = Ledger.objects.create(name="Refund Supplier", group=self.sundry_creditors, company=self.company, ledger_type="SUPPLIER")

        # Deposit into bank from supplier (supplier refund)
        # In bank statement: Deposit = Credit on bank passbook
        bank_tx = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=bank_ledger,
            transaction_date=date.today(),
            description="REFUND FROM SUPPLIER XYZ",
            credit_amount=Decimal('5000.00'),
            debit_amount=Decimal('0.00'),
            status='UNRESOLVED'
        )

        res = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type='CONFIRM_RECEIPT',
            payload={'party_id': str(supplier.id)},
            user=self.user
        )

        bank_tx.refresh_from_db()
        # Ensure bank statement facts were NOT mutated/flipped
        self.assertEqual(bank_tx.credit_amount, Decimal('5000.00'))
        self.assertEqual(bank_tx.debit_amount, Decimal('0.00'))
        self.assertEqual(bank_tx.status, 'RECONCILED')

        voucher = bank_tx.matched_voucher
        self.assertEqual(voucher.voucher_type, 'RECEIPT')
        self.assertEqual(voucher.party_ledger, supplier)
        # Bank debited (asset increase), Supplier credited (liability decrease / refund)
        bank_entry = voucher.ledger_entries.get(ledger=bank_ledger)
        supplier_entry = voucher.ledger_entries.get(ledger=supplier)
        self.assertEqual(bank_entry.debit_amount, Decimal('5000.00'))
        self.assertEqual(supplier_entry.credit_amount, Decimal('5000.00'))

    def test_health_checks_contract(self):
        from apps.accounting.services.integrity_engine import AccountingIntegrityEngine
        report = AccountingIntegrityEngine.run_all_checks(self.company)

        self.assertIn('health_score', report)
        self.assertIn('health_status', report)
        self.assertIn('checks', report)
        self.assertEqual(len(report['checks']), 10)

        for check in report['checks']:
            self.assertIn('name', check)
            self.assertIn('category', check)
            self.assertIn('status', check)
            self.assertIn('severity', check)
            self.assertIn('findings_count', check)
            self.assertIn('description', check)
            self.assertIn('passed', check)
            self.assertIn(check['status'], ['PASSED', 'WARNING', 'CRITICAL'])
            self.assertEqual(check['passed'], check['status'] == 'PASSED')


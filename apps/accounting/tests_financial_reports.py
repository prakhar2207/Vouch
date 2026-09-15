from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear, BankTransaction
from apps.accounting.services.financial_statements_service import FinancialStatementsService

class FinancialStatementsAndBulkResolveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='accountant@example.com', password='password123')
        self.company = Company.objects.create(name='Test Corp Pvt Ltd', pan='AAACT1234F')
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.fy = FinancialYear.objects.create(
            company=self.company,
            name='FY 2026-27',
            code='26-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_closed=False
        )

        # Groups
        self.grp_sales = LedgerGroup.objects.create(company=self.company, name='Sales Accounts', nature='INCOME')
        self.grp_purchases = LedgerGroup.objects.create(company=self.company, name='Purchase Accounts', nature='EXPENSE')
        self.grp_direct_exp = LedgerGroup.objects.create(company=self.company, name='Direct Expenses', nature='EXPENSE')
        self.grp_indirect_exp = LedgerGroup.objects.create(company=self.company, name='Indirect Expenses', nature='EXPENSE')
        self.grp_capital = LedgerGroup.objects.create(company=self.company, name='Capital Account', nature='EQUITY')
        self.grp_bank = LedgerGroup.objects.create(company=self.company, name='Bank Accounts', nature='ASSET')
        self.grp_debtors = LedgerGroup.objects.create(company=self.company, name='Sundry Debtors', nature='ASSET')

        # Ledgers
        self.led_sales = Ledger.objects.create(company=self.company, group=self.grp_sales, name='Sales GST 18%', ledger_type='SALES')
        self.led_purchase = Ledger.objects.create(company=self.company, group=self.grp_purchases, name='Purchase GST 18%', ledger_type='PURCHASE')
        self.led_rent = Ledger.objects.create(company=self.company, group=self.grp_indirect_exp, name='Office Rent', ledger_type='EXPENSE')
        self.led_capital = Ledger.objects.create(company=self.company, group=self.grp_capital, name='Promoter Capital', ledger_type='GENERAL', opening_balance=Decimal('50000.00'), opening_balance_type='CREDIT')
        self.led_bank = Ledger.objects.create(company=self.company, group=self.grp_bank, name='HDFC Bank', ledger_type='BANK', opening_balance=Decimal('50000.00'), opening_balance_type='DEBIT')
        self.led_customer = Ledger.objects.create(company=self.company, group=self.grp_debtors, name='Customer Alpha', ledger_type='CUSTOMER')

    def test_01_profit_and_loss_calculation(self):
        # Create Sales Voucher (Dr Customer 10,000, Cr Sales 10,000)
        v_sale = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type='SALES',
            voucher_number='INV-001', voucher_date='2026-05-10', status='POSTED',
            total_amount=Decimal('10000.00'), created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_sale, ledger=self.led_customer, debit_amount=Decimal('10000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_sale, ledger=self.led_sales, debit_amount=Decimal('0.00'), credit_amount=Decimal('10000.00'))

        # Create Purchase Voucher (Dr Purchase 6,000, Cr Bank 6,000)
        v_pur = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type='PURCHASE',
            voucher_number='PUR-001', voucher_date='2026-05-12', status='POSTED',
            total_amount=Decimal('6000.00'), created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_pur, ledger=self.led_purchase, debit_amount=Decimal('6000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_pur, ledger=self.led_bank, debit_amount=Decimal('0.00'), credit_amount=Decimal('6000.00'))

        # Create Rent Expense Voucher (Dr Rent 1,500, Cr Bank 1,500)
        v_exp = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type='PAYMENT',
            voucher_number='PAY-001', voucher_date='2026-05-15', status='POSTED',
            total_amount=Decimal('1500.00'), created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_exp, ledger=self.led_rent, debit_amount=Decimal('1500.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_exp, ledger=self.led_bank, debit_amount=Decimal('0.00'), credit_amount=Decimal('1500.00'))

        pl = FinancialStatementsService.generate_profit_and_loss(self.company, '2026-04-01', '2026-05-31')
        self.assertEqual(Decimal(pl['trading_account']['direct_income']['total']), Decimal('10000.00'))
        self.assertEqual(Decimal(pl['trading_account']['direct_expense']['total']), Decimal('6000.00'))
        self.assertEqual(Decimal(pl['trading_account']['gross_profit']), Decimal('4000.00'))
        self.assertEqual(Decimal(pl['profit_and_loss']['indirect_expense']['total']), Decimal('1500.00'))
        self.assertEqual(Decimal(pl['profit_and_loss']['net_profit']), Decimal('2500.00'))

    def test_02_balance_sheet_equilibrium(self):
        # Create Sales (Dr Customer 10,000, Cr Sales 10,000)
        v_sale = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type='SALES',
            voucher_number='INV-002', voucher_date='2026-05-10', status='POSTED',
            total_amount=Decimal('10000.00'), created_by=self.user
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_sale, ledger=self.led_customer, debit_amount=Decimal('10000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_sale, ledger=self.led_sales, debit_amount=Decimal('0.00'), credit_amount=Decimal('10000.00'))

        bs = FinancialStatementsService.generate_balance_sheet(self.company, '2026-05-31')
        self.assertTrue(bs['is_balanced'])
        self.assertEqual(Decimal(bs['difference']), Decimal('0.00'))

    def test_03_financial_reports_api_views(self):
        # P&L endpoint
        url_pl = reverse('profit_and_loss_report_company', kwargs={'company_id': self.company.id})
        res_pl = self.client.get(url_pl)
        self.assertEqual(res_pl.status_code, status.HTTP_200_OK)
        self.assertTrue(res_pl.data['success'])

        # Balance Sheet endpoint
        url_bs = reverse('balance_sheet_report_company', kwargs={'company_id': self.company.id})
        res_bs = self.client.get(url_bs)
        self.assertEqual(res_bs.status_code, status.HTTP_200_OK)
        self.assertTrue(res_bs.data['success'])

    def test_04_bulk_bank_reconcile_api(self):
        # Create bank transaction with high confidence match
        tx1 = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.led_bank,
            transaction_date='2026-05-20',
            description='UPI/Ranju/Payment',
            credit_amount=Decimal('500.00'),
            matched_party=self.led_customer,
            match_confidence=0.95,
            status='NEEDS_REVIEW'
        )
        tx2 = BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.led_bank,
            transaction_date='2026-05-21',
            description='Bank Interest Capitalized',
            debit_amount=Decimal('50.00'),
            matched_party=self.led_rent,
            match_confidence=0.90,
            status='NEEDS_REVIEW'
        )

        url = reverse('banking_transaction_bulk_resolve')
        res = self.client.post(url, {
            'min_confidence': 85
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['resolved_count'], 2)
        tx1.refresh_from_db()
        tx2.refresh_from_db()
        self.assertEqual(tx1.status, 'RECONCILED')
        self.assertEqual(tx2.status, 'RECONCILED')

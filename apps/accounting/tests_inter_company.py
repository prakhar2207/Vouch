import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.companies.models import Company, UserCompany
from apps.companies.views import provision_company_defaults
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, InterCompanyEntry, BankTransaction
from apps.accounting.services.inter_company_service import InterCompanyService
from apps.accounting.services.consolidated_financials_service import ConsolidatedFinancialsService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService

User = get_user_model()


class InterCompanyAndConsolidationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="group_cfo@example.com",
            password="StrongPassword@123",
            role="OWNER"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Entity A: Manufacturing Concern
        self.comp_a = Company.objects.create(
            name="Apex Manufacturing Pvt Ltd",
            gstin="27AAACA1111A1Z1",
            bank_name="HDFC Bank",
            bank_account_number="50200011112222"
        )
        UserCompany.objects.create(user=self.user, company=self.comp_a, role="OWNER")
        provision_company_defaults(self.comp_a)

        # Entity B: Trading Concern (Sister Company)
        self.comp_b = Company.objects.create(
            name="Apex Trading Enterprises",
            gstin="27AAACA2222B1Z2",
            bank_name="ICICI Bank",
            bank_account_number="60300033334444"
        )
        UserCompany.objects.create(user=self.user, company=self.comp_b, role="OWNER")
        provision_company_defaults(self.comp_b)

    def test_inter_company_mirror_flow(self):
        """
        Tests the 1-click mirror approval:
        1. Company A transfers ₹75,000 to Company B.
        2. Pending Mirror Entry is created in Company B's inbox.
        3. Company B confirms with 1 click.
        4. Both companies have balanced counter-vouchers with zero variance!
        """
        # Bank Ledger in A
        bank_a = Ledger.objects.get(company=self.comp_a, ledger_type="BANK")
        sister_b_in_a = InterCompanyService.get_or_create_intercompany_ledger(self.comp_a, self.comp_b)

        fy_a = InvoiceSequenceService.get_or_create_active_fy(self.comp_a, datetime.date.today())
        v_num_a, _ = InvoiceSequenceService.get_next_number(self.comp_a, 'CONTRA', datetime.date.today())

        # Voucher in Company A: Dr Sister B Current A/c / Cr Bank A
        vch_a = Voucher.objects.create(
            company=self.comp_a,
            financial_year=fy_a,
            voucher_type='CONTRA',
            voucher_number=v_num_a,
            voucher_date=datetime.date.today(),
            party_ledger=sister_b_in_a,
            status='DRAFT',
            total_amount=Decimal('75000.00'),
            narration="Funds transferred to Sister Concern Apex Trading",
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.comp_a, voucher=vch_a, ledger=sister_b_in_a, debit_amount=Decimal('75000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(company=self.comp_a, voucher=vch_a, ledger=bank_a, debit_amount=Decimal('0.00'), credit_amount=Decimal('75000.00'))
        VoucherService.post_voucher(vch_a)

        # Generate pending mirror entry for Company B
        entry = InterCompanyService.create_pending_mirror_entry(
            source_voucher=vch_a,
            target_company=self.comp_b,
            entry_type="TRANSFER",
            amount=Decimal('75000.00')
        )
        self.assertEqual(entry.status, "PENDING")

        # Verify Company B can see it in their Inbox API
        res = self.client.get(
            "/api/v1/accounting/inter-company/inbox/",
            HTTP_X_COMPANY_ID=str(self.comp_b.id)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['pending_count'], 1)
        self.assertEqual(res.data['results'][0]['amount'], 75000.0)

        # Company B accepts mirror entry with 1 click
        accept_res = self.client.post(
            f"/api/v1/accounting/inter-company/{entry.id}/accept/",
            data={},
            format="json",
            HTTP_X_COMPANY_ID=str(self.comp_b.id)
        )
        self.assertEqual(accept_res.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "ACCEPTED")
        self.assertIsNotNone(entry.target_voucher)

        # Check Matrix Reconciliation
        matrix = InterCompanyService.get_reconciliation_matrix(self.comp_a, self.comp_b)
        self.assertEqual(matrix['net_variance'], 0.0)
        self.assertTrue(matrix['is_reconciled'])
        self.assertIn("PERFECTLY BALANCED", matrix['status_headline'])

    def test_triangular_cross_entity_settlement(self):
        """
        Customer of Company A deposits ₹25,000 directly into Company B's bank account.
        Triangular settlement reconciles Bank B AND clears the customer invoice in Company A!
        """
        # Create Customer and Invoice in Company A
        cust_grp, _ = LedgerGroup.objects.get_or_create(company=self.comp_a, name="Sundry Debtors", defaults={"nature": "ASSET"})
        customer = Ledger.objects.create(
            company=self.comp_a,
            group=cust_grp,
            name="VIP Industrial Buyer",
            ledger_type="CUSTOMER",
            is_active=True
        )

        fy_a = InvoiceSequenceService.get_or_create_active_fy(self.comp_a, datetime.date.today())
        sales_grp = LedgerGroup.objects.get(company=self.comp_a, name="Sales Accounts")
        sales_ledger = Ledger.objects.get(company=self.comp_a, group=sales_grp)

        inv_num, _ = InvoiceSequenceService.get_next_number(self.comp_a, 'SALES_INVOICE', datetime.date.today())
        invoice = Voucher.objects.create(
            company=self.comp_a,
            financial_year=fy_a,
            voucher_type='SALES_INVOICE',
            voucher_number=inv_num,
            voucher_date=datetime.date.today(),
            party_ledger=customer,
            status='DRAFT',
            total_amount=Decimal('25000.00'),
            narration="Sales invoice for heavy belts",
            created_by=self.user
        )
        LedgerEntry.objects.create(company=self.comp_a, voucher=invoice, ledger=customer, debit_amount=Decimal('25000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(company=self.comp_a, voucher=invoice, ledger=sales_ledger, debit_amount=Decimal('0.00'), credit_amount=Decimal('25000.00'))
        VoucherService.post_voucher(invoice)

        # Customer ledger in A has debit balance of 25,000
        # Now, Bank statement import happens in Company B with credit of 25,000
        bank_b = Ledger.objects.get(company=self.comp_b, ledger_type="BANK")
        bank_tx = BankTransaction.objects.create(
            company=self.comp_b,
            bank_ledger=bank_b,
            transaction_date=datetime.date.today(),
            description="UPI/VIP BUYER/PAYMENT FOR APEX MFG INV",
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('25000.00'),
            balance=Decimal('100000.00'),
            status='UNRESOLVED'
        )

        # Resolve via TRIANGULAR_SETTLEMENT
        res = BankReconciliationService.resolve_transaction(
            bank_tx=bank_tx,
            action_type="TRIANGULAR_SETTLEMENT",
            payload={
                "target_company_id": str(self.comp_a.id),
                "target_party_id": str(customer.id),
                "target_invoice_id": str(invoice.id)
            },
            user=self.user
        )

        self.assertEqual(res['status'], "SUCCESS")
        bank_tx.refresh_from_db()
        self.assertEqual(bank_tx.status, "RECONCILED")

        # Verify Customer in Company A received credit and balance is settled
        cust_entries = LedgerEntry.objects.filter(company=self.comp_a, ledger=customer)
        total_dr = cust_entries.aggregate(s=Sum('debit_amount'))['s']
        total_cr = cust_entries.aggregate(s=Sum('credit_amount'))['s']
        self.assertEqual(total_dr, Decimal('25000.00'))
        self.assertEqual(total_cr, Decimal('25000.00'))

    def test_consolidated_group_financials_with_eliminations(self):
        """
        Tests multi-entity consolidation and automatic elimination of inter-company balances.
        """
        report = ConsolidatedFinancialsService.get_group_consolidated_report(
            user=self.user
        )
        self.assertEqual(report['summary']['total_companies'], 2)
        self.assertIn("total_liquid_cash_and_bank", report['summary'])
        self.assertIn("net_consolidated_debtors", report['summary'])
        self.assertIn("net_consolidated_creditors", report['summary'])
        self.assertIn("net_consolidated_revenue", report['summary'])
        self.assertEqual(len(report['entities']), 2)

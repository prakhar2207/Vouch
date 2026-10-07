import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.accounting.models import Voucher, LedgerEntry, BankTransaction, BankStatementImport, FinancialYear
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.advance_receipt_service import AdvanceReceiptService
from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
from apps.gst.services.gstr_report_service import GSTRReportService

User = get_user_model()


class AccountingPhase2MaturityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Horizon Renewable Energy Ltd",
            gstin="07AAACH1234H1Z8",
            state_code="07"
        )
        self.user = User.objects.create_user(
            email="finance_controller@horizon.com",
            password="StrongPassword987!"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        # Ledger Groups
        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Current Assets", nature="ASSET")
        self.liab_grp = LedgerGroup.objects.create(company=self.company, name="Current Liabilities", nature="LIABILITY")
        self.tax_grp = LedgerGroup.objects.create(company=self.company, name="Duties & Taxes", nature="LIABILITY")
        self.income_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")

        # Master Ledgers
        self.bank_ledger = Ledger.objects.create(
            company=self.company,
            name="HDFC Current Account",
            group=self.asset_grp,
            ledger_type="BANK",
            bank_account_number="50200012345678",
            opening_balance=Decimal("50000.00"),
            opening_balance_type="DEBIT",
            current_balance=Decimal("50000.00")
        )

        self.customer = Ledger.objects.create(
            company=self.company,
            name="Delhi Power Distribution Corp",
            group=self.asset_grp,
            ledger_type="CUSTOMER",
            state_code="07", # Intra-state (same as company 07)
            gstin="07AAACD9999D1Z2"
        )

        self.sales_ac = Ledger.objects.create(
            company=self.company,
            name="Solar Equipment Sales",
            group=self.income_grp,
            ledger_type="SALES"
        )

        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
            is_closed=False
        )

    def test_create_advance_receipt_double_entry_and_gst_liability(self):
        """
        Verify creation of GST Advance Receipt (Rule 50 / Section 31(3)(d)):
        - Advance received: ₹1,18,000 (tax rate 18%)
        - Intra-state (07 -> 07):
          Taxable Base = (1,18,000 * 100) / 118 = ₹1,00,000
          CGST (9%) = ₹9,000
          SGST (9%) = ₹9,000
        - Double Entry:
          Debit: Bank Ledger ₹1,18,000
          Credit: Customer Party ₹1,18,000
        - Total Dr == Total Cr.
        """
        v_date = datetime.date(2026, 7, 5)
        adv_v = AdvanceReceiptService.create_advance_receipt(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            bank_ledger=self.bank_ledger,
            amount=Decimal("118000.00"),
            tax_rate=Decimal("18.00"),
            voucher_date=v_date,
            narration="Advance for Solar Inverter Project"
        )

        self.assertEqual(adv_v.status, 'POSTED')
        self.assertTrue(adv_v.is_advance)
        self.assertEqual(adv_v.advance_tax_rate, Decimal("18.00"))
        self.assertEqual(adv_v.advance_tax_amount, Decimal("18000.00"))
        self.assertEqual(adv_v.advance_cgst, Decimal("9000.00"))
        self.assertEqual(adv_v.advance_sgst, Decimal("9000.00"))
        self.assertEqual(adv_v.advance_igst, Decimal("0.00"))
        self.assertEqual(adv_v.advance_adjusted_amount, Decimal("0.00"))

        entries = list(adv_v.ledger_entries.all())
        self.assertEqual(len(entries), 2)
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, total_cr)
        self.assertEqual(total_dr, Decimal("118000.00"))

    def test_advance_adjustment_against_invoice(self):
        """
        Verify partial adjustment of advance receipt against a subsequently posted Sales invoice.
        """
        # 1. Advance receipt of ₹1,18,000 (Tax ₹18,000)
        adv_v = AdvanceReceiptService.create_advance_receipt(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            bank_ledger=self.bank_ledger,
            amount=Decimal("118000.00"),
            tax_rate=Decimal("18.00"),
            voucher_date=datetime.date(2026, 7, 5)
        )

        # 2. Sales Invoice of ₹1,18,000
        inv_v = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='SALES',
            voucher_number='INV-SOLAR-01',
            voucher_date=datetime.date(2026, 7, 20),
            party_ledger=self.customer,
            status='DRAFT',
            total_amount=Decimal('118000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=inv_v, ledger=self.customer, debit_amount=Decimal('118000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=inv_v, ledger=self.sales_ac, debit_amount=Decimal('0.00'), credit_amount=Decimal('118000.00'))
        VoucherService.post_voucher(inv_v)

        # 3. Adjust ₹59,000 (50% of advance) against the invoice
        alloc = AdvanceReceiptService.adjust_advance_against_invoice(
            advance_voucher=adv_v,
            invoice_voucher=inv_v,
            allocated_amount=Decimal("59000.00")
        )

        self.assertEqual(alloc.allocated_amount, Decimal("59000.00"))
        # 50% of ₹18,000 advance tax = ₹9,000 adjusted
        self.assertEqual(alloc.adjusted_advance_tax, Decimal("9000.00"))

        adv_v.refresh_from_db()
        self.assertEqual(adv_v.advance_adjusted_amount, Decimal("59000.00"))

        # 4. Attempt to over-adjust (remaining unadjusted is ₹59,000; attempting ₹60,000 should raise ValidationError)
        with self.assertRaises(ValidationError) as ctx:
            AdvanceReceiptService.adjust_advance_against_invoice(
                advance_voucher=adv_v,
                invoice_voucher=inv_v,
                allocated_amount=Decimal("60000.00")
            )
        self.assertIn("unadjusted advance remains", str(ctx.exception))

    def test_gstr1_table_11a_and_11b_reporting(self):
        """
        Verify that GSTR-1 populates Table 11A (advances received) and Table 11B (advances adjusted).
        """
        # Create advance receipt in July
        adv_v = AdvanceReceiptService.create_advance_receipt(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            bank_ledger=self.bank_ledger,
            amount=Decimal("118000.00"),
            tax_rate=Decimal("18.00"),
            voucher_date=datetime.date(2026, 7, 10)
        )

        # Sales invoice in July
        inv_v = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='SALES',
            voucher_number='INV-SOLAR-02',
            voucher_date=datetime.date(2026, 7, 25),
            party_ledger=self.customer,
            status='DRAFT',
            total_amount=Decimal('118000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=inv_v, ledger=self.customer, debit_amount=Decimal('118000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=inv_v, ledger=self.sales_ac, debit_amount=Decimal('0.00'), credit_amount=Decimal('118000.00'))
        VoucherService.post_voucher(inv_v)

        # Adjust advance in July
        AdvanceReceiptService.adjust_advance_against_invoice(
            advance_voucher=adv_v,
            invoice_voucher=inv_v,
            allocated_amount=Decimal("59000.00")
        )

        gstr1 = GSTRReportService.generate_gstr1(self.company, "2026-07-01", "2026-07-31")

        # Table 11A check
        self.assertIn("at", gstr1)
        self.assertTrue(len(gstr1["at"]) > 0)
        table_11a_item = gstr1["at"][0]["itms"][0]
        self.assertEqual(table_11a_item["ad_amt"], 118000.0)
        self.assertEqual(table_11a_item["camt"], 9000.0)
        self.assertEqual(table_11a_item["samt"], 9000.0)

        # Table 11B check
        self.assertIn("atadj", gstr1)
        self.assertTrue(len(gstr1["atadj"]) > 0)
        table_11b_item = gstr1["atadj"][0]["itms"][0]
        self.assertEqual(table_11b_item["ad_amt"], 59000.0)
        self.assertEqual(table_11b_item["camt"], 4500.0)
        self.assertEqual(table_11b_item["samt"], 4500.0)

    def test_statutory_bank_reconciliation_statement_perfect_balance(self):
        """
        Verify Classical 2-Column Statutory Bank Reconciliation Statement (BRS):
        - Book Ledger Balance:
          Opening: ₹50,000
          Cheque Issued (Unpresented Payment): ₹10,000 (Cr)
          Cheque Deposited (Uncleared Deposit): ₹15,000 (Dr)
          Book Ledger Balance = ₹55,000
        - Bank Statement:
          Direct Credit (Unrecorded Credit): ₹500
          Bank Charges (Unrecorded Debit): ₹200
        - Formula:
          Reconciled Balance = Book Balance (₹55,000)
                              + Unpresented Payments (₹10,000)
                              + Unrecorded Credits (₹500)
                              - Uncleared Deposits (₹15,000)
                              - Unrecorded Debits (₹200)
                              = ₹50,300
        - When actual statement balance is ₹50,300, variance must be ₹0.00 and status PERFECTLY_RECONCILED.
        """
        as_of = datetime.date(2026, 7, 31)

        # 1. Unpresented payment in books (Cheque issued to supplier)
        v_pay = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='PAYMENT',
            voucher_number='PAY-CHQ-01',
            voucher_date=datetime.date(2026, 7, 15),
            status='DRAFT',
            total_amount=Decimal('10000.00'),
            created_by=self.user,
            narration="Cheque issued to Vendor X"
        )
        LedgerEntry.objects.create(voucher=v_pay, ledger=self.sales_ac, debit_amount=Decimal('10000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=v_pay, ledger=self.bank_ledger, debit_amount=Decimal('0.00'), credit_amount=Decimal('10000.00'))
        VoucherService.post_voucher(v_pay)

        # 2. Uncleared deposit in books (Cheque deposited from customer)
        v_rec = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='RECEIPT',
            voucher_number='REC-CHQ-02',
            voucher_date=datetime.date(2026, 7, 18),
            status='DRAFT',
            total_amount=Decimal('15000.00'),
            created_by=self.user,
            narration="Cheque received from Customer Y"
        )
        LedgerEntry.objects.create(voucher=v_rec, ledger=self.bank_ledger, debit_amount=Decimal('15000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=v_rec, ledger=self.customer, debit_amount=Decimal('0.00'), credit_amount=Decimal('15000.00'))
        VoucherService.post_voucher(v_rec)

        # 3. Direct statement credit not in books (Interest)
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 7, 28),
            description="Credit Interest Q1",
            credit_amount=Decimal('500.00'),
            debit_amount=Decimal('0.00'),
            balance=Decimal('50300.00'),
            status='UNRESOLVED'
        )

        # 4. Direct statement debit not in books (Bank SMS charges)
        BankTransaction.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            transaction_date=datetime.date(2026, 7, 29),
            description="Consolidated SMS charges",
            credit_amount=Decimal('0.00'),
            debit_amount=Decimal('200.00'),
            balance=Decimal('50300.00'),
            status='UNRESOLVED'
        )

        brs = BankReconciliationService.generate_statutory_brs(
            company=self.company,
            bank_ledger_id=str(self.bank_ledger.id),
            as_of_date=as_of
        )

        self.assertEqual(brs["balance_as_per_books"], "55000.00")
        self.assertEqual(brs["additions"]["unpresented_payments"]["total"], "10000.00")
        self.assertEqual(brs["additions"]["unrecorded_bank_credits"]["total"], "500.00")
        self.assertEqual(brs["deductions"]["uncleared_deposits"]["total"], "15000.00")
        self.assertEqual(brs["deductions"]["unrecorded_bank_debits"]["total"], "200.00")
        self.assertEqual(brs["reconciled_balance"], "50300.00")
        self.assertEqual(brs["actual_statement_balance"], "50300.00")
        self.assertEqual(brs["variance"], "0.00")
        self.assertTrue(brs["is_reconciled"])
        self.assertEqual(brs["reconciliation_status"], "PERFECTLY_RECONCILED")

    def test_statutory_bank_reconciliation_statement_variance_detection(self):
        """
        Verify that BRS detects discrepancy when statement balance does not match reconciled balance.
        """
        as_of = datetime.date(2026, 7, 31)

        # Statement import with closing balance of ₹55,000 when books have ₹50,000
        BankStatementImport.objects.create(
            company=self.company,
            bank_ledger=self.bank_ledger,
            source_file_name="hdfc_july_statement.csv",
            statement_start_date=datetime.date(2026, 7, 1),
            statement_end_date=datetime.date(2026, 7, 31),
            opening_balance=Decimal('50000.00'),
            closing_balance=Decimal('55000.00')
        )

        brs = BankReconciliationService.generate_statutory_brs(
            company=self.company,
            bank_ledger_id=str(self.bank_ledger.id),
            as_of_date=as_of
        )

        self.assertEqual(brs["balance_as_per_books"], "50000.00")
        self.assertEqual(brs["actual_statement_balance"], "55000.00")
        self.assertEqual(brs["variance"], "5000.00")
        self.assertFalse(brs["is_reconciled"])
        self.assertEqual(brs["reconciliation_status"], "VARIANCE_DETECTED")

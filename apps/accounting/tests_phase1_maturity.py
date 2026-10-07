import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company, UserCompany, CompanySettings
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, FinancialYear
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.accounting.services.tds_service import TDSService
from apps.accounting.services.integrity_engine import AccountingIntegrityEngine

User = get_user_model()


class AccountingPhase1MaturityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Paramount Infra Pvt Ltd",
            gstin="27AAACP0123P1Z5",
            state_code="27"
        )
        self.settings, _ = CompanySettings.objects.get_or_create(company=self.company)

        self.user = User.objects.create_user(
            email="ca_auditor@paramount.com",
            password="SecurePassword999!"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        # Chart of Accounts Groups
        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Current Assets", nature="ASSET")
        self.liab_grp = LedgerGroup.objects.create(company=self.company, name="Current Liabilities", nature="LIABILITY")
        self.tax_grp = LedgerGroup.objects.create(company=self.company, name="Duties & Taxes", nature="LIABILITY")
        self.exp_grp = LedgerGroup.objects.create(company=self.company, name="Direct Expenses", nature="EXPENSE")

        # Standard Ledgers
        self.supplier = Ledger.objects.create(
            company=self.company,
            name="BuildWell Contractors",
            group=self.liab_grp,
            ledger_type="SUPPLIER",
            pan="AAACB1234D",
            state_code="27",
            tds_applicable=True,
            tds_section="194C",
            tds_rate=Decimal("2.00")
        )
        self.purchase_ac = Ledger.objects.create(
            company=self.company,
            name="Contracting Expenses",
            group=self.exp_grp,
            ledger_type="PURCHASE"
        )
        self.input_cgst = Ledger.objects.create(
            company=self.company,
            name="Input CGST",
            group=self.asset_grp,
            ledger_type="TAX"
        )
        self.input_sgst = Ledger.objects.create(
            company=self.company,
            name="Input SGST",
            group=self.asset_grp,
            ledger_type="TAX"
        )

        self.category = ProductCategory.objects.create(company=self.company, name="Construction Work")
        self.product = Product.objects.create(
            company=self.company,
            name="RCC Labour Contract",
            category=self.category,
            purchase_price=Decimal("100000.00"),
            selling_price=Decimal("120000.00"),
            gst_rate=Decimal("18.00"),
            unit="JOB"
        )

        self.fy = FinancialYear.objects.create(
            company=self.company,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
            is_closed=False
        )

    def test_post_voucher_blocked_on_locked_period(self):
        """
        Verify that attempting to post a voucher on or before books_lock_date raises ValidationError.
        """
        lock_date = datetime.date(2026, 6, 30)
        self.settings.books_lock_date = lock_date
        self.settings.save(update_fields=['books_lock_date'])

        # Voucher dated before lock date (2026-06-15)
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='JOURNAL',
            voucher_number='JV-LOCK-01',
            voucher_date=datetime.date(2026, 6, 15),
            status='DRAFT',
            total_amount=Decimal('5000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=voucher, ledger=self.purchase_ac, debit_amount=Decimal('5000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.supplier, debit_amount=Decimal('0.00'), credit_amount=Decimal('5000.00'))

        with self.assertRaises(ValidationError) as ctx:
            VoucherService.post_voucher(voucher)

        self.assertIn(f"Accounting books are locked up to {lock_date}", str(ctx.exception))

    def test_post_voucher_allowed_with_override_period_lock(self):
        """
        Verify supervisor bypass (override_period_lock=True) allows posting when authorized.
        """
        lock_date = datetime.date(2026, 6, 30)
        self.settings.books_lock_date = lock_date
        self.settings.save(update_fields=['books_lock_date'])

        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='JOURNAL',
            voucher_number='JV-BYPASS-01',
            voucher_date=datetime.date(2026, 6, 15),
            status='DRAFT',
            total_amount=Decimal('5000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=voucher, ledger=self.purchase_ac, debit_amount=Decimal('5000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.supplier, debit_amount=Decimal('0.00'), credit_amount=Decimal('5000.00'))

        posted_v = VoucherService.post_voucher(voucher, override_period_lock=True)
        self.assertEqual(posted_v.status, 'POSTED')

    def test_update_and_cancel_voucher_blocked_on_locked_period(self):
        """
        Verify editing or cancelling a voucher on or before books_lock_date is blocked.
        """
        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='JOURNAL',
            voucher_number='JV-HIST-01',
            voucher_date=datetime.date(2026, 5, 20),
            status='DRAFT',
            total_amount=Decimal('2000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=voucher, ledger=self.purchase_ac, debit_amount=Decimal('2000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.supplier, debit_amount=Decimal('0.00'), credit_amount=Decimal('2000.00'))
        VoucherService.post_voucher(voucher)

        # Now freeze books up to 2026-05-31
        self.settings.books_lock_date = datetime.date(2026, 5, 31)
        self.settings.save(update_fields=['books_lock_date'])

        # Attempt edit
        with self.assertRaises(ValidationError) as ctx_edit:
            VoucherService.update_voucher(voucher, narration="Altered after freeze")
        self.assertIn("Accounting books are locked", str(ctx_edit.exception))

        # Attempt cancel
        with self.assertRaises(ValidationError) as ctx_cancel:
            VoucherService.cancel_voucher(voucher)
        self.assertIn("Accounting books are locked", str(ctx_cancel.exception))

    def test_closed_financial_year_blocks_all_actions(self):
        """
        Verify vouchers in a closed FY cannot be posted, edited, or cancelled.
        """
        self.fy.is_closed = True
        self.fy.save(update_fields=['is_closed'])

        voucher = Voucher.objects.create(
            company=self.company,
            financial_year=self.fy,
            voucher_type='JOURNAL',
            voucher_number='JV-CLOSED-01',
            voucher_date=datetime.date(2026, 5, 10),
            status='DRAFT',
            total_amount=Decimal('1000.00'),
            created_by=self.user
        )
        LedgerEntry.objects.create(voucher=voucher, ledger=self.purchase_ac, debit_amount=Decimal('1000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.supplier, debit_amount=Decimal('0.00'), credit_amount=Decimal('1000.00'))

        with self.assertRaises(ValidationError) as ctx:
            VoucherService.post_voucher(voucher)
        self.assertIn("closed financial year", str(ctx.exception))

    def test_tds_deduction_purchase_invoice_double_entry(self):
        """
        Verify end-to-end purchase invoice with TDS deduction:
        - Base: ₹1,00,000
        - GST (18%): CGST ₹9,000 + SGST ₹9,000 = ₹18,000
        - Gross Invoice Total: ₹1,18,000
        - TDS (Sec 194C @ 2% on base ₹1,00,000): ₹2,000
        - Net Supplier Payable: ₹1,16,000
        - Double Entry:
          Debit Expense: ₹1,00,000
          Debit CGST: ₹9,000
          Debit SGST: ₹9,000
          Credit Supplier: ₹1,16,000
          Credit TDS Payable - Sec 194C: ₹2,000
          Total Dr: ₹1,18,000 == Total Cr: ₹1,18,000.
        """
        voucher = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.company,
            user=self.user,
            party_ledger=self.supplier,
            purchase_ledger=self.purchase_ac,
            input_cgst_ledger=self.input_cgst,
            input_sgst_ledger=self.input_sgst,
            supplier_invoice_number="BILL-BW-101",
            voucher_date=datetime.date(2026, 7, 10),
            items_data=[
                {
                    "product_id": self.product.id,
                    "quantity": 1,
                    "rate": Decimal("100000.00"),
                    "discount_percent": Decimal("0.00")
                }
            ],
            tds_section="194C",
            tds_rate=Decimal("2.00")
        )

        self.assertEqual(voucher.tds_section, "194C")
        self.assertEqual(voucher.tds_rate, Decimal("2.00"))
        self.assertEqual(voucher.tds_amount, Decimal("2000.00"))
        self.assertIsNotNone(voucher.tds_ledger)
        self.assertEqual(voucher.tds_ledger.name, "TDS Payable - Sec 194C")

        # Check ledger entries
        entries = list(voucher.ledger_entries.all())
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, total_cr)
        self.assertEqual(total_dr, Decimal("118000.00"))

        supplier_entry = next(e for e in entries if e.ledger_id == self.supplier.id)
        self.assertEqual(supplier_entry.credit_amount, Decimal("116000.00"))

        tds_entry = next(e for e in entries if e.ledger_id == voucher.tds_ledger.id)
        self.assertEqual(tds_entry.credit_amount, Decimal("2000.00"))

        # Post voucher to verify double entry invariance and ledger balance update
        posted_v = VoucherService.post_voucher(voucher)
        self.assertEqual(posted_v.status, 'POSTED')

        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.current_balance, Decimal("116000.00"))

    def test_tds_section_206aa_penal_rate_missing_pan(self):
        """
        Verify that payee without a valid PAN is charged the 20% penal rate under Section 206AA.
        """
        vendor_no_pan = Ledger.objects.create(
            company=self.company,
            name="Local Labour Subcontractor",
            group=self.liab_grp,
            ledger_type="SUPPLIER",
            pan=None, # Missing PAN
            tds_applicable=True,
            tds_section="194C"
        )

        calc = TDSService.calculate_tds(
            company=self.company,
            party_ledger=vendor_no_pan,
            taxable_amount=Decimal("50000.00"),
            section="194C"
        )

        self.assertTrue(calc['applicable'])
        self.assertTrue(calc['penal_206aa'])
        self.assertEqual(calc['rate'], Decimal("20.00"))
        self.assertEqual(calc['tds_amount'], Decimal("10000.00"))
        self.assertEqual(calc['net_payable'], Decimal("40000.00"))

    def test_tds_summary_and_integrity_check_missing_pan(self):
        """
        Verify quarterly TDS summary (Form 26Q) and Integrity Engine detection of Section 206AA risk.
        """
        vendor_no_pan = Ledger.objects.create(
            company=self.company,
            name="Adhoc Professional",
            group=self.liab_grp,
            ledger_type="SUPPLIER",
            pan="INVALID_PAN",
            tds_applicable=True,
            tds_section="194J"
        )

        voucher = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.company,
            user=self.user,
            party_ledger=vendor_no_pan,
            purchase_ledger=self.purchase_ac,
            input_cgst_ledger=self.input_cgst,
            input_sgst_ledger=self.input_sgst,
            supplier_invoice_number="BILL-NOPAN-01",
            voucher_date=datetime.date(2026, 8, 1),
            items_data=[
                {
                    "product_id": self.product.id,
                    "quantity": 1,
                    "rate": Decimal("50000.00")
                }
            ],
            tds_section="194J",
            tds_amount=Decimal("5000.00")
        )
        VoucherService.post_voucher(voucher)

        # 1. Test quarterly Form 26Q summary
        summary = TDSService.generate_tds_summary(self.company)
        self.assertEqual(summary['total_vouchers'], 1)
        self.assertEqual(summary['missing_pan_vouchers'], 1)
        self.assertEqual(Decimal(summary['total_tds_deducted']), Decimal("5000.00"))

        # 2. Test Integrity Engine finding
        findings = AccountingIntegrityEngine.check_tds_compliance(self.company)
        self.assertTrue(any("Missing payee PAN on TDS deduction" in f.title for f in findings))

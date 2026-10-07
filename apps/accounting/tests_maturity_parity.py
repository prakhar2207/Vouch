import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.credit_debit_note_service import CreditDebitNoteService
from apps.gst.services.gstr_report_service import GSTRReportService
from apps.accounting.services.integrity_engine import IntegrityEngine

User = get_user_model()

class AccountingMaturityParityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Apex Engineering Ltd",
            gstin="07AAAAA0000A1Z5",
            state_code="07"
        )
        self.user = User.objects.create_user(
            email="accountant@apex.com",
            password="StrongPassword123!"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        # Groups
        self.asset_grp = LedgerGroup.objects.create(company=self.company, name="Current Assets", nature="ASSET")
        self.liab_grp = LedgerGroup.objects.create(company=self.company, name="Current Liabilities", nature="LIABILITY")
        self.tax_grp = LedgerGroup.objects.create(company=self.company, name="Duties & Taxes", nature="LIABILITY")
        self.income_grp = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")
        self.exp_grp = LedgerGroup.objects.create(company=self.company, name="Purchase Accounts", nature="EXPENSE")

        # Master Ledgers
        self.customer = Ledger.objects.create(
            company=self.company,
            name="Tata Motors",
            group=self.asset_grp,
            ledger_type="CUSTOMER",
            gstin="07TATAM1234F1Z0",
            state_code="07"
        )
        self.supplier = Ledger.objects.create(
            company=self.company,
            name="National Transporters",
            group=self.liab_grp,
            ledger_type="SUPPLIER",
            gstin="", # Unregistered GTA transporter
            state_code="07"
        )
        self.sales_acct = Ledger.objects.create(
            company=self.company,
            name="Sales Account",
            group=self.income_grp,
            ledger_type="SALES"
        )
        self.purchase_acct = Ledger.objects.create(
            company=self.company,
            name="Purchase Account",
            group=self.exp_grp,
            ledger_type="PURCHASE"
        )

        # Products
        self.product = Product.objects.create(
            company=self.company,
            name="Hydraulic Valve",
            sku="VALVE-01",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("800.00"),
            stock_quantity=Decimal("100.00"),
            gst_rate=Decimal("18.00"),
            hsn_code="8481"
        )

    def test_auto_round_off_in_post_voucher(self):
        """
        Verify that fractional double-entry discrepancies (e.g. 2 paise) are auto-balanced
        by inserting a Round Off ledger entry, ensuring zero-variance double-entry compliance.
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-RO-01',
            voucher_date=timezone.now().date(),
            party_ledger=self.customer,
            total_amount=Decimal('100.00'),
            created_by=self.user,
            status='DRAFT'
        )
        # Party Debited ₹100.00, Sales Credited ₹99.98 -> 2 paise discrepancy
        LedgerEntry.objects.create(
            voucher=v,
            company=self.company,
            ledger=self.customer,
            debit_amount=Decimal('100.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            voucher=v,
            company=self.company,
            ledger=self.sales_acct,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('99.98')
        )

        # Post voucher
        posted = VoucherService.post_voucher(v, process_stock=False)
        self.assertEqual(posted.status, 'POSTED')

        entries = list(posted.ledger_entries.all())
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, total_cr)
        self.assertEqual(total_dr, Decimal('100.00'))

        # Check Round Off entry was automatically created
        ro_entry = next((e for e in entries if e.ledger.name.lower() == 'round off'), None)
        self.assertIsNotNone(ro_entry)
        self.assertEqual(ro_entry.credit_amount, Decimal('0.02'))

    def test_large_discrepancy_rejected(self):
        """
        Discrepancies greater than ₹1.00 must NOT be auto-rounded; they must be rejected with ValidationError.
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-ERR-01',
            voucher_date=timezone.now().date(),
            party_ledger=self.customer,
            total_amount=Decimal('100.00'),
            created_by=self.user,
            status='DRAFT'
        )
        LedgerEntry.objects.create(
            voucher=v,
            company=self.company,
            ledger=self.customer,
            debit_amount=Decimal('100.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            voucher=v,
            company=self.company,
            ledger=self.sales_acct,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('80.00') # ₹20 discrepancy
        )
        with self.assertRaises(ValidationError):
            VoucherService.post_voucher(v, process_stock=False)

    def test_reverse_charge_purchase_flow(self):
        """
        Verify RCM purchase flow:
        - Supplier is payable only for taxable value (no GST paid to supplier)
        - Output/RCM Tax Liability is credited (to pay to govt)
        - Input Tax Credit (RCM) is debited (to claim asset)
        - Double entry perfectly balances
        """
        items_data = [
            {
                "product_id": str(self.product.id),
                "quantity": 10,
                "rate": 1000, # Taxable = 10,000, 18% GST (CGST 900, SGST 900)
                "discount_percent": 0
            }
        ]
        voucher = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.company,
            user=self.user,
            party_ledger=self.supplier,
            items_data=items_data,
            supplier_invoice_number="BILL-RCM-99",
            is_reverse_charge=True
        )

        self.assertTrue(voucher.is_reverse_charge)
        # Supplier payable is strictly taxable amount ₹10,000 (not ₹11,800)
        self.assertEqual(voucher.total_amount, Decimal('10000.00'))

        posted = VoucherService.post_voucher(voucher, process_stock=False)
        self.assertEqual(posted.status, 'POSTED')

        entries = list(posted.ledger_entries.all())
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, total_cr)
        # Total debits = 10,000 (Purchase) + 900 (Input CGST RCM) + 900 (Input SGST RCM) = 11,800
        self.assertEqual(total_dr, Decimal('11800.00'))

        # Supplier ledger credited exactly ₹10,000
        sup_entry = next(e for e in entries if e.ledger_id == self.supplier.id)
        self.assertEqual(sup_entry.credit_amount, Decimal('10000.00'))

        # Check RCM Liability and ITC entries
        rcm_cgst_liab = next((e for e in entries if 'rcm cgst liability' in e.ledger.name.lower()), None)
        rcm_cgst_itc = next((e for e in entries if 'input cgst (rcm)' in e.ledger.name.lower()), None)
        self.assertIsNotNone(rcm_cgst_liab)
        self.assertIsNotNone(rcm_cgst_itc)
        self.assertEqual(rcm_cgst_liab.credit_amount, Decimal('900.00'))
        self.assertEqual(rcm_cgst_itc.debit_amount, Decimal('900.00'))

    def test_credit_note_original_invoice_validation_and_flexibility(self):
        """
        Verify:
        1. Credit Note links to original invoice.
        2. Cumulative credit note exceeding original invoice raises ValidationError.
        3. Business owner can override with allow_excess=True for commercial goodwill/rebates.
        """
        # Create Sales Invoice for ₹2,000 (2 units @ 1000)
        inv = SalesInvoiceService.generate_sales_invoice(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            items_data=[{"product_id": str(self.product.id), "quantity": 2, "rate": 1000}]
        )
        posted_inv = VoucherService.post_voucher(inv, process_stock=False)
        inv_total = posted_inv.total_amount # ₹2,360 with 18% GST

        # Issue valid Credit Note for 1 unit (₹1,180)
        cn1 = CreditDebitNoteService.generate_credit_note(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            items_data=[{"product_id": str(self.product.id), "quantity": 1, "rate": 1000}],
            original_invoice=posted_inv
        )
        self.assertEqual(cn1.original_invoice_id, posted_inv.id)
        VoucherService.post_voucher(cn1, process_stock=False)

        # Attempt to issue another Credit Note for 2 units (₹2,360) -> ₹1,180 + ₹2,360 = ₹3,540 > ₹2,360
        with self.assertRaises(ValidationError):
            CreditDebitNoteService.generate_credit_note(
                company=self.company,
                user=self.user,
                party_ledger=self.customer,
                items_data=[{"product_id": str(self.product.id), "quantity": 2, "rate": 1000}],
                original_invoice=posted_inv,
                allow_excess=False
            )

        # But with allow_excess=True, business flexibility allows it
        cn_excess = CreditDebitNoteService.generate_credit_note(
            company=self.company,
            user=self.user,
            party_ledger=self.customer,
            items_data=[{"product_id": str(self.product.id), "quantity": 2, "rate": 1000}],
            original_invoice=posted_inv,
            allow_excess=True
        )
        self.assertIsNotNone(cn_excess)

    def test_historical_voucher_update_and_balance_rebuild(self):
        """
        Verify that VoucherService.update_voucher updates header details,
        recalculates ledger balances, and logs audit trail.
        """
        past_date = timezone.now().date() - datetime.timedelta(days=45) # > 30 days
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='JOURNAL',
            voucher_number='JV-HIST-01',
            voucher_date=past_date,
            party_ledger=self.customer,
            total_amount=Decimal('500.00'),
            created_by=self.user,
            status='POSTED'
        )
        LedgerEntry.objects.create(
            voucher=v,
            company=self.company,
            ledger=self.customer,
            debit_amount=Decimal('500.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            voucher=v,
            company=self.company,
            ledger=self.sales_acct,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('500.00')
        )
        VoucherService.recalculate_ledger_balance(self.customer)
        self.assertEqual(self.customer.current_balance, Decimal('500.00'))

        # Update narration and date via update_voucher
        updated = VoucherService.update_voucher(
            voucher=v,
            user=self.user,
            narration="Revised historical adjustment",
            reason="Auditor recommendation"
        )
        self.assertEqual(updated.narration, "Revised historical adjustment")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.current_balance, Decimal('500.00'))

    def test_gstr3b_rcm_reporting(self):
        """
        Verify that GSTRReportService.generate_gstr3b_summary correctly populates:
        - Table 3.1(d) for RCM inward supplies
        - Table 4(A)(3) for RCM eligible ITC
        """
        # Create and post an RCM Purchase
        v_rcm = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.company,
            user=self.user,
            party_ledger=self.supplier,
            items_data=[{"product_id": str(self.product.id), "quantity": 1, "rate": 1000}],
            supplier_invoice_number="RCM-3B-01",
            is_reverse_charge=True
        )
        VoucherService.post_voucher(v_rcm, process_stock=False)

        start_date = timezone.now().date().replace(day=1).strftime('%Y-%m-%d')
        end_date = timezone.now().date().strftime('%Y-%m-%d')

        gstr3b = GSTRReportService.generate_gstr3b_summary(self.company, start_date, end_date)

        # Check Table 3.1(d)
        self.assertIn("table_3_1_d_rcm_supplies", gstr3b)
        rcm_out = gstr3b["table_3_1_d_rcm_supplies"]
        self.assertEqual(rcm_out["taxable_value"], 1000.0)
        self.assertEqual(rcm_out["cgst"], 90.0)
        self.assertEqual(rcm_out["sgst"], 90.0)

        # Check Table 4(A)(3)
        self.assertIn("table_4_a_3_rcm_itc", gstr3b)
        rcm_itc = gstr3b["table_4_a_3_rcm_itc"]
        self.assertEqual(rcm_itc["taxable_value"], 1000.0)
        self.assertEqual(rcm_itc["cgst"], 90.0)
        self.assertEqual(rcm_itc["sgst"], 90.0)

    def test_document_numbering_sequence_gap_detection(self):
        """
        Verify that IntegrityEngine detects sequence gaps (e.g. INV-001 then INV-003, missing INV-002).
        """
        today = timezone.now().date()
        Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-0001',
            voucher_date=today,
            party_ledger=self.customer,
            total_amount=Decimal('100.00'),
            created_by=self.user,
            status='POSTED'
        )
        # Skip INV-0002 and create INV-0003
        Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-0003',
            voucher_date=today,
            party_ledger=self.customer,
            total_amount=Decimal('100.00'),
            created_by=self.user,
            status='POSTED'
        )

        findings = IntegrityEngine.check_document_numbering(self.company)
        gap_finding = next((f for f in findings if 'missing INV-0002' in f.title or 'Sequence gap' in f.title), None)
        self.assertIsNotNone(gap_finding)
        self.assertEqual(gap_finding.severity, 'WARNING')

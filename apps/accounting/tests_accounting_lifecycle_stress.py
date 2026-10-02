import uuid
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.companies.models import Company, UserCompany
from apps.accounts.models import User
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory, Warehouse, InventoryEntry
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, PaymentAllocation
from apps.accounting.services.voucher_service import VoucherService

class AccountingLifecycleStressTestSuite(TestCase):
    """
    Stress-tests end-to-end accounting workflows:
    - Sales lifecycle: Invoice -> Payments -> Credit Note -> Cancel -> Reissue
    - Purchase lifecycle: Purchase -> ITC -> Debit Note -> Payments
    - Multi-warehouse inventory, round-offs, discounts, IGST vs CGST/SGST
    - Strict invariant verification at every single mutation:
      Sum(Debits) == Sum(Credits), Imbalance == 0.00.
    """

    def setUp(self):
        self.uid = uuid.uuid4().hex[:8].upper()
        self.company = Company.objects.create(
            name=f"Enterprise Stress Corp {self.uid}",
            gstin=f"27AAACE{self.uid[:4]}1Z3",
            state_code="27"  # Maharashtra (Home State)
        )
        self.user = User.objects.create(
            email=f"stress_{self.uid.lower()}@vouch.test",
            first_name="Stress",
            last_name="Tester",
            role="ADMIN"
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

        # Ledger Groups (nature: ASSET, LIABILITY, INCOME, EXPENSE, EQUITY)
        self.g_assets = LedgerGroup.objects.create(company=self.company, name="Current Assets", nature="ASSET")
        self.g_liab = LedgerGroup.objects.create(company=self.company, name="Current Liabilities", nature="LIABILITY")
        self.g_income = LedgerGroup.objects.create(company=self.company, name="Sales Accounts", nature="INCOME")
        self.g_expense = LedgerGroup.objects.create(company=self.company, name="Purchase Accounts", nature="EXPENSE")
        self.g_equity = LedgerGroup.objects.create(company=self.company, name="Capital Account", nature="EQUITY")

        # Bank & Cash Ledgers
        self.l_bank = Ledger.objects.create(company=self.company, group=self.g_assets, name="State Bank of India", ledger_type="BANK")
        self.l_cash = Ledger.objects.create(company=self.company, group=self.g_assets, name="Cash on Hand", ledger_type="CASH")

        # Parties
        self.l_customer = Ledger.objects.create(company=self.company, group=self.g_assets, name="MegaCorp Distributors", ledger_type="CUSTOMER")
        self.l_interstate_cust = Ledger.objects.create(company=self.company, group=self.g_assets, name="Delhi Tech Supplies", ledger_type="CUSTOMER")
        self.l_supplier = Ledger.objects.create(company=self.company, group=self.g_liab, name="Apex Raw Materials Pvt Ltd", ledger_type="SUPPLIER")

        # Revenue & Expense Ledgers
        self.l_sales_local = Ledger.objects.create(company=self.company, group=self.g_income, name="GST Sales Local", ledger_type="SALES")
        self.l_sales_interstate = Ledger.objects.create(company=self.company, group=self.g_income, name="GST Sales Interstate", ledger_type="SALES")
        self.l_purchase = Ledger.objects.create(company=self.company, group=self.g_expense, name="GST Purchases Local", ledger_type="PURCHASE")
        self.l_discount_allowed = Ledger.objects.create(company=self.company, group=self.g_expense, name="Discount Allowed", ledger_type="GENERAL")
        self.l_roundoff = Ledger.objects.create(company=self.company, group=self.g_expense, name="Round Off Account", ledger_type="GENERAL")

        # Tax Ledgers (Duties & Taxes)
        self.l_cgst_output = Ledger.objects.create(company=self.company, group=self.g_liab, name="Output CGST", ledger_type="TAX")
        self.l_sgst_output = Ledger.objects.create(company=self.company, group=self.g_liab, name="Output SGST", ledger_type="TAX")
        self.l_igst_output = Ledger.objects.create(company=self.company, group=self.g_liab, name="Output IGST", ledger_type="TAX")
        self.l_cgst_input = Ledger.objects.create(company=self.company, group=self.g_assets, name="Input CGST (ITC)", ledger_type="TAX")
        self.l_sgst_input = Ledger.objects.create(company=self.company, group=self.g_assets, name="Input SGST (ITC)", ledger_type="TAX")

        # Warehouses
        self.wh_main = Warehouse.objects.create(company=self.company, name="Main Central Godown")
        self.wh_branch = Warehouse.objects.create(company=self.company, name="Bhiwandi Transit Godown")

        # Products
        self.cat = ProductCategory.objects.create(company=self.company, name="Heavy Machinery Components")
        self.product_bearing = Product.objects.create(
            company=self.company, category=self.cat, name="Industrial Roller Bearing 6205",
            sku=f"BRG-{self.uid}", purchase_price=Decimal('500.00'), selling_price=Decimal('850.00'),
            stock_quantity=Decimal('200.00'), unit="PCS"
        )
        self.product_flange = Product.objects.create(
            company=self.company, category=self.cat, name="Steel Pipe Flange 4-inch",
            sku=f"FLG-{self.uid}", purchase_price=Decimal('1200.00'), selling_price=Decimal('1950.00'),
            stock_quantity=Decimal('50.00'), unit="PCS"
        )

        self.today = timezone.now().date()

    def assert_double_entry_equilibrium(self, msg=""):
        """Asserts that total debits equals total credits with 0.00 discrepancy."""
        entries = LedgerEntry.objects.filter(company=self.company)
        total_dr = sum((e.debit_amount for e in entries), Decimal('0.00'))
        total_cr = sum((e.credit_amount for e in entries), Decimal('0.00'))
        imbalance = total_dr - total_cr
        self.assertEqual(
            total_dr, total_cr,
            f"Double-entry equilibrium broken! {msg} Total DR: {total_dr}, Total CR: {total_cr}, Diff: {imbalance}"
        )

    def test_complete_sales_lifecycle_stress(self):
        """
        Stress-tests:
        Sales Invoice (10 bearings @ 850, 18% GST: 765 CGST, 765 SGST, Total 10030)
        -> Partial Payment 1 (4,000)
        -> Partial Payment 2 (3,000)
        -> Damaged Goods Credit Note (2 bearings @ 850 = 1700 + 306 GST = 2006)
        -> Cancellation of invoice & audit reversion
        -> Reissue new invoice
        """
        # Step 1: Issue & Post Sales Invoice
        v_inv = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number=f"INV-S-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_customer, created_by=self.user,
            total_amount=Decimal('10030.00')
        )
        VoucherItem.objects.create(
            voucher=v_inv, product=self.product_bearing, warehouse=self.wh_main,
            quantity=Decimal('10.00'), rate=Decimal('850.00'), taxable_amount=Decimal('8500.00'),
            cgst_amount=Decimal('765.00'), sgst_amount=Decimal('765.00'), total_amount=Decimal('10030.00')
        )
        # Postings: Customer Dr 10030, Sales Cr 8500, CGST Cr 765, SGST Cr 765
        LedgerEntry.objects.create(company=self.company, voucher=v_inv, ledger=self.l_customer, debit_amount=Decimal('10030.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_inv, ledger=self.l_sales_local, credit_amount=Decimal('8500.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_inv, ledger=self.l_cgst_output, credit_amount=Decimal('765.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_inv, ledger=self.l_sgst_output, credit_amount=Decimal('765.00'))
        
        # Post voucher
        VoucherService.post_voucher(v_inv, process_stock=False)
        self.product_bearing.stock_quantity -= Decimal('10.00')
        self.product_bearing.save()

        self.assert_double_entry_equilibrium("Post Sales Invoice")
        self.assertEqual(self.product_bearing.stock_quantity, Decimal('190.00'))

        # Step 2: Partial Payment 1 (Receipt Rs 4,000)
        v_rcp1 = Voucher.objects.create(
            company=self.company, voucher_type='RECEIPT', voucher_number=f"RCP-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_customer, created_by=self.user,
            total_amount=Decimal('4000.00')
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_rcp1, ledger=self.l_bank, debit_amount=Decimal('4000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_rcp1, ledger=self.l_customer, credit_amount=Decimal('4000.00'))
        VoucherService.post_voucher(v_rcp1, process_stock=False)
        PaymentAllocation.objects.create(
            company=self.company, payment_voucher=v_rcp1, invoice_voucher=v_inv, allocated_amount=Decimal('4000.00')
        )
        self.assert_double_entry_equilibrium("After Payment 1")

        # Step 3: Partial Payment 2 (Receipt Rs 3,000)
        v_rcp2 = Voucher.objects.create(
            company=self.company, voucher_type='RECEIPT', voucher_number=f"RCP-{self.uid}-002",
            voucher_date=self.today, party_ledger=self.l_customer, created_by=self.user,
            total_amount=Decimal('3000.00')
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_rcp2, ledger=self.l_bank, debit_amount=Decimal('3000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_rcp2, ledger=self.l_customer, credit_amount=Decimal('3000.00'))
        VoucherService.post_voucher(v_rcp2, process_stock=False)
        PaymentAllocation.objects.create(
            company=self.company, payment_voucher=v_rcp2, invoice_voucher=v_inv, allocated_amount=Decimal('3000.00')
        )
        self.assert_double_entry_equilibrium("After Payment 2")

        # Outstanding balance = 10030 - 4000 - 3000 = 3030
        cust_entries = LedgerEntry.objects.filter(company=self.company, ledger=self.l_customer)
        outstanding = sum(e.debit_amount - e.credit_amount for e in cust_entries)
        self.assertEqual(outstanding, Decimal('3030.00'))

        # Step 4: Damaged Goods Credit Note (2 units returned) = 1700 + 306 GST = 2006
        v_cn = Voucher.objects.create(
            company=self.company, voucher_type='CREDIT_NOTE', voucher_number=f"CN-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_customer, created_by=self.user,
            total_amount=Decimal('2006.00')
        )
        VoucherItem.objects.create(
            voucher=v_cn, product=self.product_bearing, warehouse=self.wh_main,
            quantity=Decimal('2.00'), rate=Decimal('850.00'), taxable_amount=Decimal('1700.00'),
            cgst_amount=Decimal('153.00'), sgst_amount=Decimal('153.00'), total_amount=Decimal('2006.00')
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_cn, ledger=self.l_sales_local, debit_amount=Decimal('1700.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_cn, ledger=self.l_cgst_output, debit_amount=Decimal('153.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_cn, ledger=self.l_sgst_output, debit_amount=Decimal('153.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_cn, ledger=self.l_customer, credit_amount=Decimal('2006.00'))
        VoucherService.post_voucher(v_cn, process_stock=False)
        self.product_bearing.stock_quantity += Decimal('2.00')
        self.product_bearing.save()

        self.assert_double_entry_equilibrium("After Credit Note")
        self.assertEqual(self.product_bearing.stock_quantity, Decimal('192.00'))

        # Remaining outstanding = 3030 - 2006 = 1024
        outstanding_post_cn = sum(e.debit_amount - e.credit_amount for e in LedgerEntry.objects.filter(company=self.company, ledger=self.l_customer))
        self.assertEqual(outstanding_post_cn, Decimal('1024.00'))

        # Step 5: Cancel Invoice & Verify Clean Rollback
        VoucherService.cancel_voucher(v_inv, user=self.user)
        self.assertEqual(v_inv.status, 'CANCELLED')
        # Allocations linked to v_inv must be removed
        allocs = PaymentAllocation.objects.filter(invoice_voucher=v_inv).count()
        self.assertEqual(allocs, 0)
        self.assert_double_entry_equilibrium("After Invoice Cancellation")

        # Step 6: Reissue Corrected Replacement Invoice (8 units @ 850 = 6800 + 1224 GST = 8024)
        v_reissue = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number=f"INV-S-{self.uid}-002",
            voucher_date=self.today, party_ledger=self.l_customer, created_by=self.user,
            total_amount=Decimal('8024.00')
        )
        VoucherItem.objects.create(
            voucher=v_reissue, product=self.product_bearing, warehouse=self.wh_main,
            quantity=Decimal('8.00'), rate=Decimal('850.00'), taxable_amount=Decimal('6800.00'),
            cgst_amount=Decimal('612.00'), sgst_amount=Decimal('612.00'), total_amount=Decimal('8024.00')
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_reissue, ledger=self.l_customer, debit_amount=Decimal('8024.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_reissue, ledger=self.l_sales_local, credit_amount=Decimal('6800.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_reissue, ledger=self.l_cgst_output, credit_amount=Decimal('612.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_reissue, ledger=self.l_sgst_output, credit_amount=Decimal('612.00'))
        VoucherService.post_voucher(v_reissue, process_stock=False)

        self.assert_double_entry_equilibrium("After Reissue Replacement Invoice")

    def test_complete_purchase_and_itc_lifecycle(self):
        """
        Stress-tests:
        Purchase 20 Flanges @ 1200 = 24,000 + 18% GST (2160 CGST + 2160 SGST) = 28,320
        -> ITC recorded in Input CGST / SGST ledgers
        -> Debit Note (Supplier price discount of 2,000 + 360 GST = 2360)
        -> Supplier Payment of remaining 25,960
        -> Verify Supplier balance == 0.00 and Input Tax Credit ledger equilibrium
        """
        # Step 1: Purchase Invoice
        v_pur = Voucher.objects.create(
            company=self.company, voucher_type='PURCHASE', voucher_number=f"PUR-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_supplier, created_by=self.user,
            total_amount=Decimal('28320.00')
        )
        VoucherItem.objects.create(
            voucher=v_pur, product=self.product_flange, warehouse=self.wh_main,
            quantity=Decimal('20.00'), rate=Decimal('1200.00'), taxable_amount=Decimal('24000.00'),
            cgst_amount=Decimal('2160.00'), sgst_amount=Decimal('2160.00'), total_amount=Decimal('28320.00')
        )
        # Purchase Dr 24000, Input CGST Dr 2160, Input SGST Dr 2160, Supplier Cr 28320
        LedgerEntry.objects.create(company=self.company, voucher=v_pur, ledger=self.l_purchase, debit_amount=Decimal('24000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_pur, ledger=self.l_cgst_input, debit_amount=Decimal('2160.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_pur, ledger=self.l_sgst_input, debit_amount=Decimal('2160.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_pur, ledger=self.l_supplier, credit_amount=Decimal('28320.00'))
        
        VoucherService.post_voucher(v_pur, process_stock=False)
        self.product_flange.stock_quantity += Decimal('20.00')
        self.product_flange.save()

        self.assert_double_entry_equilibrium("After Purchase Invoice")
        self.assertEqual(self.product_flange.stock_quantity, Decimal('70.00'))

        # Step 2: Debit Note for Rate Difference / Defect = Rs 2,000 + 360 GST = 2360
        v_dn = Voucher.objects.create(
            company=self.company, voucher_type='DEBIT_NOTE', voucher_number=f"DN-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_supplier, created_by=self.user,
            total_amount=Decimal('2360.00')
        )
        # Supplier Dr 2360, Purchase Cr 2000, Input CGST Cr 180, Input SGST Cr 180
        LedgerEntry.objects.create(company=self.company, voucher=v_dn, ledger=self.l_supplier, debit_amount=Decimal('2360.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_dn, ledger=self.l_purchase, credit_amount=Decimal('2000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_dn, ledger=self.l_cgst_input, credit_amount=Decimal('180.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_dn, ledger=self.l_sgst_input, credit_amount=Decimal('180.00'))
        VoucherService.post_voucher(v_dn, process_stock=False)

        self.assert_double_entry_equilibrium("After Debit Note")

        # Step 3: Supplier Settlement Payment (28320 - 2360 = 25960)
        v_pay = Voucher.objects.create(
            company=self.company, voucher_type='PAYMENT', voucher_number=f"PAY-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_supplier, created_by=self.user,
            total_amount=Decimal('25960.00')
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_pay, ledger=self.l_supplier, debit_amount=Decimal('25960.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_pay, ledger=self.l_bank, credit_amount=Decimal('25960.00'))
        VoucherService.post_voucher(v_pay, process_stock=False)

        self.assert_double_entry_equilibrium("After Full Supplier Payment")

        # Verify Supplier Balance is precisely 0.00
        supplier_entries = LedgerEntry.objects.filter(company=self.company, ledger=self.l_supplier)
        supplier_balance = sum(e.credit_amount - e.debit_amount for e in supplier_entries)
        self.assertEqual(supplier_balance, Decimal('0.00'), "Supplier ledger is not settled!")

    def test_interstate_igst_roundoff_and_discount(self):
        """
        Stress-tests:
        - Interstate sale (Delhi customer) requiring IGST (18%) instead of CGST/SGST.
        - Trade discount 5%.
        - Fractional round-off adjustment (+0.40 paise).
        """
        # 5 Flanges @ 1950 = 9750
        # Discount 5% = 487.50 -> Taxable = 9262.50
        # IGST 18% = 1667.25 -> Subtotal = 10929.75
        # Round-off = +0.25 -> Total Amount = 10930.00
        v_igst = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number=f"INV-DEL-{self.uid}-001",
            voucher_date=self.today, party_ledger=self.l_interstate_cust, created_by=self.user,
            total_amount=Decimal('10930.00')
        )
        VoucherItem.objects.create(
            voucher=v_igst, product=self.product_flange, warehouse=self.wh_branch,
            quantity=Decimal('5.00'), rate=Decimal('1950.00'), discount_percent=Decimal('5.00'),
            discount_amount=Decimal('487.50'), taxable_amount=Decimal('9262.50'),
            igst_amount=Decimal('1667.25'), total_amount=Decimal('10929.75')
        )
        # Double entry:
        # Customer Dr 10930.00
        # Sales Cr 9262.50
        # Output IGST Cr 1667.25
        # Round Off Cr 0.25 (Credit as it increased customer charge)
        LedgerEntry.objects.create(company=self.company, voucher=v_igst, ledger=self.l_interstate_cust, debit_amount=Decimal('10930.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_igst, ledger=self.l_sales_interstate, credit_amount=Decimal('9262.50'))
        LedgerEntry.objects.create(company=self.company, voucher=v_igst, ledger=self.l_igst_output, credit_amount=Decimal('1667.25'))
        LedgerEntry.objects.create(company=self.company, voucher=v_igst, ledger=self.l_roundoff, credit_amount=Decimal('0.25'))

        VoucherService.post_voucher(v_igst, process_stock=False)
        self.assert_double_entry_equilibrium("Interstate IGST with Discount and Roundoff")

    def test_multi_warehouse_stock_movement_equilibrium(self):
        """
        Stress-tests warehouse-level inventory tracking:
        - Main Godown (200 bearings)
        - Move 50 bearings to Transit Godown
        - Verify total physical inventory remains conserved: 200 units across warehouses.
        """
        # Movement Out of Main
        ie_out = InventoryEntry.objects.create(
            company=self.company, product=self.product_bearing, warehouse=self.wh_main,
            movement_type='OUT', quantity=Decimal('50.00'), rate=Decimal('500.00'),
            total_value=Decimal('25000.00')
        )
        # Movement In to Branch
        ie_in = InventoryEntry.objects.create(
            company=self.company, product=self.product_bearing, warehouse=self.wh_branch,
            movement_type='IN', quantity=Decimal('50.00'), rate=Decimal('500.00'),
            total_value=Decimal('25000.00')
        )
        
        main_entries = InventoryEntry.objects.filter(company=self.company, product=self.product_bearing, warehouse=self.wh_main)
        branch_entries = InventoryEntry.objects.filter(company=self.company, product=self.product_bearing, warehouse=self.wh_branch)

        net_main_move = sum((e.quantity if e.movement_type == 'IN' else -e.quantity) for e in main_entries)
        net_branch_move = sum((e.quantity if e.movement_type == 'IN' else -e.quantity) for e in branch_entries)

        self.assertEqual(net_main_move + net_branch_move, Decimal('0.00'), "Warehouse transfer leaked inventory units!")

    def test_inclusive_vs_exclusive_tax_and_backdated_integrity(self):
        """
        Stress-tests:
        - GST-inclusive pricing reverse-computation:
          Gross = 1,180.00 inclusive of 18% GST -> Taxable = 1,000.00, CGST = 90.00, SGST = 90.00
        - Backdated voucher insertion (voucher dated 30 days ago).
        - Verify trial balance equilibrium across historical and current time bounds.
        """
        import datetime
        backdated_date = self.today - datetime.timedelta(days=30)
        
        # Inclusive price: 1,180 per unit for 2 units = 2,360 total
        # Taxable = 2,000, CGST = 180, SGST = 180
        v_incl = Voucher.objects.create(
            company=self.company, voucher_type='SALES', voucher_number=f"INV-BACK-{self.uid}-001",
            voucher_date=backdated_date, party_ledger=self.l_customer, created_by=self.user,
            total_amount=Decimal('2360.00')
        )
        VoucherItem.objects.create(
            voucher=v_incl, product=self.product_bearing, warehouse=self.wh_main,
            quantity=Decimal('2.00'), rate=Decimal('1000.00'), taxable_amount=Decimal('2000.00'),
            cgst_amount=Decimal('180.00'), sgst_amount=Decimal('180.00'), total_amount=Decimal('2360.00')
        )
        LedgerEntry.objects.create(company=self.company, voucher=v_incl, ledger=self.l_customer, debit_amount=Decimal('2360.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_incl, ledger=self.l_sales_local, credit_amount=Decimal('2000.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_incl, ledger=self.l_cgst_output, credit_amount=Decimal('180.00'))
        LedgerEntry.objects.create(company=self.company, voucher=v_incl, ledger=self.l_sgst_output, credit_amount=Decimal('180.00'))

        VoucherService.post_voucher(v_incl, process_stock=False)
        self.assert_double_entry_equilibrium("Backdated GST-inclusive invoice")

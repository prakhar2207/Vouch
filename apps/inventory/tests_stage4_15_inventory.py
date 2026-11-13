import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import User
from apps.accounting.models import FinancialYear, Voucher
from apps.accounting.services.financial_statements_service import FinancialStatementsService
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.credit_debit_note_service import CreditDebitNoteService
from apps.companies.models import Company, CompanySettings, UserCompany
from apps.companies.views import provision_company_defaults
from apps.inventory.models import InventoryEntry, Product
from apps.ledgers.models import Ledger, LedgerGroup


def _seed_inv_tenant(suffix: str, costing_method: str = "FIFO", open_stock: Decimal = Decimal("10.00"), allow_negative: bool = True):
    user = User.objects.create_user(
        email=f"inv_{suffix}@s415.test", password="Password123!", role="OWNER", email_verified=True
    )
    company = Company.objects.create(name=f"Inv S415 {suffix}", state_code="27", gstin="27AABCI4150F1Z5")
    UserCompany.objects.create(user=user, company=company, role="OWNER")
    CompanySettings.objects.update_or_create(company=company, defaults={"allow_negative_stock": allow_negative})
    provision_company_defaults(company)
    FinancialYear.objects.get_or_create(
        company=company, code="26-27",
        defaults={"name": "FY 26-27", "start_date": datetime.date(2026, 4, 1), "end_date": datetime.date(2027, 3, 31)},
    )

    debtors = LedgerGroup.objects.get(company=company, name="Sundry Debtors")
    creditors = LedgerGroup.objects.get(company=company, name="Sundry Creditors")
    cust = Ledger.objects.create(company=company, group=debtors, name="Cust S415", ledger_type="CUSTOMER", state_code="27")
    supp = Ledger.objects.create(company=company, group=creditors, name="Supp S415", ledger_type="SUPPLIER", state_code="27")
    sales = Ledger.objects.get(company=company, ledger_type="SALES")
    purchase = Ledger.objects.get(company=company, ledger_type="PURCHASE")
    liab = LedgerGroup.objects.get(company=company, name="Duties & Taxes")
    cgst_out = Ledger.objects.filter(company=company, name__icontains="Output CGST").first() or Ledger.objects.create(company=company, group=liab, name="Output CGST", ledger_type="TAX")
    sgst_out = Ledger.objects.filter(company=company, name__icontains="Output SGST").first() or Ledger.objects.create(company=company, group=liab, name="Output SGST", ledger_type="TAX")
    cgst_in = Ledger.objects.filter(company=company, name__icontains="Input CGST").first() or Ledger.objects.create(company=company, group=liab, name="Input CGST", ledger_type="TAX")
    sgst_in = Ledger.objects.filter(company=company, name__icontains="Input SGST").first() or Ledger.objects.create(company=company, group=liab, name="Input SGST", ledger_type="TAX")

    prod = Product.objects.create(
        company=company, name=f"Item {suffix}", sku=f"SKU-{suffix}", unit="PCS",
        gst_rate=Decimal("18.00"), selling_price=Decimal("200.00"), purchase_price=Decimal("100.00"),
        stock_quantity=open_stock, costing_method=costing_method,
    )
    return {
        "user": user, "company": company, "cust": cust, "supp": supp,
        "sales": sales, "purchase": purchase,
        "cgst_out": cgst_out, "sgst_out": sgst_out, "cgst_in": cgst_in, "sgst_in": sgst_in,
        "prod": prod,
    }


class Stage415InventoryIntegrityTests(TestCase):
    """Covers Stage 4.15 Section 8 & 13 inventory, negative-stock policy, FIFO, returns, and BS parity."""

    def test_01_sale_within_stock_partial_and_negative_stock_policies(self):
        # Negative stock prohibited raises ValidationError cleanly without changing stock
        env_strict = _seed_inv_tenant("strict", open_stock=Decimal("3.00"), allow_negative=False)
        v_fail = SalesInvoiceService.generate_sales_invoice(
            company=env_strict["company"], user=env_strict["user"], party_ledger=env_strict["cust"],
            items_data=[{"product_id": env_strict["prod"].id, "quantity": 5, "rate": Decimal("200.00"), "gst_rate": Decimal("18.00")}],
            sales_ledger=env_strict["sales"], cgst_ledger=env_strict["cgst_out"], sgst_ledger=env_strict["sgst_out"],
            manual_voucher_date=datetime.date(2026, 5, 1),
        )
        with self.assertRaises(ValidationError):
            VoucherService.post_voucher(v_fail)
        env_strict["prod"].refresh_from_db()
        self.assertEqual(env_strict["prod"].stock_quantity, Decimal("3.00"))

        # Allowed negative stock (default policy) permits partial -> negative oversell & later purchase recovery
        env = _seed_inv_tenant("flex", open_stock=Decimal("3.00"), allow_negative=True)
        v_sale = SalesInvoiceService.generate_sales_invoice(
            company=env["company"], user=env["user"], party_ledger=env["cust"],
            items_data=[{"product_id": env["prod"].id, "quantity": 5, "rate": Decimal("200.00"), "gst_rate": Decimal("18.00")}],
            sales_ledger=env["sales"], cgst_ledger=env["cgst_out"], sgst_ledger=env["sgst_out"],
            manual_voucher_date=datetime.date(2026, 5, 2),
        )
        VoucherService.post_voucher(v_sale)
        env["prod"].refresh_from_db()
        self.assertEqual(env["prod"].stock_quantity, Decimal("-2.00"))

        # Balance Sheet clamps negative product stock valuation to 0.00 (zero negative asset)
        bs = FinancialStatementsService.generate_balance_sheet(env["company"], datetime.date(2027, 3, 31))
        self.assertTrue(bs["is_balanced"])

        # Purchase after negative stock restores positive quantity cleanly
        v_pur = PurchaseInvoiceService.generate_purchase_invoice(
            company=env["company"], user=env["user"], party_ledger=env["supp"],
            items_data=[{"product_id": env["prod"].id, "quantity": 10, "rate": Decimal("120.00"), "gst_rate": Decimal("18.00")}],
            purchase_ledger=env["purchase"], input_cgst_ledger=env["cgst_in"], input_sgst_ledger=env["sgst_in"],
            voucher_date=datetime.date(2026, 5, 3),
        )
        VoucherService.post_voucher(v_pur)
        env["prod"].refresh_from_db()
        self.assertEqual(env["prod"].stock_quantity, Decimal("8.00"))

    def test_02_fifo_lot_exhaustion_credit_note_cost_and_debit_note(self):
        env = _seed_inv_tenant("fifo", costing_method="FIFO", open_stock=Decimal("0.00"), allow_negative=True)
        p1 = PurchaseInvoiceService.generate_purchase_invoice(
            company=env["company"], user=env["user"], party_ledger=env["supp"],
            items_data=[{"product_id": env["prod"].id, "quantity": 5, "rate": Decimal("100.00"), "gst_rate": Decimal("18.00")}],
            purchase_ledger=env["purchase"], input_cgst_ledger=env["cgst_in"], input_sgst_ledger=env["sgst_in"],
            voucher_date=datetime.date(2026, 5, 1),
        )
        VoucherService.post_voucher(p1)
        p2 = PurchaseInvoiceService.generate_purchase_invoice(
            company=env["company"], user=env["user"], party_ledger=env["supp"],
            items_data=[{"product_id": env["prod"].id, "quantity": 5, "rate": Decimal("200.00"), "gst_rate": Decimal("18.00")}],
            purchase_ledger=env["purchase"], input_cgst_ledger=env["cgst_in"], input_sgst_ledger=env["sgst_in"],
            voucher_date=datetime.date(2026, 5, 2),
        )
        VoucherService.post_voucher(p2)

        s1 = SalesInvoiceService.generate_sales_invoice(
            company=env["company"], user=env["user"], party_ledger=env["cust"],
            items_data=[{"product_id": env["prod"].id, "quantity": 7, "rate": Decimal("300.00"), "gst_rate": Decimal("18.00")}],
            sales_ledger=env["sales"], cgst_ledger=env["cgst_out"], sgst_ledger=env["sgst_out"],
            manual_voucher_date=datetime.date(2026, 5, 3),
        )
        VoucherService.post_voucher(s1)
        out_entry = InventoryEntry.objects.get(voucher_id=s1.id, movement_type="OUT")
        # FIFO: 5 * 100 + 2 * 200 = 900.00
        self.assertEqual(out_entry.total_value, Decimal("900.00"))

        # Sales Return / Credit Note restores stock at original COGS unit acquisition cost (900/7 = 128.57), NOT selling price 300.00
        cn = CreditDebitNoteService.generate_credit_note(
            company=env["company"], user=env["user"], party_ledger=env["cust"],
            items_data=[{"product_id": env["prod"].id, "quantity": 2, "rate": Decimal("300.00"), "gst_rate": Decimal("18.00")}],
            original_invoice=s1,
            voucher_date=datetime.date(2026, 5, 4),
        )
        VoucherService.post_voucher(cn)
        cn_in = InventoryEntry.objects.get(voucher_id=cn.id, movement_type="IN")
        self.assertEqual(cn_in.rate, Decimal("128.57"))
        env["prod"].refresh_from_db()
        self.assertEqual(env["prod"].stock_quantity, Decimal("5.00"))

        # Purchase Return / Debit Note against p1 restores cost from p1 (100.00) and deducts 1 unit -> 4.00
        dn = CreditDebitNoteService.generate_debit_note(
            company=env["company"], user=env["user"], party_ledger=env["supp"],
            items_data=[{"product_id": env["prod"].id, "quantity": 1, "rate": Decimal("100.00"), "gst_rate": Decimal("18.00")}],
            original_invoice=p1,
            voucher_date=datetime.date(2026, 5, 5),
        )
        VoucherService.post_voucher(dn)
        dn_out = InventoryEntry.objects.get(voucher_id=dn.id, movement_type="OUT")
        self.assertEqual(dn_out.rate, Decimal("100.00"))
        env["prod"].refresh_from_db()
        self.assertEqual(env["prod"].stock_quantity, Decimal("4.00"))

        # Reversal of s1 restores stock back cleanly (+7 -> 11.00) and deletes s1 OUT entry
        VoucherService.create_reversal_voucher(s1, user=env["user"], reason="Reversal check")
        env["prod"].refresh_from_db()
        self.assertEqual(env["prod"].stock_quantity, Decimal("11.00"))
        self.assertEqual(InventoryEntry.objects.filter(voucher_id=s1.id).count(), 0)


class Stage415ConcurrentInventoryTests(TransactionTestCase):
    """Concurrent sales stock deduction integrity under PostgreSQL select_for_update()."""

    def test_concurrent_sales_deduct_stock_without_lost_update(self):
        env = _seed_inv_tenant("concinv", open_stock=Decimal("20.00"), allow_negative=True)

        def post_one(qty):
            close_old_connections()
            try:
                v = SalesInvoiceService.generate_sales_invoice(
                    company=env["company"], user=env["user"], party_ledger=env["cust"],
                    items_data=[{"product_id": env["prod"].id, "quantity": qty, "rate": Decimal("200.00"), "gst_rate": Decimal("18.00")}],
                    sales_ledger=env["sales"], cgst_ledger=env["cgst_out"], sgst_ledger=env["sgst_out"],
                    manual_voucher_date=datetime.date(2026, 5, 10),
                )
                VoucherService.post_voucher(v)
                return str(v.id)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            v_ids = list(pool.map(post_one, [3, 4]))

        self.assertEqual(len(v_ids), 2)
        env["prod"].refresh_from_db()
        self.assertEqual(env["prod"].stock_quantity, Decimal("13.00"))
        self.assertEqual(InventoryEntry.objects.filter(product=env["prod"], movement_type="OUT").count(), 2)

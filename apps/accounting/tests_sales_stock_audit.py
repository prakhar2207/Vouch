from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product, ProductCategory, Warehouse, InventoryEntry
from apps.accounting.models import Voucher, VoucherItem

class SalesInvoiceStockAuditTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(
            name="Apex Distribution",
            legal_name="Apex Distribution Pvt Ltd",
            gstin="27ABCDE1234F1Z5",
            state_code="27",
            financial_year_start="2026-04-01"
        )
        self.user = User.objects.create_user(email="admin@apex.com", password="Password123!")
        UserCompany.objects.create(user=self.user, company=self.company, role="OWNER")
        self.client.force_authenticate(user=self.user)

        # Ledgers
        debtors_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Sundry Debtors', defaults={'nature': 'ASSET'})
        self.customer = Ledger.objects.create(company=self.company, group=debtors_grp, name='Customer Alpha', ledger_type='DEBTOR', state_code='27')
        
        sales_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name='Sales Accounts', defaults={'nature': 'INCOME'})
        self.sales_ledger = Ledger.objects.create(company=self.company, group=sales_grp, name='Sales Account', ledger_type='SALES')

        # Product with initial stock of 100
        self.product = Product.objects.create(
            company=self.company,
            name="Industrial Valve 50mm",
            sku="VALVE-50",
            selling_price=Decimal("500.00"),
            purchase_price=Decimal("350.00"),
            stock_quantity=Decimal("100.00"),
            unit="PCS",
            gst_rate=Decimal("18.00")
        )

    def test_regular_stock_depletion_on_consecutive_sales(self):
        """Verify that stock decreases regularly with every sales invoice generated."""
        headers = {'HTTP_X_COMPANY_ID': str(self.company.id)}

        # Invoice 1: Sell 15 PCS
        payload_1 = {
            "company_id": str(self.company.id),
            "party_ledger_id": str(self.customer.id),
            "voucher_date": "2026-04-10",
            "items": [
                {
                    "product_id": str(self.product.id),
                    "quantity": 15,
                    "rate": 500.00,
                    "gst_rate": 18.00
                }
            ],
            "post_immediately": True
        }
        res1 = self.client.post("/api/v1/accounting/sales-invoice/", payload_1, format="json", **headers)
        self.assertEqual(res1.status_code, 201, res1.data)
        
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("85.00")) # 100 - 15 = 85

        # Check InventoryEntry audit trail
        entry1 = InventoryEntry.objects.filter(product=self.product, movement_type='OUT').order_by('-created_at').first()
        self.assertIsNotNone(entry1)
        self.assertEqual(entry1.quantity, Decimal("15.00"))

        # Invoice 2: Sell 25 PCS
        payload_2 = {
            "company_id": str(self.company.id),
            "party_ledger_id": str(self.customer.id),
            "voucher_date": "2026-04-11",
            "items": [
                {
                    "product_id": str(self.product.id),
                    "quantity": 25,
                    "rate": 500.00,
                    "gst_rate": 18.00
                }
            ],
            "post_immediately": True
        }
        res2 = self.client.post("/api/v1/accounting/sales-invoice/", payload_2, format="json", **headers)
        self.assertEqual(res2.status_code, 201, res2.data)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("60.00")) # 85 - 25 = 60

        # Invoice 3: Sell 10 PCS
        payload_3 = {
            "company_id": str(self.company.id),
            "party_ledger_id": str(self.customer.id),
            "voucher_date": "2026-04-12",
            "items": [
                {
                    "product_id": str(self.product.id),
                    "quantity": 10,
                    "rate": 500.00,
                    "gst_rate": 18.00
                }
            ],
            "post_immediately": True
        }
        res3 = self.client.post("/api/v1/accounting/sales-invoice/", payload_3, format="json", **headers)
        self.assertEqual(res3.status_code, 201, res3.data)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("50.00")) # 60 - 10 = 50

        # Verify that all 3 OUT entries exist in InventoryEntry
        out_entries = InventoryEntry.objects.filter(product=self.product, movement_type='OUT')
        self.assertEqual(out_entries.count(), 3)
        self.assertEqual(sum(e.quantity for e in out_entries), Decimal("50.00"))

        # Verify inventory API returns exact 50 stock
        inv_res = self.client.get(f"/api/v1/inventory/products/{self.company.id}/", **headers)
        self.assertEqual(inv_res.status_code, 200)
        prod_data = next(p for p in inv_res.data['data'] if p['id'] == str(self.product.id))
        self.assertEqual(Decimal(str(prod_data['stock_quantity'])), Decimal("50.00"))

    def test_draft_invoice_does_not_deplete_stock_until_posted(self):
        """A DRAFT sales invoice should NOT decrement stock until it is explicitly POSTED."""
        from apps.accounting.models import Voucher
        from apps.accounting.services.voucher_service import VoucherService

        headers = {'HTTP_X_COMPANY_ID': str(self.company.id)}

        payload = {
            "company_id": str(self.company.id),
            "party_ledger_id": str(self.customer.id),
            "voucher_date": "2026-04-10",
            "items": [
                {
                    "product_id": str(self.product.id),
                    "quantity": 10,
                    "rate": 500.00,
                    "gst_rate": 18.00
                }
            ],
            "post_immediately": False # Leave as DRAFT
        }
        res = self.client.post("/api/v1/accounting/sales-invoice/", payload, format="json", **headers)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'DRAFT')

        # Stock remains untouched at 100 while in DRAFT
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("100.00"))

        # Now post the draft voucher
        v_id = res.data['voucher_id']
        voucher = Voucher.objects.get(id=v_id)
        VoucherService.post_voucher(voucher)

        # Stock is now decremented by 10 to 90
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("90.00"))

    def test_cancelled_or_deleted_sales_invoice_restores_stock(self):
        """Cancelling or deleting a posted sales invoice restores the depleted stock."""
        headers = {'HTTP_X_COMPANY_ID': str(self.company.id)}

        payload = {
            "company_id": str(self.company.id),
            "party_ledger_id": str(self.customer.id),
            "voucher_date": "2026-04-10",
            "items": [
                {
                    "product_id": str(self.product.id),
                    "quantity": 20,
                    "rate": 500.00,
                    "gst_rate": 18.00
                }
            ],
            "post_immediately": True
        }
        res = self.client.post("/api/v1/accounting/sales-invoice/", payload, format="json", **headers)
        self.assertEqual(res.status_code, 201)
        v_id = res.data['voucher_id']

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("80.00")) # 100 - 20

        # Delete the voucher via API endpoint
        del_res = self.client.delete(f"/api/v1/accounting/vouchers/detail/{v_id}/", **headers)
        self.assertEqual(del_res.status_code, 200, del_res.data)

        # Stock is restored to 100
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, Decimal("100.00"))

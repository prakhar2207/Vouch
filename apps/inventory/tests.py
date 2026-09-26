from decimal import Decimal
from django.test import TestCase
from apps.companies.models import Company
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, VoucherItem
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.services.item_analytics_service import ItemAnalyticsService


class ItemAnalyticsServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Reorder Store")
        self.category = ProductCategory.objects.create(name="Belts", company=self.company)
        self.other_category = ProductCategory.objects.create(name="Bearings", company=self.company)

        # 1. High Velocity Item with Low Stock (should be in reorder recommendations)
        self.prod_low = Product.objects.create(
            name="C 90 Belt",
            sku="SKU-C90",
            company=self.company,
            category=self.category,
            stock_quantity=Decimal('0.00'),
            purchase_price=Decimal('500.00'),
            selling_price=Decimal('700.00')
        )

        # 2. High Velocity Item with High Stock (should NOT be in reorder recommendations)
        self.prod_high_stock = Product.objects.create(
            name="B 65 Belt",
            sku="SKU-B65",
            company=self.company,
            category=self.category,
            stock_quantity=Decimal('100.00'),
            purchase_price=Decimal('300.00'),
            selling_price=Decimal('450.00')
        )

        # 3. Deadstock Item with Low Stock (0 sales - should NOT be in reorder recommendations)
        self.prod_deadstock = Product.objects.create(
            name="Old Antique Belt",
            sku="SKU-ANTIQUE",
            company=self.company,
            category=self.category,
            stock_quantity=Decimal('1.00'),
            purchase_price=Decimal('200.00'),
            selling_price=Decimal('300.00')
        )

        # Create Ledger and Vouchers
        group, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name="Sundry Debtors",
            defaults={"nature": "ASSET"}
        )
        self.customer = Ledger.objects.create(
            company=self.company,
            name="Acme Corp",
            group=group,
            ledger_type="CUSTOMER"
        )

        from django.contrib.auth import get_user_model
        import datetime
        self.user = get_user_model().objects.create(email="testuser_reorder@example.com")

        # Sales Voucher for prod_low and prod_high_stock
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            status='POSTED',
            voucher_number='INV-001',
            voucher_date=datetime.date.today(),
            party_ledger=self.customer,
            created_by=self.user
        )

        VoucherItem.objects.create(
            voucher=voucher,
            product=self.prod_low,
            quantity=Decimal('10.00'),
            rate=Decimal('700.00'),
            taxable_amount=Decimal('7000.00'),
            total_amount=Decimal('7000.00')
        )

        VoucherItem.objects.create(
            voucher=voucher,
            product=self.prod_high_stock,
            quantity=Decimal('20.00'),
            rate=Decimal('450.00'),
            taxable_amount=Decimal('9000.00'),
            total_amount=Decimal('9000.00')
        )

    def test_reorder_recommendations_filters_deadstock_and_high_stock(self):
        result = ItemAnalyticsService.get_top_moving_items(self.company)

        self.assertIn("reorder_items", result)
        self.assertIn("categories", result)
        self.assertIn("top_sold", result)
        self.assertIn("top_purchased", result)

        reorder_names = [item["name"] for item in result["reorder_items"]]

        # C 90 has sales and stock <= 0 -> MUST be in reorder items
        self.assertIn("C 90 Belt", reorder_names)

        # B 65 has stock = 100 -> MUST NOT be in reorder items
        self.assertNotIn("B 65 Belt", reorder_names)

        # Old Antique Belt has 0 sales -> MUST NOT be in reorder items (Deadstock excluded)
        self.assertNotIn("Old Antique Belt", reorder_names)

        c90_item = next(item for item in result["reorder_items"] if item["name"] == "C 90 Belt")
        self.assertEqual(c90_item["urgency"], "OUT_OF_STOCK")
        self.assertGreaterEqual(c90_item["suggested_qty"], 5)

    def test_category_filtering(self):
        result_bearings = ItemAnalyticsService.get_top_moving_items(
            self.company, category_id=str(self.other_category.id)
        )
        self.assertEqual(len(result_bearings["reorder_items"]), 0)

        result_belts = ItemAnalyticsService.get_top_moving_items(
            self.company, category_id=str(self.category.id)
        )
        self.assertEqual(len(result_belts["reorder_items"]), 1)
        self.assertEqual(result_belts["reorder_items"][0]["name"], "C 90 Belt")

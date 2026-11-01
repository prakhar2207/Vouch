import os
import io
import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.inventory.models import (
    Product,
    ProductCategory,
    PriceListImportJob,
    PriceListExtractedItem,
    PriceHistory,
)
from apps.inventory.services.price_list_service import PriceListService
from apps.common.ocr_engine import OCRMemoryLimiter, PDFPageImageStreamer
from apps.audit.models import AuditLog
from apps.accounting.models import SyncEvent

User = get_user_model()


class PriceListIntegrityTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="inventory_auditor@vouch.test",
            password="testpassword123",
            first_name="Inventory",
            last_name="Auditor"
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name="Apex Belting Test Tenant",
            email="test_apex@vouch.test",
            gstin="07AAAAA0000A1Z5",
            state_code="07"
        )

        self.category = ProductCategory.objects.create(
            company=self.company,
            name="V-Belts",
            hsn_code="40103999",
            gst_rate=Decimal("18.00")
        )

        # Existing base products in inventory
        self.prod_a18 = Product.objects.create(
            company=self.company,
            category=self.category,
            name="A 18",
            brand="PIX",
            sku="A18-PIX-001",
            unit="PCS",
            selling_price=Decimal("120.00"),
            purchase_price=Decimal("80.00"),
            stock_quantity=Decimal("50.00"),
            description="PIX Classical A 18"
        )

        self.prod_1kg = Product.objects.create(
            company=self.company,
            category=self.category,
            name="Industrial Grease 1 kg",
            brand="SKF",
            sku="GREASE-1KG",
            unit="KG",
            selling_price=Decimal("450.00"),
            purchase_price=Decimal("320.00"),
            stock_quantity=Decimal("20.00"),
            description="SKF Lithium Grease 1kg pack"
        )

    def test_price_list_never_guesses_purchase_price_from_mrp(self):
        """
        Phase C Audit Invariant:
        When a price list contains only MRP / List Price, purchase_price must NOT
        be fabricated as 70% of MRP (remediation of the 70% purchase price defect).
        """
        csv_content = (
            "Item,MRP,Case Qty\n"
            "A 18,150.00,10\n"
            "A 19,160.00,10\n"
        ).encode('utf-8')

        job = PriceListService.create_import_job(
            company=self.company,
            category=self.category,
            brand="PIX",
            file_bytes=csv_content,
            filename="pix_mrp_catalog.csv",
            user=self.user
        )

        self.assertEqual(job.status, "REVIEW_REQUIRED")
        self.assertEqual(job.total_detected, 2)

        items = list(job.extracted_items.all().order_by('item_name'))
        item_a18 = items[0]
        self.assertEqual(item_a18.item_name, "A 18")
        self.assertEqual(item_a18.mrp, Decimal("150.00"))
        self.assertEqual(item_a18.selling_price, Decimal("150.00"))
        # Strict assertion: Purchase price must NOT be 70% of 150 (₹105.00)
        self.assertEqual(item_a18.purchase_price, Decimal("0.00"))

    def test_price_list_variant_isolation_different_pack_sizes(self):
        """
        Phase E Audit Invariant:
        Different packaging sizes (e.g. 1 kg vs 5 kg, or 500g vs 1L)
        must NEVER be merged into a single existing product.
        """
        csv_content = (
            "Item,MRP,Unit\n"
            "Industrial Grease 5 kg,2100.00,KG\n"
        ).encode('utf-8')

        job = PriceListService.create_import_job(
            company=self.company,
            category=self.category,
            brand="SKF",
            file_bytes=csv_content,
            filename="skf_grease.csv",
            user=self.user
        )

        item = job.extracted_items.first()
        # Must NOT match existing "Industrial Grease 1 kg"
        self.assertNotEqual(item.matched_product_id, self.prod_1kg.id)
        self.assertEqual(item.proposed_action, "CREATE_PRODUCT")
        self.assertIsNone(item.matched_product)

    def test_price_list_job_preview_before_commit_workflow(self):
        """
        Phase F Audit Invariant:
        Price changes must require explicit confirmation.
        Before commit, existing product prices are unchanged.
        After commit, products are updated and PriceHistory is recorded.
        """
        csv_content = (
            "Item,MRP,Selling Price\n"
            "A 18,140.00,140.00\n"
            "A 20,180.00,180.00\n"
        ).encode('utf-8')

        job = PriceListService.create_import_job(
            company=self.company,
            category=self.category,
            brand="PIX",
            file_bytes=csv_content,
            filename="pix_revised.csv",
            user=self.user
        )

        # Before commit: prod_a18 selling price must still be 120.00
        self.prod_a18.refresh_from_db()
        self.assertEqual(self.prod_a18.selling_price, Decimal("120.00"))

        # Commit job
        res = PriceListService.commit_import_job(
            job=job,
            update_selling_price=True,
            update_purchase_price=False,
            user=self.user
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["updated"], 1) # A 18 updated
        self.assertEqual(res["created"], 1) # A 20 created

        # After commit: prod_a18 selling price updated to 140.00
        self.prod_a18.refresh_from_db()
        self.assertEqual(self.prod_a18.selling_price, Decimal("140.00"))

        # Verify PriceHistory recorded
        history = PriceHistory.objects.filter(product=self.prod_a18).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_selling_price, Decimal("120.00"))
        self.assertEqual(history.new_selling_price, Decimal("140.00"))
        self.assertEqual(history.changed_by, self.user)

    def test_price_list_zero_inventory_quantity_corruption(self):
        """
        Phase G Audit Invariant:
        Price list imports must NEVER modify stock_quantity or alter accounting ledgers.
        """
        initial_stock = self.prod_a18.stock_quantity # 50.00

        items_data = [{
            "name": "A 18",
            "selling_price": "145.00",
            "mrp": "145.00",
            "opening_qty": 9999 # Malicious or erroneous stock qty in upload payload
        }]

        PriceListService.bulk_import_price_list(
            company=self.company,
            category_id=str(self.category.id),
            brand="PIX",
            items_data=items_data,
            user=self.user
        )

        self.prod_a18.refresh_from_db()
        # Stock quantity MUST remain 50.00, untouched by price list import
        self.assertEqual(self.prod_a18.stock_quantity, initial_stock)
        self.assertEqual(self.prod_a18.selling_price, Decimal("145.00"))

    def test_ocr_memory_limiter_concurrency_guard(self):
        """
        Phase H Audit Invariant:
        OCRMemoryLimiter restricts concurrency to 1 and enforces cleanup.
        """
        with OCRMemoryLimiter.guard("Test_Guard"):
            # Inside guard, acquiring again with timeout=0.01 must fail
            self.assertRaises(TimeoutError, lambda: OCRMemoryLimiter.guard("Nested_Guard", timeout=0.01).__enter__())

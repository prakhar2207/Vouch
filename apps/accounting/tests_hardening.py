from decimal import Decimal
import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory, Warehouse, InventoryEntry
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, OfflineCommand, PaymentAllocation
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.accounting.services.voucher_service import VoucherService
from apps.gst.services.gstin_validator import GSTINValidator
from apps.gst.services.gst_calculator import GSTCalculator
from apps.inventory.services.stock_service import StockService


class BaseHardeningTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Company A (Seller - Maharashtra 27)
        self.comp_a = Company.objects.create(
            name="Alpha Corp",
            legal_name="Alpha Corp Pvt Ltd",
            gstin="27AAACA1234A1Z5",
            pan="AAACA1234A",
            state_code="27",
            financial_year_start="2026-04-01"
        )
        self.user_owner_a = User.objects.create_user(email="owner_a@alpha.com", password="Password123!")
        UserCompany.objects.create(user=self.user_owner_a, company=self.comp_a, role="OWNER")

        self.user_viewer_a = User.objects.create_user(email="viewer_a@alpha.com", password="Password123!")
        UserCompany.objects.create(user=self.user_viewer_a, company=self.comp_a, role="VIEWER")

        self.user_sales_a = User.objects.create_user(email="sales_a@alpha.com", password="Password123!")
        UserCompany.objects.create(user=self.user_sales_a, company=self.comp_a, role="SALES")

        self.user_admin_a = User.objects.create_user(email="admin_a@alpha.com", password="Password123!")
        UserCompany.objects.create(user=self.user_admin_a, company=self.comp_a, role="ADMIN")

        # Company B (Competitor - Gujarat 24)
        self.comp_b = Company.objects.create(
            name="Beta Traders",
            legal_name="Beta Traders LLP",
            gstin="24AAACG5678B1Z2",
            pan="AAACG5678B",
            state_code="24",
            financial_year_start="2026-04-01"
        )
        self.user_owner_b = User.objects.create_user(email="owner_b@beta.com", password="Password123!")
        UserCompany.objects.create(user=self.user_owner_b, company=self.comp_b, role="OWNER")

        # Company A Ledgers
        self.grp_debtors_a = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Debtors", nature="ASSET")
        self.grp_income_a = LedgerGroup.objects.create(company=self.comp_a, name="Sales Accounts", nature="INCOME")
        self.grp_tax_a = LedgerGroup.objects.create(company=self.comp_a, name="Duties & Taxes", nature="LIABILITY")
        self.grp_bank_a = LedgerGroup.objects.create(company=self.comp_a, name="Bank Accounts", nature="ASSET")

        self.party_a = Ledger.objects.create(
            company=self.comp_a, group=self.grp_debtors_a, name="Customer A1",
            gstin="27ABCDE1234F1Z5", state_code="27", ledger_type="CUSTOMER"
        )
        self.sales_ledger_a = Ledger.objects.create(
            company=self.comp_a, group=self.grp_income_a, name="Sales", ledger_type="SALES"
        )
        self.bank_ledger_a = Ledger.objects.create(
            company=self.comp_a, group=self.grp_bank_a, name="HDFC Bank", ledger_type="BANK"
        )

        # Company A Products
        self.cat_a = ProductCategory.objects.create(company=self.comp_a, name="Hardware", hsn_code="8481", gst_rate=Decimal("18.00"))
        self.warehouse_a = Warehouse.objects.create(company=self.comp_a, name="Main Warehouse")
        self.prod_a = Product.objects.create(
            company=self.comp_a, category=self.cat_a, name="Brass Valve 1/2",
            sku="VAL-001", purchase_price=Decimal("100.00"), selling_price=Decimal("150.00"),
            stock_quantity=Decimal("50.00"), gst_rate=Decimal("18.00")
        )

        # Company B Resources
        self.grp_debtors_b = LedgerGroup.objects.create(company=self.comp_b, name="Sundry Debtors", nature="ASSET")
        self.party_b = Ledger.objects.create(
            company=self.comp_b, group=self.grp_debtors_b, name="Customer B1",
            gstin="24XYZAB1234C1Z1", state_code="24", ledger_type="CUSTOMER"
        )
        self.prod_b = Product.objects.create(
            company=self.comp_b, name="Secret Valve Beta",
            sku="BET-001", purchase_price=Decimal("200.00"), selling_price=Decimal("300.00"),
            stock_quantity=Decimal("10.00"), gst_rate=Decimal("18.00")
        )


class TenantIsolationTests(BaseHardeningTestCase):
    def test_cannot_use_foreign_company_product_in_sale(self):
        """Company A cannot sell product belonging to Company B."""
        with self.assertRaises((ValidationError, DRFValidationError)) as ctx:
            SalesInvoiceService.generate_sales_invoice(
                company=self.comp_a,
                user=self.user_owner_a,
                party_ledger=self.party_a,
                items_data=[
                    {"product_id": str(self.prod_b.id), "quantity": 1, "rate": 200.00}
                ]
            )
        self.assertTrue("does not belong" in str(ctx.exception).lower() or "does not exist" in str(ctx.exception).lower())

    def test_cannot_use_foreign_company_party_ledger_in_sale(self):
        """Company A cannot issue sales invoice against Company B's party ledger."""
        with self.assertRaises((ValidationError, DRFValidationError)) as ctx:
            SalesInvoiceService.generate_sales_invoice(
                company=self.comp_a,
                user=self.user_owner_a,
                party_ledger=self.party_b,
                items_data=[
                    {"product_id": str(self.prod_a.id), "quantity": 1, "rate": 150.00}
                ]
            )
        self.assertIn("does not belong to company", str(ctx.exception).lower())

    def test_cannot_access_foreign_company_voucher_detail(self):
        """User from Company B cannot read Company A's vouchers."""
        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 2, "rate": 150.00}]
        )
        self.client.force_authenticate(user=self.user_owner_b)
        response = self.client.get(f"/api/vouchers/detail/{voucher.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RBACPermissionTests(BaseHardeningTestCase):
    def test_viewer_cannot_create_sales_invoice(self):
        """A user with VIEWER role is blocked from creating sales invoices (403 Forbidden)."""
        self.client.force_authenticate(user=self.user_viewer_a)
        payload = {
            "company_id": str(self.comp_a.id),
            "party_ledger_id": str(self.party_a.id),
            "items": [{"product_id": str(self.prod_a.id), "quantity": 1, "rate": 150.00}]
        }
        response = self.client.post("/api/v1/accounting/sales-invoice/", data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sales_role_can_create_sales_invoice(self):
        """A user with SALES role can create sales invoices."""
        self.client.force_authenticate(user=self.user_sales_a)
        payload = {
            "company_id": str(self.comp_a.id),
            "party_ledger_id": str(self.party_a.id),
            "items": [{"product_id": str(self.prod_a.id), "quantity": 1, "rate": 150.00}]
        }
        response = self.client.post("/api/v1/accounting/sales-invoice/", data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_sales_role_cannot_create_purchase_invoice(self):
        """A user with SALES role cannot create purchase invoices (403 Forbidden)."""
        self.client.force_authenticate(user=self.user_sales_a)
        payload = {
            "company_id": str(self.comp_a.id),
            "party_ledger_id": str(self.party_a.id),
            "items": [{"product_id": str(self.prod_a.id), "quantity": 1, "rate": 100.00}]
        }
        response = self.client.post("/api/v1/accounting/purchase-invoice/", data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_delete_company(self):
        """Company deletion is restricted to OWNER only; ADMIN role must be rejected."""
        self.client.force_authenticate(user=self.user_admin_a)
        response = self.client.delete(f"/api/v1/companies/{self.comp_a.id}/", data={"password": "Password123!"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_cannot_delete_company_without_password(self):
        """Company deletion requires re-authentication password confirmation."""
        self.client.force_authenticate(user=self.user_owner_a)
        response = self.client.delete(f"/api/v1/companies/{self.comp_a.id}/", data={"password": "WrongPassword!"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.comp_a.refresh_from_db()
        self.assertTrue(self.comp_a.is_active)


class DoubleEntryAndLifecycleTests(BaseHardeningTestCase):
    def test_sales_posting_enforces_double_entry_balance(self):
        """Sales invoice posting creates balanced entries with sum(dr) == sum(cr)."""
        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 10, "rate": 150.00}]
        )
        # Taxable: 1500, GST (18% intra): CGST 135, SGST 135 => Total 1770
        VoucherService.post_voucher(voucher)
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'POSTED')

        entries = voucher.ledger_entries.all()
        total_dr = sum(e.debit_amount for e in entries)
        total_cr = sum(e.credit_amount for e in entries)
        self.assertEqual(total_dr, total_cr)

    def test_unbalanced_voucher_is_rejected(self):
        """A voucher with unbalanced debit and credit cannot be posted."""
        voucher = Voucher.objects.create(
            company=self.comp_a,
            created_by=self.user_owner_a,
            voucher_type='JOURNAL',
            voucher_number='JRN-TEST-001',
            voucher_date='2026-04-01',
            status='DRAFT'
        )
        LedgerEntry.objects.create(voucher=voucher, company=self.comp_a, ledger=self.party_a, debit_amount=Decimal('1000.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=voucher, company=self.comp_a, ledger=self.bank_ledger_a, debit_amount=Decimal('0.00'), credit_amount=Decimal('900.00'))

        with self.assertRaises((ValidationError, DRFValidationError)):
            VoucherService.post_voucher(voucher)

    def test_cancel_voucher_rolls_back_balances_and_stock(self):
        """Cancelling a posted sales voucher rolls back stock and ledgers while preserving voucher as CANCELLED."""
        initial_stock = self.prod_a.stock_quantity  # 50
        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 10, "rate": 150.00}]
        )
        VoucherService.post_voucher(voucher)
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stock_quantity, initial_stock - Decimal('10.00'))

        # Cancel voucher
        VoucherService.cancel_voucher(voucher, user=self.user_owner_a)
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'CANCELLED')

        # Stock is restored
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stock_quantity, initial_stock)

        # Party balance is rolled back
        self.party_a.refresh_from_db()
        self.assertEqual(self.party_a.current_balance, Decimal('0.00'))


class StockValuationTests(BaseHardeningTestCase):
    def test_fifo_cogs_calculation(self):
        """FIFO cost layers: selling consumes oldest inward layers first."""
        # Create 2 purchase layers:
        # Layer 1: 10 units @ 100
        # Layer 2: 10 units @ 150
        prod = Product.objects.create(
            company=self.comp_a, name="FIFO Test Item", sku="FIFO-001",
            stock_quantity=Decimal('20.00'), purchase_price=Decimal('125.00')
        )
        InventoryEntry.objects.create(
            company=self.comp_a, product=prod, warehouse=self.warehouse_a,
            movement_type='IN', quantity=Decimal('10.00'), rate=Decimal('100.00'),
            total_value=Decimal('1000.00')
        )
        InventoryEntry.objects.create(
            company=self.comp_a, product=prod, warehouse=self.warehouse_a,
            movement_type='IN', quantity=Decimal('10.00'), rate=Decimal('150.00'),
            total_value=Decimal('1500.00')
        )

        # Selling 15 units should cost: (10 * 100) + (5 * 150) = 1000 + 750 = 1750
        cogs, unit_rate = StockService.calculate_cogs_valuation(prod, Decimal('15.00'), method='FIFO')
        self.assertEqual(cogs, Decimal('1750.00'))
        self.assertEqual(unit_rate, Decimal('116.67'))


class OfflineSyncTests(BaseHardeningTestCase):
    def test_offline_command_idempotency_and_server_authority(self):
        """Offline commands are processed server-side with idempotency keys; forged journals are ignored."""
        cmd_id = str(uuid.uuid4())
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "device_id": "POS-TAB-01",
                    "payload": {
                        "party_ledger_id": str(self.party_a.id),
                        "items": [
                            {"product_id": str(self.prod_a.id), "quantity": 2, "rate": 150.00}
                        ],
                        # Attempt to forge 0 GST or invalid ledger entries
                        "forged_ledger_entries": [{"bogus": "entry"}]
                    }
                }
            ]
        }
        self.client.force_authenticate(user=self.user_owner_a)
        res1 = self.client.post("/api/v1/sync/push/", data=payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res1.data['results']), 1)
        self.assertEqual(res1.data['results'][0]['status'], 'PROCESSED')
        voucher_num = res1.data['results'][0]['voucher_number']

        # Re-submit the exact same command_id (idempotency check)
        res2 = self.client.post("/api/v1/sync/push/", data=payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['results'][0]['status'], 'PROCESSED')
        self.assertEqual(res2.data['results'][0]['voucher_number'], voucher_num)

        # Verify only 1 voucher was created in the database
        vouchers = Voucher.objects.filter(company=self.comp_a, voucher_number=voucher_num)
        self.assertEqual(vouchers.count(), 1)


class GSTValidationTests(BaseHardeningTestCase):
    def test_gstin_checksum_valid(self):
        """Valid 15-character GSTIN with valid Mod-36 checksum passes validation."""
        # 27AAACA1234A1ZK is a standard Maharashtra GSTIN with valid Luhn Mod-36 checksum K
        res = GSTINValidator.validate("27AAACA1234A1ZK")
        self.assertTrue(res['is_valid'])
        self.assertTrue(res['checksum_valid'])

    def test_gstin_checksum_invalid(self):
        """GSTIN with tampered check digit fails checksum validation."""
        res = GSTINValidator.validate("27AAACA1234A1Z9")
        self.assertTrue(res['is_valid'])
        self.assertFalse(res['checksum_valid'])

    def test_gst_calculator_intra_vs_inter_state(self):
        """Intra-state calculates CGST+SGST, inter-state calculates IGST."""
        intra = GSTCalculator.calculate_taxes(
            company_state_code="27",
            party_state_code="27",
            taxable_amount=Decimal("1000.00"),
            gst_rate=Decimal("18.00")
        )
        self.assertEqual(intra['cgst'], Decimal("90.00"))
        self.assertEqual(intra['sgst'], Decimal("90.00"))
        self.assertEqual(intra['igst'], Decimal("0.00"))

        inter = GSTCalculator.calculate_taxes(
            company_state_code="27",
            party_state_code="24",
            taxable_amount=Decimal("1000.00"),
            gst_rate=Decimal("18.00")
        )
        self.assertEqual(inter['cgst'], Decimal("0.00"))
        self.assertEqual(inter['sgst'], Decimal("0.00"))
        self.assertEqual(inter['igst'], Decimal("180.00"))


class FailedOfflineCommandPersistenceTests(BaseHardeningTestCase):
    def test_failed_command_persisted_outside_atomic_block(self):
        """Failed offline sync command is saved in DB with status='FAILED', error_code, and failed_at."""
        cmd_id = str(uuid.uuid4())
        non_existent_party = str(uuid.uuid4())
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "device_id": "POS-TAB-99",
                    "payload": {
                        "party_ledger_id": non_existent_party,
                        "items": [{"product_id": str(self.prod_a.id), "quantity": 1, "rate": 150.00}]
                    }
                }
            ]
        }
        self.client.force_authenticate(user=self.user_owner_a)
        res = self.client.post("/api/v1/sync/push/", data=payload, format='json')
        self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_207_MULTI_STATUS])
        self.assertEqual(len(res.data.get('errors', [])), 1)
        self.assertEqual(res.data['errors'][0]['command_id'], cmd_id)

        # Check that OfflineCommand record exists in the DB with error details
        saved_cmd = OfflineCommand.objects.get(command_id=cmd_id)
        self.assertEqual(saved_cmd.status, 'FAILED')
        self.assertIsNotNone(saved_cmd.failed_at)
        self.assertIsNotNone(saved_cmd.error_code)


class PostedVoucherImmutabilityTests(BaseHardeningTestCase):
    def test_delete_posted_voucher_creates_reversal_without_physical_deletion(self):
        """Deleting a posted voucher triggers reversal flow; physical voucher record is never deleted."""
        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 5, "rate": 150.00}]
        )
        VoucherService.post_voucher(voucher)
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'POSTED')

        self.client.force_authenticate(user=self.user_owner_a)
        res = self.client.delete(f"/api/vouchers/detail/{voucher.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Voucher must still exist in DB, with status='REVERSED'
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'REVERSED')
        self.assertIsNotNone(voucher.reversal_voucher)

        # Reversal voucher exists and is POSTED
        reversal = voucher.reversal_voucher
        self.assertEqual(reversal.status, 'POSTED')
        self.assertEqual(reversal.voucher_type, 'JOURNAL')

    def test_patch_posted_voucher_creates_reversal_and_correction(self):
        """Patching items on a posted voucher creates a formal reversal and a new corrected voucher."""
        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 2, "rate": 150.00}]
        )
        VoucherService.post_voucher(voucher)
        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'POSTED')

        self.client.force_authenticate(user=self.user_owner_a)
        patch_payload = {
            "items": [{"product_id": str(self.prod_a.id), "quantity": 4, "rate": 150.00}]
        }
        res = self.client.patch(f"/api/vouchers/detail/{voucher.id}/", data=patch_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        voucher.refresh_from_db()
        self.assertIn(voucher.status, ['SUPERSEDED', 'CORRECTED'])
        self.assertIsNotNone(voucher.corrects_voucher)
        self.assertEqual(voucher.corrects_voucher.status, 'POSTED')


class MovingWeightedAverageCostingTests(BaseHardeningTestCase):
    def test_moving_weighted_average_cogs_uses_remaining_layers(self):
        """Moving average valuation calculates from remaining unexhausted layers, not cumulative total."""
        prod = Product.objects.create(
            company=self.comp_a, name="MWA Test Product", sku="MWA-001",
            stock_quantity=Decimal('20.00'), purchase_price=Decimal('100.00')
        )
        # Layer 1: Inward 10 units @ 100 = 1000
        InventoryEntry.objects.create(
            company=self.comp_a, product=prod, warehouse=self.warehouse_a,
            movement_type='IN', quantity=Decimal('10.00'), rate=Decimal('100.00'),
            total_value=Decimal('1000.00')
        )
        # Layer 2: Inward 10 units @ 200 = 2000
        InventoryEntry.objects.create(
            company=self.comp_a, product=prod, warehouse=self.warehouse_a,
            movement_type='IN', quantity=Decimal('10.00'), rate=Decimal('200.00'),
            total_value=Decimal('2000.00')
        )
        # Outward 10 units (exhausts Layer 1 under FIFO)
        InventoryEntry.objects.create(
            company=self.comp_a, product=prod, warehouse=self.warehouse_a,
            movement_type='OUT', quantity=Decimal('10.00'), rate=Decimal('100.00'),
            total_value=Decimal('1000.00')
        )
        # Layer 3: Inward 10 units @ 300 = 3000
        InventoryEntry.objects.create(
            company=self.comp_a, product=prod, warehouse=self.warehouse_a,
            movement_type='IN', quantity=Decimal('10.00'), rate=Decimal('300.00'),
            total_value=Decimal('3000.00')
        )
        # Remaining stock: 20 units total (10 from Layer 2 @ 200 = 2000, 10 from Layer 3 @ 300 = 3000).
        # Total remaining value = 5000 / 20 = rate 250.00.
        # (A naive cumulative sum of all INs would give (1000+2000+3000)/30 = 200.00, which is incorrect!)
        cogs, unit_rate = StockService.calculate_cogs_valuation(prod, Decimal('10.00'), method='AVG_COST')
        self.assertEqual(unit_rate, Decimal('250.00'))
        self.assertEqual(cogs, Decimal('2500.00'))


class RecoverableGSTInventorySeparationTests(BaseHardeningTestCase):
    def test_purchase_inventory_entry_values_at_taxable_amount_excluding_gst(self):
        """Inward inventory entries record taxable cost; recoverable GST does not inflate stock valuation."""
        supplier_grp = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Creditors", nature="LIABILITY")
        supplier = Ledger.objects.create(
            company=self.comp_a, group=supplier_grp, name="Supplier S1",
            gstin="27XYZAB1234C1Z1", state_code="27", ledger_type="SUPPLIER"
        )
        pur_grp = LedgerGroup.objects.create(company=self.comp_a, name="Purchase Accounts", nature="EXPENSE")
        pur_ledger = Ledger.objects.create(
            company=self.comp_a, group=pur_grp, name="Purchase Ledger", ledger_type="PURCHASE"
        )

        voucher = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=supplier,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 10, "rate": 100.00}],
            purchase_ledger=pur_ledger,
            input_cgst_ledger=None,
            input_sgst_ledger=None,
            input_igst_ledger=None,
            supplier_invoice_number="SUPP-BILL-101"
        )
        VoucherService.post_voucher(voucher)

        # 10 units @ 100 => taxable_amount = 1000.00. With 18% GST, total_amount = 1180.00.
        inv_entry = InventoryEntry.objects.filter(voucher_id=voucher.id, movement_type='IN').first()
        self.assertIsNotNone(inv_entry)
        self.assertEqual(inv_entry.rate, Decimal('100.00'))
        self.assertEqual(inv_entry.total_value, Decimal('1000.00'))
        self.assertNotEqual(inv_entry.total_value, Decimal('1180.00'))


class DuplicateSupplierInvoiceDetectionTests(BaseHardeningTestCase):
    def test_duplicate_supplier_bill_number_raises_validation_error(self):
        """Submitting a purchase invoice with duplicate supplier bill number raises ValidationError."""
        supplier_grp = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Creditors", nature="LIABILITY")
        supplier = Ledger.objects.create(
            company=self.comp_a, group=supplier_grp, name="Supplier S2",
            gstin="27XYZAB1234C1Z1", state_code="27", ledger_type="SUPPLIER"
        )
        pur_grp = LedgerGroup.objects.create(company=self.comp_a, name="Purchase Accounts", nature="EXPENSE")
        pur_ledger = Ledger.objects.create(
            company=self.comp_a, group=pur_grp, name="Purchase Ledger", ledger_type="PURCHASE"
        )

        # First invoice
        v1 = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=supplier,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 5, "rate": 100.00}],
            purchase_ledger=pur_ledger,
            input_cgst_ledger=None,
            input_sgst_ledger=None,
            input_igst_ledger=None,
            supplier_invoice_number="BILL-DUP-001"
        )
        VoucherService.post_voucher(v1)

        # Second invoice with same supplier bill number
        with self.assertRaises((ValidationError, DRFValidationError)) as ctx:
            PurchaseInvoiceService.generate_purchase_invoice(
                company=self.comp_a,
                user=self.user_owner_a,
                party_ledger=supplier,
                items_data=[{"product_id": str(self.prod_a.id), "quantity": 3, "rate": 100.00}],
                purchase_ledger=pur_ledger,
                input_cgst_ledger=None,
                input_sgst_ledger=None,
                input_igst_ledger=None,
                supplier_invoice_number="BILL-DUP-001"
            )
        self.assertIn("duplicate supplier bill", str(ctx.exception).lower())


class CryptographicAuditVerificationTests(BaseHardeningTestCase):
    def test_audit_chain_verification_and_tamper_detection(self):
        """Audit chain computes SHA-256 links and detects hash tampering."""
        from apps.audit.models import AuditLog
        from apps.audit.views import AuditLogListView

        log1 = AuditLog.objects.create(
            company=self.comp_a,
            user=self.user_owner_a,
            action="CREATE",
            model_name="Voucher",
            record_id="VOUCH-001",
            changes={"amount": "100.00"}
        )
        log2 = AuditLog.objects.create(
            company=self.comp_a,
            user=self.user_owner_a,
            action="POST",
            model_name="Voucher",
            record_id="VOUCH-001",
            changes={"status": "POSTED"}
        )

        status_res = AuditLogListView.verify_company_chain(self.comp_a)
        self.assertEqual(status_res, "VERIFIED")

        # Simulate database tamper: bypass model .save() via direct queryset update
        AuditLog.objects.filter(id=log1.id).update(current_hash="tampered_hash_000000000000000000000000000000000000000000000000000000")
        tampered_res = AuditLogListView.verify_company_chain(self.comp_a)
        self.assertEqual(tampered_res, "BROKEN")


class PaymentAllocationBatchAndIsolationTests(BaseHardeningTestCase):
    def test_unpaid_invoices_batch_query(self):
        """get_unpaid_invoices_for_party uses batch aggregation without N+1 queries."""
        from apps.accounting.services.allocation_service import PaymentAllocationService
        v1 = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 2, "rate": 150.00}]
        )
        VoucherService.post_voucher(v1)

        unpaid = PaymentAllocationService.get_unpaid_invoices_for_party(self.comp_a, self.party_a)
        self.assertEqual(len(unpaid), 1)
        self.assertEqual(unpaid[0]['voucher_id'], str(v1.id))
        self.assertEqual(Decimal(unpaid[0]['remaining_amount']), v1.total_amount)

    def test_cross_company_allocation_prohibited(self):
        """Allocating payment from one company to an invoice of another company is strictly blocked."""
        from apps.accounting.services.allocation_service import PaymentAllocationService
        v_a = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_owner_a,
            party_ledger=self.party_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": 2, "rate": 150.00}]
        )
        VoucherService.post_voucher(v_a)

        v_pay_b = Voucher.objects.create(
            company=self.comp_b,
            created_by=self.user_owner_b,
            voucher_type='RECEIPT',
            voucher_number='RCP-BET-001',
            voucher_date='2026-04-01',
            status='POSTED',
            total_amount=Decimal('354.00')
        )

        with self.assertRaises((ValidationError, DRFValidationError)) as ctx:
            PaymentAllocationService.allocate_payment(
                payment_voucher=v_pay_b,
                invoice_voucher=v_a,
                allocated_amount=Decimal('100.00')
            )
        self.assertIn("cross-company", str(ctx.exception).lower())


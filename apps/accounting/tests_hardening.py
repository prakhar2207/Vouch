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

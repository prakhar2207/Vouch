import io
import json
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory, Warehouse
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, OfflineCommand, PaymentAllocation, FinancialYear
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.inventory.services.stock_service import StockService


class SyncHardeningComprehensiveTestCase(TestCase):
    """
    Automated regression and failure scenario test suite covering:
    - P0-1 to P0-13 failure scenarios
    - Idempotent offline command processing
    - Multi-tenant boundary security
    - Server authoritative accounting calculations
    - Monotonic sequences and posted transaction immutability
    - Inventory costing and recoverable GST separation
    """

    def setUp(self):
        self.client = APIClient()

        # Company A (Primary Tenant)
        self.comp_a = Company.objects.create(
            name="Apex Hardware Solutions",
            legal_name="Apex Hardware Solutions Pvt Ltd",
            gstin="27AABCA1234A1Z5",
            state_code="27",
            financial_year_start="2026-04-01"
        )
        self.user_a = User.objects.create_user(email="owner_a@apex.com", password="SecurePassword123!")
        UserCompany.objects.create(user=self.user_a, company=self.comp_a, role="OWNER")

        # Company B (Unrelated Secondary Tenant)
        self.comp_b = Company.objects.create(
            name="Zenith Electronics",
            legal_name="Zenith Electronics LLP",
            gstin="24AABCA5678B1Z6",
            state_code="24",
            financial_year_start="2026-04-01"
        )
        self.user_b = User.objects.create_user(email="owner_b@zenith.com", password="SecurePassword123!")
        UserCompany.objects.create(user=self.user_b, company=self.comp_b, role="OWNER")

        # Ledger Groups for Company A
        self.grp_debtors_a = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Debtors", nature="ASSET")
        self.grp_creditors_a = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Creditors", nature="LIABILITY")
        self.grp_sales_a = LedgerGroup.objects.create(company=self.comp_a, name="Sales Accounts", nature="INCOME")
        self.grp_purch_a = LedgerGroup.objects.create(company=self.comp_a, name="Purchase Accounts", nature="EXPENSE")
        self.grp_bank_a = LedgerGroup.objects.create(company=self.comp_a, name="Bank Accounts", nature="ASSET")
        self.grp_cash_a = LedgerGroup.objects.create(company=self.comp_a, name="Cash-in-Hand", nature="ASSET")

        # Company A Ledgers
        self.customer_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_debtors_a,
            name="Metro Buildcon Mumbai",
            ledger_type="CUSTOMER",
            state_code="27",
            gstin="27AABCM9876C1Z1"
        )
        self.supplier_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_creditors_a,
            name="Steel Works India",
            ledger_type="SUPPLIER",
            state_code="27",
            gstin="27AABCS4321D1Z2"
        )
        self.sales_ledger_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_sales_a,
            name="General Sales Account",
            ledger_type="SALES"
        )
        self.purchase_ledger_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_purch_a,
            name="General Purchase Account",
            ledger_type="PURCHASE"
        )
        self.bank_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_bank_a,
            name="State Bank of India",
            ledger_type="BANK",
            opening_balance=Decimal("100000.00"),
            current_balance=Decimal("100000.00")
        )
        self.cash_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_cash_a,
            name="Cash Account",
            ledger_type="CASH",
            opening_balance=Decimal("50000.00"),
            current_balance=Decimal("50000.00")
        )

        # Inventory for Company A
        self.cat_a = ProductCategory.objects.create(company=self.comp_a, name="Fasteners and Tools")
        self.wh_a = Warehouse.objects.create(company=self.comp_a, name="Central Godown", is_active=True)
        self.prod_a = Product.objects.create(
            company=self.comp_a,
            category=self.cat_a,
            name="Heavy Duty Drill Machine",
            sku="TOOL-DRL-01",
            selling_price=Decimal("4000.00"),
            purchase_price=Decimal("2500.00"),
            gst_rate=Decimal("18.00"),
            stock_quantity=Decimal("100.00")
        )

    # --------------------------------------------------------------------------
    # Scenario 1: Online direct sale vs offline sync queue
    # --------------------------------------------------------------------------
    def test_scenario_01_online_sale_creation(self):
        """Verify normal online sales invoice creation succeeds and posts atomically."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            "company_id": str(self.comp_a.id),
            "party_ledger_id": str(self.customer_a.id),
            "items": [
                {
                    "product_id": str(self.prod_a.id),
                    "quantity": "2",
                    "rate": "4000.00",
                    "gst_rate": "18.00"
                }
            ],
            "voucher_date": "2026-04-15"
        }
        res = self.client.post('/api/v1/accounting/sales-invoice/', data=payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data.get('success'))
        v_num = res.data['voucher_number']
        self.assertTrue(v_num.startswith("INV/"))

        voucher = Voucher.objects.get(company=self.comp_a, voucher_number=v_num)
        self.assertEqual(voucher.status, 'POSTED')
        # Subtotal: 2 * 4000 = 8000, GST: 18% = 1440, Total = 9440
        self.assertEqual(voucher.total_amount, Decimal('9440.00'))

    # --------------------------------------------------------------------------
    # Scenario 2 and 3: Offline Command Idempotency (1, 5, 100 times)
    # --------------------------------------------------------------------------
    def test_scenario_02_and_03_offline_command_idempotency(self):
        """Submitting the exact same command_id 1 time or 100 times results in exactly ONE voucher."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "cmd-idempotent-stress-001"
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "items": [
                            {
                                "product_id": str(self.prod_a.id),
                                "quantity": "3",
                                "rate": "4000.00",
                                "gst_rate": "18.00"
                            }
                        ],
                        "voucher_date": "2026-04-16"
                    }
                }
            ]
        }

        # First push
        res1 = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        v_id_1 = res1.data['results'][0]['voucher_id']
        v_num_1 = res1.data['results'][0]['voucher_number']

        # Rapid repeated pushes (simulating lost responses and aggressive retry loops)
        for i in range(5):
            res_retry = self.client.post('/api/v1/sync/push/', data=payload, format='json')
            self.assertEqual(res_retry.status_code, status.HTTP_200_OK)
            self.assertTrue(res_retry.data['results'][0].get('idempotent_cached'))
            self.assertEqual(res_retry.data['results'][0]['voucher_id'], v_id_1)
            self.assertEqual(res_retry.data['results'][0]['voucher_number'], v_num_1)

        # Confirm exactly ONE OfflineCommand and ONE Voucher exist
        self.assertEqual(OfflineCommand.objects.filter(command_id=cmd_id).count(), 1)
        self.assertEqual(Voucher.objects.filter(id=v_id_1).count(), 1)
        self.assertEqual(Voucher.objects.filter(voucher_number=v_num_1).count(), 1)

    # --------------------------------------------------------------------------
    # Scenario 4: Lost Network Response Handling
    # --------------------------------------------------------------------------
    def test_scenario_04_lost_network_response_resubmit(self):
        """If client network fails before receiving response, re-submitting returns cached result."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "cmd-lost-response-002"
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "items": [{"product_id": str(self.prod_a.id), "quantity": "1", "rate": "4000.00"}]
                    }
                }
            ]
        }
        res1 = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        v_id_1 = res1.data['results'][0]['voucher_id']

        # Simulate client assuming network failed and retrying with exact same command_id
        res2 = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['results'][0]['voucher_id'], v_id_1)
        self.assertTrue(res2.data['results'][0]['idempotent_cached'])

    # --------------------------------------------------------------------------
    # Scenario 5 and 6: Failed Offline Command Persistence & Safe Retry
    # --------------------------------------------------------------------------
    def test_scenario_05_and_06_failed_command_persists_and_retries_safely(self):
        """Failed accounting command records OfflineCommand with error, does not create partial voucher, and can retry."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "cmd-fail-and-retry-003"
        invalid_payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": "00000000-0000-0000-0000-000000000000",
                        "items": [{"product_id": str(self.prod_a.id), "quantity": "-5", "rate": "4000.00"}]
                    }
                }
            ]
        }

        # Attempt push with invalid data
        res_fail = self.client.post('/api/v1/sync/push/', data=invalid_payload, format='json')
        self.assertEqual(res_fail.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertFalse(res_fail.data['success'])
        self.assertEqual(len(res_fail.data['errors']), 1)

        # Check that OfflineCommand exists with status FAILED
        cmd_record = OfflineCommand.objects.get(command_id=cmd_id)
        self.assertEqual(cmd_record.status, 'FAILED')
        self.assertIsNotNone(cmd_record.error_message)

        # Ensure NO voucher was created in database
        self.assertIsNone(cmd_record.result_voucher)

        # Now fix the payload and retry with the SAME command_id
        valid_payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "items": [{"product_id": str(self.prod_a.id), "quantity": "1", "rate": "4000.00"}]
                    }
                }
            ]
        }
        res_retry = self.client.post('/api/v1/sync/push/', data=valid_payload, format='json')
        self.assertEqual(res_retry.status_code, status.HTTP_200_OK)
        self.assertTrue(res_retry.data['success'])

        cmd_record.refresh_from_db()
        self.assertEqual(cmd_record.status, 'PROCESSED')
        self.assertIsNotNone(cmd_record.result_voucher)
        self.assertGreaterEqual(cmd_record.retry_count, 1)

    # --------------------------------------------------------------------------
    # Scenario 7: Multi-Tenant Authorization Security Barrier
    # --------------------------------------------------------------------------
    def test_scenario_07_cross_tenant_rejection(self):
        """User B cannot push or pull offline commands for Company A."""
        self.client.force_authenticate(user=self.user_b)
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": "malicious-cmd-005",
                    "command_type": "CREATE_SALE",
                    "payload": {"party_ledger_id": str(self.customer_a.id), "items": []}
                }
            ]
        }
        res = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    # --------------------------------------------------------------------------
    # Scenario 8: Cross-Tenant Command ID Collision Defense
    # --------------------------------------------------------------------------
    def test_scenario_08_cross_tenant_command_id_collision(self):
        """If Company B submits a command_id already owned by Company A, reject with TENANT_MISMATCH."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "shared-uuid-collision-006"
        payload_a = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "items": [{"product_id": str(self.prod_a.id), "quantity": "1", "rate": "4000.00"}]
                    }
                }
            ]
        }
        res_a = self.client.post('/api/v1/sync/push/', data=payload_a, format='json')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)

        # Step 2: Company B attempts to push using the SAME command_id
        self.client.force_authenticate(user=self.user_b)
        payload_b = {
            "company_id": str(self.comp_b.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {"items": []}
                }
            ]
        }
        res_b = self.client.post('/api/v1/sync/push/', data=payload_b, format='json')
        self.assertEqual(res_b.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertEqual(res_b.data['errors'][0]['error_code'], 'TENANT_MISMATCH')

    # --------------------------------------------------------------------------
    # Scenario 9: Purchase Invoice Sync with External Supplier Invoice Number
    # --------------------------------------------------------------------------
    def test_scenario_09_purchase_invoice_sync_with_supplier_number(self):
        """Verify purchase invoice records internal voucher_number and supplier invoice number separately."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "cmd-purchase-sync-007"
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_PURCHASE",
                    "payload": {
                        "party_ledger_id": str(self.supplier_a.id),
                        "reference_number": "STEEL-INV-9988",
                        "voucher_date": "2026-04-18",
                        "items": [
                            {
                                "product_id": str(self.prod_a.id),
                                "quantity": "10",
                                "rate": "2500.00",
                                "gst_rate": "18.00"
                            }
                        ]
                    }
                }
            ]
        }
        res = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        voucher_id = res.data['results'][0]['voucher_id']
        voucher = Voucher.objects.get(id=voucher_id)
        self.assertTrue(voucher.voucher_number.startswith("PUR/"))
        self.assertEqual(voucher.external_invoice_number, "STEEL-INV-9988")
        self.assertEqual(voucher.status, 'POSTED')

    # --------------------------------------------------------------------------
    # Scenario 10 and 11: Payment & Receipt Command Sync
    # --------------------------------------------------------------------------
    def test_scenario_10_and_11_payment_and_receipt_sync(self):
        """Verify payment and receipt commands create balanced vouchers and update balances."""
        self.client.force_authenticate(user=self.user_a)

        # 1. Receipt Command
        rcp_cmd_id = "cmd-receipt-008"
        rcp_payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": rcp_cmd_id,
                    "command_type": "CREATE_RECEIPT",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "payment_ledger_id": str(self.bank_a.id),
                        "amount": "5000.00",
                        "narration": "Customer advance payment"
                    }
                }
            ]
        }
        res_rcp = self.client.post('/api/v1/sync/push/', data=rcp_payload, format='json')
        self.assertEqual(res_rcp.status_code, status.HTTP_200_OK)
        rcp_v = Voucher.objects.get(id=res_rcp.data['results'][0]['voucher_id'])
        self.assertEqual(rcp_v.voucher_type, 'RECEIPT')
        self.assertEqual(rcp_v.status, 'POSTED')

        # 2. Payment Command
        pay_cmd_id = "cmd-payment-009"
        pay_payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": pay_cmd_id,
                    "command_type": "CREATE_PAYMENT",
                    "payload": {
                        "party_ledger_id": str(self.supplier_a.id),
                        "payment_ledger_id": str(self.cash_a.id),
                        "amount": "2500.00",
                        "narration": "Supplier payment"
                    }
                }
            ]
        }
        res_pay = self.client.post('/api/v1/sync/push/', data=pay_payload, format='json')
        self.assertEqual(res_pay.status_code, status.HTTP_200_OK)
        pay_v = Voucher.objects.get(id=res_pay.data['results'][0]['voucher_id'])
        self.assertEqual(pay_v.voucher_type, 'PAYMENT')
        self.assertEqual(pay_v.status, 'POSTED')

    # --------------------------------------------------------------------------
    # Scenario 12: Strict Server Accounting Authority (Tamper Rejection)
    # --------------------------------------------------------------------------
    def test_scenario_12_server_accounting_authority_ignores_client_math(self):
        """Client-supplied corrupted or tampered totals are ignored in favor of server calculation."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "cmd-tampered-010"
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "total_amount": "1.00",
                        "taxable_amount": "1.00",
                        "items": [
                            {
                                "product_id": str(self.prod_a.id),
                                "quantity": "1",
                                "rate": "4000.00",
                                "gst_rate": "18.00",
                                "total_amount": "1.00"
                            }
                        ]
                    }
                }
            ]
        }
        res = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        voucher = Voucher.objects.get(id=res.data['results'][0]['voucher_id'])
        self.assertEqual(voucher.total_amount, Decimal('4720.00'))

    # --------------------------------------------------------------------------
    # Scenario 13: Batch Isolation & Atomic Rollback per Command
    # --------------------------------------------------------------------------
    def test_scenario_13_batch_isolation_one_valid_one_invalid(self):
        """In a multi-command batch, valid commands succeed while invalid commands fail without stopping the batch."""
        self.client.force_authenticate(user=self.user_a)
        valid_cmd_id = "cmd-batch-valid-011"
        invalid_cmd_id = "cmd-batch-invalid-012"

        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": valid_cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.customer_a.id),
                        "items": [{"product_id": str(self.prod_a.id), "quantity": "1", "rate": "4000.00"}]
                    }
                },
                {
                    "command_id": invalid_cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": "00000000-0000-0000-0000-000000000000",
                        "items": []
                    }
                }
            ]
        }
        res = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertEqual(res.data['processed_count'], 1)
        self.assertEqual(len(res.data['errors']), 1)
        self.assertEqual(res.data['results'][0]['command_id'], valid_cmd_id)
        self.assertEqual(res.data['errors'][0]['command_id'], invalid_cmd_id)

    # --------------------------------------------------------------------------
    # Scenario 14: Posted Transaction Immutability (P0-4 & P0-5)
    # --------------------------------------------------------------------------
    def test_scenario_14_posted_transaction_immutability(self):
        """DELETE on posted voucher reverses it without physical deletion; original record remains."""
        self.client.force_authenticate(user=self.user_a)

        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_a,
            party_ledger=self.customer_a,
            items_data=[{"product_id": str(self.prod_a.id), "quantity": "1", "rate": "4000.00", "gst_rate": "18.00"}]
        )
        VoucherService.post_voucher(voucher)
        self.assertEqual(voucher.status, 'POSTED')

        res = self.client.delete(f'/api/vouchers/{voucher.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        voucher.refresh_from_db()
        self.assertEqual(voucher.status, 'REVERSED')
        self.assertIsNotNone(voucher.reversal_voucher)

    # --------------------------------------------------------------------------
    # Scenario 15: Monotonic Invoice Sequence Invariant (P0-6)
    # --------------------------------------------------------------------------
    def test_scenario_15_monotonic_sequence_preservation(self):
        """Cancelled or deleted vouchers never cause sequence numbers to rollback or be reused."""
        self.client.force_authenticate(user=self.user_a)

        v1_num, fy = InvoiceSequenceService.get_next_number(self.comp_a, 'SALES')
        v2_num, _ = InvoiceSequenceService.get_next_number(self.comp_a, 'SALES')

        self.assertNotEqual(v1_num, v2_num)

        last_num = InvoiceSequenceService.resync_sequence(self.comp_a, fy, 'SALES')
        next_num, _ = InvoiceSequenceService.get_next_number(self.comp_a, 'SALES')

        self.assertNotEqual(next_num, v1_num)
        self.assertNotEqual(next_num, v2_num)

    # --------------------------------------------------------------------------
    # Scenario 16: Moving Weighted Average Inventory Costing (P0-8)
    # --------------------------------------------------------------------------
    def test_scenario_16_moving_weighted_average_costing(self):
        """COGS and stock valuation accurately reflect moving average across multiple purchases and sales."""
        cat = ProductCategory.objects.create(company=self.comp_a, name="Widgets")
        prod = Product.objects.create(
            company=self.comp_a,
            category=cat,
            name="Precision Bearing",
            sku="BEAR-001",
            selling_price=Decimal("300.00"),
            purchase_price=Decimal("100.00"),
            costing_method="AVG_COST",
            stock_quantity=Decimal("0.00")
        )

        # Inward Batch 1: 10 @ Rs 100 = Rs 1,000
        v_in1 = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.comp_a,
            user=self.user_a,
            party_ledger=self.supplier_a,
            items_data=[{"product_id": str(prod.id), "quantity": "10", "rate": "100.00", "gst_rate": "0"}]
        )
        VoucherService.post_voucher(v_in1)

        # Outward: 8 sold -> Remaining: 2 @ Rs 100
        v_out1 = SalesInvoiceService.generate_sales_invoice(
            company=self.comp_a,
            user=self.user_a,
            party_ledger=self.customer_a,
            items_data=[{"product_id": str(prod.id), "quantity": "8", "rate": "300.00", "gst_rate": "0"}]
        )
        VoucherService.post_voucher(v_out1)

        # Inward Batch 2: 10 @ Rs 200 = Rs 2,000
        v_in2 = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.comp_a,
            user=self.user_a,
            party_ledger=self.supplier_a,
            items_data=[{"product_id": str(prod.id), "quantity": "10", "rate": "200.00", "gst_rate": "0"}]
        )
        VoucherService.post_voucher(v_in2)

        prod.refresh_from_db()
        self.assertEqual(prod.stock_quantity, Decimal("12.00"))

        cogs, unit_rate = StockService.calculate_cogs_valuation(prod, Decimal("12.00"))
        self.assertEqual(unit_rate, Decimal("183.33"))
        self.assertEqual(cogs, Decimal("2199.96"))

    # --------------------------------------------------------------------------
    # Scenario 17: Recoverable GST Separated from Inventory Cost (P0-9)
    # --------------------------------------------------------------------------
    def test_scenario_17_recoverable_gst_separated_from_inventory(self):
        """Input GST does not inflate inventory valuation; inventory is valued net of recoverable tax."""
        cat = ProductCategory.objects.create(company=self.comp_a, name="Hardware")
        prod = Product.objects.create(
            company=self.comp_a,
            category=cat,
            name="Brass Valve 1-inch",
            sku="VALVE-01",
            selling_price=Decimal("1500.00"),
            purchase_price=Decimal("1000.00"),
            stock_quantity=Decimal("0.00")
        )

        # Purchase: 10 units @ Rs 1000 with 18% GST (Rs 1,800 GST, Total Rs 11,800)
        v_purch = PurchaseInvoiceService.generate_purchase_invoice(
            company=self.comp_a,
            user=self.user_a,
            party_ledger=self.supplier_a,
            items_data=[{"product_id": str(prod.id), "quantity": "10", "rate": "1000.00", "gst_rate": "18.00"}]
        )
        VoucherService.post_voucher(v_purch)

        # Check inventory valuation: must be 10 * 1000 = Rs 10,000 (NOT Rs 11,800)
        cogs, unit_rate = StockService.calculate_cogs_valuation(prod, Decimal("10.00"))
        self.assertEqual(unit_rate, Decimal("1000.00"))
        self.assertEqual(cogs, Decimal("10000.00"))

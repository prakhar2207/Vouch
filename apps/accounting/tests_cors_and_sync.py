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
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, LedgerEntry, OfflineCommand


class CorsAndSyncSprintTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Company A
        self.comp_a = Company.objects.create(
            name="Vouch Apex Technologies",
            legal_name="Vouch Apex Technologies Pvt Ltd",
            gstin="27AAACA1111A1Z1",
            state_code="27",
            financial_year_start="2026-04-01"
        )
        self.user_a = User.objects.create_user(email="tenant_a@vouch.com", password="Password123!")
        UserCompany.objects.create(user=self.user_a, company=self.comp_a, role="OWNER")

        # Company B (Unrelated tenant)
        self.comp_b = Company.objects.create(
            name="Vouch Blue Star Enterprises",
            legal_name="Vouch Blue Star Enterprises LLP",
            gstin="24AAACB2222B1Z2",
            state_code="24",
            financial_year_start="2026-04-01"
        )
        self.user_b = User.objects.create_user(email="tenant_b@vouch.com", password="Password123!")
        UserCompany.objects.create(user=self.user_b, company=self.comp_b, role="OWNER")

        # Company A Ledgers
        self.grp_debtors_a = LedgerGroup.objects.create(company=self.comp_a, name="Sundry Debtors", nature="ASSET")
        self.grp_sales_a = LedgerGroup.objects.create(company=self.comp_a, name="Sales Accounts", nature="INCOME")
        self.grp_bank_a = LedgerGroup.objects.create(company=self.comp_a, name="Bank Accounts", nature="ASSET")

        self.party_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_debtors_a,
            name="Alpha Retailers Mumbai",
            ledger_type="CUSTOMER",
            state_code="27",
            gstin="27AABCA5678B1Z5"
        )
        self.sales_ledger_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_sales_a,
            name="Domestic Sales Account",
            ledger_type="SALES"
        )
        self.bank_a = Ledger.objects.create(
            company=self.comp_a,
            group=self.grp_bank_a,
            name="HDFC Current Account",
            ledger_type="BANK"
        )

        self.cat_a = ProductCategory.objects.create(company=self.comp_a, name="Electronics")
        self.prod_a = Product.objects.create(
            company=self.comp_a,
            category=self.cat_a,
            name="Thermal POS Printer",
            sku="POS-PRN-01",
            selling_price=Decimal("5000.00"),
            purchase_price=Decimal("3500.00"),
            gst_rate=Decimal("18.00"),
            stock_quantity=Decimal("50.00")
        )

    # --------------------------------------------------------------------------
    # 1. CORS Verification
    # --------------------------------------------------------------------------
    def test_cors_preflight_production_origin(self):
        """Verify OPTIONS preflight succeeds with Access-Control-Allow-Origin for production frontend."""
        response = self.client.options(
            '/api/v1/companies/',
            HTTP_ORIGIN='https://vouch-pi-one.vercel.app',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type,x-company-id'
        )
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])
        self.assertEqual(response.get('Access-Control-Allow-Origin'), 'https://vouch-pi-one.vercel.app')
        self.assertEqual(response.get('Access-Control-Allow-Credentials'), 'true')
        allow_headers = response.get('Access-Control-Allow-Headers', '').lower()
        self.assertIn('authorization', allow_headers)
        self.assertIn('x-company-id', allow_headers)

    from django.test import override_settings

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGIN_REGEXES=[])
    def test_cors_disallowed_origin(self):
        """Verify unauthorized origins are rejected by CORS headers."""
        response = self.client.options(
            '/api/v1/companies/',
            HTTP_ORIGIN='https://unauthorized-malicious-site.com',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type'
        )
        self.assertNotEqual(response.get('Access-Control-Allow-Origin'), 'https://unauthorized-malicious-site.com')

    # --------------------------------------------------------------------------
    # 2. Offline Sync Dual Routes & Server Authoritative Execution
    # --------------------------------------------------------------------------
    def test_sync_push_creates_voucher_authoritatively(self):
        """Pushing an offline command calculates GST, creates voucher, and posts ledger entries server-side."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "test-cmd-unique-001"
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.party_a.id),
                        "items": [
                            {
                                "product_id": str(self.prod_a.id),
                                "quantity": "2",
                                "rate": "5000.00",
                                "gst_rate": "18.00"
                            }
                        ],
                        "narration": "Offline sales invoice test"
                    }
                }
            ]
        }
        # Test canonical route
        res = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        self.assertEqual(res.data.get('processed_count'), 1)

        result = res.data['results'][0]
        self.assertEqual(result['command_id'], cmd_id)
        self.assertEqual(result['status'], 'PROCESSED')
        voucher_id = result['voucher_id']

        # Verify Voucher in DB
        voucher = Voucher.objects.get(id=voucher_id)
        self.assertEqual(voucher.company, self.comp_a)
        self.assertEqual(voucher.status, 'POSTED')
        # Total = 2 * 5000 + 18% = 11800.00
        self.assertEqual(voucher.total_amount, Decimal('11800.00'))

        # Verify Ledger Entries (Double entry invariant: Debits == Credits)
        entries = LedgerEntry.objects.filter(voucher=voucher)
        self.assertTrue(entries.exists())
        total_debits = sum(e.debit_amount for e in entries)
        total_credits = sum(e.credit_amount for e in entries)
        self.assertEqual(total_debits, total_credits)
        
        # Verify Customer Debit entry equals invoice total amount
        party_entry = entries.filter(ledger=self.party_a).first()
        self.assertIsNotNone(party_entry)
        self.assertEqual(party_entry.debit_amount, Decimal('11800.00'))

    def test_sync_push_idempotency(self):
        """Sending the exact same command_id must not double-post or create duplicate vouchers."""
        self.client.force_authenticate(user=self.user_a)
        cmd_id = "test-cmd-idempotent-002"
        payload = {
            "company_id": str(self.comp_a.id),
            "commands": [
                {
                    "command_id": cmd_id,
                    "command_type": "CREATE_SALE",
                    "payload": {
                        "party_ledger_id": str(self.party_a.id),
                        "items": [
                            {
                                "product_id": str(self.prod_a.id),
                                "quantity": "1",
                                "rate": "5000.00",
                                "gst_rate": "18.00"
                            }
                        ]
                    }
                }
            ]
        }

        # First post
        res1 = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        v_id_1 = res1.data['results'][0]['voucher_id']

        # Second post with identical command_id
        res2 = self.client.post('/api/v1/sync/push/', data=payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        v_id_2 = res2.data['results'][0]['voucher_id']
        self.assertTrue(res2.data['results'][0].get('idempotent_cached'))
        self.assertEqual(v_id_1, v_id_2)

        # Confirm only ONE voucher was created
        cmd_records = OfflineCommand.objects.filter(command_id=cmd_id)
        self.assertEqual(cmd_records.count(), 1)
        vouchers = Voucher.objects.filter(narration__icontains=cmd_id)
        self.assertEqual(Voucher.objects.filter(id=v_id_1).count(), 1)

    def test_sync_dual_route_aliases(self):
        """Verify both /api/v1/sync/ and /api/v1/accounting/sync/ paths work properly."""
        self.client.force_authenticate(user=self.user_a)

        # Push to accounting namespace
        res_push = self.client.post(
            '/api/v1/accounting/sync/push/',
            data={
                "company_id": str(self.comp_a.id),
                "commands": [
                    {
                        "command_id": "test-cmd-alias-003",
                        "command_type": "CREATE_SALE",
                        "payload": {
                            "party_ledger_id": str(self.party_a.id),
                            "items": [{"product_id": str(self.prod_a.id), "quantity": "1", "rate": "1000"}]
                        }
                    }
                ]
            },
            format='json'
        )
        self.assertEqual(res_push.status_code, status.HTTP_200_OK)

        # Pull from both endpoints
        res_pull_1 = self.client.post('/api/v1/sync/pull/', data={"company_id": str(self.comp_a.id)}, format='json')
        res_pull_2 = self.client.post('/api/v1/accounting/sync/pull/', data={"company_id": str(self.comp_a.id)}, format='json')
        self.assertEqual(res_pull_1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pull_2.status_code, status.HTTP_200_OK)
        self.assertIn('changes', res_pull_1.data)
        self.assertIn('changes', res_pull_2.data)

    # --------------------------------------------------------------------------
    # 3. Multi-Tenant Authorization Security Barrier
    # --------------------------------------------------------------------------
    def test_multi_tenant_sync_security(self):
        """User B must be rejected when attempting to push or pull for Company A."""
        self.client.force_authenticate(user=self.user_b)

        # Pull attempt
        res_pull = self.client.post('/api/v1/sync/pull/', data={"company_id": str(self.comp_a.id)}, format='json')
        self.assertIn(res_pull.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # Push attempt
        res_push = self.client.post(
            '/api/v1/sync/push/',
            data={
                "company_id": str(self.comp_a.id),
                "commands": [
                    {
                        "command_id": "malicious-cmd-004",
                        "command_type": "CREATE_SALE",
                        "payload": {"party_ledger_id": str(self.party_a.id), "items": []}
                    }
                ]
            },
            format='json'
        )
        self.assertIn(res_push.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    # --------------------------------------------------------------------------
    # 4. Bank Statement Upload Boundary & Error Handling
    # --------------------------------------------------------------------------
    def test_bank_statement_upload_bad_file_returns_400(self):
        """Corrupt or invalid bank files return HTTP 400 with descriptive error, not 500."""
        self.client.force_authenticate(user=self.user_a)

        bad_file = io.BytesIO(b"random-garbage-non-tabular-bytes")
        bad_file.name = "corrupt_statement.csv"

        response = self.client.post(
            '/api/v1/accounting/banking/upload/',
            data={
                'file': bad_file,
                'bank_ledger_id': str(self.bank_a.id),
                'company_id': str(self.comp_a.id)
            },
            format='multipart',
            HTTP_X_COMPANY_ID=str(self.comp_a.id)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

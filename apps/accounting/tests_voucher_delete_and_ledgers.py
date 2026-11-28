import uuid
from decimal import Decimal
from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.gst.models import GSTReportingAllocation

User = get_user_model()


class VoucherDeleteAndLedgersQueryParamTests(TestCase):
    """
    Independent verification tests for:
    1. Ledgers endpoint query param matching (/api/v1/ledgers/?company_id=...&ledger_type=SUPPLIER)
    2. Voucher deletion with unfiled GSTReportingAllocation (no ProtectedError)
    3. Statutory preservation of filed/reported GSTReportingAllocation (blocks deletion with clear validation)
    4. Voucher PATCH updating discount_percent
    """

    def setUp(self):
        # Mandatory Test Isolation: Apex Belting & Industrial Store (Demo)
        self.sandbox_company_id = uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33')
        self.company, _ = Company.objects.get_or_create(
            id=self.sandbox_company_id,
            defaults={
                'name': 'Apex Belting & Industrial Store (Demo)',
                'gstin': '07AAAAA0000A1Z5',
                'state_code': '07'
            }
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "ABORT: Tests may ONLY run against Apex Belting Store sandbox!"
        )

        self.user, _ = User.objects.get_or_create(
            email='sandbox_tester@apexbelting.demo',
            defaults={'first_name': 'Sandbox', 'last_name': 'Tester'}
        )
        self.user.set_password('ApexTestPass123!')
        self.user.save()
        UserCompany.objects.get_or_create(
            user=self.user,
            company=self.company,
            defaults={'role': 'OWNER'}
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Setup ledger groups
        self.group_creditors, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Sundry Creditors',
            defaults={'nature': 'LIABILITY'}
        )
        self.group_debtors, _ = LedgerGroup.objects.get_or_create(
            company=self.company,
            name='Sundry Debtors',
            defaults={'nature': 'ASSET'}
        )

        # Setup ledgers
        self.supplier_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Satyam & Co.',
            defaults={
                'group': self.group_creditors,
                'ledger_type': 'SUPPLIER',
                'gstin': '07AAAAA1111A1Z1',
                'state_code': '07'
            }
        )
        self.customer_ledger, _ = Ledger.objects.get_or_create(
            company=self.company,
            name='Acme Retailers',
            defaults={
                'group': self.group_debtors,
                'ledger_type': 'CUSTOMER',
                'gstin': '07AAAAA2222A1Z2',
                'state_code': '07'
            }
        )

    def test_ledger_list_with_query_param_company_id(self):
        """GET /api/v1/ledgers/?company_id=... should return 200 (not 404)."""
        url = f"/api/v1/ledgers/?company_id={self.company.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        ledger_names = [l['name'] for l in response.data.get('data', [])]
        self.assertIn('Satyam & Co.', ledger_names)
        self.assertIn('Acme Retailers', ledger_names)

    def test_ledger_list_with_ledger_type_supplier_filter(self):
        """GET /api/v1/ledgers/?company_id=...&ledger_type=SUPPLIER returns only suppliers."""
        url = f"/api/v1/ledgers/?company_id={self.company.id}&ledger_type=SUPPLIER"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        data = response.data.get('data', [])
        ledger_names = [l['name'] for l in data]
        self.assertIn('Satyam & Co.', ledger_names)
        self.assertNotIn('Acme Retailers', ledger_names)

    def test_delete_voucher_with_unfiled_gst_allocation_succeeds(self):
        """
        When deleting an unfiled voucher that has an active/excluded GSTReportingAllocation,
        the allocation is safely cleaned up without raising ProtectedError.
        """
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-TEST-DEL-01',
            voucher_date=date(2026, 11, 26),
            party_ledger=self.supplier_ledger,
            status='POSTED',
            total_amount=Decimal('1000.00'),
            created_by=self.user
        )
        allocation = GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=voucher,
            event_type='INWARD_ITC',
            voucher_date=date(2026, 11, 26),
            original_period='112026',
            assigned_period='112026',
            financial_year='2026-27',
            status='EXCLUDED',
            is_statutorily_eligible=False,
            is_active=False,
            idempotency_key=f"test-del-{uuid.uuid4().hex}"
        )

        # Issue DELETE via API
        url = f"/api/vouchers/{voucher.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data.get('success'))

        # Verify voucher and allocation are gone
        self.assertFalse(Voucher.objects.filter(id=voucher.id).exists())
        self.assertFalse(GSTReportingAllocation.objects.filter(id=allocation.id).exists())

    def test_delete_voucher_with_filed_gst_allocation_blocked(self):
        """
        When attempting to delete a voucher with a FILED GSTReportingAllocation,
        deletion is strictly blocked with a clear ValidationError to protect statutory audit records.
        """
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-TEST-FILED-01',
            voucher_date=date(2026, 11, 26),
            party_ledger=self.supplier_ledger,
            status='POSTED',
            total_amount=Decimal('2500.00'),
            created_by=self.user
        )
        allocation = GSTReportingAllocation.objects.create(
            company=self.company,
            voucher=voucher,
            event_type='INWARD_ITC',
            voucher_date=date(2026, 11, 26),
            original_period='112026',
            assigned_period='112026',
            financial_year='2026-27',
            status='FILED',
            is_statutorily_eligible=True,
            is_active=True,
            idempotency_key=f"test-filed-{uuid.uuid4().hex}"
        )

        url = f"/api/vouchers/{voucher.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been reported or filed in a statutory GST return", response.data.get('error', ''))

        # Voucher and allocation must be intact
        self.assertTrue(Voucher.objects.filter(id=voucher.id).exists())
        self.assertTrue(GSTReportingAllocation.objects.filter(id=allocation.id).exists())

    def test_patch_voucher_with_item_discount(self):
        """
        PATCH /api/vouchers/<id>/ properly calculates and saves discount_percent on voucher items.
        """
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR-DISC-01',
            voucher_date=date(2026, 11, 26),
            party_ledger=self.supplier_ledger,
            status='DRAFT',
            total_amount=Decimal('0.00'),
            version=1,
            created_by=self.user
        )

        payload = {
            'voucher_number': 'PUR-DISC-01',
            'voucher_date': '2026-11-26',
            'party_ledger_id': str(self.supplier_ledger.id),
            'version': 1,
            'items': [
                {
                    'product_name': 'PIX C 90',
                    'brand': 'PIX',
                    'hsn_code': '401039',
                    'quantity': 5,
                    'rate': 1000.0,
                    'discount_percent': 10.0,  # 10% discount -> Net = 900 each -> Gross 4500
                    'unit': 'PCS',
                    'gst_rate': 18.0,
                }
            ]
        }

        url = f"/api/vouchers/{voucher.id}/"
        headers = {'HTTP_X_VOUCHER_VERSION': '1', 'HTTP_IF_MATCH': '"1"'}
        response = self.client.patch(url, data=payload, format='json', **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Verify discount_percent and amounts
        item = VoucherItem.objects.filter(voucher=voucher).first()
        self.assertIsNotNone(item)
        self.assertEqual(item.discount_percent, Decimal('10.00'))
        self.assertEqual(item.discount_amount, Decimal('500.00'))  # 5 * 1000 * 10% = 500
        self.assertEqual(item.taxable_amount, Decimal('4500.00'))   # 5000 - 500 = 4500

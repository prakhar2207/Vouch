from decimal import Decimal
import datetime
from django.test import TestCase
from rest_framework.test import APIClient
from apps.companies.models import Company
from apps.ledgers.models import LedgerGroup, Ledger
from apps.accounting.models import FinancialYear, Voucher, LedgerEntry, PaymentAllocation
from apps.inventory.models import Product, ProductCategory
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.sales_service import SalesInvoiceService
from apps.accounting.services.voucher_service import VoucherService
from django.contrib.auth import get_user_model

User = get_user_model()

class CashAccountingAndAllocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='cash_user@vouch.com', password='password123')
        self.company = Company.objects.create(name='Cash Test Org', gstin='27AABCU9603R1ZM', state_code='27')
        self.company.users.create(user=self.user, role='OWNER')
        
        self.fy = FinancialYear.objects.create(
            company=self.company,
            name='FY 2026-27',
            code='26-27',
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31)
        )

        # Groups
        self.grp_assets = LedgerGroup.objects.create(company=self.company, name='Current Assets', nature='ASSET')
        self.grp_cash = LedgerGroup.objects.create(company=self.company, name='Cash-in-Hand', parent_group=self.grp_assets, nature='ASSET')
        self.grp_debtors = LedgerGroup.objects.create(company=self.company, name='Sundry Debtors', parent_group=self.grp_assets, nature='ASSET')
        self.grp_creditors = LedgerGroup.objects.create(company=self.company, name='Sundry Creditors', nature='LIABILITY')
        self.grp_sales = LedgerGroup.objects.create(company=self.company, name='Sales Accounts', nature='INCOME')
        self.grp_purchases = LedgerGroup.objects.create(company=self.company, name='Purchase Accounts', nature='EXPENSE')
        self.grp_taxes = LedgerGroup.objects.create(company=self.company, name='Duties & Taxes', nature='LIABILITY')

        # Ledgers
        self.cash_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_cash,
            name='Cash Account',
            ledger_type='CASH',
            opening_balance=Decimal('50000.00'),
            current_balance=Decimal('50000.00')
        )
        self.customer_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_debtors,
            name='Acme Retailer',
            ledger_type='CUSTOMER'
        )
        self.supplier_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_creditors,
            name='National Distro',
            ledger_type='SUPPLIER'
        )
        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_sales,
            name='Domestic Sales',
            ledger_type='SALES'
        )
        self.purchase_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_purchases,
            name='Raw Materials Purchase',
            ledger_type='PURCHASE'
        )
        self.cgst_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_taxes,
            name='Output CGST',
            ledger_type='TAX'
        )
        self.sgst_ledger = Ledger.objects.create(
            company=self.company,
            group=self.grp_taxes,
            name='Output SGST',
            ledger_type='TAX'
        )

        self.category = ProductCategory.objects.create(company=self.company, name='Hardware', hsn_code='8483', gst_rate=18)
        self.product = Product.objects.create(
            company=self.company,
            category=self.category,
            name='V-Belt B42',
            selling_price=Decimal('500.00'),
            purchase_price=Decimal('350.00'),
            hsn_code='8483',
            gst_rate=18
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_direct_cash_sale_payment_status(self):
        """Spot cash sale posted with Cash ledger as party is immediately recognized as PAID."""
        voucher = SalesInvoiceService.generate_sales_invoice(
            company=self.company,
            user=self.user,
            party_ledger=self.cash_ledger,
            items_data=[{
                'product_id': str(self.product.id),
                'quantity': 2,
                'rate': 500,
                'discount_percent': 0
            }],
            sales_ledger=self.sales_ledger,
            cgst_ledger=self.cgst_ledger,
            sgst_ledger=self.sgst_ledger,
            buyer_name='Walk-in Counter Customer'
        )
        VoucherService.post_voucher(voucher)

        self.assertTrue(PaymentAllocationService.is_cash_voucher(voucher))
        p_status, paid_amt = PaymentAllocationService.get_voucher_payment_status(voucher)
        self.assertEqual(p_status, 'PAID')
        self.assertEqual(paid_amt, float(voucher.total_amount))

        # Verify API returns payment_status as PAID
        res = self.client.get(f'/api/v1/accounting/vouchers/{self.company.id}/')
        self.assertEqual(res.status_code, 200)
        found = next((item for item in res.data['data'] if item['id'] == str(voucher.id)), None)
        self.assertIsNotNone(found)
        self.assertEqual(found['payment_status'], 'PAID')
        self.assertEqual(found['paid_amount'], float(voucher.total_amount))

    def test_counter_instant_cash_settlement_on_invoice_creation(self):
        """Customer invoice created with payment_ledger_id auto-creates linked receipt and marks invoice PAID."""
        payload = {
            'company_id': str(self.company.id),
            'party_ledger_id': str(self.customer_ledger.id),
            'sales_ledger_id': str(self.sales_ledger.id),
            'cgst_ledger_id': str(self.cgst_ledger.id),
            'sgst_ledger_id': str(self.sgst_ledger.id),
            'items': [{
                'product_id': str(self.product.id),
                'quantity': 4,
                'rate': 500,
                'discount_percent': 0
            }],
            'payment_ledger_id': str(self.cash_ledger.id),
            'post_immediately': True
        }
        res = self.client.post('/api/v1/accounting/sales-invoice/', payload, format='json')
        if res.status_code != 201:
            print("ERROR IN SALES INVOICE RES:", res.data)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['payment_status'], 'PAID')
        self.assertEqual(float(res.data['paid_amount']), float(res.data['total_amount']))

        inv_voucher = Voucher.objects.get(id=res.data['voucher_id'])
        self.cash_ledger.refresh_from_db()
        self.customer_ledger.refresh_from_db()

        # Customer balance is settled (0.00)
        self.assertEqual(self.customer_ledger.current_balance, Decimal('0.00'))
        # Cash balance increased by total invoice amount
        self.assertEqual(self.cash_ledger.current_balance, Decimal('50000.00') + inv_voucher.total_amount)

        # A linked Receipt exists and is allocated to the invoice
        receipt = Voucher.objects.filter(company=self.company, voucher_type='RECEIPT', party_ledger=self.customer_ledger).first()
        self.assertIsNotNone(receipt)
        alloc = PaymentAllocation.objects.filter(payment_voucher=receipt, invoice_voucher=inv_voucher).first()
        self.assertIsNotNone(alloc)
        self.assertEqual(alloc.allocated_amount, inv_voucher.total_amount)

    def test_targeted_invoice_allocation_overrides_fifo(self):
        """Passing invoice_id explicitly allocates against chosen invoice instead of defaulting to older invoice FIFO."""
        # Create Inv 1 (Old)
        inv1 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type='SALES',
            voucher_number='INV-TEST-001', voucher_date=datetime.date(2026, 4, 10),
            party_ledger=self.customer_ledger, total_amount=Decimal('10000.00'), status='POSTED',
            created_by=self.user
        )
        # Create Inv 2 (New)
        inv2 = Voucher.objects.create(
            company=self.company, financial_year=self.fy, voucher_type='SALES',
            voucher_number='INV-TEST-002', voucher_date=datetime.date(2026, 4, 15),
            party_ledger=self.customer_ledger, total_amount=Decimal('15000.00'), status='POSTED',
            created_by=self.user
        )

        # Receive payment specifically for Inv 2
        payload = {
            'company_id': str(self.company.id),
            'voucher_type': 'RECEIPT',
            'party_ledger_id': str(self.customer_ledger.id),
            'payment_ledger_id': str(self.cash_ledger.id),
            'amount': '15000.00',
            'invoice_id': str(inv2.id),
            'narration': 'Payment specifically for Inv 2'
        }
        res = self.client.post('/api/v1/accounting/payment-receipt/', payload, format='json')
        self.assertEqual(res.status_code, 201)

        # Verify Inv 2 is fully paid, Inv 1 remains completely unpaid
        p_status1, paid1 = PaymentAllocationService.get_voucher_payment_status(inv1)
        p_status2, paid2 = PaymentAllocationService.get_voucher_payment_status(inv2)

        self.assertEqual(p_status2, 'PAID')
        self.assertEqual(paid2, 15000.0)
        self.assertEqual(p_status1, 'UNPAID')
        self.assertEqual(paid1, 0.0)

    def test_statutory_section_269st_and_negative_cash_guards(self):
        """Cash receipt >= 2,00,000 violates Section 269ST, and cash outflow exceeding cash drawer is blocked."""
        # 1. Section 269ST Violation (Receipt of 2,50,000 in cash)
        res_269 = self.client.post('/api/v1/accounting/payment-receipt/', {
            'company_id': str(self.company.id),
            'voucher_type': 'RECEIPT',
            'party_ledger_id': str(self.customer_ledger.id),
            'payment_ledger_id': str(self.cash_ledger.id),
            'amount': '250000.00'
        }, format='json')
        self.assertEqual(res_269.status_code, 400)
        self.assertEqual(res_269.data.get('statutory_code'), 'SECTION_269ST_VIOLATION')

        # 2. Section 40A(3) Disallowance (Payment of 25,000 in cash to supplier)
        res_40a = self.client.post('/api/v1/accounting/payment-receipt/', {
            'company_id': str(self.company.id),
            'voucher_type': 'PAYMENT',
            'party_ledger_id': str(self.supplier_ledger.id),
            'payment_ledger_id': str(self.cash_ledger.id),
            'amount': '25000.00'
        }, format='json')
        self.assertEqual(res_40a.status_code, 400)
        self.assertEqual(res_40a.data.get('statutory_code'), 'SECTION_40A3_DISALLOWANCE')

        # 3. Negative Cash in Hand Guard (Drawer has 50,000, paying 60,000 with statutory override)
        res_neg = self.client.post('/api/v1/accounting/payment-receipt/', {
            'company_id': str(self.company.id),
            'voucher_type': 'PAYMENT',
            'party_ledger_id': str(self.supplier_ledger.id),
            'payment_ledger_id': str(self.cash_ledger.id),
            'amount': '60000.00',
            'allow_statutory_override': True
        }, format='json')
        self.assertEqual(res_neg.status_code, 400)
        self.assertEqual(res_neg.data.get('cash_code'), 'NEGATIVE_CASH_DEFICIT')

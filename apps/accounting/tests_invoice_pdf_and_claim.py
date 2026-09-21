from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem, InwardVoucherRequest
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.invoice_pdf_service import InvoicePDFService, amount_to_words_indian
from apps.accounting.services.invoice_notification_service import InvoiceNotificationService

User = get_user_model()


class InvoicePDFAndClaimTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='seller@test.com',
            password='TestPassword123!'
        )

        self.company = Company.objects.create(
            name='Alpha Industrial Corp',
            legal_name='Alpha Industrial Corp Pvt Ltd',
            gstin='07AAAAA1111A1Z1',
            state_code='07',
            email='billing@alpha.com'
        )

        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')
        self.warehouse = Warehouse.objects.create(company=self.company, name='Main Warehouse')

        self.debtors_group = LedgerGroup.objects.create(company=self.company, name='Sundry Debtors', nature='ASSET')
        self.sales_group = LedgerGroup.objects.create(company=self.company, name='Sales Accounts', nature='INCOME')

        self.customer_ledger = Ledger.objects.create(
            company=self.company,
            group=self.debtors_group,
            name='Beta Retailers',
            gstin='07BBBBB2222B1Z2',
            state_code='07',
            phone='9876543210',
            email='accounts@betaretail.com',
            ledger_type='DEBTOR'
        )
        self.sales_ledger = Ledger.objects.create(
            company=self.company,
            group=self.sales_group,
            name='Domestic Sales',
            ledger_type='SALES'
        )

        self.product = Product.objects.create(
            company=self.company,
            name='Industrial V-Belt B-42',
            sku='VBLT-B42',
            hsn_code='40103990',
            unit='PCS',
            gst_rate=Decimal('18.00')
        )


        from datetime import date
        # Create Sales Voucher
        self.sales_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV/2026-27/0101',
            voucher_date=date(2026, 9, 15),
            due_date=date(2026, 9, 30),

            party_ledger=self.customer_ledger,
            buyer_name='Beta Retailers',
            buyer_gstin='07BBBBB2222B1Z2',
            buyer_email='accounts@betaretail.com',
            buyer_phone='9876543210',
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='DRAFT'
        )
        self.voucher_item = VoucherItem.objects.create(
            voucher=self.sales_voucher,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('1000.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('90.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('90.00'),
            total_amount=Decimal('1180.00')
        )


    def test_amount_to_words_indian(self):
        words = amount_to_words_indian(Decimal('1180.00'))
        self.assertEqual(words, "One Thousand One Hundred and Eighty Only")

        words_large = amount_to_words_indian(Decimal('12543210.50'))
        self.assertIn("One Crore", words_large)
        self.assertIn("Twenty Five Lakh", words_large)

    def test_invoice_pdf_generation(self):
        pdf_bytes = InvoicePDFService.generate_invoice_pdf(self.sales_voucher)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_claim_token_generation_and_verification(self):
        token = InvoiceNotificationService.generate_claim_token(self.sales_voucher)
        self.assertTrue(bool(token))

        payload = InvoiceNotificationService.verify_claim_token(token)
        self.assertEqual(payload['voucher_id'], str(self.sales_voucher.id))
        self.assertEqual(payload['voucher_number'], 'INV/2026-27/0101')
        self.assertEqual(payload['seller_name'], 'Alpha Industrial Corp')
        self.assertEqual(payload['buyer_gstin'], '07BBBBB2222B1Z2')
        self.assertEqual(payload['total_amount'], 1180.0)

    def test_whatsapp_share_payload(self):
        payload = InvoiceNotificationService.generate_whatsapp_share_payload(self.sales_voucher)
        self.assertIn('919876543210', payload['whatsapp_url'])
        self.assertIn('/print', payload['public_url'])
        self.assertIn(str(self.sales_voucher.id), payload['public_url'])

    def test_claim_preview_api(self):
        token = InvoiceNotificationService.generate_claim_token(self.sales_voucher)
        url = reverse('claim_preview') + f'?token={token}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['voucher_number'], 'INV/2026-27/0101')
        self.assertEqual(response.data['total_amount'], 1180.0)
        self.assertEqual(response.data['buyer_prefill']['gstin'], '07BBBBB2222B1Z2')
        self.assertEqual(len(response.data['items']), 1)

    def test_claim_register_viral_onboarding(self):
        token = InvoiceNotificationService.generate_claim_token(self.sales_voucher)
        url = reverse('claim_register')
        reg_payload = {
            'token': token,
            'email': 'onboarding_buyer@betaretail.com',
            'password': 'SecureBuyerPass123!',
            'company_name': 'Beta Retailers Pvt Ltd',
            'gstin': '07BBBBB2222B1Z2',
        }
        response = self.client.post(url, reg_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('inward_request_id', response.data)

        # Verify new buyer company was created with the pre-filled GSTIN
        buyer_comp = Company.objects.get(gstin='07BBBBB2222B1Z2')
        self.assertEqual(buyer_comp.name, 'Beta Retailers Pvt Ltd')

        # Verify InwardVoucherRequest was created and linked to the buyer's EDI Inbox
        inward_req = InwardVoucherRequest.objects.get(target_company=buyer_comp, source_voucher=self.sales_voucher)
        self.assertEqual(inward_req.status, 'PENDING')
        self.assertEqual(inward_req.source_company, self.company)

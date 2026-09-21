from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import GSTR2BImport, GSTR2BRecord
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
from apps.gst.services.itc_notification_service import ITCNotificationService

User = get_user_model()


class ITCReconciliationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='buyer@testcorp.com',
            password='TestBuyerPass123!'
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name='Precision Engineering Works',
            legal_name='Precision Engineering Works Pvt Ltd',
            gstin='07AAAAA9999A1Z9',
            state_code='07',
            email='accounts@precisioneng.com'
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')
        self.warehouse = Warehouse.objects.create(company=self.company, name='Raw Material Store')

        self.creditors_group = LedgerGroup.objects.create(company=self.company, name='Sundry Creditors', nature='LIABILITY')
        self.purchase_group = LedgerGroup.objects.create(company=self.company, name='Purchase Accounts', nature='EXPENSE')

        self.vendor_ledger = Ledger.objects.create(
            company=self.company,
            group=self.creditors_group,
            name='Steel Tubes & Alloys Ltd',
            gstin='07STEEL8888S1Z8',
            state_code='07',
            phone='9811122233',
            email='sales@steeltubes.com',
            ledger_type='CREDITOR'
        )
        self.purchase_ledger = Ledger.objects.create(
            company=self.company,
            group=self.purchase_group,
            name='Raw Material Purchases',
            ledger_type='PURCHASE'
        )

        self.product = Product.objects.create(
            company=self.company,
            name='Seamless Steel Tube 25mm',
            sku='TUBE-25MM',
            hsn_code='7306',
            unit='MTR',
            gst_rate=Decimal('18.00')
        )

        # 1. Purchase Voucher that WILL MATCH GSTR-2B
        self.matched_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/001',
            external_invoice_number='INV/2026/088',
            voucher_date=date(2026, 8, 10),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('11800.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=self.matched_voucher,
            product=self.product,
            quantity=Decimal('100.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('10000.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('900.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )

        # 2. Purchase Voucher that has VALUE MISMATCH with GSTR-2B
        self.mismatched_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/002',
            external_invoice_number='INV/2026/099',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('23600.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=self.mismatched_voucher,
            product=self.product,
            quantity=Decimal('200.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('20000.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('1800.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('1800.00'),
            total_amount=Decimal('23600.00')
        )

        # 3. Purchase Voucher MISSING IN GSTR-2B (Supplier defaulted / never filed)
        self.missing_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/003',
            external_invoice_number='INV/2026/500',
            voucher_date=date(2026, 8, 15),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('5900.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=self.missing_voucher,
            product=self.product,
            quantity=Decimal('50.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('5000.00'),
            cgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('450.00'),
            sgst_rate=Decimal('9.00'),
            sgst_amount=Decimal('450.00'),
            total_amount=Decimal('5900.00')
        )

    def test_invoice_normalization(self):
        norm = ITCReconciliationService.normalize_invoice_number('INV/2026-27/0081')
        self.assertEqual(norm, '2026270081')

        norm2 = ITCReconciliationService.normalize_invoice_number('inv-088')
        self.assertEqual(norm2, '088')

    def test_gstr2b_json_ingestion_and_reconciliation(self):
        # Sample GSTR-2B JSON payload with:
        # - Record 1: INV/2026/088 (matches matched_voucher exactly)
        # - Record 2: INV/2026/099 (has taxable 15,000 instead of 20,000 -> mismatch)
        # - Record 3: INV/2026/999 (supplier filed, but buyer missing in books)
        sample_gstr2b = {
            "gstin": "07AAAAA9999A1Z9",
            "fp": "082026",
            "data": {
                "b2b": [
                    {
                        "ctin": "07STEEL8888S1Z8",
                        "trdnm": "Steel Tubes & Alloys Ltd",
                        "inv": [
                            {
                                "inum": "INV/2026/088",
                                "dt": "10-08-2026",
                                "val": 11800.0,
                                "pos": "07",
                                "rev": "N",
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "itmdet": {
                                            "txval": 10000.0,
                                            "rt": 18.0,
                                            "iamt": 0.0,
                                            "camt": 900.0,
                                            "samt": 900.0,
                                            "csamt": 0.0
                                        }
                                    }
                                ]
                            },
                            {
                                "inum": "INV/2026/099",
                                "dt": "12-08-2026",
                                "val": 17700.0,
                                "pos": "07",
                                "rev": "N",
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "itmdet": {
                                            "txval": 15000.0,
                                            "rt": 18.0,
                                            "iamt": 0.0,
                                            "camt": 1350.0,
                                            "samt": 1350.0,
                                            "csamt": 0.0
                                        }
                                    }
                                ]
                            },
                            {
                                "inum": "INV/2026/999",
                                "dt": "20-08-2026",
                                "val": 3540.0,
                                "pos": "07",
                                "rev": "N",
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "itmdet": {
                                            "txval": 3000.0,
                                            "rt": 18.0,
                                            "iamt": 0.0,
                                            "camt": 270.0,
                                            "samt": 270.0,
                                            "csamt": 0.0
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }

        # Ingest and reconcile
        import_batch = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_gstr2b,
            user=self.user,
            return_period='082026'
        )

        self.assertEqual(import_batch.status, 'PROCESSED')
        self.assertEqual(import_batch.total_invoices_count, 3)

        # Check matched voucher
        self.matched_voucher.refresh_from_db()
        self.assertEqual(self.matched_voucher.itc_match_status, 'MATCHED')

        # Check mismatched voucher
        self.mismatched_voucher.refresh_from_db()
        self.assertEqual(self.mismatched_voucher.itc_match_status, 'MISMATCHED')
        self.assertIn("Taxable value mismatch", self.mismatched_voucher.itc_notes)

        # Check missing voucher in 2B
        self.missing_voucher.refresh_from_db()
        self.assertEqual(self.missing_voucher.itc_match_status, 'MISSING_IN_2B')
        # Total tax is 900 -> auto held amount is 900.00
        self.assertEqual(self.missing_voucher.itc_held_amount, Decimal('900.00'))

        # Check summary stats
        stats = ITCReconciliationService.get_summary_stats(self.company, return_period='082026')
        self.assertEqual(stats['matched_count'], 1)
        self.assertEqual(stats['mismatched_count'], 1)
        self.assertEqual(stats['missing_in_2b_count'], 1)
        self.assertEqual(stats['missing_in_books_count'], 1)
        self.assertEqual(stats['itc_safe'], 1800.0) # 900 CGST + 900 SGST
        self.assertEqual(stats['itc_at_risk'], 4500.0) # 3600 (mismatched) + 900 (missing)

    def test_smart_payment_hold_api(self):
        url = reverse('itc_hold_gst')
        payload = {
            'company_id': str(self.company.id),
            'voucher_id': str(self.missing_voucher.id),
            'held_amount': 900.00,
            'notes': 'Holding ₹900 GST until supplier files in September GSTR-1.'
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.missing_voucher.refresh_from_db()
        self.assertEqual(self.missing_voucher.itc_held_amount, Decimal('900.00'))
        self.assertIn('Holding ₹900 GST', self.missing_voucher.itc_notes)

    def test_whatsapp_notice_generator(self):
        self.missing_voucher.itc_match_status = 'MISSING_IN_2B'
        self.missing_voucher.itc_held_amount = Decimal('900.00')
        self.missing_voucher.save()

        notice = ITCNotificationService.generate_whatsapp_filing_notice(self.missing_voucher, self.company)
        self.assertEqual(notice['supplier_phone'], '919811122233')
        self.assertIn('INV/2026/500', notice['message_text'])
        self.assertIn('900.00', notice['message_text'])
        self.assertIn('https://wa.me/919811122233', notice['whatsapp_url'])
        self.assertIn('Section 16(2)(aa)', notice['message_text'])

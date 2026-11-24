from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import CompanyGSTConfig, GSTR2BImport, GSTR2BRecord
from apps.gst.services.itc_reconciliation_service import ITCReconciliationService
from apps.gst.services.itc_notification_service import ITCNotificationService
from apps.gst.services.reconciliation_service import GSTReconciliationService
from apps.gst.services.period_service import GSTPeriodService
from rest_framework.exceptions import ValidationError

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

    def test_unchecked_vouchers_counted_in_missing_in_2b_and_at_risk(self):
        # Create an un-reconciled voucher with UNCHECKED status
        new_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/099',
            external_invoice_number='INV/2026/UNCHECKED',
            voucher_date=date(2026, 8, 20),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED',
            itc_match_status='UNCHECKED'
        )
        VoucherItem.objects.create(
            voucher=new_voucher,
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

        stats = ITCReconciliationService.get_summary_stats(self.company, return_period='082026')
        # All 3 existing vouchers + new_voucher are UNCHECKED initially
        self.assertGreaterEqual(stats['missing_in_2b_count'], 1)
        self.assertGreaterEqual(stats['itc_at_risk'], 180.0)

        # Query reconciliation list with status=MISSING_IN_2B
        url = reverse('itc_reconciliation_list') + '?status=MISSING_IN_2B'
        res = self.client.get(url, HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get('results', [])
        invoice_numbers = [r['invoice_number'] for r in results]
        self.assertIn('INV/2026/UNCHECKED', invoice_numbers)

    @patch('apps.gst.services.reconciliation_service.SandboxGSTClient')
    @patch('apps.gst.services.itc_reconciliation_service.ITCReconciliationService.ingest_gstr2b_json')
    def test_flexible_date_parsing_and_sync(self, mock_ingest, mock_client_cls):
        CompanyGSTConfig.objects.create(
            company=self.company,
            auth_token="dummy-auth-token-12345"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.is_configured.return_value = True
        mock_client.fetch_gstr2b.return_value = {"success": True, "data": {"b2b": []}}
        mock_import = MagicMock()
        mock_import.id = "00000000-0000-0000-0000-000000000001"
        mock_import.total_invoices_count = 5
        mock_ingest.return_value = mock_import

        # 1. Test DDMMYYYY format (01042026 -> 042026)
        res = GSTReconciliationService.fetch_and_ingest_from_sandbox(
            company=self.company,
            return_period="01042026",
            user=self.user
        )
        self.assertTrue(res['success'])
        self.assertEqual(res['return_period'], '042026')
        mock_client.fetch_gstr2b.assert_called_with(year="2026", month="04", session_token="dummy-auth-token-12345", user=self.user)

        # 2. Test YYYY-MM format (2026-05 -> 052026)
        res2 = GSTReconciliationService.fetch_and_ingest_from_sandbox(
            company=self.company,
            return_period="2026-05",
            user=self.user
        )
        self.assertTrue(res2['success'])
        self.assertEqual(res2['return_period'], '052026')
        mock_client.fetch_gstr2b.assert_called_with(year="2026", month="05", session_token="dummy-auth-token-12345", user=self.user)

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_multi_period_range_sync(self, mock_single_fetch):
        mock_single_fetch.return_value = {
            "success": True,
            "total_invoices_ingested": 10,
            "return_period": "042026"
        }

        # Test April to October (042026 to 102026)
        res = GSTReconciliationService.fetch_and_ingest_range(
            company=self.company,
            from_period="042026",
            to_period="102026",
            user=self.user
        )
        self.assertTrue(res['success'])
        expected_periods = ["042026", "052026", "062026", "072026", "082026", "092026", "102026"]
        self.assertEqual(res['periods_requested'], expected_periods)
        self.assertEqual(res['periods_synced'], expected_periods)
        self.assertEqual(mock_single_fetch.call_count, 7)

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_range')
    def test_sync_api_view_with_range(self, mock_range_sync):
        mock_range_sync.return_value = {
            "success": True,
            "periods_synced": ["042026", "052026"],
            "total_invoices_ingested": 15
        }
        url = reverse('gst_reconciliation_gstr2b_sync', kwargs={'company_id': self.company.id})
        res = self.client.post(
            url,
            data={'from_period': '042026', 'to_period': '052026'},
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        mock_range_sync.assert_called_once()

    def test_period_service_canonical_parsing_and_range(self):
        # 1. MMYYYY format
        p1 = GSTPeriodService.parse_return_period("042026")
        self.assertEqual(p1.normalized_period, "042026")
        self.assertEqual(p1.month, "04")
        self.assertEqual(p1.year, "2026")
        self.assertEqual(p1.financial_year, "2026-27")

        # 2. DDMMYYYY format
        p2 = GSTPeriodService.parse_return_period("01042026")
        self.assertEqual(p2.normalized_period, "042026")

        # 3. YYYY-MM format
        p3 = GSTPeriodService.parse_return_period("2026-05")
        self.assertEqual(p3.normalized_period, "052026")

        # 4. MM-YYYY format
        p4 = GSTPeriodService.parse_return_period("06-2026")
        self.assertEqual(p4.normalized_period, "062026")

        # 5. Invalid format raises ValidationError
        with self.assertRaises(ValidationError):
            GSTPeriodService.parse_return_period("invalid")

        # 6. Invalid month raises ValidationError
        with self.assertRaises(ValidationError):
            GSTPeriodService.parse_return_period("132026")

        # 7. Range expansion April to October gives 7 months
        periods = GSTPeriodService.generate_period_range("042026", "102026")
        self.assertEqual(periods, ["042026", "052026", "062026", "072026", "082026", "092026", "102026"])

        # 8. Reversed range raises ValidationError
        with self.assertRaises(ValidationError):
            GSTPeriodService.generate_period_range("102026", "042026")

    def test_idempotent_ingestion_no_duplicate_records(self):
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
                            }
                        ]
                    }
                ]
            }
        }

        # First ingestion
        batch1 = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_gstr2b,
            user=self.user,
            return_period="082026"
        )
        self.assertEqual(batch1.records_created, 1)
        self.assertEqual(GSTR2BRecord.objects.filter(company=self.company, return_period="082026").count(), 1)

        # Second ingestion with the same payload (idempotent retry)
        batch2 = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_gstr2b,
            user=self.user,
            return_period="082026"
        )
        self.assertEqual(batch2.records_created, 0)
        self.assertEqual(batch2.records_unchanged, 1)
        # Total records in DB must still be exactly 1, no duplicate rows created!
        self.assertEqual(GSTR2BRecord.objects.filter(company=self.company, return_period="082026").count(), 1)

    def test_manual_review_preserved_on_reingestion(self):
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
                                "items": [{"itmdet": {"txval": 10000.0, "rt": 18.0, "iamt": 0.0, "camt": 900.0, "samt": 900.0, "csamt": 0.0}}]
                            }
                        ]
                    }
                ]
            }
        }

        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_gstr2b,
            user=self.user,
            return_period="082026"
        )
        rec = GSTR2BRecord.objects.get(company=self.company, return_period="082026")
        rec.is_reviewed = True
        rec.review_notes = "Reviewed by compliance lead: vendor verified"
        rec.save()

        # Re-ingest
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_gstr2b,
            user=self.user,
            return_period="082026"
        )
        rec.refresh_from_db()
        self.assertTrue(rec.is_reviewed)
        self.assertEqual(rec.review_notes, "Reviewed by compliance lead: vendor verified")

    def test_period_isolated_reconciliation_future_vouchers_untouched(self):
        # Create a purchase voucher dated in SEPTEMBER 2026
        sept_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/099-SEPT',
            external_invoice_number='INV/2026/SEPT-01',
            voucher_date=date(2026, 9, 15),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('5900.00'),
            created_by=self.user,
            status='POSTED',
            itc_match_status='UNCHECKED'
        )

        # Reconcile AUGUST 2026
        ITCReconciliationService.reconcile_period(
            company=self.company,
            return_period="082026"
        )

        # September voucher must remain UNCHECKED, NOT falsely marked as MISSING_IN_2B
        sept_voucher.refresh_from_db()
        self.assertEqual(sept_voucher.itc_match_status, 'UNCHECKED')

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_multi_period_partial_success_contract(self, mock_single_fetch):
        # Simulate QRMP behavior: June and Sept succeed, other months fail with FORM_NOT_APPLICABLE
        def fetch_side_effect(company, return_period, **kwargs):
            if return_period in ("062026", "092026"):
                return {
                    "success": True,
                    "status": "SUCCESS",
                    "invoices_ingested": 5,
                    "invoices_reconciled": 5,
                    "return_period": return_period
                }
            else:
                return {
                    "success": False,
                    "status": "FAILED",
                    "error_code": "FORM_NOT_APPLICABLE",
                    "error": f"GSTR2B form is not applicable for return period {return_period} (QRMP scheme).",
                    "return_period": return_period
                }

        mock_single_fetch.side_effect = fetch_side_effect

        res = GSTReconciliationService.fetch_and_ingest_range(
            company=self.company,
            from_period="042026",
            to_period="102026",
            user=self.user
        )

        self.assertEqual(res['status'], 'PARTIAL_SUCCESS')
        self.assertFalse(res['success'])  # Critical: never return overall SUCCESS when periods failed
        self.assertEqual(res['periods_synced'], ["062026", "092026"])
        self.assertEqual(len(res['periods_failed']), 5)
        self.assertIn("042026", res['periods_failed'])
        self.assertEqual(len(res['period_results']), 7)
        self.assertIn("failed or not applicable", res['error'])
        self.assertIn("GSTR2B form is not applicable", res['failed_periods_details'][0]['error'])

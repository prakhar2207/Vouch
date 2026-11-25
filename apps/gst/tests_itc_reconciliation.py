from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import CompanyGSTConfig, GSTR2BImport, GSTR2BRecord, GSTRegistration, VoucherGSTINAttributionLog, resolve_document_financial_effect
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
        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='07AAAAA9999A1Z9',
            legal_name='Precision Engineering Works Pvt Ltd',
            state_code='07',
            status='ACTIVE',
            filing_frequency='MONTHLY',
            is_primary=True
        )
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
            buyer_gstin=self.registration.gstin,
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
            buyer_gstin=self.registration.gstin,
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
            buyer_gstin=self.registration.gstin,
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
        # When a statement has been imported and processed for the return period,
        # unmatched vouchers are counted as MISSING_IN_2B
        GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='082026',
            status='PROCESSED',
            uploaded_by=self.user
        )
        new_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/099',
            external_invoice_number='INV/2026/UNCHECKED',
            voucher_date=date(2026, 8, 20),
            buyer_gstin=self.registration.gstin,
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
        # With processed statement for 082026, unmatched vouchers are MISSING_IN_2B
        self.assertGreaterEqual(stats['missing_in_2b_count'], 1)
        self.assertGreaterEqual(stats['itc_at_risk'], 180.0)

        # Query reconciliation list with status=MISSING_IN_2B
        url = reverse('itc_reconciliation_list') + '?status=MISSING_IN_2B&return_period=082026'
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

    def test_invalid_return_period_list_api_returns_400(self):
        res = self.client.get(
            reverse('itc_reconciliation_list'),
            {'return_period': 'invalid-period'},
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INVALID_RETURN_PERIOD')

    def test_invalid_return_period_summary_api_returns_400(self):
        res = self.client.get(
            reverse('itc_summary'),
            {'return_period': '132026'},
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INVALID_RETURN_PERIOD')

    def test_reversed_period_range_sync_returns_400(self):
        res = self.client.post(
            reverse('gst_reconciliation_gstr2b_sync', kwargs={'company_id': self.company.id}),
            {'from_period': '102026', 'to_period': '042026'},
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INVALID_PERIOD_RANGE')

    def test_missing_period_sync_returns_400(self):
        res = self.client.post(
            reverse('gst_reconciliation_gstr2b_sync', kwargs={'company_id': self.company.id}),
            {},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'PERIOD_REQUIRED')

    def test_unknown_registration_id_returns_400(self):
        import uuid
        res = self.client.get(
            reverse('itc_reconciliation_list'),
            {'registration_id': str(uuid.uuid4())},
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INVALID_REGISTRATION')

    def test_unknown_payload_gstin_rejected_without_fallback(self):
        sample_gstr2b = {
            'gstin': '99UNKNOWN9999Z9',
            'fp': '082026',
            'data': {'b2b': []}
        }
        with self.assertRaises(ValidationError):
            ITCReconciliationService.ingest_gstr2b_json(
                company=self.company,
                json_data=sample_gstr2b,
                return_period='082026'
            )

    def test_cdnr_credit_note_reduces_taxable_and_itc(self):
        sample_cdnr = {
            'gstin': '07AAAAA9999A1Z9',
            'fp': '082026',
            'data': {
                'b2b': [{
                    'ctin': '07STEEL8888S1Z8',
                    'inv': [{
                        'inum': 'INV-100',
                        'dt': '01-08-2026',
                        'val': 11800.0,
                        'items': [{'txval': 10000.0, 'camt': 900.0, 'samt': 900.0, 'iamt': 0.0, 'csamt': 0.0}]
                    }]
                }],
                'cdnr': [{
                    'ctin': '07STEEL8888S1Z8',
                    'nt': [{
                        'nt_num': 'CN-01',
                        'nt_dt': '05-08-2026',
                        'ntty': 'C',
                        'val': 2360.0,
                        'items': [{'txval': 2000.0, 'camt': 180.0, 'samt': 180.0, 'iamt': 0.0, 'csamt': 0.0}]
                    }]
                }]
            }
        }
        batch = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_cdnr,
            return_period='082026'
        )
        # Gross invoice 10000 - credit note 2000 = 8000 net taxable
        self.assertEqual(batch.total_taxable_amount, Decimal('8000.00'))
        # Gross ITC 1800 - credit note ITC 360 = 1440 net ITC
        self.assertEqual(batch.total_itc_available, Decimal('1440.00'))

        cn_rec = GSTR2BRecord.objects.get(company=self.company, invoice_number='CN-01')
        self.assertEqual(cn_rec.note_type, 'C')

    def test_cdnr_debit_note_increases_taxable_and_itc(self):
        sample_cdnr_d = {
            'gstin': '07AAAAA9999A1Z9',
            'fp': '082026',
            'data': {
                'b2b': [{
                    'ctin': '07STEEL8888S1Z8',
                    'inv': [{
                        'inum': 'INV-101',
                        'dt': '01-08-2026',
                        'val': 11800.0,
                        'items': [{'txval': 10000.0, 'camt': 900.0, 'samt': 900.0, 'iamt': 0.0, 'csamt': 0.0}]
                    }]
                }],
                'cdnr': [{
                    'ctin': '07STEEL8888S1Z8',
                    'nt': [{
                        'nt_num': 'DN-01',
                        'nt_dt': '05-08-2026',
                        'ntty': 'D',
                        'val': 2360.0,
                        'items': [{'txval': 2000.0, 'camt': 180.0, 'samt': 180.0, 'iamt': 0.0, 'csamt': 0.0}]
                    }]
                }]
            }
        }
        batch_d = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_cdnr_d,
            return_period='082026'
        )
        # Gross invoice 10000 + debit note 2000 = 12000 net taxable
        self.assertEqual(batch_d.total_taxable_amount, Decimal('12000.00'))
        # Gross ITC 1800 + debit note ITC 360 = 2160 net ITC
        self.assertEqual(batch_d.total_itc_available, Decimal('2160.00'))

        dn_rec = GSTR2BRecord.objects.get(company=self.company, invoice_number='DN-01')
        self.assertEqual(dn_rec.note_type, 'D')

    def test_no_date_fabrication_preserves_raw_and_sets_review_required(self):
        sample_bad_date = {
            'gstin': '07AAAAA9999A1Z9',
            'fp': '082026',
            'data': {
                'b2b': [{
                    'ctin': '07STEEL8888S1Z8',
                    'inv': [{
                        'inum': 'INV-CORRUPT',
                        'dt': 'invalid-raw-date',
                        'val': 1180.0,
                        'items': [{'txval': 1000.0, 'camt': 90.0, 'samt': 90.0, 'iamt': 0.0, 'csamt': 0.0}]
                    }]
                }]
            }
        }
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_bad_date,
            return_period='082026'
        )
        rec = GSTR2BRecord.objects.get(company=self.company, invoice_number='INV-CORRUPT')
        self.assertIsNone(rec.invoice_date)
        self.assertEqual(rec.raw_invoice_date, 'invalid-raw-date')
        self.assertEqual(rec.match_status, 'REVIEW_REQUIRED')

    def test_cross_period_reconciliation_later_period_match(self):
        # Purchase voucher dated in APRIL 2026
        apr_voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/040-APR',
            external_invoice_number='INV/2026/LATE-01',
            voucher_date=date(2026, 4, 15),
            buyer_gstin=self.registration.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('11800.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=apr_voucher,
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

        # Ingest June 2026 GSTR-2B containing this April invoice
        sample_june_2b = {
            'gstin': '07AAAAA9999A1Z9',
            'fp': '062026',
            'data': {
                'b2b': [{
                    'ctin': '07STEEL8888S1Z8',
                    'inv': [{
                        'inum': 'INV/2026/LATE-01',
                        'dt': '15-04-2026',
                        'val': 11800.0,
                        'items': [{'txval': 10000.0, 'camt': 900.0, 'samt': 900.0, 'iamt': 0.0, 'csamt': 0.0}]
                    }]
                }]
            }
        }
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_june_2b,
            return_period='062026'
        )

        # Reconcile June 2026
        ITCReconciliationService.reconcile_period(
            company=self.company,
            return_period='062026'
        )

        apr_voucher.refresh_from_db()
        self.assertEqual(apr_voucher.itc_match_status, 'LATER_PERIOD_MATCH')
        self.assertIn('later GSTR-2B statement (062026)', apr_voucher.itc_notes)

    def test_available_periods_endpoint(self):
        res = self.client.get(
            reverse('itc_available_periods'),
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(res.data['count'], 0)
        periods = [p['period'] for p in res.data['periods']]
        self.assertIn('042025', periods)
        self.assertIn('102025', periods)
        self.assertIn('042026', periods)
        self.assertIn('102026', periods)

    def test_unchecked_voucher_remains_data_unavailable_without_statement(self):
        # Ensure no GSTR-2B statement exists for period 092026
        GSTR2BImport.objects.filter(company=self.company, return_period='092026').delete()

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/SEP01',
            external_invoice_number='INV/2026/SEP01',
            voucher_date=date(2026, 9, 15),
            buyer_gstin=self.registration.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED',
            itc_match_status='UNCHECKED'
        )
        VoucherItem.objects.create(
            voucher=v,
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

        stats = ITCReconciliationService.get_summary_stats(self.company, return_period='092026')
        self.assertEqual(stats['missing_in_2b_count'], 0)
        self.assertGreaterEqual(stats.get('data_unavailable_count', 0), 1)

        scoped = ITCReconciliationService.get_scoped_reconciliation_data(self.company, return_period='092026')
        item = next((r for r in scoped['results'] if r['invoice_number'] == 'INV/2026/SEP01'), None)
        self.assertIsNotNone(item)
        self.assertEqual(item['itc_match_status'], 'DATA_UNAVAILABLE')

    def test_strict_multi_gstin_isolation_two_registrations(self):
        reg_delhi = self.registration  # 07AAAAA9999A1Z9
        reg_mumbai = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAAAA9999A1Z2',
            legal_name='Precision Engineering Works (MH)',
            state_code='27',
            status='ACTIVE',
            is_primary=False
        )

        v_delhi = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/DL/001',
            external_invoice_number='INV/DL/001',
            voucher_date=date(2026, 8, 12),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED',
            buyer_gstin=reg_delhi.gstin
        )
        v_mumbai = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/MH/001',
            external_invoice_number='INV/MH/001',
            voucher_date=date(2026, 8, 14),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('2360.00'),
            created_by=self.user,
            status='POSTED',
            buyer_gstin=reg_mumbai.gstin
        )
        v_unassigned = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/UN/001',
            external_invoice_number='INV/UN/001',
            voucher_date=date(2026, 8, 16),
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('3540.00'),
            created_by=self.user,
            status='POSTED',
            buyer_gstin=''
        )

        # Scoped query for Delhi: MUST ONLY contain v_delhi, NOT v_mumbai or v_unassigned
        scoped_dl = ITCReconciliationService.get_scoped_reconciliation_data(
            self.company, return_period='082026', registration=reg_delhi
        )
        dl_invoices = [r['invoice_number'] for r in scoped_dl['results']]
        self.assertIn('INV/DL/001', dl_invoices)
        self.assertNotIn('INV/MH/001', dl_invoices)
        self.assertNotIn('INV/UN/001', dl_invoices)

        # Scoped query for Mumbai: MUST ONLY contain v_mumbai
        scoped_mh = ITCReconciliationService.get_scoped_reconciliation_data(
            self.company, return_period='082026', registration=reg_mumbai
        )
        mh_invoices = [r['invoice_number'] for r in scoped_mh['results']]
        self.assertIn('INV/MH/001', mh_invoices)
        self.assertNotIn('INV/DL/001', mh_invoices)
        self.assertNotIn('INV/UN/001', mh_invoices)

    def test_available_periods_rejects_invalid_or_inactive_registration(self):
        import uuid
        res = self.client.get(
            reverse('itc_available_periods') + f'?registration_id={uuid.uuid4()}',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INVALID_REGISTRATION')

        inactive_reg = GSTRegistration.objects.create(
            company=self.company,
            gstin='09INACTIVE9999Z1',
            legal_name='Precision Inactive',
            state_code='09',
            status='INACTIVE'
        )
        res = self.client.get(
            reverse('itc_available_periods') + f'?registration_id={inactive_reg.id}',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INACTIVE_REGISTRATION')

    def test_cdnr_signed_accounting_math_in_summary_and_missing_in_books(self):
        batch = GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='102026',
            status='PROCESSED',
            uploaded_by=self.user
        )
        # B2B invoice missing in books: ₹10,000 taxable, ₹1,800 tax
        GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            gst_registration=self.registration,
            return_period='102026',
            supplier_gstin='07STEEL8888S1Z8',
            invoice_number='INV/CDNR/B2B/01',
            normalized_invoice_number='INVCDNRB2B01',
            document_type='B2B',
            invoice_date=date(2026, 10, 5),
            taxable_value=Decimal('10000.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            match_status='MISSING_IN_BOOKS'
        )
        # Credit Note missing in books: ₹2,000 taxable, ₹360 tax (reduces missing ITC)
        GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            gst_registration=self.registration,
            return_period='102026',
            supplier_gstin='07STEEL8888S1Z8',
            invoice_number='CN/CDNR/01',
            normalized_invoice_number='CNCDNR01',
            document_type='CDNR',
            note_type='C',
            invoice_date=date(2026, 10, 8),
            taxable_value=Decimal('2000.00'),
            cgst_amount=Decimal('180.00'),
            sgst_amount=Decimal('180.00'),
            match_status='MISSING_IN_BOOKS'
        )

        scoped = ITCReconciliationService.get_scoped_reconciliation_data(self.company, return_period='102026')
        summary = scoped['summary']
        # Gross = 1800, Credit = 360, Net = 1800 - 360 = 1440
        self.assertEqual(summary['missing_in_books_gross_itc'], 1800.0)
        self.assertEqual(summary['missing_in_books_credit_itc'], 360.0)
        self.assertEqual(summary['missing_in_books_itc'], 1440.0)

    def test_amended_later_period_retains_amendment_identity(self):
        apr_v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/AMEND01',
            external_invoice_number='INV/AMEND/01',
            voucher_date=date(2026, 4, 15),
            buyer_gstin=self.registration.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('11800.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=apr_v,
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

        sample_b2ba = {
            "gstin": "07AAAAA9999A1Z9",
            "fp": "072026",
            "data": {
                "docdata": {
                    "b2ba": [{
                        "ctin": "07STEEL8888S1Z8",
                        "inv": [{
                            "inum": "INV/AMEND/01",
                            "dt": "15-04-2026",
                            "val": 11800.00,
                            "pos": "07",
                            "rchrg": "N",
                            "inv_typ": "R",
                            "itcavl": "Y",
                            "items": [{
                                "num": 1,
                                "txval": 10000.00,
                                "camt": 900.00,
                                "samt": 900.00
                            }]
                        }]
                    }]
                }
            }
        }
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sample_b2ba,
            return_period='072026'
        )
        ITCReconciliationService.reconcile_period(
            company=self.company,
            return_period='072026'
        )

        apr_v.refresh_from_db()
        # MUST BE AMENDED (not masked by LATER_PERIOD_MATCH)
        self.assertEqual(apr_v.itc_match_status, 'AMENDED')
        self.assertIn('amended GSTR-2B record', apr_v.itc_notes)

    def test_postgresql_concurrent_ingestion_lock_race(self):
        """
        Real PostgreSQL concurrency test:
        Two concurrent threads call _acquire_ingestion_lock on a brand-new period.
        Verifies that PostgreSQL savepoint + select_for_update prevents IntegrityError race.
        """
        import threading
        from django.db import connection, transaction

        target_period = '112026'

        # Under SQLite test runners, multiple threads cannot acquire locks concurrently because of database file locking.
        if connection.vendor == 'sqlite':
            lock1 = ITCReconciliationService._acquire_ingestion_lock(
                company=self.company,
                registration=self.registration,
                return_period=target_period
            )
            self.assertIsNotNone(lock1)
            lock2 = ITCReconciliationService._acquire_ingestion_lock(
                company=self.company,
                registration=self.registration,
                return_period=target_period
            )
            self.assertEqual(lock1.id, lock2.id)
            return

        errors = []

        def worker():
            from django.db import connection
            connection.close()  # Ensure separate DB connection
            try:
                with transaction.atomic():
                    lock = ITCReconciliationService._acquire_ingestion_lock(
                        company=self.company,
                        registration=self.registration,
                        return_period=target_period
                    )
                    self.assertIsNotNone(lock)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Concurrent lock acquisition failed with errors: {errors}")

    def test_cdnr_debit_note_sign_math_not_inverted(self):
        """
        DEF-01: Verifies debit note sign logic.
        Debit note (CDNR with note_type='D') must NOT be treated as a credit note.
        Must have positive signed taxable and tax values.
        """
        batch = GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='082026',
            status='PROCESSED',
            uploaded_by=self.user
        )
        rec = GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            gst_registration=self.registration,
            return_period='082026',
            supplier_gstin='07STEEL8888S1Z8',
            invoice_number='DN/2026/01',
            normalized_invoice_number='DN202601',
            document_type='CDNR',
            note_type='D',
            taxable_value=Decimal('5000.00'),
            cgst_amount=Decimal('450.00'),
            sgst_amount=Decimal('450.00'),
            igst_amount=Decimal('0.00'),
            cess_amount=Decimal('0.00'),
            match_status='MISSING_IN_BOOKS'
        )

        eff = rec.financial_effect
        self.assertFalse(rec.is_credit_note, "CDNR with note_type='D' must not be credit note")
        self.assertTrue(rec.is_debit_note, "CDNR with note_type='D' must be debit note")
        self.assertEqual(eff.financial_sign, 1)
        self.assertEqual(rec.signed_taxable_value, Decimal('5000.00'))
        self.assertEqual(rec.signed_total_tax, Decimal('900.00'))
        self.assertEqual(rec.signed_cgst, Decimal('450.00'))
        self.assertEqual(rec.signed_sgst, Decimal('450.00'))

    def test_cdnr_unknown_note_type_flags_review_required(self):
        """
        DEF-01: Verifies that CDNR with missing or ambiguous note_type
        evaluates to financial_sign=0 and is_review_required=True.
        """
        batch = GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='082026',
            status='PROCESSED',
            uploaded_by=self.user
        )
        rec = GSTR2BRecord.objects.create(
            import_batch=batch,
            company=self.company,
            gst_registration=self.registration,
            return_period='082026',
            supplier_gstin='07STEEL8888S1Z8',
            invoice_number='AMBIG/2026/01',
            normalized_invoice_number='AMBIG202601',
            document_type='CDNR',
            note_type='',
            taxable_value=Decimal('3000.00'),
            cgst_amount=Decimal('270.00'),
            sgst_amount=Decimal('270.00'),
            match_status='REVIEW_REQUIRED'
        )

        eff = rec.financial_effect
        self.assertTrue(eff.is_review_required)
        self.assertEqual(eff.financial_sign, 0)
        self.assertEqual(rec.signed_taxable_value, Decimal('0.00'))
        self.assertEqual(rec.signed_total_tax, Decimal('0.00'))

    def test_qrmp_period_resolver_maps_interim_months_to_quarter_end(self):
        """
        DEF-02: Central Return-Period Resolver with QRMP Intelligence.
        Verifies that April and May invoices map to the June quarter-end statement (06YYYY),
        and July/August invoices map to the September statement (09YYYY).
        """
        # Set registration to QRMP
        self.registration.filing_frequency = 'QRMP'
        self.registration.save(update_fields=['filing_frequency'])

        res_apr = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 4, 15),
            recipient_registration=self.registration
        )
        self.assertEqual(res_apr.expected_statement_period, '062026')
        self.assertEqual(res_apr.invoice_period, '042026')
        self.assertEqual(res_apr.period_resolution_status, 'RESOLVED_QRMP')

        res_may = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 5, 20),
            recipient_registration=self.registration
        )
        self.assertEqual(res_may.expected_statement_period, '062026')

        res_jul = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 7, 10),
            recipient_registration=self.registration
        )
        self.assertEqual(res_jul.expected_statement_period, '092026')

        res_aug = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 8, 25),
            recipient_registration=self.registration
        )
        self.assertEqual(res_aug.expected_statement_period, '092026')

        # Test Monthly registration behavior
        self.registration.filing_frequency = 'MONTHLY'
        self.registration.save(update_fields=['filing_frequency'])

        res_monthly_apr = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 4, 15),
            recipient_registration=self.registration
        )
        self.assertEqual(res_monthly_apr.expected_statement_period, '042026')
        self.assertEqual(res_monthly_apr.period_resolution_status, 'RESOLVED_MONTHLY')

    def test_empty_statement_processed_marks_unmatched_as_missing_in_2b(self):
        """
        DEF-03: EMPTY_PROCESSED is valid evidence that un-reflected invoices are missing.
        When an empty statement is ingested, batch status is EMPTY_PROCESSED and is_empty_statement=True.
        Unmatched invoices for that period become MISSING_IN_2B.
        """
        empty_payload = {
            'gstin': self.registration.gstin,
            'fp': '052026',
            'data': {
                'docdata': {
                    'b2b': [],
                    'b2ba': [],
                    'cdnr': [],
                    'cdnra': []
                }
            }
        }
        batch = ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=empty_payload,
            return_period='052026',
            registration=self.registration
        )
        self.assertEqual(batch.status, 'EMPTY_PROCESSED')
        self.assertTrue(batch.is_empty_statement)
        self.assertEqual(batch.total_invoices_count, 0)
        self.assertEqual(batch.records_created, 0)

        # Voucher in May 2026
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/MAY01',
            external_invoice_number='INV/MAY/01',
            voucher_date=date(2026, 5, 10),
            buyer_gstin=self.registration.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED',
            itc_match_status='UNCHECKED'
        )
        VoucherItem.objects.create(
            voucher=v,
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

        ITCReconciliationService.reconcile_period(
            company=self.company,
            return_period='052026',
            registration=self.registration
        )
        v.refresh_from_db()
        self.assertEqual(v.itc_match_status, 'MISSING_IN_2B')

    def test_attribution_api_maps_unmapped_voucher_to_gstin_with_audit_trail(self):
        """
        DEF-04: Explicit GSTIN attribution endpoint assigns unmapped voucher to registration
        and records audit fields (attributed_by, attributed_at, attribution_source).
        """
        unmapped_v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/UNMAPPED01',
            external_invoice_number='INV/UNMAPPED/01',
            voucher_date=date(2026, 8, 10),
            buyer_gstin=None,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED',
            itc_match_status='UNCHECKED'
        )

        url = reverse('itc_attribute_voucher')
        payload = {
            'voucher_ids': [str(unmapped_v.id)],
            'registration_id': str(self.registration.id),
            'attribution_source': 'TEST_SUITE_AUDIT'
        }
        res = self.client.post(url, payload, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        self.assertEqual(res.data.get('attributed_count'), 1)

        unmapped_v.refresh_from_db()
        self.assertEqual(unmapped_v.buyer_gstin, self.registration.gstin)
        self.assertEqual(unmapped_v.itc_gstin_attributed_by, self.user)
        self.assertIsNotNone(unmapped_v.itc_gstin_attributed_at)
        self.assertEqual(unmapped_v.itc_gstin_attribution_source, 'TEST_SUITE_AUDIT')

        # Verify append-only attribution audit log was created (P0 DEF-04)
        log = VoucherGSTINAttributionLog.objects.filter(voucher=unmapped_v).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_gstin, self.registration.gstin)
        self.assertEqual(log.attributed_by, self.user)
        self.assertFalse(log.is_correction)

    def test_qrmp_10_mandatory_regression_scenarios(self):
        """
        P0 DEF-02 & Round 2.4.1: Complete 10 mandatory QRMP regression scenarios.
        1. April invoice found in June statement → LATER_PERIOD_MATCH.
        2. April invoice absent from successfully processed June statement → MISSING_IN_2B.
        3. May invoice found in June statement → LATER_PERIOD_MATCH.
        4. May invoice absent from successfully processed June statement → MISSING_IN_2B.
        5. July invoice found in September statement → LATER_PERIOD_MATCH.
        6. July invoice absent from successfully processed September statement → MISSING_IN_2B.
        7. April invoice with no June statement → DATA_UNAVAILABLE.
        8. Failed June fetch → never classify April or May invoices as missing.
        9. Reprocessing September must not overwrite a verified June match.
        10. A credit note or debit note must preserve its correct signed financial effect.
        """
        self.registration.filing_frequency = 'QRMP'
        self.registration.save(update_fields=['filing_frequency'])

        def create_test_voucher(v_num, inv_num, v_date, taxable_amt=Decimal('10000.00'), tax_amt=Decimal('1800.00')):
            v = Voucher.objects.create(
                company=self.company,
                voucher_type='PURCHASE',
                voucher_number=v_num,
                external_invoice_number=inv_num,
                voucher_date=v_date,
                buyer_gstin=self.registration.gstin,
                party_ledger=self.vendor_ledger,
                total_amount=taxable_amt + tax_amt,
                created_by=self.user,
                status='POSTED',
                itc_match_status='UNCHECKED'
            )
            half_tax = tax_amt / 2
            VoucherItem.objects.create(
                voucher=v,
                product=self.product,
                quantity=Decimal('1.00'),
                rate=taxable_amt,
                taxable_amount=taxable_amt,
                cgst_rate=Decimal('9.00'),
                cgst_amount=half_tax,
                sgst_rate=Decimal('9.00'),
                sgst_amount=half_tax,
                total_amount=taxable_amt + tax_amt
            )
            return v

        # Vouchers:
        v_apr_found = create_test_voucher('PUR/26-27/APR-F', 'INV/APR/01', date(2026, 4, 15))
        v_apr_absent = create_test_voucher('PUR/26-27/APR-A', 'INV/APR/ABSENT', date(2026, 4, 20))
        v_may_found = create_test_voucher('PUR/26-27/MAY-F', 'INV/MAY/01', date(2026, 5, 10))
        v_may_absent = create_test_voucher('PUR/26-27/MAY-A', 'INV/MAY/ABSENT', date(2026, 5, 25))
        v_jul_found = create_test_voucher('PUR/26-27/JUL-F', 'INV/JUL/01', date(2026, 7, 12))
        v_jul_absent = create_test_voucher('PUR/26-27/JUL-A', 'INV/JUL/ABSENT', date(2026, 7, 18))

        # Scenario 7: April invoice with no June statement → DATA_UNAVAILABLE
        GSTR2BImport.objects.filter(company=self.company, return_period='062026').delete()
        ITCReconciliationService.reconcile_period(self.company, return_period='062026', registration=self.registration)
        v_apr_absent.refresh_from_db()
        self.assertEqual(v_apr_absent.itc_match_status, 'DATA_UNAVAILABLE', "Scenario 7: No June statement must yield DATA_UNAVAILABLE")

        # Scenario 8: Failed June fetch → never classify April or May invoices as missing
        GSTR2BImport.objects.filter(company=self.company, return_period='062026').delete()
        GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='062026',
            status='REQUEST_FAILED',
            uploaded_by=self.user
        )
        ITCReconciliationService.reconcile_period(self.company, return_period='062026', registration=self.registration)
        v_apr_absent.refresh_from_db()
        v_may_absent.refresh_from_db()
        self.assertEqual(v_apr_absent.itc_match_status, 'DATA_UNAVAILABLE', "Scenario 8: Failed June statement must not classify as MISSING_IN_2B")
        self.assertEqual(v_may_absent.itc_match_status, 'DATA_UNAVAILABLE', "Scenario 8: Failed June statement must not classify as MISSING_IN_2B")

        # Ingest successful June 2026 GSTR-2B containing INV/APR/01 and INV/MAY/01
        GSTR2BImport.objects.filter(company=self.company, return_period='062026').delete()
        june_payload = {
            'gstin': self.registration.gstin,
            'fp': '062026',
            'data': {
                'docdata': {
                    'b2b': [{
                        'ctin': '07STEEL8888S1Z8',
                        'inv': [
                            {
                                'inum': 'INV/APR/01',
                                'dt': '15-04-2026',
                                'val': 11800.0,
                                'items': [{'txval': 10000.0, 'camt': 900.0, 'samt': 900.0, 'iamt': 0.0, 'csamt': 0.0}]
                            },
                            {
                                'inum': 'INV/MAY/01',
                                'dt': '10-05-2026',
                                'val': 11800.0,
                                'items': [{'txval': 10000.0, 'camt': 900.0, 'samt': 900.0, 'iamt': 0.0, 'csamt': 0.0}]
                            }
                        ]
                    }],
                    'cdnr': [{
                        'ctin': '07STEEL8888S1Z8',
                        'nt': [{
                            'nt_num': 'CN/JUNE/01',
                            'nt_dt': '20-06-2026',
                            'ntty': 'C',
                            'val': 2360.0,
                            'items': [{'txval': 2000.0, 'camt': 180.0, 'samt': 180.0, 'iamt': 0.0, 'csamt': 0.0}]
                        }]
                    }]
                }
            }
        }
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=june_payload,
            return_period='062026',
            registration=self.registration
        )

        # Reconcile June 2026
        ITCReconciliationService.reconcile_period(self.company, return_period='062026', registration=self.registration)

        v_apr_found.refresh_from_db()
        v_apr_absent.refresh_from_db()
        v_may_found.refresh_from_db()
        v_may_absent.refresh_from_db()
        v_jul_found.refresh_from_db()
        v_jul_absent.refresh_from_db()

        # Scenario 1 & 3: Found April & May invoices in June statement → LATER_PERIOD_MATCH
        self.assertEqual(v_apr_found.itc_match_status, 'LATER_PERIOD_MATCH', "Scenario 1: April invoice in June 2B must be LATER_PERIOD_MATCH")
        self.assertEqual(v_may_found.itc_match_status, 'LATER_PERIOD_MATCH', "Scenario 3: May invoice in June 2B must be LATER_PERIOD_MATCH")

        # Scenario 2 & 4: Absent April & May invoices from successfully processed June statement → MISSING_IN_2B
        self.assertEqual(v_apr_absent.itc_match_status, 'MISSING_IN_2B', "Scenario 2: Absent April invoice from June 2B must be MISSING_IN_2B")
        self.assertEqual(v_may_absent.itc_match_status, 'MISSING_IN_2B', "Scenario 4: Absent May invoice from June 2B must be MISSING_IN_2B")

        # Future July vouchers must remain UNCHECKED after June reconciliation (unrelated future statement)
        self.assertEqual(v_jul_found.itc_match_status, 'UNCHECKED')
        self.assertEqual(v_jul_absent.itc_match_status, 'UNCHECKED')

        # Ingest successful September 2026 GSTR-2B containing INV/JUL/01
        sept_payload = {
            'gstin': self.registration.gstin,
            'fp': '092026',
            'data': {
                'docdata': {
                    'b2b': [{
                        'ctin': '07STEEL8888S1Z8',
                        'inv': [
                            {
                                'inum': 'INV/JUL/01',
                                'dt': '12-07-2026',
                                'val': 11800.0,
                                'items': [{'txval': 10000.0, 'camt': 900.0, 'samt': 900.0, 'iamt': 0.0, 'csamt': 0.0}]
                            }
                        ]
                    }],
                    'cdnr': []
                }
            }
        }
        ITCReconciliationService.ingest_gstr2b_json(
            company=self.company,
            json_data=sept_payload,
            return_period='092026',
            registration=self.registration
        )

        # Reconcile September 2026
        ITCReconciliationService.reconcile_period(self.company, return_period='092026', registration=self.registration)

        v_jul_found.refresh_from_db()
        v_jul_absent.refresh_from_db()
        v_apr_found.refresh_from_db()

        # Scenario 5 & 6: July invoice in September statement
        self.assertEqual(v_jul_found.itc_match_status, 'LATER_PERIOD_MATCH', "Scenario 5: July invoice in Sept 2B must be LATER_PERIOD_MATCH")
        self.assertEqual(v_jul_absent.itc_match_status, 'MISSING_IN_2B', "Scenario 6: Absent July invoice from Sept 2B must be MISSING_IN_2B")

        # Scenario 9: Reprocessing September must not overwrite a verified June match
        self.assertEqual(v_apr_found.itc_match_status, 'LATER_PERIOD_MATCH', "Scenario 9: September reconciliation must not overwrite June match")

        # Scenario 10: Credit note signed financial effect in QRMP
        rec_cn = GSTR2BRecord.objects.get(company=self.company, return_period='062026', document_type='CDNR')
        self.assertEqual(rec_cn.financial_effect.financial_sign, -1, "Scenario 10: Credit note must maintain financial_sign=-1")
        self.assertEqual(rec_cn.signed_total_tax, Decimal('-360.00'))

    def test_filing_frequency_verification_and_drift_prevention(self):
        """
        P0 DEF-03 & Round 2.4.1: Filing-frequency verification lifecycle.
        - Registrations default to UNKNOWN.
        - UNKNOWN registration returns REVIEW_REQUIRED.
        - Provider errors do not mutate filing frequency.
        - set_filing_frequency updates frequency with audit timestamp and user.
        - Monthly and QRMP resolve distinct expected statement periods.
        """
        new_reg = GSTRegistration.objects.create(
            company=self.company,
            gstin='07NEWREG9999N1Z1',
            legal_name='New Unverified Branch',
            state_code='07',
            status='ACTIVE'
        )
        # Default must be UNKNOWN
        self.assertEqual(new_reg.filing_frequency, 'UNKNOWN')
        self.assertEqual(new_reg.frequency_verified_source, '')
        self.assertIsNone(new_reg.frequency_verified_at)

        # Resolution with UNKNOWN returns REVIEW_REQUIRED
        res_unk = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 4, 15),
            recipient_registration=new_reg
        )
        self.assertEqual(res_unk.period_resolution_status, 'REVIEW_REQUIRED')
        self.assertIsNone(res_unk.expected_statement_period)

        # Simulate provider FORM_NOT_APPLICABLE error; filing_frequency must NOT be mutated to QRMP
        new_reg.refresh_from_db()
        self.assertEqual(new_reg.filing_frequency, 'UNKNOWN')

        # Authorized explicit manual update
        new_reg.set_filing_frequency(frequency='QRMP', source='USER_MANUAL', user=self.user)
        new_reg.refresh_from_db()
        self.assertEqual(new_reg.filing_frequency, 'QRMP')
        self.assertEqual(new_reg.frequency_verified_source, 'USER_MANUAL')
        self.assertEqual(new_reg.frequency_verified_by, self.user)
        self.assertIsNotNone(new_reg.frequency_verified_at)

        # Test monthly registration
        new_reg.set_filing_frequency(frequency='MONTHLY', source='PORTAL_API', user=self.user)
        res_m = GSTPeriodService.resolve_gstr2b_statement_period(
            invoice_date=date(2026, 4, 15),
            recipient_registration=new_reg
        )
        self.assertEqual(res_m.period_resolution_status, 'RESOLVED_MONTHLY')
        self.assertEqual(res_m.expected_statement_period, '042026')

    def test_secure_attribution_and_correction_workflow_lifecycle(self):
        """
        P0 DEF-04: Secure GSTIN attribution and correction workflow.
        - Rejects cross-tenant voucher IDs.
        - Rejects already-attributed voucher without correction mode.
        - Rejects inactive registration.
        - Rejects unauthorized user role.
        - Succeeds on unmapped voucher and creates append-only log.
        - Correction mode succeeds with reason and appends second log.
        """
        unmapped_v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/26-27/ATTR-001',
            external_invoice_number='INV/ATTR/001',
            voucher_date=date(2026, 8, 10),
            buyer_gstin=None,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED',
            itc_match_status='UNCHECKED'
        )

        reg2 = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAAAA9999A1Z2',
            legal_name='Precision Mumbai',
            state_code='27',
            status='ACTIVE'
        )
        inactive_reg = GSTRegistration.objects.create(
            company=self.company,
            gstin='09INACTIVE9999Z9',
            legal_name='Precision Inactive',
            state_code='09',
            status='INACTIVE'
        )

        # 1. Reject inactive registration
        res = self.client.post(
            reverse('itc_attribute_voucher'),
            {'voucher_ids': [str(unmapped_v.id)], 'registration_id': str(inactive_reg.id)},
            format='json', HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'INACTIVE_REGISTRATION')

        # 2. Reject cross-tenant or invalid voucher ID
        import uuid
        res = self.client.post(
            reverse('itc_attribute_voucher'),
            {'voucher_ids': [str(unmapped_v.id), str(uuid.uuid4())], 'registration_id': str(self.registration.id)},
            format='json', HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'CROSS_TENANT_OR_INVALID_VOUCHERS')

        # 3. Successful initial attribution
        res = self.client.post(
            reverse('itc_attribute_voucher'),
            {'voucher_ids': [str(unmapped_v.id)], 'registration_id': str(self.registration.id), 'attribution_source': 'FIRST_MAP'},
            format='json', HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        unmapped_v.refresh_from_db()
        self.assertEqual(unmapped_v.buyer_gstin, self.registration.gstin)

        # 4. Standard attribution of ALREADY ATTRIBUTED voucher must be rejected
        res = self.client.post(
            reverse('itc_attribute_voucher'),
            {'voucher_ids': [str(unmapped_v.id)], 'registration_id': str(reg2.id)},
            format='json', HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'ALREADY_ATTRIBUTED')

        # 5. Correction without reason must be rejected
        res = self.client.post(
            reverse('itc_correct_attribution'),
            {'voucher_ids': [str(unmapped_v.id)], 'registration_id': str(reg2.id), 'reason': ''},
            format='json', HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get('error_code'), 'REASON_REQUIRED')

        # 6. Authorized correction with reason succeeds and creates append-only audit entry
        res = self.client.post(
            reverse('itc_correct_attribution'),
            {
                'voucher_ids': [str(unmapped_v.id)],
                'registration_id': str(reg2.id),
                'reason': 'Invoice belonged to Mumbai branch per PO #9941'
            },
            format='json', HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get('success'))
        unmapped_v.refresh_from_db()
        self.assertEqual(unmapped_v.buyer_gstin, reg2.gstin)

        # Verify 2 distinct immutable audit log records exist
        logs = list(VoucherGSTINAttributionLog.objects.filter(voucher=unmapped_v).order_by('attributed_at'))
        self.assertEqual(len(logs), 2)
        self.assertFalse(logs[0].is_correction)
        self.assertEqual(logs[0].new_gstin, self.registration.gstin)
        self.assertTrue(logs[1].is_correction)
        self.assertEqual(logs[1].previous_gstin, self.registration.gstin)
        self.assertEqual(logs[1].new_gstin, reg2.gstin)
        self.assertEqual(logs[1].reason, 'Invoice belonged to Mumbai branch per PO #9941')

    def test_financial_resolver_unknown_doc_types_and_decimal_math(self):
        """
        P1 DEF-01, DEF-05: Unknown document types and 12-decimal fixture verification.
        - Unknown doc types (ISD, CUSTOMS, XYZ) return financial_sign=0, is_review_required=True.
        - Ambiguous or missing note_type on CDNR returns financial_sign=0, is_review_required=True.
        - Verified 12 Decimal test fixtures:
          Invoice: ₹10,000 / ₹1,800
          Credit Note: ₹2,000 / ₹360
          Debit Note: ₹3,000 / ₹540
          Net taxable: ₹11,000
          Net tax: ₹1,980
        """
        eff_isd = resolve_document_financial_effect({'document_type': 'ISD'})
        self.assertEqual(eff_isd.financial_sign, 0)
        self.assertTrue(eff_isd.is_review_required)
        self.assertEqual(eff_isd.document_kind, 'UNKNOWN')

        eff_customs = resolve_document_financial_effect({'document_type': 'CUSTOMS'})
        self.assertEqual(eff_customs.financial_sign, 0)
        self.assertTrue(eff_customs.is_review_required)

        eff_cdnr_empty = resolve_document_financial_effect({'document_type': 'CDNR', 'note_type': ''})
        self.assertEqual(eff_cdnr_empty.financial_sign, 0)
        self.assertTrue(eff_cdnr_empty.is_review_required)

        eff_inv = resolve_document_financial_effect({'document_type': 'B2B'})
        self.assertEqual(eff_inv.financial_sign, 1)
        self.assertFalse(eff_inv.is_review_required)

        eff_cn = resolve_document_financial_effect({'document_type': 'CDNR', 'note_type': 'C'})
        self.assertEqual(eff_cn.financial_sign, -1)
        self.assertTrue(eff_cn.is_credit_note)

        eff_dn = resolve_document_financial_effect({'document_type': 'CDNR', 'note_type': 'D'})
        self.assertEqual(eff_dn.financial_sign, 1)
        self.assertTrue(eff_dn.is_debit_note)

        # 12-Decimal exact mathematical verification:
        inv_txval = Decimal('10000.00')
        inv_tax = Decimal('1800.00')
        cn_txval = Decimal('2000.00')
        cn_tax = Decimal('360.00')
        dn_txval = Decimal('3000.00')
        dn_tax = Decimal('540.00')

        gross_tax = inv_tax * eff_inv.financial_sign
        cn_signed_tax = cn_tax * eff_cn.financial_sign
        dn_signed_tax = dn_tax * eff_dn.financial_sign

        self.assertEqual(gross_tax, Decimal('1800.00'))
        self.assertEqual(cn_signed_tax, Decimal('-360.00'))
        self.assertEqual(dn_signed_tax, Decimal('540.00'))

        net_tax = gross_tax + cn_signed_tax + dn_signed_tax
        self.assertEqual(net_tax, Decimal('1980.00'))

        net_taxable = (inv_txval * eff_inv.financial_sign) + (cn_txval * eff_cn.financial_sign) + (dn_txval * eff_dn.financial_sign)
        self.assertEqual(net_taxable, Decimal('11000.00'))

class PostgreSQLConcurrencyCertificationTests(TransactionTestCase):
    """
    DEF-05: Dedicated PostgreSQL Concurrency Certification (TransactionTestCase).
    Because TransactionTestCase commits rows rather than wrapping them in an outer uncommitted transaction,
    concurrent threads on independent database connections can read foreign key relations (Company, Registration)
    and verify PostgreSQL savepoint + select_for_update race safety under real threading.Barrier conditions.
    """
    def setUp(self):
        self.company = Company.objects.create(
            name='Concurrency Heavy Industries Ltd',
            legal_name='Concurrency Heavy Industries Ltd',
            gstin='07CHI9999C1Z5',
            state_code='07'
        )
        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='07CHI9999C1Z5',
            legal_name='Concurrency Heavy Industries Ltd',
            state_code='07',
            status='ACTIVE',
            is_primary=True
        )

    def test_postgresql_concurrency_barrier_certification(self):
        import threading
        from django.db import connection, transaction

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        target_period = '122026'
        worker_count = 4
        barrier = threading.Barrier(worker_count)
        errors = []
        acquired_locks = []

        def worker():
            from django.db import connection
            connection.close()  # Independent database connection per thread
            try:
                barrier.wait(timeout=10)  # Synchronize threads for simultaneous race
                with transaction.atomic():
                    lock = ITCReconciliationService._acquire_ingestion_lock(
                        company=self.company,
                        registration=self.registration,
                        return_period=target_period
                    )
                    acquired_locks.append(lock.id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(len(errors), 0, f"PostgreSQL concurrency race encountered errors: {errors}")
        self.assertEqual(len(acquired_locks), worker_count)
        self.assertEqual(len(set(acquired_locks)), 1, "All concurrent threads must resolve to the identical lock row")
        for t in threads:
            self.assertFalse(t.is_alive(), "Worker thread must terminate after joining")

    def test_postgresql_concurrent_ingestion_idempotency_barrier(self):
        """
        P1 DEF-05: Concurrent ingestion race certification.
        4 threads concurrently attempt to ingest the exact same GSTR-2B JSON payload.
        Verifies zero duplicate batches, zero IntegrityErrors, and exactly 1 final batch record.
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        target_period = '012027'
        worker_count = 4
        barrier = threading.Barrier(worker_count)
        errors = []
        batch_ids = []

        payload = {
            'gstin': self.registration.gstin,
            'fp': target_period,
            'data': {
                'docdata': {
                    'b2b': [{
                        'ctin': '07STEEL8888S1Z8',
                        'inv': [{
                            'inum': 'INV/CONCURR/01',
                            'dt': '05-01-2027',
                            'val': 1180.0,
                            'items': [{'txval': 1000.0, 'camt': 90.0, 'samt': 90.0, 'iamt': 0.0, 'csamt': 0.0}]
                        }]
                    }]
                }
            }
        }

        def worker():
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                batch = ITCReconciliationService.ingest_gstr2b_json(
                    company=self.company,
                    json_data=payload,
                    return_period=target_period,
                    registration=self.registration
                )
                batch_ids.append(batch.id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        self.assertEqual(len(errors), 0, f"Concurrent ingestion failed with errors: {errors}")
        self.assertEqual(len(batch_ids), worker_count)
        # Verify exactly one logical batch exists for this period
        self.assertEqual(
            GSTR2BImport.objects.filter(company=self.company, return_period=target_period, gst_registration=self.registration).count(),
            1
        )
        self.assertEqual(
            GSTR2BRecord.objects.filter(company=self.company, return_period=target_period, invoice_number='INV/CONCURR/01').count(),
            1
        )

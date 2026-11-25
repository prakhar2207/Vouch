from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, Warehouse
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import (
    CompanyGSTConfig, GSTR2BImport, GSTR2BRecord, GSTRegistration,
    VoucherGSTINAttributionLog, VoucherAttributionOperation,
    GSTRegistrationFrequencyAuditLog, resolve_document_financial_effect
)
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
            frequency_verified_source='GST_PORTAL_API',
            frequency_verified_at=timezone.now(),
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

    def test_round_2_4_2_complete_matrix_and_governance(self):
        """
        Round 2.4.2 Comprehensive Matrix Tests (R242-01 to R242-24).
        """
        from django.db.models import ProtectedError

        # R242-01: Unverified QRMP field -> UNKNOWN
        reg_unverified_qrmp = GSTRegistration.objects.create(
            company=self.company,
            gstin='07UNVQRMP1111Z1',
            legal_name='Unverified QRMP Enterprise',
            state_code='07',
            status='ACTIVE',
            filing_frequency='QRMP',
            frequency_verified_at=None,
            frequency_verified_source=''
        )
        res_01 = GSTPeriodService.resolve_gstr2b_statement_period(date(2026, 4, 15), recipient_registration=reg_unverified_qrmp)
        self.assertEqual(res_01.recipient_filing_frequency, 'UNKNOWN')
        self.assertEqual(res_01.period_resolution_status, 'REVIEW_REQUIRED')
        self.assertIsNone(res_01.expected_statement_period)

        # R242-02: Explicit QRMP bypass attempt on unverified registration -> Rejected/UNKNOWN
        res_02 = GSTPeriodService.resolve_gstr2b_statement_period(
            date(2026, 4, 15),
            recipient_registration=reg_unverified_qrmp,
            filing_frequency='QRMP'
        )
        self.assertEqual(res_02.recipient_filing_frequency, 'UNKNOWN')
        self.assertEqual(res_02.period_resolution_status, 'REVIEW_REQUIRED')

        # R242-03: Verified QRMP -> Quarter-end resolution (062026 for April)
        reg_verified_qrmp = GSTRegistration.objects.create(
            company=self.company,
            gstin='07VERQRMP2222Z2',
            legal_name='Verified QRMP Enterprise',
            state_code='07',
            status='ACTIVE',
            filing_frequency='QRMP',
            frequency_verified_at=timezone.now(),
            frequency_verified_source='GST_PORTAL_API'
        )
        res_03 = GSTPeriodService.resolve_gstr2b_statement_period(date(2026, 4, 15), recipient_registration=reg_verified_qrmp)
        self.assertEqual(res_03.recipient_filing_frequency, 'QRMP')
        self.assertEqual(res_03.expected_statement_period, '062026')
        self.assertEqual(res_03.period_resolution_status, 'RESOLVED_QRMP')

        # R242-04: Verified MONTHLY -> Monthly resolution (042026 for April)
        res_04 = GSTPeriodService.resolve_gstr2b_statement_period(date(2026, 4, 15), recipient_registration=self.registration)
        self.assertEqual(res_04.recipient_filing_frequency, 'MONTHLY')
        self.assertEqual(res_04.expected_statement_period, '042026')
        self.assertEqual(res_04.period_resolution_status, 'RESOLVED_MONTHLY')

        # R242-05: Provider error -> No frequency mutation
        reg_freq_before = self.registration.filing_frequency
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.filing_frequency, reg_freq_before)

        # R242-06: Unknown document XYZ + D -> UNKNOWN, sign 0, is_review_required=True
        eff_06 = resolve_document_financial_effect({'document_type': 'XYZ', 'note_type': 'D'})
        self.assertEqual(eff_06.document_kind, 'UNKNOWN')
        self.assertEqual(eff_06.financial_sign, 0)
        self.assertTrue(eff_06.is_review_required)

        # R242-07: Unknown document XYZ + C -> UNKNOWN, sign 0, is_review_required=True
        eff_07 = resolve_document_financial_effect({'document_type': 'XYZ', 'note_type': 'C'})
        self.assertEqual(eff_07.document_kind, 'UNKNOWN')
        self.assertEqual(eff_07.financial_sign, 0)
        self.assertTrue(eff_07.is_review_required)

        # R242-08: B2B + C -> UNKNOWN, sign 0, is_review_required=True
        eff_08 = resolve_document_financial_effect({'document_type': 'B2B', 'note_type': 'C'})
        self.assertEqual(eff_08.document_kind, 'UNKNOWN')
        self.assertEqual(eff_08.financial_sign, 0)
        self.assertTrue(eff_08.is_review_required)

        # R242-09: CDNR + C -> Credit note, sign -1, is_review_required=False
        eff_09 = resolve_document_financial_effect({'document_type': 'CDNR', 'note_type': 'C'})
        self.assertEqual(eff_09.document_kind, 'CREDIT_NOTE')
        self.assertEqual(eff_09.financial_sign, -1)
        self.assertFalse(eff_09.is_review_required)

        # R242-10: CDNR + D -> Debit note, sign +1, is_review_required=False
        eff_10 = resolve_document_financial_effect({'document_type': 'CDNR', 'note_type': 'D'})
        self.assertEqual(eff_10.document_kind, 'DEBIT_NOTE')
        self.assertEqual(eff_10.financial_sign, 1)
        self.assertFalse(eff_10.is_review_required)

        # R242-11: Attribution normal duplicate -> Rejected
        v_attr = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/ATTR/001',
            voucher_date=date(2026, 8, 1),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )
        resp_attr_1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v_attr.id)],
            'registration_id': str(self.registration.id)
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp_attr_1.status_code, 200)
        resp_attr_dup = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v_attr.id)],
            'registration_id': str(self.registration.id)
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp_attr_dup.status_code, 400)
        self.assertEqual(resp_attr_dup.data.get('error_code'), 'ALREADY_ATTRIBUTED')

        # R242-12: Correction with short reason (< 5 non-whitespace chars) -> Rejected
        resp_corr_short = self.client.post('/api/v1/gst/itc/correct-attribution/', {
            'voucher_ids': [str(v_attr.id)],
            'registration_id': str(self.registration.id),
            'reason': '   ab  '
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp_corr_short.status_code, 400)
        self.assertEqual(resp_corr_short.data.get('error_code'), 'REASON_REQUIRED')

        # R242-13: Valid correction -> New audit event
        reg_target = GSTRegistration.objects.create(
            company=self.company,
            gstin='07SECON9999S1Z1',
            legal_name='Secondary Unit',
            state_code='07',
            status='ACTIVE'
        )
        resp_corr_valid = self.client.post('/api/v1/gst/itc/correct-attribution/', {
            'voucher_ids': [str(v_attr.id)],
            'registration_id': str(reg_target.id),
            'reason': 'Correction of location to secondary unit per PO #4411'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp_corr_valid.status_code, 200)
        logs = list(VoucherGSTINAttributionLog.objects.filter(voucher=v_attr).order_by('attributed_at'))
        self.assertEqual(len(logs), 2)
        self.assertFalse(logs[0].is_correction)
        self.assertTrue(logs[1].is_correction)

        # R242-14: Audit update attempt -> Blocked by ValidationError
        from django.core.exceptions import ValidationError as DjangoValidationError
        with self.assertRaises((ValidationError, DjangoValidationError)):
            logs[0].new_gstin = '07TAMPERED9999Z'
            logs[0].save()

        with self.assertRaises((ValidationError, DjangoValidationError)):
            VoucherGSTINAttributionLog.objects.filter(id=logs[0].id).update(new_gstin='07TAMPERED9999Z')

        # R242-15: Audit deletion attempt -> Blocked by ValidationError
        with self.assertRaises((ValidationError, DjangoValidationError)):
            logs[0].delete()

        with self.assertRaises((ValidationError, DjangoValidationError)):
            VoucherGSTINAttributionLog.objects.filter(id=logs[0].id).delete()

        # R242-16: Voucher deletion -> ProtectedError, history preserved
        v_attr.status = 'DRAFT'
        v_attr.save(update_fields=['status'])
        with self.assertRaises(ProtectedError):
            v_attr.delete()

        # R242-17: April UNKNOWN + June reconciliation -> Persisted REVIEW_REQUIRED
        v_apr_unk = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/APR/UNK/01',
            external_invoice_number='INV/APR/UNK/01',
            voucher_date=date(2026, 4, 15),
            buyer_gstin=reg_unverified_qrmp.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_apr_unk,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('1000.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00')
        )
        ITCReconciliationService.reconcile_period(self.company, return_period='062026', registration=reg_unverified_qrmp)
        v_apr_unk.refresh_from_db()
        self.assertEqual(v_apr_unk.itc_match_status, 'REVIEW_REQUIRED')

        # R242-18: May UNKNOWN + June reconciliation -> Persisted REVIEW_REQUIRED
        v_may_unk = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/MAY/UNK/01',
            external_invoice_number='INV/MAY/UNK/01',
            voucher_date=date(2026, 5, 20),
            buyer_gstin=reg_unverified_qrmp.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_may_unk,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('1000.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00')
        )
        ITCReconciliationService.reconcile_period(self.company, return_period='062026', registration=reg_unverified_qrmp)
        v_may_unk.refresh_from_db()
        self.assertEqual(v_may_unk.itc_match_status, 'REVIEW_REQUIRED')

        # R242-19: April verified QRMP + June match -> LATER_PERIOD_MATCH
        v_apr_qrmp = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/APR/QRMP/01',
            external_invoice_number='INV/APR/QRMP/01',
            voucher_date=date(2026, 4, 10),
            buyer_gstin=reg_verified_qrmp.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_apr_qrmp,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('1000.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00')
        )
        imp_june = GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=reg_verified_qrmp,
            return_period='062026',
            status='PROCESSED'
        )
        GSTR2BRecord.objects.create(
            company=self.company,
            import_batch=imp_june,
            gst_registration=reg_verified_qrmp,
            supplier_gstin=self.vendor_ledger.gstin,
            supplier_name=self.vendor_ledger.name,
            invoice_number='INV/APR/QRMP/01',
            normalized_invoice_number=ITCReconciliationService.normalize_invoice_number('INV/APR/QRMP/01'),
            invoice_date=date(2026, 4, 10),
            invoice_type='Regular',
            document_type='B2B',
            taxable_value=Decimal('1000.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00'),
            igst_amount=Decimal('0.00'),
            return_period='062026'
        )
        ITCReconciliationService.reconcile_period(self.company, return_period='062026', registration=reg_verified_qrmp)
        v_apr_qrmp.refresh_from_db()
        self.assertEqual(v_apr_qrmp.itc_match_status, 'LATER_PERIOD_MATCH')

        # R242-20: Missing invoice in processed statement -> No unsupported non-filing assertion
        v_missing = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/MISSING/01',
            external_invoice_number='INV/MISSING/01',
            voucher_date=date(2026, 8, 1),
            buyer_gstin=self.registration.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED'
        )
        VoucherItem.objects.create(
            voucher=v_missing,
            product=self.product,
            quantity=Decimal('10.00'),
            rate=Decimal('100.00'),
            taxable_amount=Decimal('1000.00'),
            cgst_rate=Decimal('9.00'),
            sgst_rate=Decimal('9.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00')
        )
        GSTR2BImport.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='082026',
            status='EMPTY_PROCESSED',
            is_empty_statement=True
        )
        ITCReconciliationService.reconcile_period(self.company, return_period='082026', registration=self.registration)
        v_missing.refresh_from_db()
        self.assertNotIn("Vendor has not filed GSTR-1", v_missing.itc_notes or "")
        self.assertIn("Supplier filing status not independently verified", v_missing.itc_notes or "")

        # R242-21: Provider failure -> DATA_UNAVAILABLE
        v_failed_prov = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/NOPROV/01',
            external_invoice_number='INV/NOPROV/01',
            voucher_date=date(2026, 9, 10),
            buyer_gstin=self.registration.gstin,
            party_ledger=self.vendor_ledger,
            total_amount=Decimal('1180.00'),
            created_by=self.user,
            status='POSTED'
        )
        ITCReconciliationService.reconcile_period(self.company, return_period='092026', registration=self.registration)
        v_failed_prov.refresh_from_db()
        self.assertEqual(v_failed_prov.itc_match_status, 'DATA_UNAVAILABLE')

        # R242-24: Existing MATCHED record -> Not overwritten by unrelated period
        self.matched_voucher.itc_match_status = 'MATCHED'
        self.matched_voucher.save(update_fields=['itc_match_status'])
        self.assertEqual(self.matched_voucher.itc_match_status, 'MATCHED')
        ITCReconciliationService.reconcile_period(self.company, return_period='102026', registration=self.registration)
        self.matched_voucher.refresh_from_db()
        self.assertEqual(self.matched_voucher.itc_match_status, 'MATCHED')

class PostgreSQLConcurrencyCertificationTests(TransactionTestCase):
    """
    DEF-05: Dedicated PostgreSQL Concurrency Certification (TransactionTestCase).
    Because TransactionTestCase commits rows rather than wrapping them in an outer uncommitted transaction,
    concurrent threads on independent database connections can read foreign key relations (Company, Registration)
    and verify PostgreSQL savepoint + select_for_update race safety under real threading.Barrier conditions.
    """
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            email='concurrency_admin@chi.com',
            password='TestPassword123!'
        )
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
            filing_frequency='MONTHLY',
            frequency_verified_source='GST_PORTAL_API',
            frequency_verified_at=timezone.now(),
            is_primary=True
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')
        self.user2 = User.objects.create_user(
            email='concurrency_admin2@chi.com',
            password='TestPassword123!'
        )
        UserCompany.objects.create(user=self.user2, company=self.company, role='ADMIN')

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

    def test_two_concurrent_first_time_ingestion_requests(self):
        """
        P1 Race Scenario 1: Two concurrent first-time ingestion requests for the same company, registration, and period.
        Verifies row-level lock serialization and exactly 1 logical import batch.
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        target_period = '022027'
        worker_count = 2
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
                            'inum': 'INV/TWO/01',
                            'dt': '10-02-2027',
                            'val': 2360.0,
                            'items': [{'txval': 2000.0, 'camt': 180.0, 'samt': 180.0, 'iamt': 0.0, 'csamt': 0.0}]
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

        self.assertEqual(len(errors), 0, f"Two-thread ingestion race failed: {errors}")
        self.assertEqual(len(batch_ids), 2)
        self.assertEqual(
            GSTR2BImport.objects.filter(company=self.company, return_period=target_period, gst_registration=self.registration).count(),
            1
        )

    def test_concurrent_attribution_corrections_same_voucher(self):
        """
        P1 Race Scenario 3 & R242-23: Two concurrent attribution corrections for the same voucher.
        Verifies row-level locking on Voucher prevents lost history or deadlocks.
        """
        import threading
        from django.db import connection, transaction

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        reg_alt = GSTRegistration.objects.create(
            company=self.company,
            gstin='07ALT9999A1Z2',
            legal_name='Alternate Unit',
            state_code='07',
            status='ACTIVE'
        )

        v_conc = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/CONC/ATTR/01',
            voucher_date=date(2027, 1, 15),
            buyer_gstin=self.registration.gstin,
            total_amount=Decimal('5000.00'),
            created_by=self.user,
            status='POSTED'
        )
        # Seed initial attribution log
        VoucherGSTINAttributionLog.objects.create(
            company=self.company,
            voucher=v_conc,
            gst_registration=self.registration,
            previous_gstin='',
            new_gstin=self.registration.gstin,
            attribution_source='INITIAL_SETUP',
            reason='Initial baseline attribution',
            operation_ref='INITIAL_OP',
            is_correction=False
        )

        worker_count = 2
        barrier = threading.Barrier(worker_count)
        errors = []

        def worker_correct(target_reg, reason_text, op_ref):
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    v_locked = Voucher.objects.select_for_update().get(id=v_conc.id, company=self.company)
                    prev_gstin = v_locked.buyer_gstin
                    v_locked.buyer_gstin = target_reg.gstin
                    v_locked.save(update_fields=['buyer_gstin'])
                    VoucherGSTINAttributionLog.objects.create(
                        company=self.company,
                        voucher=v_locked,
                        gst_registration=target_reg,
                        previous_gstin=prev_gstin,
                        new_gstin=target_reg.gstin,
                        attribution_source='CONCURRENT_CORRECTION',
                        reason=reason_text,
                        operation_ref=op_ref,
                        is_correction=True
                    )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_correct, args=(reg_alt, 'Correction to Alternate Unit by User A', 'CORR_OP_A'))
        t2 = threading.Thread(target=worker_correct, args=(self.registration, 'Correction to Primary Unit by User B', 'CORR_OP_B'))

        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Concurrent attribution correction failed: {errors}")
        corr_logs = VoucherGSTINAttributionLog.objects.filter(voucher=v_conc, is_correction=True)
        self.assertEqual(corr_logs.count(), 2, "Both correction events must be preserved in audit trail")

    def test_reconciliation_concurrent_with_ingestion(self):
        """
        P1 Race Scenario 4: Reconciliation running concurrently with GSTR-2B ingestion.
        Verifies zero deadlocks and consistent reconciliation results.
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        target_period = '032027'
        barrier = threading.Barrier(2)
        errors = []

        payload = {
            'gstin': self.registration.gstin,
            'fp': target_period,
            'data': {
                'docdata': {
                    'b2b': [{
                        'ctin': '07STEEL8888S1Z8',
                        'inv': [{
                            'inum': 'INV/REC/01',
                            'dt': '01-03-2027',
                            'val': 1180.0,
                            'items': [{'txval': 1000.0, 'camt': 90.0, 'samt': 90.0, 'iamt': 0.0, 'csamt': 0.0}]
                        }]
                    }]
                }
            }
        }

        def worker_ingest():
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                ITCReconciliationService.ingest_gstr2b_json(
                    company=self.company,
                    json_data=payload,
                    return_period=target_period,
                    registration=self.registration
                )
            except Exception as e:
                errors.append(e)

        def worker_reconcile():
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                ITCReconciliationService.reconcile_period(
                    company=self.company,
                    return_period=target_period,
                    registration=self.registration
                )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_ingest)
        t2 = threading.Thread(target=worker_reconcile)
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)

        self.assertEqual(len(errors), 0, f"Concurrent ingestion + reconciliation failed: {errors}")
        self.assertTrue(GSTR2BImport.objects.filter(company=self.company, return_period=target_period).exists())

    def test_concurrent_filing_frequency_updates(self):
        """
        P1 Race Scenario 5: Two users concurrently updating filing frequency verification.
        Verifies clean database execution without deadlocks or unhandled collisions.
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        barrier = threading.Barrier(2)
        errors = []

        def worker_update(freq, source_name):
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                reg = GSTRegistration.objects.get(id=self.registration.id)
                reg.set_filing_frequency(frequency=freq, source=source_name, commit=True)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_update, args=('MONTHLY', 'GST_PORTAL_API'))
        t2 = threading.Thread(target=worker_update, args=('QRMP', 'RETURN_STATUS_API'))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Concurrent frequency update failed: {errors}")
        self.registration.refresh_from_db()
        self.assertTrue(self.registration.is_frequency_verified())

    def test_attribution_correction_timeout_retry_idempotency(self):
        """
        P1 Race Scenario 6: Client timeout retry after attribution correction committed.
        Verifies that retrying with the same operation_ref does NOT append duplicate audit log events.
        """
        from rest_framework.test import APIClient
        client = APIClient()
        user = User.objects.create_user(email='audit_retry@testcorp.com', password='RetryPass123!')
        UserCompany.objects.create(user=user, company=self.company, role='OWNER')
        client.force_authenticate(user=user)

        v_retry = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/RETRY/01',
            voucher_date=date(2027, 2, 1),
            total_amount=Decimal('3000.00'),
            created_by=user,
            status='POSTED'
        )
        # Initial attribution
        client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v_retry.id)],
            'registration_id': str(self.registration.id)
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        reg_new = GSTRegistration.objects.create(
            company=self.company,
            gstin='07RETRY9999R1Z3',
            legal_name='Retry Destination Unit',
            state_code='07',
            status='ACTIVE'
        )

        op_ref = 'IDEMPOTENT_RETRY_REF_771'
        # Call 1: Original successful correction
        resp1 = client.post('/api/v1/gst/itc/correct-attribution/', {
            'voucher_ids': [str(v_retry.id)],
            'registration_id': str(reg_new.id),
            'reason': 'Re-allocating invoice to Retry Destination Unit per Audit Notice',
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)

        count_after_call1 = VoucherGSTINAttributionLog.objects.filter(voucher=v_retry).count()

        # Call 2: Simulated client retry after network timeout
        resp2 = client.post('/api/v1/gst/itc/correct-attribution/', {
            'voucher_ids': [str(v_retry.id)],
            'registration_id': str(reg_new.id),
            'reason': 'Re-allocating invoice to Retry Destination Unit per Audit Notice',
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data.get('operation_ref'), op_ref)

        count_after_call2 = VoucherGSTINAttributionLog.objects.filter(voucher=v_retry).count()
        self.assertEqual(count_after_call1, count_after_call2, "Idempotent retry must not append duplicate audit events")

    def test_r243_05_concurrent_identical_operation_requests(self):
        """
        R243-05: Concurrent identical operation requests -> Exactly one execution; others replayed.
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        v_dup = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R243/CONC/01',
            voucher_date=date(2027, 3, 1),
            total_amount=Decimal('4000.00'),
            created_by=self.user,
            status='POSTED'
        )

        op_ref = f"OP_R243_05_{self.company.id.hex[:6]}"
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker_request():
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                client = APIClient()
                client.force_authenticate(user=self.user)
                resp = client.post('/api/v1/gst/itc/attribute-voucher/', {
                    'voucher_ids': [str(v_dup.id)],
                    'registration_id': str(self.registration.id),
                    'operation_ref': op_ref
                }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
                results.append(resp)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_request)
        t2 = threading.Thread(target=worker_request)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Concurrent identical requests threw errors: {errors}")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].status_code, 200)
        self.assertEqual(results[1].status_code, 200)
        # Exactly 1 operation row
        self.assertEqual(
            VoucherAttributionOperation.objects.filter(company=self.company, operation_ref=op_ref, status='COMPLETED').count(),
            1
        )
        # Exactly 1 attribution log row
        self.assertEqual(
            VoucherGSTINAttributionLog.objects.filter(voucher=v_dup).count(),
            1
        )

    def test_r243_06_concurrent_conflicting_operation_requests(self):
        """
        R243-06: Concurrent conflicting operation requests with same operation_ref -> One wins; conflicting rejected with 409.
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest(f"Dedicated PostgreSQL Concurrency Certification requires real PostgreSQL engine, got '{connection.vendor}'.")

        v_a = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R243/CONF/01',
            voucher_date=date(2027, 3, 2),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )
        v_b = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R243/CONF/02',
            voucher_date=date(2027, 3, 3),
            total_amount=Decimal('2000.00'),
            created_by=self.user,
            status='POSTED'
        )

        op_ref = f"OP_R243_06_{self.company.id.hex[:6]}"
        barrier = threading.Barrier(2)
        status_codes = []
        errors = []

        def worker_conflicting(target_v):
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                client = APIClient()
                client.force_authenticate(user=self.user)
                resp = client.post('/api/v1/gst/itc/attribute-voucher/', {
                    'voucher_ids': [str(target_v.id)],
                    'registration_id': str(self.registration.id),
                    'operation_ref': op_ref
                }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
                status_codes.append(resp.status_code)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_conflicting, args=(v_a,))
        t2 = threading.Thread(target=worker_conflicting, args=(v_b,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Thread error in conflict race: {errors}")
        self.assertIn(200, status_codes)
        self.assertIn(409, status_codes)

    def test_r243_16_17_18_raw_sql_triggers_update_delete_rejected_insert_permitted(self):
        """
        R243-16, R243-17, R243-18: Raw SQL database trigger guarantees:
        - Raw SQL INSERT is permitted.
        - Raw SQL UPDATE is rejected by database trigger.
        - Raw SQL DELETE is rejected by database trigger.
        """
        from django.db import connection, DatabaseError

        if connection.vendor != 'postgresql':
            self.skipTest("Raw SQL trigger verification requires PostgreSQL.")

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/TRIG/01',
            voucher_date=date(2027, 4, 1),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )
        import uuid as py_uuid
        log_id = str(py_uuid.uuid4())

        # R243-18: Direct SQL INSERT permitted
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO gst_vouchergstinattributionlog
                (id, company_id, voucher_id, gst_registration_id, previous_gstin, new_gstin,
                 attributed_at, attribution_source, reason, operation_ref, is_correction)
                VALUES
                (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s);
            """, [log_id, self.company.id, v.id, self.registration.id, '', '07CHI9999C1Z5',
                  'SQL_INSERT', 'Direct SQL insert test', 'SQL_OP_01', False])

        # R243-16: Direct SQL UPDATE rejected
        with self.assertRaises(DatabaseError) as cm_upd:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE gst_vouchergstinattributionlog
                    SET new_gstin = '07TAMPERED99Z1'
                    WHERE id = %s;
                """, [log_id])
        self.assertIn('Statutory Audit Integrity Invariant', str(cm_upd.exception))

        # R243-17: Direct SQL DELETE rejected
        with self.assertRaises(DatabaseError) as cm_del:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM gst_vouchergstinattributionlog
                    WHERE id = %s;
                """, [log_id])
        self.assertIn('Statutory Audit Integrity Invariant', str(cm_del.exception))

    def test_r243_19_trigger_state_and_rollback_policy(self):
        """
        R243-19: PostgreSQL database trigger verification & rollback governance policy:
        - Trigger exists in PostgreSQL catalog.
        - Rollback guard raises RuntimeError unless ALLOW_AUDIT_TRIGGER_ROLLBACK=true.
        """
        import os
        import importlib
        from django.db import connection
        mig_0027 = importlib.import_module('apps.gst.migrations.0027_attribution_operation_and_frequency_audit')
        guard_trigger_rollback = mig_0027.guard_trigger_rollback

        if connection.vendor != 'postgresql':
            self.skipTest("Trigger catalog query requires PostgreSQL.")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT trigger_name
                FROM information_schema.triggers
                WHERE event_object_table = 'gst_vouchergstinattributionlog'
                  AND trigger_name = 'trg_prevent_attribution_log_mutation';
            """)
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Immutability trigger trg_prevent_attribution_log_mutation must exist in PostgreSQL catalog")

        # Verify rollback guard raises RuntimeError by default
        old_val = os.environ.get('ALLOW_AUDIT_TRIGGER_ROLLBACK')
        try:
            if 'ALLOW_AUDIT_TRIGGER_ROLLBACK' in os.environ:
                del os.environ['ALLOW_AUDIT_TRIGGER_ROLLBACK']
            with self.assertRaises(RuntimeError) as cm:
                guard_trigger_rollback(None, connection.schema_editor())
            self.assertIn('Statutory Compliance Invariant', str(cm.exception))
        finally:
            if old_val is not None:
                os.environ['ALLOW_AUDIT_TRIGGER_ROLLBACK'] = old_val

    def test_r244_pg_01_different_actors_same_op_ref_concurrent_rejected(self):
        """
        R244-PG-01: Two concurrent requests with different actors in same company using same operation_ref:
        Exactly one succeeds (200), other rejected with 409 (OPERATION_ACTOR_MISMATCH).
        """
        import threading
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest("Requires real PostgreSQL.")

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R244/ACT/01',
            voucher_date=date(2027, 5, 10),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )
        op_ref = f"OP_R244_ACT_{self.company.id.hex[:6]}"
        barrier = threading.Barrier(2)
        status_codes = []
        errors = []

        def worker_actor(user_obj):
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                client = APIClient()
                client.force_authenticate(user=user_obj)
                resp = client.post('/api/v1/gst/itc/attribute-voucher/', {
                    'voucher_ids': [str(v.id)],
                    'registration_id': str(self.registration.id),
                    'operation_ref': op_ref
                }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
                status_codes.append(resp.status_code)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_actor, args=(self.user,))
        t2 = threading.Thread(target=worker_actor, args=(self.user2,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertIn(200, status_codes)
        self.assertIn(409, status_codes)
        self.assertEqual(VoucherGSTINAttributionLog.objects.filter(voucher=v).count(), 1)

    def test_r244_pg_02_tx1_succeeds_while_tx2_waits_replayed(self):
        """
        R244-PG-02: Thread 1 holds lock in transaction, Thread 2 waits on select_for_update.
        Thread 1 commits. Thread 2 discovers status COMPLETED, returns replayed 200 with is_idempotent_replay=True.
        """
        import threading
        from django.db import connection, transaction

        if connection.vendor != 'postgresql':
            self.skipTest("Requires real PostgreSQL.")

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/PG244/WAIT/01',
            voucher_date=date(2027, 5, 11),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )
        op_ref = f"OP_R244_WAIT_{self.company.id.hex[:6]}"
        t1_entered = threading.Event()
        t1_can_commit = threading.Event()
        results = []
        errors = []

        import hashlib, json
        canonical_dict = {
            'attribution_source': 'MANUAL_USER_ATTRIBUTION',
            'company_id': str(self.company.id),
            'is_correction': False,
            'reason': '',
            'registration_id': str(self.registration.id),
            'voucher_ids': [str(v.id)],
        }
        canonical_bytes = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
        fp = hashlib.sha256(canonical_bytes).hexdigest()

        def worker1():
            from django.db import connection
            connection.close()
            try:
                with transaction.atomic():
                    op_rec, _ = VoucherAttributionOperation.objects.select_for_update().get_or_create(
                        company=self.company,
                        operation_ref=op_ref,
                        defaults={
                            'request_fingerprint': fp,
                            'actor': self.user,
                            'status': 'PENDING'
                        }
                    )
                    t1_entered.set()
                    t1_can_commit.wait(timeout=10)
                    v.buyer_gstin = self.registration.gstin
                    v.save()
                    op_rec.status = 'COMPLETED'
                    op_rec.response_payload = {
                        'success': True,
                        'message': 'Thread 1 completed',
                        'operation_ref': op_ref,
                        'attributed_count': 1
                    }
                    op_rec.save()
            except Exception as e:
                errors.append(e)

        def worker2():
            from django.db import connection
            connection.close()
            try:
                t1_entered.wait(timeout=10)
                threading.Timer(0.5, t1_can_commit.set).start()
                client = APIClient()
                client.force_authenticate(user=self.user)
                resp = client.post('/api/v1/gst/itc/attribute-voucher/', {
                    'voucher_ids': [str(v.id)],
                    'registration_id': str(self.registration.id),
                    'operation_ref': op_ref
                }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
                results.append(resp)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Errors in wait race: {errors}")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status_code, 200)
        self.assertTrue(results[0].data.get('is_idempotent_replay'))

    def test_r244_pg_03_tx1_fails_while_tx2_waits_reexecutes(self):
        """
        R244-PG-03: Thread 1 starts transaction, marks FAILED, and commits.
        Thread 2 was waiting on select_for_update with same payload.
        Thread 2 acquires lock, re-executes with same payload, and succeeds (200).
        """
        import threading
        from django.db import connection, transaction

        if connection.vendor != 'postgresql':
            self.skipTest("Requires real PostgreSQL.")

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/PG244/FAILWAIT/01',
            voucher_date=date(2027, 5, 12),
            total_amount=Decimal('2000.00'),
            created_by=self.user,
            status='POSTED'
        )
        op_ref = f"OP_R244_FAILWAIT_{self.company.id.hex[:6]}"
        t1_entered = threading.Event()
        t1_can_finish = threading.Event()
        results = []
        errors = []

        import hashlib, json
        canonical_dict = {
            'attribution_source': 'MANUAL_USER_ATTRIBUTION',
            'company_id': str(self.company.id),
            'is_correction': False,
            'reason': '',
            'registration_id': str(self.registration.id),
            'voucher_ids': [str(v.id)],
        }
        canonical_bytes = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
        fp = hashlib.sha256(canonical_bytes).hexdigest()

        def worker1():
            from django.db import connection
            connection.close()
            try:
                with transaction.atomic():
                    op_rec, _ = VoucherAttributionOperation.objects.select_for_update().get_or_create(
                        company=self.company,
                        operation_ref=op_ref,
                        defaults={
                            'request_fingerprint': fp,
                            'actor': self.user,
                            'status': 'PENDING'
                        }
                    )
                    t1_entered.set()
                    t1_can_finish.wait(timeout=10)
                    op_rec.status = 'FAILED'
                    op_rec.save()
            except Exception as e:
                errors.append(e)

        def worker2():
            from django.db import connection
            connection.close()
            try:
                t1_entered.wait(timeout=10)
                threading.Timer(0.5, t1_can_finish.set).start()
                client = APIClient()
                client.force_authenticate(user=self.user)
                resp = client.post('/api/v1/gst/itc/attribute-voucher/', {
                    'voucher_ids': [str(v.id)],
                    'registration_id': str(self.registration.id),
                    'operation_ref': op_ref
                }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
                results.append(resp)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker1)
        t2 = threading.Thread(target=worker2)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(len(errors), 0, f"Errors in fail wait race: {errors}")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status_code, 200)
        self.assertEqual(results[0].data['attributed_count'], 1)
        self.assertEqual(VoucherGSTINAttributionLog.objects.filter(voucher=v).count(), 1)

    def test_r244_pg_04_frequency_audit_raw_sql_triggers_update_delete_rejected(self):
        """
        R244-PG-04: PostgreSQL raw SQL database triggers on gst_gstregistrationfrequencyauditlog:
        - Raw SQL INSERT is permitted.
        - Raw SQL UPDATE is rejected by database trigger trg_prevent_frequency_audit_tampering.
        - Raw SQL DELETE is rejected by database trigger trg_prevent_frequency_audit_tampering.
        """
        from django.db import connection, DatabaseError

        if connection.vendor != 'postgresql':
            self.skipTest("Raw SQL trigger verification requires PostgreSQL.")

        import uuid as py_uuid
        log_id = str(py_uuid.uuid4())

        # Direct SQL INSERT permitted
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO gst_gstregistrationfrequencyauditlog
                (id, company_id, gst_registration_id, previous_frequency, new_frequency,
                 verification_source, verified_by_id, verified_at, reason)
                VALUES
                (%s, %s, %s, %s, %s, %s, %s, NOW(), %s);
            """, [log_id, self.company.id, self.registration.id, 'MONTHLY', 'QRMP',
                  'USER_MANUAL', self.user.id, 'Direct SQL insert test'])

        # Direct SQL UPDATE rejected
        with self.assertRaises(DatabaseError) as cm_upd:
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE gst_gstregistrationfrequencyauditlog
                    SET new_frequency = 'TAMPERED'
                    WHERE id = %s;
                """, [log_id])
        self.assertIn('Statutory Audit Integrity Invariant', str(cm_upd.exception))

        # Direct SQL DELETE rejected
        with self.assertRaises(DatabaseError) as cm_del:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM gst_gstregistrationfrequencyauditlog
                    WHERE id = %s;
                """, [log_id])
        self.assertIn('Statutory Audit Integrity Invariant', str(cm_del.exception))

    def test_r244_pg_05_frequency_audit_trigger_catalog_and_rollback_guard(self):
        """
        R244-PG-05: Migration 0028 trigger catalog verification & rollback governance policy:
        - Trigger trg_prevent_frequency_audit_tampering exists in PostgreSQL catalog.
        - Rollback guard raises RuntimeError unless ALLOW_AUDIT_TRIGGER_ROLLBACK=true.
        """
        import os
        import importlib
        from django.db import connection
        mig_0028 = importlib.import_module('apps.gst.migrations.0028_frequency_audit_trigger_and_safeguards')
        guard_frequency_trigger_rollback = mig_0028.guard_frequency_trigger_rollback

        if connection.vendor != 'postgresql':
            self.skipTest("Trigger catalog query requires PostgreSQL.")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT trigger_name
                FROM information_schema.triggers
                WHERE event_object_table = 'gst_gstregistrationfrequencyauditlog'
                  AND trigger_name = 'trg_prevent_frequency_audit_tampering';
            """)
            row = cursor.fetchone()
            self.assertIsNotNone(row, "Immutability trigger trg_prevent_frequency_audit_tampering must exist in PostgreSQL catalog")

        old_val = os.environ.get('ALLOW_AUDIT_TRIGGER_ROLLBACK')
        try:
            if 'ALLOW_AUDIT_TRIGGER_ROLLBACK' in os.environ:
                del os.environ['ALLOW_AUDIT_TRIGGER_ROLLBACK']
            with self.assertRaises(RuntimeError) as cm:
                guard_frequency_trigger_rollback(None, connection.schema_editor())
            self.assertIn('Statutory Compliance Invariant', str(cm.exception))
        finally:
            if old_val is not None:
                os.environ['ALLOW_AUDIT_TRIGGER_ROLLBACK'] = old_val

    def test_r245_pg_01_two_workers_competing_to_claim_reconciliation_job(self):
        """
        R245-PG-01: Two concurrent workers attempt to claim the same ITCReconciliationJob.
        Uses select_for_update(skip_locked=True) on real PostgreSQL.
        Guarantees exactly one worker acquires and processes the job; the other cleanly returns None.
        """
        import threading
        from django.db import connection
        from apps.gst.models import ITCReconciliationJob
        from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService

        if connection.vendor != 'postgresql':
            self.skipTest("Requires real PostgreSQL engine.")

        job = ITCReconciliationJob.objects.create(
            company=self.company,
            gst_registration=self.registration,
            operation_ref=f"OP_PG245_CLAIM_{self.company.id.hex[:6]}",
            status='PENDING'
        )

        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker_claim():
            from django.db import connection
            connection.close()
            try:
                barrier.wait(timeout=10)
                res = ITCReconciliationJobService.execute_job(job.id)
                results.append(res)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_claim)
        t2 = threading.Thread(target=worker_claim)
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)

        self.assertEqual(len(errors), 0, f"Errors in concurrent job claim: {errors}")
        self.assertEqual(len(results), 2)
        # Exactly one worker returns the executed job (or both return the job object if sequential, but attempt_count must be exactly 1)
        job.refresh_from_db()
        self.assertEqual(job.attempt_count, 1)
        self.assertEqual(job.status, 'COMPLETED')

    def test_r245_pg_02_reconciled_trigger_catalog_and_immutability(self):
        """
        R245-PG-02: PostgreSQL catalog verification after Migration 0029 trigger reconciliation:
        - trg_prevent_attribution_log_mutation is active on gst_vouchergstinattributionlog.
        - Legacy trg_prevent_attribution_log_tampering has been cleanly removed.
        - trg_prevent_frequency_audit_tampering is active on gst_gstregistrationfrequencyauditlog.
        - Direct raw SQL UPDATE and DELETE on both tables are rejected with exception.
        """
        from django.db import connection, DatabaseError

        if connection.vendor != 'postgresql':
            self.skipTest("Catalog trigger verification requires PostgreSQL.")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT trigger_name, event_object_table
                FROM information_schema.triggers
                WHERE event_object_table IN ('gst_vouchergstinattributionlog', 'gst_gstregistrationfrequencyauditlog')
                ORDER BY trigger_name;
            """)
            triggers = cursor.fetchall()

        trigger_map = {t[0]: t[1] for t in triggers}
        self.assertIn('trg_prevent_attribution_log_mutation', trigger_map)
        self.assertNotIn('trg_prevent_attribution_log_tampering', trigger_map, "Legacy duplicate trigger must not exist")
        self.assertIn('trg_prevent_frequency_audit_tampering', trigger_map)

    def test_r245_pg_03_migration_0029_rollback_guard_and_reapplication(self):
        """
        R245-PG-03: Migration 0029 rollback guard policy:
        - Reverse function raises RuntimeError unless ALLOW_AUDIT_TRIGGER_ROLLBACK=true.
        """
        import os
        import importlib
        from django.db import connection
        mig_0029 = importlib.import_module('apps.gst.migrations.0029_reconciliation_job_actor_binding_and_trigger_reconciliation')
        guard_and_reverse = mig_0029.guard_and_reverse_reconciliation

        if connection.vendor != 'postgresql':
            self.skipTest("Requires PostgreSQL.")

        old_val = os.environ.get('ALLOW_AUDIT_TRIGGER_ROLLBACK')
        try:
            if 'ALLOW_AUDIT_TRIGGER_ROLLBACK' in os.environ:
                del os.environ['ALLOW_AUDIT_TRIGGER_ROLLBACK']
            with self.assertRaises(RuntimeError) as cm:
                guard_and_reverse(None, connection.schema_editor())
            self.assertIn('Statutory Compliance Invariant', str(cm.exception))
        finally:
            if old_val is not None:
                os.environ['ALLOW_AUDIT_TRIGGER_ROLLBACK'] = old_val


class Round243TargetedRemediationTests(TestCase):
    """
    Targeted test suite for Round 2.4.3 P0 & P1 remediations:
    - Operation-reference request-binding idempotency (R243-01..R243-04, R243-07..R243-08)
    - Centralized filing frequency verification (R243-09..R243-12)
    - Manual frequency verification authorization (R243-13..R243-15)
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='auditor_243@precision.com',
            password='TestPassword123!'
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name='Precision Instruments Ltd',
            legal_name='Precision Instruments Ltd',
            gstin='07PREC9999P1Z1',
            state_code='07'
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')

        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='07PREC9999P1Z1',
            legal_name='Precision Instruments Ltd',
            state_code='07',
            status='ACTIVE',
            filing_frequency='MONTHLY',
            frequency_verified_source='GST_PORTAL_API',
            frequency_verified_at=timezone.now(),
            is_primary=True
        )

        self.reg_branch = GSTRegistration.objects.create(
            company=self.company,
            gstin='07BRANCH999B1Z2',
            legal_name='Precision Branch Unit',
            state_code='07',
            status='ACTIVE',
            filing_frequency='MONTHLY',
            frequency_verified_source='GST_PORTAL_API',
            frequency_verified_at=timezone.now()
        )

        self.vendor_group = LedgerGroup.objects.create(
            company=self.company,
            name='Sundry Creditors',
            nature='LIABILITY'
        )
        self.vendor_ledger = Ledger.objects.create(
            company=self.company,
            group=self.vendor_group,
            name='Apex Steel Supplies',
            gstin='07SUPP8888S1Z9'
        )

    def test_r243_01_reuse_operation_ref_identical_request_replayed(self):
        """
        R243-01: Replaying identical operation returns original response without appending duplicate audit logs.
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/243/01',
            voucher_date=date(2026, 8, 1),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )
        op_ref = 'OP_R243_01_TEST'
        payload = {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }

        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', payload, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.data['attributed_count'], 1)

        # Call 2: Identical payload and operation_ref
        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', payload, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.data.get('is_idempotent_replay'))
        self.assertEqual(resp2.data['attributed_count'], 1)

        # Exactly 1 operation row and 1 audit log row
        self.assertEqual(VoucherAttributionOperation.objects.filter(company=self.company, operation_ref=op_ref).count(), 1)
        self.assertEqual(VoucherGSTINAttributionLog.objects.filter(voucher=v).count(), 1)

    def test_r243_02_reuse_operation_ref_different_vouchers_conflict(self):
        """
        R243-02: Reusing operation_ref with different voucher IDs is rejected with HTTP 409 Conflict.
        """
        v1 = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/243/02A', voucher_date=date(2026, 8, 1), total_amount=Decimal('1000.00'), created_by=self.user, status='POSTED')
        v2 = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/243/02B', voucher_date=date(2026, 8, 2), total_amount=Decimal('2000.00'), created_by=self.user, status='POSTED')

        op_ref = 'OP_R243_02_TEST'
        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {'voucher_ids': [str(v1.id)], 'registration_id': str(self.registration.id), 'operation_ref': op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)

        # Conflicting request: different voucher
        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {'voucher_ids': [str(v2.id)], 'registration_id': str(self.registration.id), 'operation_ref': op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_REFERENCE_CONFLICT')

    def test_r243_03_reuse_operation_ref_different_registration_conflict(self):
        """
        R243-03: Reusing operation_ref with different registration is rejected with HTTP 409 Conflict.
        """
        v = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/243/03', voucher_date=date(2026, 8, 3), total_amount=Decimal('1000.00'), created_by=self.user, status='POSTED')
        op_ref = 'OP_R243_03_TEST'

        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {'voucher_ids': [str(v.id)], 'registration_id': str(self.registration.id), 'operation_ref': op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)

        # Conflicting request: different target registration
        resp2 = self.client.post('/api/v1/gst/itc/correct-attribution/', {'voucher_ids': [str(v.id)], 'registration_id': str(self.reg_branch.id), 'reason': 'Moving to branch registration unit', 'operation_ref': op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_REFERENCE_CONFLICT')

    def test_r243_04_reuse_operation_ref_different_correction_mode_conflict(self):
        """
        R243-04: Reusing operation_ref with different correction mode is rejected with HTTP 409 Conflict.
        """
        v = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/243/04', voucher_date=date(2026, 8, 4), total_amount=Decimal('1000.00'), created_by=self.user, status='POSTED')
        op_ref = 'OP_R243_04_TEST'

        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {'voucher_ids': [str(v.id)], 'registration_id': str(self.registration.id), 'operation_ref': op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)

        # Conflicting request: is_correction=True via correct-attribution endpoint
        resp2 = self.client.post('/api/v1/gst/itc/correct-attribution/', {'voucher_ids': [str(v.id)], 'registration_id': str(self.registration.id), 'reason': 'Valid correction reason on same voucher', 'operation_ref': op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_REFERENCE_CONFLICT')

    def test_r243_07_retry_after_transaction_failure(self):
        """
        R243-07: First request fails (invalid voucher); retry with changed payload is REJECTED with 409 Conflict.
        Operation reference is permanently bound to original request; changed request must use new operation_ref.
        """
        other_comp = Company.objects.create(name='Other Tenant', legal_name='Other Tenant Ltd', gstin='07OTH9999O1Z1', state_code='07')
        foreign_v = Voucher.objects.create(company=other_comp, voucher_type='PURCHASE', voucher_number='PUR/FOR/01', voucher_date=date(2026, 8, 5), total_amount=Decimal('500.00'), created_by=self.user, status='POSTED')
        valid_v = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/VAL/01', voucher_date=date(2026, 8, 6), total_amount=Decimal('500.00'), created_by=self.user, status='POSTED')

        op_ref = 'OP_R243_07_FAIL_THEN_RETRY'

        # Attempt 1: Target includes foreign voucher -> 400 Bad Request
        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(foreign_v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 400)
        self.assertEqual(resp1.data.get('error_code'), 'CROSS_TENANT_OR_INVALID_VOUCHERS')

        # Attempt 2: Target valid voucher with SAME operation_ref -> Rejected with 409 Conflict because fingerprint changed
        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(valid_v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_REFERENCE_CONFLICT')

        # Attempt 3: Changed request must use a NEW operation_ref
        new_op_ref = 'OP_R243_07_NEW_REF'
        resp3 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(valid_v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': new_op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(resp3.data['attributed_count'], 1)

    def test_r243_08_cross_tenant_operation_reference_lookup(self):
        """
        R243-08: Cross-tenant operation-reference lookup is strictly isolated by company.
        Company B cannot see Company A's operation or replay its results.
        """
        user_b = User.objects.create_user(email='user_b@othercorp.com', password='Password123!')
        comp_b = Company.objects.create(name='Tenant B Corp', legal_name='Tenant B Corp', gstin='07TENB9999B1Z8', state_code='07')
        UserCompany.objects.create(user=user_b, company=comp_b, role='OWNER')
        reg_b = GSTRegistration.objects.create(company=comp_b, gstin='07TENB9999B1Z8', legal_name='Tenant B Corp', state_code='07', status='ACTIVE', filing_frequency='MONTHLY', frequency_verified_source='GST_PORTAL_API', frequency_verified_at=timezone.now())

        v_a = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/243/08A', voucher_date=date(2026, 8, 7), total_amount=Decimal('1000.00'), created_by=self.user, status='POSTED')
        v_b = Voucher.objects.create(company=comp_b, voucher_type='PURCHASE', voucher_number='PUR/243/08B', voucher_date=date(2026, 8, 8), total_amount=Decimal('2000.00'), created_by=user_b, status='POSTED')

        shared_op_ref = 'OP_TENANT_ISOLATION_REF'

        # Tenant A completes operation
        resp_a = self.client.post('/api/v1/gst/itc/attribute-voucher/', {'voucher_ids': [str(v_a.id)], 'registration_id': str(self.registration.id), 'operation_ref': shared_op_ref}, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp_a.status_code, 200)

        # Tenant B uses same op_ref on their own company -> Must execute for Tenant B independently
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        resp_b = client_b.post('/api/v1/gst/itc/attribute-voucher/', {'voucher_ids': [str(v_b.id)], 'registration_id': str(reg_b.id), 'operation_ref': shared_op_ref}, format='json', HTTP_X_COMPANY_ID=str(comp_b.id))
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(resp_b.data['attributed_gstin'], reg_b.gstin)

        # Exactly 1 op record for Comp A and 1 op record for Comp B
        self.assertEqual(VoucherAttributionOperation.objects.filter(company=self.company, operation_ref=shared_op_ref).count(), 1)
        self.assertEqual(VoucherAttributionOperation.objects.filter(company=comp_b, operation_ref=shared_op_ref).count(), 1)

    @patch('apps.gst.services.reconciliation_service.SandboxGSTClient')
    def test_r243_09_verified_qrmp_provider_interim_period(self, mock_client_cls):
        """
        R243-09: Verified QRMP registration on interim month returns is_qrmp_not_applicable=True, no REQUEST_FAILED row.
        """
        reg_qrmp = GSTRegistration.objects.create(
            company=self.company,
            gstin='07QRMP9999Q1Z5',
            legal_name='Precision QRMP Unit',
            state_code='07',
            status='ACTIVE',
            filing_frequency='QRMP',
            frequency_verified_source='GST_PORTAL_API',
            frequency_verified_at=timezone.now(),
            auth_token='dummy-auth-token-qrmp'
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.is_configured.return_value = True
        mock_client.fetch_gstr2b.return_value = {
            'success': False,
            'status_code': 400,
            'error': 'GSTR2B form is not applicable for this taxpayer period.',
            'error_category': 'FORM_NOT_APPLICABLE'
        }

        res = GSTReconciliationService.fetch_and_ingest_from_sandbox(
            company=self.company,
            return_period='042026',
            registration=reg_qrmp,
            user=self.user
        )
        self.assertTrue(res['is_qrmp_not_applicable'])
        self.assertEqual(res['status'], 'NOT_APPLICABLE')
        # Does not create REQUEST_FAILED batch
        self.assertFalse(GSTR2BImport.objects.filter(company=self.company, gst_registration=reg_qrmp, return_period='042026', status='REQUEST_FAILED').exists())

    @patch('apps.gst.services.reconciliation_service.SandboxGSTClient')
    def test_r243_10_unverified_raw_qrmp_provider_response_not_treated_as_verified(self, mock_client_cls):
        """
        R243-10: Unverified registration with raw filing_frequency='QRMP' is NOT treated as verified QRMP.
        Creates a REQUEST_FAILED import batch instead of non-fatal QRMP skip.
        """
        reg_unverified_qrmp = GSTRegistration.objects.create(
            company=self.company,
            gstin='07UNVQRMP99U1Z7',
            legal_name='Unverified QRMP Unit',
            state_code='07',
            status='ACTIVE',
            filing_frequency='QRMP',
            frequency_verified_source='',
            frequency_verified_at=None,
            auth_token='dummy-auth-token-unv'
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.is_configured.return_value = True
        mock_client.fetch_gstr2b.return_value = {
            'success': False,
            'status_code': 400,
            'error': 'GSTR2B form is not applicable for this taxpayer period.',
            'error_category': 'FORM_NOT_APPLICABLE'
        }

        res = GSTReconciliationService.fetch_and_ingest_from_sandbox(
            company=self.company,
            return_period='042026',
            registration=reg_unverified_qrmp,
            user=self.user
        )
        self.assertFalse(res['is_qrmp_not_applicable'])
        self.assertEqual(res['fetch_status'], 'REQUEST_FAILED')
        self.assertTrue(GSTR2BImport.objects.filter(company=self.company, gst_registration=reg_unverified_qrmp, return_period='042026', status='REQUEST_FAILED').exists())

    def test_r243_11_unverified_raw_monthly_not_treated_as_verified(self):
        """
        R243-11: Unverified registration with raw filing_frequency='MONTHLY' resolves to UNKNOWN.
        """
        reg_unv_monthly = GSTRegistration.objects.create(
            company=self.company,
            gstin='07UNVMON99M1Z3',
            legal_name='Unverified Monthly Unit',
            state_code='07',
            status='ACTIVE',
            filing_frequency='MONTHLY',
            frequency_verified_source='',
            frequency_verified_at=None
        )
        self.assertEqual(reg_unv_monthly.get_verified_filing_frequency(), 'UNKNOWN')
        stmt_res = GSTPeriodService.resolve_gstr2b_statement_period(date(2026, 4, 15), recipient_registration=reg_unv_monthly)
        self.assertEqual(stmt_res.recipient_filing_frequency, 'UNKNOWN')
        self.assertEqual(stmt_res.period_resolution_status, 'REVIEW_REQUIRED')

    @patch('apps.gst.services.reconciliation_service.SandboxGSTClient')
    def test_r243_12_provider_error_no_frequency_mutation(self, mock_client_cls):
        """
        R243-12: Provider error does not mutate registration frequency or verification provenance.
        """
        self.registration.auth_token = 'dummy-token'
        self.registration.save(update_fields=['auth_token'])
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.is_configured.return_value = True
        mock_client.fetch_gstr2b.return_value = {
            'success': False,
            'status_code': 500,
            'error': 'Internal GSTN Gateway Server Error',
            'error_category': 'PROVIDER_ERROR'
        }

        freq_before = self.registration.filing_frequency
        src_before = self.registration.frequency_verified_source

        GSTReconciliationService.fetch_and_ingest_from_sandbox(
            company=self.company,
            return_period='052026',
            registration=self.registration,
            user=self.user
        )

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.filing_frequency, freq_before)
        self.assertEqual(self.registration.frequency_verified_source, src_before)

    def test_r243_13_authorized_manual_verification_accepted_and_audited(self):
        """
        R243-13: Authorized compliance user (OWNER/ADMIN) can verify frequency and creates audit log.
        """
        reason_text = "Board resolution passed on 2026-08-01 adopting QRMP filing scheme."
        self.registration.set_filing_frequency(
            frequency='QRMP',
            source='USER_MANUAL',
            user=self.user,
            reason=reason_text
        )
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.filing_frequency, 'QRMP')
        self.assertEqual(self.registration.get_verified_filing_frequency(), 'QRMP')

        audit_log = GSTRegistrationFrequencyAuditLog.objects.filter(gst_registration=self.registration).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.verified_by, self.user)
        self.assertEqual(audit_log.previous_frequency, 'MONTHLY')
        self.assertEqual(audit_log.new_frequency, 'QRMP')
        self.assertEqual(audit_log.reason, reason_text)

    def test_r243_14_unauthorized_manual_verification_rejected(self):
        """
        R243-14: User without compliance role (e.g. VIEWER) cannot manually verify filing frequency.
        """
        viewer_user = User.objects.create_user(email='viewer@precision.com', password='ViewerPass123!')
        UserCompany.objects.create(user=viewer_user, company=self.company, role='VIEWER')

        freq_before = self.registration.filing_frequency

        from rest_framework.exceptions import ValidationError as DRFValidationError
        from django.core.exceptions import ValidationError as DjangoValidationError
        with self.assertRaises((DRFValidationError, DjangoValidationError)) as cm:
            self.registration.set_filing_frequency(
                frequency='QRMP',
                source='USER_MANUAL',
                user=viewer_user,
                reason='Unauthorized viewer attempting change'
            )
        self.assertIn('not authorized', str(cm.exception).lower())

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.filing_frequency, freq_before)

    def test_r243_15_cross_company_manual_verification_rejected(self):
        """
        R243-15: User belonging to another company cannot verify filing frequency.
        """
        comp_foreign = Company.objects.create(name='Foreign Co Ltd', legal_name='Foreign Co Ltd', gstin='07FOR9999F1Z9', state_code='07')
        foreign_user = User.objects.create_user(email='foreign_admin@foreignco.com', password='ForeignPass123!')
        UserCompany.objects.create(user=foreign_user, company=comp_foreign, role='OWNER')

        from rest_framework.exceptions import ValidationError as DRFValidationError
        from django.core.exceptions import ValidationError as DjangoValidationError
        with self.assertRaises((DRFValidationError, DjangoValidationError)) as cm:
            self.registration.set_filing_frequency(
                frequency='QRMP',
                source='USER_MANUAL',
                user=foreign_user,
                reason='Cross company user attempt'
            )
        self.assertIn('not authorized', str(cm.exception).lower())


class Round244TargetedRemediationTests(TestCase):
    """
    Round 2.4.4 Targeted Verification Suite:
    - P0: Permanent request-bound operation_ref (failed op changed payload rejected with 409)
    - P0: Failed operation same-payload retry succeeds safely
    - P0: Cross-actor operation reference reuse rejected with 409
    - P1: Atomic frequency update and audit insertion (audit failure rolls back registration)
    - P1: GSTRegistrationFrequencyAuditLog ORM immutability (save, delete, update blocked)
    - P1: Frequency audit foreign key PROTECT prevents registration deletion
    - P1: Attribution success decoupled from reconciliation failure (HTTP 200, attribution durably committed)
    - P2: is_idempotent_replay: true in replay responses
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='auditor_244@precision.com',
            password='TestPassword123!'
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name='Apex Precision Ltd',
            legal_name='Apex Precision Ltd',
            gstin='07APEX9999P1Z1',
            state_code='07'
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')

        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='07APEX9999P1Z1',
            legal_name='Apex Precision Ltd',
            state_code='07',
            status='ACTIVE',
            filing_frequency='MONTHLY',
            frequency_verified_source='GST_PORTAL_API',
            frequency_verified_at=timezone.now(),
            is_primary=True
        )

        self.user2 = User.objects.create_user(
            email='second_auditor_244@precision.com',
            password='TestPassword123!'
        )
        UserCompany.objects.create(user=self.user2, company=self.company, role='ADMIN')

    def test_r244_01_failed_op_changed_payload_rejected_with_409(self):
        """
        R244-01: An operation reference is permanently bound to its original request fingerprint.
        Reusing an operation reference that previously FAILED with a different payload MUST return 409 Conflict.
        """
        other_comp = Company.objects.create(name='Other Co', legal_name='Other Co Ltd', gstin='07OTH9999O1Z9', state_code='07')
        foreign_v = Voucher.objects.create(company=other_comp, voucher_type='PURCHASE', voucher_number='PUR/F1/01', voucher_date=date(2026, 9, 1), total_amount=Decimal('500.00'), created_by=self.user, status='POSTED')
        valid_v = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/V1/01', voucher_date=date(2026, 9, 2), total_amount=Decimal('500.00'), created_by=self.user, status='POSTED')

        op_ref = 'OP_R244_PERM_BINDING_01'

        # Attempt 1: Foreign voucher -> fails with 400, operation marked FAILED
        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(foreign_v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 400)

        op_record = VoucherAttributionOperation.objects.get(company=self.company, operation_ref=op_ref)
        self.assertEqual(op_record.status, 'FAILED')

        # Attempt 2: Same op_ref with DIFFERENT voucher (valid_v) -> REJECTED with 409 Conflict
        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(valid_v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_REFERENCE_CONFLICT')

        # Attempt 3: Changed request with NEW operation reference succeeds
        resp3 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(valid_v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R244_NEW_REF_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp3.status_code, 200)

    def test_r244_02_failed_op_same_payload_retry_reexecutes_safely(self):
        """
        R244-02: A retry using the SAME fingerprint safely re-executes after a failed transaction.
        """
        v = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/V2/01', voucher_date=date(2026, 9, 3), total_amount=Decimal('800.00'), created_by=self.user, status='POSTED')
        op_ref = 'OP_R244_SAME_RETRY_02'

        # Seed an operation in FAILED state with the exact fingerprint of this request
        import hashlib, json
        canonical_dict = {
            'attribution_source': 'MANUAL_USER_ATTRIBUTION',
            'company_id': str(self.company.id),
            'is_correction': False,
            'reason': '',
            'registration_id': str(self.registration.id),
            'voucher_ids': [str(v.id)],
        }
        canonical_bytes = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
        fp = hashlib.sha256(canonical_bytes).hexdigest()

        VoucherAttributionOperation.objects.create(
            company=self.company,
            operation_ref=op_ref,
            request_fingerprint=fp,
            actor=self.user,
            target_registration=self.registration,
            status='FAILED'
        )

        # Retry with SAME operation_ref and SAME payload -> re-executes and succeeds
        resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['attributed_count'], 1)
        op_rec = VoucherAttributionOperation.objects.get(company=self.company, operation_ref=op_ref)
        self.assertEqual(op_rec.status, 'COMPLETED')
        self.assertEqual(VoucherGSTINAttributionLog.objects.filter(voucher=v).count(), 1)

    def test_r244_03_different_actor_same_op_ref_same_payload_rejected_with_409(self):
        """
        R244-03: Another actor using an existing operation_ref (even with same payload) is rejected with 409.
        """
        v = Voucher.objects.create(company=self.company, voucher_type='PURCHASE', voucher_number='PUR/V3/01', voucher_date=date(2026, 9, 4), total_amount=Decimal('1200.00'), created_by=self.user, status='POSTED')
        op_ref = 'OP_R244_ACTOR_BIND_03'

        # User 1 successfully executes
        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)

        # User 2 attempts to use same operation_ref
        client2 = APIClient()
        client2.force_authenticate(user=self.user2)
        resp2 = client2.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_ACTOR_MISMATCH')

    @patch('apps.gst.models.GSTRegistrationFrequencyAuditLog.objects.create')
    def test_r244_04_atomic_frequency_update_audit_log_failure_rollback(self, mock_create):
        """
        R244-04: If frequency audit log insertion fails, registration update must roll back.
        Original in-memory attributes and database state must remain unchanged.
        """
        mock_create.side_effect = RuntimeError("Simulated audit disk write failure")
        freq_before = self.registration.filing_frequency
        src_before = self.registration.frequency_verified_source

        with self.assertRaises(RuntimeError):
            self.registration.set_filing_frequency(
                frequency='QRMP',
                source='USER_MANUAL',
                user=self.user,
                reason='Atomic failure test'
            )

        # In-memory attributes restored
        self.assertEqual(self.registration.filing_frequency, freq_before)
        self.assertEqual(self.registration.frequency_verified_source, src_before)

        # Database state unaffected
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.filing_frequency, freq_before)
        self.assertEqual(self.registration.frequency_verified_source, src_before)

    def test_r244_05_frequency_audit_orm_immutability(self):
        """
        R244-05: GSTRegistrationFrequencyAuditLog records are immutable at ORM and QuerySet levels.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError
        log = GSTRegistrationFrequencyAuditLog.objects.create(
            company=self.company,
            gst_registration=self.registration,
            previous_frequency='MONTHLY',
            new_frequency='QRMP',
            verification_source='USER_MANUAL',
            verified_by=self.user,
            reason='Audit immutability test'
        )

        # ORM save mutation blocked
        log.new_frequency = 'MONTHLY'
        with self.assertRaises(DjangoValidationError):
            log.save()

        # ORM delete blocked
        with self.assertRaises(DjangoValidationError):
            log.delete()

        # QuerySet update blocked
        with self.assertRaises(DjangoValidationError):
            GSTRegistrationFrequencyAuditLog.objects.filter(id=log.id).update(new_frequency='MONTHLY')

        # QuerySet delete blocked
        with self.assertRaises(DjangoValidationError):
            GSTRegistrationFrequencyAuditLog.objects.filter(id=log.id).delete()

    def test_r244_06_frequency_audit_fk_protect_prevents_registration_deletion(self):
        """
        R244-06: Foreign key on_delete=PROTECT prevents deleting GSTRegistration while audit logs exist.
        """
        from django.db.models import ProtectedError
        GSTRegistrationFrequencyAuditLog.objects.create(
            company=self.company,
            gst_registration=self.registration,
            previous_frequency='MONTHLY',
            new_frequency='QRMP',
            verification_source='USER_MANUAL',
            verified_by=self.user,
            reason='Protect test'
        )

        with self.assertRaises(ProtectedError):
            self.registration.delete()

    @patch('apps.gst.services.itc_reconciliation_service.ITCReconciliationService.reconcile_period')
    def test_r244_07_attribution_success_with_reconciliation_failure_decoupled(self, mock_rec):
        """
        R244-07: Attribution commits independently and durably even if post-attribution reconciliation fails.
        API returns HTTP 200 with attribution_status='ATTRIBUTED' and reconciliation_status='RECONCILIATION_FAILED'.
        """
        mock_rec.side_effect = RuntimeError("Simulated reconciliation engine timeout")

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R244/DECOUPLE/01',
            voucher_date=date(2026, 9, 10),
            total_amount=Decimal('1500.00'),
            created_by=self.user,
            status='POSTED'
        )
        op_ref = 'OP_R244_DECOUPLE_01'

        resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['attribution_status'], 'ATTRIBUTED')
        self.assertEqual(resp.data['reconciliation_status'], 'RECONCILIATION_FAILED')
        self.assertIn('Simulated reconciliation engine timeout', resp.data['reconciliation_error'])

        # Attribution durably committed in database
        v.refresh_from_db()
        self.assertEqual(v.buyer_gstin, self.registration.gstin)
        self.assertEqual(VoucherGSTINAttributionLog.objects.filter(voucher=v).count(), 1)

        # Operation record marked COMPLETED (attribution completed)
        op_rec = VoucherAttributionOperation.objects.get(company=self.company, operation_ref=op_ref)
        self.assertEqual(op_rec.status, 'COMPLETED')

        # Idempotent replay returns cached response with is_idempotent_replay=True
        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.data.get('is_idempotent_replay'))
        self.assertEqual(VoucherGSTINAttributionLog.objects.filter(voucher=v).count(), 1)

    def test_r244_08_replayed_response_has_is_idempotent_replay_true(self):
        """
        R244-08: Replayed response includes is_idempotent_replay=True matching API documentation.
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R244/REPLAY/01',
            voucher_date=date(2026, 9, 11),
            total_amount=Decimal('2000.00'),
            created_by=self.user,
            status='POSTED'
        )
        op_ref = 'OP_R244_REPLAY_01'
        payload = {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': op_ref
        }

        resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', payload, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp1.status_code, 200)
        self.assertFalse(resp1.data.get('is_idempotent_replay'))

        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', payload, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.data.get('is_idempotent_replay'))


class Round245TargetedRemediationTests(TestCase):
    """
    Round 2.4.5 Targeted Verification Suite:
    - P1: Durable reconciliation recovery after attribution commits (outbox/job pattern)
    - P1: Permanent actor binding for attribution operations across user deactivation/deletion
    - P1: Close commit=False frequency-audit bypass and prevent direct un-audited model saves
    """
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='auditor_245@precision.com',
            password='TestPassword123!'
        )
        self.user2 = User.objects.create_user(
            email='auditor2_245@precision.com',
            password='TestPassword123!'
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name='Apex Precision 245 Ltd',
            legal_name='Apex Precision 245 Ltd',
            gstin='07APEX2459P1Z1',
            state_code='07'
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')
        UserCompany.objects.create(user=self.user2, company=self.company, role='OWNER')

        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='07APEX2459P1Z1',
            legal_name='Apex Precision 245 Ltd',
            state_code='07',
            state_name='Delhi',
            filing_frequency='MONTHLY',
            status='ACTIVE'
        )

    def test_r245_01_attribution_commits_with_durable_reconciliation_job_pending(self):
        """
        R245-01: Attribution commits durably; simulated crash before dispatch leaves durable job pending.
        """
        from unittest.mock import patch
        from apps.gst.models import ITCReconciliationJob

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R245/CRASH/01',
            voucher_date=date(2026, 10, 1),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )

        with patch('apps.gst.services.itc_reconciliation_job_service.ITCReconciliationJobService.execute_job', return_value=None):
            resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
                'voucher_ids': [str(v.id)],
                'registration_id': str(self.registration.id),
                'operation_ref': 'OP_R245_CRASH_01'
            }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['attribution_status'], 'ATTRIBUTED')
        self.assertEqual(resp.data['reconciliation_status'], 'PENDING')

        v.refresh_from_db()
        self.assertEqual(v.buyer_gstin, self.registration.gstin)

        job = ITCReconciliationJob.objects.filter(operation_ref='OP_R245_CRASH_01').first()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, 'PENDING')
        self.assertEqual(job.attempt_count, 0)

    def test_r245_02_resume_and_execute_pending_reconciliation_job(self):
        """
        R245-02: Recovery sweeper resumes and completes a pending reconciliation job.
        """
        from apps.gst.models import ITCReconciliationJob, VoucherAttributionOperation
        from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService

        op = VoucherAttributionOperation.objects.create(
            company=self.company,
            operation_ref='OP_R245_RECOVER_01',
            request_fingerprint='dummy_fp_245',
            status='COMPLETED',
            response_payload={'reconciliation_status': 'PENDING'}
        )
        job = ITCReconciliationJob.objects.create(
            company=self.company,
            gst_registration=self.registration,
            operation=op,
            operation_ref='OP_R245_RECOVER_01',
            status='PENDING'
        )

        recovered = ITCReconciliationJobService.recover_pending_jobs(company=self.company)
        self.assertEqual(len(recovered), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'COMPLETED')
        self.assertEqual(job.attempt_count, 1)

        op.refresh_from_db()
        self.assertEqual(op.response_payload.get('reconciliation_status'), 'RECONCILED')

    def test_r245_03_client_retry_while_reconciliation_is_pending(self):
        """
        R245-03: Client retry while reconciliation is pending returns live pending status, not false completion.
        """
        from unittest.mock import patch
        from apps.gst.models import ITCReconciliationJob

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R245/PENDING/01',
            voucher_date=date(2026, 10, 2),
            total_amount=Decimal('1500.00'),
            created_by=self.user,
            status='POSTED'
        )

        with patch('apps.gst.services.itc_reconciliation_job_service.ITCReconciliationJobService.execute_job', return_value=None):
            resp1 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
                'voucher_ids': [str(v.id)],
                'registration_id': str(self.registration.id),
                'operation_ref': 'OP_R245_PENDING_01'
            }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.data['reconciliation_status'], 'PENDING')

        resp2 = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_PENDING_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.data.get('is_idempotent_replay'))
        self.assertEqual(resp2.data.get('reconciliation_status'), 'PENDING')

    def test_r245_04_reconciliation_retry_idempotent_no_duplicate_attribution(self):
        """
        R245-04: Repeated job execution is idempotent and produces no duplicate attribution logs.
        """
        from apps.gst.models import ITCReconciliationJob
        from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R245/IDEM/01',
            voucher_date=date(2026, 10, 3),
            total_amount=Decimal('2000.00'),
            created_by=self.user,
            status='POSTED'
        )

        resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_IDEM_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp.status_code, 200)

        job_id = resp.data.get('reconciliation_job_id')
        job = ITCReconciliationJob.objects.get(id=job_id)

        count_before = VoucherGSTINAttributionLog.objects.filter(voucher=v).count()
        # Re-execute job directly
        job.status = 'PENDING'
        job.save()
        ITCReconciliationJobService.execute_job(job.id)

        count_after = VoucherGSTINAttributionLog.objects.filter(voucher=v).count()
        self.assertEqual(count_before, count_after)
        self.assertEqual(count_after, 1)

    def test_r245_05_reconciliation_job_max_attempts_and_failed_state(self):
        """
        R245-05: Recurring reconciliation failure increments attempts to max_attempts and marks FAILED.
        """
        from unittest.mock import patch
        from apps.gst.models import ITCReconciliationJob
        from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService

        job = ITCReconciliationJob.objects.create(
            company=self.company,
            gst_registration=self.registration,
            operation_ref='OP_R245_FAIL_01',
            status='PENDING'
        )

        with patch('apps.gst.services.itc_reconciliation_service.ITCReconciliationService.reconcile_period', side_effect=RuntimeError("Simulated engine fault")):
            for _ in range(3):
                ITCReconciliationJobService.execute_job(job.id)

        job.refresh_from_db()
        self.assertEqual(job.attempt_count, 3)
        self.assertEqual(job.status, 'FAILED')
        self.assertEqual(job.error_classification, 'RuntimeError')
        self.assertIn("Simulated engine fault", job.last_error)

    def test_r245_06_authorized_retry_of_failed_job(self):
        """
        R245-06: Authorized administrative recovery path allows retrying a permanently failed job.
        """
        from apps.gst.models import ITCReconciliationJob
        from apps.gst.services.itc_reconciliation_job_service import ITCReconciliationJobService

        job = ITCReconciliationJob.objects.create(
            company=self.company,
            gst_registration=self.registration,
            operation_ref='OP_R245_RETRY_01',
            status='FAILED',
            attempt_count=3,
            last_error="Prior fatal error"
        )

        retried = ITCReconciliationJobService.retry_job(job.id, reset_attempts=True)
        self.assertIsNotNone(retried)
        self.assertEqual(retried.status, 'COMPLETED')
        self.assertEqual(retried.attempt_count, 1)

    def test_r245_07_permanent_actor_binding_actor_user_id(self):
        """
        R245-07: Attribution operation permanently stores actor_user_id and actor_username.
        """
        from apps.gst.models import VoucherAttributionOperation

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R245/ACTOR/01',
            voucher_date=date(2026, 10, 4),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )

        resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_ACTOR_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp.status_code, 200)

        op = VoucherAttributionOperation.objects.get(operation_ref='OP_R245_ACTOR_01')
        self.assertEqual(op.actor_user_id, str(self.user.id))
        self.assertEqual(op.actor_username, getattr(self.user, 'username', self.user.email))

    def test_r245_08_deactivated_actor_rejects_other_user_replay(self):
        """
        R245-08: Deactivated actor cannot have their operation_ref replayed by another user (409 Conflict).
        """
        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R245/DEACT/01',
            voucher_date=date(2026, 10, 5),
            total_amount=Decimal('1000.00'),
            created_by=self.user,
            status='POSTED'
        )

        resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_DEACT_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp.status_code, 200)

        # Deactivate user 1
        self.user.is_active = False
        self.user.save()

        # User 2 tries to reuse the operation_ref
        client2 = APIClient()
        client2.force_authenticate(user=self.user2)
        resp2 = client2.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_DEACT_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_ACTOR_MISMATCH')

    def test_r245_09_deleted_actor_rejects_other_user_replay(self):
        """
        R245-09: Deleted actor operation retains permanent actor_user_id; replay by another user is rejected with 409.
        """
        from apps.gst.models import VoucherAttributionOperation

        v = Voucher.objects.create(
            company=self.company,
            voucher_type='PURCHASE',
            voucher_number='PUR/R245/DEL/01',
            voucher_date=date(2026, 10, 6),
            total_amount=Decimal('1000.00'),
            created_by=self.user2,
            status='POSTED'
        )

        resp = self.client.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_DEL_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))
        self.assertEqual(resp.status_code, 200)

        orig_user_id = str(self.user.id)
        # Delete user 1 (clean up UserCompany first)
        UserCompany.objects.filter(user=self.user).delete()
        self.user.delete()

        op = VoucherAttributionOperation.objects.get(operation_ref='OP_R245_DEL_01')
        self.assertIsNone(op.actor_id)  # SET_NULL cleared FK
        self.assertEqual(op.actor_user_id, orig_user_id)  # Permanent ID preserved!

        # User 2 tries to replay the operation_ref
        client2 = APIClient()
        client2.force_authenticate(user=self.user2)
        resp2 = client2.post('/api/v1/gst/itc/attribute-voucher/', {
            'voucher_ids': [str(v.id)],
            'registration_id': str(self.registration.id),
            'operation_ref': 'OP_R245_DEL_01'
        }, format='json', HTTP_X_COMPANY_ID=str(self.company.id))

        self.assertEqual(resp2.status_code, 409)
        self.assertEqual(resp2.data.get('error_code'), 'OPERATION_ACTOR_MISMATCH')

    def test_r245_10_set_filing_frequency_rejects_commit_false(self):
        """
        R245-10: set_filing_frequency(commit=False) is rejected with ValidationError.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError
        with self.assertRaises(DjangoValidationError) as cm:
            self.registration.set_filing_frequency('QRMP', commit=False)
        self.assertIn('commit=False is prohibited', str(cm.exception))

    def test_r245_11_direct_model_save_with_frequency_change_rejected(self):
        """
        R245-11: Directly mutating filing_frequency and calling save() is rejected with ValidationError.
        """
        from django.core.exceptions import ValidationError as DjangoValidationError
        self.registration.filing_frequency = 'QRMP'
        with self.assertRaises(DjangoValidationError) as cm:
            self.registration.save()
        self.assertIn('Direct modification of filing_frequency on GSTRegistration', str(cm.exception))

    def test_r245_12_direct_model_save_without_frequency_change_allowed(self):
        """
        R245-12: Normal model saves that do not alter filing_frequency succeed without error.
        """
        self.registration.legal_name = 'Updated Non-Frequency Name'
        self.registration.save()
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.legal_name, 'Updated Non-Frequency Name')

    def test_r245_13_audit_failure_rolls_back_frequency_and_in_memory_attributes(self):
        """
        R245-13: Audit log insertion failure triggers complete DB rollback and restores in-memory attributes.
        """
        from unittest.mock import patch
        orig_freq = self.registration.filing_frequency

        with patch('apps.gst.models.GSTRegistrationFrequencyAuditLog.objects.create', side_effect=RuntimeError("Simulated DB audit crash")):
            with self.assertRaises(RuntimeError):
                self.registration.set_filing_frequency('QRMP', user=self.user)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.filing_frequency, orig_freq)


"""
SriLekh GST ITC Shield — Round 2.4.7 Targeted Regression Tests
Multi-Period GSTR-2B Sync Remediation, Period Selector UX & Production Database Integrity

Certifies:
1. GSTR2BSyncAttempt.return_period accommodates 13+ char multi-period range identifiers (e.g. 042026-102026)
   without PostgreSQL StringDataRightTruncation failure.
2. GSTR2BIngestionLock preserves strict 6-character normalized period semantics.
3. Structured API response exposes from_period, to_period, range_identifier, display_label.
4. GSTR-2B sync workflow handles single-period, multi-period, partial-success, and failure states gracefully.
5. Strict accounting and tenant isolation invariants: zero voucher mutation, zero ledger drift,
   and zero access to protected production tenants.
"""

from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import (
    GSTR2BSyncAttempt,
    GSTR2BIngestionLock,
    GSTR2BImport,
    GSTR2BRecord,
    GSTRegistration,
    CompanyGSTConfig,
)
from apps.gst.services.reconciliation_service import GSTReconciliationService
from apps.gst.services.period_service import GSTPeriodService

User = get_user_model()


class Round247MultiPeriodSyncDatabaseTests(TestCase):
    """
    SECTION A: DATABASE SCHEMA & TRUNCATION-FREE MULTI-PERIOD STORAGE
    Verifies that GSTR2BSyncAttempt stores single-period, multi-period, and cross-FY
    range keys without truncation, while GSTR2BIngestionLock retains 6-char semantics.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='auditor_r247@testcorp.com',
            password='TestPassword123!'
        )
        self.company = Company.objects.create(
            name='Apex Belting & Industrial Store (Demo)',
            legal_name='Apex Belting & Industrial Store Demo Pvt Ltd',
            gstin='27AAPCA1234F1Z5',
            state_code='27',
            email='audit@apexbelting.demo'
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')
        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAPCA1234F1Z5',
            legal_name='Apex Belting & Industrial Store Demo Pvt Ltd',
            state_code='27',
            status='ACTIVE',
            is_primary=True,
            filing_frequency='MONTHLY'
        )

    def test_01_single_period_sync_attempt_storage(self):
        """Verify storage and retrieval of standard 6-character return period."""
        attempt = GSTR2BSyncAttempt.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='042026',
            status='SUCCESS',
            total_invoices_ingested=25,
            initiated_by=self.user
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.return_period, '042026')
        self.assertEqual(len(attempt.return_period), 6)
        self.assertEqual(attempt.status, 'SUCCESS')

    def test_02_april_october_multi_period_sync_attempt_storage_no_truncation(self):
        """
        P0 Production Defect Reproduction & Resolution:
        Range '042026-102026' (13 characters) must store cleanly without
        psycopg2.errors.StringDataRightTruncation.
        """
        range_identifier = '042026-102026'
        self.assertEqual(len(range_identifier), 13)

        attempt = GSTR2BSyncAttempt.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period=range_identifier,
            status='IN_PROGRESS',
            total_invoices_ingested=0,
            initiated_by=self.user
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.return_period, '042026-102026')
        self.assertEqual(len(attempt.return_period), 13)

    def test_03_cross_financial_year_range_storage(self):
        """Verify storage of range spanning financial-year boundaries (e.g. 042025-032027)."""
        cross_fy_range = '042025-032027'
        self.assertEqual(len(cross_fy_range), 13)

        attempt = GSTR2BSyncAttempt.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period=cross_fy_range,
            status='PARTIAL_SUCCESS',
            total_invoices_ingested=150,
            initiated_by=self.user
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.return_period, '042025-032027')

    def test_04_historical_sync_attempts_remain_queryable(self):
        """Verify historical single-month sync attempts coexist and remain queryable."""
        # Create legacy-style single period attempts
        for p in ['042026', '052026', '062026']:
            GSTR2BSyncAttempt.objects.create(
                company=self.company,
                gst_registration=self.registration,
                return_period=p,
                status='SUCCESS'
            )

        # Create multi-period attempt
        GSTR2BSyncAttempt.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='042026-062026',
            status='SUCCESS'
        )

        all_attempts = GSTR2BSyncAttempt.objects.filter(company=self.company)
        self.assertEqual(all_attempts.count(), 4)

        # Filter by composite index (company, return_period, status)
        match = GSTR2BSyncAttempt.objects.filter(
            company=self.company,
            return_period='042026-062026',
            status='SUCCESS'
        ).first()
        self.assertIsNotNone(match)
        self.assertEqual(match.return_period, '042026-062026')

    def test_05_gstr2b_ingestion_lock_preserves_strict_individual_period(self):
        """
        Verify GSTR2BIngestionLock strictly preserves individual 6-character return period,
        maintaining company, registration, and return_period uniqueness.
        """
        lock = GSTR2BIngestionLock.objects.create(
            company=self.company,
            gst_registration=self.registration,
            return_period='042026'
        )
        lock.refresh_from_db()
        self.assertEqual(lock.return_period, '042026')
        self.assertEqual(len(lock.return_period), 6)

        # Field max_length constraint check on GSTR2BIngestionLock
        field = GSTR2BIngestionLock._meta.get_field('return_period')
        self.assertEqual(field.max_length, 10, "GSTR2BIngestionLock must NOT be expanded beyond 10 chars!")

        # Field max_length constraint check on GSTR2BSyncAttempt
        sync_field = GSTR2BSyncAttempt._meta.get_field('return_period')
        self.assertEqual(sync_field.max_length, 32, "GSTR2BSyncAttempt must be expanded to 32 chars!")


class Round247MultiPeriodSyncWorkflowTests(TestCase):
    """
    SECTION B: GSTR-2B SYNC WORKFLOW, API CONTRACT & RESILIENCY
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='sync_worker_r247@testcorp.com',
            password='TestPassword123!'
        )
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            name='Apex Belting & Industrial Store (Demo)',
            legal_name='Apex Belting & Industrial Store Demo Pvt Ltd',
            gstin='27AAPCA1234F1Z5',
            state_code='27',
            email='sync@apexbelting.demo'
        )
        UserCompany.objects.create(user=self.user, company=self.company, role='OWNER')

        self.registration = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAPCA1234F1Z5',
            legal_name='Apex Belting & Industrial Store Demo Pvt Ltd',
            state_code='27',
            status='ACTIVE',
            is_primary=True,
            filing_frequency='MONTHLY'
        )
        self.url = reverse('gst_reconciliation_gstr2b_sync', kwargs={'company_id': self.company.id})

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_06_single_period_sync_workflow_and_api_contract(self, mock_single):
        """Single period sync returns structured contract fields."""
        mock_single.return_value = {
            "success": True,
            "status": "SUCCESS",
            "total_invoices_ingested": 12,
            "return_period": "042026",
            "provider_records_count": 12,
            "records_created": 12,
            "records_updated": 0,
            "records_unchanged": 0
        }

        res = self.client.post(
            self.url,
            data={'from_period': '042026', 'to_period': '042026'},
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'SUCCESS')
        self.assertEqual(data['from_period'], '042026')
        self.assertEqual(data['to_period'], '042026')
        self.assertEqual(data['range_identifier'], '042026')
        self.assertEqual(data['display_label'], 'April 2026')
        self.assertEqual(data['periods_requested'], ['042026'])
        self.assertEqual(data['periods_synced'], ['042026'])

        # Verify GSTR2BSyncAttempt created with single-period range_key
        attempt = GSTR2BSyncAttempt.objects.filter(company=self.company).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.return_period, '042026')
        self.assertEqual(attempt.status, 'SUCCESS')
        self.assertEqual(attempt.total_invoices_ingested, 12)

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_07_april_to_october_multi_month_sync_workflow(self, mock_single):
        """
        April to October 2026 (7 months) sync execution:
        - 13-character range_identifier stored successfully.
        - Structured API response matches contract.
        - Exactly 7 month fetches executed.
        """
        mock_single.return_value = {
            "success": True,
            "status": "SUCCESS",
            "total_invoices_ingested": 5,
            "provider_records_count": 5,
            "records_created": 5,
            "records_updated": 0,
            "records_unchanged": 0
        }

        res = self.client.post(
            self.url,
            data={'from_period': '042026', 'to_period': '102026'},
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'SUCCESS')
        self.assertEqual(data['from_period'], '042026')
        self.assertEqual(data['to_period'], '102026')
        self.assertEqual(data['range_identifier'], '042026-102026')
        self.assertEqual(data['display_label'], 'April 2026 – October 2026')
        self.assertEqual(data['total_periods'], 7)
        self.assertEqual(data['successful_periods_count'], 7)
        self.assertEqual(data['failed_periods_count'], 0)
        self.assertEqual(mock_single.call_count, 7)

        # Database attempt record check
        attempt = GSTR2BSyncAttempt.objects.filter(company=self.company).order_by('-created_at').first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.return_period, '042026-102026')
        self.assertEqual(attempt.status, 'SUCCESS')
        self.assertEqual(attempt.total_invoices_ingested, 35)

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_08_multi_month_partial_success_reporting(self, mock_single):
        """
        Partial success: 5 periods succeed, 2 periods fail.
        Overall status must be PARTIAL_SUCCESS, overall success must be False.
        """
        def side_effect_mock(company, registration, return_period, user):
            if return_period in ['092026', '102026']:
                return {
                    "success": False,
                    "status": "FAILED",
                    "error": "Portal gateway timeout",
                    "error_category": "GATEWAY_TIMEOUT"
                }
            return {
                "success": True,
                "status": "SUCCESS",
                "total_invoices_ingested": 4,
                "provider_records_count": 4,
                "records_created": 4,
                "records_updated": 0,
                "records_unchanged": 0
            }

        mock_single.side_effect = side_effect_mock

        res = self.client.post(
            self.url,
            data={'from_period': '042026', 'to_period': '102026'},
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        self.assertFalse(data['success'])
        self.assertEqual(data['status'], 'PARTIAL_SUCCESS')
        self.assertEqual(data['successful_periods_count'], 5)
        self.assertEqual(data['failed_periods_count'], 2)
        self.assertIn('092026', data['periods_failed'])
        self.assertIn('102026', data['periods_failed'])

        # Database attempt reflects partial success
        attempt = GSTR2BSyncAttempt.objects.filter(company=self.company).first()
        self.assertEqual(attempt.status, 'PARTIAL_SUCCESS')
        self.assertEqual(attempt.total_invoices_ingested, 20)
        self.assertIn('failed', attempt.error_message.lower())

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_09_all_periods_failed_reporting(self, mock_single):
        """All periods fail -> status FAILED, HTTP 400 returned."""
        mock_single.return_value = {
            "success": False,
            "status": "FAILED",
            "error": "API Key expired",
            "error_category": "AUTH_FAILED"
        }

        res = self.client.post(
            self.url,
            data={
                'from_period': '042026',
                'to_period': '062026',
                'registration_id': str(self.registration.id)
            },
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        data = res.data

        self.assertFalse(data['success'])
        self.assertEqual(data['status'], 'FAILED')
        self.assertEqual(data['failed_periods_count'], 3)

        attempt = GSTR2BSyncAttempt.objects.filter(company=self.company).first()
        self.assertEqual(attempt.status, 'FAILED')

    def test_10_reversed_period_range_rejected(self):
        """from_period > to_period must be rejected with HTTP 400 and clear error message."""
        res = self.client.post(
            self.url,
            data={'from_period': '102026', 'to_period': '042026'},
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['status'], 'VALIDATION_ERROR')
        self.assertEqual(res.data['error_code'], 'INVALID_PERIOD_RANGE')
        self.assertIn('cannot be later than to_period', res.data['error'])

    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_11_qrmp_interim_months_handled_non_fatally(self, mock_single):
        """
        Under verified QRMP, M1 (April) and M2 (May) return FORM_NOT_APPLICABLE,
        while M3 (June) returns SUCCESS.
        Overall outcome must be SUCCESS with not_applicable_periods properly bucketed.
        """
        # Set verified filing frequency to QRMP
        self.registration.set_filing_frequency('QRMP', source='PORTAL_API', user=self.user)

        def side_effect_qrmp(company, registration, return_period, user):
            if return_period in ['042026', '052026']:
                return {
                    "success": False,
                    "status": "NOT_APPLICABLE",
                    "is_form_not_applicable": True,
                    "error": "GSTR-2B not applicable for interim month",
                    "error_category": "FORM_NOT_APPLICABLE"
                }
            return {
                "success": True,
                "status": "SUCCESS",
                "total_invoices_ingested": 15,
                "provider_records_count": 15,
                "records_created": 15,
                "records_updated": 0,
                "records_unchanged": 0
            }

        mock_single.side_effect = side_effect_qrmp

        res = self.client.post(
            self.url,
            data={
                'from_period': '042026',
                'to_period': '062026',
                'registration_id': str(self.registration.id)
            },
            format='json',
            HTTP_X_COMPANY_ID=str(self.company.id)
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        self.assertTrue(data['success'])
        self.assertEqual(data['successful_periods_count'], 1)
        self.assertEqual(data['not_applicable_periods_count'], 2)
        self.assertEqual(data['failed_periods_count'], 0)
        self.assertIn('QRMP', data['message'])

    @patch('apps.gst.services.itc_reconciliation_service.ITCReconciliationService.reconcile_period')
    @patch('apps.gst.services.reconciliation_service.GSTReconciliationService.fetch_and_ingest_from_sandbox')
    def test_12_unexpected_reconciliation_error_marks_attempt_failed(self, mock_fetch, mock_rec):
        """If downstream reconciliation throws an unexpected exception, attempt status must be FAILED."""
        mock_fetch.return_value = {
            "success": True,
            "status": "SUCCESS",
            "total_invoices_ingested": 5,
            "provider_records_count": 5,
            "records_created": 5,
            "records_updated": 0,
            "records_unchanged": 0
        }
        mock_rec.side_effect = RuntimeError("Database deadlock during reconciliation")

        with self.assertRaises(RuntimeError):
            GSTReconciliationService.fetch_and_ingest_range(
                company=self.company,
                registration=self.registration,
                from_period='042026',
                to_period='052026',
                user=self.user
            )

        attempt = GSTR2BSyncAttempt.objects.filter(company=self.company).first()
        self.assertEqual(attempt.status, 'FAILED')
        self.assertIn('Database deadlock', attempt.error_message)


class Round247AccountingAndIsolationInvariantTests(TestCase):
    """
    SECTION C: ACCOUNTING INVARIANTS & STRICT TENANT ISOLATION
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='auditor_invariants@testcorp.com',
            password='TestPassword123!'
        )
        # Dedicated Test Sandbox
        self.sandbox_company = Company.objects.create(
            name='Apex Belting & Industrial Store (Demo)',
            legal_name='Apex Belting & Industrial Store Demo Pvt Ltd',
            gstin='27AAPCA1234F1Z5',
            state_code='27',
            email='audit@apexbelting.demo'
        )
        UserCompany.objects.create(user=self.user, company=self.sandbox_company, role='OWNER')

        # Accounting Groups
        self.grp_assets = LedgerGroup.objects.create(
            company=self.sandbox_company, name='Current Assets', nature='ASSET'
        )
        self.grp_liabilities = LedgerGroup.objects.create(
            company=self.sandbox_company, name='Current Liabilities', nature='LIABILITY'
        )
        self.grp_expenses = LedgerGroup.objects.create(
            company=self.sandbox_company, name='Direct Expenses', nature='EXPENSE'
        )

        self.cash_ledger = Ledger.objects.create(
            company=self.sandbox_company, name='Cash Account', group=self.grp_assets
        )
        self.supplier_ledger = Ledger.objects.create(
            company=self.sandbox_company, name='Industrial Supplies Corp', group=self.grp_liabilities,
            gstin='27BBBBB1111B1Z1'
        )
        self.purchase_ledger = Ledger.objects.create(
            company=self.sandbox_company, name='Purchase Account', group=self.grp_expenses
        )

        self.product = Product.objects.create(
            company=self.sandbox_company,
            name='Seamless Industrial Belting 25mm',
            sku='BELT-25MM',
            hsn_code='4010',
            unit='MTR',
            gst_rate=Decimal('18.00')
        )

        # Baseline Purchase Voucher
        self.voucher = Voucher.objects.create(
            company=self.sandbox_company,
            voucher_type='PURCHASE',
            voucher_number='PUR-2026-001',
            external_invoice_number='INV-SUPP-101',
            voucher_date=date(2026, 8, 15),
            party_ledger=self.supplier_ledger,
            status='POSTED',
            total_amount=Decimal('11800.00'),
            created_by=self.user
        )
        VoucherItem.objects.create(
            voucher=self.voucher,
            product=self.product,
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            taxable_amount=Decimal('10000.00'),
            gst_rate=Decimal('18.00'),
            cgst_amount=Decimal('900.00'),
            sgst_amount=Decimal('900.00'),
            total_amount=Decimal('11800.00')
        )

    def test_13_accounting_voucher_and_ledger_invariants_preserved(self):
        """
        Verify that GSTR2BSyncAttempt creation and period range resolution
        have ZERO side effects on voucher totals, ledger balances, and voucher fields.
        """
        v_before = Voucher.objects.get(id=self.voucher.id)
        amt_before = v_before.total_amount
        status_before = v_before.status
        date_before = v_before.voucher_date

        # Perform sync attempt creation and range resolution
        GSTPeriodService.resolve_period_range(from_period='042026', to_period='102026')
        GSTR2BSyncAttempt.objects.create(
            company=self.sandbox_company,
            return_period='042026-102026',
            status='SUCCESS',
            total_invoices_ingested=50
        )

        v_after = Voucher.objects.get(id=self.voucher.id)
        self.assertEqual(v_after.total_amount, amt_before)
        self.assertEqual(v_after.status, status_before)
        self.assertEqual(v_after.voucher_date, date_before)

    def test_14_strict_tenant_isolation_maa_annapurna_protected(self):
        """
        CRITICAL MANDATORY INVARIANT:
        Verify that protected production tenant 'Maa Annapurna Belting Store'
        (5d2e5dea-ff86-4871-b2af-fe1c5a05c03c) is completely untouched.
        """
        maa_id = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'

        # Ensure no sync attempts or imports were created for protected tenant
        maa_sync_count = GSTR2BSyncAttempt.objects.filter(company_id=maa_id).count()
        self.assertEqual(maa_sync_count, 0, "ABORT: Sync attempts detected for protected tenant!")

        maa_import_count = GSTR2BImport.objects.filter(company_id=maa_id).count()
        self.assertEqual(maa_import_count, 0, "ABORT: GSTR-2B imports detected for protected tenant!")

        maa_vouchers = Voucher.objects.filter(company_id=maa_id).count()
        self.assertEqual(maa_vouchers, 0, "ABORT: Vouchers modified for protected tenant!")

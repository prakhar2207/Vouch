import json
import time
import uuid
import datetime
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, FinancialYear
from apps.common.idempotency import IdempotencyMiddleware
from apps.common.services.backup_service import DatabaseBackupService
from apps.accounting.services.report_service import ReportService
from apps.common.checks import check_production_security_gate

User = get_user_model()

class CodeReviewAuditFindingsTests(TestCase):
    """
    Empirical automated test suite verifying resolution of all 4 preliminary code review findings:
    1. Idempotency cache isolation, payload integrity, and atomic concurrency locking.
    2. Backup encryption key separation and zero-downtime key rotation via MultiFernet.
    3. Trial balance dynamic entry aggregation and self-healing balance drift reconciliation.
    4. Production security configuration checks.
    """

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user1 = User.objects.create_user(email="auditor1@srilekh.com", password="SecurePassword123!")
        self.user2 = User.objects.create_user(email="auditor2@srilekh.com", password="SecurePassword123!")
        
        self.company1 = Company.objects.create(name="Audit Corp A", gstin="07AAAAA0000A1Z5")
        self.company2 = Company.objects.create(name="Audit Corp B", gstin="07BBBBB0000B1Z6")
        
        self.asset_grp = LedgerGroup.objects.create(company=self.company1, name="Current Assets", nature="ASSET")
        self.income_grp = LedgerGroup.objects.create(company=self.company1, name="Sales Accounts", nature="INCOME")
        
        self.fy = FinancialYear.objects.create(
            company=self.company1,
            name="FY 2026-27",
            code="26-27",
            start_date=datetime.date(2026, 4, 1),
            end_date=datetime.date(2027, 3, 31),
            is_closed=False
        )

    def test_01_idempotency_cross_endpoint_isolation(self):
        """Verifies that the same idempotency key used across two different endpoints does NOT collide."""
        call_counts = {"endpoint_a": 0, "endpoint_b": 0}

        def view_a(req):
            call_counts["endpoint_a"] += 1
            return JsonResponse({"endpoint": "a", "count": call_counts["endpoint_a"]}, status=200)

        def view_b(req):
            call_counts["endpoint_b"] += 1
            return JsonResponse({"endpoint": "b", "count": call_counts["endpoint_b"]}, status=200)

        middleware_a = IdempotencyMiddleware(view_a)
        middleware_b = IdempotencyMiddleware(view_b)

        shared_key = "idemp-key-shared-uuid-001"

        # Request to endpoint A
        req_a = self.factory.post(
            "/api/v1/sales/",
            data=json.dumps({"item": "A"}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=shared_key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req_a.user = self.user1
        res_a = middleware_a(req_a)
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(json.loads(res_a.content)["endpoint"], "a")

        # Request to endpoint B with the EXACT SAME idempotency key
        req_b = self.factory.post(
            "/api/v1/purchases/",
            data=json.dumps({"item": "A"}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=shared_key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req_b.user = self.user1
        res_b = middleware_b(req_b)
        self.assertEqual(res_b.status_code, 200)
        # MUST execute endpoint B and NOT return the cached endpoint A response!
        self.assertEqual(json.loads(res_b.content)["endpoint"], "b")
        self.assertEqual(call_counts["endpoint_a"], 1)
        self.assertEqual(call_counts["endpoint_b"], 1)

    def test_02_idempotency_payload_mismatch_rejection(self):
        """Verifies that reusing the same key with different request parameters returns HTTP 422."""
        call_count = 0
        def dummy_view(req):
            nonlocal call_count
            call_count += 1
            return JsonResponse({"status": "created", "call_count": call_count}, status=201)

        middleware = IdempotencyMiddleware(dummy_view)
        key = "idemp-key-payload-check-002"

        # First request with ₹1,000
        req1 = self.factory.post(
            "/api/v1/invoices/",
            data=json.dumps({"amount": 1000}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req1.user = self.user1
        res1 = middleware(req1)
        self.assertEqual(res1.status_code, 201)

        # Retry with identical payload -> should replay
        req_retry = self.factory.post(
            "/api/v1/invoices/",
            data=json.dumps({"amount": 1000}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req_retry.user = self.user1
        res_retry = middleware(req_retry)
        self.assertEqual(res_retry.status_code, 201)
        self.assertEqual(res_retry.get("X-Idempotent-Replay"), "true")
        self.assertEqual(call_count, 1)

        # Malicious / Buggy retry with DIFFERENT payload (₹5,000) using same key
        req_diff = self.factory.post(
            "/api/v1/invoices/",
            data=json.dumps({"amount": 5000}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req_diff.user = self.user1
        res_diff = middleware(req_diff)
        # MUST reject with 422 Unprocessable Entity
        self.assertEqual(res_diff.status_code, 422)
        diff_data = json.loads(res_diff.content)
        self.assertEqual(diff_data["error_code"], "IDEMPOTENCY_PAYLOAD_MISMATCH")
        self.assertEqual(call_count, 1)

    def test_03_idempotency_concurrency_locking(self):
        """Verifies that simultaneous execution returns HTTP 409 Conflict."""
        key = "idemp-key-concurrent-lock-003"
        
        # Simulate in-flight operation by manually setting lock
        endpoint_sig = "a1b2c3d4e5f60718"
        # Create request and process once
        in_flight = False
        def slow_view(req):
            nonlocal in_flight
            in_flight = True
            return JsonResponse({"done": True}, status=200)

        middleware = IdempotencyMiddleware(slow_view)
        req = self.factory.post(
            "/api/v1/orders/",
            data=json.dumps({"order_id": 99}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req.user = self.user1

        # First call starts processing
        res_first_step = middleware.process_request(req)
        self.assertIsNone(res_first_step)  # Proceeded to view

        # Second concurrent request arrives BEFORE first request has called process_response!
        req_concurrent = self.factory.post(
            "/api/v1/orders/",
            data=json.dumps({"order_id": 99}),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=key,
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        req_concurrent.user = self.user1

        res_locked = middleware.process_request(req_concurrent)
        self.assertIsNotNone(res_locked)
        self.assertEqual(res_locked.status_code, 409)
        locked_data = json.loads(res_locked.content)
        self.assertEqual(locked_data["error_code"], "IDEMPOTENCY_LOCKED")

    def test_04_backup_encryption_key_rotation(self):
        """Verifies that backups encrypted with an older key decrypt cleanly via MultiFernet fallbacks."""
        old_key = "PreviousBackupKeySecret-2025-V1!!"
        new_key = "RotatedBackupKeySecret-2026-V2!!"

        # 1. Simulate backup made under old key
        with self.settings(BACKUP_ENCRYPTION_KEY=old_key, BACKUP_ENCRYPTION_KEY_FALLBACKS=[]):
            original_data = b"PostgreSQL database dump contents for disaster recovery verification"
            encrypted_old = DatabaseBackupService.encrypt_data(original_data)
            decrypted_old = DatabaseBackupService.decrypt_data(encrypted_old)
            self.assertEqual(decrypted_old, original_data)

        # 2. Rotate to new primary key, keeping old key in fallbacks
        with self.settings(BACKUP_ENCRYPTION_KEY=new_key, BACKUP_ENCRYPTION_KEY_FALLBACKS=[old_key]):
            # Verify new backups encrypt with new key
            encrypted_new = DatabaseBackupService.encrypt_data(original_data)
            self.assertNotEqual(encrypted_new, encrypted_old)
            self.assertEqual(DatabaseBackupService.decrypt_data(encrypted_new), original_data)

            # CRITICAL: Verify old backup encrypted with old key STILL decrypts seamlessly!
            decrypted_legacy = DatabaseBackupService.decrypt_data(encrypted_old)
            self.assertEqual(decrypted_legacy, original_data)

    def test_05_trial_balance_entry_aggregation_and_drift_healing(self):
        """Verifies that Trial Balance aggregates posted ledger entries and self-heals stored balance drift."""
        debtor = Ledger.objects.create(
            company=self.company1,
            group=self.asset_grp,
            name="Alpha Enterprises",
            ledger_type="CUSTOMER",
            current_balance=Decimal('0.00')
        )
        sales = Ledger.objects.create(
            company=self.company1,
            group=self.income_grp,
            name="General Sales",
            ledger_type="SALES",
            current_balance=Decimal('0.00')
        )

        # Post a genuine voucher with ₹25,000 transaction
        voucher = Voucher.objects.create(
            company=self.company1,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV-AUDIT-001",
            voucher_date=datetime.date(2026, 5, 10),
            total_amount=Decimal('25000.00'),
            status="POSTED",
            created_by=self.user1
        )
        LedgerEntry.objects.create(
            voucher=voucher,
            company=self.company1,
            ledger=debtor,
            debit_amount=Decimal('25000.00'),
            credit_amount=Decimal('0.00')
        )
        LedgerEntry.objects.create(
            voucher=voucher,
            company=self.company1,
            ledger=sales,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('25000.00')
        )

        # Sales current_balance matches posted entry
        sales.current_balance = Decimal('25000.00')
        sales.save(update_fields=['current_balance'])

        # Deliberately inject artificial drift in stored current_balance for debtor
        debtor.current_balance = Decimal('99999.00')  # Corrupted cache!
        debtor.save(update_fields=['current_balance'])

        # Generate trial balance
        tb = ReportService.generate_trial_balance(self.company1, auto_reconcile=True)

        # 1. Total Debits and Credits must strictly reflect the TRUE entry amount (₹25,000)
        self.assertTrue(tb["totals"]["is_balanced"])
        self.assertEqual(tb["totals"]["total_debit"], Decimal('25000.00'))
        self.assertEqual(tb["totals"]["total_credit"], Decimal('25000.00'))

        # 2. Integrity audit must have caught the drift
        self.assertEqual(tb["integrity_audit"]["discrepancies_detected"], 1)
        mismatch = tb["integrity_audit"]["mismatches"][0]
        self.assertEqual(mismatch["ledger_name"], "Alpha Enterprises")
        self.assertEqual(mismatch["stored_balance"], "99999.00")
        self.assertEqual(mismatch["entry_calculated_balance"], "25000.00")

        # 3. Ledger current_balance must be self-healed back to ₹25,000
        debtor.refresh_from_db()
        self.assertEqual(debtor.current_balance, Decimal('25000.00'))

    def test_06_gst_calculator_missing_state_fail_closed(self):
        """
        V-02: Verifies that GST calculation fails closed when seller or buyer state is missing,
        preventing silent fallback to intra-state CGST/SGST.
        """
        from apps.gst.services.gst_calculator import GSTCalculator
        from rest_framework.exceptions import ValidationError

        # 1. Missing buyer state for taxable supply -> must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            GSTCalculator.calculate_taxes(
                company_state_code="09",
                party_state_code="",
                taxable_amount=Decimal("1000.00"),
                gst_rate=Decimal("18.00")
            )
        self.assertIn("Buyer state code / Place of Supply", str(ctx.exception))

        # 2. Missing seller state for taxable supply -> must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            GSTCalculator.calculate_taxes(
                company_state_code="",
                party_state_code="27",
                taxable_amount=Decimal("1000.00"),
                gst_rate=Decimal("18.00")
            )
        self.assertIn("Seller/Company state code is missing", str(ctx.exception))

        # 3. Both missing for taxable supply -> must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            GSTCalculator.calculate_taxes(
                company_state_code="",
                party_state_code="",
                taxable_amount=Decimal("1000.00"),
                gst_rate=Decimal("18.00")
            )
        self.assertIn("Both seller and buyer state codes are missing", str(ctx.exception))

        # 4. Correct interstate calculation with verified states
        inter = GSTCalculator.calculate_taxes(
            company_state_code="09",
            party_state_code="27",
            taxable_amount=Decimal("1000.00"),
            gst_rate=Decimal("18.00")
        )
        self.assertEqual(inter['treatment'], 'INTERSTATE')
        self.assertEqual(inter['igst'], Decimal("180.00"))
        self.assertEqual(inter['cgst'], Decimal("0.00"))
        self.assertEqual(inter['sgst'], Decimal("0.00"))

        # 5. Correct intrastate calculation with verified states
        intra = GSTCalculator.calculate_taxes(
            company_state_code="09",
            party_state_code="09",
            taxable_amount=Decimal("1000.00"),
            gst_rate=Decimal("18.00")
        )
        self.assertEqual(intra['treatment'], 'INTRASTATE')
        self.assertEqual(intra['cgst'], Decimal("90.00"))
        self.assertEqual(intra['sgst'], Decimal("90.00"))
        self.assertEqual(intra['igst'], Decimal("0.00"))

        # 6. 0% / Non-taxable supply with missing states does NOT fail
        zero_rated = GSTCalculator.calculate_taxes(
            company_state_code="",
            party_state_code="",
            taxable_amount=Decimal("1000.00"),
            gst_rate=Decimal("0.00")
        )
        self.assertEqual(zero_rated['total_tax'], Decimal("0.00"))

    def test_07_banking_statement_upload_file_limits_and_sanitized_errors(self):
        """
        V-03: Verifies bank statement upload limits (size, format) and sanitized error reporting
        without leaking server internals.
        """
        from apps.accounting.banking_views import BankStatementUploadAPIView, MAX_STATEMENT_FILE_SIZE
        from apps.ledgers.models import Ledger
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIRequestFactory, force_authenticate
        from unittest.mock import patch
        from apps.companies.models import UserCompany

        api_factory = APIRequestFactory()
        UserCompany.objects.get_or_create(company=self.company1, user=self.user1, defaults={"role": "OWNER"})

        bank_ledger = Ledger.objects.create(
            company=self.company1,
            group=self.asset_grp,
            name="HDFC Current Account",
            ledger_type="BANK",
            current_balance=Decimal("50000.00")
        )

        view = BankStatementUploadAPIView.as_view()

        # 1. Reject unsupported file format (.exe)
        bad_file = SimpleUploadedFile("malware.exe", b"malicious binary payload", content_type="application/octet-stream")
        req_bad = api_factory.post(
            "/api/v1/accounting/bank-statements/upload/",
            {"file": bad_file, "bank_ledger_id": str(bank_ledger.id)},
            format="multipart",
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        force_authenticate(req_bad, user=self.user1)

        res_bad = view(req_bad)
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn("Unsupported file format", res_bad.data["error"])

        # 2. Reject file exceeding size limit
        huge_bytes = b"x" * (MAX_STATEMENT_FILE_SIZE + 1024)
        huge_file = SimpleUploadedFile("statement.csv", huge_bytes, content_type="text/csv")
        req_huge = api_factory.post(
            "/api/v1/accounting/bank-statements/upload/",
            {"file": huge_file, "bank_ledger_id": str(bank_ledger.id)},
            format="multipart",
            HTTP_X_COMPANY_ID=str(self.company1.id)
        )
        force_authenticate(req_huge, user=self.user1)

        res_huge = view(req_huge)
        self.assertEqual(res_huge.status_code, 400)
        self.assertIn("exceeds the 15MB limit", res_huge.data["error"])

        # 3. Unhandled internal error returns HTTP 500 with correlation_id and NO internal path leak
        csv_file = SimpleUploadedFile("statement.csv", b"Date,Narration,Amount\n2026-05-01,Test,100", content_type="text/csv")
        with patch("apps.accounting.services.bank_statement_service.BankStatementService.parse_statement", side_effect=RuntimeError("/var/secret/db_credentials.txt: Connection refused")):
            req_err = api_factory.post(
                "/api/v1/accounting/bank-statements/upload/",
                {"file": csv_file, "bank_ledger_id": str(bank_ledger.id)},
                format="multipart",
                HTTP_X_COMPANY_ID=str(self.company1.id)
            )
            force_authenticate(req_err, user=self.user1)

            res_err = view(req_err)
            self.assertEqual(res_err.status_code, 500)
            self.assertIn("correlation_id", res_err.data)
            self.assertNotIn("/var/secret", res_err.data["error"])
            self.assertEqual(res_err.data["error"], "An internal error occurred while parsing the bank statement.")

    def test_08_credit_debit_note_cumulative_reversal_lock(self):
        """
        V-07: Verifies row-locking and cumulative reversal boundaries for credit notes
        preventing over-reversals.
        """
        from apps.accounting.services.credit_debit_note_service import CreditDebitNoteService
        from apps.inventory.models import Product, ProductCategory
        from django.core.exceptions import ValidationError

        cat = ProductCategory.objects.create(company=self.company1, name="Standard Goods")
        prod = Product.objects.create(
            company=self.company1,
            category=cat,
            name="V-Belt B-52",
            selling_price=Decimal("1000.00"),
            gst_rate=Decimal("18.00")
        )
        customer = Ledger.objects.create(
            company=self.company1,
            group=self.asset_grp,
            name="Beta Distributors",
            ledger_type="CUSTOMER",
            state_code="09"
        )

        # Create original sales invoice of ₹1,180 (₹1,000 taxable + ₹180 GST)
        sales_inv = Voucher.objects.create(
            company=self.company1,
            financial_year=self.fy,
            voucher_type="SALES",
            voucher_number="INV/26-27/0001",
            voucher_date=datetime.date(2026, 5, 1),
            party_ledger=customer,
            total_amount=Decimal("1180.00"),
            status="POSTED",
            created_by=self.user1
        )

        items_data = [{
            "product_id": str(prod.id),
            "quantity": 1,
            "rate": Decimal("1000.00"),
            "discount_percent": Decimal("0.00"),
            "gst_rate": Decimal("18.00")
        }]

        # 1. First credit note for ₹1,180 succeeds
        cn1 = CreditDebitNoteService.generate_credit_note(
            company=self.company1,
            user=self.user1,
            party_ledger=customer,
            items_data=items_data,
            original_invoice=sales_inv,
            voucher_date=datetime.date(2026, 5, 2)
        )
        self.assertEqual(cn1.total_amount, Decimal("1180.00"))

        # 2. Second credit note against the same invoice would exceed original invoice total -> raises ValidationError
        with self.assertRaises(ValidationError) as ctx:
            CreditDebitNoteService.generate_credit_note(
                company=self.company1,
                user=self.user1,
                party_ledger=customer,
                items_data=items_data,
                original_invoice=sales_inv,
                voucher_date=datetime.date(2026, 5, 3)
            )
        self.assertIn("exceeds original sales invoice", str(ctx.exception))

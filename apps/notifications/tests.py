import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounting.models import Voucher, VoucherItem
from apps.accounting.services.voucher_service import VoucherService
from apps.companies.models import Company, UserCompany
from apps.inventory.models import Product
from apps.ledgers.models import LedgerGroup, Ledger
from apps.notifications.email_service import EmailService
from apps.notifications.models import (
    EmailDeliveryLog,
    TransactionalOutboxEvent,
    NotificationPreference,
    SecureInvoiceAccessToken,
)
from apps.notifications.outbox_service import OutboxService


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SYNCHRONOUS_NOTIFICATIONS=True,
)
class NotificationSystemTests(TestCase):
    """
    Automated verification suite for SriLekh's Transactional Email Service,
    Transactional Outbox, Secure Invoice Access Tokens, and Company Notification Preferences.
    """

    def setUp(self):
        self.client = APIClient()
        mail.outbox.clear()

        # Create sandbox company and owner
        self.owner = User.objects.create_user(
            email="owner.apex@srilekh-sandbox.local",
            password="SecurePass123!@#",
            role="OWNER",
            email_verified=True,
        )
        self.company = Company.objects.create(
            name="Apex Belting Sandbox Corp",
            legal_name="Apex Belting Sandbox Corp",
            gstin="09ACHFS9225Q1Z7",
            pan="ACHFS9225Q",
            state_code="09",
            email="contact@apexbelting-sandbox.local",
            phone="9876543210",
            address="Plot 44, Industrial Area, Kanpur",
        )
        self.user_company = UserCompany.objects.create(
            user=self.owner,
            company=self.company,
            role="OWNER",
        )
        self.preference, _ = NotificationPreference.objects.get_or_create(company=self.company)

        # Setup core accounting groups & ledgers
        debtors_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name="Sundry Debtors", defaults={"nature": "ASSET"})
        sales_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name="Sales Accounts", defaults={"nature": "INCOME"})
        duties_grp, _ = LedgerGroup.objects.get_or_create(company=self.company, name="Duties & Taxes", defaults={"nature": "LIABILITY"})

        self.sales_ledger = Ledger.objects.create(company=self.company, group=sales_grp, name="Sales Account", ledger_type="SALES")
        self.cgst_ledger = Ledger.objects.create(company=self.company, group=duties_grp, name="Output CGST", ledger_type="TAX")
        self.sgst_ledger = Ledger.objects.create(company=self.company, group=duties_grp, name="Output SGST", ledger_type="TAX")

        # Customer Party Ledger
        self.customer_ledger = Ledger.objects.create(
            company=self.company,
            group=debtors_grp,
            name="Alpha Supplies Ltd",
            email="accounts@alphasupplies-sandbox.local",
            phone="9123456780",
            gstin="09AABCU9603R1ZM",
        )

        # Unit & Item
        self.item = Product.objects.create(
            company=self.company,
            name="High Heat Conveyor Belt 1200mm",
            unit="MTR",
            selling_price=Decimal("1000.00"),
            gst_rate=Decimal("18.00"),
        )

    # =========================================================================
    # EmailService Tests
    # =========================================================================

    def test_email_service_dispatches_with_verified_sender_and_reply_to(self):
        """EmailService: Sends from SriLekh <admin@srilekh.com> with support@srilekh.com reply-to."""
        success, log, err = EmailService.send_email(
            to_email="customer@destination.local",
            subject="Test SriLekh Notification",
            template_name="registration_otp",
            context={"otp_code": "654321"},
            email_type="REGISTRATION_OTP",
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        sent = mail.outbox[0]
        self.assertEqual(sent.from_email, "SriLekh <admin@srilekh.com>")
        self.assertEqual(sent.reply_to, ["support@srilekh.com"])
        self.assertEqual(sent.to, ["customer@destination.local"])
        self.assertIn("654321", sent.body)

        # Delivery log verified
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SENT')
        self.assertEqual(log.attempts, 1)

    def test_email_service_idempotency_prevents_duplicate_sends(self):
        """EmailService: Repeated send with identical idempotency_key returns cached result without re-dispatching."""
        idempotency_key = "unique_idem_test_key_999"

        # First send
        success1, log1, _ = EmailService.send_email(
            to_email="customer@destination.local",
            subject="Invoice Notification",
            template_name="registration_otp",
            context={"otp_code": "111222"},
            idempotency_key=idempotency_key,
        )
        self.assertTrue(success1)
        self.assertEqual(len(mail.outbox), 1)

        # Duplicate send
        success2, log2, msg2 = EmailService.send_email(
            to_email="customer@destination.local",
            subject="Invoice Notification",
            template_name="registration_otp",
            context={"otp_code": "111222"},
            idempotency_key=idempotency_key,
        )
        self.assertTrue(success2)
        self.assertEqual(msg2, "idempotent_duplicate")
        # Invariant: No additional email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(log1.id, log2.id)

    # =========================================================================
    # Transactional Outbox & Invoice Notification Tests
    # =========================================================================

    def test_posted_sales_invoice_creates_outbox_event_and_dispatches_notification(self):
        """Invoice Notification: Posting a sales invoice creates an outbox event and dispatches email with secure link."""
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-2026-0042',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            buyer_name='Alpha Supplies Ltd',
            buyer_email='accounts@alphasupplies-sandbox.local',
            buyer_gstin='09AABCU9603R1ZM',
            total_amount=Decimal('1180.00'),
            status='DRAFT',
            created_by=self.owner,
        )
        VoucherItem.objects.create(
            voucher=voucher,
            product=self.item,
            quantity=Decimal('1.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('1000.00'),
            total_amount=Decimal('1180.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00'),
        )

        mail.outbox.clear()

        # Double-entry ledger entries (Total Debits == Total Credits == 1180.00)
        from apps.accounting.models import LedgerEntry
        LedgerEntry.objects.create(voucher=voucher, ledger=self.customer_ledger, debit_amount=Decimal('1180.00'), credit_amount=Decimal('0.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.sales_ledger, debit_amount=Decimal('0.00'), credit_amount=Decimal('1000.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.cgst_ledger, debit_amount=Decimal('0.00'), credit_amount=Decimal('90.00'))
        LedgerEntry.objects.create(voucher=voucher, ledger=self.sgst_ledger, debit_amount=Decimal('0.00'), credit_amount=Decimal('90.00'))

        # Post Voucher with on_commit hooks captured
        with self.captureOnCommitCallbacks(execute=True):
            posted_voucher = VoucherService.post_voucher(voucher)
        self.assertEqual(posted_voucher.status, 'POSTED')

        # 1. Verify TransactionalOutboxEvent created
        outbox_event = TransactionalOutboxEvent.objects.filter(
            aggregate_id=str(voucher.id),
            event_type='INVOICE_POSTED'
        ).first()
        self.assertIsNotNone(outbox_event)
        self.assertEqual(outbox_event.company, self.company)

        # 2. Process outbox event
        success = OutboxService.process_outbox_event(outbox_event.id)
        self.assertTrue(success)

        outbox_event.refresh_from_db()
        self.assertEqual(outbox_event.status, 'PROCESSED')
        self.assertIsNotNone(outbox_event.processed_at)

        # 3. Verify Secure Access Token created
        access_token = SecureInvoiceAccessToken.objects.filter(voucher=voucher).first()
        self.assertIsNotNone(access_token)
        self.assertTrue(access_token.is_valid())

        # 4. Verify Email Dispatched
        self.assertEqual(len(mail.outbox), 1)
        invoice_mail = mail.outbox[0]
        self.assertIn("accounts@alphasupplies-sandbox.local", invoice_mail.to)
        self.assertIn("INV-2026-0042", invoice_mail.subject)
        self.assertIn("Alpha Supplies Ltd", invoice_mail.subject)
        self.assertIn("SriLekh <admin@srilekh.com>", invoice_mail.from_email)
        self.assertIn(access_token.token, invoice_mail.body)

        # 5. Verify PDF attached
        self.assertTrue(len(invoice_mail.attachments) > 0)
        self.assertTrue(invoice_mail.attachments[0][0].endswith('.pdf'))

    def test_draft_invoice_does_not_create_outbox_event(self):
        """Trigger Invariant: Saving a draft voucher creates NO outbox event."""
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='DRAFT-001',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            total_amount=Decimal('500.00'),
            status='DRAFT',
            created_by=self.owner,
        )
        self.assertFalse(
            TransactionalOutboxEvent.objects.filter(aggregate_id=str(voucher.id)).exists()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_rolled_back_voucher_transaction_creates_no_outbox_event(self):
        """Atomicity Invariant: An aborted or rolled-back transaction creates NO durable outbox event."""
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='FAIL-001',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            total_amount=Decimal('500.00'),
            status='DRAFT',
            created_by=self.owner,
        )

        try:
            with transaction.atomic():
                OutboxService.create_invoice_outbox_event(voucher)
                # Intentionally trigger an error to simulate database rollback
                raise RuntimeError("Simulated transaction rollback during financial write")
        except RuntimeError:
            pass

        # Invariant: Outbox event was rolled back with the transaction
        self.assertFalse(
            TransactionalOutboxEvent.objects.filter(aggregate_id=str(voucher.id)).exists()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_recipient_email_marks_outbox_event_skipped(self):
        """Safety Invariant: When no recipient email is available, outbox marks SKIPPED without failing."""
        # Ledger without email
        no_email_ledger = Ledger.objects.create(
            company=self.company,
            group=self.customer_ledger.group,
            name="Cash Customer Walk-In",
            email="",
        )

        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-NOEMAIL-001',
            voucher_date=date.today(),
            party_ledger=no_email_ledger,
            buyer_name='Cash Customer Walk-In',
            buyer_email='',
            total_amount=Decimal('200.00'),
            status='POSTED',
            created_by=self.owner,
        )

        event = OutboxService.create_invoice_outbox_event(voucher)
        self.assertIsNotNone(event)

        success = OutboxService.process_outbox_event(event.id)
        self.assertTrue(success)

        event.refresh_from_db()
        self.assertEqual(event.status, 'SKIPPED')
        self.assertIn("No recipient email found", event.error_log)
        self.assertEqual(len(mail.outbox), 0)

    def test_notification_preference_disabling_skips_outbox_creation(self):
        """Preference Invariant: When send_invoice_email_on_post is False, no outbox event is created."""
        self.preference.send_invoice_email_on_post = False
        self.preference.save()

        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-DISABLED-001',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            total_amount=Decimal('500.00'),
            status='POSTED',
            created_by=self.owner,
        )

        event = OutboxService.create_invoice_outbox_event(voucher)
        self.assertIsNone(event)
        self.assertEqual(len(mail.outbox), 0)

    # =========================================================================
    # Secure Invoice Access Token Tests (IDOR Protection)
    # =========================================================================

    def test_secure_invoice_public_view_allows_tokenized_access(self):
        """IDOR Protection: Public view endpoint allows access with valid cryptographic token."""
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-SECURE-001',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            total_amount=Decimal('1000.00'),
            status='POSTED',
            created_by=self.owner,
        )

        token_obj = SecureInvoiceAccessToken.objects.create(
            voucher=voucher,
            token="cryptographic_secure_token_abc123_xyz789",
            expires_at=timezone.now() + timedelta(days=30),
        )

        res = self.client.get(f"/api/v1/invoices/public/view/?token={token_obj.token}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        self.assertEqual(res.data["data"]["invoice_number"], "INV-SECURE-001")
        self.assertEqual(res.data["data"]["seller"]["name"], self.company.name)

        # Access count tracked
        token_obj.refresh_from_db()
        self.assertEqual(token_obj.view_count, 1)
        self.assertIsNotNone(token_obj.last_accessed_at)

    def test_secure_invoice_public_view_rejects_expired_token(self):
        """Security: Expired access tokens return 410 GONE."""
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-EXPIRED-001',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            total_amount=Decimal('1000.00'),
            status='POSTED',
            created_by=self.owner,
        )

        token_obj = SecureInvoiceAccessToken.objects.create(
            voucher=voucher,
            token="expired_token_12345",
            expires_at=timezone.now() - timedelta(days=1),  # Expired
        )

        res = self.client.get(f"/api/v1/invoices/public/view/?token={token_obj.token}")
        self.assertEqual(res.status_code, 410)
        self.assertIn("expired", res.data["error"])

    def test_secure_invoice_public_view_rejects_revoked_token(self):
        """Security: Revoked access tokens return 404 NOT FOUND."""
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-REVOKED-001',
            voucher_date=date.today(),
            party_ledger=self.customer_ledger,
            total_amount=Decimal('1000.00'),
            status='POSTED',
            created_by=self.owner,
        )

        token_obj = SecureInvoiceAccessToken.objects.create(
            voucher=voucher,
            token="revoked_token_67890",
            expires_at=timezone.now() + timedelta(days=30),
            is_revoked=True,
        )

        res = self.client.get(f"/api/v1/invoices/public/view/?token={token_obj.token}")
        self.assertEqual(res.status_code, 404)
        self.assertIn("invalid or has been revoked", res.data["error"])

    # =========================================================================
    # Notification Preferences API Tests
    # =========================================================================

    def test_notification_preferences_get_and_patch(self):
        """Preferences API: Authenticated owner can inspect and toggle company notification preferences."""
        self.client.force_authenticate(user=self.owner)

        # GET
        res_get = self.client.get("/api/v1/notifications/preferences/")
        self.assertEqual(res_get.status_code, 200)
        self.assertTrue(res_get.data["data"]["send_invoice_email_on_post"])
        self.assertTrue(res_get.data["data"]["attach_invoice_pdf"])

        # PATCH
        patch_payload = {
            "send_invoice_email_on_post": False,
            "attach_invoice_pdf": False,
            "send_overdue_reminder_email": True,
        }
        res_patch = self.client.patch("/api/v1/notifications/preferences/", data=patch_payload, format="json")
        self.assertEqual(res_patch.status_code, 200)
        self.assertFalse(res_patch.data["data"]["send_invoice_email_on_post"])
        self.assertFalse(res_patch.data["data"]["attach_invoice_pdf"])
        self.assertTrue(res_patch.data["data"]["send_overdue_reminder_email"])
        self.assertEqual(res_patch.data["data"]["updated_by"], self.owner.email)

import json
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework.test import APIClient

from apps.accounts.models import User, EmailVerificationChallenge, PendingRegistration
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.notifications.models import NotificationPreference, EmailDeliveryLog


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SYNCHRONOUS_NOTIFICATIONS=True,
)
class EmailAuthOtpTests(TestCase):
    """
    Comprehensive verification suite for SriLekh's Enterprise Email Verification,
    OTP Authentication, Business Registration, and Password Recovery.
    """

    def setUp(self):
        self.client = APIClient()
        self.test_email = "test.merchant@srilekh-sandbox.local"
        self.test_password = "SecureEnterprisePass123!@#"
        mail.outbox.clear()

    # =========================================================================
    # Step 1: Initiate Registration & OTP Generation
    # =========================================================================

    def test_initiate_registration_creates_hashed_otp_and_sends_email(self):
        """Test Step 1: Valid initiate request generates hashed OTP and sends branded email."""
        payload = {
            "email": self.test_email,
            "password": self.test_password,
            "confirm_password": self.test_password,
        }
        res = self.client.post("/api/v1/auth/register/initiate/", data=payload, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        self.assertIn("session_token", res.data)
        self.assertEqual(res.data["resend_cooldown"], 60)

        # 1. Verify Challenge in DB
        challenge = EmailVerificationChallenge.objects.filter(session_token=res.data["session_token"]).first()
        self.assertIsNotNone(challenge)
        self.assertEqual(challenge.email, self.test_email)
        self.assertFalse(challenge.is_verified)
        self.assertFalse(challenge.is_consumed)
        self.assertEqual(challenge.failed_attempts, 0)

        # Invariant: Plaintext OTP is NEVER stored in database
        self.assertTrue(challenge.otp_hash.startswith("pbkdf2_"))
        self.assertNotEqual(len(challenge.otp_hash), 6)

        # 2. Verify PendingRegistration record created
        pending = PendingRegistration.objects.filter(email=self.test_email).first()
        self.assertIsNotNone(pending)
        self.assertFalse(pending.is_verified)
        # Verify password is pre-hashed
        self.assertTrue(check_password(self.test_password, pending.password_hash))

        # 3. Verify Email Sent via Locmem backend
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn(self.test_email, sent_email.to)
        self.assertIn("SriLekh <admin@srilekh.com>", sent_email.from_email)
        self.assertIn("Verify your email address", sent_email.subject)
        self.assertEqual(sent_email.reply_to, ["support@srilekh.com"])

        # 4. Verify EmailDeliveryLog
        log = EmailDeliveryLog.objects.filter(recipient_email=self.test_email, email_type='REGISTRATION_OTP').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SENT')

    def test_initiate_registration_rejects_weak_password(self):
        """Step 1: Enforces password complexity rules."""
        payload = {
            "email": "weak@srilekh-sandbox.local",
            "password": "123",  # Too short, entirely numeric
        }
        res = self.client.post("/api/v1/auth/register/initiate/", data=payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data["success"])
        self.assertIn("Password requirement not met", res.data["error"])

    def test_initiate_registration_rejects_password_mismatch(self):
        """Step 1: Enforces password matching when confirm_password is provided."""
        payload = {
            "email": "mismatch@srilekh-sandbox.local",
            "password": self.test_password,
            "confirm_password": "DifferentPassword123!",
        }
        res = self.client.post("/api/v1/auth/register/initiate/", data=payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Passwords do not match", res.data["error"])

    def test_initiate_registration_rejects_duplicate_registered_user(self):
        """Step 1: Pre-checks user existence and prevents duplicate registration."""
        User.objects.create_user(email="existing@srilekh-sandbox.local", password=self.test_password)
        payload = {
            "email": "existing@srilekh-sandbox.local",
            "password": self.test_password,
        }
        res = self.client.post("/api/v1/auth/register/initiate/", data=payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", res.data["error"])

    # =========================================================================
    # Step 2: OTP Verification & Attempt Limits
    # =========================================================================

    def test_valid_otp_verification_activates_pending_registration(self):
        """Step 2: Correct OTP consumes challenge and issues registration_token."""
        # Initiate
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        session_token = res_init.data["session_token"]
        challenge = EmailVerificationChallenge.objects.get(session_token=session_token)

        # Force a known OTP hash for testing
        test_otp = "481920"
        challenge.otp_hash = make_password(test_otp)
        challenge.save(update_fields=['otp_hash'])

        # Submit OTP
        res_verify = self.client.post("/api/v1/auth/register/verify-otp/", {
            "session_token": session_token,
            "otp": test_otp,
        }, format="json")
        self.assertEqual(res_verify.status_code, 200)
        self.assertTrue(res_verify.data["success"])
        self.assertIn("registration_token", res_verify.data)

        # Verify challenge state: consumed and verified
        challenge.refresh_from_db()
        self.assertTrue(challenge.is_verified)
        self.assertTrue(challenge.is_consumed)

        # Verify pending registration state
        pending = PendingRegistration.objects.get(email=self.test_email)
        self.assertTrue(pending.is_verified)
        self.assertEqual(pending.registration_token, res_verify.data["registration_token"])

    def test_invalid_otp_decrements_remaining_attempts(self):
        """Step 2: Incorrect OTP increments failed attempts and returns warning."""
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        session_token = res_init.data["session_token"]

        res_bad = self.client.post("/api/v1/auth/register/verify-otp/", {
            "session_token": session_token,
            "otp": "000000",
        }, format="json")
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn("attempt(s) remaining", res_bad.data["error"])

        challenge = EmailVerificationChallenge.objects.get(session_token=session_token)
        self.assertEqual(challenge.failed_attempts, 1)

    def test_maximum_failed_attempts_locks_otp_challenge(self):
        """Step 2: 5 consecutive failed attempts lock and invalidate the challenge."""
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        session_token = res_init.data["session_token"]

        for _ in range(5):
            self.client.post("/api/v1/auth/register/verify-otp/", {
                "session_token": session_token,
                "otp": "999999",
            }, format="json")

        # 6th attempt is rejected due to lockout
        res_locked = self.client.post("/api/v1/auth/register/verify-otp/", {
            "session_token": session_token,
            "otp": "999999",
        }, format="json")
        self.assertEqual(res_locked.status_code, 400)
        self.assertTrue(any(p in res_locked.data["error"] for p in ["Maximum failed attempts", "Invalid or expired", "locked"]))

    def test_expired_otp_is_rejected(self):
        """Step 2: OTP challenges older than 5 minutes fail closed."""
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        session_token = res_init.data["session_token"]

        challenge = EmailVerificationChallenge.objects.get(session_token=session_token)
        challenge.expires_at = timezone.now() - timedelta(minutes=1)
        challenge.save(update_fields=['expires_at'])

        res_expired = self.client.post("/api/v1/auth/register/verify-otp/", {
            "session_token": session_token,
            "otp": "123456",
        }, format="json")
        self.assertEqual(res_expired.status_code, 400)
        self.assertIn("expired", res_expired.data["error"])

    def test_reused_consumed_otp_is_rejected(self):
        """Step 2: Prevent replay of already-consumed verification challenges."""
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        session_token = res_init.data["session_token"]
        challenge = EmailVerificationChallenge.objects.get(session_token=session_token)
        test_otp = "777888"
        challenge.otp_hash = make_password(test_otp)
        challenge.save(update_fields=['otp_hash'])

        # First verification succeeds
        self.client.post("/api/v1/auth/register/verify-otp/", {"session_token": session_token, "otp": test_otp})

        # Replay attempt fails
        res_replay = self.client.post("/api/v1/auth/register/verify-otp/", {"session_token": session_token, "otp": test_otp})
        self.assertEqual(res_replay.status_code, 400)
        self.assertIn("Invalid or expired", res_replay.data["error"])

    # =========================================================================
    # Step 3: Resend OTP Cooldown
    # =========================================================================

    def test_resend_cooldown_enforced(self):
        """Step 3: Reject resend attempts before 60-second cooldown expires."""
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        session_token = res_init.data["session_token"]

        # Immediate resend fails with 429
        res_resend = self.client.post("/api/v1/auth/register/resend-otp/", {
            "session_token": session_token,
        }, format="json")
        self.assertEqual(res_resend.status_code, 429)
        self.assertIn("Please wait", res_resend.data["error"])

    def test_resend_after_cooldown_succeeds_and_invalidates_old_challenge(self):
        """Step 3: Resend after 60s issues new session token and invalidates old."""
        res_init = self.client.post("/api/v1/auth/register/initiate/", {
            "email": self.test_email,
            "password": self.test_password,
        }, format="json")
        old_session_token = res_init.data["session_token"]
        old_challenge = EmailVerificationChallenge.objects.get(session_token=old_session_token)

        # Fast forward time beyond cooldown
        old_challenge.resend_available_at = timezone.now() - timedelta(seconds=1)
        old_challenge.save(update_fields=['resend_available_at'])

        mail.outbox.clear()
        res_resend = self.client.post("/api/v1/auth/register/resend-otp/", {
            "session_token": old_session_token,
        }, format="json")
        self.assertEqual(res_resend.status_code, 200)
        self.assertIn("session_token", res_resend.data)
        new_session_token = res_resend.data["session_token"]
        self.assertNotEqual(old_session_token, new_session_token)

        # Old challenge must be consumed
        old_challenge.refresh_from_db()
        self.assertTrue(old_challenge.is_consumed)

        # New challenge exists
        new_challenge = EmailVerificationChallenge.objects.get(session_token=new_session_token)
        self.assertFalse(new_challenge.is_consumed)
        self.assertEqual(len(mail.outbox), 1)

    # =========================================================================
    # Step 4: Business Registration & Atomic Provisioning
    # =========================================================================

    def test_complete_registration_gst_registered_business(self):
        """Step 4: Atomic business provisioning with valid GSTIN, default ledgers, and welcome email."""
        # 1. Setup verified pending registration
        pending = PendingRegistration.objects.create(
            email=self.test_email,
            password_hash=make_password(self.test_password),
            registration_token="test_reg_token_gst_123",
            is_verified=True,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        mail.outbox.clear()
        payload = {
            "registration_token": "test_reg_token_gst_123",
            "name": "SriLekh Verified Belts Pvt Ltd",
            "is_gst_registered": "true",
            "gstin": "09ACHFS9225Q1Z7",
            "phone": "9876543210",
            "state_code": "09",
            "address": "Transport Nagar, Kanpur",
            "proprietor_name": "Suresh Gupta",
            "proprietor_phone": "9876543210",
        }

        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post("/api/v1/auth/register/complete/", data=payload, format="multipart")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data["success"])
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

        # Invariant: User created with email_verified=True
        user = User.objects.get(email=self.test_email)
        self.assertTrue(user.email_verified)
        self.assertTrue(check_password(self.test_password, user.password))

        # Invariant: Company created with PAN derived from GSTIN
        company = Company.objects.get(name="SriLekh Verified Belts Pvt Ltd")
        self.assertEqual(company.gstin, "09ACHFS9225Q1Z7")
        self.assertEqual(company.pan, "ACHFS9225Q")
        self.assertEqual(company.state_code, "09")

        # Invariant: Core chart of accounts auto-provisioned
        self.assertTrue(LedgerGroup.objects.filter(company=company, name="Sundry Debtors").exists())
        self.assertTrue(LedgerGroup.objects.filter(company=company, name="Sundry Creditors").exists())
        self.assertTrue(Ledger.objects.filter(company=company, name="Sales Account").exists())
        self.assertTrue(Ledger.objects.filter(company=company, name="Output CGST").exists())

        # Invariant: NotificationPreference auto-created
        pref = NotificationPreference.objects.filter(company=company).first()
        self.assertIsNotNone(pref)
        self.assertTrue(pref.send_invoice_email_on_post)

        # Invariant: Pending registration consumed
        self.assertFalse(PendingRegistration.objects.filter(email=self.test_email).exists())

        # Invariant: Welcome email sent
        self.assertEqual(len(mail.outbox), 1)
        welcome_email = mail.outbox[0]
        self.assertIn(self.test_email, welcome_email.to)
        self.assertIn("Welcome to SriLekh", welcome_email.subject)
        self.assertIn("SriLekh Verified Belts Pvt Ltd", welcome_email.body)

    def test_complete_registration_gst_unregistered_business(self):
        """Step 4: Unregistered business can register without providing a GSTIN."""
        pending = PendingRegistration.objects.create(
            email="unregistered@srilekh-sandbox.local",
            password_hash=make_password(self.test_password),
            registration_token="test_reg_token_nogst_456",
            is_verified=True,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        payload = {
            "registration_token": "test_reg_token_nogst_456",
            "name": "Small Corner Kirana Store",
            "is_gst_registered": "false",
            "gstin": "",  # Blank GSTIN
            "phone": "9876543211",
            "state_code": "09",
            "address": "Chowk Bazar, Varanasi",
            "proprietor_name": "Anil Verma",
        }

        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post("/api/v1/auth/register/complete/", data=payload, format="multipart")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data["success"])

        company = Company.objects.get(name="Small Corner Kirana Store")
        self.assertEqual(company.gstin, "")
        user = User.objects.get(email="unregistered@srilekh-sandbox.local")
        self.assertTrue(user.email_verified)

    def test_complete_registration_rejects_invalid_gstin_for_gst_registered(self):
        """Step 4: Rejects malformed or invalid GSTIN for GST-registered business."""
        pending = PendingRegistration.objects.create(
            email="badgstin@srilekh-sandbox.local",
            password_hash=make_password(self.test_password),
            registration_token="test_bad_gstin_789",
            is_verified=True,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        payload = {
            "registration_token": "test_bad_gstin_789",
            "name": "Invalid GST Firm",
            "is_gst_registered": "true",
            "gstin": "INVALID12345678",  # Invalid checksum and structure
            "phone": "9876543212",
            "state_code": "09",
            "address": "Noida Sector 62",
        }

        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post("/api/v1/auth/register/complete/", data=payload, format="multipart")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid GSTIN", res.data["error"])
        # Invariant: No user or company created
        self.assertFalse(User.objects.filter(email="badgstin@srilekh-sandbox.local").exists())

    # =========================================================================
    # Step 5: Login & Account Verification Enforcement
    # =========================================================================

    def test_unverified_account_login_is_rejected(self):
        """Login: Rejects login when user email_verified is False."""
        user = User.objects.create_user(
            email="unverified.user@srilekh-sandbox.local",
            password=self.test_password,
            email_verified=False
        )

        res = self.client.post("/api/v1/auth/login/", {
            "email": "unverified.user@srilekh-sandbox.local",
            "password": self.test_password,
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Your email address is not verified", str(res.data))

    def test_verified_account_login_succeeds_with_jwt_tokens(self):
        """Login: Verified user logs in and receives JWT access and refresh tokens."""
        user = User.objects.create_user(
            email="verified.user@srilekh-sandbox.local",
            password=self.test_password,
            email_verified=True
        )

        res = self.client.post("/api/v1/auth/login/", {
            "email": "verified.user@srilekh-sandbox.local",
            "password": self.test_password,
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertTrue(res.data["user"]["email_verified"])

    # =========================================================================
    # Step 6: Password Reset Lifecycle
    # =========================================================================

    def test_password_reset_request_sends_email_with_token(self):
        """Password Reset: User requests reset link; backend sends email with expiring token."""
        user = User.objects.create_user(
            email="reset.user@srilekh-sandbox.local",
            password=self.test_password,
            email_verified=True
        )

        mail.outbox.clear()
        res = self.client.post("/api/v1/auth/password/reset/request/", {
            "email": "reset.user@srilekh-sandbox.local",
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])

        # Check reset email
        self.assertEqual(len(mail.outbox), 1)
        reset_mail = mail.outbox[0]
        self.assertIn("Reset Your Password", reset_mail.subject)
        self.assertIn("token=", reset_mail.body)

    def test_password_reset_confirm_updates_password_and_sends_confirmation(self):
        """Password Reset: Confirm with valid token sets new password and sends alert email."""
        user = User.objects.create_user(
            email="confirm.reset@srilekh-sandbox.local",
            password=self.test_password,
            email_verified=True
        )

        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        new_pass = "BrandNewSuperSecurePass456!@#"

        mail.outbox.clear()
        res = self.client.post("/api/v1/auth/password/reset/confirm/", {
            "uid": uid,
            "token": token,
            "new_password": new_pass,
        }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])

        # Verify password changed
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_pass))
        self.assertFalse(user.check_password(self.test_password))

        # Verify password changed confirmation email sent
        self.assertEqual(len(mail.outbox), 1)
        confirm_email = mail.outbox[0]
        self.assertIn("Your Password Was Changed", confirm_email.subject)

    def test_password_reset_token_replay_rejected(self):
        """Password Reset: A token cannot be reused after password has been changed."""
        user = User.objects.create_user(
            email="replay.reset@srilekh-sandbox.local",
            password=self.test_password,
            email_verified=True
        )

        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        new_pass = "FirstChangeSecurePass456!@#"

        # First use succeeds
        self.client.post("/api/v1/auth/password/reset/confirm/", {
            "uid": uid,
            "token": token,
            "new_password": new_pass,
        })

        # Replay with same token fails
        res_replay = self.client.post("/api/v1/auth/password/reset/confirm/", {
            "uid": uid,
            "token": token,
            "new_password": "SecondAttemptPass789!@#",
        })
        self.assertEqual(res_replay.status_code, 400)
        self.assertIn("Invalid or expired", res_replay.data["error"])


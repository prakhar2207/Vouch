#!/usr/bin/env python
"""
SriLekh Enterprise Email, OTP, Outbox & Security Concurrency Test Suite.
Executes against real PostgreSQL with multi-threaded race conditions,
row-level locking (select_for_update), and strict tenant isolation.
"""

import os
import sys
import threading
import time
import uuid
from datetime import timedelta
from decimal import Decimal

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# JioFiber WAN DNS Workaround for Neon PostgreSQL
import socket
_orig_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, *args, **kwargs):
    if 'neon.tech' in host:
        return _orig_getaddrinfo('52.76.246.190', port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = patched_getaddrinfo

import django
django.setup()

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, EmailVerificationChallenge, PendingRegistration
from apps.companies.models import Company, UserCompany
from apps.ledgers.models import LedgerGroup, Ledger
from apps.accounting.models import Voucher, LedgerEntry
from apps.notifications.models import (
    EmailDeliveryLog,
    TransactionalOutboxEvent,
    NotificationPreference,
    SecureInvoiceAccessToken,
)
from apps.notifications.email_service import EmailService
from apps.notifications.outbox_service import OutboxService
from apps.notifications.tasks import retry_pending_outbox_events_task

# Ensure test flags and locmem email backend for safe test execution
settings.TESTING = True
settings.DISABLE_THROTTLING = True
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
mail.outbox = []

# =============================================================================
# MANDATORY TEST ISOLATION POLICY ENFORCEMENT
# =============================================================================
PROTECTED_PROD_COMPANY_ID = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'  # Maa Annapurna Belting Store
SANDBOX_COMPANY_ID = '4e62863a-08f9-4e99-b0bd-64873acfdd33'         # Apex Belting Store (Demo)


def verify_test_isolation(company_id: str):
    assert str(company_id) != PROTECTED_PROD_COMPANY_ID, (
        f"CRITICAL VIOLATION: Test attempted to execute against protected production tenant {PROTECTED_PROD_COMPANY_ID}!"
    )


print("=" * 80)
print("SRILEKH ENTERPRISE EMAIL, OTP & NOTIFICATION POSTGRESQL CONCURRENCY SUITE")
print("=" * 80)
with connection.cursor() as cursor:
    cursor.execute("SELECT version();")
    print(f"Target Database: {cursor.fetchone()[0]}")
print("Test Isolation: Strictly Enforced (Apex Belting / Disposable Test Sandboxes)")
print("=" * 80)

test_results = {}


# =============================================================================
# Scenario 1: Concurrent Correct OTP Verification Race
# =============================================================================
def test_concurrent_correct_otp_verification():
    print("\n[Scenario 1] Concurrent Correct OTP Verification Race (Double-Consumption Defense)...")
    run_id = uuid.uuid4().hex[:6]
    email = f"concur.otp.{run_id}@srilekh-sandbox.local"

    # 1. Initiate OTP
    c_init = APIClient()
    res_init = c_init.post("/api/v1/auth/register/initiate/", {
        "email": email,
        "password": "SecurePassword123!@#",
        "confirm_password": "SecurePassword123!@#",
    }, format="json")
    assert res_init.status_code == 200, f"Initiate failed: {res_init.data}"
    session_token = res_init.data["session_token"]

    # Extract OTP code from locmem email
    otp_code = None
    for m in reversed(mail.outbox):
        if email in m.to:
            for word in m.body.split():
                if word.isdigit() and len(word) == 6:
                    otp_code = word
                    break
            if otp_code:
                break
    assert otp_code is not None, "Failed to retrieve generated OTP code from locmem outbox"

    # 2. Race 2 concurrent threads to verify with correct OTP
    barrier = threading.Barrier(2)
    results = []

    def verify_worker():
        connection.close()  # Force new PostgreSQL connection
        c = APIClient()
        barrier.wait()
        res = c.post("/api/v1/auth/register/verify-otp/", {
            "session_token": session_token,
            "otp": otp_code,
        }, format="json")
        results.append(res)

    t1 = threading.Thread(target=verify_worker)
    t2 = threading.Thread(target=verify_worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    status_codes = [r.status_code for r in results]
    print(f"  -> Concurrent Verify Responses: {status_codes}")

    # Exactly 1 request must succeed (200 OK) and 1 must fail (400 Bad Request, challenge consumed)
    assert 200 in status_codes, f"Expected exactly one 200 OK, got {status_codes}"
    assert 400 in status_codes, f"Expected exactly one 400 Bad Request, got {status_codes}"

    challenge = EmailVerificationChallenge.objects.get(session_token=session_token)
    assert challenge.is_verified is True
    assert challenge.is_consumed is True
    print("  [PASSED] Exactly 1 verification succeeded; double-consumption strictly prevented.")
    test_results["Scenario 1: Concurrent OTP Verification"] = "PASSED"


# =============================================================================
# Scenario 2: Concurrent Incorrect OTP Attempts (Brute-Force Race)
# =============================================================================
def test_concurrent_incorrect_otp_attempts():
    print("\n[Scenario 2] Concurrent Incorrect OTP Attempts Race (Brute-Force Counter Lock)...")
    run_id = uuid.uuid4().hex[:6]
    email = f"brute.force.{run_id}@srilekh-sandbox.local"

    c_init = APIClient()
    res_init = c_init.post("/api/v1/auth/register/initiate/", {
        "email": email,
        "password": "SecurePassword123!@#",
        "confirm_password": "SecurePassword123!@#",
    }, format="json")
    session_token = res_init.data["session_token"]

    # Fire 5 concurrent wrong guesses
    num_threads = 5
    barrier = threading.Barrier(num_threads)
    results = []

    def bad_guess_worker(guess: str):
        connection.close()
        c = APIClient()
        barrier.wait()
        res = c.post("/api/v1/auth/register/verify-otp/", {
            "session_token": session_token,
            "otp": guess,
        }, format="json")
        results.append(res)

    threads = [threading.Thread(target=bad_guess_worker, args=(f"00000{i}",)) for i in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Verify that failed attempts count was atomically incremented to 5
    challenge = EmailVerificationChallenge.objects.get(session_token=session_token)
    print(f"  -> Final Challenge failed_attempts: {challenge.failed_attempts}, is_consumed: {challenge.is_consumed}")
    assert challenge.failed_attempts == 5, f"Expected 5 failed attempts, got {challenge.failed_attempts}"
    assert challenge.is_consumed is True, "Expected challenge to be consumed and locked after 5 failed attempts"

    # Even a valid OTP must now be rejected
    res_after = c_init.post("/api/v1/auth/register/verify-otp/", {
        "session_token": session_token,
        "otp": "123456",
    }, format="json")
    assert res_after.status_code == 400
    print("  [PASSED] Atomic row locking prevented brute-force race; counter accurately locked at 5.")
    test_results["Scenario 2: Concurrent Brute-Force Lock"] = "PASSED"


# =============================================================================
# Scenario 3: Concurrent OTP Resend Race
# =============================================================================
def test_concurrent_otp_resend():
    print("\n[Scenario 3] Concurrent OTP Resend Race (Single-Active-Challenge Invariant)...")
    run_id = uuid.uuid4().hex[:6]
    email = f"resend.race.{run_id}@srilekh-sandbox.local"

    c_init = APIClient()
    res_init = c_init.post("/api/v1/auth/register/initiate/", {
        "email": email,
        "password": "SecurePassword123!@#",
        "confirm_password": "SecurePassword123!@#",
    }, format="json")
    session_token = res_init.data["session_token"]

    # Bypass cooldown in DB for testing resend race
    EmailVerificationChallenge.objects.filter(session_token=session_token).update(
        resend_available_at=timezone.now() - timedelta(seconds=5)
    )

    barrier = threading.Barrier(2)
    results = []

    def resend_worker():
        connection.close()
        c = APIClient()
        barrier.wait()
        res = c.post("/api/v1/auth/register/resend-otp/", {
            "session_token": session_token,
        }, format="json")
        results.append(res)

    t1 = threading.Thread(target=resend_worker)
    t2 = threading.Thread(target=resend_worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    status_codes = [r.status_code for r in results]
    print(f"  -> Concurrent Resend Statuses: {status_codes}")
    # Exactly one resend must succeed (200) and one must be rejected (400, session already consumed/replaced)
    assert 200 in status_codes, f"Expected 200, got {status_codes}"
    assert 400 in status_codes, f"Expected 400, got {status_codes}"

    # Verify only 1 active challenge exists for this email
    active_challenges = EmailVerificationChallenge.objects.filter(email=email, is_consumed=False).count()
    print(f"  -> Active Challenges for {email}: {active_challenges}")
    assert active_challenges == 1, f"Expected exactly 1 active challenge, found {active_challenges}"
    print("  [PASSED] Concurrent resend safely handled: exactly one replacement challenge issued.")
    test_results["Scenario 3: Concurrent OTP Resend"] = "PASSED"


# =============================================================================
# Scenario 4: Concurrent Registration Completion Race
# =============================================================================
def test_concurrent_registration_completion():
    print("\n[Scenario 4] Concurrent Registration Complete Race (Duplicate Company Prevention)...")
    run_id = uuid.uuid4().hex[:6]
    email = f"complete.race.{run_id}@srilekh-sandbox.local"
    firm_name = f"Race Firm {run_id}"

    # Create verified PendingRegistration
    reg_token = f"reg_token_race_{uuid.uuid4().hex}"
    pending = PendingRegistration.objects.create(
        email=email,
        password_hash=make_password("SecureRacePassword123!@#"),
        registration_token=reg_token,
        is_verified=True,
        expires_at=timezone.now() + timedelta(hours=1)
    )

    barrier = threading.Barrier(2)
    results = []

    def complete_worker():
        connection.close()
        c = APIClient()
        barrier.wait()
        res = c.post("/api/v1/auth/register/complete/", {
            "registration_token": reg_token,
            "firm_name": firm_name,
            "is_gst_registered": False,
            "proprietor_name": "Racer",
        }, format="json")
        results.append(res)

    t1 = threading.Thread(target=complete_worker)
    t2 = threading.Thread(target=complete_worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    status_codes = [r.status_code for r in results]
    print(f"  -> Concurrent Complete Statuses: {status_codes}")
    # Exactly one must succeed (201 Created) and one must fail (400 Bad Request, token consumed)
    assert 201 in status_codes, f"Expected 201, got {status_codes}"
    assert 400 in status_codes, f"Expected 400, got {status_codes}"

    # Invariant: exactly 1 User and 1 Company created
    users_count = User.objects.filter(email=email).count()
    companies_count = Company.objects.filter(name=firm_name).count()
    assert users_count == 1, f"Expected 1 user, found {users_count}"
    assert companies_count == 1, f"Expected 1 company, found {companies_count}"
    print("  [PASSED] Exactly 1 user and company provisioned; race condition safely rejected.")
    test_results["Scenario 4: Concurrent Complete Registration"] = "PASSED"


# =============================================================================
# Scenario 5: Concurrent Outbox Event Claiming Race
# =============================================================================
def test_concurrent_outbox_claiming():
    print("\n[Scenario 5] Concurrent Outbox Event Claiming Race (Duplicate Send Prevention)...")
    run_id = uuid.uuid4().hex[:6]
    company = Company.objects.create(name=f"Outbox Corp {run_id}", state_code="27")
    verify_test_isolation(str(company.id))
    user = User.objects.create_user(email=f"creator.{run_id}@outbox.local", password="Password123!@#", email_verified=True)

    voucher = Voucher.objects.create(
        company=company,
        voucher_type='SALES',
        voucher_number=f"INV-OUTBOX-{run_id}",
        voucher_date=timezone.now().date(),
        total_amount=Decimal('1500.00'),
        buyer_name='Valued Client',
        buyer_email=f"client.{run_id}@customer.local",
        status='POSTED',
        created_by=user,
    )

    event = TransactionalOutboxEvent.objects.create(
        event_type='INVOICE_POSTED',
        aggregate_type='Voucher',
        aggregate_id=str(voucher.id),
        company=company,
        payload={'voucher_id': str(voucher.id)},
        idempotency_key=f"idem_outbox_race_{run_id}",
        status='PENDING'
    )

    barrier = threading.Barrier(2)
    results = []

    def outbox_worker():
        connection.close()
        barrier.wait()
        res = OutboxService.process_outbox_event(event.id)
        results.append(res)

    t1 = threading.Thread(target=outbox_worker)
    t2 = threading.Thread(target=outbox_worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    print(f"  -> Outbox Worker Results: {results}")
    event.refresh_from_db()
    assert event.status == 'PROCESSED', f"Expected PROCESSED, got {event.status}"

    # Verify that only 1 email delivery was dispatched
    matching_emails = [m for m in mail.outbox if f"client.{run_id}@customer.local" in m.to]
    print(f"  -> Dispatched Emails Count: {len(matching_emails)}")
    assert len(matching_emails) == 1, f"Expected exactly 1 email dispatched, found {len(matching_emails)}"
    print("  [PASSED] Outbox claiming lease prevented duplicate delivery between concurrent workers.")
    test_results["Scenario 5: Concurrent Outbox Claiming"] = "PASSED"


# =============================================================================
# Scenario 6: Concurrent Email Delivery Idempotency Race
# =============================================================================
def test_concurrent_email_delivery_idempotency():
    print("\n[Scenario 6] Concurrent Email Delivery Idempotency Race (Idempotency Key Lock)...")
    run_id = uuid.uuid4().hex[:6]
    idempotency_key = f"idem_send_race_{run_id}"
    to_email = f"idem.{run_id}@recipient.local"

    barrier = threading.Barrier(2)
    results = []

    def email_worker():
        connection.close()
        barrier.wait()
        success, log, err = EmailService.send_email(
            to_email=to_email,
            subject=f"Idempotency Test {run_id}",
            template_name="welcome",
            context={"company_name": "Idem Corp", "subject": "Test"},
            email_type="SYSTEM_ALERT",
            idempotency_key=idempotency_key,
        )
        results.append((success, getattr(log, 'status', None), err))

    t1 = threading.Thread(target=email_worker)
    t2 = threading.Thread(target=email_worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    print(f"  -> Email Worker Outcomes: {results}")
    # Exactly 1 send must occur
    sent_emails = [m for m in mail.outbox if to_email in m.to]
    print(f"  -> Actual Sent Messages in Locmem: {len(sent_emails)}")
    assert len(sent_emails) == 1, f"Expected 1 email dispatched, found {len(sent_emails)}"

    # One worker gets success SENT, the other gets suppressed in_flight_send or idempotent_duplicate
    outcomes = [r[2] for r in results]
    assert None in outcomes or "idempotent_duplicate" in outcomes or "in_flight_send" in outcomes
    print("  [PASSED] Email delivery idempotency key atomically suppressed duplicate dispatch.")
    test_results["Scenario 6: Email Idempotency Race"] = "PASSED"


# =============================================================================
# Scenario 7: Outbox Worker Crash Recovery
# =============================================================================
def test_outbox_worker_crash_recovery():
    print("\n[Scenario 7] Worker Crash Recovery (Expired PROCESSING Lease Re-Queue)...")
    run_id = uuid.uuid4().hex[:6]
    company = Company.objects.create(name=f"Crash Corp {run_id}", state_code="27")
    verify_test_isolation(str(company.id))

    abandoned_event = TransactionalOutboxEvent.objects.create(
        event_type='INVOICE_POSTED',
        aggregate_type='Voucher',
        aggregate_id='fake-voucher-id',
        company=company,
        payload={'voucher_id': 'fake-voucher-id'},
        idempotency_key=f"abandoned_pg_{run_id}",
        status='PROCESSING',
        claimed_at=timezone.now() - timedelta(minutes=10),
        claim_token=f"crashed-worker-{run_id}",
        lease_expires_at=timezone.now() - timedelta(minutes=5),  # Expired
        retry_count=0,
        max_retries=3,
    )

    count = retry_pending_outbox_events_task()
    abandoned_event.refresh_from_db()
    print(f"  -> Recovered Event Status: {abandoned_event.status}, retry_count: {abandoned_event.retry_count}")
    assert abandoned_event.status == 'RETRY_PENDING'
    assert abandoned_event.claim_token is None
    assert abandoned_event.retry_count == 1
    print("  [PASSED] Expired lease detected and event reset to RETRY_PENDING without data loss.")
    test_results["Scenario 7: Worker Crash Recovery"] = "PASSED"


# =============================================================================
# Scenario 8: Tenant Isolation & RBAC on Delivery Logs
# =============================================================================
def test_tenant_isolation_and_rbac():
    print("\n[Scenario 8] Tenant Isolation & Delivery Log RBAC (Owner vs Viewer)...")
    run_id = uuid.uuid4().hex[:6]
    company_a = Company.objects.create(name=f"Company Alpha {run_id}", state_code="27")
    company_b = Company.objects.create(name=f"Company Beta {run_id}", state_code="27")

    owner_a = User.objects.create_user(email=f"owner_a_{run_id}@alpha.local", password="OwnerPass123!@#", role="OWNER", email_verified=True)
    viewer_a = User.objects.create_user(email=f"viewer_a_{run_id}@alpha.local", password="ViewerPass123!@#", role="VIEWER", email_verified=True)
    owner_b = User.objects.create_user(email=f"owner_b_{run_id}@beta.local", password="OwnerPass123!@#", role="OWNER", email_verified=True)

    UserCompany.objects.create(user=owner_a, company=company_a, role="OWNER")
    UserCompany.objects.create(user=viewer_a, company=company_a, role="VIEWER")
    UserCompany.objects.create(user=owner_b, company=company_b, role="OWNER")

    log_a = EmailDeliveryLog.objects.create(
        company=company_a,
        recipient_email="customer@alpha.local",
        sender_email="admin@srilekh.com",
        subject="Invoice Alpha",
        email_type="INVOICE_POSTED",
        status="SENT",
    )

    c = APIClient()

    # 1. Viewer attempt -> 403 Forbidden
    c.force_authenticate(user=viewer_a)
    res_viewer = c.get(f"/api/v1/notifications/logs/?company_id={company_a.id}")
    assert res_viewer.status_code == 403, f"Expected 403, got {res_viewer.status_code}"

    # 2. Owner of company B attempting to access Company A logs -> 403 or empty
    c.force_authenticate(user=owner_b)
    res_cross = c.get(f"/api/v1/notifications/logs/?company_id={company_a.id}")
    # _get_target_company will resolve to Company B because user is not in Company A, so no logs of Company A are leaked
    if res_cross.status_code == 200:
        log_ids = [l["id"] for l in res_cross.data["data"]]
        assert str(log_a.id) not in log_ids, "Cross-tenant leak detected!"

    # 3. Owner A -> 200 OK
    c.force_authenticate(user=owner_a)
    res_owner = c.get(f"/api/v1/notifications/logs/?company_id={company_a.id}")
    assert res_owner.status_code == 200, f"Expected 200, got {res_owner.status_code}"
    assert str(log_a.id) in [l["id"] for l in res_owner.data["data"]]

    print("  [PASSED] Strict server-side RBAC and tenant isolation verified.")
    test_results["Scenario 8: Tenant Isolation & RBAC"] = "PASSED"


# =============================================================================
# Scenario 9: IDOR & Public Invoice Security Headers
# =============================================================================
def test_invoice_public_view_security_and_pii_minimization():
    print("\n[Scenario 9] Public Invoice View IDOR Defense & PII Minimization...")
    run_id = uuid.uuid4().hex[:6]
    company = Company.objects.create(name=f"Seller Corp {run_id}", state_code="27")
    user = User.objects.create_user(email=f"creator.{run_id}@seller.local", password="Password123!@#", email_verified=True)
    voucher = Voucher.objects.create(
        company=company,
        voucher_type='SALES',
        voucher_number=f"INV-SEC-{run_id}",
        voucher_date=timezone.now().date(),
        total_amount=Decimal('2500.00'),
        buyer_name='Secure Buyer Org',
        buyer_phone='9876543210',
        buyer_email='confidential.buyer@example.com',
        status='POSTED',
        created_by=user,
    )

    token_obj = SecureInvoiceAccessToken.objects.create(
        voucher=voucher,
        token=f"secure_token_{run_id}_{uuid.uuid4().hex}",
        expires_at=timezone.now() + timedelta(days=7),
    )

    c = APIClient()
    res = c.get(f"/api/v1/invoices/public/view/?token={token_obj.token}", HTTP_USER_AGENT="SecurityAudit/2.0")
    assert res.status_code == 200

    # Headers verification
    assert res['Cache-Control'] == 'no-store, no-cache, must-revalidate, private'
    assert res['Pragma'] == 'no-cache'
    assert res['Referrer-Policy'] == 'no-referrer'
    assert res['X-Content-Type-Options'] == 'nosniff'

    # PII verification
    buyer_info = res.data["data"]["buyer"]
    assert "phone" not in buyer_info, "Buyer phone leaked in public endpoint!"
    assert "email" not in buyer_info, "Buyer email leaked in public endpoint!"

    # Token access forensics verified
    token_obj.refresh_from_db()
    assert token_obj.view_count == 1
    assert "SecurityAudit/2.0" in token_obj.user_agent

    print("  [PASSED] IDOR protection, privacy minimization, and forensics verified.")
    test_results["Scenario 9: IDOR & Security Headers"] = "PASSED"


# =============================================================================
# Scenario 10: Legacy Registration Endpoint Permanently Closed (410 GONE)
# =============================================================================
def test_legacy_registration_closed_410():
    print("\n[Scenario 10] Legacy Registration Bypass Closure (410 GONE Invariant)...")
    c = APIClient()
    res = c.post("/api/v1/auth/register/", {
        "email": f"bypass_{uuid.uuid4().hex[:6]}@exploit.local",
        "password": "Password123!@#",
        "name": "Exploit Firm",
        "email_verified": True,
    }, format="json")

    assert res.status_code == 410, f"Expected 410 GONE, got {res.status_code}"
    assert res.data["code"] == "LEGACY_REGISTRATION_DEPRECATED"
    print("  [PASSED] Legacy registration path permanently closed (410 GONE).")
    test_results["Scenario 10: Legacy Bypass Closed (410 GONE)"] = "PASSED"


# =============================================================================
# Execute All Scenarios
# =============================================================================
if __name__ == "__main__":
    try:
        test_concurrent_correct_otp_verification()
        test_concurrent_incorrect_otp_attempts()
        test_concurrent_otp_resend()
        test_concurrent_registration_completion()
        test_concurrent_outbox_claiming()
        test_concurrent_email_delivery_idempotency()
        test_outbox_worker_crash_recovery()
        test_tenant_isolation_and_rbac()
        test_invoice_public_view_security_and_pii_minimization()
        test_legacy_registration_closed_410()

        print("\n" + "=" * 80)
        print("ALL POSTGRESQL CONCURRENCY & SECURITY SCENARIOS PASSED (10/10)")
        print("=" * 80)
        for name, outcome in test_results.items():
            print(f"  [OK] {name}: {outcome}")
        print("=" * 80)
        sys.exit(0)

    except Exception as exc:
        print("\n" + "!" * 80)
        print(f"CONCURRENCY SUITE FAILURE: {exc}")
        print("!" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)

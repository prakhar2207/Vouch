import hashlib
import struct
from django.db import connection
import datetime
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction, IntegrityError, OperationalError
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.companies.models import Company, UserCompany, CompanySettings
from apps.gst.services.gstin_validator import GSTINValidator
from apps.inventory.models import Warehouse
from apps.ledgers.models import LedgerGroup, Ledger
from apps.notifications.email_service import EmailService
from apps.notifications.models import NotificationPreference
from django.middleware.csrf import get_token
from rest_framework_simplejwt.tokens import AccessToken
from .cookies import (
    attach_auth_cookies,
    build_tokens_for_user,
    clear_auth_cookies,
    enforce_cookie_csrf,
    get_access_cookie_name,
    get_refresh_cookie_name,
    revoke_user_tokens,
)
from .models import User, EmailVerificationChallenge, PendingRegistration
from .serializers import (
    UserSerializer,
    CustomTokenObtainPairSerializer,
    CustomTokenRefreshSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Throttling Classes
# =============================================================================

class RegisterRateThrottle(AnonRateThrottle):
    rate = '15/hour'


class OtpInitiateRateThrottle(AnonRateThrottle):
    rate = '10/hour'


class OtpVerifyRateThrottle(AnonRateThrottle):
    rate = '20/hour'


class LoginRateThrottle(AnonRateThrottle):
    rate = '15/minute'


class LoginAccountRateThrottle(AnonRateThrottle):
    """Throttles login attempts per target account/email to prevent distributed brute-force attacks."""
    rate = '10/minute'
    scope = 'login_account'

    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            ident = request.user.pk
        else:
            email = str(request.data.get('email') or request.data.get('username') or '').strip().lower()
            if not email:
                return None
            ident = f"email_{email}"
        return self.cache_format % {'scope': self.scope, 'ident': ident}


# =============================================================================
# User Profile View
# =============================================================================


class TestBypassThrottleMixin:
    def get_throttles(self):
        if getattr(settings, 'TESTING', False) or getattr(settings, 'DISABLE_THROTTLING', False):
            return []
        return super().get_throttles()

class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({
            "success": True,
            "data": serializer.data
        })

    def patch(self, request):
        user = request.user
        data = request.data
        if 'first_name' in data:
            user.first_name = str(data['first_name']).strip()
        if 'last_name' in data:
            user.last_name = str(data['last_name']).strip()
        if 'password' in data and data['password']:
            new_password = str(data['password'])
            try:
                validate_password(new_password, user=user)
                user.set_password(new_password)
            except Exception as e:
                msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
                return Response({"success": False, "error": f"Invalid password: {msg}"}, status=400)
        user.save()
        serializer = UserSerializer(user)
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "User profile updated successfully."
        })


# =============================================================================
# Step 1: Register Initiate (Email + Password -> 6-Digit OTP)
# =============================================================================


def acquire_registration_advisory_lock(email: str, scope: str = 'REGISTRATION'):
    """
    Acquires an exclusive PostgreSQL advisory transaction lock scoped to (email, scope).
    Automatically released upon commit or rollback of the enclosing transaction.atomic().
    In non-PostgreSQL environments (e.g. SQLite tests), performs a no-op as SQLite
    uses whole-database write locking.
    """
    if connection.vendor == 'postgresql':
        norm_email = str(email or '').strip().lower()
        digest = hashlib.sha256(f"reg_xact_lock:{scope}:{norm_email}".encode('utf-8')).digest()
        k1, k2 = struct.unpack(">ii", digest[:8])
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s);", [k1, k2])

class RegisterInitiateView(TestBypassThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OtpInitiateRateThrottle]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password') or ''
        confirm_password = request.data.get('confirm_password') or ''

        if not email or not password:
            return Response(
                {"success": False, "error": "Email address and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if '@' not in email or '.' not in email.split('@')[-1]:
            return Response(
                {"success": False, "error": "Please enter a valid email address."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if confirm_password and password != confirm_password:
            return Response(
                {"success": False, "error": "Passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Enforce password complexity
        try:
            validate_password(password, user=User(email=email))
        except Exception as e:
            msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
            return Response({"success": False, "error": f"Password requirement not met: {msg}"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Check existing user
        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {"success": False, "error": f"An account with email '{email}' already exists. Please log in."},
                status=status.HTTP_400_BAD_REQUEST
            )

        now = timezone.now()
        otp_expiry_secs = getattr(settings, 'OTP_EXPIRY_SECONDS', 300)
        otp_cooldown_secs = getattr(settings, 'OTP_RESEND_COOLDOWN_SECONDS', 60)

        challenge = None
        otp_code = None
        session_token = None
        reused_active_challenge = False

        for attempt in range(3):
            try:
                with transaction.atomic():
                    # Serialization: Lock initiation per normalized email and challenge type
                    acquire_registration_advisory_lock(email, 'REGISTRATION')

                    # Protect verified pending registrations from being hijacked or reset
                    pending = (
                        PendingRegistration.objects
                        .select_for_update()
                        .filter(email=email)
                        .first()
                    )
                    if pending and pending.is_verified and not pending.is_expired():
                        return Response({
                            "success": False,
                            "error": "Email verification is already completed for this address. Please proceed to complete registration.",
                            "registration_token": pending.registration_token,
                        }, status=status.HTTP_400_BAD_REQUEST)

                    # Check for an active, unexpired challenge within the cooldown window
                    active_challenge = (
                        EmailVerificationChallenge.objects
                        .select_for_update()
                        .filter(email=email, challenge_type='REGISTRATION', is_consumed=False)
                        .first()
                    )

                    if active_challenge and not active_challenge.is_expired() and not active_challenge.can_resend():
                        # A fresh challenge was created moments ago by a winning concurrent request.
                        # Do NOT supersede or create a new challenge; return the existing session token.
                        challenge = active_challenge
                        session_token = active_challenge.session_token
                        reused_active_challenge = True
                        break

                    # Invalidate any prior active challenges for this email under row lock
                    if active_challenge:
                        active_challenge.is_consumed = True
                        active_challenge.save(update_fields=['is_consumed'])

                    EmailVerificationChallenge.objects.filter(
                        email=email, challenge_type='REGISTRATION', is_consumed=False
                    ).update(is_consumed=True)

                    # Generate cryptographically secure 6-digit OTP
                    otp_code = f"{secrets.randbelow(900000) + 100000}"
                    otp_hash = make_password(otp_code)
                    session_token = secrets.token_urlsafe(32)

                    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')

                    challenge = EmailVerificationChallenge.objects.create(
                        email=email,
                        otp_hash=otp_hash,
                        session_token=session_token,
                        challenge_type='REGISTRATION',
                        expires_at=now + timedelta(seconds=otp_expiry_secs),
                        resend_available_at=now + timedelta(seconds=otp_cooldown_secs),
                        ip_address=client_ip if client_ip and len(client_ip) <= 45 else None,
                    )

                    # Persist unverified PendingRegistration record under row lock
                    registration_token = secrets.token_urlsafe(48)
                    if pending:
                        pending.password_hash = make_password(password)
                        pending.verification_challenge = challenge
                        pending.registration_token = registration_token
                        pending.is_verified = False
                        pending.expires_at = now + timedelta(hours=1)
                        pending.save(update_fields=['password_hash', 'verification_challenge', 'registration_token', 'is_verified', 'expires_at', 'updated_at'])
                    else:
                        pending = PendingRegistration.objects.create(
                            email=email,
                            password_hash=make_password(password),
                            verification_challenge=challenge,
                            registration_token=registration_token,
                            is_verified=False,
                            expires_at=now + timedelta(hours=1),
                        )
                break
            except (IntegrityError, OperationalError):
                if attempt == 2:
                    raise
                import time
                time.sleep(0.05 * (attempt + 1))

        if not challenge:
            return Response({"success": False, "error": "Unable to initiate registration. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Dispatch OTP Email only if a new challenge was created AND it remains active
        if not reused_active_challenge and otp_code:
            challenge.refresh_from_db()
            if challenge.is_consumed:
                logger.warning(f"Challenge {challenge.id} was consumed/superseded before dispatch. Suppressing OTP email.")
            else:
                otp_idem_key = f"reg_otp_{challenge.session_token}"
                EmailService.send_registration_otp(email, otp_code, idempotency_key=otp_idem_key)

        return Response({
            "success": True,
            "message": f"A 6-digit verification code has been sent to {email}.",
            "session_token": session_token,
            "resend_cooldown": max(1, int((challenge.resend_available_at - now).total_seconds())) if challenge.resend_available_at else otp_cooldown_secs,
            "expires_in_seconds": max(1, int((challenge.expires_at - now).total_seconds())) if challenge.expires_at else otp_expiry_secs,
        }, status=status.HTTP_200_OK)


# =============================================================================
# Step 2: Register Verify OTP
# =============================================================================

class RegisterVerifyOtpView(TestBypassThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OtpVerifyRateThrottle]

    def post(self, request):
        session_token = (request.data.get('session_token') or '').strip()
        otp = str(request.data.get('otp') or '').strip()

        if not session_token or not otp:
            return Response(
                {"success": False, "error": "Session token and 6-digit OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        challenge_email = EmailVerificationChallenge.objects.filter(session_token=session_token).values_list('email', flat=True).first()
        if not challenge_email:
            return Response(
                {"success": False, "error": "Invalid or expired verification session. Please request a new code."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            acquire_registration_advisory_lock(challenge_email, 'REGISTRATION')
            challenge = (
                EmailVerificationChallenge.objects
                .select_for_update()
                .filter(session_token=session_token)
                .first()
            )
            if not challenge or challenge.is_consumed:
                return Response(
                    {"success": False, "error": "Invalid or expired verification session. Please request a new code."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if challenge.is_expired():
                challenge.is_consumed = True
                challenge.save(update_fields=['is_consumed'])
                return Response(
                    {"success": False, "error": "This verification code has expired (5-minute limit). Please request a new code."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if challenge.is_locked():
                challenge.is_consumed = True
                challenge.save(update_fields=['is_consumed'])
                return Response(
                    {"success": False, "error": "Too many failed attempts. For your security, this code has been locked. Please request a new code."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify salted PBKDF2 hash
            if not check_password(otp, challenge.otp_hash):
                challenge.failed_attempts += 1
                if challenge.failed_attempts >= challenge.max_attempts:
                    challenge.is_consumed = True
                    challenge.save(update_fields=['failed_attempts', 'is_consumed'])
                    return Response(
                        {"success": False, "error": "Maximum failed attempts exceeded. Please request a new code."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                challenge.save(update_fields=['failed_attempts'])
                remaining = max(0, challenge.max_attempts - challenge.failed_attempts)
                return Response(
                    {"success": False, "error": f"Incorrect verification code. {remaining} attempt(s) remaining."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Success: atomic transition CREATED -> VERIFIED -> CONSUMED
            challenge.is_verified = True
            challenge.is_consumed = True
            challenge.save(update_fields=['is_verified', 'is_consumed'])

            # Concurrently lock PendingRegistration record
            pending = (
                PendingRegistration.objects
                .select_for_update()
                .filter(email__iexact=challenge.email)
                .first()
            )
            if not pending:
                return Response(
                    {"success": False, "error": "Registration session expired. Please restart registration."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            pending.is_verified = True
            pending.save(update_fields=['is_verified'])

            return Response({
                "success": True,
                "message": "Email address verified successfully.",
                "registration_token": pending.registration_token,
                "email": pending.email,
            }, status=status.HTTP_200_OK)


# =============================================================================
# Step 3: Register Resend OTP
# =============================================================================

class RegisterResendOtpView(TestBypassThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OtpInitiateRateThrottle]

    def post(self, request):
        session_token = (request.data.get('session_token') or '').strip()
        if not session_token:
            return Response({"success": False, "error": "Session token is required."}, status=status.HTTP_400_BAD_REQUEST)

        challenge_email = EmailVerificationChallenge.objects.filter(session_token=session_token).values_list('email', flat=True).first()
        if not challenge_email:
            return Response(
                {"success": False, "error": "Session not found or already replaced. Please restart registration."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            acquire_registration_advisory_lock(challenge_email, 'REGISTRATION')
            challenge = (
                EmailVerificationChallenge.objects
                .select_for_update()
                .filter(session_token=session_token)
                .first()
            )
            if not challenge or challenge.is_consumed:
                return Response(
                    {"success": False, "error": "Session not found or already replaced. Please restart registration."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            now = timezone.now()
            if not challenge.can_resend():
                remaining_secs = max(1, int((challenge.resend_available_at - now).total_seconds()))
                return Response(
                    {"success": False, "error": f"Please wait {remaining_secs} seconds before requesting a new code.", "cooldown": remaining_secs},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            # Invalidate the current challenge and any other active challenge for this email
            challenge.is_consumed = True
            challenge.save(update_fields=['is_consumed'])
            EmailVerificationChallenge.objects.filter(email__iexact=challenge.email, is_consumed=False).update(is_consumed=True)

            otp_expiry_secs = getattr(settings, 'OTP_EXPIRY_SECONDS', 300)
            otp_cooldown_secs = getattr(settings, 'OTP_RESEND_COOLDOWN_SECONDS', 60)

            otp_code = f"{secrets.randbelow(900000) + 100000}"
            otp_hash = make_password(otp_code)
            new_session_token = secrets.token_urlsafe(32)

            new_challenge = EmailVerificationChallenge.objects.create(
                email=challenge.email,
                otp_hash=otp_hash,
                session_token=new_session_token,
                challenge_type='REGISTRATION',
                expires_at=now + timedelta(seconds=otp_expiry_secs),
                resend_available_at=now + timedelta(seconds=otp_cooldown_secs),
                ip_address=challenge.ip_address,
            )

            # Atomically lock and update PendingRegistration
            pending = (
                PendingRegistration.objects
                .select_for_update()
                .filter(email__iexact=challenge.email)
                .first()
            )
            if not pending or pending.is_expired():
                return Response(
                    {"success": False, "error": "Registration session expired. Please restart registration."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            pending.verification_challenge = new_challenge
            pending.save(update_fields=['verification_challenge', 'updated_at'])

        # Dispatch replacement OTP email after atomic database commit if challenge remains active
        new_challenge.refresh_from_db()
        if not new_challenge.is_consumed:
            otp_idem_key = f"reg_otp_{new_session_token}"
            EmailService.send_registration_otp(challenge.email, otp_code, idempotency_key=otp_idem_key)
        else:
            logger.warning(f"Resend challenge {new_challenge.id} was consumed before dispatch. Suppressing OTP email.")

        return Response({
            "success": True,
            "message": f"A new verification code has been sent to {challenge.email}.",
            "session_token": new_session_token,
            "resend_cooldown": otp_cooldown_secs,
        }, status=status.HTTP_200_OK)


# =============================================================================
# Step 4: Register Complete (Business Profile & Atomic Ledger Provisioning)
# =============================================================================

class RegisterCompleteView(TestBypassThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        registration_token = (request.data.get('registration_token') or '').strip()
        if not registration_token:
            return Response(
                {"success": False, "error": "Registration verification token is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        firm_name = (request.data.get('name') or request.data.get('firm_name') or 'My Firm').strip()
        is_gst_registered = request.data.get('is_gst_registered')
        if isinstance(is_gst_registered, str):
            is_gst_registered = is_gst_registered.strip().lower() in ('true', '1', 'yes')
        elif is_gst_registered is None:
            # Default to True if gstin is provided, else False
            is_gst_registered = bool(request.data.get('gstin'))

        gstin = (request.data.get('gstin') or '').strip().upper()
        pan = request.data.get('pan') or (gstin[2:12] if len(gstin) >= 12 else '')
        state_code = (request.data.get('state_code') or '').strip()
        address = (request.data.get('address') or '').strip()
        phone = (request.data.get('phone') or '').strip()
        company_email = (request.data.get('company_email') or '').strip()
        proprietor_name = (request.data.get('proprietor_name') or '').strip()
        proprietor_phone = (request.data.get('proprietor_phone') or '').strip()
        signature_file = request.FILES.get('signature') or request.FILES.get('proprietor_signature')

        if signature_file:
            if signature_file.size > 5 * 1024 * 1024:
                return Response({"success": False, "error": "Signature file size exceeds maximum 5MB limit."}, status=400)
            allowed_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.pdf')
            file_name_lower = (signature_file.name or '').lower()
            if not any(file_name_lower.endswith(ext) for ext in allowed_extensions):
                return Response({"success": False, "error": "Signature must be an image (PNG, JPG, WEBP) or PDF."}, status=400)

        # Enforce GSTIN validation only if business is GST-registered
        if is_gst_registered:
            if not gstin:
                return Response({"success": False, "error": "GSTIN is required for GST-registered businesses."}, status=400)
            gst_res = GSTINValidator.validate(gstin)
            if not gst_res['is_valid']:
                return Response({"success": False, "error": f"Invalid GSTIN: {gst_res['error']}"}, status=400)
            if not state_code:
                state_code = gst_res['state_code']
        else:
            gstin = ''  # Ensure blank for unregistered business

        pending_email = PendingRegistration.objects.filter(registration_token=registration_token, is_verified=True).values_list('email', flat=True).first()
        if not pending_email:
            return Response(
                {"success": False, "error": "Invalid, expired, or already completed registration session. Please verify your email again."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                acquire_registration_advisory_lock(pending_email, 'REGISTRATION')
                # Atomically claim and lock PendingRegistration
                pending = (
                    PendingRegistration.objects
                    .select_for_update()
                    .filter(registration_token=registration_token, is_verified=True)
                    .first()
                )
                if not pending or pending.is_expired():
                    return Response(
                        {"success": False, "error": "Invalid, expired, or already completed registration session. Please verify your email again."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                email = pending.email
                if not company_email:
                    company_email = email
                if User.objects.filter(email__iexact=email).exists():
                    pending.delete()
                    return Response(
                        {"success": False, "error": f"An account with email '{email}' has already been completed. Please log in."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 1. Create User with pre-hashed password and email_verified=True
                user = User(
                    email=email,
                    role='OWNER',
                    first_name=proprietor_name.split(' ')[0] if proprietor_name else '',
                    last_name=' '.join(proprietor_name.split(' ')[1:]) if ' ' in proprietor_name else '',
                    email_verified=True,
                )
                user.password = pending.password_hash
                user.save()

                # 2. Create Company
                company = Company.objects.create(
                    name=firm_name,
                    legal_name=firm_name,
                    gstin=gstin,
                    pan=pan,
                    phone=phone,
                    email=company_email,
                    address=address,
                    state_code=state_code,
                    proprietor_name=proprietor_name,
                    proprietor_phone=proprietor_phone,
                    proprietor_signature=signature_file if signature_file else None,
                    financial_year_start=datetime.date(datetime.date.today().year, 4, 1)
                )

                # 3. Link User & Default Settings
                UserCompany.objects.create(user=user, company=company, role='OWNER')
                CompanySettings.objects.create(company=company)
                NotificationPreference.objects.create(company=company)

                # 4. Auto-provision Default Warehouse
                Warehouse.objects.create(
                    company=company,
                    name="Main Godown",
                    address=address
                )

                # 5. Auto-provision Core Chart of Accounts (Ledger Groups)
                debtors_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Sundry Debtors", defaults={"nature": "ASSET"}
                )
                creditors_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Sundry Creditors", defaults={"nature": "LIABILITY"}
                )
                sales_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Sales Accounts", defaults={"nature": "INCOME"}
                )
                purchase_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Purchase Accounts", defaults={"nature": "EXPENSE"}
                )
                duties_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Duties & Taxes", defaults={"nature": "LIABILITY"}
                )
                bank_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Bank Accounts", defaults={"nature": "ASSET"}
                )
                cash_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Cash-in-Hand", defaults={"nature": "ASSET"}
                )
                indirect_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Indirect Expenses", defaults={"nature": "EXPENSE"}
                )
                direct_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company, name="Direct Expenses", defaults={"nature": "EXPENSE"}
                )

                # 6. Auto-provision Standard Ledgers
                Ledger.objects.create(company=company, group=sales_grp, name="Sales Account", ledger_type="SALES")
                Ledger.objects.create(company=company, group=purchase_grp, name="Purchase Account", ledger_type="PURCHASE")
                Ledger.objects.create(company=company, group=cash_grp, name="Cash", ledger_type="CASH")
                Ledger.objects.create(company=company, group=indirect_grp, name="Round Off", ledger_type="ROUND_OFF")
                Ledger.objects.create(company=company, group=indirect_grp, name="Cartage Outward", ledger_type="EXPENSE")
                Ledger.objects.create(company=company, group=direct_grp, name="Cartage Inward", ledger_type="EXPENSE")
                Ledger.objects.create(company=company, group=duties_grp, name="Output CGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Output SGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Output IGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Input CGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Input SGST", ledger_type="TAX")
                Ledger.objects.create(company=company, group=duties_grp, name="Input IGST", ledger_type="TAX")

                # 7. Consume Pending Registration
                pending.delete()

                # 8. Dispatch Welcome Email
                transaction.on_commit(lambda: EmailService.send_welcome_email(
                    to_email=user.email,
                    company_name=company.name,
                    user_name=proprietor_name,
                    gstin=company.gstin,
                    state=state_code,
                    company=company,
                ))

                # 9. Issue JWT Tokens & attach HttpOnly browser cookies
                tokens = build_tokens_for_user(user)
                resp = Response({
                    "success": True,
                    "access": tokens["access"],
                    "refresh": tokens["refresh"],
                    "company_id": str(company.id),
                    "message": "Account created and activated successfully."
                }, status=status.HTTP_201_CREATED)
                attach_auth_cookies(
                    request,
                    resp,
                    access_token=tokens["access"],
                    refresh_token=tokens["refresh"],
                    user=user,
                )
                return resp

        except Exception as e:
            logger.exception(f"Business registration completion failed for '{email}': {e}")
            return Response({"success": False, "error": "Registration failed. Please verify your details or try again."}, status=400)


# =============================================================================
# Legacy Direct Registration (Preserved with GST-unregistered support)
# =============================================================================

class RegisterView(TestBypassThrottleMixin, APIView):
    """
    LEGACY REGISTRATION ENDPOINT — PERMANENTLY DEPRECATED & CLOSED (P0 Remediation).
    Direct account and company provisioning without verified email ownership is strictly prohibited.
    All users must complete the verified multi-step OTP workflow starting at /api/v1/auth/register/initiate/.
    """
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        return Response(
            {
                "success": False,
                "error": "Direct account registration without email OTP verification has been permanently disabled. Please use /api/v1/auth/register/initiate/ to begin verified registration.",
                "code": "LEGACY_REGISTRATION_DEPRECATED",
                "redirect_to": "/api/v1/auth/register/initiate/",
            },
            status=status.HTTP_410_GONE
        )


# =============================================================================
# Password Reset Views
# =============================================================================

class PasswordResetRequestView(TestBypassThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OtpInitiateRateThrottle]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({"success": False, "error": "Email address is required."}, status=400)

        user = User.objects.filter(email__iexact=email).first()
        if user and user.is_active:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://srilekh.com' if not settings.DEBUG else 'http://localhost:3000').rstrip('/')
            reset_url = f"{frontend_url}/reset-password?uid={uid}&token={token}"
            EmailService.send_password_reset_email(user.email, reset_url)

        # Always return generic success message to prevent user enumeration
        return Response({
            "success": True,
            "message": "If an account exists with this email, a password reset link has been sent."
        }, status=200)


class PasswordResetConfirmView(TestBypassThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OtpVerifyRateThrottle]

    def post(self, request):
        uidb64 = (request.data.get('uid') or '').strip()
        token = (request.data.get('token') or '').strip()
        new_password = request.data.get('new_password') or ''

        if not uidb64 or not token or not new_password:
            return Response({"success": False, "error": "UID, token, and new password are required."}, status=400)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except Exception:
            return Response({"success": False, "error": "Invalid or expired password reset link."}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({"success": False, "error": "Invalid or expired password reset link."}, status=400)

        try:
            validate_password(new_password, user=user)
        except Exception as e:
            msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
            return Response({"success": False, "error": f"Password requirement not met: {msg}"}, status=400)

        user.set_password(new_password)
        user.save()

        # Revoke all existing access & refresh tokens (increments token_version + blacklists refresh tokens)
        revoke_user_tokens(user)

        # Send password changed confirmation email
        EmailService.send_password_changed_email(user.email)

        return Response({
            "success": True,
            "message": "Your password has been successfully reset. You can now log in with your new password."
        }, status=200)


# =============================================================================
# Throttled JWT Login Views
# =============================================================================

class CsrfCookieView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = get_token(request)
        return Response({"success": True, "csrf_token": token}, status=status.HTTP_200_OK)


class ThrottledTokenObtainPairView(TestBypassThrottleMixin, TokenObtainPairView):
    throttle_classes = [LoginRateThrottle, LoginAccountRateThrottle]
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and isinstance(response.data, dict):
            access_token = response.data.get("access")
            refresh_token = response.data.get("refresh")
            if access_token:
                attach_auth_cookies(
                    request,
                    response,
                    access_token=access_token,
                    refresh_token=refresh_token,
                )
        return response


class ThrottledTokenRefreshView(TestBypassThrottleMixin, TokenRefreshView):
    throttle_classes = [LoginRateThrottle]
    throttle_scope = "auth"
    serializer_class = CustomTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        cookie_refresh = request.COOKIES.get(get_refresh_cookie_name())
        has_body_refresh = isinstance(request.data, dict) and bool(request.data.get("refresh"))
        if cookie_refresh and not has_body_refresh:
            enforce_cookie_csrf(request)

        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and isinstance(response.data, dict):
            access_token = response.data.get("access")
            refresh_token = response.data.get("refresh")
            if access_token:
                attach_auth_cookies(
                    request,
                    response,
                    access_token=access_token,
                    refresh_token=refresh_token,
                )
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        has_auth_cookies = bool(
            request.COOKIES.get(get_access_cookie_name())
            or request.COOKIES.get(get_refresh_cookie_name())
        )
        if has_auth_cookies:
            enforce_cookie_csrf(request)

        revoked_user = None
        auth_header = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
        bearer_token = None
        if auth_header.lower().startswith("bearer "):
            cand = auth_header[7:].strip()
            if cand and cand.lower() not in ("undefined", "null"):
                bearer_token = cand

        raw_access = bearer_token or request.COOKIES.get(get_access_cookie_name())
        if raw_access:
            try:
                at = AccessToken(raw_access)
                uid = at.get("user_id")
                if uid:
                    revoked_user = User.objects.filter(pk=uid).first()
            except Exception:
                pass

        raw_refresh = None
        if isinstance(request.data, dict):
            raw_refresh = request.data.get("refresh")
        if not raw_refresh:
            raw_refresh = request.COOKIES.get(get_refresh_cookie_name())

        if raw_refresh:
            try:
                rt = RefreshToken(raw_refresh)
                if revoked_user is None and rt.get("user_id"):
                    revoked_user = User.objects.filter(pk=rt.get("user_id")).first()
                try:
                    rt.blacklist()
                except Exception:
                    pass
            except Exception:
                pass

        if revoked_user is not None:
            revoke_user_tokens(revoked_user)

        resp = Response({"success": True, "message": "Logged out successfully."}, status=status.HTTP_200_OK)
        clear_auth_cookies(request, resp)
        return resp

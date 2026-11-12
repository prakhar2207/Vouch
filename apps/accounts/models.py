import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('email_verified', True)

        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('OWNER', 'Owner'),
        ('CA', 'Chartered Accountant'),
        ('EMPLOYEE', 'Employee'),
        ('VIEWER', 'Viewer'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='VIEWER')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False, db_index=True)
    token_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class EmailVerificationChallenge(models.Model):
    """
    Cryptographic challenge for email verification and OTP authentication.
    OTPs are stored strictly as salted PBKDF2/Argon2 hashes, never in plaintext.
    """
    CHALLENGE_TYPE_CHOICES = (
        ('REGISTRATION', 'Registration'),
        ('PASSWORD_RESET', 'Password Reset'),
        ('EMAIL_CHANGE', 'Email Change'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    otp_hash = models.CharField(max_length=255)
    session_token = models.CharField(max_length=128, unique=True, db_index=True)
    challenge_type = models.CharField(max_length=30, choices=CHALLENGE_TYPE_CHOICES, default='REGISTRATION', db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    resend_available_at = models.DateTimeField(db_index=True)
    is_verified = models.BooleanField(default=False)
    is_consumed = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_verified', 'is_consumed']),
            models.Index(fields=['session_token', 'is_consumed']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['email', 'challenge_type'],
                condition=models.Q(is_consumed=False),
                name='unique_active_challenge_per_email_and_type'
            )
        ]

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_locked(self):
        return self.failed_attempts >= self.max_attempts

    def can_resend(self):
        return timezone.now() >= self.resend_available_at

    def __str__(self):
        return f"OTP Challenge ({self.challenge_type}) for {self.email} [Verified: {self.is_verified}]"


class PendingRegistration(models.Model):
    """
    Durable, isolated record for unverified user registrations.
    Prevents unverified users from cluttering permanent User, Company, or Ledger tables.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    password_hash = models.CharField(max_length=255)
    verification_challenge = models.ForeignKey(
        EmailVerificationChallenge, on_delete=models.SET_NULL, null=True, blank=True, related_name='pending_registrations'
    )
    registration_token = models.CharField(max_length=128, unique=True, db_index=True)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Pending Registration: {self.email} [Verified: {self.is_verified}]"


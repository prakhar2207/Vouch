import uuid
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
from apps.companies.models import Company


class PushSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=100)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'endpoint')


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']


class EmailDeliveryLog(models.Model):
    """
    Durable, audit-ready log for all transactional email deliveries across SriLekh.
    Stores delivery status, attempts, provider message IDs, and error forensics without leaking credentials.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('SKIPPED', 'Skipped'),
    )
    EMAIL_TYPE_CHOICES = (
        ('REGISTRATION_OTP', 'Registration OTP'),
        ('WELCOME', 'Welcome & Onboarding'),
        ('PASSWORD_RESET', 'Password Reset'),
        ('PASSWORD_CHANGED', 'Password Changed'),
        ('INVOICE_POSTED', 'Invoice Posted'),
        ('INVOICE_REVISED', 'Invoice Revised'),
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('CREDIT_NOTE_ISSUED', 'Credit Note Issued'),
        ('SYSTEM_ALERT', 'System Alert'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_logs')
    recipient_email = models.EmailField(db_index=True)
    sender_email = models.EmailField(default='admin@srilekh.com')
    subject = models.CharField(max_length=255)
    email_type = models.CharField(max_length=50, choices=EMAIL_TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    provider_name = models.CharField(max_length=50, default='SMTP')
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'email_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.email_type} to {self.recipient_email} [{self.status}]"


class TransactionalOutboxEvent(models.Model):
    """
    Transactional Outbox pattern implementation for business events (e.g. Invoice Posting).
    Guarantees that database commits and notification dispatches remain strictly decoupled
    and resilient against worker crashes or network interruptions.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('PROCESSED', 'Processed'),
        ('FAILED', 'Failed'),
        ('DEAD_LETTER', 'Dead Letter'),
        ('SKIPPED', 'Skipped'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=50, db_index=True)
    aggregate_type = models.CharField(max_length=50, default='Voucher')
    aggregate_id = models.CharField(max_length=100, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='outbox_events')
    payload = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error_log = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['company', 'event_type', 'status']),
        ]

    def __str__(self):
        return f"OutboxEvent {self.event_type} for {self.aggregate_id} [{self.status}]"


class NotificationPreference(models.Model):
    """
    Company-level configuration governing automatic transactional notification dispatches.
    Empowers business owners to toggle invoice emails, payment receipts, and PDF attachments.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='notification_preferences')
    send_invoice_email_on_post = models.BooleanField(default=True)
    attach_invoice_pdf = models.BooleanField(default=True)
    send_payment_receipt_email = models.BooleanField(default=True)
    send_credit_note_email = models.BooleanField(default=True)
    send_revised_invoice_email = models.BooleanField(default=True)
    send_overdue_reminder_email = models.BooleanField(default=False)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification Preferences for {self.company.name}"


class SecureInvoiceAccessToken(models.Model):
    """
    Cryptographically secure, time-limited access tokens for customer invoice viewing and download.
    Mitigates IDOR vulnerabilities by eliminating predictable primary-key URL parameters.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey('accounting.Voucher', on_delete=models.CASCADE, related_name='access_tokens')
    token = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_revoked = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        return not self.is_revoked and timezone.now() <= self.expires_at

    def __str__(self):
        return f"AccessToken for Voucher {self.voucher.voucher_number} [Valid: {self.is_valid()}]"

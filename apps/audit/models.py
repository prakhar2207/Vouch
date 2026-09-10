import uuid
import hashlib
import json
from django.db import models
from rest_framework.exceptions import PermissionDenied
from apps.companies.models import Company
from apps.accounts.models import User

class AuditLog(models.Model):
    ACTION_CHOICES = (
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('POST', 'Post'),
        ('CANCEL', 'Cancel'),
        ('REVERSE', 'Reverse'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)  # e.g., 'Voucher'
    record_id = models.CharField(max_length=255)
    changes = models.JSONField(null=True, blank=True)  # Store state before/after
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    previous_hash = models.CharField(max_length=64, null=True, blank=True)
    current_hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['company', 'model_name', 'record_id']),
            models.Index(fields=['company', 'created_at']),
        ]

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Audit log records are immutable and cannot be deleted.")

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("Audit log records are immutable and cannot be modified.")

        # Cryptographic tamper-evident hash chaining
        last_log = AuditLog.objects.filter(company=self.company).order_by('-created_at').first()
        self.previous_hash = last_log.current_hash if last_log and last_log.current_hash else "0" * 64
        payload = f"{self.previous_hash}:{self.company_id}:{self.action}:{self.model_name}:{self.record_id}:{json.dumps(self.changes, sort_keys=True) if self.changes else ''}"
        self.current_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.action} on {self.model_name} by {self.user.email if self.user else 'System'}"

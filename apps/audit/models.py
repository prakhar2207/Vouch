import uuid
import hashlib
import json
from django.db import models, transaction
from django.utils import timezone
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
        ('EXCLUDE', 'Exclude'),
        ('RECONCILE', 'Reconcile'),
        ('RESOLVE', 'Resolve'),
        ('EXECUTE_FIX', 'Execute Fix'),
        ('IMPORT', 'Import'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)  # e.g., 'Voucher'
    record_id = models.CharField(max_length=255)
    changes = models.JSONField(null=True, blank=True)  # Store state before/after
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    previous_hash = models.CharField(max_length=64, null=True, blank=True)
    current_hash = models.CharField(max_length=64, null=True, blank=True)
    schema_version = models.CharField(max_length=10, default='v2', db_index=True)
    sequence = models.BigIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    def compute_hash(self, prev_hash: str) -> str:
        changes_json = json.dumps(self.changes or {}, sort_keys=True, separators=(',', ':'))
        ts_iso = self.created_at.isoformat() if self.created_at else ''
        payload_parts = [
            str(self.schema_version or 'v2'),
            str(prev_hash or '0' * 64),
            str(self.id or ''),
            str(self.company_id or 'NO_COMPANY'),
            str(self.user_id or 'SYSTEM'),
            str(self.action or '').upper(),
            str(self.model_name or ''),
            str(self.record_id or ''),
            ts_iso,
            str(self.ip_address or '0.0.0.0'),
            changes_json
        ]
        canonical_str = '|'.join(payload_parts)
        return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()

    class Meta:
        ordering = ['sequence', 'created_at']
        indexes = [
            models.Index(fields=['company', 'model_name', 'record_id']),
            models.Index(fields=['company', 'created_at']),
        ]

    def delete(self, *args, **kwargs):
        if kwargs.pop('force', False):
            return super().delete(*args, **kwargs)
        raise PermissionDenied("Audit log records are immutable and cannot be deleted.")

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("Audit log records are immutable and cannot be modified.")

        with transaction.atomic():
            # Cryptographic tamper-evident hash chaining serialized per-company
            if self.company_id:
                Company.objects.select_for_update(no_key=True).filter(id=self.company_id).first()

            if not self.created_at:
                from django.utils import timezone
                self.created_at = timezone.now()

            last_log = AuditLog.objects.filter(company=self.company).order_by('-sequence', '-created_at').first()
            self.sequence = (last_log.sequence + 1) if last_log and last_log.sequence is not None else 1
            self.previous_hash = last_log.current_hash if last_log and last_log.current_hash else "0" * 64
            if self.schema_version == 'v2':
                self.current_hash = self.compute_hash(self.previous_hash)
            else:
                payload = f"{self.previous_hash}:{self.company_id}:{self.action}:{self.model_name}:{self.record_id}:{json.dumps(self.changes, sort_keys=True) if self.changes else ''}"
                self.current_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.action} on {self.model_name} by {self.user.email if self.user else 'System'}"

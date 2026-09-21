import uuid
from django.db import models
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User


class DocumentSnapshot(models.Model):
    DOCUMENT_TYPE_CHOICES = (
        ('SALES_INVOICE', 'Sales Invoice'),
        ('PURCHASE_INVOICE', 'Purchase Invoice'),
        ('CREDIT_NOTE', 'Credit Note'),
        ('DEBIT_NOTE', 'Debit Note'),
        ('PAYMENT', 'Payment Voucher'),
        ('RECEIPT', 'Receipt Voucher'),
        ('CONTRA', 'Contra Voucher'),
        ('JOURNAL', 'Journal Voucher'),
        ('CUSTOMER_STATEMENT', 'Customer Statement'),
        ('SUPPLIER_STATEMENT', 'Supplier Statement'),
        ('LEDGER', 'Ledger Statement'),
        ('TRIAL_BALANCE', 'Trial Balance'),
        ('PROFIT_AND_LOSS', 'Profit & Loss'),
        ('BALANCE_SHEET', 'Balance Sheet'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='document_snapshots')
    document_type = models.CharField(max_length=40, choices=DOCUMENT_TYPE_CHOICES, db_index=True)
    source_type = models.CharField(max_length=50, blank=True, default='')  # 'Voucher', 'Ledger', 'Report'
    source_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    source_version = models.PositiveIntegerField(default=1)
    
    document_number = models.CharField(max_length=100, blank=True, default='', db_index=True)
    document_date = models.DateField(null=True, blank=True, db_index=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    snapshot_json = models.JSONField(help_text="Canonical Document DTO (JSON only, no binary or base64 PDF)")
    template_code = models.CharField(max_length=50, default='gst_invoice_classic')
    template_version = models.CharField(max_length=20, default='1.0')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_document_snapshots')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'document_type', 'source_id']),
            models.Index(fields=['company', 'document_date']),
            models.Index(fields=['company', 'source_type', 'source_id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.document_type} - {self.document_number or self.source_id} ({self.company.name})"


class DocumentTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, db_index=True)
    version = models.CharField(max_length=20, default='1.0')
    document_type = models.CharField(max_length=40)
    name = models.CharField(max_length=100)
    configuration = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('code', 'version')

    def __str__(self):
        return f"{self.name} ({self.code} v{self.version})"


class DocumentShare(models.Model):
    SHARE_TYPE_CHOICES = (
        ('INVOICE', 'Invoice'),
        ('STATEMENT', 'Statement'),
        ('DOCUMENT', 'Document'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_snapshot = models.ForeignKey(DocumentSnapshot, on_delete=models.CASCADE, related_name='shares')
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    share_type = models.CharField(max_length=20, choices=SHARE_TYPE_CHOICES, default='INVOICE')
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_document_shares')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True

    def __str__(self):
        return f"Share {self.share_type} for {self.document_snapshot.document_number} (Active: {self.is_active})"


class DocumentShareEvent(models.Model):
    EVENT_CHOICES = (
        ('CREATED', 'Created'),
        ('VIEWED', 'Viewed'),
        ('DOWNLOADED', 'Downloaded'),
        ('EMAILED', 'Emailed'),
        ('WHATSAPP_SHARED', 'WhatsApp Shared'),
        ('REVOKED', 'Revoked'),
        ('EXPIRED', 'Expired'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share = models.ForeignKey(DocumentShare, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    ip_hash = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} on {self.share_id} at {self.created_at}"


class EDIDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_snapshot = models.OneToOneField(DocumentSnapshot, on_delete=models.CASCADE, related_name='edi_document')
    schema_version = models.CharField(max_length=20, default='1.0')
    sender_company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='sent_edi_documents')
    receiver_gstin = models.CharField(max_length=15, db_index=True)
    payload = models.JSONField(help_text="Standardized canonical EDI payload for invoice import")
    payload_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"EDI Doc {self.idempotency_key} -> {self.receiver_gstin}"


class EDIExchange(models.Model):
    STATUS_CHOICES = (
        ('CREATED', 'Created'),
        ('SHARED', 'Shared'),
        ('VIEWED', 'Viewed'),
        ('IMPORT_INITIATED', 'Import Initiated'),
        ('DRAFT_CREATED', 'Draft Created'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edi_document = models.ForeignKey(EDIDocument, on_delete=models.CASCADE, related_name='exchanges')
    target_company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='received_edi_exchanges')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='CREATED', db_index=True)
    draft_purchase_voucher = models.ForeignKey(
        'accounting.Voucher', on_delete=models.SET_NULL, null=True, blank=True, related_name='edi_exchanges'
    )
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['target_company', 'status']),
        ]

    def __str__(self):
        return f"EDIExchange {self.edi_document.idempotency_key} -> {self.target_company_id} ({self.status})"


class DocumentAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='document_audit_events')
    document_snapshot = models.ForeignKey(DocumentSnapshot, on_delete=models.CASCADE, related_name='audit_events')
    action = models.CharField(max_length=50)
    details = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='document_audit_events')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on snapshot {self.document_snapshot_id} by {self.user_id}"

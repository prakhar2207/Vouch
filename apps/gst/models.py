import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.encryption import EncryptedTextField


class ProtectedGSTAllocationQuerySet(models.QuerySet):
    """Guarantees QuerySet.delete() cannot bulk-delete active, reported, or superseded allocations."""
    def delete(self):
        for alloc in self:
            if alloc.status in ['APPROVED', 'REPORTED', 'FILED'] or alloc.is_active:
                raise ValidationError(
                    f"Statutory Compliance Invariant: Cannot bulk-delete active or reported GST reporting allocation '{alloc.id}'."
                )
            if alloc.supersedes.exists() or alloc.superseded_by:
                raise ValidationError(
                    f"Statutory Compliance Invariant: Cannot bulk-delete historical allocation '{alloc.id}' in supersession chain."
                )
        return super().delete()


class ProtectedGSTWorkspaceQuerySet(models.QuerySet):
    """Guarantees QuerySet.delete() cannot bulk-delete exported, filed, or reviewed return workspaces."""
    def delete(self):
        for ws in self:
            if ws.status in ['EXPORTED', 'FILED', 'REVIEWED']:
                raise ValidationError(
                    f"Statutory Audit Invariant: Cannot bulk-delete GST return workspace for period '{ws.return_period}' in '{ws.status}' status."
                )
        return super().delete()


class ProtectedGSTSnapshotQuerySet(models.QuerySet):
    """Guarantees QuerySet.delete() cannot bulk-delete exported snapshot archives."""
    def delete(self):
        raise ValidationError(
            "Statutory Compliance Invariant: GST workspace export snapshots are immutable historical records and cannot be bulk-deleted."
        )


class ProtectedGSTFilingRecordQuerySet(models.QuerySet):
    """Guarantees QuerySet.delete() cannot bulk-delete filed return records."""
    def delete(self):
        for rec in self:
            if rec.status in ['FILED', 'SUBMITTED', 'SUBMITTING']:
                raise ValidationError(
                    f"Statutory Audit Invariant: Cannot bulk-delete GST filing record '{rec.id}' in '{rec.status}' status."
                )
        return super().delete()


class CompanyGSTConfig(models.Model):
    PROVIDER_CHOICES = (
        ('MOCK', 'Mock / Sandbox Provider (Offline & Testing)'),
        ('SANDBOX_CO_IN', 'Sandbox by Quicko (api.sandbox.co.in)'),
        ('CLEAR', 'Clear (ClearTax API Gateway)'),
        ('MASTERS_INDIA', 'Masters India GST Gateway'),
        ('CASHFREE', 'Cashfree Verification Gateway'),
        ('NIC_DIRECT', 'Direct NIC API (Government Portal)'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='gst_config')
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default='MOCK')
    is_sandbox = models.BooleanField(default=True)
    
    # Legacy / Generic API Gateway Credentials (Fernet AES-256 Encrypted at Rest)
    api_key = EncryptedTextField(blank=True, default='')
    api_secret = EncryptedTextField(blank=True, default='')

    # Dedicated Sandbox by Quicko Gateway Credentials (Fernet AES-256 Encrypted at Rest)
    sandbox_api_key = EncryptedTextField(blank=True, default='')
    sandbox_api_secret = EncryptedTextField(blank=True, default='')
    sandbox_base_url = models.CharField(max_length=255, default='https://api.sandbox.co.in')
    sandbox_access_token = EncryptedTextField(blank=True, default='')
    sandbox_token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # E-Way Bill NIC Credentials (Fernet AES-256 Encrypted at Rest)
    eway_username = models.CharField(max_length=100, blank=True, default='')
    eway_password = EncryptedTextField(blank=True, default='')
    
    # E-Invoice NIC / IRP Credentials (Fernet AES-256 Encrypted at Rest)
    einvoice_username = models.CharField(max_length=100, blank=True, default='')
    einvoice_password = EncryptedTextField(blank=True, default='')
    
    # Session / Bearer Token Cache (Fernet AES-256 Encrypted at Rest)
    auth_token = EncryptedTextField(blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company.name} GST Config ({self.provider}, Sandbox={self.is_sandbox})"


class GSTRegistration(models.Model):
    """
    Multi-state / Multi-GSTIN entity model.
    A company may maintain distinct GST registrations across different Indian states or union territories.
    Every GST return, e-invoice, and e-way bill operation explicitly references its GST registration.
    """
    TAXPAYER_TYPE_CHOICES = (
        ('REGULAR', 'Regular Taxpayer'),
        ('COMPOSITION', 'Composition Scheme'),
        ('ISD', 'Input Service Distributor'),
        ('SEZ_DEVELOPER', 'SEZ Developer'),
        ('SEZ_UNIT', 'SEZ Unit'),
        ('CASUAL', 'Casual Taxable Person'),
        ('NON_RESIDENT', 'Non-Resident Taxable Person'),
    )

    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('SUSPENDED', 'Suspended'),
        ('CANCELLED', 'Cancelled'),
        ('INACTIVE', 'Inactive'),
    )

    VERIFICATION_STATUS_CHOICES = (
        ('NOT_VERIFIED', 'Not Verified'),
        ('PENDING', 'Verification Pending'),
        ('VERIFIED', 'Verified'),
        ('INVALID', 'Invalid GSTIN'),
        ('INACTIVE', 'Inactive Registration'),
        ('FAILED', 'Verification Failed'),
        ('PROVIDER_UNAVAILABLE', 'Provider Unavailable'),
        ('EXPIRED', 'Verification Expired'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gst_registrations')
    
    gstin = models.CharField(max_length=15, db_index=True)
    legal_name = models.CharField(max_length=255)
    trade_name = models.CharField(max_length=255, blank=True, default='')
    
    state_code = models.CharField(max_length=2, db_index=True)  # e.g., '27', '09'
    state_name = models.CharField(max_length=100)
    
    address = models.TextField(blank=True, default='')
    pincode = models.CharField(max_length=10, blank=True, default='')
    
    taxpayer_type = models.CharField(max_length=30, choices=TAXPAYER_TYPE_CHOICES, default='REGULAR')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    registration_date = models.DateField(null=True, blank=True)
    
    # Verification details
    verification_status = models.CharField(
        max_length=30,
        choices=VERIFICATION_STATUS_CHOICES,
        default='NOT_VERIFIED',
        db_index=True
    )
    last_verified_at = models.DateTimeField(null=True, blank=True)
    provider_reference_id = models.CharField(max_length=100, blank=True, default='')

    is_primary = models.BooleanField(default=False)
    
    # Portal compliance / OTP username & cached session token
    taxpayer_username = models.CharField(max_length=100, blank=True, default='')
    auth_token = EncryptedTextField(blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # E-Invoice NIC / IRP credentials
    einvoice_username = models.CharField(max_length=100, blank=True, default='')
    einvoice_password = EncryptedTextField(blank=True, default='')
    
    # E-Way Bill NIC credentials
    eway_username = models.CharField(max_length=100, blank=True, default='')
    eway_password = EncryptedTextField(blank=True, default='')

    # Authorized users for this registration (optional restriction)
    authorized_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='authorized_gst_registrations'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', 'state_code']
        unique_together = ('company', 'gstin')
        indexes = [
            models.Index(fields=['company', 'gstin']),
            models.Index(fields=['company', 'state_code']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company'],
                condition=models.Q(is_primary=True),
                name='unique_primary_gstin_per_company'
            )
        ]

    def __str__(self):
        return f"{self.gstin} ({self.state_name}) - {self.company.name} [{self.status}]"


class EWayBillRecord(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
        ('EXTENDED', 'Extended'),
    )

    TRANSPORT_MODE_CHOICES = (
        ('1', 'Road'),
        ('2', 'Rail'),
        ('3', 'Air'),
        ('4', 'Ship'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='eway_bills')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eway_bills'
    )
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='eway_bills')
    
    ewb_number = models.CharField(max_length=20, unique=True, db_index=True)
    ewb_date = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    
    supply_type = models.CharField(max_length=20, default='OUTWARD')
    sub_supply_type = models.CharField(max_length=30, default='SUPPLY')
    doc_type = models.CharField(max_length=10, default='INV')
    
    transport_mode = models.CharField(max_length=5, choices=TRANSPORT_MODE_CHOICES, default='1')
    distance_km = models.PositiveIntegerField(default=0)
    
    transporter_id = models.CharField(max_length=15, blank=True, default='')
    transporter_name = models.CharField(max_length=255, blank=True, default='')
    
    vehicle_number = models.CharField(max_length=20, blank=True, default='')
    vehicle_type = models.CharField(max_length=10, default='R')  # R = Regular, O = Over Dimensional Cargo
    
    transporter_doc_no = models.CharField(max_length=50, blank=True, default='')
    transporter_doc_date = models.DateField(null=True, blank=True)
    
    cancel_reason = models.CharField(max_length=50, blank=True, default='')
    cancel_remarks = models.TextField(blank=True, default='')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    raw_response_json = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-ewb_date']

    def __str__(self):
        return f"EWB #{self.ewb_number} ({self.voucher.voucher_number}) - {self.status}"


class EInvoiceRecord(models.Model):
    STATUS_CHOICES = (
        ('GENERATED', 'Generated'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='einvoices')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='einvoices'
    )
    voucher = models.OneToOneField(Voucher, on_delete=models.CASCADE, related_name='einvoice_record')
    
    irn = models.CharField(max_length=64, unique=True, db_index=True)
    signed_invoice = models.TextField(blank=True, default='')
    signed_qr_code = models.TextField(blank=True, default='')
    ack_number = models.CharField(max_length=50, blank=True, default='')
    ack_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='GENERATED')
    
    cancel_reason = models.CharField(max_length=50, blank=True, default='')
    cancel_remarks = models.TextField(blank=True, default='')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    raw_response_json = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"IRN {self.irn[:12]}... ({self.voucher.voucher_number}) - {self.status}"


class GSTTaxpayerCache(models.Model):
    gstin = models.CharField(max_length=15, unique=True, db_index=True)
    legal_name = models.CharField(max_length=255)
    trade_name = models.CharField(max_length=255, blank=True, default='')
    state_code = models.CharField(max_length=2)
    state_name = models.CharField(max_length=100)
    address = models.TextField(blank=True, default='')
    pincode = models.CharField(max_length=10, blank=True, default='')
    taxpayer_type = models.CharField(max_length=50, default='Regular')
    status = models.CharField(max_length=50, default='Active')
    registration_date = models.DateField(null=True, blank=True)
    raw_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.gstin} - {self.trade_name or self.legal_name} ({self.status})"


class GSTR2BImport(models.Model):
    STATUS_CHOICES = (
        ('PROCESSING', 'Processing'),
        ('PROCESSED', 'Processed'),
        ('FAILED', 'Failed'),
    )
    FILE_FORMAT_CHOICES = (
        ('JSON', 'GST Portal JSON'),
        ('EXCEL', 'GSTR-2B Excel'),
        ('API', 'GSP Direct API'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gstr2b_imports')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gstr2b_imports'
    )
    return_period = models.CharField(max_length=10, db_index=True)  # e.g. "082026" or "2026-08"
    financial_year = models.CharField(max_length=10, blank=True, default='')  # e.g. "2026-27"
    file_format = models.CharField(max_length=10, choices=FILE_FORMAT_CHOICES, default='JSON')
    file_name = models.CharField(max_length=255, blank=True, default='')
    
    total_invoices_count = models.PositiveIntegerField(default=0)
    total_taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_itc_available = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROCESSED')
    error_log = models.TextField(blank=True, default='')
    
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"GSTR-2B {self.return_period} - {self.company.name} ({self.status})"


class GSTR2BRecord(models.Model):
    MATCH_STATUS_CHOICES = (
        ('MATCHED', 'Matched in Books'),
        ('MISMATCHED', 'Value / Tax Mismatch'),
        ('MISSING_IN_BOOKS', 'Missing in Purchase Books'),
        ('MISSING_IN_2B', 'Missing in GSTR-2B'),
        ('TAX_MISMATCH', 'Tax Breakdown Mismatch'),
        ('GSTIN_MISMATCH', 'GSTIN Mismatch'),
        ('DOC_NUM_MISMATCH', 'Invoice Number Format Mismatch'),
        ('DATE_MISMATCH', 'Invoice Date Mismatch'),
        ('DUPLICATE', 'Duplicate Invoice'),
        ('INELIGIBLE_ITC', 'Blocked / Ineligible ITC'),
        ('PARTIAL_MATCH', 'Partial Match'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(GSTR2BImport, on_delete=models.CASCADE, related_name='records')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gstr2b_records', db_index=True)
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gstr2b_records'
    )
    
    supplier_gstin = models.CharField(max_length=15, db_index=True)
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    invoice_number = models.CharField(max_length=100, db_index=True)
    normalized_invoice_number = models.CharField(max_length=100, db_index=True)
    invoice_type = models.CharField(max_length=10, default='R')  # Regular, Deemed, SEZ, etc.
    invoice_date = models.DateField()
    invoice_value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    igst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    cess_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    place_of_supply = models.CharField(max_length=10, blank=True, default='')
    reverse_charge = models.CharField(max_length=5, default='N')
    itc_available = models.BooleanField(default=True)
    itc_ineligible_reason = models.CharField(max_length=100, blank=True, default='')
    
    gstr1_filing_date = models.DateField(null=True, blank=True)
    gstr3b_status = models.CharField(max_length=20, default='UNKNOWN')
    
    matched_voucher = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='gstr2b_matches')
    match_status = models.CharField(max_length=30, choices=MATCH_STATUS_CHOICES, default='MISSING_IN_BOOKS')
    mismatch_details = models.JSONField(default=dict, blank=True)
    
    # Audit & User Action tracking
    is_reviewed = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_gstr2b_records')
    review_notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'supplier_gstin', 'normalized_invoice_number']),
            models.Index(fields=['company', 'match_status']),
        ]

    def __str__(self):
        return f"{self.supplier_gstin} - {self.invoice_number} (₹{self.invoice_value}) - {self.match_status}"


class GSTFilingRecord(models.Model):
    """
    Authoritative persistence for GST Return filings, portal submissions, and offline exports.
    Tracks state machine from DRAFT through SUBMITTED, FILED, or RECONCILIATION_REQUIRED.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('VALIDATING', 'Validating'),
        ('SUBMITTING', 'Submitting to Portal'),
        ('SUBMITTED', 'Submitted'),
        ('FILED', 'Filed'),
        ('FAILED', 'Filing Failed'),
        ('RECONCILIATION_REQUIRED', 'Reconciliation Required'),
    )

    RETURN_TYPE_CHOICES = (
        ('GSTR1', 'GSTR-1 (Outward Supplies)'),
        ('GSTR3B', 'GSTR-3B (Monthly Summary Return)'),
        ('GSTR9', 'GSTR-9 (Annual Return)'),
        ('CMP08', 'CMP-08 (Composition Scheme)'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gst_filings')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gst_filings'
    )
    return_type = models.CharField(max_length=20, choices=RETURN_TYPE_CHOICES, default='GSTR1')
    return_period = models.CharField(max_length=20, db_index=True)  # e.g., "082026", "2026-08", "2025-26"
    financial_year = models.CharField(max_length=15, blank=True, default='')

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='FILED')
    arn = models.CharField(max_length=50, blank=True, default='', db_index=True)  # Application Reference Number
    provider_reference = models.CharField(max_length=100, blank=True, default='')
    payload_hash = models.CharField(max_length=64, blank=True, default='')

    total_taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    invoices_count = models.PositiveIntegerField(default=0)

    filing_mode = models.CharField(max_length=30, default='DIRECT_PORTAL')  # DIRECT_PORTAL, OFFLINE_JSON, MANUAL
    response_snapshot = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProtectedGSTFilingRecordQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        if self.status in ['FILED', 'SUBMITTED', 'SUBMITTING']:
            raise ValidationError(
                f"Statutory Audit Invariant: Cannot delete GST filing record '{self.id}' in '{self.status}' status."
            )
        super().delete(*args, **kwargs)

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['company', 'return_type', 'return_period']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.return_type} ({self.return_period}) [{self.status}] ARN: {self.arn or 'N/A'}"


class GSTAuditLog(models.Model):
    """
    Cryptographically timestamped audit log of all outbound GST provider requests and compliance events.
    Never persists plaintext secrets, API keys, passwords, or taxpayer OTPs.
    """
    ACTION_CHOICES = (
        ('AUTH_TOKEN', 'Provider Authentication Token Exchange'),
        ('GSTIN_VERIFY', 'Taxpayer GSTIN Verification'),
        ('PORTAL_OTP_REQUEST', 'Taxpayer Portal OTP Request'),
        ('PORTAL_OTP_VERIFY', 'Taxpayer Portal OTP Verification'),
        ('GSTR1_PREPARE', 'GSTR-1 Outward Supply Preparation'),
        ('GSTR1_SUBMIT', 'GSTR-1 Direct Portal Submission'),
        ('GSTR1_STATUS', 'GSTR-1 Portal Processing Status Check'),
        ('GSTR2B_FETCH', 'GSTR-2B Statement Fetch'),
        ('GSTR2B_RECONCILE', 'GSTR-2B Purchase Register Reconciliation'),
        ('EINVOICE_GENERATE', 'e-Invoice IRN Generation'),
        ('EINVOICE_CANCEL', 'e-Invoice IRN Cancellation'),
        ('EWAYBILL_GENERATE', 'e-Way Bill Generation'),
        ('EWAYBILL_UPDATE_VEHICLE', 'e-Way Bill Vehicle Update'),
        ('EWAYBILL_CANCEL', 'e-Way Bill Cancellation'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gst_audit_logs')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gst_audit_logs'
    )
    
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    correlation_id = models.CharField(max_length=64, db_index=True)
    endpoint = models.CharField(max_length=255)
    http_method = models.CharField(max_length=10, default='POST')
    
    status_code = models.PositiveIntegerField(null=True, blank=True)
    is_success = models.BooleanField(default=True)
    
    # Redacted JSON summaries
    request_summary = models.JSONField(default=dict, blank=True)
    response_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')
    
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gst_audit_events'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'action', '-created_at']),
            models.Index(fields=['correlation_id']),
        ]

    def __str__(self):
        return f"[{self.action}] {self.company.name} - Success={self.is_success} ({self.created_at.strftime('%Y-%m-%d %H:%M:%S')})"


class GSTReturnWorkspace(models.Model):
    """
    Unified GST Workspace model tracking return period lifecycle, draft snapshots,
    pre-filing validations, and voucher drift detection.
    
    Lifecycle Statuses:
    NOT_STARTED -> DRAFT -> VALIDATION_REQUIRED -> READY_FOR_REVIEW -> REVIEWED -> EXPORTED
    """
    STATUS_CHOICES = (
        ('NOT_STARTED', 'Not Started'),
        ('DRAFT', 'Draft Generated'),
        ('VALIDATION_REQUIRED', 'Validation Required'),
        ('READY_FOR_REVIEW', 'Ready for Review'),
        ('REVIEWED', 'Reviewed & Approved'),
        ('EXPORTED', 'Exported'),
    )

    RETURN_TYPE_CHOICES = (
        ('GSTR1', 'GSTR-1 (Outward Supplies)'),
        ('GSTR3B', 'GSTR-3B (Monthly Summary)'),
        ('GSTR2B_RECON', 'GSTR-2B Reconciliation'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gst_return_workspaces')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='return_workspaces'
    )
    financial_year = models.CharField(max_length=15, db_index=True)  # e.g. "2026-27"
    return_period = models.CharField(max_length=20, db_index=True)   # e.g. "082026" or "2026-08"
    return_type = models.CharField(max_length=20, choices=RETURN_TYPE_CHOICES, default='GSTR1', db_index=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='NOT_STARTED', db_index=True)

    sales_data_available = models.BooleanField(default=False)
    purchase_data_available = models.BooleanField(default=False)
    unclassified_count = models.PositiveIntegerField(default=0)
    validation_error_count = models.PositiveIntegerField(default=0)
    validation_warning_count = models.PositiveIntegerField(default=0)

    tax_liability_summary = models.JSONField(default=dict, blank=True)
    itc_summary = models.JSONField(default=dict, blank=True)
    reconciliation_status = models.CharField(max_length=30, default='NOT_STARTED')
    validation_errors = models.JSONField(default=list, blank=True)

    # Snapshot and Drift Detection
    source_voucher_hash = models.CharField(max_length=64, blank=True, default='')
    is_stale = models.BooleanField(default=False)
    draft_payload = models.JSONField(default=dict, blank=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_gst_workspaces'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-return_period', 'return_type']
        unique_together = ('company', 'gst_registration', 'return_type', 'return_period')
        indexes = [
            models.Index(fields=['company', 'return_type', 'return_period']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'financial_year']),
        ]

    def delete(self, *args, **kwargs):
        if self.status in ['EXPORTED', 'FILED', 'REVIEWED']:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                f"Statutory Audit Invariant: Cannot delete GST return workspace for period '{self.return_period}' "
                f"in '{self.status}' status. Historical tax returns and signed-off workspaces are immutable."
            )
        super().delete(*args, **kwargs)

    objects = ProtectedGSTWorkspaceQuerySet.as_manager()

    def __str__(self):
        reg = self.gst_registration.gstin if self.gst_registration else "Default"
        return f"{self.company.name} [{reg}] {self.return_type} ({self.return_period}) - {self.status}"


class GSTReportingAllocation(models.Model):
    """
    Dedicated GST Reporting Allocation & Prior-Period Event Model.
    Separates accounting dates (historical books truth) from GST reporting periods (statutory compliance).
    Ensures that transactions remain historically correct in the accounting ledgers while SriLekh
    independently determines when and how their GST consequences are reported.
    """
    RECEIPT_TYPE_CHOICES = (
        ('SINGLE', 'Single Consignment Receipt'),
        ('LOTS_INSTALMENTS', 'Lots or Instalments (First Proviso to Sec 16(2))'),
        ('SERVICE_COMPLETION', 'Service Completion / Acceptance Certificate'),
    )

    RECEIPT_DOCUMENT_TYPE_CHOICES = (
        ('GRN', 'Goods Receipt Note'),
        ('DELIVERY_CHALLAN', 'Delivery Challan'),
        ('EWAY_BILL', 'E-Way Bill Proof of Delivery'),
        ('SERVICE_COMPLETION', 'Service Completion / Acceptance Certificate'),
        ('INVOICE_PHYSICAL_COPY', 'Endorsed Physical Invoice'),
        ('NONE', 'No Affirmative Receipt Evidence'),
        ('OTHER', 'Other Affirmative Receipt Evidence'),
    )

    EVENT_TYPE_CHOICES = (
        ('OUTWARD_SUPPLY', 'Outward Supply (GSTR-1 Table 4/5/6/7)'),
        ('INWARD_ITC', 'Inward Supply / Eligible ITC (GSTR-3B Table 4A)'),
        ('CREDIT_NOTE', 'Statutory GST Credit Note (CGST Act Section 34 / Table 9B)'),
        ('DEBIT_NOTE', 'Statutory GST Debit Note (CGST Act Section 34 / Table 9B)'),
        ('INWARD_RCM', 'Inward Supply Subject to Reverse Charge (GSTR-3B Table 3.1d)'),
        ('ADVANCE_RECEIVED', 'Advance Received (GSTR-1 Table 11A)'),
        ('ADVANCE_ADJUSTED', 'Advance Adjusted (GSTR-1 Table 11B)'),
        ('ITC_REVERSAL_RULE_42', 'ITC Reversal - Common Credit Attribution (Rule 42/43 / Table 4B1)'),
        ('ITC_REVERSAL_RULE_37', 'ITC Reversal - 180-Day Non-Payment of Consideration (Rule 37 / Table 4B2)'),
        ('ITC_REVERSAL_RULE_37A', 'ITC Reversal - Supplier Non-Payment of Tax in GSTR-3B (Rule 37A / Table 4B2)'),
        ('ITC_REVERSAL_SEC_17_5', 'ITC Reversal - Blocked Credits (Section 17(5) / Table 4B1)'),
        ('ITC_REVERSAL_OTHER', 'ITC Reversal - Other Statutory Grounds (Table 4B2)'),
        ('ITC_RECLAIM', 'ITC Reclaim of Previously Reversed Credit (Table 4D1)'),
        ('INTERNAL_ACCOUNTING_REVERSAL', 'Internal Non-GST Accounting Reversal Journal (Exempt from GSTR-1 Table 9B)'),
        ('COMMERCIAL_CREDIT_NOTE', 'Commercial Credit Note without tax liability reduction (Exempt from Table 9B)'),
    )

    ALLOCATION_REASON_CHOICES = (
        ('REGULAR', 'Regular On-Time Entry'),
        ('LATE_OUTWARD_SUPPLY', 'Late Entry Outward Supply (Reported in later tax period)'),
        ('LATE_INWARD_RECEIPT', 'Late Received Inward Supply (Section 16(2) Receipt Month)'),
        ('RESTRICTED_SECTION_16_4', 'Statute-Barred ITC (Section 16(4) 30th November deadline exceeded)'),
        ('STATUTORY_DEADLINE_EXCEEDED', 'Statutory Outward Amendment Deadline Exceeded (Section 37(3))'),
        ('GOODS_SERVICES_NOT_RECEIVED', 'Section 16(2)(b): Goods/Services Not Received'),
        ('PARTIAL_LOT_PENDING_LAST_INSTALMENT', 'First Proviso to Section 16(2): Goods in lots/instalments (last lot pending)'),
        ('PARTIAL_RECEIPT_PROPORTIONATE', 'Section 16(2)(b): Partial Consignment Received (Proportionate ITC Claim)'),
        ('REVOCATION_SECTION_16_6', 'Section 16(6): 30-Day Window Following Registration Revocation Order'),
        ('INELIGIBLE_SECTION_17_5', 'Section 17(5): Ineligible Blocked Credit at Inception'),
        ('MANUAL_REALLOCATION', 'Manual Reallocation by Accountant/CA'),
        ('REVERSAL_CREDIT_NOTE', 'Statutory Section 34 Credit Note Reversal'),
        ('COMMERCIAL_CREDIT_NOTE_NO_TAX', 'Commercial Credit Note without tax liability reduction'),
        ('REVERSAL_INTERNAL_JOURNAL', 'Internal Accounting Reversal Journal (Exempt from GST Return Tables)'),
        ('REVERSAL_RULE_37', 'Rule 37 Reversal (180 days non-payment)'),
        ('REVERSAL_RULE_37A', 'Rule 37A Reversal (Supplier default in GSTR-3B)'),
        ('REVERSAL_RULE_42_43', 'Rule 42/43 Reversal (Exempt/non-business attribution)'),
        ('REVERSAL_SECTION_17_5', 'Section 17(5) Reversal (Ineligible blocked credit)'),
        ('REVERSAL_ADJUSTMENT', 'General Reversal Adjustment'),
    )

    ALLOCATION_STATUS_CHOICES = (
        ('PROPOSED', 'Proposed'),
        ('APPROVED', 'Approved / Active'),
        ('REPORTED', 'Included in Filed Return'),
        ('SUPERSEDED', 'Superseded by Newer Allocation'),
        ('EXCLUDED', 'Statutorily Excluded'),
        ('FILED', 'Filed Return Allocation'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='gst_allocations')
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT, related_name='gst_allocations')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gst_allocations'
    )

    event_type = models.CharField(max_length=35, choices=EVENT_TYPE_CHOICES, db_index=True)
    voucher_date = models.DateField(db_index=True)
    entry_date = models.DateField(default=timezone.now)

    # Section 16(2)(b) Goods/Service Receipt Evidence (Fails closed by default: False)
    goods_received_date = models.DateField(null=True, blank=True, db_index=True)
    is_receipt_confirmed = models.BooleanField(default=False, db_index=True)
    receipt_type = models.CharField(max_length=25, choices=RECEIPT_TYPE_CHOICES, default='SINGLE')
    last_instalment_received = models.BooleanField(default=False, db_index=True)
    receipt_document_number = models.CharField(max_length=100, blank=True, default='')
    receipt_document_type = models.CharField(max_length=30, choices=RECEIPT_DOCUMENT_TYPE_CHOICES, default='NONE')
    receipt_confirmed_at = models.DateTimeField(null=True, blank=True)
    receipt_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_gst_receipts'
    )
    partial_received_fraction = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('1.0000'))

    original_period = models.CharField(max_length=10, db_index=True)   # MMYYYY derived from voucher_date
    assigned_period = models.CharField(max_length=10, db_index=True)   # MMYYYY tax reporting period
    financial_year = models.CharField(max_length=15, db_index=True)    # e.g. "2025-26" or "2026-27"

    allocation_reason = models.CharField(max_length=40, choices=ALLOCATION_REASON_CHOICES, default='REGULAR')
    status = models.CharField(max_length=20, choices=ALLOCATION_STATUS_CHOICES, default='APPROVED', db_index=True)

    # Statutory Eligibility
    is_statutorily_eligible = models.BooleanField(default=True, db_index=True)
    statutory_rule = models.CharField(max_length=100, blank=True, default='')
    statutory_notes = models.TextField(blank=True, default='')
    exclusion_reason = models.TextField(blank=True, default='')

    # Monetary Snapshot for Reporting Verification
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_tax = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    # Auditing and History
    is_active = models.BooleanField(default=True, db_index=True)
    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='supersedes'
    )
    superseded_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_gst_allocations'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProtectedGSTAllocationQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        if self.status in ['APPROVED', 'REPORTED', 'FILED'] or self.is_active:
            raise ValidationError(
                f"Statutory Compliance Invariant: Cannot delete active or reported GST reporting allocation '{self.id}'."
            )
        if self.supersedes.exists() or self.superseded_by:
            raise ValidationError(
                f"Statutory Compliance Invariant: Cannot delete historical allocation '{self.id}' in supersession chain."
            )
        super().delete(*args, **kwargs)

    class Meta:
        ordering = ['-assigned_period', '-created_at']
        indexes = [
            models.Index(fields=['company', 'assigned_period', 'is_active']),
            models.Index(fields=['company', 'voucher', 'is_active']),
            models.Index(fields=['company', 'event_type', 'assigned_period']),
            models.Index(fields=['company', 'is_statutorily_eligible', 'assigned_period']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['voucher', 'event_type'],
                condition=models.Q(is_active=True),
                name='unique_active_allocation_per_voucher_event'
            )
        ]

    def __str__(self):
        return f"[{self.assigned_period}] {self.voucher.voucher_number} - {self.event_type} ({self.status}) Eligible={self.is_statutorily_eligible}"


class GSTWorkspaceExportSnapshot(models.Model):
    """
    Immutable historical audit snapshot of an exported return workspace.
    Ensures that once a return is EXPORTED, its exact canonical payload and checksum
    are preserved immutably, even if drafts are later recompiled.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(GSTReturnWorkspace, on_delete=models.PROTECT, related_name='export_snapshots')
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='gst_export_snapshots')
    return_type = models.CharField(max_length=20, db_index=True)
    return_period = models.CharField(max_length=20, db_index=True)
    export_format = models.CharField(max_length=20)  # JSON or REVIEW_REPORT
    payload_hash = models.CharField(max_length=64, db_index=True)
    source_voucher_hash = models.CharField(max_length=64, blank=True, default='')
    exported_payload = models.JSONField(default=dict)
    summary = models.JSONField(default=dict, blank=True)
    exported_at = models.DateTimeField(auto_now_add=True, db_index=True)
    exported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gst_exported_snapshots'
    )

    class Meta:
        ordering = ['-exported_at']
        indexes = [
            models.Index(fields=['company', 'return_type', 'return_period']),
            models.Index(fields=['payload_hash']),
        ]

    def __str__(self):
        return f"{self.company.name} {self.return_type} ({self.return_period}) [{self.export_format}] - {self.payload_hash[:12]}"

    objects = ProtectedGSTSnapshotQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Statutory Compliance Invariant: GST workspace export snapshots are immutable historical records and cannot be deleted."
        )


# =============================================================================
# Statutory Audit Deletion Protection Signals (Multi-Layer Defense)
# =============================================================================

@receiver(pre_delete, sender=GSTReportingAllocation)
def protect_gst_allocation_pre_delete(sender, instance, **kwargs):
    if instance.status in ['APPROVED', 'REPORTED', 'FILED'] or instance.is_active:
        raise ValidationError(
            f"Statutory Compliance Invariant: Cannot delete active or reported GST reporting allocation '{instance.id}'."
        )
    if instance.supersedes.exists() or instance.superseded_by:
        raise ValidationError(
            f"Statutory Compliance Invariant: Cannot delete historical allocation '{instance.id}' in supersession chain."
        )


@receiver(pre_delete, sender=GSTWorkspaceExportSnapshot)
def protect_gst_snapshot_pre_delete(sender, instance, **kwargs):
    raise ValidationError(
        "Statutory Compliance Invariant: GST workspace export snapshots are immutable historical records and cannot be deleted."
    )


@receiver(pre_delete, sender=GSTReturnWorkspace)
def protect_gst_workspace_pre_delete(sender, instance, **kwargs):
    if instance.status in ['EXPORTED', 'FILED', 'REVIEWED']:
        raise ValidationError(
            f"Statutory Audit Invariant: Cannot delete GST return workspace for period '{instance.return_period}' "
            f"in '{instance.status}' status. Historical tax returns and signed-off workspaces are immutable."
        )


@receiver(pre_delete, sender=GSTFilingRecord)
def protect_gst_filing_record_pre_delete(sender, instance, **kwargs):
    if instance.status in ['FILED', 'SUBMITTED', 'SUBMITTING']:
        raise ValidationError(
            f"Statutory Audit Invariant: Cannot delete GST filing record '{instance.id}' in '{instance.status}' status."
        )



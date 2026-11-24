import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Dict
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.encryption import EncryptedTextField


@dataclass(frozen=True)
class DocumentFinancialEffect:
    document_kind: str          # 'INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE', 'UNKNOWN'
    financial_sign: int         # +1, -1, 0
    is_credit_note: bool
    is_debit_note: bool
    is_review_required: bool
    reason: str


def resolve_document_financial_effect(record_or_dict: Any) -> DocumentFinancialEffect:
    """
    Canonical Financial & Document Type Resolver for GST Invoices, Credit Notes, and Debit Notes.
    Accurately distinguishes CDNR credit notes ('C') from CDNR debit notes ('D').
    Prevents negative inversion of debit notes.
    Flags records with missing or ambiguous note_type as REVIEW_REQUIRED with financial_sign=0.
    """
    if hasattr(record_or_dict, 'document_type'):
        doc_type = (getattr(record_or_dict, 'document_type', None) or '').strip().upper()
        note_type = (getattr(record_or_dict, 'note_type', None) or '').strip().upper()
    elif isinstance(record_or_dict, dict):
        doc_type = (record_or_dict.get('document_type') or record_or_dict.get('doctype') or '').strip().upper()
        note_type = (record_or_dict.get('note_type') or record_or_dict.get('ntty') or '').strip().upper()
    else:
        doc_type = ''
        note_type = ''

    # Credit Note / Debit Note sections (CDNR, CDNRA)
    if doc_type in ['CDNR', 'CDNRA'] or note_type in ['C', 'CR', 'CREDIT', 'D', 'DR', 'DEBIT']:
        if note_type in ['C', 'CR', 'CREDIT']:
            return DocumentFinancialEffect(
                document_kind='CREDIT_NOTE',
                financial_sign=-1,
                is_credit_note=True,
                is_debit_note=False,
                is_review_required=False,
                reason='Credit note reduces recipient ITC balance'
            )
        elif note_type in ['D', 'DR', 'DEBIT']:
            return DocumentFinancialEffect(
                document_kind='DEBIT_NOTE',
                financial_sign=1,
                is_credit_note=False,
                is_debit_note=True,
                is_review_required=False,
                reason='Debit note increases recipient ITC balance'
            )
        else:
            return DocumentFinancialEffect(
                document_kind='UNKNOWN',
                financial_sign=0,
                is_credit_note=False,
                is_debit_note=False,
                is_review_required=True,
                reason=f"Ambiguous or missing note_type '{note_type}' on {doc_type} record"
            )

    # Standard B2B / B2BA tax invoices
    if doc_type in ['B2B', 'B2BA', 'INV', 'INVOICE', ''] and not note_type:
        return DocumentFinancialEffect(
            document_kind='INVOICE',
            financial_sign=1,
            is_credit_note=False,
            is_debit_note=False,
            is_review_required=False,
            reason='Standard B2B tax invoice'
        )

    # Fallback to standard positive invoice
    return DocumentFinancialEffect(
        document_kind='INVOICE',
        financial_sign=1,
        is_credit_note=False,
        is_debit_note=False,
        is_review_required=False,
        reason='Default positive financial effect'
    )


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
    
    FILING_FREQUENCY_CHOICES = (
        ('MONTHLY', 'Monthly'),
        ('QRMP', 'Quarterly (QRMP)'),
        ('UNKNOWN', 'Unknown'),
    )

    taxpayer_type = models.CharField(max_length=30, choices=TAXPAYER_TYPE_CHOICES, default='REGULAR')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    filing_frequency = models.CharField(
        max_length=20,
        choices=FILING_FREQUENCY_CHOICES,
        default='MONTHLY',
        db_index=True,
        help_text="GSTR-1 / GSTR-2B compliance frequency: MONTHLY or QRMP (Quarterly)"
    )
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

    def has_active_portal_session(self) -> bool:
        from django.utils import timezone
        return bool(self.auth_token and (not self.token_expires_at or self.token_expires_at > timezone.now()))

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
        ('NOT_REQUESTED', 'Not Requested'),
        ('PROCESSING', 'Processing'),
        ('FETCHED', 'Fetched'),
        ('IMPORTED', 'Imported'),
        ('PROCESSED', 'Processed'),
        ('EMPTY_PROCESSED', 'Empty Processed (No Invoices Reported)'),
        ('REQUEST_FAILED', 'Request Failed'),
        ('INVALID_PAYLOAD', 'Invalid Payload'),
        ('REVIEW_REQUIRED', 'Review Required'),
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
    provider_records_count = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_unchanged = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    period_records_count = models.PositiveIntegerField(default=0)
    is_empty_statement = models.BooleanField(default=False, db_index=True)
    source_info = models.CharField(max_length=100, blank=True, default='')
    
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
        ('REVIEW_REQUIRED', 'Review Required'),
        ('LATER_PERIOD_MATCH', 'Matched in Later Period'),
        ('AMENDED', 'Amended in Later Period'),
        ('CDNR_LATER_PERIOD', 'Credit/Debit Note in Later Period'),
        ('NOT_YET_REFLECTED', 'Not Yet Reflected in 2B'),
        ('DATA_UNAVAILABLE', 'Statement Data Unavailable'),
        ('UNMAPPED_GSTIN', 'Unmapped GSTIN'),
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
    return_period = models.CharField(max_length=10, db_index=True, blank=True, default='')
    document_type = models.CharField(max_length=10, default='B2B', db_index=True)  # B2B, B2BA, CDNR, CDNRA
    original_document_number = models.CharField(max_length=100, blank=True, default='')
    original_document_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, db_index=True)
    normalized_invoice_number = models.CharField(max_length=100, db_index=True)
    invoice_type = models.CharField(max_length=10, default='R')  # Regular, Deemed, SEZ, etc.
    invoice_date = models.DateField(null=True, blank=True)
    raw_invoice_date = models.CharField(max_length=100, blank=True, default='')
    note_type = models.CharField(max_length=5, blank=True, default='')  # 'C' = Credit Note, 'D' = Debit Note
    is_amendment = models.BooleanField(default=False)
    amendment_return_period = models.CharField(max_length=10, blank=True, default='')
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
    gstr3b_filing_date = models.DateField(null=True, blank=True, help_text="Date supplier filed GSTR-3B")
    gstr3b_filing_arn = models.CharField(max_length=50, blank=True, default="", help_text="Filing ARN for GSTR-3B")
    gstr3b_return_period = models.CharField(max_length=7, blank=True, default="", help_text="Return period of GSTR-3B (MMYYYY)")
    gstr3b_verification_source = models.CharField(max_length=50, blank=True, default="", help_text="Source of GSTR-3B status (API, PORTAL, MANUAL_EVIDENCE, etc.)")
    gstr3b_verified_at = models.DateTimeField(null=True, blank=True)
    
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

    def is_gstr3b_stale(self, threshold_days: int = 30) -> bool:
        """
        Evidence Freshness Rule for GSTR-2B GSTR-3B status:
        Returns True if GSTR-3B verification is older than threshold_days and not conclusively verified filed with ARN.
        Stale evidence must be treated as DATA_UNAVAILABLE until re-verified.
        """
        if self.gstr3b_status == 'FILED' and self.gstr3b_filing_arn and self.gstr3b_filing_date:
            return False
        if not self.gstr3b_verified_at:
            return True
        age = (timezone.now() - self.gstr3b_verified_at).days
        return age > threshold_days

    @property
    def financial_effect(self) -> DocumentFinancialEffect:
        return resolve_document_financial_effect(self)

    @property
    def is_credit_note(self) -> bool:
        return self.financial_effect.is_credit_note

    @property
    def is_debit_note(self) -> bool:
        return self.financial_effect.is_debit_note

    @property
    def signed_taxable_value(self) -> Decimal:
        val = Decimal(str(self.taxable_value or 0))
        return val * self.financial_effect.financial_sign

    @property
    def signed_total_tax(self) -> Decimal:
        tax = (
            Decimal(str(self.igst_amount or 0)) +
            Decimal(str(self.cgst_amount or 0)) +
            Decimal(str(self.sgst_amount or 0)) +
            Decimal(str(self.cess_amount or 0))
        )
        return tax * self.financial_effect.financial_sign

    @property
    def signed_cgst(self) -> Decimal:
        return Decimal(str(self.cgst_amount or 0)) * self.financial_effect.financial_sign

    @property
    def signed_sgst(self) -> Decimal:
        return Decimal(str(self.sgst_amount or 0)) * self.financial_effect.financial_sign

    @property
    def signed_igst(self) -> Decimal:
        return Decimal(str(self.igst_amount or 0)) * self.financial_effect.financial_sign

    @property
    def signed_cess(self) -> Decimal:
        return Decimal(str(self.cess_amount or 0)) * self.financial_effect.financial_sign

    class Meta:
        indexes = [
            models.Index(fields=['company', 'supplier_gstin', 'normalized_invoice_number']),
            models.Index(fields=['company', 'match_status']),
            models.Index(fields=['company', 'return_period']),
            models.Index(fields=['company', 'gst_registration', 'return_period']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'gst_registration', 'return_period', 'supplier_gstin', 'normalized_invoice_number', 'document_type', 'original_document_number'],
                name='unique_gstr2b_logical_doc_with_reg',
                condition=models.Q(gst_registration__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['company', 'return_period', 'supplier_gstin', 'normalized_invoice_number', 'document_type', 'original_document_number'],
                name='unique_gstr2b_logical_doc_null_reg',
                condition=models.Q(gst_registration__isnull=True)
            ),
        ]

    def __str__(self):
        return f"{self.supplier_gstin} - {self.invoice_number} (₹{self.invoice_value}) - {self.match_status}"


class GSTR2BSyncAttempt(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('SUCCESS', 'Success'),
        ('PARTIAL_SUCCESS', 'Partial Success'),
        ('FAILED', 'Failed'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gstr2b_sync_attempts')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gstr2b_sync_attempts'
    )
    return_period = models.CharField(max_length=10, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS')
    total_invoices_ingested = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_unchanged = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'return_period', 'status']),
        ]

    def __str__(self):
        return f"Sync {self.company.name} - {self.return_period} ({self.status})"


class GSTR2BIngestionLock(models.Model):
    """
    Parent synchronization lock row keyed by company, registration, and return period.
    Used with select_for_update() inside transaction.atomic() to serialize concurrent
    ingestion workers for the same statement window without deadlock.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gstr2b_ingestion_locks')
    gst_registration = models.ForeignKey(
        GSTRegistration,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='gstr2b_ingestion_locks'
    )
    return_period = models.CharField(max_length=10, db_index=True)
    locked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'gst_registration', 'return_period'],
                name='unique_gstr2b_lock_with_reg',
                condition=models.Q(gst_registration__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['company', 'return_period'],
                name='unique_gstr2b_lock_null_reg',
                condition=models.Q(gst_registration__isnull=True)
            ),
        ]

    def __str__(self):
        return f"Lock {self.company.name} - {self.return_period}"


class SupplierGSTR3BFilingRecord(models.Model):
    """
    Statutory evidence record tracking supplier GSTR-3B return filings.
    Under Section 16(2)(c) and Rule 37A, GSTR-1 outward reporting is NOT proof of tax payment.
    Proof of GSTR-3B return discharge must be maintained with ARN, filing date, and verified source.
    """
    STATUS_CHOICES = (
        ('VERIFIED_FILED', 'Verified Filed in GSTR-3B'),
        ('VERIFIED_NOT_FILED', 'Verified Not Filed'),
        ('DATA_UNAVAILABLE', 'Data Unavailable from GSTN / Provider'),
        ('MANUALLY_CONFIRMED', 'Manually Confirmed by User / Tax Auditor'),
        ('PENDING', 'Pending Verification from GST Portal'),
        ('UNKNOWN', 'Unknown / Unchecked'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='supplier_gstr3b_records', db_index=True)
    supplier_gstin = models.CharField(max_length=15, db_index=True)
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    return_period = models.CharField(max_length=7, db_index=True)  # MMYYYY format
    financial_year = models.CharField(max_length=9, blank=True, default='')  # e.g. 2024-25
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DATA_UNAVAILABLE', db_index=True)
    filing_date = models.DateField(null=True, blank=True)
    arn = models.CharField(max_length=50, blank=True, default='')
    verification_source = models.CharField(max_length=50, default='API')
    evidence_document_ref = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    verified_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_supplier_gstr3b_records'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'supplier_gstin', 'return_period']),
            models.Index(fields=['company', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'supplier_gstin', 'return_period'],
                name='unique_supplier_gstr3b_record'
            )
        ]

    def is_stale(self, threshold_days: int = 30) -> bool:
        """
        Statutory Evidence Freshness Rule:
        Returns True if verification is older than threshold_days and not conclusively verified filed.
        Stale evidence must be treated as DATA_UNAVAILABLE until re-verified from GSTN.
        """
        if self.status == 'VERIFIED_FILED' and self.arn and self.filing_date:
            return False  # Once filed with ARN, filing status is an immutable historical fact
        if not self.verified_at:
            return True
        age = (timezone.now() - self.verified_at).days
        return age > threshold_days

    def __str__(self):
        return f"{self.supplier_gstin} - {self.return_period}: {self.status} (ARN: {self.arn or 'None'})"


class Rule37AManualFilingEvidence(models.Model):
    """
    Dedicated, authoritative persisted record for Rule 37A manual filing verification.
    Required by Section 16(2)(c) and Rule 37A to prevent unauthenticated, unpersisted,
    or arbitrary string-based manual reclaim authorizations.
    """
    DOCUMENT_TYPE_CHOICES = (
        ('CA_CERTIFICATE', 'Chartered Accountant Certificate'),
        ('TAX_CHALLAN_CIN', 'Tax Payment Challan (CIN)'),
        ('VENDOR_AFFIDAVIT', 'Vendor Sworn Affidavit'),
        ('PORTAL_SCREENSHOT', 'Direct Portal Filing Proof'),
        ('OTHER', 'Other Statutory Proof'),
    )

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Approval'),
        ('APPROVED', 'Approved by Authorized Verifier'),
        ('REJECTED', 'Rejected'),
        ('INVALIDATED', 'Invalidated / Superseded'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='rule37a_manual_evidences', db_index=True)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='rule37a_manual_evidences', db_index=True)
    supplier_gstin = models.CharField(max_length=15, db_index=True)
    return_period = models.CharField(max_length=7, db_index=True)  # Normalized MMYYYY
    evidence_document_type = models.CharField(max_length=50, default='CA_CERTIFICATE', choices=DOCUMENT_TYPE_CHOICES)
    evidence_document_ref = models.CharField(max_length=255)
    verification_reason = models.TextField()
    status = models.CharField(max_length=20, default='DRAFT', choices=STATUS_CHOICES, db_index=True)
    verifier_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='rule37a_verified_evidences'
    )
    verifier_role = models.CharField(max_length=50, blank=True, default='')
    verification_timestamp = models.DateTimeField(default=timezone.now)
    evidence_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    initial_fingerprint = models.CharField(max_length=64, blank=True, default='', db_index=True)
    is_self_approved = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rule37a_manual_evidences_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rule37a_manual_evidences_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rule37a_manual_evidences_rejected'
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    invalidated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rule37a_manual_evidences_invalidated'
    )
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidation_reason = models.TextField(blank=True, default='')

    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='superseded_by_records'
    )

    class Meta:
        indexes = [
            models.Index(fields=['company', 'voucher', 'status']),
            models.Index(fields=['company', 'supplier_gstin', 'return_period']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['voucher', 'return_period'],
                condition=models.Q(status='APPROVED'),
                name='unique_active_approved_manual_evidence_per_voucher_period'
            )
        ]

    def compute_fingerprint(self) -> str:
        raw_payload = (
            f"{str(self.company_id)}|{str(self.voucher_id)}|{self.supplier_gstin.strip().upper()}|"
            f"{self.return_period.strip()}|MANUAL|{self.status.strip().upper()}|"
            f"{self.evidence_document_type.strip()}|"
            f"{self.evidence_document_ref.strip()}|"
            f"{self.verification_timestamp.isoformat() if self.verification_timestamp else ''}"
        )
        return hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        # Preserve original evidence fingerprint permanently; do NOT overwrite on updates
        if self.pk:
            orig = Rule37AManualFilingEvidence.objects.filter(pk=self.pk).values('evidence_hash', 'initial_fingerprint').first()
            if orig and orig['evidence_hash']:
                self.evidence_hash = orig['evidence_hash']
            if orig and orig['initial_fingerprint']:
                self.initial_fingerprint = orig['initial_fingerprint']
        if not self.initial_fingerprint:
            self.initial_fingerprint = self.compute_fingerprint()
        if not self.evidence_hash:
            self.evidence_hash = self.initial_fingerprint
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ManualEvidence #{self.id} [{self.status}] Voucher:{self.voucher_id} Period:{self.return_period}"


class ImmutableAuditEventQuerySet(models.QuerySet):
    """
    Immutable queryset for Rule37AManualEvidenceAuditEvent.
    Blocks bulk mutation and bulk deletion to preserve tamper-evident audit trails under Section 155.
    """
    def update(self, **kwargs):
        raise ValidationError("Rule37AManualEvidenceAuditEvent records are strictly immutable and cannot be updated via queryset.")

    def delete(self):
        raise ValidationError("Rule37AManualEvidenceAuditEvent records are strictly immutable and cannot be deleted via queryset.")


class ImmutableAuditEventManager(models.Manager):
    def get_queryset(self):
        return ImmutableAuditEventQuerySet(self.model, using=self._db)


class Rule37AManualEvidenceAuditEvent(models.Model):
    """
    Cryptographically chained, immutable audit event record for Rule 37A manual evidence lifecycle.
    Guarantees tamper-evident traceability under Section 155 of the CGST Act, 2017.
    Every state transition (CREATED, SUBMITTED, APPROVED, REJECTED, INVALIDATED, SUPERSEDED)
    generates a permanent, cryptographically linked entry.
    """
    ACTION_CHOICES = (
        ('CREATED', 'Evidence Created in DRAFT'),
        ('SUBMITTED', 'Submitted for Verification Approval'),
        ('APPROVED', 'Statutorily Approved by Authorized Verifier'),
        ('REJECTED', 'Rejected by Authorized Verifier'),
        ('INVALIDATED', 'Invalidated / Withdrawn with Documented Cause'),
        ('SUPERSEDED', 'Superseded by Corrected Evidence Record'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence = models.ForeignKey(
        Rule37AManualFilingEvidence,
        on_delete=models.CASCADE,
        related_name='audit_events',
        db_index=True
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='rule37a_evidence_audit_events',
        db_index=True
    )
    voucher = models.ForeignKey(
        Voucher,
        on_delete=models.CASCADE,
        related_name='rule37a_evidence_audit_events',
        db_index=True
    )
    supplier_gstin = models.CharField(max_length=15, db_index=True)
    return_period = models.CharField(max_length=7, db_index=True)
    document_ref = models.CharField(max_length=255)
    previous_state = models.CharField(max_length=20, blank=True, default='')
    new_state = models.CharField(max_length=20)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='rule37a_evidence_actions'
    )
    actor_role = models.CharField(max_length=50)
    event_timestamp = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True, default='')
    previous_event_hash = models.CharField(max_length=64, blank=True, default='')
    current_event_hash = models.CharField(max_length=64, db_index=True)
    sequence_number = models.PositiveIntegerField(default=1)

    objects = ImmutableAuditEventManager()

    class Meta:
        ordering = ['evidence', 'sequence_number']
        indexes = [
            models.Index(fields=['evidence', 'sequence_number']),
            models.Index(fields=['company', 'current_event_hash']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['evidence', 'sequence_number'],
                name='unique_evidence_event_sequence'
            ),
            models.UniqueConstraint(
                fields=['evidence', 'current_event_hash'],
                name='unique_evidence_event_hash'
            )
        ]

    def compute_event_hash(self) -> str:
        """
        Computes deterministic canonical SHA-256 fingerprint for this lifecycle transition.
        Chained to previous_event_hash.
        """
        raw_payload = (
            f"{self.sequence_number}|{str(self.evidence_id)}|{str(self.company_id)}|"
            f"{str(self.voucher_id)}|{self.supplier_gstin.strip().upper()}|"
            f"{self.return_period.strip()}|{self.document_ref.strip()}|"
            f"{self.previous_state.strip().upper()}|{self.new_state.strip().upper()}|"
            f"{self.action.strip().upper()}|{str(self.actor_user_id)}|{self.actor_role.strip().upper()}|"
            f"{self.event_timestamp.isoformat() if self.event_timestamp else ''}|"
            f"{self.previous_event_hash.strip()}"
        )
        return hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        # Strict immutability check
        if self.pk and Rule37AManualEvidenceAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("Rule37AManualEvidenceAuditEvent records are strictly immutable and cannot be updated.")
        if not self.current_event_hash:
            self.current_event_hash = self.compute_event_hash()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Rule37AManualEvidenceAuditEvent records are strictly immutable and cannot be deleted.")

    def __str__(self):
        return f"AuditEvent #{self.sequence_number} Evidence:{self.evidence_id} [{self.action}]"


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
            models.Index(fields=['company', 'gst_registration', 'return_type', 'return_period']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'gst_registration', 'return_type', 'return_period'],
                name='unique_company_reg_return_identity'
            ),
            models.UniqueConstraint(
                fields=['company', 'return_type', 'return_period'],
                condition=models.Q(gst_registration__isnull=True),
                name='unique_company_null_reg_return_identity'
            ),
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
    source_reversal = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='direct_reclaims'
    )
    payment_allocation = models.ForeignKey(
        'accounting.PaymentAllocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gst_reclaim_allocations'
    )
    payment_event_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    payment_reference = models.CharField(max_length=100, blank=True, default='')
    payment_fingerprint = models.CharField(max_length=64, blank=True, default='', db_index=True)
    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='supersedes'
    )
    superseded_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)

    # Rule 37A Statutory Evidence & Provenance Audit Trail
    evidence_source = models.CharField(max_length=50, blank=True, default='')
    evidence_status = models.CharField(max_length=30, blank=True, default='')
    evidence_supplier_gstin = models.CharField(max_length=15, blank=True, default='', db_index=True)
    evidence_return_period = models.CharField(max_length=7, blank=True, default='', db_index=True)
    evidence_verified_at = models.DateTimeField(null=True, blank=True)
    evidence_document_ref = models.CharField(max_length=255, blank=True, default='')
    evidence_arn = models.CharField(max_length=50, blank=True, default='')
    evidence_filing_date = models.DateField(null=True, blank=True)
    evidence_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    evidence_metadata = models.JSONField(default=dict, blank=True)

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
            models.Index(fields=['company', 'payment_event_id']),
            models.Index(fields=['company', 'payment_fingerprint']),
            models.Index(fields=['company', 'evidence_supplier_gstin', 'evidence_return_period']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['voucher', 'event_type'],
                condition=models.Q(is_active=True) & ~models.Q(event_type__in=['ITC_RECLAIM', 'ITC_REVERSAL_RULE_37']),
                name='unique_active_allocation_per_voucher_event'
            ),
            models.UniqueConstraint(
                fields=['company', 'payment_event_id'],
                condition=models.Q(is_active=True) & ~models.Q(payment_event_id=''),
                name='unique_active_reclaim_per_company_payment_event'
            ),
        ]

    def __str__(self):
        return f"[{self.assigned_period}] {self.voucher.voucher_number} - {self.event_type} ({self.status}) Eligible={self.is_statutorily_eligible}"


class GSTReversalReclaimLineage(models.Model):
    """
    Audit-grade foreign key event linkage connecting an ITC Reclaim allocation
    to the specific prior Reversal allocation(s) that it restores.
    Tracks exact tax breakdown (IGST, CGST, SGST, Cess) and preserves mathematical equilibrium.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='gst_reclaim_lineages')
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT, related_name='gst_reclaim_lineages')
    reversal_allocation = models.ForeignKey(
        GSTReportingAllocation,
        on_delete=models.PROTECT,
        related_name='reclaim_lineages_as_reversal'
    )
    reclaim_allocation = models.ForeignKey(
        GSTReportingAllocation,
        on_delete=models.PROTECT,
        related_name='reclaim_lineages_as_reclaim'
    )
    reclaimed_tax = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_reclaimed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_reclaimed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_reclaimed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_reclaimed = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    statutory_rule = models.CharField(max_length=20, default='RULE_37')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_gst_lineages'
    )

    class Meta:
        indexes = [
            models.Index(fields=['company', 'voucher']),
            models.Index(fields=['reversal_allocation', 'reclaim_allocation']),
        ]

    def __str__(self):
        return f"Lineage {self.voucher.voucher_number}: Reversal {self.reversal_allocation_id} -> Reclaim {self.reclaim_allocation_id} (₹{self.reclaimed_tax})"


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



import uuid
from django.db import models
from django.conf import settings
from apps.companies.models import Company
from apps.accounting.models import Voucher



class CompanyGSTConfig(models.Model):
    PROVIDER_CHOICES = (
        ('MOCK', 'Mock / Sandbox Provider (Offline & Testing)'),
        ('CLEAR', 'Clear (ClearTax API Gateway)'),
        ('MASTERS_INDIA', 'Masters India GST Gateway'),
        ('CASHFREE', 'Cashfree Verification Gateway'),
        ('NIC_DIRECT', 'Direct NIC API (Government Portal)'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='gst_config')
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default='MOCK')
    is_sandbox = models.BooleanField(default=True)
    
    # API Gateway Credentials
    api_key = models.CharField(max_length=255, blank=True, default='')
    api_secret = models.CharField(max_length=255, blank=True, default='')
    
    # E-Way Bill NIC Credentials
    eway_username = models.CharField(max_length=100, blank=True, default='')
    eway_password = models.CharField(max_length=255, blank=True, default='')
    
    # E-Invoice NIC / IRP Credentials
    einvoice_username = models.CharField(max_length=100, blank=True, default='')
    einvoice_password = models.CharField(max_length=255, blank=True, default='')
    
    # Session / Bearer Token Cache
    auth_token = models.TextField(blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company.name} GST Config ({self.provider}, Sandbox={self.is_sandbox})"


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
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(GSTR2BImport, on_delete=models.CASCADE, related_name='records')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gstr2b_records', db_index=True)
    
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'supplier_gstin', 'normalized_invoice_number']),
        ]

    def __str__(self):
        return f"{self.supplier_gstin} - {self.invoice_number} (₹{self.invoice_value}) - {self.match_status}"


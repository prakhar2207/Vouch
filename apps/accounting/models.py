import uuid
from django.db import models
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger
from apps.inventory.models import Product

class FinancialYear(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='financial_years')
    name = models.CharField(max_length=50)  # e.g. "1-Apr-2026 to 31-Mar-2027" or "FY 2026-27"
    code = models.CharField(max_length=10)  # e.g. "26-27"
    start_date = models.DateField()         # e.g. 2026-04-01
    end_date = models.DateField()           # e.g. 2027-03-31
    is_closed = models.BooleanField(default=False)
    is_split_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('company', 'code')
        ordering = ['start_date']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class VoucherSequence(models.Model):
    VOUCHER_TYPE_CHOICES = (
        ('SALES', 'Sales'),
        ('PURCHASE', 'Purchase'),
        ('PAYMENT', 'Payment'),
        ('RECEIPT', 'Receipt'),
        ('CONTRA', 'Contra'),
        ('JOURNAL', 'Journal'),
        ('CREDIT_NOTE', 'Credit Note'),
        ('DEBIT_NOTE', 'Debit Note'),
        ('OPENING', 'Opening Balance'),
        ('OPENING_INVOICE', 'Opening Invoice'),
        ('OPENING_BILL', 'Opening Bill'),
    )

    METHOD_CHOICES = (
        ('AUTOMATIC', 'Automatic (Sequential)'),
        ('MANUAL', 'Manual Override'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='voucher_sequences')
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.CASCADE, related_name='sequences')
    voucher_type = models.CharField(max_length=20, choices=VOUCHER_TYPE_CHOICES)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='AUTOMATIC')
    prefix = models.CharField(max_length=10, default='INV')
    suffix = models.CharField(max_length=10, blank=True, default="")
    starting_number = models.PositiveIntegerField(default=1)
    last_number = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=4)  # Zero-padding width (e.g. 0001)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'financial_year', 'voucher_type')

    def __str__(self):
        return f"{self.company.name} | {self.financial_year.code} | {self.voucher_type} -> {self.last_number}"


class LedgerBalance(models.Model):
    TYPE_CHOICES = (
        ('DR', 'Debit'),
        ('CR', 'Credit'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ledger = models.ForeignKey(Ledger, on_delete=models.CASCADE, related_name='year_balances')
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.CASCADE, related_name='ledger_balances')
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    opening_type = models.CharField(max_length=2, choices=TYPE_CHOICES, default='DR')
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    closing_type = models.CharField(max_length=2, choices=TYPE_CHOICES, default='DR')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('ledger', 'financial_year')

    def __str__(self):
        return f"{self.ledger.name} | {self.financial_year.code} | Op: {self.opening_type} {self.opening_balance} | Cl: {self.closing_type} {self.closing_balance}"


class Voucher(models.Model):
    VOUCHER_TYPE_CHOICES = (
        ('CONTRA', 'Contra'),
        ('PAYMENT', 'Payment'),
        ('RECEIPT', 'Receipt'),
        ('JOURNAL', 'Journal'),
        ('SALES', 'Sales'),
        ('PURCHASE', 'Purchase'),
        ('CREDIT_NOTE', 'Credit Note'),
        ('DEBIT_NOTE', 'Debit Note'),
        ('OPENING', 'Opening Balance'),
        ('OPENING_INVOICE', 'Opening Invoice'),
        ('OPENING_BILL', 'Opening Bill'),
    )
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('VALIDATING', 'Validating'),
        ('POSTED', 'Posted'),
        ('CANCELLED', 'Cancelled'),
        ('SUPERSEDED', 'Superseded'),
        ('REVERSED', 'Reversed'),
        ('CORRECTED', 'Corrected'),
    )

    CORRECTION_TYPE_CHOICES = (
        ('CLERICAL', 'Clerical / Typo'),
        ('QUANTITY', 'Wrong Quantity'),
        ('RATE', 'Wrong Price / Rate'),
        ('PRODUCT', 'Wrong Product'),
        ('CUSTOMER', 'Wrong Customer Details'),
        ('GST', 'Wrong GST'),
        ('DATE', 'Wrong Date'),
        ('PAYMENT', 'Payment Adjustment'),
        ('OTHER', 'Other'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='vouchers')
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name='vouchers')
    voucher_type = models.CharField(max_length=20, choices=VOUCHER_TYPE_CHOICES)
    voucher_number = models.CharField(max_length=100)
    external_invoice_number = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    reversal_voucher = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reverses_vouchers')
    corrects_voucher = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='corrected_by_vouchers')
    
    # Revision / History relationships (P0 & P1)
    revision_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='revisions')
    superseded_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='supersedes')
    revision_number = models.PositiveIntegerField(default=1)
    correction_reason = models.TextField(null=True, blank=True)
    correction_type = models.CharField(max_length=30, choices=CORRECTION_TYPE_CHOICES, null=True, blank=True)
    corrected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='voucher_corrections')
    corrected_at = models.DateTimeField(null=True, blank=True)
    voucher_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, null=True, blank=True)
    party_ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, null=True, blank=True, related_name='party_vouchers')
    
    # Ad-hoc Buyer Details for Cash / Counter Sales (decoupled from Sundry Debtors)
    buyer_name = models.CharField(max_length=255, null=True, blank=True)
    buyer_address = models.TextField(null=True, blank=True)
    buyer_gstin = models.CharField(max_length=15, null=True, blank=True)
    buyer_state_code = models.CharField(max_length=10, null=True, blank=True)
    buyer_phone = models.CharField(max_length=20, null=True, blank=True)
    
    narration = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    attachment_data = models.TextField(null=True, blank=True)
    attachment_mime = models.CharField(max_length=100, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_vouchers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'financial_year', 'voucher_number')
        indexes = [
            models.Index(fields=['company', 'financial_year', 'voucher_number']),
            models.Index(fields=['company', 'voucher_date']),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.status == 'POSTED' and self.pk:
            entries = self.ledger_entries.all()
            if entries.exists():
                total_dr = sum(e.debit_amount for e in entries)
                total_cr = sum(e.credit_amount for e in entries)
                if total_dr != total_cr:
                    raise ValidationError(f"Double-entry constraint violated: Total Debit ({total_dr}) does not equal Total Credit ({total_cr}).")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.voucher_number} - {self.company.name}"

class VoucherItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='voucher_items')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='voucher_items')
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    rate = models.DecimalField(max_digits=15, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Historical Tax Snapshots
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    cess_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    igst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    cess_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    hsn_code = models.CharField(max_length=50, null=True, blank=True)
    
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name='chk_voucher_item_quantity_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gte=0),
                name='chk_voucher_item_rate_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(discount_percent__gte=0) & models.Q(discount_percent__lte=100),
                name='chk_voucher_item_discount_pct_range'
            ),
        ]
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity} on {self.voucher.voucher_number}"

class LedgerEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ledger_entries', null=True, blank=True)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='ledger_entries')
    ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name='entries')
    debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    narration = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit_amount__gte=0),
                name='chk_ledger_entry_debit_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(credit_amount__gte=0),
                name='chk_ledger_entry_credit_positive'
            ),
            models.CheckConstraint(
                condition=~(models.Q(debit_amount__gt=0) & models.Q(credit_amount__gt=0)),
                name='chk_ledger_entry_not_both_dr_and_cr'
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'ledger', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.company_id and self.voucher_id:
            self.company_id = self.voucher.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"VCH: {self.voucher.voucher_number} | LDR: {self.ledger.name} | DR: {self.debit_amount} | CR: {self.credit_amount}"


class PaymentAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payment_allocations')
    payment_voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='allocations_made')
    invoice_voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='allocations_received')
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gt=0),
                name='chk_payment_allocation_positive'
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'payment_voucher']),
            models.Index(fields=['company', 'invoice_voucher']),
        ]

    def __str__(self):
        return f"Allocation: {self.payment_voucher.voucher_number} -> {self.invoice_voucher.voucher_number} (₹{self.allocated_amount})"


class OfflineCommand(models.Model):
    STATUS_CHOICES = (
        ('RECEIVED', 'Received'),
        ('PROCESSING', 'Processing'),
        ('PROCESSED', 'Processed'),
        ('FAILED', 'Failed'),
        ('CONFLICT', 'Conflict'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    command_id = models.CharField(max_length=100, unique=True, db_index=True)
    device_id = models.CharField(max_length=100, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='offline_commands')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='offline_commands')
    command_type = models.CharField(max_length=50)  # e.g., 'CREATE_SALE', 'CREATE_PURCHASE', 'CREATE_PAYMENT'
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RECEIVED')
    result_voucher = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='originating_command')
    error_code = models.CharField(max_length=50, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    failed_at = models.DateTimeField(null=True, blank=True)
    client_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['company', 'command_type', 'status']),
        ]

    def __str__(self):
        return f"Command {self.command_id} ({self.command_type}) - {self.status}"


class InwardVoucherRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('DISPUTED', 'Disputed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='outgoing_edi_requests')
    target_company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='incoming_edi_requests')
    source_voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='edi_requests')
    payload = models.JSONField(help_text="Snapshot of invoice lines, amounts, taxes, HSN codes")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    digital_signature_hash = models.CharField(max_length=64, null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    created_purchase_voucher = models.OneToOneField(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='inward_edi_request')
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"EDI #{self.id} | {self.source_company.name} -> {self.target_company.name} ({self.status})"


class BankStatementImport(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('PARTIAL', 'Partial with Warnings'),
        ('FAILED', 'Failed'),
    )

    FORMAT_CHOICES = (
        ('CSV', 'CSV Statement'),
        ('XLSX', 'Excel Spreadsheet (XLSX)'),
        ('XLS', 'Excel Spreadsheet (XLS)'),
        ('PDF', 'PDF Statement'),
        ('IMAGE', 'Scanned Statement / Image'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='bank_statement_imports')
    bank_ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name='statement_imports')
    source_file_name = models.CharField(max_length=255)
    file_format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='CSV')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_rows = models.PositiveIntegerField(default=0)
    successful_rows = models.PositiveIntegerField(default=0)
    unresolved_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    error_summary = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bank_imports')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'bank_ledger', '-created_at']),
        ]

    def __str__(self):
        return f"Import {self.source_file_name} ({self.status}) - {self.successful_rows}/{self.total_rows} rows"


class BankTransaction(models.Model):
    STATUS_CHOICES = (
        ('UNPROCESSED', 'Unprocessed'),
        ('MATCHED_AUTO', 'Matched (Automatic)'),
        ('MATCHED_SUGGESTED', 'Matched (Suggested)'),
        ('UNRESOLVED', 'Unresolved'),
        ('RECONCILED', 'Reconciled'),
        ('IGNORED', 'Ignored'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='bank_transactions')
    statement_import = models.ForeignKey(BankStatementImport, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    bank_ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name='bank_transactions')
    transaction_date = models.DateField(db_index=True)
    value_date = models.DateField(null=True, blank=True)
    description = models.TextField()
    normalized_narration = models.CharField(max_length=500, db_index=True)
    reference_number = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    fingerprint = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    source_file = models.CharField(max_length=255, blank=True)
    source_page = models.IntegerField(null=True, blank=True)
    extraction_confidence = models.FloatField(default=1.0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='UNPROCESSED', db_index=True)
    matched_party = models.ForeignKey(Ledger, on_delete=models.SET_NULL, null=True, blank=True, related_name='matched_bank_transactions')
    matched_voucher = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciled_bank_transactions')
    matched_invoice = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice_bank_transactions')
    match_confidence = models.FloatField(default=0.0)
    match_notes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'transaction_date']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'reference_number']),
            models.Index(fields=['company', 'bank_ledger']),
            models.Index(fields=['company', 'fingerprint']),
        ]

    def __str__(self):
        amount = self.credit_amount if self.credit_amount > 0 else -self.debit_amount
        return f"{self.transaction_date} | ₹{amount} | {self.normalized_narration[:40]} ({self.status})"


class PartyMapping(models.Model):
    MAPPING_TYPE_CHOICES = (
        ('UPI', 'UPI ID'),
        ('BANK_ACCOUNT', 'Bank Account / IFSC'),
        ('NARRATION', 'Narration Keyword / Entity'),
        ('EXPENSE_CATEGORY', 'Expense Category'),
        ('RECURRING_CHARGE', 'Recurring Charge'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='party_mappings')
    pattern = models.CharField(max_length=255)
    normalized_pattern = models.CharField(max_length=255, db_index=True)
    party = models.ForeignKey(Ledger, on_delete=models.CASCADE, related_name='learned_mappings')
    mapping_type = models.CharField(max_length=50, choices=MAPPING_TYPE_CHOICES, default='NARRATION')
    confirmed_by_user = models.BooleanField(default=True)
    confidence = models.FloatField(default=1.0)
    usage_count = models.PositiveIntegerField(default=1)
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'normalized_pattern', 'mapping_type')
        indexes = [
            models.Index(fields=['company', 'mapping_type', 'normalized_pattern']),
        ]

    def __str__(self):
        return f"{self.pattern} -> {self.party.name} ({self.mapping_type}, count={self.usage_count})"


class AccountingFinding(models.Model):
    SEVERITY_CHOICES = (
        ('CRITICAL', 'Critical'),
        ('WARNING', 'Warning'),
        ('INFO', 'Info'),
    )

    CATEGORY_CHOICES = (
        ('TRIAL_BALANCE', 'Trial Balance Equilibrium'),
        ('WRONG_PARTY', 'Possible Wrong Party'),
        ('DUPLICATE', 'Duplicate Invoices/Bills'),
        ('BANK', 'Bank Reconciliation Mismatch'),
        ('PAYMENT', 'Payment Allocation Anomaly'),
        ('GST', 'GST Rate or State Mismatch'),
        ('INVENTORY', 'Inventory & Stock Discrepancy'),
        ('OPENING_BALANCE', 'Opening Balance Discrepancy'),
        ('NUMBERING', 'Voucher Numbering Sequence'),
        ('UNUSUAL_ACTIVITY', 'Unusual Business Activity'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='accounting_findings')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, db_index=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    expected_state = models.TextField(blank=True)
    actual_state = models.TextField(blank=True)
    probable_cause = models.TextField(blank=True)
    suggested_action = models.TextField(blank=True)
    confidence = models.FloatField(default=0.90)
    fix_action = models.CharField(max_length=50, null=True, blank=True)
    fix_preview = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_findings')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'is_resolved', 'severity']),
            models.Index(fields=['company', 'category']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title} ({self.category})"

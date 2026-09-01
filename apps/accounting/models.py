import uuid
from django.db import models
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger
from apps.inventory.models import Product

class Voucher(models.Model):
    VOUCHER_TYPE_CHOICES = (
        ('CONTRA', 'Contra'),
        ('PAYMENT', 'Payment'),
        ('RECEIPT', 'Receipt'),
        ('JOURNAL', 'Journal'),
        ('SALES', 'Sales'),
        ('PURCHASE', 'Purchase'),
    )
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('VALIDATING', 'Validating'),
        ('POSTED', 'Posted'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='vouchers')
    voucher_type = models.CharField(max_length=20, choices=VOUCHER_TYPE_CHOICES)
    voucher_number = models.CharField(max_length=100)
    voucher_date = models.DateField()
    reference_number = models.CharField(max_length=100, null=True, blank=True)
    party_ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, null=True, blank=True, related_name='party_vouchers')
    narration = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    attachment_data = models.TextField(null=True, blank=True)
    attachment_mime = models.CharField(max_length=100, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_vouchers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'voucher_number')

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
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    rate = models.DecimalField(max_digits=15, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity} on {self.voucher.voucher_number}"

class LedgerEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='ledger_entries')
    ledger = models.ForeignKey(Ledger, on_delete=models.PROTECT, related_name='entries')
    debit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    narration = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"VCH: {self.voucher.voucher_number} | LDR: {self.ledger.name} | DR: {self.debit_amount} | CR: {self.credit_amount}"


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

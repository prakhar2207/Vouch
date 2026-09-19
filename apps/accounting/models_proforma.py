import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger
from apps.inventory.models import Product


class ProformaInvoice(models.Model):
    TYPE_CHOICES = (
        ('PROFORMA', 'Proforma Invoice'),
        ('QUOTATION', 'Quotation / Estimate'),
    )

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent to Customer'),
        ('ACCEPTED', 'Accepted'),
        ('CONVERTED', 'Converted to Tax Invoice'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='proforma_invoices')
    financial_year = models.ForeignKey(
        'accounting.FinancialYear',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='proforma_invoices'
    )
    proforma_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='PROFORMA')
    proforma_number = models.CharField(max_length=100, db_index=True)
    date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)

    # Customer / Party reference
    party_ledger = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='proforma_invoices'
    )

    # Ad-hoc / Walk-in Buyer Details
    buyer_name = models.CharField(max_length=255, null=True, blank=True)
    buyer_address = models.TextField(null=True, blank=True)
    buyer_gstin = models.CharField(max_length=15, null=True, blank=True)
    buyer_state_code = models.CharField(max_length=10, null=True, blank=True)
    buyer_phone = models.CharField(max_length=20, null=True, blank=True)
    buyer_email = models.CharField(max_length=100, null=True, blank=True)

    # Default sales & tax ledgers for conversion
    sales_ledger = models.ForeignKey(Ledger, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    cgst_ledger = models.ForeignKey(Ledger, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    sgst_ledger = models.ForeignKey(Ledger, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    igst_ledger = models.ForeignKey(Ledger, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    # Amounts
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_tax = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cartage_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    # Notes & Terms
    customer_notes = models.TextField(null=True, blank=True)
    terms_and_conditions = models.TextField(null=True, blank=True)

    # Status & Conversion Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    converted_voucher = models.ForeignKey(
        'accounting.Voucher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_proforma'
    )
    converted_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_proformas')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ('company', 'financial_year', 'proforma_number')
        indexes = [
            models.Index(fields=['company', 'proforma_number']),
            models.Index(fields=['company', 'date']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'proforma_type']),
        ]

    def __str__(self):
        doc_type = "PI" if self.proforma_type == 'PROFORMA' else "QTN"
        return f"{doc_type}: {self.proforma_number} - {self.buyer_name or (self.party_ledger.name if self.party_ledger else 'Customer')} (₹{self.total_amount})"

    @property
    def display_party_name(self) -> str:
        if self.buyer_name:
            return self.buyer_name
        if self.party_ledger:
            return self.party_ledger.name
        return "Walk-in Customer"


class ProformaItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proforma = models.ForeignKey(ProformaInvoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='proforma_items')
    item_name = models.CharField(max_length=255)
    hsn_code = models.CharField(max_length=20, blank=True, default="")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit = models.CharField(max_length=20, default='PCS')
    rate = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.item_name} ({self.quantity} {self.unit} @ ₹{self.rate})"

import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
from apps.companies.models import Company


class SubscriptionPlan(models.Model):
    """
    Authoritative commercial subscription plan definition.
    Single source of truth for pricing, billing interval, features, and limits.
    All prices are stored as integer paise (1 INR = 100 paise).
    """
    INTERVAL_CHOICES = (
        ('annual', 'Annual'),
        ('monthly', 'Monthly'),
    )

    id = models.CharField(max_length=50, primary_key=True, help_text="Plan code, e.g. starter, growth, pro_ai, enterprise")
    name = models.CharField(max_length=100)
    tagline = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    target_persona = models.CharField(max_length=150, blank=True, default="")
    billing_interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, default='annual')

    base_amount_paise = models.BigIntegerField(help_text="Base price in paise excluding tax")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'), help_text="GST percentage")
    tax_amount_paise = models.BigIntegerField(help_text="Tax amount in paise")
    total_amount_paise = models.BigIntegerField(help_text="Final payable amount in paise including GST")
    currency = models.CharField(max_length=10, default='INR')

    razorpay_plan_id = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    tier_order = models.PositiveIntegerField(default=1)

    # Feature flags and limits JSON
    features = models.JSONField(default=dict, blank=True, help_text="Dictionary of feature flags (e.g. rfm, forecast, pareto)")
    limits = models.JSONField(default=dict, blank=True, help_text="Dictionary of operational limits (e.g. ocr_fast_daily, ocr_deep_daily)")
    version = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tier_order', 'base_amount_paise']
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'

    def __str__(self):
        return f"{self.name} (₹{self.base_amount_rupees:.2f} / {self.billing_interval})"

    @property
    def base_amount_rupees(self) -> Decimal:
        return Decimal(self.base_amount_paise) / Decimal(100)

    @property
    def tax_amount_rupees(self) -> Decimal:
        return Decimal(self.tax_amount_paise) / Decimal(100)

    @property
    def total_amount_rupees(self) -> Decimal:
        return Decimal(self.total_amount_paise) / Decimal(100)


class Subscription(models.Model):
    """
    Tenant subscription linking a company workspace to an active commercial plan.
    Enforces subscription lifecycle, periods, renewals, and cancellations.
    """
    STATUS_CHOICES = (
        ('created', 'Created'),
        ('authenticated', 'Authenticated'),
        ('active', 'Active'),
        ('pending', 'Pending Renewal'),
        ('past_due', 'Past Due'),
        ('halted', 'Halted'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='subscriptions')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')

    billing_interval = models.CharField(max_length=20, default='annual')
    razorpay_subscription_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    razorpay_plan_id = models.CharField(max_length=100, blank=True, default="")

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='active', db_index=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(db_index=True)
    next_billing_at = models.DateTimeField(null=True, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.plan.name} ({self.status})"

    @property
    def is_currently_active(self) -> bool:
        if self.status != 'active':
            return False
        return self.current_period_end >= timezone.now()


class PaymentTransaction(models.Model):
    """
    SaaS payment transaction tracking Razorpay orders, payments, amounts, and signatures.
    Strictly isolated from tenant accounting vouchers and ledgers.
    """
    STATUS_CHOICES = (
        ('created', 'Order Created'),
        ('authorized', 'Authorized'),
        ('captured', 'Captured (Paid)'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_number = models.CharField(max_length=64, unique=True, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payment_transactions')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_transactions')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    razorpay_order_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default="", unique=True, null=True, db_index=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, default="")

    amount_paise = models.BigIntegerField(help_text="Amount in paise")
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='created', db_index=True)
    payment_method = models.CharField(max_length=50, blank=True, default="")
    signature_verified = models.BooleanField(default=False)
    failure_reason = models.TextField(blank=True, default="")

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_number} - {self.amount_rupees} INR ({self.status})"

    @property
    def amount_rupees(self) -> Decimal:
        return Decimal(self.amount_paise) / Decimal(100)


class BillingInvoice(models.Model):
    """
    SaaS subscription billing invoice issued by SriLekh to the customer.
    Separated from tenant customer accounting invoices.
    """
    STATUS_CHOICES = (
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('void', 'Void'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=64, unique=True, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='billing_invoices')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_invoices')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    transaction = models.OneToOneField(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')

    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_address = models.TextField(blank=True, default="")
    customer_gstin = models.CharField(max_length=15, blank=True, default="")

    plan_name = models.CharField(max_length=100)
    plan_description = models.TextField(blank=True, default="")
    billing_period_start = models.DateField()
    billing_period_end = models.DateField()

    taxable_amount_paise = models.BigIntegerField(help_text="Base subscription in paise")
    cgst_amount_paise = models.BigIntegerField(default=0, help_text="CGST (9%) in paise")
    sgst_amount_paise = models.BigIntegerField(default=0, help_text="SGST (9%) in paise")
    igst_amount_paise = models.BigIntegerField(default=0, help_text="IGST (18%) in paise")
    total_amount_paise = models.BigIntegerField(help_text="Total in paise")
    currency = models.CharField(max_length=10, default='INR')

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='paid')
    invoice_date = models.DateField(default=timezone.now)
    pdf_path = models.CharField(max_length=500, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.company.name} (₹{self.total_amount_rupees:.2f})"

    @property
    def taxable_amount_rupees(self) -> Decimal:
        return Decimal(self.taxable_amount_paise) / Decimal(100)

    @property
    def total_amount_rupees(self) -> Decimal:
        return Decimal(self.total_amount_paise) / Decimal(100)


class WebhookEvent(models.Model):
    """
    Audit log of incoming Razorpay webhook events.
    Prevents duplicate processing via unique event_id constraint.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('ignored', 'Ignored'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    signature = models.CharField(max_length=255, blank=True, default="")
    signature_verified = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)

    processing_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending', db_index=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} ({self.event_id}) - {self.processing_status}"


class DailyUsageTracker(models.Model):
    """
    Tracks daily consumption of rate-limited plan metrics (e.g. Fast OCR scans, Deep OCR scans).
    Guarantees atomic increments and tenant isolation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='billing_usage')
    metric = models.CharField(max_length=50, db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('company', 'metric', 'date')
        indexes = [
            models.Index(fields=['company', 'metric', 'date']),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.metric} on {self.date}: {self.count}"

# apps/payments/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, BankTransaction
from apps.payments.constants import (
    PaymentStatus,
    PaymentMethod,
    PaymentProviderType,
    SettlementStatus,
    AccountingPostingStatus,
    BeneficiaryType,
    VerificationStatus,
)


class MerchantPaymentAccount(models.Model):
    """
    Per-company merchant payment configuration and onboarding state.
    Enforces tenant isolation: each business configures its own VPAs,
    settlement accounts, and provider credentials.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name='payment_account'
    )
    merchant_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    vpa = models.CharField(max_length=255, blank=True, null=True, help_text="Registered UPI VPA, e.g. company@bank")
    is_onboarded = models.BooleanField(default=False, db_index=True)
    onboarding_status = models.CharField(max_length=50, default='PENDING')
    
    # Designated accounting ledgers in this company's Chart of Accounts
    default_settlement_ledger = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merchant_settlement_accounts',
        help_text="Primary bank ledger where settled funds arrive"
    )
    payment_clearing_ledger = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merchant_clearing_accounts',
        help_text="Intermediary clearing ledger for in-flight captured funds"
    )
    gateway_charges_ledger = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merchant_gateway_fee_accounts',
        help_text="Expense ledger for payment gateway / transaction fees"
    )

    # Virtual Account details for NEFT/IMPS/RTGS bank collections
    virtual_account_prefix = models.CharField(max_length=32, blank=True, null=True)
    virtual_account_ifsc = models.CharField(max_length=20, blank=True, null=True)

    webhook_secret = models.CharField(max_length=255, blank=True, null=True)
    auto_post_accounting = models.BooleanField(default=True, help_text="Auto-post vouchers on verified payment confirmation")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"MerchantAccount for {self.company.name} ({self.vpa or 'No VPA'})"


class Beneficiary(models.Model):
    """
    Company-specific Beneficiary Directory.
    Enforces strict tenant isolation: beneficiaries are never shared across unrelated companies.
    Supports Discovery via Mobile Number (UPI Number), VPA (UPI ID), QR, and Bank Account (IFSC).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='payment_beneficiaries',
        db_index=True
    )
    beneficiary_type = models.CharField(
        max_length=30,
        choices=BeneficiaryType.choices,
        default=BeneficiaryType.VPA,
        db_index=True
    )
    name = models.CharField(max_length=255, help_text="Contact / entity name")
    nickname = models.CharField(max_length=100, blank=True, null=True)
    mobile_number = models.CharField(max_length=15, blank=True, null=True, db_index=True)
    vpa = models.CharField(max_length=255, blank=True, null=True, db_index=True, help_text="UPI ID")
    account_number = models.CharField(max_length=64, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    branch_name = models.CharField(max_length=100, blank=True, null=True)

    # Verification status & audit fields
    is_verified = models.BooleanField(default=False, db_index=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True
    )
    verified_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Authoritative legal name returned by banking/UPI network"
    )
    verification_source = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="e.g. SETU_VPA, NPCI_UPI_NUMBER, PENNY_DROP"
    )
    verification_timestamp = models.DateTimeField(null=True, blank=True)

    # Quick access & directory metadata
    is_favorite = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    linked_party = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_beneficiaries',
        help_text="Associated Supplier/Customer ledger in this company"
    )
    last_paid_at = models.DateTimeField(null=True, blank=True)
    total_payments_count = models.PositiveIntegerField(default=0)
    total_paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_favorite', '-last_paid_at', '-created_at']
        indexes = [
            models.Index(fields=['company', 'beneficiary_type', 'is_active']),
            models.Index(fields=['company', 'mobile_number']),
            models.Index(fields=['company', 'vpa']),
        ]

    def __str__(self):
        ident = self.vpa or self.mobile_number or self.masked_account_number
        return f"{self.name} ({ident}) [{self.company.name}]"

    @property
    def masked_account_number(self):
        if self.account_number and len(self.account_number) >= 4:
            return f"{'•' * (len(self.account_number) - 4)}{self.account_number[-4:]}"
        return self.account_number or ""

    @property
    def masked_mobile_number(self):
        if self.mobile_number and len(self.mobile_number) >= 4:
            return f"{'•' * (len(self.mobile_number) - 4)}{self.mobile_number[-4:]}"
        return self.mobile_number or ""


class PaymentRequest(models.Model):
    """
    Central lifecycle record for all B2B payments across SriLekh Pay.
    Guarantees traceability from initiation -> provider verification -> double-entry vouchers -> bank settlement.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    srilekh_pay_id = models.CharField(max_length=64, unique=True, db_index=True, help_text="Human-readable ID e.g. SLP-202611-XXXXX")
    
    # Initiating company (Payer)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='outgoing_payment_requests',
        help_text="The company making the payment (or collecting on its own behalf)"
    )
    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        help_text="Beneficiary directory entry used for this payment"
    )
    payer_party = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_made',
        help_text="Supplier ledger in payer's chart of accounts"
    )

    # Recipient entities (Internal SriLekh tenant vs External business)
    recipient_company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_payment_requests',
        help_text="Set if recipient is also a SriLekh customer company"
    )
    recipient_party = models.ForeignKey(
        Ledger,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts_received',
        help_text="Customer ledger in recipient's chart of accounts (when recipient is SriLekh tenant)"
    )
    recipient_name = models.CharField(max_length=255)
    recipient_vpa = models.CharField(max_length=255, blank=True, null=True)
    recipient_account_number = models.CharField(max_length=64, blank=True, null=True)
    recipient_ifsc = models.CharField(max_length=20, blank=True, null=True)

    # Link to related invoice (Purchase invoice for payer, Sales invoice for recipient)
    invoice = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_requests'
    )

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.UPI, db_index=True)
    provider = models.CharField(max_length=30, choices=PaymentProviderType.choices, default=PaymentProviderType.SETU, db_index=True)
    
    # Provider transaction identifiers
    provider_reference = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    utr = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Bank UTR / RRN")
    payer_vpa = models.CharField(max_length=255, blank=True, null=True)

    # Status tracking
    status = models.CharField(max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.INITIATED, db_index=True)
    settlement_status = models.CharField(max_length=30, choices=SettlementStatus.choices, default=SettlementStatus.PENDING, db_index=True)
    accounting_status = models.CharField(max_length=30, choices=AccountingPostingStatus.choices, default=AccountingPostingStatus.PENDING, db_index=True)

    # Gateway fees and settlement amounts
    gateway_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_settled_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # UI generation artifacts
    qr_data = models.TextField(blank=True, null=True, help_text="Dynamic UPI QR payload / intent URI")
    payment_url = models.URLField(max_length=500, blank=True, null=True)

    # Timestamps
    initiated_at = models.DateTimeField(default=timezone.now, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    # Double-entry accounting links
    payer_voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payer_payment_requests',
        help_text="PAYMENT voucher posted in payer's books"
    )
    recipient_voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recipient_payment_requests',
        help_text="RECEIPT voucher posted in recipient's books"
    )
    bank_transaction = models.ForeignKey(
        BankTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_requests',
        help_text="Bank statement transaction feed entry matched to this payment"
    )

    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['company', 'status', 'initiated_at']),
            models.Index(fields=['recipient_company', 'status', 'initiated_at']),
            models.Index(fields=['utr', 'status']),
            models.Index(fields=['provider_reference', 'status']),
        ]

    def __str__(self):
        return f"{self.srilekh_pay_id} — ₹{self.amount} ({self.status})"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Payment amount must be strictly greater than 0.00")


class PaymentWebhookEvent(models.Model):
    """
    Immutable raw audit trail for all incoming provider webhooks.
    Guarantees cryptographic verification, replay defense, and idempotency.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=30, choices=PaymentProviderType.choices, db_index=True)
    event_id = models.CharField(max_length=255, unique=True, db_index=True, help_text="Unique event ID for replay protection")
    event_type = models.CharField(max_length=100, db_index=True)
    signature = models.TextField(blank=True, null=True)
    headers = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict)
    
    is_verified = models.BooleanField(default=False, db_index=True)
    is_processed = models.BooleanField(default=False, db_index=True)
    error_message = models.TextField(blank=True, null=True)
    
    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.provider} Event {self.event_id} ({'Verified' if self.is_verified else 'Unverified'})"


class PaymentRefund(models.Model):
    """
    Tracks payment refunds, reversals, and corresponding accounting reversals.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.CASCADE,
        related_name='refunds'
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payment_refunds')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.TextField()
    provider_refund_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)
    
    reversal_voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refund_records',
        help_text="Reversal journal voucher posted for this refund"
    )
    authorized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund ₹{self.amount} for {self.payment_request.srilekh_pay_id} [{self.status}]"


class UnmatchedPaymentRecord(models.Model):
    """
    Suspense tracking for incoming payments received that could not be unambiguously
    matched to an existing recipient sales invoice or customer ledger.
    Prevents erroneous accounting postings while providing an accountant-friendly review tray.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='unmatched_payments',
        help_text="The recipient company that received the unallocated funds"
    )
    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unmatched_records'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    utr = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    payer_identifier = models.CharField(max_length=255, blank=True, null=True, help_text="Payer VPA / Name / Bank Account")
    unmatched_reason = models.TextField(blank=True, null=True)
    
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_voucher = models.ForeignKey(
        Voucher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_unmatched_payments'
    )
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Unmatched ₹{self.amount} ({self.payer_identifier}) — UTR: {self.utr}"

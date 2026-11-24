# apps/payments/constants.py
from django.db import models


class PaymentStatus(models.TextChoices):
    CREATED = 'CREATED', 'Created'
    INITIATED = 'INITIATED', 'Initiated'
    PENDING = 'PENDING', 'Pending Confirmation'
    PROCESSING = 'PROCESSING', 'Processing'
    SUCCESS = 'SUCCESS', 'Successful'
    FAILED = 'FAILED', 'Failed'
    EXPIRED = 'EXPIRED', 'Expired'
    REVERSED = 'REVERSED', 'Reversed'
    REFUND_PENDING = 'REFUND_PENDING', 'Refund Pending'
    PARTIALLY_REFUNDED = 'PARTIALLY_REFUNDED', 'Partially Refunded'
    REFUNDED = 'REFUNDED', 'Refunded'


class BeneficiaryType(models.TextChoices):
    MOBILE_UPI = 'MOBILE_UPI', 'Mobile Number (UPI)'
    VPA = 'VPA', 'UPI ID (VPA)'
    BANK_ACCOUNT = 'BANK_ACCOUNT', 'Bank Account & IFSC'
    QR = 'QR', 'Scanned QR Code'


class VerificationStatus(models.TextChoices):
    UNVERIFIED = 'UNVERIFIED', 'Unverified'
    VERIFIED = 'VERIFIED', 'Verified'
    FAILED = 'FAILED', 'Verification Failed'


class PaymentMethod(models.TextChoices):
    UPI = 'UPI', 'UPI (Instant / QR / DeepLink)'
    NEFT = 'NEFT', 'NEFT'
    IMPS = 'IMPS', 'IMPS'
    RTGS = 'RTGS', 'RTGS'
    NET_BANKING = 'NET_BANKING', 'Internet Banking'
    MANUAL_BANK_TRANSFER = 'MANUAL_BANK_TRANSFER', 'Bank Transfer (Verified UTR)'


class PaymentProviderType(models.TextChoices):
    SETU = 'SETU', 'Setu UPI & DeepLinks'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer & Virtual Account Adapter'
    CUSTOM_ADAPTER = 'CUSTOM_ADAPTER', 'Custom Banking Adapter'


class SettlementStatus(models.TextChoices):
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'
    PENDING = 'PENDING', 'Pending Settlement'
    SETTLED = 'SETTLED', 'Settled to Bank'
    PARTIALLY_SETTLED = 'PARTIALLY_SETTLED', 'Partially Settled'
    FAILED = 'FAILED', 'Settlement Failed'


class AccountingPostingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Accounting'
    POSTED = 'POSTED', 'Posted (Dual-Party Balanced)'
    PAYER_ONLY = 'PAYER_ONLY', 'Posted (Payer Only - External Beneficiary)'
    UNMATCHED = 'UNMATCHED', 'Unmatched Recipient (Suspense)'
    FAILED = 'FAILED', 'Posting Failed'

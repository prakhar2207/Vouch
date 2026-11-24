# apps/payments/services/accounting_posting_service.py
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.accounting.models import Voucher, LedgerEntry
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounts.models import User
from apps.companies.models import UserCompany
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.payments.models import PaymentRequest, UnmatchedPaymentRecord
from apps.payments.constants import (
    PaymentStatus,
    AccountingPostingStatus,
)

logger = logging.getLogger(__name__)


class AccountingPostingService:
    """
    Performs double-entry accounting posting for SriLekh Pay transactions.
    Ensures mathematical equilibrium (Total Debits == Total Credits),
    preserves complete audit trails, and performs automated FIFO invoice allocation.
    """

    @classmethod
    def _resolve_audit_user(cls, company, user=None, pr_user=None):
        """Resolves a valid user for voucher audit trails to satisfy DB NOT-NULL constraint."""
        if user:
            return user
        if pr_user:
            return pr_user
        uc = UserCompany.objects.filter(company=company, role__in=['OWNER', 'ADMIN']).select_related('user').first()
        if uc and uc.user:
            return uc.user
        any_uc = UserCompany.objects.filter(company=company).select_related('user').first()
        if any_uc and any_uc.user:
            return any_uc.user
        return User.objects.filter(is_superuser=True).first() or User.objects.first()

    @classmethod
    def _get_or_create_clearing_ledger(cls, company, name="SriLekh Pay Clearing"):
        """
        Gets or provisions the intermediary payment clearing ledger (Current Asset)
        for transactions awaiting bank statement reconciliation.
        """
        asset_group, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Current Assets",
            defaults={"nature": "ASSET"}
        )
        ledger = Ledger.objects.filter(company=company, name__iexact=name).first()
        if not ledger:
            ledger = Ledger.objects.create(
                company=company,
                group=asset_group,
                name=name,
                ledger_type="BANK"
            )
        return ledger

    @classmethod
    def _resolve_bank_or_clearing_ledger(cls, company, preferred_ledger=None):
        """
        Resolves the ledger to credit (payer) or debit (recipient).
        Priority: preferred_ledger -> merchant_account.payment_clearing_ledger -> merchant_account.default_settlement_ledger -> first BANK ledger -> auto-provisioned clearing ledger.
        """
        if preferred_ledger and preferred_ledger.company_id == company.id:
            return preferred_ledger

        merchant_acc = getattr(company, 'payment_account', None)
        if merchant_acc:
            if merchant_acc.default_settlement_ledger:
                return merchant_acc.default_settlement_ledger
            if merchant_acc.payment_clearing_ledger:
                return merchant_acc.payment_clearing_ledger

        # Try to find an existing Bank / Cash ledger
        bank_ledger = Ledger.objects.filter(
            company=company,
            ledger_type='BANK',
            is_archived=False
        ).first()
        if bank_ledger:
            return bank_ledger

        return cls._get_or_create_clearing_ledger(company)

    @classmethod
    @transaction.atomic
    def post_payment_accounting(cls, payment_request: PaymentRequest, user=None) -> PaymentRequest:
        """
        Posts atomic double-entry vouchers for the verified payment.
        Dual-party symmetric posting:
          - Payer: Dr Supplier / Dr Payable, Cr Bank / Clearing (PAYMENT voucher)
          - Recipient (if SriLekh tenant): Dr Bank / Clearing, Cr Customer / Receivable (RECEIPT voucher)
        """
        pr = PaymentRequest.objects.select_for_update().get(id=payment_request.id)

        # Idempotency guard: never double-post
        if pr.accounting_status in [AccountingPostingStatus.POSTED, AccountingPostingStatus.PAYER_ONLY]:
            logger.info("Accounting already posted for %s (Status: %s)", pr.srilekh_pay_id, pr.accounting_status)
            return pr

        if pr.status != PaymentStatus.SUCCESS:
            raise ValidationError(f"Cannot post accounting for payment {pr.srilekh_pay_id} with status '{pr.status}'. Only SUCCESS payments may be posted.")

        payment_date = pr.confirmed_at.date() if pr.confirmed_at else timezone.now().date()
        amount = pr.amount

        # =========================================================================
        # 1. PAYER ACCOUNTING (Payment Outflow)
        # =========================================================================
        payer_company = pr.company
        payer_party = pr.payer_party

        if not payer_party:
            # Fallback: find or create supplier ledger matching recipient_name
            supplier_group, _ = LedgerGroup.objects.get_or_create(
                company=payer_company,
                name="Sundry Creditors",
                defaults={"nature": "LIABILITY"}
            )
            payer_party, _ = Ledger.objects.get_or_create(
                company=payer_company,
                name=pr.recipient_name,
                defaults={
                    "group": supplier_group,
                    "ledger_type": "SUPPLIER"
                }
            )
            pr.payer_party = payer_party

        payer_bank_ledger = cls._resolve_bank_or_clearing_ledger(payer_company)
        payer_audit_user = cls._resolve_audit_user(payer_company, user=user, pr_user=pr.created_by)

        # Generate unique voucher number & Financial Year
        v_number, fy = InvoiceSequenceService.get_next_number(payer_company, 'PAYMENT', payment_date)

        payer_voucher = Voucher.objects.create(
            company=payer_company,
            financial_year=fy,
            voucher_type='PAYMENT',
            voucher_number=v_number,
            voucher_date=payment_date,
            party_ledger=payer_party,
            total_amount=amount,
            status='DRAFT',
            narration=f"SriLekh Pay {pr.srilekh_pay_id} via {pr.payment_method} to {pr.recipient_name}. UTR: {pr.utr or 'N/A'}",
            reference_number=pr.utr or pr.provider_reference or pr.srilekh_pay_id,
            created_by=payer_audit_user
        )

        # Debit: Supplier Payable (Liability reduction)
        LedgerEntry.objects.create(
            voucher=payer_voucher,
            company=payer_company,
            ledger=payer_party,
            debit_amount=amount,
            credit_amount=Decimal('0.00'),
            narration=f"Payment to {pr.recipient_name}"
        )

        # Credit: Bank / Clearing (Asset outflow)
        LedgerEntry.objects.create(
            voucher=payer_voucher,
            company=payer_company,
            ledger=payer_bank_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=amount,
            narration=f"Outflow via {pr.payment_method} (Ref: {pr.srilekh_pay_id})"
        )

        # Post and enforce double-entry mathematical equilibrium
        VoucherService.post_voucher(payer_voucher)
        pr.payer_voucher = payer_voucher

        # Auto-allocate to preferred purchase bill or FIFO
        preferred_inv_id = pr.invoice_id if pr.invoice and pr.invoice.company_id == payer_company.id else None
        try:
            PaymentAllocationService.auto_allocate_voucher(payer_voucher, preferred_invoice_id=preferred_inv_id)
        except Exception as alloc_err:
            logger.warning("Payer invoice allocation non-critical warning for %s: %s", pr.srilekh_pay_id, alloc_err)

        logger.info("Successfully posted PAYMENT voucher %s in payer company %s", payer_voucher.voucher_number, payer_company.name)

        # =========================================================================
        # 2. RECIPIENT ACCOUNTING (Payment Inflow - if SriLekh customer company)
        # =========================================================================
        if pr.recipient_company:
            recipient_company = pr.recipient_company
            recipient_party = pr.recipient_party

            if recipient_party:
                recipient_bank_ledger = cls._resolve_bank_or_clearing_ledger(recipient_company)
                recip_audit_user = cls._resolve_audit_user(recipient_company, user=user, pr_user=pr.created_by)
                r_v_number, r_fy = InvoiceSequenceService.get_next_number(recipient_company, 'RECEIPT', payment_date)

                recipient_voucher = Voucher.objects.create(
                    company=recipient_company,
                    financial_year=r_fy,
                    voucher_type='RECEIPT',
                    voucher_number=r_v_number,
                    voucher_date=payment_date,
                    party_ledger=recipient_party,
                    total_amount=amount,
                    status='DRAFT',
                    narration=f"SriLekh Pay Receipt {pr.srilekh_pay_id} via {pr.payment_method} from {payer_company.name}. UTR: {pr.utr or 'N/A'}",
                    reference_number=pr.utr or pr.provider_reference or pr.srilekh_pay_id,
                    created_by=recip_audit_user
                )

                # Debit: Bank / Payment Clearing (Asset inflow)
                LedgerEntry.objects.create(
                    voucher=recipient_voucher,
                    company=recipient_company,
                    ledger=recipient_bank_ledger,
                    debit_amount=amount,
                    credit_amount=Decimal('0.00'),
                    narration=f"Funds received via {pr.payment_method}"
                )

                # Credit: Customer Receivable (Asset reduction)
                LedgerEntry.objects.create(
                    voucher=recipient_voucher,
                    company=recipient_company,
                    ledger=recipient_party,
                    debit_amount=Decimal('0.00'),
                    credit_amount=amount,
                    narration=f"Receipt from {payer_company.name}"
                )

                VoucherService.post_voucher(recipient_voucher)
                pr.recipient_voucher = recipient_voucher

                # Auto-allocate to preferred sales invoice or FIFO
                r_preferred_inv_id = pr.invoice_id if pr.invoice and pr.invoice.company_id == recipient_company.id else None
                try:
                    PaymentAllocationService.auto_allocate_voucher(recipient_voucher, preferred_invoice_id=r_preferred_inv_id)
                except Exception as r_alloc_err:
                    logger.warning("Recipient invoice allocation non-critical warning for %s: %s", pr.srilekh_pay_id, r_alloc_err)

                pr.accounting_status = AccountingPostingStatus.POSTED
                logger.info("Successfully posted RECEIPT voucher %s in recipient company %s", recipient_voucher.voucher_number, recipient_company.name)

            else:
                # Recipient company is known, but party ledger is ambiguous -> route to Unmatched suspense
                UnmatchedPaymentRecord.objects.create(
                    company=recipient_company,
                    payment_request=pr,
                    amount=amount,
                    utr=pr.utr,
                    payer_identifier=payer_company.name,
                    unmatched_reason=f"Customer ledger not matched for incoming payment from {payer_company.name} (Amount: ₹{amount})"
                )
                pr.accounting_status = AccountingPostingStatus.UNMATCHED
                logger.warning("Payment %s routed to UnmatchedPaymentRecord suspense in recipient company %s", pr.srilekh_pay_id, recipient_company.name)
        else:
            # External recipient (not a SriLekh platform company)
            pr.accounting_status = AccountingPostingStatus.PAYER_ONLY

        pr.save(update_fields=['payer_party', 'payer_voucher', 'recipient_voucher', 'accounting_status'])
        return pr

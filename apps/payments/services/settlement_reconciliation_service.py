# apps/payments/services/settlement_reconciliation_service.py
import logging
from decimal import Decimal
from typing import Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.accounting.models import Voucher, LedgerEntry, BankTransaction
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.payments.models import PaymentRequest, MerchantPaymentAccount
from apps.payments.constants import SettlementStatus, PaymentStatus
from apps.payments.services.accounting_posting_service import AccountingPostingService

logger = logging.getLogger(__name__)


class SettlementReconciliationService:
    """
    Handles bank settlement reconciliation and fee accounting for SriLekh Pay collections.
    Reconciles in-flight clearing ledger balances against final bank statement entries.
    """

    @classmethod
    @transaction.atomic
    def record_settlement(
        cls,
        payment_request: PaymentRequest,
        net_amount: Decimal,
        fee_amount: Decimal = Decimal('0.00'),
        settlement_date=None,
        bank_transaction: Optional[BankTransaction] = None,
        user=None
    ) -> PaymentRequest:
        """
        Posts double-entry settlement journal voucher:
          Dr Primary Bank Account (Net received)
          Dr Gateway Charges Expense (Fee deduction)
          Cr Payment Clearing Ledger (Gross captured funds)
        Mathematical equilibrium: Net + Fee == Gross!
        """
        pr = PaymentRequest.objects.select_for_update().get(id=payment_request.id)

        if pr.status != PaymentStatus.SUCCESS:
            raise ValidationError("Cannot settle an unconfirmed payment.")

        if pr.settlement_status == SettlementStatus.SETTLED:
            logger.info("Payment %s is already marked SETTLED.", pr.srilekh_pay_id)
            return pr

        target_company = pr.recipient_company or pr.company
        merchant_account = getattr(target_company, 'payment_account', None)

        settlement_bank = (
            merchant_account.default_settlement_ledger if merchant_account and merchant_account.default_settlement_ledger else None
        )
        clearing_ledger = (
            merchant_account.payment_clearing_ledger if merchant_account and merchant_account.payment_clearing_ledger else None
        )
        fee_ledger = (
            merchant_account.gateway_charges_ledger if merchant_account and merchant_account.gateway_charges_ledger else None
        )

        date_val = settlement_date or timezone.now().date()
        v_num, fy = InvoiceSequenceService.get_next_number(target_company, 'JOURNAL', date_val)

        audit_user = AccountingPostingService._resolve_audit_user(target_company, user=user, pr_user=pr.created_by)

        # Post settlement journal voucher
        settlement_voucher = Voucher.objects.create(
            company=target_company,
            financial_year=fy,
            voucher_type='JOURNAL',
            voucher_number=v_num,
            voucher_date=date_val,
            total_amount=pr.amount,
            status='DRAFT',
            narration=f"Settlement for SriLekh Pay {pr.srilekh_pay_id}. Net: ₹{net_amount}, Fee: ₹{fee_amount}. UTR: {pr.utr or 'N/A'}",
            reference_number=pr.utr or pr.srilekh_pay_id,
            created_by=audit_user
        )

        # 1. Dr Primary Bank Account (Net Amount)
        if settlement_bank:
            LedgerEntry.objects.create(
                voucher=settlement_voucher,
                company=target_company,
                ledger=settlement_bank,
                debit_amount=net_amount,
                credit_amount=Decimal('0.00'),
                narration=f"Net settlement deposit for {pr.srilekh_pay_id}"
            )

        # 2. Dr Gateway Charges (Fee Amount)
        if fee_amount > Decimal('0.00') and fee_ledger:
            LedgerEntry.objects.create(
                voucher=settlement_voucher,
                company=target_company,
                ledger=fee_ledger,
                debit_amount=fee_amount,
                credit_amount=Decimal('0.00'),
                narration=f"Gateway processing fee for {pr.srilekh_pay_id}"
            )
        elif fee_amount > Decimal('0.00') and not fee_ledger:
            # If no fee ledger configured, net is full amount
            net_amount += fee_amount
            fee_amount = Decimal('0.00')

        # 3. Cr Payment Clearing Ledger (Gross Amount)
        if clearing_ledger:
            LedgerEntry.objects.create(
                voucher=settlement_voucher,
                company=target_company,
                ledger=clearing_ledger,
                debit_amount=Decimal('0.00'),
                credit_amount=pr.amount,
                narration=f"Clear in-flight funds for {pr.srilekh_pay_id}"
            )

        # Validate debits == credits and post
        if settlement_bank and clearing_ledger:
            VoucherService.post_voucher(settlement_voucher)

        pr.settlement_status = SettlementStatus.SETTLED
        pr.gateway_fee = fee_amount
        pr.net_settled_amount = net_amount
        pr.settled_at = timezone.now()
        if bank_transaction:
            pr.bank_transaction = bank_transaction

        pr.save(update_fields=['settlement_status', 'gateway_fee', 'net_settled_amount', 'settled_at', 'bank_transaction'])
        logger.info("Payment %s settled successfully (Net: ₹%s, Fee: ₹%s)", pr.srilekh_pay_id, net_amount, fee_amount)
        return pr

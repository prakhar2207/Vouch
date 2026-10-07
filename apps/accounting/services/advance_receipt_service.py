import datetime
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, LedgerEntry, PaymentAllocation
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService


class AdvanceReceiptService:
    """
    Statutory GST Advance Receipt & Tax Adjustment Engine.
    Implements:
    - CGST Act Section 31(3)(d) read with Rule 50 (Receipt Voucher for Advance).
    - GSTR-1 Table 11A (Advances received during the tax period).
    - GSTR-1 Table 11B (Advances adjusted against subsequent tax invoices).
    """

    @classmethod
    @transaction.atomic
    def create_advance_receipt(
        cls,
        company: Company,
        user,
        party_ledger: Ledger,
        bank_ledger: Ledger,
        amount: Decimal,
        tax_rate: Decimal = Decimal('18.00'),
        voucher_date: Optional[datetime.date] = None,
        reference_number: Optional[str] = None,
        narration: Optional[str] = None,
        auto_post: bool = True
    ) -> Voucher:
        """
        Creates and posts an Advance Receipt Voucher with GST liability breakdown.
        Amount received is treated as inclusive of GST (Rule 50).
        Double-entry:
          Debit: Bank / Cash (Asset)
          Credit: Customer Party (Liability / Advance from Customer)
        """
        amt = Decimal(str(amount)).quantize(Decimal('0.01'))
        if amt <= Decimal('0.00'):
            raise ValidationError("Advance receipt amount must be greater than zero.")

        if party_ledger.company_id != company.id:
            raise ValidationError(f"Party ledger '{party_ledger.name}' does not belong to company '{company.name}'.")
        if bank_ledger.company_id != company.id:
            raise ValidationError(f"Bank ledger '{bank_ledger.name}' does not belong to company '{company.name}'.")

        v_date = voucher_date or timezone.now().date()
        fy = InvoiceSequenceService.get_or_create_active_fy(company, v_date)
        v_num, _ = InvoiceSequenceService.get_next_number(company, 'RECEIPT', v_date)

        rate = Decimal(str(tax_rate)).quantize(Decimal('0.01'))
        # Rule 50: Gross Amount = Taxable Base + Tax Component
        # Taxable Base = (Gross * 100) / (100 + Rate)
        taxable_base = (amt * Decimal('100.00') / (Decimal('100.00') + rate)).quantize(Decimal('0.01'))
        total_tax = (amt - taxable_base).quantize(Decimal('0.01'))

        # Intra-state vs Inter-state supply determination
        party_state = (party_ledger.state_code or company.state_code or '09').zfill(2)
        comp_state = (company.state_code or '09').zfill(2)
        is_intra = (party_state == comp_state)

        if is_intra:
            cgst = (total_tax / Decimal('2.00')).quantize(Decimal('0.01'))
            sgst = total_tax - cgst
            igst = Decimal('0.00')
        else:
            cgst = Decimal('0.00')
            sgst = Decimal('0.00')
            igst = total_tax

        narr = narration or f"Advance receipt from {party_ledger.name} [GST {rate}%: ₹{total_tax}]"

        voucher = Voucher.objects.create(
            company=company,
            financial_year=fy,
            voucher_type='RECEIPT',
            voucher_number=v_num,
            reference_number=reference_number or v_num,
            voucher_date=v_date,
            party_ledger=party_ledger,
            status='DRAFT',
            total_amount=amt,
            is_advance=True,
            advance_tax_rate=rate,
            advance_tax_amount=total_tax,
            advance_cgst=cgst,
            advance_sgst=sgst,
            advance_igst=igst,
            advance_adjusted_amount=Decimal('0.00'),
            created_by=user,
            narration=narr
        )

        # 1. Debit Bank/Cash (Asset Inflow)
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=bank_ledger,
            debit_amount=amt,
            credit_amount=Decimal('0.00'),
            narration=f"Advance receipt deposited into {bank_ledger.name}"
        )

        # 2. Credit Customer Party (Liability / Advance)
        LedgerEntry.objects.create(
            voucher=voucher,
            ledger=party_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=amt,
            narration=f"Advance payment received from {party_ledger.name}"
        )

        if auto_post:
            VoucherService.post_voucher(voucher)

        return voucher

    @classmethod
    @transaction.atomic
    def adjust_advance_against_invoice(
        cls,
        advance_voucher: Voucher,
        invoice_voucher: Voucher,
        allocated_amount: Decimal
    ) -> PaymentAllocation:
        """
        Adjusts an advance receipt against a subsequently posted Sales Tax Invoice.
        Updates cumulative advance_adjusted_amount on the advance voucher and
        records adjusted_advance_tax on PaymentAllocation for GSTR-1 Table 11B offset.
        """
        amt = Decimal(str(allocated_amount)).quantize(Decimal('0.01'))
        if amt <= Decimal('0.00'):
            raise ValidationError("Allocated amount must be greater than zero.")

        if not advance_voucher.is_advance:
            raise ValidationError(f"Voucher #{advance_voucher.voucher_number} is not an Advance Receipt.")
        if advance_voucher.status != 'POSTED':
            raise ValidationError(f"Advance voucher #{advance_voucher.voucher_number} must be POSTED before adjustment.")
        if invoice_voucher.voucher_type != 'SALES':
            raise ValidationError(f"Invoice voucher #{invoice_voucher.voucher_number} must be a SALES invoice.")
        if invoice_voucher.status != 'POSTED':
            raise ValidationError(f"Invoice voucher #{invoice_voucher.voucher_number} must be POSTED before adjustment.")

        if advance_voucher.party_ledger_id != invoice_voucher.party_ledger_id:
            raise ValidationError("Advance receipt party does not match invoice party.")

        rem_advance = advance_voucher.total_amount - advance_voucher.advance_adjusted_amount
        if amt > rem_advance:
            raise ValidationError(
                f"Cannot adjust ₹{amt}: Only ₹{rem_advance} unadjusted advance remains on #{advance_voucher.voucher_number}."
            )

        # Calculate proportional advance tax adjusted for GSTR-1 Table 11B
        if advance_voucher.total_amount > Decimal('0.00'):
            prop = amt / advance_voucher.total_amount
            adj_tax = (advance_voucher.advance_tax_amount * prop).quantize(Decimal('0.01'))
        else:
            adj_tax = Decimal('0.00')

        allocation = PaymentAllocation.objects.create(
            company=advance_voucher.company,
            payment_voucher=advance_voucher,
            invoice_voucher=invoice_voucher,
            allocated_amount=amt,
            adjusted_advance_tax=adj_tax
        )

        advance_voucher.advance_adjusted_amount += amt
        advance_voucher.save(update_fields=['advance_adjusted_amount'])

        return allocation

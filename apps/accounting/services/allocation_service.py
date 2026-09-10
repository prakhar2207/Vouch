from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, PaymentAllocation
from apps.common.money import to_decimal, quantize_money

class PaymentAllocationService:
    @staticmethod
    def get_voucher_allocated_amount(voucher: Voucher) -> Decimal:
        """
        Calculates how much of an invoice has already been paid via PaymentAllocations.
        """
        alloc = PaymentAllocation.objects.filter(invoice_voucher=voucher).aggregate(
            total=Sum('allocated_amount')
        )['total']
        return quantize_money(alloc or Decimal('0.00'))

    @staticmethod
    def get_unpaid_invoices_for_party(company: Company, party_ledger: Ledger) -> list:
        """
        Returns all posted invoices for a party that have remaining unpaid balances,
        ordered by voucher_date ascending (FIFO order).
        Eliminates N+1 query overhead by batch-aggregating allocations in a single query.
        """
        if not party_ledger:
            return []

        # Canonical party role: CUSTOMER (receivable) vs SUPPLIER (payable)
        is_customer = (party_ledger.canonical_role == 'CUSTOMER') or (party_ledger.opening_balance_type == 'DEBIT')
        target_vtypes = ['SALES', 'OPENING_INVOICE'] if is_customer else ['PURCHASE', 'OPENING_BILL']

        invoices = list(Voucher.objects.filter(
            company=company,
            party_ledger=party_ledger,
            voucher_type__in=target_vtypes,
            status='POSTED'
        ).order_by('due_date', 'voucher_date', 'created_at'))

        if not invoices:
            return []

        inv_ids = [inv.id for inv in invoices]
        allocations_map = {}
        if inv_ids:
            alloc_totals = PaymentAllocation.objects.filter(
                invoice_voucher_id__in=inv_ids
            ).values('invoice_voucher_id').annotate(total_paid=Sum('allocated_amount'))
            allocations_map = {item['invoice_voucher_id']: item['total_paid'] for item in alloc_totals}

        unpaid = []
        for inv in invoices:
            total = quantize_money(inv.total_amount)
            paid = quantize_money(allocations_map.get(inv.id, Decimal('0.00')))
            remaining = total - paid
            if remaining > Decimal('0.00'):
                unpaid.append({
                    'voucher_id': str(inv.id),
                    'voucher_number': inv.voucher_number,
                    'voucher_date': str(inv.voucher_date),
                    'total_amount': str(total),
                    'paid_amount': str(paid),
                    'remaining_amount': str(remaining)
                })

        return unpaid

    @classmethod
    @transaction.atomic
    def auto_allocate_voucher(cls, payment_voucher: Voucher) -> list:
        """
        Automatically performs FIFO allocation of a Payment or Receipt voucher
        against the party's oldest outstanding invoices.
        Any remaining unallocated amount represents an Advance.
        Enforces strict cross-company isolation invariant.
        """
        if payment_voucher.voucher_type not in ['PAYMENT', 'RECEIPT']:
            return []

        party = payment_voucher.party_ledger
        if not party:
            return []

        unpaid_invoices = cls.get_unpaid_invoices_for_party(payment_voucher.company, party)
        rem_funds = quantize_money(payment_voucher.total_amount)
        allocations = []

        # Delete any prior allocations for this payment voucher
        PaymentAllocation.objects.filter(payment_voucher=payment_voucher).delete()

        for inv_info in unpaid_invoices:
            if rem_funds <= Decimal('0.00'):
                break

            inv = Voucher.objects.get(id=inv_info['voucher_id'])
            # P1-18: Payment Allocation Company Invariant
            if inv.company_id != payment_voucher.company_id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError("Cross-company payment allocation is strictly prohibited.")

            inv_due = Decimal(inv_info['remaining_amount'])
            alloc_amt = min(rem_funds, inv_due)

            alloc = PaymentAllocation.objects.create(
                company=payment_voucher.company,
                payment_voucher=payment_voucher,
                invoice_voucher=inv,
                allocated_amount=alloc_amt
            )
            allocations.append({
                'invoice_voucher_id': str(inv.id),
                'invoice_number': inv.voucher_number,
                'allocated_amount': str(alloc_amt)
            })
            rem_funds -= alloc_amt

        return allocations

    @classmethod
    @transaction.atomic
    def allocate_payment(cls, payment_voucher: Voucher, invoice_voucher: Voucher, allocated_amount: Decimal) -> PaymentAllocation:
        """
        Allocates a specific payment amount against an invoice.
        Enforces strict cross-company isolation invariant.
        """
        if payment_voucher.company_id != invoice_voucher.company_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cross-company payment allocation is strictly prohibited.")

        alloc = PaymentAllocation.objects.create(
            company=payment_voucher.company,
            payment_voucher=payment_voucher,
            invoice_voucher=invoice_voucher,
            allocated_amount=allocated_amount
        )
        return alloc

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
        """
        if not party_ledger:
            return []

        # If party is debtor (customer), look for posted SALES
        # If party is creditor (supplier), look for posted PURCHASE
        target_vtype = 'SALES' if party_ledger.group and 'debtor' in party_ledger.group.name.lower() else 'PURCHASE'

        invoices = Voucher.objects.filter(
            company=company,
            party_ledger=party_ledger,
            voucher_type=target_vtype,
            status='POSTED'
        ).order_by('voucher_date', 'created_at')

        unpaid = []
        for inv in invoices:
            total = quantize_money(inv.total_amount)
            paid = PaymentAllocationService.get_voucher_allocated_amount(inv)
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

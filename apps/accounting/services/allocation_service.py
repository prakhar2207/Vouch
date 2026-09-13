from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, PaymentAllocation
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

def quantize_money(amount) -> Decimal:
    if amount is None:
        return Decimal('0.00')
    return Decimal(str(amount)).quantize(Decimal('0.00'))

class PaymentAllocationService:
    @staticmethod
    def is_party_customer(party: Ledger) -> bool:
        """
        Determines whether party is a Customer (receivable) or Supplier (payable)
        using canonical role first, group name nature second, normal balance third.
        Never relies on opening_balance_type which is just an opening balance sign.
        """
        if not party:
            return True
        role = getattr(party, 'canonical_role', None)
        if role == 'CUSTOMER':
            return True
        if role == 'SUPPLIER':
            return False
        
        group_name = (party.group.name or '').lower() if getattr(party, 'group', None) else ''
        if any(k in group_name for k in ['debtor', 'customer', 'receivable']):
            return True
        if any(k in group_name for k in ['creditor', 'supplier', 'payable']):
            return False
            
        return getattr(party, 'normal_balance', 'DEBIT') == 'DEBIT'

    @staticmethod
    def get_invoice_allocated_amount(voucher: Voucher) -> Decimal:
        alloc = PaymentAllocation.objects.filter(invoice_voucher=voucher).aggregate(
            total=Sum('allocated_amount')
        )['total']
        return quantize_money(alloc or Decimal('0.00'))

    @classmethod
    def get_unpaid_invoices_for_party(cls, company: Company, party_ledger: Ledger) -> list:
        """
        Returns all posted invoices for a party that have remaining unpaid balances,
        ordered by voucher_date ascending (FIFO order).
        Eliminates N+1 query overhead by batch-aggregating allocations in a single query.
        """
        if not party_ledger:
            return []

        is_customer = cls.is_party_customer(party_ledger)
        target_vtypes = ['SALES', 'OPENING_INVOICE'] if is_customer else ['PURCHASE', 'OPENING_BILL']

        invoices = list(Voucher.objects.filter(
            company=company,
            party_ledger=party_ledger,
            voucher_type__in=target_vtypes,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
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
    def auto_allocate_voucher(cls, payment_voucher: Voucher, preferred_invoice_id: str = None) -> list:
        """
        Automatically performs reference-aware and FIFO allocation of a Payment or Receipt voucher
        against the party's outstanding invoices.
        Uses select_for_update() row locks on both payment and invoices to prevent concurrent over-allocation.
        Any remaining unallocated amount represents an Advance.
        Enforces strict cross-company isolation invariant.
        """
        if payment_voucher.voucher_type not in ['PAYMENT', 'RECEIPT']:
            return []

        # Lock the payment voucher row
        pv = Voucher.objects.select_for_update().get(id=payment_voucher.id)
        party = pv.party_ledger
        if not party:
            return []

        # Delete any prior allocations for this payment voucher
        PaymentAllocation.objects.filter(payment_voucher=pv).delete()

        rem_funds = quantize_money(pv.total_amount)
        if rem_funds <= Decimal('0.00'):
            return []

        is_customer = cls.is_party_customer(party)
        target_vtypes = ['SALES', 'OPENING_INVOICE'] if is_customer else ['PURCHASE', 'OPENING_BILL']

        # Determine candidate invoices
        candidate_qs = Voucher.objects.filter(
            company=pv.company,
            party_ledger=party,
            voucher_type__in=target_vtypes,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        ).order_by('due_date', 'voucher_date', 'created_at')

        # Check for explicit invoice reference match in reference_number
        preferred_inv = None
        if preferred_invoice_id:
            preferred_inv = candidate_qs.filter(id=preferred_invoice_id).first()
        elif pv.reference_number:
            ref = str(pv.reference_number).strip()
            preferred_inv = candidate_qs.filter(voucher_number__iexact=ref).first()

        ordered_candidates = []
        if preferred_inv:
            ordered_candidates.append(preferred_inv)

        for inv in candidate_qs:
            if preferred_inv and inv.id == preferred_inv.id:
                continue
            ordered_candidates.append(inv)

        allocations = []
        for candidate in ordered_candidates:
            if rem_funds <= Decimal('0.00'):
                break

            # Lock candidate invoice row
            inv = Voucher.objects.select_for_update().get(id=candidate.id)
            if inv.company_id != pv.company_id:
                from rest_framework.exceptions import ValidationError
                raise ValidationError("Cross-company payment allocation is strictly prohibited.")

            # Calculate real-time remaining unpaid balance under lock
            currently_paid = PaymentAllocation.objects.filter(
                invoice_voucher=inv
            ).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')

            inv_due = max(Decimal('0.00'), quantize_money(inv.total_amount - currently_paid))
            if inv_due <= Decimal('0.00'):
                continue

            alloc_amt = min(rem_funds, inv_due)
            alloc = PaymentAllocation.objects.create(
                company=pv.company,
                payment_voucher=pv,
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
        Enforces row-locking and invoice total capacity invariants.
        """
        if payment_voucher.company_id != invoice_voucher.company_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cross-company payment allocation is strictly prohibited.")

        alloc_amt = quantize_money(allocated_amount)
        if alloc_amt <= Decimal('0.00'):
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Allocated amount must be greater than zero.")

        # Lock both payment and invoice rows to prevent concurrent over-allocation
        pv = Voucher.objects.select_for_update().get(id=payment_voucher.id)
        inv = Voucher.objects.select_for_update().get(id=invoice_voucher.id)

        # Check payment capacity
        other_pv_alloc = PaymentAllocation.objects.filter(
            payment_voucher=pv
        ).exclude(invoice_voucher=inv).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')
        pv_capacity = max(Decimal('0.00'), quantize_money(pv.total_amount - other_pv_alloc))
        if alloc_amt > pv_capacity:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                f"Cannot allocate ₹{alloc_amt}: remaining unallocated funds on payment {pv.voucher_number} is only ₹{pv_capacity}."
            )

        currently_paid = PaymentAllocation.objects.filter(
            invoice_voucher=inv
        ).exclude(payment_voucher=pv).aggregate(total=Sum('allocated_amount'))['total'] or Decimal('0.00')

        remaining_capacity = max(Decimal('0.00'), quantize_money(inv.total_amount - currently_paid))
        if alloc_amt > remaining_capacity:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                f"Cannot allocate ₹{alloc_amt}: remaining unpaid balance on invoice {inv.voucher_number} is only ₹{remaining_capacity}."
            )

        # Remove existing allocation for this pair if any
        PaymentAllocation.objects.filter(payment_voucher=pv, invoice_voucher=inv).delete()

        alloc = PaymentAllocation.objects.create(
            company=pv.company,
            payment_voucher=pv,
            invoice_voucher=inv,
            allocated_amount=alloc_amt
        )
        return alloc

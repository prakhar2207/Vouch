from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
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
        ).annotate(effective_due=Coalesce('due_date', 'voucher_date')).order_by('effective_due', 'created_at'))

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
        ).annotate(effective_due=Coalesce('due_date', 'voucher_date')).order_by('effective_due', 'created_at')

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

    @classmethod
    def get_aging_analysis(cls, company: Company, party_type: str = 'CUSTOMER', as_of_date=None, start_date=None, end_date=None) -> dict:
        """
        Computes party-wise outstanding receivables/payables aging breakdown:
        - Current (Not Due)
        - 1-30 Days
        - 31-60 Days
        - 61-90 Days
        - >90 Days
        - MSME 45-day overdue indicator
        """
        import datetime
        today = datetime.date.today()
        comparison_date = as_of_date or end_date or today
        is_customer = (party_type.upper() == 'CUSTOMER')
        target_vtypes = ['SALES', 'OPENING_INVOICE'] if is_customer else ['PURCHASE', 'OPENING_BILL']

        inv_qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=target_vtypes,
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        )
        if as_of_date or end_date:
            inv_qs = inv_qs.filter(voucher_date__lte=as_of_date or end_date)
        if start_date:
            inv_qs = inv_qs.filter(voucher_date__gte=start_date)

        invoices = list(inv_qs.select_related('party_ledger').order_by('due_date', 'voucher_date'))

        if not invoices:
            return {
                "party_type": party_type,
                "total_outstanding": 0.0,
                "parties": [],
                "summary": {"current": 0.0, "days_1_30": 0.0, "days_31_60": 0.0, "days_61_90": 0.0, "above_90": 0.0, "msme_overdue_count": 0}
            }

        inv_ids = [inv.id for inv in invoices]
        alloc_qs = PaymentAllocation.objects.filter(invoice_voucher_id__in=inv_ids)
        if as_of_date or end_date:
            alloc_qs = alloc_qs.filter(payment_voucher__voucher_date__lte=as_of_date or end_date)

        alloc_totals = alloc_qs.values('invoice_voucher_id').annotate(total_paid=Sum('allocated_amount'))
        allocations_map = {item['invoice_voucher_id']: item['total_paid'] for item in alloc_totals}

        parties_map = {}
        summary = {"current": 0.0, "days_1_30": 0.0, "days_31_60": 0.0, "days_61_90": 0.0, "above_90": 0.0, "msme_overdue_count": 0}

        for inv in invoices:
            tot = quantize_money(inv.total_amount)
            paid = quantize_money(allocations_map.get(inv.id, Decimal('0.00')))
            remaining = tot - paid
            if remaining <= Decimal('0.00'):
                continue

            ref_date = inv.due_date or inv.voucher_date
            overdue_days = (comparison_date - ref_date).days if comparison_date > ref_date else 0
            is_msme_alert = overdue_days > 45

            if is_msme_alert:
                summary["msme_overdue_count"] += 1

            p_id = str(inv.party_ledger_id) if inv.party_ledger_id else "counter"
            p_name = inv.party_ledger.name if inv.party_ledger else (inv.buyer_name or "Counter Party")

            if p_id not in parties_map:
                parties_map[p_id] = {
                    "party_id": p_id,
                    "party_name": p_name,
                    "phone": inv.party_ledger.phone if inv.party_ledger else "",
                    "gstin": inv.party_ledger.gstin if inv.party_ledger else "",
                    "total_outstanding": Decimal('0.00'),
                    "current": Decimal('0.00'),
                    "days_1_30": Decimal('0.00'),
                    "days_31_60": Decimal('0.00'),
                    "days_61_90": Decimal('0.00'),
                    "above_90": Decimal('0.00'),
                    "msme_overdue": False,
                    "bills_count": 0,
                }

            parties_map[p_id]["total_outstanding"] += remaining
            parties_map[p_id]["bills_count"] += 1
            if is_msme_alert:
                parties_map[p_id]["msme_overdue"] = True

            rem_flt = float(remaining)
            if overdue_days <= 0:
                parties_map[p_id]["current"] += remaining
                summary["current"] += rem_flt
            elif 1 <= overdue_days <= 30:
                parties_map[p_id]["days_1_30"] += remaining
                summary["days_1_30"] += rem_flt
            elif 31 <= overdue_days <= 60:
                parties_map[p_id]["days_31_60"] += remaining
                summary["days_31_60"] += rem_flt
            elif 61 <= overdue_days <= 90:
                parties_map[p_id]["days_61_90"] += remaining
                summary["days_61_90"] += rem_flt
            else:
                parties_map[p_id]["above_90"] += remaining
                summary["above_90"] += rem_flt

        parties_list = []
        for p in parties_map.values():
            parties_list.append({
                "party_id": p["party_id"],
                "party_name": p["party_name"],
                "phone": p["phone"],
                "gstin": p["gstin"],
                "total_outstanding": float(p["total_outstanding"]),
                "current": float(p["current"]),
                "days_1_30": float(p["days_1_30"]),
                "days_31_60": float(p["days_31_60"]),
                "days_61_90": float(p["days_61_90"]),
                "above_90": float(p["above_90"]),
                "msme_overdue": p["msme_overdue"],
                "bills_count": p["bills_count"],
            })

        parties_list.sort(key=lambda x: x["total_outstanding"], reverse=True)
        total_out = sum(p["total_outstanding"] for p in parties_list)

        return {
            "party_type": party_type,
            "total_outstanding": float(total_out),
            "parties": parties_list,
            "summary": summary,
        }

    @classmethod
    @transaction.atomic
    def auto_reconcile_all_unallocated(cls, company: Company, party_ledger: Ledger = None) -> dict:
        """
        One-click FIFO reconciliation: takes all unallocated Payment/Receipt vouchers
        and automatically maps them against the oldest unpaid invoices.
        """
        qs = Voucher.objects.filter(
            company=company,
            voucher_type__in=['PAYMENT', 'RECEIPT'],
            status__in=EffectiveVoucherService.ACTIVE_STATUSES
        )
        if party_ledger:
            qs = qs.filter(party_ledger=party_ledger)

        # Clear prior allocations for the targeted payment vouchers in bulk first,
        # so earlier payments in FIFO sequence are not blocked by allocations from later payments.
        PaymentAllocation.objects.filter(payment_voucher__in=qs).delete()

        # Order chronologically so earlier receipts/payments are applied first
        pvs = list(qs.order_by('voucher_date', 'created_at'))

        total_settled_amount = Decimal('0.00')
        allocations_made = 0

        for pv in pvs:
            allocs = cls.auto_allocate_voucher(pv)
            for a in allocs:
                total_settled_amount += Decimal(str(a.get('allocated_amount', 0)))
                allocations_made += 1

        return {
            "success": True,
            "allocations_count": allocations_made,
            "total_settled_amount": float(total_settled_amount),
            "message": f"Successfully settled {allocations_made} bills totaling ₹{total_settled_amount:,.2f} via FIFO."
        }


"""
SriLekh GST Reporting Allocation & Late-Entry Engine.
Separates accounting transaction dates from GST reporting periods in strict accordance
with the Central Goods and Services Tax (CGST) Act, 2017.

Statutory Rules Enforced:
1. Section 37(1) & 37(3): Outward supplies omitted in a prior tax period may be reported
   in subsequent returns up to 30th November following the end of the financial year.
2. Section 16(2)(b): ITC entitlement is conditioned on receipt of goods/services; purchase
   invoices received in a subsequent period are reportable in the tax period of receipt.
3. Section 16(4): ITC claims are strictly statute-barred after 30th November following the
   end of the financial year to which the invoice/debit note pertains.
4. Section 34(2): Credit notes may be declared up to 30th November following the end of the FY.
"""

import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import (
    GSTReportingAllocation,
    GSTRegistration,
    GSTReturnWorkspace,
    GSTAuditLog,
    GSTFilingRecord
)

logger = logging.getLogger('apps.gst.allocation_service')


def quantize_amount(val) -> Decimal:
    if val is None:
        return Decimal('0.00')
    return Decimal(str(val)).quantize(Decimal('0.01'))


class GSTAllocationService:
    """
    Statutory Allocation Engine governing when and how accounting transactions
    are reported in GSTR-1 and GSTR-3B tax returns.
    """

    @classmethod
    def get_financial_year(cls, d: date) -> str:
        """Computes Indian Financial Year string (e.g. '2025-26', '2026-27')."""
        if d.month >= 4:
            return f"{d.year}-{str(d.year + 1)[2:]}"
        return f"{d.year - 1}-{str(d.year)[2:]}"

    @classmethod
    def get_statutory_cutoff_date(
        cls,
        invoice_date: date,
        company: Optional[Company] = None,
        return_type: str = 'GSTR3B',
        registration_revocation_date: Optional[date] = None
    ) -> date:
        """
        Computes statutory deadline pursuant to Section 16(4), Section 16(5), Section 16(6),
        and Section 37(3) of the CGST Act.
        
        Statutory Rules:
        1. Section 16(4) / 37(3): The 30th day of November following the end of the financial year OR
           the date of furnishing of the relevant annual return (GSTR-9), whichever is earlier.
        2. Section 16(5) [Retrospective Non-Obstante via Finance (No. 2) Act, 2024 & Circular 237/31/2024-GST]:
           "Notwithstanding anything contained in sub-section (4)..."
           For invoices/debit notes for FY 2017-18, 2018-19, 2019-20, and 2020-21, the statutory deadline
           for availing ITC in GSTR-3B is fixed at 30th November 2021. The date of furnishing of the Annual
           Return does NOT shorten or restrict this window because Section 16(5) overrides Section 16(4) in toto.
        3. Section 16(6) [Revocation Window Extension]:
           Where registration was cancelled under Section 29 and subsequently revoked under Section 30:
           Taxpayer is entitled to avail ITC up to 30 days from the date of the revocation order, if later
           than the ordinary Section 16(4) / Section 16(5) deadline.
           - For FY 2017-18 through 2020-21: max(30 Nov 2021, revocation_date + 30 days).
           - For FY 2021-22 onwards: max(earlier of 30 Nov or GSTR-9, revocation_date + 30 days).
        """
        fy = cls.get_financial_year(invoice_date)
        is_sec16_5_period = fy in ('2017-18', '2018-19', '2019-20', '2020-21') and return_type in ('GSTR3B', 'INWARD_ITC')

        if is_sec16_5_period:
            # Under non-obstante Section 16(5), GSTR-9 filing date does not override 30-Nov-2021
            base_cutoff = date(2021, 11, 30)
        else:
            fy_end_year = invoice_date.year if invoice_date.month <= 3 else (invoice_date.year + 1)
            base_cutoff = date(fy_end_year, 11, 30)

            # Check if relevant Annual Return (GSTR-9) was furnished earlier than 30th November
            if company:
                ar_filing = GSTFilingRecord.objects.filter(
                    company=company,
                    return_type='GSTR9',
                    status='FILED'
                ).filter(Q(financial_year=fy) | Q(return_period=fy)).order_by('submitted_at').first()
                if ar_filing and ar_filing.submitted_at:
                    ar_date = ar_filing.submitted_at.date()
                    if ar_date < base_cutoff:
                        base_cutoff = ar_date

        # Section 16(6) Revocation Window
        if registration_revocation_date:
            revocation_window = registration_revocation_date + timedelta(days=30)
            if revocation_window > base_cutoff:
                return revocation_window

        return base_cutoff

    @classmethod
    def resolve_event_type(cls, voucher: Voucher) -> str:
        """Determines the statutory GST reporting event type for a voucher."""
        vtype = voucher.voucher_type
        if vtype == 'SALES':
            return 'OUTWARD_SUPPLY'
        elif vtype == 'PURCHASE':
            return 'INWARD_RCM' if getattr(voucher, 'is_reverse_charge', False) else 'INWARD_ITC'
        elif vtype == 'CREDIT_NOTE':
            # Check Section 34 vs Section 15(3)(b) Commercial Credit Note
            orig_ref = getattr(voucher, 'original_invoice', None) or getattr(voucher, 'reference_number', '')
            summary = cls.compute_voucher_monetary_summary(voucher)
            if not orig_ref or summary["total_tax"] <= Decimal('0.00'):
                return 'COMMERCIAL_CREDIT_NOTE'
            return 'CREDIT_NOTE'
        elif vtype == 'DEBIT_NOTE':
            return 'DEBIT_NOTE'
        elif vtype in ('RECEIPT', 'PAYMENT') and getattr(voucher, 'is_advance', False):
            return 'ADVANCE_RECEIVED' if vtype == 'RECEIPT' else 'ADVANCE_ADJUSTED'
        return 'OUTWARD_SUPPLY'

    @classmethod
    def compute_voucher_monetary_summary(cls, voucher: Voucher) -> Dict[str, Decimal]:
        """Calculates aggregated taxable value and tax heads from voucher items."""
        items = voucher.items.all()
        if not items.exists():
            txval = quantize_amount(voucher.total_amount)
            return {
                "taxable_value": txval,
                "igst_amount": Decimal('0.00'),
                "cgst_amount": Decimal('0.00'),
                "sgst_amount": Decimal('0.00'),
                "cess_amount": Decimal('0.00'),
                "total_tax": Decimal('0.00'),
            }

        taxable = Decimal('0.00')
        igst = Decimal('0.00')
        cgst = Decimal('0.00')
        sgst = Decimal('0.00')
        cess = Decimal('0.00')

        for item in items:
            taxable += quantize_amount(item.taxable_amount)
            igst += quantize_amount(item.igst_amount)
            cgst += quantize_amount(item.cgst_amount)
            sgst += quantize_amount(item.sgst_amount)
            cess += quantize_amount(getattr(item, 'cess_amount', 0))

        tot_tax = igst + cgst + sgst + cess
        return {
            "taxable_value": taxable,
            "igst_amount": igst,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "cess_amount": cess,
            "total_tax": tot_tax,
        }

    @classmethod
    def allocate_voucher(
        cls,
        voucher: Voucher,
        preferred_period: Optional[str] = None,
        received_date: Optional[date] = None,
        reason: Optional[str] = None,
        user: Any = None,
        force_reallocate: bool = False,
        goods_received_date: Optional[date] = None,
        is_receipt_confirmed: Optional[bool] = None,
        receipt_type: str = 'SINGLE',
        last_instalment_received: Optional[bool] = None,
        receipt_document_number: str = '',
        receipt_document_type: str = 'NONE',
        receipt_confirmed_at: Optional[Any] = None,
        receipt_confirmed_by: Optional[Any] = None,
        partial_received_fraction: Decimal = Decimal('1.0000'),
        registration_revocation_date: Optional[date] = None
    ) -> GSTReportingAllocation:
        """
        Allocates a voucher to a GST reporting period while preserving accounting immutability.
        Evaluates Section 16(2)(b), First Proviso to Section 16(2), Section 16(4), Section 16(5),
        Section 16(6), and Section 37(3) statutory eligibility rules.
        """
        company = voucher.company
        event_type = cls.resolve_event_type(voucher)
        v_date = voucher.voucher_date
        entry_date = received_date or goods_received_date or (voucher.created_at.date() if voucher.created_at else timezone.now().date())
        original_period = v_date.strftime('%m%Y')
        financial_year = cls.get_financial_year(v_date)
        statutory_cutoff = cls.get_statutory_cutoff_date(
            v_date,
            company=company,
            return_type='INWARD_ITC' if voucher.voucher_type == 'PURCHASE' else 'GSTR1',
            registration_revocation_date=registration_revocation_date
        )

        # 1. Determine Assigned Period & Allocation Reason
        allocation_reason = 'REGULAR'
        assigned_period = original_period
        is_statutorily_eligible = True
        statutory_rule = ''
        statutory_notes = ''
        exclusion_reason = ''

        # Check if original period is already closed/exported in return workspace
        orig_ws = GSTReturnWorkspace.objects.filter(
            company=company,
            return_period=original_period,
            status__in=['EXPORTED', 'REVIEWED']
        ).first()

        is_late_entry = bool(orig_ws or (entry_date.year > v_date.year or entry_date.month > v_date.month))

        # Check Section 16(2)(b) goods/services receipt condition & First Proviso (Fail-closed)
        confirmed_flag = False
        last_inst_flag = True if last_instalment_received is None else bool(last_instalment_received)
        doc_type = receipt_document_type or 'NONE'
        doc_num = (receipt_document_number or '').strip()

        if voucher.voucher_type == 'PURCHASE':
            has_affirmative_evidence = bool(
                is_receipt_confirmed is True or
                goods_received_date or
                received_date or
                doc_num or
                receipt_type == 'LOTS_INSTALMENTS'
            )

            if receipt_type == 'LOTS_INSTALMENTS' and not last_inst_flag:
                confirmed_flag = True
                is_statutorily_eligible = False
                allocation_reason = 'PARTIAL_LOT_PENDING_LAST_INSTALMENT'
                statutory_rule = 'First Proviso to Section 16(2)'
                exclusion_reason = (
                    f"First Proviso to Section 16(2): When goods are received in lots or instalments, "
                    f"ITC can only be availed upon receipt of the last lot or instalment."
                )
                statutory_notes = f"Inward invoice #{voucher.voucher_number}: lot pending last instalment. Excluded."
            elif is_receipt_confirmed is False or not has_affirmative_evidence:
                confirmed_flag = False
                is_statutorily_eligible = False
                allocation_reason = 'GOODS_SERVICES_NOT_RECEIVED'
                statutory_rule = 'CGST Act Section 16(2)(b)'
                exclusion_reason = (
                    f"Section 16(2)(b) statutory condition failed: Goods or services receipt has not been confirmed with "
                    f"affirmative documentation for invoice #{voucher.voucher_number}. ITC cannot be availed until receipt is confirmed."
                )
                statutory_notes = f"Inward invoice #{voucher.voucher_number}: receipt unconfirmed. Excluded from ITC under Sec 16(2)(b)."
            else:
                confirmed_flag = True
                if goods_received_date and not preferred_period:
                    assigned_period = goods_received_date.strftime('%m%Y')
                    if goods_received_date.year > v_date.year or goods_received_date.month > v_date.month:
                        allocation_reason = 'LATE_INWARD_RECEIPT'
                        statutory_rule = 'CGST Act Section 16(2)(b)'
                        statutory_notes = (
                            f"Inward invoice #{voucher.voucher_number} dated {v_date.strftime('%d-%m-%Y')} "
                            f"received on {goods_received_date.strftime('%d-%m-%Y')}. ITC claimed in receipt period {assigned_period}."
                        )
        elif event_type == 'COMMERCIAL_CREDIT_NOTE':
            confirmed_flag = True
            allocation_reason = 'COMMERCIAL_CREDIT_NOTE_NO_TAX'
            statutory_rule = 'CGST Act Section 15(3)(b) (Commercial Discount / Credit Note)'
            statutory_notes = (
                f"Commercial credit note #{voucher.voucher_number} without GST adjustment / original invoice reference. "
                f"Excluded from GSTR-1 Table 9B pursuant to Section 15(3)(b)."
            )
        else:
            confirmed_flag = True

        if preferred_period:
            assigned_period = preferred_period.strip().replace('-', '').replace('/', '')
            if is_statutorily_eligible and event_type != 'COMMERCIAL_CREDIT_NOTE':
                allocation_reason = reason or ('MANUAL_REALLOCATION' if assigned_period != original_period else 'REGULAR')
        elif is_late_entry and is_statutorily_eligible and event_type != 'COMMERCIAL_CREDIT_NOTE':
            # Determine appropriate late entry period based on statutory rules
            assigned_period = entry_date.strftime('%m%Y')
            if voucher.voucher_type == 'SALES':
                allocation_reason = 'LATE_OUTWARD_SUPPLY'
                statutory_rule = 'CGST Act Section 37(1) / 37(3)'
                statutory_notes = (
                    f"Outward invoice #{voucher.voucher_number} dated {v_date.strftime('%d-%m-%Y')} "
                    f"entered late on {entry_date.strftime('%d-%m-%Y')}. Allocated to active return period {assigned_period}."
                )
            elif voucher.voucher_type == 'PURCHASE' and not goods_received_date:
                allocation_reason = 'LATE_INWARD_RECEIPT'
                statutory_rule = 'CGST Act Section 16(2)(b)'
                statutory_notes = (
                    f"Inward invoice #{voucher.voucher_number} dated {v_date.strftime('%d-%m-%Y')} "
                    f"recorded as received on {entry_date.strftime('%d-%m-%Y')}. ITC claimed in receipt period {assigned_period}."
                )
            elif voucher.voucher_type in ('CREDIT_NOTE', 'DEBIT_NOTE'):
                allocation_reason = 'LATE_OUTWARD_SUPPLY'
                statutory_rule = 'CGST Act Section 34(2)'
                statutory_notes = f"Credit/Debit note dated {v_date.strftime('%d-%m-%Y')} allocated to active period {assigned_period}."

        # 2. Check Statutory Section 16(4) and Section 37(3) Time Bars
        # If entry date (or assigned period date) is after statutory cutoff
        assigned_month = int(assigned_period[:2]) if len(assigned_period) >= 2 else entry_date.month
        assigned_year = int(assigned_period[2:]) if len(assigned_period) >= 6 else entry_date.year
        assigned_date_proxy = date(assigned_year, assigned_month, 1)

        if entry_date > statutory_cutoff or assigned_date_proxy > statutory_cutoff:
            if voucher.voucher_type == 'PURCHASE':
                is_statutorily_eligible = False
                allocation_reason = 'RESTRICTED_SECTION_16_4'
                statutory_rule = 'CGST Act Section 16(4)'
                statutory_notes = (
                    f"Statutory ITC deadline expired on {statutory_cutoff.strftime('%d-%m-%Y')} "
                    f"for FY {financial_year}. Input Tax Credit is statute-barred."
                )
                exclusion_reason = (
                    f"Section 16(4) time-limit exceeded: ITC cannot be availed after 30th November "
                    f"cutoff ({statutory_cutoff.strftime('%d-%m-%Y')}) following the end of financial year {financial_year}."
                )
            elif voucher.voucher_type == 'SALES':
                is_statutorily_eligible = False
                allocation_reason = 'STATUTORY_DEADLINE_EXCEEDED'
                statutory_rule = 'CGST Act Section 37(3)'
                statutory_notes = (
                    f"Statutory amendment/addition deadline expired on {statutory_cutoff.strftime('%d-%m-%Y')} "
                    f"for FY {financial_year}."
                )
                exclusion_reason = (
                    f"Section 37(3) time bar: Outward supply omissions cannot be reported in GSTR-1 "
                    f"after 30th November cutoff ({statutory_cutoff.strftime('%d-%m-%Y')}) following financial year {financial_year}."
                )

        # 3. Monetary Snapshot
        summary = cls.compute_voucher_monetary_summary(voucher)

        # Handle Partial Receipt Proportionate ITC (Section 16(2)(b))
        if voucher.voucher_type == 'PURCHASE' and Decimal('0.0000') < partial_received_fraction < Decimal('1.0000'):
            summary["taxable_value"] = quantize_amount(summary["taxable_value"] * partial_received_fraction)
            summary["igst_amount"] = quantize_amount(summary["igst_amount"] * partial_received_fraction)
            summary["cgst_amount"] = quantize_amount(summary["cgst_amount"] * partial_received_fraction)
            summary["sgst_amount"] = quantize_amount(summary["sgst_amount"] * partial_received_fraction)
            summary["cess_amount"] = quantize_amount(summary["cess_amount"] * partial_received_fraction)
            summary["total_tax"] = summary["igst_amount"] + summary["cgst_amount"] + summary["sgst_amount"] + summary["cess_amount"]
            if is_statutorily_eligible:
                allocation_reason = 'PARTIAL_RECEIPT_PROPORTIONATE'
                statutory_rule = 'CGST Act Section 16(2)(b) (Proportionate Delivery)'
                statutory_notes = (
                    f"Inward invoice #{voucher.voucher_number}: Partial receipt of {partial_received_fraction * 100:.2f}%. "
                    f"Proportionate ITC claimed in period {assigned_period}."
                )

        # 4. Check for existing active allocation
        existing_alloc = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type=event_type,
            is_active=True
        ).first()

        if existing_alloc and not force_reallocate:
            # If period and eligibility remain identical, return existing (idempotent)
            if (existing_alloc.assigned_period == assigned_period and
                existing_alloc.is_statutorily_eligible == is_statutorily_eligible and
                existing_alloc.is_receipt_confirmed == confirmed_flag and
                existing_alloc.last_instalment_received == last_inst_flag and
                existing_alloc.partial_received_fraction == partial_received_fraction and
                existing_alloc.receipt_document_number == doc_num):
                # Update amounts if voucher item totals changed
                existing_alloc.taxable_value = summary["taxable_value"]
                existing_alloc.igst_amount = summary["igst_amount"]
                existing_alloc.cgst_amount = summary["cgst_amount"]
                existing_alloc.sgst_amount = summary["sgst_amount"]
                existing_alloc.cess_amount = summary["cess_amount"]
                existing_alloc.total_tax = summary["total_tax"]
                existing_alloc.save(update_fields=[
                    'taxable_value', 'igst_amount', 'cgst_amount',
                    'sgst_amount', 'cess_amount', 'total_tax', 'updated_at'
                ])
                return existing_alloc

        # 5. Create or Supersede Allocation within an atomic transaction
        with transaction.atomic():
            # If an existing active allocation exists, mark it SUPERSEDED
            version = 1
            if existing_alloc:
                version = GSTReportingAllocation.objects.filter(voucher=voucher, event_type=event_type).count() + 1
                existing_alloc.is_active = False
                existing_alloc.status = 'SUPERSEDED'
                existing_alloc.superseded_at = timezone.now()
                existing_alloc.save(update_fields=['is_active', 'status', 'superseded_at'])

            idempotency_key = f"alloc_{company.id}_{voucher.id}_{event_type}_v{version}_{assigned_period}"

            new_alloc = GSTReportingAllocation.objects.create(
                company=company,
                voucher=voucher,
                gst_registration=getattr(voucher, 'gst_registration', None),
                event_type=event_type,
                voucher_date=v_date,
                entry_date=entry_date,
                goods_received_date=goods_received_date,
                is_receipt_confirmed=confirmed_flag,
                receipt_type=receipt_type,
                last_instalment_received=last_inst_flag,
                receipt_document_number=doc_num,
                receipt_document_type=doc_type,
                receipt_confirmed_at=receipt_confirmed_at or (timezone.now() if confirmed_flag else None),
                receipt_confirmed_by=receipt_confirmed_by or (user if confirmed_flag else None),
                partial_received_fraction=partial_received_fraction,
                original_period=original_period,
                assigned_period=assigned_period,
                financial_year=financial_year,
                allocation_reason=allocation_reason,
                status='APPROVED' if is_statutorily_eligible else 'EXCLUDED',
                is_statutorily_eligible=is_statutorily_eligible,
                statutory_rule=statutory_rule,
                statutory_notes=statutory_notes,
                exclusion_reason=exclusion_reason,
                taxable_value=summary["taxable_value"],
                igst_amount=summary["igst_amount"],
                cgst_amount=summary["cgst_amount"],
                sgst_amount=summary["sgst_amount"],
                cess_amount=summary["cess_amount"],
                total_tax=summary["total_tax"],
                is_active=True,
                idempotency_key=idempotency_key,
                created_by=user
            )

            if existing_alloc:
                existing_alloc.superseded_by = new_alloc
                existing_alloc.save(update_fields=['superseded_by'])

            # Log Audit Trail
            if orig_ws or is_late_entry or not is_statutorily_eligible:
                GSTAuditLog.objects.create(
                    company=company,
                    action='GSTR1_PREPARE' if voucher.voucher_type == 'SALES' else 'GSTR2B_RECONCILE',
                    correlation_id=f"ALLOC-{new_alloc.id.hex[:12].upper()}",
                    endpoint='/api/v1/gst/allocations/',
                    http_method='POST',
                    is_success=True,
                    request_summary={
                        "voucher_id": str(voucher.id),
                        "voucher_number": voucher.voucher_number,
                        "original_period": original_period,
                        "assigned_period": assigned_period,
                        "reason": allocation_reason,
                        "is_eligible": is_statutorily_eligible
                    },
                    response_summary={"allocation_id": str(new_alloc.id), "status": new_alloc.status},
                    performed_by=user
                )

        return new_alloc

    @classmethod
    def reallocate_voucher(
        cls,
        voucher: Voucher,
        new_period: Optional[str] = None,
        reason: str = "Manual accountant reallocation",
        user: Any = None,
        target_period: Optional[str] = None
    ) -> GSTReportingAllocation:
        """
        Manually reallocates a voucher to a different GST return period.
        Preserves original allocation in historical audit chain (Scenario D).
        """
        period_to_use = new_period or target_period
        if not period_to_use:
            raise ValueError("Target period must be provided.")
        clean_period = period_to_use.strip().replace('-', '').replace('/', '')

        statutory_cutoff = cls.get_statutory_cutoff_date(
            voucher.voucher_date,
            company=voucher.company,
            return_type='INWARD_ITC' if voucher.voucher_type == 'PURCHASE' else 'GSTR1'
        )
        target_month = int(clean_period[:2]) if len(clean_period) >= 2 else 1
        target_year = int(clean_period[2:]) if len(clean_period) >= 6 else 2026
        target_date_proxy = date(target_year, target_month, 1)

        if target_date_proxy > statutory_cutoff:
            fy = cls.get_financial_year(voucher.voucher_date)
            raise ValueError(
                f"Cannot reallocate to period {clean_period}: statutory deadline for FY {fy} "
                f"expired on {statutory_cutoff.strftime('%d-%m-%Y')}."
            )

        return cls.allocate_voucher(
            voucher=voucher,
            preferred_period=clean_period,
            reason='MANUAL_REALLOCATION',
            user=user,
            force_reallocate=True
        )

    @classmethod
    def handle_voucher_reversal(
        cls,
        voucher: Voucher,
        reversal_voucher: Voucher,
        user: Any = None,
        reversal_reason: Optional[str] = None
    ) -> Optional[GSTReportingAllocation]:
        """
        Handles GST allocation lifecycle when a voucher is reversed.
        If the original voucher's assigned return has not been exported or filed,
        the active allocation is deactivated so neither original nor reversal appears in the unfiled return.
        If the original return WAS already exported or filed, the historical allocation remains
        active/reported, and an auditable reversal allocation is created for the reversal voucher.

        Statutory Semantics:
        - Section 34 Credit Notes (voucher_type == 'CREDIT_NOTE') are genuine GST credit notes reportable
          in GSTR-1 Table 9B.
        - Internal accounting reversal journals (voucher_type == 'JOURNAL') are internal adjustments that
          do NOT satisfy Section 34 / Rule 53 and are tagged INTERNAL_ACCOUNTING_REVERSAL, excluded from GSTR-1 Table 9B.
        - Inward reversals are categorized under Rule 37 (180 days non-payment), Rule 37A (vendor default),
          Rule 42/43 (common credit attribution), or Section 17(5) (blocked credits).
        """
        active_alloc = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            is_active=True
        ).first()

        if not active_alloc:
            return None

        # Check if workspace for active_alloc.assigned_period was exported/filed or marked filed
        ws = GSTReturnWorkspace.objects.filter(
            company=voucher.company,
            return_period=active_alloc.assigned_period,
            status__in=['EXPORTED', 'REVIEWED', 'FILED']
        ).first()

        is_filed_or_exported = bool(
            active_alloc.status in ['FILED', 'REPORTED'] or
            ws or
            GSTFilingRecord.objects.filter(company=voucher.company, return_period=active_alloc.assigned_period, status='FILED').exists()
        )

        if not is_filed_or_exported:
            # Workspace is unfiled / open: deactivate original allocation
            active_alloc.is_active = False
            active_alloc.status = 'SUPERSEDED'
            active_alloc.superseded_at = timezone.now()
            active_alloc.save(update_fields=['is_active', 'status', 'superseded_at'])
            return active_alloc
        else:
            # Historical return was already exported/filed: create adjustment allocation for reversal
            rev_period = reversal_voucher.voucher_date.strftime('%m%Y')
            summary = cls.compute_voucher_monetary_summary(reversal_voucher)

            # Determine statutory event type and rule based on reversal voucher type and nature
            rev_type = reversal_voucher.voucher_type
            reason_str = (reversal_reason or reversal_voucher.narration or '').upper()

            if active_alloc.event_type in ('OUTWARD_SUPPLY', 'CREDIT_NOTE', 'DEBIT_NOTE'):
                if rev_type == 'CREDIT_NOTE':
                    orig_ref = getattr(reversal_voucher, 'original_invoice', None) or getattr(reversal_voucher, 'reference_number', '') or voucher.voucher_number
                    if summary["total_tax"] > Decimal('0.00') and orig_ref:
                        event_type = 'CREDIT_NOTE'
                        allocation_reason = 'REVERSAL_CREDIT_NOTE'
                        statutory_rule = 'CGST Act Section 34(1) / Rule 53'
                        statutory_notes = f"Statutory Section 34 Credit Note reversing sales invoice #{voucher.voucher_number}."
                    else:
                        event_type = 'COMMERCIAL_CREDIT_NOTE'
                        allocation_reason = 'COMMERCIAL_CREDIT_NOTE_NO_TAX'
                        statutory_rule = 'CGST Act Section 15(3)(b) (Financial / Commercial Credit Note)'
                        statutory_notes = (
                            f"Commercial credit note for invoice #{voucher.voucher_number} with zero tax / financial discount. "
                            f"Excluded from GSTR-1 Table 9B pursuant to Section 15(3)(b)."
                        )
                else:
                    event_type = 'INTERNAL_ACCOUNTING_REVERSAL'
                    allocation_reason = 'REVERSAL_INTERNAL_JOURNAL'
                    statutory_rule = 'Internal Double-Entry Adjustment (Non-Section 34)'
                    statutory_notes = (
                        f"Internal accounting reversal journal for invoice #{voucher.voucher_number}. "
                        f"Does NOT satisfy Section 34 credit note criteria; excluded from GSTR-1 Table 9B."
                    )
            elif active_alloc.event_type in ('INWARD_ITC', 'INWARD_RCM'):
                if 'RULE_37A' in reason_str:
                    event_type = 'ITC_REVERSAL_RULE_37A'
                    allocation_reason = 'REVERSAL_RULE_37A'
                    statutory_rule = 'CGST Rules Rule 37A (Supplier default in GSTR-3B)'
                    statutory_notes = f"ITC Reversal under Rule 37A for invoice #{voucher.voucher_number}."
                elif 'RULE_37' in reason_str:
                    event_type = 'ITC_REVERSAL_RULE_37'
                    allocation_reason = 'REVERSAL_RULE_37'
                    statutory_rule = 'CGST Rules Rule 37 (180-day non-payment)'
                    statutory_notes = f"ITC Reversal under Rule 37 for invoice #{voucher.voucher_number}."
                elif 'RULE_42' in reason_str or 'RULE_43' in reason_str:
                    event_type = 'ITC_REVERSAL_RULE_42'
                    allocation_reason = 'REVERSAL_RULE_42_43'
                    statutory_rule = 'CGST Rules Rule 42/43 (Exempt/non-business credit attribution)'
                    statutory_notes = f"ITC Reversal under Rule 42/43 for invoice #{voucher.voucher_number}."
                elif '17(5)' in reason_str or 'SECTION_17_5' in reason_str:
                    event_type = 'ITC_REVERSAL_SEC_17_5'
                    allocation_reason = 'REVERSAL_SECTION_17_5'
                    statutory_rule = 'CGST Act Section 17(5) (Ineligible blocked credit)'
                    statutory_notes = f"ITC Reversal under Section 17(5) for invoice #{voucher.voucher_number}."
                else:
                    event_type = 'ITC_REVERSAL_OTHER'
                    allocation_reason = 'REVERSAL_ADJUSTMENT'
                    statutory_rule = 'CGST Act Section 16 / Rule 42'
                    statutory_notes = f"ITC Reversal for invoice #{voucher.voucher_number} allocated to {rev_period}."
            else:
                event_type = 'INTERNAL_ACCOUNTING_REVERSAL'
                allocation_reason = 'REVERSAL_ADJUSTMENT'
                statutory_rule = 'General Accounting Reversal'
                statutory_notes = f"Reversal of transaction #{voucher.voucher_number} allocated to {rev_period}."

            rev_alloc = GSTReportingAllocation.objects.create(
                company=voucher.company,
                voucher=reversal_voucher,
                gst_registration=active_alloc.gst_registration,
                event_type=event_type,
                voucher_date=reversal_voucher.voucher_date,
                entry_date=reversal_voucher.created_at.date() if reversal_voucher.created_at else timezone.now().date(),
                original_period=active_alloc.assigned_period,
                assigned_period=rev_period,
                financial_year=cls.get_financial_year(reversal_voucher.voucher_date),
                allocation_reason=allocation_reason,
                status='APPROVED',
                is_statutorily_eligible=True,
                statutory_rule=statutory_rule,
                statutory_notes=statutory_notes,
                taxable_value=summary["taxable_value"],
                igst_amount=summary["igst_amount"],
                cgst_amount=summary["cgst_amount"],
                sgst_amount=summary["sgst_amount"],
                cess_amount=summary["cess_amount"],
                total_tax=summary["total_tax"],
                is_active=True,
                idempotency_key=f"alloc_rev_{voucher.company.id}_{reversal_voucher.id}_{rev_period}",
                created_by=user
            )
            return rev_alloc

    @classmethod
    def ensure_allocations_for_period(cls, company: Company, period_code: str) -> int:
        """
        Ensures all active vouchers relevant to this company and period range
        have active GSTReportingAllocation records. Guarantees 100% backward compatibility.
        """
        from apps.gst.services.returns_service import GSTReturnsService
        start_date, end_date, _, _ = GSTReturnsService.parse_period(period_code)

        unallocated_vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'PURCHASE', 'CREDIT_NOTE', 'DEBIT_NOTE'],
            voucher_date__gte=start_date,
            voucher_date__lte=end_date,
            status__in=['POSTED', 'EXPORTED', 'FILED']
        ).exclude(
            gst_allocations__is_active=True
        ).distinct()

        created_count = 0
        for v in unallocated_vouchers:
            cls.allocate_voucher(
                v,
                preferred_period=period_code,
                is_receipt_confirmed=True if v.voucher_type == 'PURCHASE' else None,
                goods_received_date=v.voucher_date if v.voucher_type == 'PURCHASE' else None
            )
            created_count += 1

        return created_count

    @classmethod
    def get_allocations_for_period(
        cls,
        company: Company,
        return_type: str,
        period: str,
        registration: Optional[GSTRegistration] = None,
        only_eligible: bool = True
    ):
        """
        Returns active GSTReportingAllocation queryset assigned to the target return period.
        Strictly enforces tenant isolation and statutory eligibility filtering.
        """
        clean_period = period.strip().replace('-', '').replace('/', '')
        qs = GSTReportingAllocation.objects.filter(
            company=company,
            assigned_period=clean_period,
            is_active=True
        ).select_related('voucher', 'voucher__party_ledger')

        if registration:
            qs = qs.filter(Q(gst_registration=registration) | Q(gst_registration__isnull=True))

        if return_type == 'GSTR1':
            qs = qs.filter(event_type__in=['OUTWARD_SUPPLY', 'CREDIT_NOTE', 'DEBIT_NOTE', 'ADVANCE_RECEIVED', 'ADVANCE_ADJUSTED'])
        elif return_type == 'GSTR3B':
            # GSTR3B aggregates both outward supplies and inward ITC
            pass

        if only_eligible:
            qs = qs.filter(is_statutorily_eligible=True)

        return qs

    @classmethod
    def get_excluded_allocations_for_period(
        cls,
        company: Company,
        period: str,
        return_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves transactions excluded from the return period with full statutory reasons.
        """
        clean_period = period.strip().replace('-', '').replace('/', '')
        qs = GSTReportingAllocation.objects.filter(
            company=company,
            assigned_period=clean_period,
            is_active=True,
            is_statutorily_eligible=False
        ).select_related('voucher')

        if return_type == 'GSTR1':
            qs = qs.filter(event_type__in=['OUTWARD_SUPPLY', 'CREDIT_NOTE', 'DEBIT_NOTE'])
        elif return_type == 'GSTR3B':
            qs = qs.filter(event_type__in=['INWARD_ITC', 'INWARD_RCM'])

        excluded = []
        for alloc in qs:
            excluded.append({
                "voucher_id": str(alloc.voucher.id),
                "voucher_number": alloc.voucher.voucher_number,
                "voucher_type": alloc.voucher.voucher_type,
                "voucher_date": alloc.voucher_date.strftime('%Y-%m-%d'),
                "event_type": alloc.event_type,
                "allocation_reason": alloc.allocation_reason,
                "statutory_rule": alloc.statutory_rule,
                "exclusion_reason": alloc.exclusion_reason,
                "taxable_value": float(alloc.taxable_value),
                "total_tax": float(alloc.total_tax),
            })
        return excluded

    @classmethod
    def calculate_rule37_reversal(
        cls,
        total_invoice_amount: Decimal,
        unpaid_amount: Decimal,
        total_tax: Decimal
    ) -> Decimal:
        """
        Calculates proportionate ITC reversal under Second Proviso to Section 16(2) and Rule 37(1).
        Reversal Amount = (Unpaid Amount / Total Invoice Amount) * Total ITC Availed.
        """
        tot_inv = quantize_amount(total_invoice_amount)
        unpaid = quantize_amount(unpaid_amount)
        tax = quantize_amount(total_tax)
        if tot_inv <= Decimal('0.00') or unpaid <= Decimal('0.00'):
            return Decimal('0.00')
        fraction = min(Decimal('1.0000'), unpaid / tot_inv)
        return quantize_amount(fraction * tax)

    @classmethod
    def create_rule37_reversal_allocation(
        cls,
        voucher: Voucher,
        unpaid_amount: Decimal,
        assigned_period: str,
        user: Any = None
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reversal allocation under Rule 37 (180 days non-payment) for GSTR-3B Table 4(B)(2).
        """
        summary = cls.compute_voucher_monetary_summary(voucher)
        rev_tax = cls.calculate_rule37_reversal(voucher.total_amount, unpaid_amount, summary["total_tax"])
        
        tot_tax = summary["total_tax"]
        ratio = (rev_tax / tot_tax) if tot_tax > Decimal('0.00') else Decimal('0.00')
        igst_rev = quantize_amount(summary["igst_amount"] * ratio)
        cgst_rev = quantize_amount(summary["cgst_amount"] * ratio)
        sgst_rev = quantize_amount(summary["sgst_amount"] * ratio)
        cess_rev = quantize_amount(summary["cess_amount"] * ratio)

        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        alloc = GSTReportingAllocation.objects.create(
            company=voucher.company,
            voucher=voucher,
            gst_registration=getattr(voucher, 'gst_registration', None),
            event_type='ITC_REVERSAL_RULE_37',
            voucher_date=voucher.voucher_date,
            entry_date=timezone.now().date(),
            original_period=voucher.voucher_date.strftime('%m%Y'),
            assigned_period=clean_period,
            financial_year=cls.get_financial_year(voucher.voucher_date),
            allocation_reason='REVERSAL_RULE_37',
            status='APPROVED',
            is_statutorily_eligible=True,
            statutory_rule='CGST Rules Rule 37 (180-day non-payment)',
            statutory_notes=(
                f"Rule 37 180-day ITC Reversal for invoice #{voucher.voucher_number}: "
                f"unpaid amount ₹{unpaid_amount} of ₹{voucher.total_amount}."
            ),
            taxable_value=Decimal('0.00'),
            igst_amount=igst_rev,
            cgst_amount=cgst_rev,
            sgst_amount=sgst_rev,
            cess_amount=cess_rev,
            total_tax=rev_tax,
            is_active=True,
            idempotency_key=f"rule37_rev_{voucher.company.id}_{voucher.id}_{clean_period}",
            created_by=user
        )
        return alloc

    @classmethod
    def create_rule37_reclaim_allocation(
        cls,
        voucher: Voucher,
        paid_amount: Decimal,
        assigned_period: str,
        user: Any = None
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reclaim allocation under Third Proviso to Section 16(2) and Rule 37(4).
        Entitled to reclaim without Section 16(4) time-limit bar.
        Reportable in GSTR-3B Table 4(A)(5) and Table 4(D)(1).
        """
        summary = cls.compute_voucher_monetary_summary(voucher)
        reclaim_tax = cls.calculate_rule37_reversal(voucher.total_amount, paid_amount, summary["total_tax"])
        
        tot_tax = summary["total_tax"]
        ratio = (reclaim_tax / tot_tax) if tot_tax > Decimal('0.00') else Decimal('0.00')
        igst_rec = quantize_amount(summary["igst_amount"] * ratio)
        cgst_rec = quantize_amount(summary["cgst_amount"] * ratio)
        sgst_rec = quantize_amount(summary["sgst_amount"] * ratio)
        cess_rec = quantize_amount(summary["cess_amount"] * ratio)

        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        alloc = GSTReportingAllocation.objects.create(
            company=voucher.company,
            voucher=voucher,
            gst_registration=getattr(voucher, 'gst_registration', None),
            event_type='ITC_RECLAIM',
            voucher_date=voucher.voucher_date,
            entry_date=timezone.now().date(),
            original_period=voucher.voucher_date.strftime('%m%Y'),
            assigned_period=clean_period,
            financial_year=cls.get_financial_year(voucher.voucher_date),
            allocation_reason='RECLAIM_RULE_37',
            status='APPROVED',
            is_statutorily_eligible=True,
            statutory_rule='Third Proviso to Section 16(2) / Rule 37(4)',
            statutory_notes=(
                f"Rule 37(4) ITC Reclaim upon payment of ₹{paid_amount} for invoice #{voucher.voucher_number}. "
                f"Exempt from Section 16(4) time-limit."
            ),
            taxable_value=quantize_amount((paid_amount / voucher.total_amount) * summary["taxable_value"]) if voucher.total_amount > 0 else Decimal('0.00'),
            igst_amount=igst_rec,
            cgst_amount=cgst_rec,
            sgst_amount=sgst_rec,
            cess_amount=cess_rec,
            total_tax=reclaim_tax,
            is_active=True,
            idempotency_key=f"rule37_rec_{voucher.company.id}_{voucher.id}_{clean_period}_{int(paid_amount*100)}",
            created_by=user
        )
        return alloc

    @classmethod
    def create_rule37a_reversal_allocation(
        cls,
        voucher: Voucher,
        assigned_period: str,
        user: Any = None
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reversal allocation under Rule 37A (Supplier default in GSTR-3B) for Table 4(B)(2).
        Must be reversed on or before 30th November following end of FY in which ITC was availed.
        """
        summary = cls.compute_voucher_monetary_summary(voucher)
        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        alloc = GSTReportingAllocation.objects.create(
            company=voucher.company,
            voucher=voucher,
            gst_registration=getattr(voucher, 'gst_registration', None),
            event_type='ITC_REVERSAL_RULE_37A',
            voucher_date=voucher.voucher_date,
            entry_date=timezone.now().date(),
            original_period=voucher.voucher_date.strftime('%m%Y'),
            assigned_period=clean_period,
            financial_year=cls.get_financial_year(voucher.voucher_date),
            allocation_reason='REVERSAL_RULE_37A',
            status='APPROVED',
            is_statutorily_eligible=True,
            statutory_rule='CGST Rules Rule 37A (Supplier non-payment of tax / GSTR-3B default)',
            statutory_notes=(
                f"Rule 37A ITC Reversal for invoice #{voucher.voucher_number}: supplier defaulted on GSTR-3B filing."
            ),
            taxable_value=Decimal('0.00'),
            igst_amount=summary["igst_amount"],
            cgst_amount=summary["cgst_amount"],
            sgst_amount=summary["sgst_amount"],
            cess_amount=summary["cess_amount"],
            total_tax=summary["total_tax"],
            is_active=True,
            idempotency_key=f"rule37a_rev_{voucher.company.id}_{voucher.id}_{clean_period}",
            created_by=user
        )
        return alloc

    @classmethod
    def create_rule37a_reclaim_allocation(
        cls,
        voucher: Voucher,
        assigned_period: str,
        user: Any = None
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reclaim allocation under Proviso to Rule 37A when supplier subsequently files GSTR-3B.
        Reclaim is permitted without any Section 16(4) time-limit bar.
        """
        summary = cls.compute_voucher_monetary_summary(voucher)
        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        alloc = GSTReportingAllocation.objects.create(
            company=voucher.company,
            voucher=voucher,
            gst_registration=getattr(voucher, 'gst_registration', None),
            event_type='ITC_RECLAIM',
            voucher_date=voucher.voucher_date,
            entry_date=timezone.now().date(),
            original_period=voucher.voucher_date.strftime('%m%Y'),
            assigned_period=clean_period,
            financial_year=cls.get_financial_year(voucher.voucher_date),
            allocation_reason='RECLAIM_RULE_37A',
            status='APPROVED',
            is_statutorily_eligible=True,
            statutory_rule='Proviso to CGST Rules Rule 37A (Reclaim after supplier files GSTR-3B)',
            statutory_notes=(
                f"Rule 37A ITC Reclaim for invoice #{voucher.voucher_number}: supplier subsequently filed GSTR-3B."
            ),
            taxable_value=summary["taxable_value"],
            igst_amount=summary["igst_amount"],
            cgst_amount=summary["cgst_amount"],
            sgst_amount=summary["sgst_amount"],
            cess_amount=summary["cess_amount"],
            total_tax=summary["total_tax"],
            is_active=True,
            idempotency_key=f"rule37a_rec_{voucher.company.id}_{voucher.id}_{clean_period}",
            created_by=user
        )
        return alloc

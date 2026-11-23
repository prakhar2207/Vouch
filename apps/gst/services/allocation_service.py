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
import json
import hashlib
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Q

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import (
    GSTReportingAllocation,
    GSTRegistration,
    GSTReturnWorkspace,
    GSTAuditLog,
    GSTFilingRecord,
    GSTR2BRecord,
    SupplierGSTR3BFilingRecord,
    GSTReversalReclaimLineage,
)
from apps.gst.services.rule37a_evidence_service import (
    Rule37AEvidenceService,
    compute_rule37a_evidence_hash,
)

logger = logging.getLogger('apps.gst.allocation_service')


def quantize_amount(val) -> Decimal:
    if val is None:
        return Decimal('0.00')
    return Decimal(str(val)).quantize(Decimal('0.01'))


def compute_payment_event_fingerprint(
    company_id: Any,
    voucher_id: Any,
    payment_event_id: str,
    paid_amount: Decimal,
    payment_date: Optional[date] = None,
    payment_allocation_id: Optional[Any] = None,
    payment_reference: Optional[str] = None,
    currency: str = 'INR'
) -> str:
    """
    Computes canonical immutable SHA-256 fingerprint of a payment event.
    Ensures payload integrity across idempotency retries under P0 payment-event requirements.
    """
    payload = {
        "company_id": str(company_id),
        "voucher_id": str(voucher_id),
        "payment_event_id": str(payment_event_id).strip(),
        "paid_amount": str(quantize_amount(paid_amount)),
        "currency": currency.upper(),
        "payment_date": str(payment_date) if payment_date else "",
        "payment_allocation_id": str(payment_allocation_id) if payment_allocation_id else "",
        "payment_reference": str(payment_reference or "").strip(),
    }
    canonical_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()


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

            # Check 1: Duplicate GRN rejected
            dup_grn = None
            if doc_type == 'GRN' and doc_num:
                dup_grn = GSTReportingAllocation.objects.filter(
                    company=company,
                    receipt_document_type='GRN',
                    receipt_document_number=doc_num,
                    is_active=True
                ).exclude(voucher=voucher).first()

            if dup_grn:
                confirmed_flag = False
                is_statutorily_eligible = False
                allocation_reason = 'GOODS_SERVICES_NOT_RECEIVED'
                statutory_rule = 'CGST Act Section 16(2)(b) (Duplicate Receipt Evidence)'
                exclusion_reason = (
                    f"Duplicate GRN #{doc_num} rejected: already associated with invoice #{dup_grn.voucher.voucher_number}."
                )
                statutory_notes = f"Inward invoice #{voucher.voucher_number}: duplicate GRN #{doc_num} rejected."
            # Check 2: First Proviso to Section 16(2) - Goods in lots/instalments
            elif receipt_type == 'LOTS_INSTALMENTS' and not last_inst_flag:
                confirmed_flag = True
                is_statutorily_eligible = False
                allocation_reason = 'PARTIAL_LOT_PENDING_LAST_INSTALMENT'
                statutory_rule = 'First Proviso to Section 16(2)'
                exclusion_reason = (
                    f"First Proviso to Section 16(2): When goods are received in lots or instalments, "
                    f"ITC can only be availed upon receipt of the last lot or instalment."
                )
                statutory_notes = f"Inward invoice #{voucher.voucher_number}: lot pending last instalment. Excluded."
            # Check 3: E-Way Bill in-transit without confirmed physical receipt fails closed
            elif doc_type == 'EWAY_BILL' and is_receipt_confirmed is not True:
                confirmed_flag = False
                is_statutorily_eligible = False
                allocation_reason = 'GOODS_SERVICES_NOT_RECEIVED'
                statutory_rule = 'CGST Act Section 16(2)(b)'
                exclusion_reason = (
                    f"Section 16(2)(b): E-Way Bill exists ({doc_num or 'in-transit'}) but physical receipt "
                    f"has not been confirmed. Goods remain in transit."
                )
                statutory_notes = f"Inward invoice #{voucher.voucher_number}: E-Way Bill in-transit; physical receipt unconfirmed."
            # Check 4: Service completion unconfirmed fails closed
            elif receipt_type == 'SERVICE_COMPLETION' and is_receipt_confirmed is not True and not has_affirmative_evidence:
                confirmed_flag = False
                is_statutorily_eligible = False
                allocation_reason = 'GOODS_SERVICES_NOT_RECEIVED'
                statutory_rule = 'CGST Act Section 16(2)(b)'
                exclusion_reason = (
                    f"Section 16(2)(b): Service receipt/completion certificate has not been confirmed for invoice #{voucher.voucher_number}."
                )
                statutory_notes = f"Inward invoice #{voucher.voucher_number}: service completion unconfirmed."
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
    def calculate_section_50_interest(
        cls,
        tax_amount: Decimal,
        start_date: date,
        end_date: date,
        annual_rate: Decimal = Decimal('18.00'),
        statutory_rule: str = 'CGST Act Section 50(1) @ 18% p.a.',
        is_verified_fact: bool = False
    ) -> Dict[str, Any]:
        """
        Calculates statutory interest under Section 50(1) of the CGST Act at the statutory rate (18% p.a.).
        Handles leap year precision (366 days in leap years, 365 in standard years) across the delay period.
        Differentiates between verified fact and statutory estimate (is_estimate).
        """
        import calendar
        tax = quantize_amount(tax_amount)
        if tax <= Decimal('0.00') or end_date <= start_date:
            return {
                "tax_amount": tax,
                "start_date": start_date,
                "end_date": end_date,
                "days_delay": 0,
                "annual_rate": annual_rate,
                "interest_amount": Decimal('0.00'),
                "statutory_provision": statutory_rule,
                "is_estimate": not is_verified_fact,
                "year_days": 365,
                "statutory_notes": "No interest payable (delay days <= 0 or tax amount <= 0)."
            }

        days_delay = (end_date - start_date).days

        # Precision leap year breakdown
        total_interest = Decimal('0.00')
        cur_year = start_date.year
        cur_date = start_date
        year_days_summary = []

        while cur_date < end_date:
            year_end = date(cur_year, 12, 31)
            segment_end = min(end_date, year_end)
            seg_days = (segment_end - cur_date).days
            if segment_end == year_end and end_date > year_end:
                seg_days += 1
                next_date = date(cur_year + 1, 1, 1)
            else:
                next_date = segment_end

            ydays = 366 if calendar.isleap(cur_year) else 365
            year_days_summary.append((cur_year, seg_days, ydays))
            seg_interest = (tax * annual_rate * Decimal(str(seg_days))) / (Decimal('100.00') * Decimal(str(ydays)))
            total_interest += seg_interest

            cur_date = next_date
            cur_year += 1

        interest = quantize_amount(total_interest)
        notes = (
            f"Statutory interest calculated under {statutory_rule}: {days_delay} days delay "
            f"at {annual_rate}% p.a. on tax amount ₹{tax}."
        )
        if not is_verified_fact:
            notes += " (Statutory estimate pending formal assessment/reversal entry)."

        return {
            "tax_amount": tax,
            "start_date": start_date,
            "end_date": end_date,
            "days_delay": days_delay,
            "annual_rate": annual_rate,
            "interest_amount": interest,
            "statutory_provision": statutory_rule,
            "is_estimate": not is_verified_fact,
            "year_days": year_days_summary[0][2] if len(year_days_summary) == 1 else "multi-year",
            "statutory_notes": notes
        }

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
    def evaluate_rule37_status(
        cls,
        voucher: Voucher,
        check_date: Optional[date] = None,
        unpaid_amount: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Evaluates Rule 37 180-day statutory payment condition, remaining reversed/reclaimable balances,
        and applicable Section 50 interest.
        """
        today = check_date or timezone.now().date()
        v_date = voucher.voucher_date
        payment_deadline = v_date + timedelta(days=180)
        is_overdue = today > payment_deadline

        summary = cls.compute_voucher_monetary_summary(voucher)
        total_tax = summary["total_tax"]

        # Determine unpaid amount if not explicitly provided
        if unpaid_amount is not None:
            unpaid = quantize_amount(unpaid_amount)
        else:
            try:
                from apps.accounting.services.allocation_service import PaymentAllocationService
                _, paid_val = PaymentAllocationService.get_voucher_payment_status(voucher)
                unpaid = quantize_amount(max(Decimal('0.00'), voucher.total_amount - Decimal(str(paid_val))))
            except Exception:
                unpaid = voucher.total_amount

        # Cumulative active reversals & reclaims for this voucher
        existing_reversals = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_RULE_37',
            is_active=True
        )
        total_reversed_tax = quantize_amount(sum(r.total_tax for r in existing_reversals))

        existing_reclaims = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_RECLAIM',
            allocation_reason='RECLAIM_RULE_37',
            is_active=True
        )
        total_reclaimed_tax = quantize_amount(sum(r.total_tax for r in existing_reclaims))

        remaining_unreversed_tax = quantize_amount(max(Decimal('0.00'), total_tax - total_reversed_tax))
        remaining_reversed_tax = quantize_amount(max(Decimal('0.00'), total_reversed_tax - total_reclaimed_tax))

        proportionate_rev_tax = cls.calculate_rule37_reversal(voucher.total_amount, unpaid, total_tax)
        required_additional_reversal = quantize_amount(max(Decimal('0.00'), min(proportionate_rev_tax - total_reversed_tax, remaining_unreversed_tax)))

        reversal_required = bool(is_overdue and unpaid > Decimal('0.00') and required_additional_reversal > Decimal('0.00'))

        # Interest applies if overdue
        interest_calc = cls.calculate_section_50_interest(
            tax_amount=required_additional_reversal if reversal_required else total_reversed_tax,
            start_date=payment_deadline,
            end_date=today
        )

        return {
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "voucher_date": v_date,
            "payment_deadline": payment_deadline,
            "is_payment_overdue": is_overdue,
            "total_invoice_amount": voucher.total_amount,
            "unpaid_amount": unpaid,
            "total_tax": total_tax,
            "total_reversed_tax": total_reversed_tax,
            "total_reclaimed_tax": total_reclaimed_tax,
            "remaining_unreversed_tax": remaining_unreversed_tax,
            "remaining_reversed_tax": remaining_reversed_tax,
            "reversal_required": reversal_required,
            "required_reversal_tax": required_additional_reversal,
            "interest_applicable": is_overdue and (reversal_required or total_reversed_tax > Decimal('0.00')),
            "interest_details": interest_calc,
            "reclaimable_balance": remaining_reversed_tax,
        }

    @classmethod
    def create_rule37_reversal_allocation(
        cls,
        voucher: Voucher,
        unpaid_amount: Decimal,
        assigned_period: str,
        user: Any = None,
        reversal_date: Optional[date] = None
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reversal allocation under Rule 37 (180 days non-payment) for GSTR-3B Table 4(B)(2).
        Enforces:
        - Atomic concurrency locking via select_for_update
        - Unpaid amount > 0
        - Cumulative reversal cannot exceed invoice total tax
        - Idempotency for repeated requests
        - Section 50 interest warning and calculation for post-180-day reversals
        """
        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        unpaid = quantize_amount(unpaid_amount)
        if unpaid <= Decimal('0.00'):
            raise ValidationError(f"Rule 37 reversal rejected: Unpaid amount ₹{unpaid} must be greater than zero.")

        rev_date = reversal_date or timezone.now().date()
        payment_deadline = voucher.voucher_date + timedelta(days=180)
        is_overdue = rev_date > payment_deadline

        with transaction.atomic():
            # Concurrency row-lock on voucher
            locked_voucher = Voucher.objects.select_for_update().get(id=voucher.id)
            summary = cls.compute_voucher_monetary_summary(locked_voucher)

            # Check existing reversals
            existing_revs = GSTReportingAllocation.objects.filter(
                voucher=locked_voucher,
                event_type='ITC_REVERSAL_RULE_37',
                is_active=True
            )
            already_reversed = quantize_amount(sum(r.total_tax for r in existing_revs))
            max_reversable = summary["total_tax"] - already_reversed

            if max_reversable <= Decimal('0.00'):
                raise ValidationError(
                    f"Rule 37 reversal rejected: Invoice #{locked_voucher.voucher_number} is already fully reversed (₹{already_reversed})."
                )

            rev_tax = cls.calculate_rule37_reversal(locked_voucher.total_amount, unpaid, summary["total_tax"])
            if rev_tax > max_reversable:
                rev_tax = max_reversable

            # Check idempotency
            idem_key = f"rule37_rev_{locked_voucher.company.id}_{locked_voucher.id}_{clean_period}_{int(unpaid*100)}"
            existing = GSTReportingAllocation.objects.filter(idempotency_key=idem_key, is_active=True).first()
            if existing:
                return existing

            tot_tax = summary["total_tax"]
            ratio = (rev_tax / tot_tax) if tot_tax > Decimal('0.00') else Decimal('0.00')
            igst_rev = quantize_amount(summary["igst_amount"] * ratio)
            cgst_rev = quantize_amount(summary["cgst_amount"] * ratio)
            sgst_rev = quantize_amount(summary["sgst_amount"] * ratio)
            cess_rev = quantize_amount(summary["cess_amount"] * ratio)

            notes = (
                f"Rule 37 180-day ITC Reversal for invoice #{locked_voucher.voucher_number}: "
                f"unpaid amount ₹{unpaid} of ₹{locked_voucher.total_amount}."
            )
            if is_overdue:
                days_over = (rev_date - payment_deadline).days
                interest_info = cls.calculate_section_50_interest(rev_tax, payment_deadline, rev_date)
                notes += f" OVERDUE ({days_over} days past 180-day deadline {payment_deadline.strftime('%d-%m-%Y')}). Est. Interest: ₹{interest_info['interest_amount']} under Sec 50(1)."

            alloc = GSTReportingAllocation.objects.create(
                company=locked_voucher.company,
                voucher=locked_voucher,
                gst_registration=getattr(locked_voucher, 'gst_registration', None),
                event_type='ITC_REVERSAL_RULE_37',
                voucher_date=locked_voucher.voucher_date,
                entry_date=rev_date,
                original_period=locked_voucher.voucher_date.strftime('%m%Y'),
                assigned_period=clean_period,
                financial_year=cls.get_financial_year(locked_voucher.voucher_date),
                allocation_reason='REVERSAL_RULE_37',
                status='APPROVED',
                is_statutorily_eligible=True,
                statutory_rule='CGST Rules Rule 37 (180-day non-payment)',
                statutory_notes=notes,
                taxable_value=Decimal('0.00'),
                igst_amount=igst_rev,
                cgst_amount=cgst_rev,
                sgst_amount=sgst_rev,
                cess_amount=cess_rev,
                total_tax=rev_tax,
                is_active=True,
                idempotency_key=idem_key,
                created_by=user
            )
            return alloc

    @classmethod
    def create_rule37_reclaim_allocation(
        cls,
        voucher: Voucher,
        paid_amount: Decimal,
        assigned_period: str,
        user: Any = None,
        reclaim_date: Optional[date] = None,
        payment_event_id: str = "",
        payment_allocation: Any = None,
        payment_reference: str = "",
        source_reversal_id: Optional[Any] = None,
        allow_legacy_unidentified: bool = False
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reclaim allocation under Third Proviso to Section 16(2) and Rule 37(4).
        Entitled to reclaim without Section 16(4) time-limit bar.
        Enforces:
        - Atomic concurrency locking via select_for_update
        - Mandatory active prior Rule 37 reversal
        - Specific or FIFO reversal tracking via GSTReversalReclaimLineage
        - Permanently ineligible Section 17(5) blocked credit strictly rejected
        - Cumulative reclaim cannot exceed remaining reversed balance
        - Stable source-event idempotency via payment_event_id & canonical fingerprint
        - Cross-invoice and payload conflict detection on identical event IDs
        - Support for multiple genuine partial payments of identical amounts
        """
        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        paid = quantize_amount(paid_amount)
        if paid <= Decimal('0.00'):
            raise ValidationError(f"Rule 37 reclaim rejected: Paid amount ₹{paid} must be greater than zero.")

        # Block Section 17(5)
        if GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_SEC_17_5',
            is_active=True
        ).exists() or getattr(voucher, 'is_section_17_5_blocked', False):
            raise ValidationError("Permanently ineligible ITC under Section 17(5) cannot be reclaimed.")

        with transaction.atomic():
            locked_voucher = Voucher.objects.select_for_update().get(id=voucher.id)
            rec_date = reclaim_date or timezone.now().date()

            # 1. Stable source-event idempotency and conflict validation
            if payment_event_id:
                clean_event_id = str(payment_event_id).strip()
                current_fingerprint = compute_payment_event_fingerprint(
                    company_id=locked_voucher.company_id,
                    voucher_id=locked_voucher.id,
                    payment_event_id=clean_event_id,
                    paid_amount=paid,
                    payment_date=rec_date,
                    payment_allocation_id=getattr(payment_allocation, 'id', None) or (payment_allocation if isinstance(payment_allocation, (str, int)) else None),
                    payment_reference=payment_reference
                )

                # Tenant-scoped lookup for active reclaim with this payment_event_id
                existing = GSTReportingAllocation.objects.filter(
                    company=locked_voucher.company,
                    payment_event_id=clean_event_id,
                    is_active=True
                ).first()

                if existing:
                    # Conflict 1: Reusing event ID across different vouchers
                    if existing.voucher_id != locked_voucher.id:
                        raise ValidationError(
                            f"Payment-Event Idempotency Conflict: payment_event_id '{clean_event_id}' is already "
                            f"registered against voucher #{existing.voucher.voucher_number} ({existing.voucher_id}), "
                            f"cannot reuse for voucher #{locked_voucher.voucher_number} ({locked_voucher.id})."
                        )
                    # Conflict 2: Payload fingerprint mismatch (amount, date, allocation, reference)
                    if existing.payment_fingerprint and existing.payment_fingerprint != current_fingerprint:
                        raise ValidationError(
                            f"Payment-Event Idempotency Conflict: An allocation for payment_event_id '{clean_event_id}' "
                            f"already exists with fingerprint '{existing.payment_fingerprint}', but incoming payload produces "
                            f"different fingerprint '{current_fingerprint}'. Payload modification on identical event ID is prohibited."
                        )
                    # Conflict 3: Fallback check on existing allocation
                    if existing.payment_allocation != payment_allocation:
                        raise ValidationError(
                            f"Payment-Event Idempotency Conflict: payment_event_id '{clean_event_id}' is linked to a different payment allocation."
                        )
                    # Identical retry: return existing allocation (idempotent success)
                    return existing
            else:
                if not allow_legacy_unidentified:
                    raise ValidationError(
                        "Statutory Compliance Invariant: Rule 37 reclaim requires a stable source 'payment_event_id' "
                        "(e.g. payment allocation ID or bank transaction ID). Unidentified reclaims are prohibited in production."
                    )
                clean_event_id = ""
                current_fingerprint = ""
                idem_key = f"rule37_rec_legacy_{locked_voucher.company.id}_{locked_voucher.id}_{clean_period}_{int(paid*100)}"
                existing = GSTReportingAllocation.objects.filter(idempotency_key=idem_key, is_active=True).first()
                if existing:
                    return existing

            # 2. Mandatory prior Rule 37 reversal check
            if source_reversal_id:
                active_reversals = list(GSTReportingAllocation.objects.filter(
                    id=source_reversal_id,
                    voucher=locked_voucher,
                    event_type='ITC_REVERSAL_RULE_37',
                    is_active=True
                ))
                if not active_reversals:
                    raise ValidationError(
                        f"Cannot reclaim under Rule 37: Specified reversal '{source_reversal_id}' not found or inactive for invoice #{locked_voucher.voucher_number}."
                    )
            else:
                active_reversals = list(GSTReportingAllocation.objects.filter(
                    voucher=locked_voucher,
                    event_type='ITC_REVERSAL_RULE_37',
                    is_active=True
                ).order_by('entry_date', 'created_at'))

            if not active_reversals:
                raise ValidationError(
                    f"Cannot reclaim under Rule 37: No active prior Rule 37 reversal found for invoice #{locked_voucher.voucher_number}."
                )

            # 3. Calculate available reversal balance considering existing active lineages and reclaims
            reversal_balances = []
            total_available_from_lineages = Decimal('0.00')
            for rev in active_reversals:
                lineages = GSTReversalReclaimLineage.objects.filter(
                    reversal_allocation=rev,
                    reclaim_allocation__is_active=True
                )
                already_reclaimed_for_rev = quantize_amount(sum(l.reclaimed_tax for l in lineages))
                avail = quantize_amount(max(Decimal('0.00'), rev.total_tax - already_reclaimed_for_rev))
                reversal_balances.append({
                    'reversal': rev,
                    'available': avail,
                    'already_reclaimed': already_reclaimed_for_rev
                })
                total_available_from_lineages += avail

            # Also check total cumulative active reclaims on the voucher
            active_reclaims = GSTReportingAllocation.objects.filter(
                voucher=locked_voucher,
                event_type='ITC_RECLAIM',
                allocation_reason='RECLAIM_RULE_37',
                is_active=True
            )
            total_already_reclaimed = quantize_amount(sum(r.total_tax for r in active_reclaims))
            total_reversed_tax = quantize_amount(sum(r.total_tax for r in active_reversals))
            remaining_cumulative_tax = quantize_amount(max(Decimal('0.00'), total_reversed_tax - total_already_reclaimed))

            effective_available = min(total_available_from_lineages, remaining_cumulative_tax)

            if effective_available <= Decimal('0.00'):
                raise ValidationError(
                    f"Rule 37 reclaim rejected: Total reversed ITC (₹{total_reversed_tax}) has already been fully reclaimed for invoice #{locked_voucher.voucher_number}."
                )

            summary = cls.compute_voucher_monetary_summary(locked_voucher)
            reclaim_tax = cls.calculate_rule37_reversal(locked_voucher.total_amount, paid, summary["total_tax"])

            if reclaim_tax > effective_available:
                raise ValidationError(
                    f"Rule 37 reclaim rejected: Requested reclaim tax ₹{reclaim_tax} exceeds remaining reversed balance ₹{effective_available} for invoice #{locked_voucher.voucher_number}."
                )

            # Proportional breakdown
            tot_tax = summary["total_tax"]
            ratio = (reclaim_tax / tot_tax) if tot_tax > Decimal('0.00') else Decimal('0.00')
            igst_rec = quantize_amount(summary["igst_amount"] * ratio)
            cgst_rec = quantize_amount(summary["cgst_amount"] * ratio)
            sgst_rec = quantize_amount(summary["sgst_amount"] * ratio)
            cess_rec = quantize_amount(summary["cess_amount"] * ratio)
            diff = reclaim_tax - (igst_rec + cgst_rec + sgst_rec + cess_rec)
            if diff != Decimal('0.00'):
                if cgst_rec > Decimal('0.00'):
                    half = quantize_amount(diff / Decimal('2.00'))
                    cgst_rec += half
                    sgst_rec += (diff - half)
                else:
                    igst_rec += diff

            if payment_event_id:
                idem_key = f"rule37_rec_{locked_voucher.company.id}_{clean_event_id}"
            else:
                idem_key = f"rule37_rec_legacy_{locked_voucher.company.id}_{locked_voucher.id}_{clean_period}_{int(paid*100)}"

            primary_rev = active_reversals[0]

            alloc = GSTReportingAllocation.objects.create(
                company=locked_voucher.company,
                voucher=locked_voucher,
                gst_registration=getattr(locked_voucher, 'gst_registration', None),
                event_type='ITC_RECLAIM',
                voucher_date=locked_voucher.voucher_date,
                entry_date=rec_date,
                original_period=locked_voucher.voucher_date.strftime('%m%Y'),
                assigned_period=clean_period,
                financial_year=cls.get_financial_year(locked_voucher.voucher_date),
                allocation_reason='RECLAIM_RULE_37',
                status='APPROVED',
                is_statutorily_eligible=True,
                statutory_rule='Third Proviso to Section 16(2) / Rule 37(4)',
                statutory_notes=(
                    f"Rule 37(4) ITC Reclaim upon payment of ₹{paid} for invoice #{locked_voucher.voucher_number}. "
                    f"Reclaim tax ₹{reclaim_tax} of ₹{total_reversed_tax} reversed. "
                    f"Remaining reversed balance: ₹{effective_available - reclaim_tax}. Exempt from Sec 16(4) time-limit."
                ),
                taxable_value=quantize_amount((paid / locked_voucher.total_amount) * summary["taxable_value"]) if locked_voucher.total_amount > 0 else Decimal('0.00'),
                igst_amount=igst_rec,
                cgst_amount=cgst_rec,
                sgst_amount=sgst_rec,
                cess_amount=cess_rec,
                total_tax=reclaim_tax,
                is_active=True,
                source_reversal=primary_rev,
                payment_allocation=payment_allocation,
                payment_event_id=clean_event_id if payment_event_id else '',
                payment_reference=payment_reference or '',
                payment_fingerprint=current_fingerprint,
                idempotency_key=idem_key,
                created_by=user
            )

            # 4. Create Lineage records linking to specific reversal(s)
            rem_to_allocate = reclaim_tax
            for rb in reversal_balances:
                rev = rb['reversal']
                avail = rb['available']
                if avail <= Decimal('0.00'):
                    continue
                chunk = min(rem_to_allocate, avail)
                chunk_ratio = (chunk / rev.total_tax) if rev.total_tax > Decimal('0.00') else Decimal('0.00')
                chunk_igst = quantize_amount(rev.igst_amount * chunk_ratio)
                chunk_cgst = quantize_amount(rev.cgst_amount * chunk_ratio)
                chunk_sgst = quantize_amount(rev.sgst_amount * chunk_ratio)
                chunk_cess = quantize_amount(rev.cess_amount * chunk_ratio)
                chunk_diff = chunk - (chunk_igst + chunk_cgst + chunk_sgst + chunk_cess)
                if chunk_diff != Decimal('0.00'):
                    if chunk_cgst > Decimal('0.00'):
                        half = quantize_amount(chunk_diff / Decimal('2.00'))
                        chunk_cgst += half
                        chunk_sgst += (chunk_diff - half)
                    else:
                        chunk_igst += chunk_diff

                GSTReversalReclaimLineage.objects.create(
                    company=locked_voucher.company,
                    voucher=locked_voucher,
                    reversal_allocation=rev,
                    reclaim_allocation=alloc,
                    reclaimed_tax=chunk,
                    igst_reclaimed=chunk_igst,
                    cgst_reclaimed=chunk_cgst,
                    sgst_reclaimed=chunk_sgst,
                    cess_reclaimed=chunk_cess,
                    statutory_rule='RULE_37',
                    created_by=user
                )
                rem_to_allocate -= chunk
                if rem_to_allocate <= Decimal('0.00'):
                    break

            return alloc

    @classmethod
    def supersede_payment_reclaim_allocation(
        cls,
        allocation: GSTReportingAllocation,
        reason: str,
        user: Any = None
    ) -> GSTReportingAllocation:
        """
        Statutory Correction & Reversal Pathway:
        Safely supersedes an existing reclaim allocation without mutating historical records.
        Preserves GSTReversalReclaimLineage audit trail and frees reversal balance for subsequent corrected payments.
        Enforces immutability of historical accounting facts under Section 155.
        """
        with transaction.atomic():
            locked_alloc = GSTReportingAllocation.objects.select_for_update().get(id=allocation.id)
            if not locked_alloc.is_active:
                return locked_alloc
            locked_alloc.is_active = False
            locked_alloc.status = 'SUPERSEDED'
            locked_alloc.superseded_at = timezone.now()
            clean_reason = str(reason).strip()
            locked_alloc.statutory_notes += f" [SUPERSEDED on {timezone.now().date().isoformat()}: {clean_reason}]"
            locked_alloc.save(update_fields=['is_active', 'status', 'superseded_at', 'statutory_notes', 'updated_at'])
            return locked_alloc

    @classmethod
    def get_rule37a_supplier_default_date(cls, financial_year: str) -> date:
        """
        Computes the statutory Rule 37A supplier default date:
        30th September following the end of the financial year in which ITC was availed.
        E.g. FY 2025-26 -> 30-Sep-2026.
        """
        start_year = int(financial_year.split('-')[0])
        end_year = start_year + 1
        return date(end_year, 9, 30)

    @classmethod
    def get_rule37a_recipient_reversal_deadline(cls, financial_year: str) -> date:
        """
        Computes the statutory Rule 37A recipient reversal deadline:
        30th November following the end of the financial year in which ITC was availed.
        Reversals on or before this date carry no interest under Section 50.
        Reversals after this date attract interest under Section 50.
        """
        start_year = int(financial_year.split('-')[0])
        end_year = start_year + 1
        return date(end_year, 11, 30)

    @classmethod
    def get_rule37a_available_reversal_balance(cls, voucher: Voucher) -> Decimal:
        """
        Calculates the remaining reversed ITC balance available for reclaim under Rule 37A.
        Derived from active ITC_REVERSAL_RULE_37A allocations minus cumulative active reclaims.
        """
        active_reversals = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_RULE_37A',
            is_active=True
        )
        if not active_reversals.exists():
            return Decimal('0.00')

        total_reversed = quantize_amount(sum(r.total_tax for r in active_reversals))
        active_lineages = GSTReversalReclaimLineage.objects.filter(
            reversal_allocation__in=active_reversals,
            reclaim_allocation__is_active=True
        )
        already_reclaimed = quantize_amount(sum(l.reclaimed_tax for l in active_lineages))
        if already_reclaimed == Decimal('0.00'):
            direct_reclaims = GSTReportingAllocation.objects.filter(
                voucher=voucher,
                event_type='ITC_RECLAIM',
                allocation_reason='RECLAIM_RULE_37A',
                is_active=True
            )
            already_reclaimed = quantize_amount(sum(rec.total_tax for rec in direct_reclaims))

        return quantize_amount(max(Decimal('0.00'), total_reversed - already_reclaimed))

    @classmethod
    def evaluate_rule37a_status(
        cls,
        voucher: Voucher,
        check_date: Optional[date] = None,
        supplier_gstr3b_filed: Optional[bool] = None,
        supplier_filing_date: Optional[date] = None,
        supplier_status: str = 'UNKNOWN',
        supplier_return_period: str = '',
        supplier_gstin: str = '',
        is_stale_evidence: bool = False,
        evidence_source: Optional[str] = None,
        verification_timestamp: Optional[Union[datetime, date, str]] = None,
        evidence_record: Optional[Any] = None,
        evidence_document_ref: Optional[str] = None,
        manual_verification_reason: Optional[str] = None,
        user: Optional[Any] = None,
        freshness_threshold_days: int = 30
    ) -> Dict[str, Any]:
        """
        Evaluates Rule 37A statutory timeline and compliance state:
        - Supplier default date: 30 September post FY end
        - Recipient reversal deadline: 30 November post FY end
        - Distinguishes: VERIFIED_FILED, VERIFIED_NOT_FILED, DATA_UNAVAILABLE, MANUALLY_CONFIRMED, PENDING, UNKNOWN
        - Invariant: UNKNOWN, DATA_UNAVAILABLE, PENDING, null, and missing evidence NEVER establish default!
        - Raw boolean (e.g. False or True) without independently validated evidence NEVER establishes filing state!
        - Fail-Closed: Missing, malformed, future, or stale verification timestamp strictly converts to DATA_UNAVAILABLE.
        """
        v_date = voucher.voucher_date
        fy = cls.get_financial_year(v_date)
        default_date = cls.get_rule37a_supplier_default_date(fy)
        reversal_deadline = cls.get_rule37a_recipient_reversal_deadline(fy)
        today = check_date or timezone.now().date()

        # Resolve supplier filing state (Fail-Closed: UNKNOWN never converts to default)
        clean_status = (supplier_status or 'UNKNOWN').upper()

        is_supplier_default = False
        default_reason = ''

        inv_gstin = Rule37AEvidenceService.resolve_supplier_gstin(voucher)
        clean_supp_gstin = (supplier_gstin or '').strip().upper()
        clean_inv_gstin = (inv_gstin or '').strip().upper()
        inv_period = v_date.strftime('%m%Y')
        clean_period = (supplier_return_period or '').strip().replace('-', '').replace('/', '')

        if clean_supp_gstin and clean_inv_gstin and clean_supp_gstin != clean_inv_gstin:
            clean_status = 'DATA_UNAVAILABLE'
            is_supplier_default = False
            default_reason = f"Supplier GSTIN '{supplier_gstin}' does not match invoice supplier GSTIN '{inv_gstin}'. Default cannot be evaluated."
        elif clean_status == 'DATA_UNAVAILABLE':
            # Statutory Guard: Unavailable data is NOT proof of default!
            is_supplier_default = False
            default_reason = 'DATA_UNAVAILABLE: Supplier filing status cannot be verified from GST portal/GSP. Default cannot be presumed.'
        elif clean_status == 'PENDING':
            is_supplier_default = False
            default_reason = 'PENDING: Supplier GSTR-3B verification is pending from GST portal. Default cannot be presumed.'
        elif clean_status == 'VERIFIED_FILED':
            if supplier_filing_date and supplier_filing_date > default_date:
                # Supplier filed, but late (after 30-Sep)
                is_supplier_default = (today >= default_date and today < supplier_filing_date)
                default_reason = f"Supplier filed late on {supplier_filing_date.strftime('%d-%m-%Y')} (after default date {default_date.strftime('%d-%m-%Y')})."
            else:
                is_supplier_default = False
                default_reason = 'Supplier verified filed on or before statutory default date.'
        elif clean_status == 'MANUALLY_CONFIRMED':
            is_supplier_default = False
            default_reason = 'Supplier filing manually confirmed by accountant with documentary evidence.'
        elif clean_status == 'VERIFIED_NOT_FILED':
            # 1. GSTIN Validation
            if not clean_supp_gstin or not clean_inv_gstin or clean_supp_gstin != clean_inv_gstin:
                clean_status = 'DATA_UNAVAILABLE'
                is_supplier_default = False
                default_reason = f"Supplier GSTIN '{supplier_gstin}' does not match invoice supplier GSTIN '{inv_gstin}'. Default cannot be evaluated."

            # 2. Return Period Validation
            elif not clean_period or clean_period != inv_period:
                clean_status = 'DATA_UNAVAILABLE'
                is_supplier_default = False
                default_reason = f"Supplier filing evidence period '{supplier_return_period}' does not match invoice return period '{inv_period}'. Non-filing cannot be assumed."

            # 3. Explicit Stale Evidence Flag
            elif is_stale_evidence:
                clean_status = 'DATA_UNAVAILABLE'
                is_supplier_default = False
                default_reason = 'Supplier filing evidence is stale (>30 days old). Re-verification required from GSTN.'

            # 4. Mandatory Verification Timestamp Validation (Fail-Closed)
            elif not verification_timestamp or (isinstance(verification_timestamp, str) and not verification_timestamp.strip()):
                clean_status = 'DATA_UNAVAILABLE'
                is_supplier_default = False
                default_reason = 'Missing verification timestamp on supplier filing evidence. Provenance cannot be established.'

            else:
                # Parse timestamp and validate freshness / validity
                vt_parsed = None
                if isinstance(verification_timestamp, datetime):
                    vt_parsed = verification_timestamp
                elif isinstance(verification_timestamp, date):
                    vt_parsed = datetime.combine(verification_timestamp, datetime.min.time(), tzinfo=timezone.get_current_timezone())
                elif isinstance(verification_timestamp, str):
                    try:
                        vt_parsed = datetime.fromisoformat(verification_timestamp.strip())
                    except (ValueError, TypeError):
                        vt_parsed = None

                if vt_parsed is None:
                    clean_status = 'DATA_UNAVAILABLE'
                    is_supplier_default = False
                    default_reason = 'Malformed or invalid verification timestamp on supplier filing evidence.'
                else:
                    if timezone.is_naive(vt_parsed):
                        vt_parsed = timezone.make_aware(vt_parsed, timezone.get_current_timezone())

                    now = timezone.now()
                    ref_date = check_date if (check_date and check_date >= vt_parsed.date()) else now.date()

                    # Future timestamp check (future relative to wall-clock or future relative to post-wall-clock check_date)
                    is_future = False
                    if vt_parsed > now + timedelta(minutes=5):
                        is_future = True
                    elif check_date and vt_parsed.date() > check_date and check_date >= now.date():
                        is_future = True

                    if is_future:
                        clean_status = 'DATA_UNAVAILABLE'
                        is_supplier_default = False
                        default_reason = 'Supplier filing verification timestamp is in the future. Invalid evidence.'
                    else:
                        age_days = (ref_date - vt_parsed.date()).days
                        if age_days > freshness_threshold_days or age_days < 0:
                            clean_status = 'DATA_UNAVAILABLE'
                            is_supplier_default = False
                            default_reason = f"Supplier filing verification timestamp is stale ({age_days} days old). Re-verification required from GSTN."
                        else:
                            # 5. Evidence Source & Record Provenance Validation
                            clean_source = (evidence_source or '').strip().upper()
                            if not clean_source or not evidence_record:
                                resolved = Rule37AEvidenceService.resolve_voucher_evidence(voucher, freshness_threshold_days=freshness_threshold_days)
                                if not clean_source and resolved.get("evidence_source"):
                                    clean_source = resolved["evidence_source"].strip().upper()
                                    evidence_source = resolved["evidence_source"]
                                if not evidence_record and resolved.get("evidence_record"):
                                    evidence_record = resolved["evidence_record"]

                            valid_sources = {'PORTAL', 'GSTN_PORTAL', 'GSTR2B', 'SUPPLIER_RECORD', 'MANUAL'}
                            if not clean_source or clean_source in ('NONE', 'CONFLICTING_SOURCES', 'AMBIGUOUS_SOURCES') or clean_source not in valid_sources:
                                clean_status = 'DATA_UNAVAILABLE'
                                is_supplier_default = False
                                default_reason = f"Missing or invalid evidence source '{evidence_source}'. Provenance cannot be verified."
                            elif clean_source == 'MANUAL':
                                # Manual verification pathway
                                has_manual = bool(
                                    str(evidence_document_ref or '').strip() and
                                    str(manual_verification_reason or '').strip() and
                                    (user or getattr(voucher, 'user', None))
                                )
                                if not has_manual:
                                    clean_status = 'DATA_UNAVAILABLE'
                                    is_supplier_default = False
                                    default_reason = 'Manual verification pathway requires documentary reference, documented reason, and authorizing user.'
                                elif today >= default_date:
                                    is_supplier_default = True
                                    default_reason = f"Supplier confirmed NOT FILED as of {today.strftime('%d-%m-%Y')} (past 30-Sep default date {default_date.strftime('%d-%m-%Y')})."
                                else:
                                    is_supplier_default = False
                                    default_reason = f"Statutory default date ({default_date.strftime('%d-%m-%Y')}) not yet reached."
                            else:
                                # Supporting evidence record validation
                                has_record = False
                                if evidence_record:
                                    if isinstance(evidence_record, SupplierGSTR3BFilingRecord):
                                        if (str(evidence_record.company_id) == str(voucher.company_id) and
                                            evidence_record.supplier_gstin.strip().upper() == clean_supp_gstin and
                                            evidence_record.return_period.strip() == clean_period and
                                            evidence_record.status == 'VERIFIED_NOT_FILED' and
                                            not evidence_record.is_stale(threshold_days=freshness_threshold_days)):
                                            has_record = True
                                    elif isinstance(evidence_record, GSTR2BRecord):
                                        if (str(evidence_record.company_id) == str(voucher.company_id) and
                                            evidence_record.supplier_gstin.strip().upper() == clean_supp_gstin and
                                            evidence_record.gstr3b_return_period.strip() == clean_period and
                                            evidence_record.gstr3b_status == 'NOT_FILED' and
                                            not evidence_record.is_gstr3b_stale(threshold_days=freshness_threshold_days)):
                                            has_record = True

                                if not has_record:
                                    clean_status = 'DATA_UNAVAILABLE'
                                    is_supplier_default = False
                                    default_reason = 'Supporting SupplierGSTR3BFilingRecord or GSTR2BRecord evidence is missing or unverified.'
                                elif today >= default_date:
                                    is_supplier_default = True
                                    default_reason = f"Supplier confirmed NOT FILED as of {today.strftime('%d-%m-%Y')} (past 30-Sep default date {default_date.strftime('%d-%m-%Y')})."
                                else:
                                    is_supplier_default = False
                                    default_reason = f"Statutory default date ({default_date.strftime('%d-%m-%Y')}) not yet reached."
        else: # UNKNOWN
            is_supplier_default = False
            default_reason = 'Supplier status UNKNOWN. Verification required.'

        existing_reversal = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_RULE_37A',
            is_active=True
        ).first()

        existing_reclaim = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_RECLAIM',
            allocation_reason='RECLAIM_RULE_37A',
            is_active=True
        ).first()

        reversal_required = bool(is_supplier_default and not existing_reversal)
        is_overdue = bool(today > reversal_deadline and is_supplier_default)
        interest_applicable = bool(is_overdue and (not existing_reversal or existing_reversal.entry_date > reversal_deadline))

        interest_details = None
        if interest_applicable:
            summary = cls.compute_voucher_monetary_summary(voucher)
            interest_details = cls.calculate_section_50_interest(
                tax_amount=summary["total_tax"],
                start_date=reversal_deadline,
                end_date=today
            )

        # Reclaim eligibility under Proviso to Rule 37A:
        # P0 Safeguard: An ITC reclaim must NEVER become eligible merely because a caller supplies
        # a positive filing status or boolean. Reclaim authorization MUST be derived from
        # independently validated, supplier-specific, company-specific, invoice-period-specific filing evidence.
        is_17_5_blocked = getattr(voucher, 'is_section_17_5_blocked', False) or GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_SEC_17_5',
            is_active=True
        ).exists()

        available_reversal_balance = Decimal('0.00')
        if existing_reversal:
            active_lineages = GSTReversalReclaimLineage.objects.filter(
                reversal_allocation=existing_reversal,
                reclaim_allocation__is_active=True
            )
            already_reclaimed = quantize_amount(sum(l.reclaimed_tax for l in active_lineages))
            available_reversal_balance = quantize_amount(max(Decimal('0.00'), existing_reversal.total_tax - already_reclaimed))

        reclaim_eligible = False
        reclaim_ineligible_reason = ""

        if not existing_reversal:
            reclaim_ineligible_reason = "No prior active Rule 37A reversal exists."
        elif is_17_5_blocked:
            reclaim_ineligible_reason = "ITC is permanently ineligible under Section 17(5)."
        elif available_reversal_balance <= Decimal('0.00'):
            reclaim_ineligible_reason = "Prior Rule 37A reversal has already been fully reclaimed."
        elif existing_reclaim:
            reclaim_ineligible_reason = "An active Rule 37A reclaim allocation already exists on this voucher."
        elif clean_status not in ('VERIFIED_FILED', 'MANUALLY_CONFIRMED'):
            reclaim_ineligible_reason = f"Supplier status '{clean_status}' does not establish positive filing."
        else:
            # Independently validate positive filing evidence
            pos_eval = Rule37AEvidenceService.validate_positive_filing_evidence(
                voucher=voucher,
                supplier_status=clean_status,
                supplier_gstin=clean_supp_gstin or Rule37AEvidenceService.resolve_supplier_gstin(voucher),
                supplier_return_period=clean_period or Rule37AEvidenceService.resolve_invoice_return_period(voucher),
                verification_source=evidence_source,
                verification_reference=evidence_document_ref,
                verification_timestamp=verification_timestamp,
                gstr3b_filing_date=supplier_filing_date,
                gstr3b_arn=evidence_document_ref,
                user=user,
                manual_verification_reason=manual_verification_reason,
                evidence_record=evidence_record,
                freshness_threshold_days=freshness_threshold_days,
                raise_exception=False
            )
            if pos_eval.is_valid:
                reclaim_eligible = True
            else:
                reclaim_eligible = False
                reclaim_ineligible_reason = pos_eval.validation_reason

        return {
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "financial_year": fy,
            "supplier_status": clean_status,
            "supplier_default_date": default_date,
            "recipient_reversal_deadline": reversal_deadline,
            "is_supplier_default": is_supplier_default,
            "default_reason": default_reason,
            "reversal_required": reversal_required,
            "is_reversal_overdue": is_overdue,
            "interest_applicable": interest_applicable,
            "interest_details": interest_details,
            "reclaim_eligible": reclaim_eligible,
            "reclaimable_balance": available_reversal_balance,
            "reclaim_ineligible_reason": reclaim_ineligible_reason,
            "has_existing_reversal": bool(existing_reversal),
            "has_existing_reclaim": bool(existing_reclaim),
        }

    @classmethod
    def create_rule37a_reversal_allocation(
        cls,
        voucher: Voucher,
        assigned_period: str,
        user: Any = None,
        reversal_date: Optional[date] = None,
        supplier_status: Optional[str] = None,
        supplier_gstin: Optional[str] = None,
        supplier_return_period: Optional[str] = None,
        evidence_source: Optional[str] = None,
        verification_timestamp: Optional[datetime] = None,
        evidence_record: Optional[Any] = None,
        evidence_document_ref: Optional[str] = None,
        manual_verification_reason: Optional[str] = None,
        is_stale_evidence: Optional[bool] = None,
        supplier_gstr3b_filed: Optional[bool] = None,
        supplier_filing_date: Optional[date] = None,
        freshness_threshold_days: int = 30
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reversal allocation under Rule 37A (Supplier default in GSTR-3B) for Table 4(B)(2).
        Must be reversed on or before 30th November following end of FY in which ITC was availed.
        Enforces all 12 statutory negative cases and preserves cryptographic evidence provenance.
        """
        # Validate evidence using unified Rule37AEvidenceService
        validated = Rule37AEvidenceService.validate_reversal_evidence(
            voucher=voucher,
            supplier_status=supplier_status,
            supplier_gstin=supplier_gstin,
            supplier_return_period=supplier_return_period,
            evidence_source=evidence_source,
            verification_timestamp=verification_timestamp,
            evidence_record=evidence_record,
            evidence_document_ref=evidence_document_ref,
            manual_verification_reason=manual_verification_reason,
            is_stale_evidence=is_stale_evidence,
            user=user,
            freshness_threshold_days=freshness_threshold_days
        )

        fy = cls.get_financial_year(voucher.voucher_date)
        default_date = cls.get_rule37a_supplier_default_date(fy)
        rev_date = reversal_date or timezone.now().date()
        if rev_date < default_date:
            raise ValidationError(
                f"Cannot execute Rule 37A reversal: Statutory default date ({default_date.strftime('%d-%m-%Y')}) has not been reached for FY {fy}."
            )

        with transaction.atomic():
            locked_voucher = Voucher.objects.select_for_update().get(id=voucher.id)

            # Duplicate reversal prevention
            if GSTReportingAllocation.objects.filter(
                voucher=locked_voucher,
                event_type='ITC_REVERSAL_RULE_37A',
                is_active=True
            ).exists():
                raise ValidationError(f"Rule 37A reversal already exists for invoice #{locked_voucher.voucher_number}.")

            summary = cls.compute_voucher_monetary_summary(locked_voucher)
            clean_period = assigned_period.strip().replace('-', '').replace('/', '')
            deadline = cls.get_rule37a_recipient_reversal_deadline(fy)
            is_overdue = rev_date > deadline

            notes = (
                f"Rule 37A ITC Reversal for invoice #{locked_voucher.voucher_number}: supplier defaulted on GSTR-3B filing. "
                f"Supplier GSTIN: {validated['supplier_gstin']} Period: {validated['supplier_return_period']} "
                f"Source: {validated['evidence_source']} Reversed on {rev_date.strftime('%d-%m-%Y')}."
            )
            if is_overdue:
                days_over = (rev_date - deadline).days
                interest_info = cls.calculate_section_50_interest(summary["total_tax"], deadline, rev_date)
                notes += f" OVERDUE ({days_over} days past deadline {deadline.strftime('%d-%m-%Y')}). Interest payable under Section 50. Est. Interest: ₹{interest_info['interest_amount']} under Section 50(1)."

            idem_key = f"rule37a_rev_{locked_voucher.company.id}_{locked_voucher.id}_{clean_period}"
            alloc = GSTReportingAllocation.objects.create(
                company=locked_voucher.company,
                voucher=locked_voucher,
                gst_registration=getattr(locked_voucher, 'gst_registration', None),
                event_type='ITC_REVERSAL_RULE_37A',
                voucher_date=locked_voucher.voucher_date,
                entry_date=rev_date,
                original_period=locked_voucher.voucher_date.strftime('%m%Y'),
                assigned_period=clean_period,
                financial_year=fy,
                allocation_reason='REVERSAL_RULE_37A',
                status='APPROVED',
                is_statutorily_eligible=True,
                statutory_rule='CGST Rules Rule 37A (Supplier non-payment of tax / GSTR-3B default)',
                statutory_notes=notes,
                taxable_value=Decimal('0.00'),
                igst_amount=summary["igst_amount"],
                cgst_amount=summary["cgst_amount"],
                sgst_amount=summary["sgst_amount"],
                cess_amount=summary["cess_amount"],
                total_tax=summary["total_tax"],
                is_active=True,
                idempotency_key=idem_key,
                evidence_source=validated["evidence_source"],
                evidence_status=validated["supplier_status"],
                evidence_supplier_gstin=validated["supplier_gstin"],
                evidence_return_period=validated["supplier_return_period"],
                evidence_verified_at=validated["verification_timestamp"],
                evidence_document_ref=validated["evidence_document_ref"],
                evidence_hash=validated["evidence_hash"],
                evidence_metadata={
                    "evidence_source": validated["evidence_source"],
                    "manual_verification_reason": validated["manual_verification_reason"],
                    "verified_by": str(user) if user else ""
                },
                created_by=user
            )
            return alloc

    @classmethod
    def get_active_rule37a_reversal_balance(cls, voucher: Voucher) -> Decimal:
        """
        Returns the active remaining un-reclaimed Rule 37A reversal balance for a voucher.
        """
        prior_rev = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_RULE_37A',
            is_active=True
        ).first()
        if not prior_rev:
            return Decimal('0.00')

        active_lineages = GSTReversalReclaimLineage.objects.filter(
            reversal_allocation=prior_rev,
            reclaim_allocation__is_active=True
        )
        already_reclaimed = quantize_amount(sum(l.reclaimed_tax for l in active_lineages))
        return quantize_amount(max(Decimal('0.00'), prior_rev.total_tax - already_reclaimed))

    @classmethod
    def create_rule37a_reclaim_allocation(
        cls,
        voucher: Voucher,
        assigned_period: str,
        user: Any = None,
        supplier_status: Optional[str] = None,
        supplier_gstin: Optional[str] = None,
        supplier_return_period: Optional[str] = None,
        gstr3b_return_period: Optional[str] = None,
        verification_source: Optional[str] = None,
        verification_reference: Optional[str] = None,
        verification_date: Optional[Union[date, datetime]] = None,
        verification_timestamp: Optional[Union[date, datetime]] = None,
        reclaim_date: Optional[date] = None,
        gstr3b_filing_date: Optional[date] = None,
        gstr3b_arn: Optional[str] = None,
        source_reversal_id: Optional[Any] = None,
        manual_verification_reason: Optional[str] = None,
        evidence_record: Optional[Any] = None,
        freshness_threshold_days: int = 30,
        supplier_gstr3b_filed: Optional[bool] = None,
        require_prior_reversal: bool = True,
        reclaim_tax: Optional[Decimal] = None,
        idempotent: bool = False,
    ) -> GSTReportingAllocation:
        """
        Creates an ITC reclaim allocation under Proviso to Rule 37A when supplier subsequently files GSTR-3B.
        Reclaim is permitted without any Section 16(4) time-limit bar.
        Enforces:
        - Mandatory prior active Rule 37A reversal (CANNOT be bypassed)
        - Verification that supplier has furnished GSTR-3B (VERIFIED_FILED or MANUALLY_CONFIRMED)
        - Reject DATA_UNAVAILABLE, PENDING, UNKNOWN, or VERIFIED_NOT_FILED
        - GSTR-1 outward date must NEVER be accepted as proof of GSTR-3B payment
        - Prevent duplicate active reclaim across periods
        - Prevent excessive reclaim: amount cannot exceed active available reversal balance
        - Block Section 17(5) permanently ineligible credit
        - Lineage linkage via GSTReversalReclaimLineage
        - Atomic transaction & row-level locking concurrency protection
        """
        clean_period = assigned_period.strip().replace('-', '').replace('/', '')
        norm_assigned = Rule37AEvidenceService.normalize_and_validate_return_period(clean_period)
        if not norm_assigned:
            raise ValidationError(f"Invalid assigned return period '{assigned_period}'. Must be MMYYYY format.")

        with transaction.atomic():
            # 1. Lock the voucher using select_for_update()
            locked_voucher = Voucher.objects.select_for_update().get(id=voucher.id)

            # Block Section 17(5) permanently ineligible credit upfront
            if getattr(voucher, 'is_section_17_5_blocked', False) or getattr(locked_voucher, 'is_section_17_5_blocked', False) or GSTReportingAllocation.objects.filter(
                voucher=locked_voucher,
                event_type='ITC_REVERSAL_SEC_17_5',
                is_active=True
            ).exists():
                raise ValidationError("Permanently ineligible ITC under Section 17(5) cannot be reclaimed.")

            # 2. Lock the selected active Rule 37A reversal allocation (CANNOT BE BYPASSED)
            if source_reversal_id:
                rev_candidate = GSTReportingAllocation.objects.select_for_update().filter(
                    id=source_reversal_id,
                    company=locked_voucher.company,
                    event_type='ITC_REVERSAL_RULE_37A',
                    is_active=True
                ).first()
                if not rev_candidate or str(rev_candidate.voucher_id) != str(locked_voucher.id):
                    raise ValidationError(
                        f"Rule 37A reversal {source_reversal_id} is not linked to invoice #{locked_voucher.voucher_number}."
                    )
                prior_rev = rev_candidate
            else:
                prior_rev = GSTReportingAllocation.objects.select_for_update().filter(
                    voucher=locked_voucher,
                    company=locked_voucher.company,
                    event_type='ITC_REVERSAL_RULE_37A',
                    is_active=True
                ).first()

            if not prior_rev:
                raise ValidationError(
                    f"Cannot reclaim under Rule 37A: No active prior Rule 37A reversal found for invoice #{locked_voucher.voucher_number}."
                )

            # Tenant isolation validation on reversal
            if str(prior_rev.company_id) != str(locked_voucher.company_id) or str(prior_rev.voucher_id) != str(locked_voucher.id):
                raise ValidationError("Reversal allocation does not belong to the locked voucher company or voucher.")

            # 3. Resolve and Lock Authoritative Evidence Record Inside Transaction
            from apps.gst.models import Rule37AManualFilingEvidence
            inv_period = locked_voucher.voucher_date.strftime('%m%Y')
            p_gstin = Rule37AEvidenceService.resolve_supplier_gstin(locked_voucher)
            eff_gstin = (supplier_gstin or p_gstin or "").strip().upper()
            eff_period = supplier_return_period or gstr3b_return_period or inv_period
            clean_status = (supplier_status or "").strip().upper()
            if not clean_status and supplier_gstr3b_filed is True:
                clean_status = 'VERIFIED_FILED'

            arn_str = str(gstr3b_arn or verification_reference or "").strip()
            g3b_date = gstr3b_filing_date
            eff_verif_date = verification_timestamp or verification_date
            locked_evidence = None

            if clean_status == 'MANUALLY_CONFIRMED':
                if evidence_record and isinstance(evidence_record, Rule37AManualFilingEvidence):
                    locked_evidence = Rule37AManualFilingEvidence.objects.select_for_update().filter(id=evidence_record.id).first()
                else:
                    locked_evidence = Rule37AManualFilingEvidence.objects.select_for_update().filter(
                        company=locked_voucher.company,
                        voucher=locked_voucher,
                        supplier_gstin=eff_gstin,
                        return_period=eff_period
                    ).order_by('-verification_timestamp').first()
            elif clean_status == 'VERIFIED_FILED':
                if evidence_record:
                    if isinstance(evidence_record, SupplierGSTR3BFilingRecord):
                        locked_evidence = SupplierGSTR3BFilingRecord.objects.select_for_update().filter(id=evidence_record.id).first()
                    elif isinstance(evidence_record, GSTR2BRecord):
                        locked_evidence = GSTR2BRecord.objects.select_for_update().filter(id=evidence_record.id).first()
                else:
                    supp_rec = SupplierGSTR3BFilingRecord.objects.select_for_update().filter(
                        company=locked_voucher.company,
                        supplier_gstin=eff_gstin,
                        return_period=eff_period
                    ).first() if eff_gstin else None
                    g2b_rec = GSTR2BRecord.objects.select_for_update().filter(
                        company=locked_voucher.company,
                        matched_voucher=locked_voucher
                    ).first()

                    if supp_rec and supp_rec.status == 'VERIFIED_FILED':
                        g3b_date = g3b_date or supp_rec.filing_date
                        arn_str = arn_str or supp_rec.arn
                        locked_evidence = supp_rec
                    elif g2b_rec and g2b_rec.gstr3b_filing_date and g2b_rec.supplier_gstin.strip().upper() == eff_gstin:
                        norm_p = Rule37AEvidenceService.normalize_and_validate_return_period(g2b_rec.gstr3b_return_period)
                        if norm_p and norm_p == eff_period:
                            g3b_date = g3b_date or g2b_rec.gstr3b_filing_date
                            arn_str = arn_str or g2b_rec.gstr3b_filing_arn
                            locked_evidence = g2b_rec
                    elif g2b_rec and g2b_rec.gstr1_filing_date and not g2b_rec.gstr3b_filing_date:
                        raise ValidationError(
                            "Cannot reclaim under Rule 37A: Supplier has filed GSTR-1, but affirmative proof of GSTR-3B return "
                            "filing (filing date / ARN) is required. GSTR-1 outward declaration does not discharge tax liability under Section 16(2)(c)."
                        )

            # 4. Revalidate complete evidence contract holding the locks
            validated = Rule37AEvidenceService.validate_reclaim_evidence(
                voucher=locked_voucher,
                supplier_status=clean_status,
                supplier_gstin=eff_gstin,
                supplier_return_period=eff_period,
                verification_source=verification_source,
                verification_reference=arn_str,
                verification_date=eff_verif_date,
                verification_timestamp=eff_verif_date,
                gstr3b_filing_date=g3b_date,
                gstr3b_arn=arn_str,
                user=user,
                manual_verification_reason=manual_verification_reason,
                evidence_record=locked_evidence,
                freshness_threshold_days=freshness_threshold_days
            )

            # 3. Duplicate reclaim in same period prevention and idempotency
            idem_key = f"rule37a_rec_{locked_voucher.company.id}_{locked_voucher.id}_{clean_period}"
            existing_same_period = GSTReportingAllocation.objects.filter(
                company=locked_voucher.company,
                voucher=locked_voucher,
                event_type='ITC_RECLAIM',
                allocation_reason='RECLAIM_RULE_37A',
                assigned_period=clean_period,
                is_active=True
            ).first()

            if existing_same_period:
                if idempotent:
                    return existing_same_period
                else:
                    raise ValidationError(
                        f"Rule 37A reclaim already active in period {clean_period} for invoice #{locked_voucher.voucher_number}."
                    )

            # 4. Check remaining available reversal balance & prevent excessive reclaim
            available_balance = cls.get_rule37a_available_reversal_balance(locked_voucher)
            if available_balance <= Decimal('0.00'):
                raise ValidationError(
                    f"Rule 37A reclaim rejected: Prior reversal for invoice #{locked_voucher.voucher_number} "
                    f"has already been fully reclaimed."
                )

            summary = cls.compute_voucher_monetary_summary(locked_voucher)
            effective_reclaim_tax = quantize_amount(reclaim_tax if reclaim_tax is not None else summary["total_tax"])
            if effective_reclaim_tax <= Decimal('0.00'):
                raise ValidationError(
                    f"Rule 37A reclaim rejected: Reclaim tax amount ₹{effective_reclaim_tax} must be greater than zero."
                )
            if effective_reclaim_tax > available_balance:
                raise ValidationError(
                    f"Rule 37A reclaim rejected: Requested reclaim ₹{effective_reclaim_tax} exceeds available reversal balance ₹{available_balance}."
                )

            # Compute tax breakdown for full or partial reclaim
            if effective_reclaim_tax == summary["total_tax"]:
                taxable_val = summary["taxable_value"]
                igst_rec = summary["igst_amount"]
                cgst_rec = summary["cgst_amount"]
                sgst_rec = summary["sgst_amount"]
                cess_rec = summary["cess_amount"]
            else:
                tot_v_tax = summary["total_tax"]
                ratio = (effective_reclaim_tax / tot_v_tax) if tot_v_tax > Decimal('0.00') else Decimal('1.00')
                taxable_val = quantize_amount(summary["taxable_value"] * ratio)
                igst_rec = quantize_amount(summary["igst_amount"] * ratio)
                cgst_rec = quantize_amount(summary["cgst_amount"] * ratio)
                sgst_rec = quantize_amount(summary["sgst_amount"] * ratio)
                cess_rec = quantize_amount(summary["cess_amount"] * ratio)
                diff = effective_reclaim_tax - (igst_rec + cgst_rec + sgst_rec + cess_rec)
                if diff != Decimal('0.00'):
                    if igst_rec > Decimal('0.00'):
                        igst_rec += diff
                    elif cgst_rec > Decimal('0.00'):
                        cgst_rec += diff
                    elif sgst_rec > Decimal('0.00'):
                        sgst_rec += diff
                    else:
                        igst_rec += diff

            rec_date = reclaim_date or timezone.now().date()
            v_date_str = (verification_date or rec_date).strftime('%d-%m-%Y')
            ref_str = f" ARN: {validated['arn']}" if validated['arn'] else (f" Ref: {validated['document_ref']}" if validated['document_ref'] else "")

            notes = (
                f"Rule 37A ITC Reclaim for invoice #{locked_voucher.voucher_number}: supplier subsequently filed GSTR-3B. "
                f"Evidence: [{validated['supplier_status']}] Source: {validated['evidence_source']}{ref_str} Verified on: {v_date_str}."
            )

            alloc = GSTReportingAllocation.objects.create(
                company=locked_voucher.company,
                voucher=locked_voucher,
                gst_registration=getattr(locked_voucher, 'gst_registration', None),
                event_type='ITC_RECLAIM',
                voucher_date=locked_voucher.voucher_date,
                entry_date=rec_date,
                original_period=locked_voucher.voucher_date.strftime('%m%Y'),
                assigned_period=clean_period,
                financial_year=cls.get_financial_year(locked_voucher.voucher_date),
                allocation_reason='RECLAIM_RULE_37A',
                status='APPROVED',
                is_statutorily_eligible=True,
                statutory_rule='Proviso to CGST Rules Rule 37A (Reclaim after supplier files GSTR-3B)',
                statutory_notes=notes,
                taxable_value=taxable_val,
                igst_amount=igst_rec,
                cgst_amount=cgst_rec,
                sgst_amount=sgst_rec,
                cess_amount=cess_rec,
                total_tax=effective_reclaim_tax,
                is_active=True,
                source_reversal=prior_rev,
                payment_reference=validated['arn'],
                idempotency_key=idem_key,
                evidence_source=validated["evidence_source"],
                evidence_status=validated["supplier_status"],
                evidence_supplier_gstin=validated["supplier_gstin"],
                evidence_return_period=validated["supplier_return_period"],
                evidence_verified_at=validated["verification_timestamp"],
                evidence_document_ref=validated["document_ref"],
                evidence_arn=validated["arn"],
                evidence_filing_date=validated["filing_date"],
                evidence_hash=validated["evidence_hash"],
                evidence_metadata={
                    "evidence_source": validated["evidence_source"],
                    "manual_verification_reason": validated["manual_verification_reason"],
                    "verified_by": str(user) if user else ""
                },
                created_by=user
            )

            # Create lineage link
            lineage = GSTReversalReclaimLineage.objects.create(
                company=locked_voucher.company,
                voucher=locked_voucher,
                reversal_allocation=prior_rev,
                reclaim_allocation=alloc,
                reclaimed_tax=alloc.total_tax,
                igst_reclaimed=alloc.igst_amount,
                cgst_reclaimed=alloc.cgst_amount,
                sgst_reclaimed=alloc.sgst_amount,
                cess_reclaimed=alloc.cess_amount,
                statutory_rule='RULE_37A',
                created_by=user
            )

            if str(lineage.reclaim_allocation_id) != str(alloc.id) or str(lineage.reversal_allocation_id) != str(prior_rev.id):
                raise ValidationError("Failed to establish consistent reversal-to-reclaim lineage.")

            return alloc

    @classmethod
    def evaluate_section_16_status(
        cls,
        voucher: Voucher,
        check_date: Optional[date] = None,
        registration_revocation_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive evaluation of an invoice's statutory ITC status under Section 16 & Section 17.
        Distinguishes between:
        - BLOCKED_SEC_17_5: Permanently ineligible blocked credits
        - RECEIPT_PENDING: Section 16(2)(b) goods/services receipt unconfirmed
        - PARTIAL_RECEIPT: Proportionate receipt under First Proviso to Section 16(2)
        - ALREADY_CLAIMED: Availed in filed or active return
        - REVERSED_RULE_37: Reversed for non-payment within 180 days (reclaimable upon payment)
        - REVERSED_RULE_37A: Reversed for supplier GSTR-3B default (reclaimable upon filing)
        - RECLAIMED: Restored following subsequent payment or filing
        - RELIEF_SEC_16_5: Protected by Finance Act 2024 retrospective relief (FY 17-18 to 20-21 up to 30-Nov-2021)
        - RELIEF_SEC_16_6: Protected by 30-day revocation order extension
        - STATUTE_BARRED_SEC_16_4: Exceeded Section 16(4) cutoff without relief
        - CLAIMABLE: Fully eligible for claim in active return
        """
        today = check_date or timezone.now().date()
        v_date = voucher.voucher_date
        fy = cls.get_financial_year(v_date)
        summary = cls.compute_voucher_monetary_summary(voucher)
        total_tax = summary["total_tax"]

        if voucher.voucher_type != 'PURCHASE':
            return {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "status": "NOT_APPLICABLE",
                "category": "NOT_APPLICABLE",
                "is_eligible": False,
                "total_tax": total_tax,
                "financial_year": fy,
                "notes": "Section 16 ITC evaluation only applies to inward purchase supplies."
            }

        # 1. Section 17(5) Blocked Credit
        if (getattr(voucher, 'is_section_17_5_blocked', False) or 
            GSTReportingAllocation.objects.filter(voucher=voucher, event_type='ITC_REVERSAL_SEC_17_5', is_active=True).exists()):
            return {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "status": "BLOCKED_SEC_17_5",
                "category": "PERMANENTLY_BLOCKED",
                "is_eligible": False,
                "total_tax": total_tax,
                "financial_year": fy,
                "notes": "Permanently ineligible blocked credit under Section 17(5) of the CGST Act."
            }

        # 2. Check Reclaims
        active_reclaim = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_RECLAIM',
            is_active=True
        ).first()
        if active_reclaim:
            return {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "status": "RECLAIMED",
                "category": "ELIGIBLE_CLAIMED",
                "is_eligible": True,
                "total_tax": total_tax,
                "reclaimed_tax": active_reclaim.total_tax,
                "assigned_period": active_reclaim.assigned_period,
                "financial_year": fy,
                "notes": f"ITC restored under {active_reclaim.statutory_rule} in period {active_reclaim.assigned_period}."
            }

        # 3. Check Active Reversals
        active_rev_37 = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_RULE_37',
            is_active=True
        ).first()
        if active_rev_37:
            return {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "status": "REVERSED_RULE_37",
                "category": "REVERSED_CONDITIONAL",
                "is_eligible": False,
                "total_tax": total_tax,
                "reversed_tax": active_rev_37.total_tax,
                "financial_year": fy,
                "notes": "Reversed under Rule 37 (180 days non-payment). Reclaimable upon payment."
            }

        active_rev_37a = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='ITC_REVERSAL_RULE_37A',
            is_active=True
        ).first()
        if active_rev_37a:
            return {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "status": "REVERSED_RULE_37A",
                "category": "REVERSED_CONDITIONAL",
                "is_eligible": False,
                "total_tax": total_tax,
                "reversed_tax": active_rev_37a.total_tax,
                "financial_year": fy,
                "notes": "Reversed under Rule 37A (Supplier non-filing). Reclaimable when supplier furnishes GSTR-3B."
            }

        # 4. Check Inward ITC Allocation
        active_inward = GSTReportingAllocation.objects.filter(
            voucher=voucher,
            event_type='INWARD_ITC',
            is_active=True
        ).first()

        if active_inward:
            if not active_inward.is_receipt_confirmed:
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "RECEIPT_PENDING",
                    "category": "NOT_YET_ELIGIBLE",
                    "is_eligible": False,
                    "total_tax": total_tax,
                    "financial_year": fy,
                    "notes": "Section 16(2)(b): Goods or services receipt unconfirmed. ITC cannot be claimed."
                }
            if active_inward.partial_received_fraction < Decimal('1.0000'):
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "PARTIAL_RECEIPT",
                    "category": "PARTIALLY_ELIGIBLE",
                    "is_eligible": True,
                    "total_tax": total_tax,
                    "claimed_tax": active_inward.total_tax,
                    "fraction": str(active_inward.partial_received_fraction),
                    "financial_year": fy,
                    "notes": f"Proportionate ITC of {active_inward.partial_received_fraction*100:.1f}% claimed under First Proviso to Section 16(2)."
                }
            if active_inward.status in ('REPORTED', 'FILED'):
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "ALREADY_CLAIMED",
                    "category": "CLAIMED",
                    "is_eligible": True,
                    "total_tax": total_tax,
                    "assigned_period": active_inward.assigned_period,
                    "financial_year": fy,
                    "notes": f"ITC claimed and filed in return period {active_inward.assigned_period}."
                }
            if active_inward.status == 'APPROVED':
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "CLAIMABLE",
                    "category": "ELIGIBLE",
                    "is_eligible": True,
                    "total_tax": total_tax,
                    "assigned_period": active_inward.assigned_period,
                    "financial_year": fy,
                    "notes": f"Allocated and approved for claim in return period {active_inward.assigned_period}."
                }

        # 5. Check Cutoff Date & Reliefs
        cutoff_date = cls.get_statutory_cutoff_date(
            invoice_date=v_date,
            company=voucher.company,
            return_type='INWARD_ITC',
            registration_revocation_date=registration_revocation_date
        )

        is_sec16_5 = fy in ('2017-18', '2018-19', '2019-20', '2020-21')
        if is_sec16_5:
            if today <= cutoff_date:
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "RELIEF_SEC_16_5",
                    "category": "SPECIAL_STATUTORY_EXCEPTION",
                    "is_eligible": True,
                    "statutory_cutoff": cutoff_date,
                    "total_tax": total_tax,
                    "financial_year": fy,
                    "notes": "Statutory relief under Section 16(5) (Finance Act 2024): Deadline extended to 30-Nov-2021."
                }
            else:
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "STATUTE_BARRED_SEC_16_4",
                    "category": "TIME_BARRED",
                    "is_eligible": False,
                    "statutory_cutoff": cutoff_date,
                    "total_tax": total_tax,
                    "financial_year": fy,
                    "notes": f"Section 16(5) deadline expired on {cutoff_date.strftime('%d-%m-%Y')}."
                }

        if registration_revocation_date and cutoff_date > date(v_date.year if v_date.month <= 3 else v_date.year + 1, 11, 30):
            if today <= cutoff_date:
                return {
                    "voucher_id": str(voucher.id),
                    "voucher_number": voucher.voucher_number,
                    "voucher_type": voucher.voucher_type,
                    "status": "RELIEF_SEC_16_6",
                    "category": "SPECIAL_STATUTORY_EXCEPTION",
                    "is_eligible": True,
                    "statutory_cutoff": cutoff_date,
                    "total_tax": total_tax,
                    "financial_year": fy,
                    "notes": f"Section 16(6) revocation extension: Eligible up to {cutoff_date.strftime('%d-%m-%Y')} (30 days post revocation order)."
                }

        if today > cutoff_date:
            return {
                "voucher_id": str(voucher.id),
                "voucher_number": voucher.voucher_number,
                "voucher_type": voucher.voucher_type,
                "status": "STATUTE_BARRED_SEC_16_4",
                "category": "TIME_BARRED",
                "is_eligible": False,
                "statutory_cutoff": cutoff_date,
                "total_tax": total_tax,
                "financial_year": fy,
                "notes": f"Statute-barred under Section 16(4): 30th November cutoff ({cutoff_date.strftime('%d-%m-%Y')}) exceeded."
            }

        return {
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "voucher_type": voucher.voucher_type,
            "status": "CLAIMABLE",
            "category": "ELIGIBLE",
            "is_eligible": True,
            "statutory_cutoff": cutoff_date,
            "total_tax": total_tax,
            "financial_year": fy,
            "notes": "Eligible for claim subject to affirmative receipt confirmation and return filing."
        }

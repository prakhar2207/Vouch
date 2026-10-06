import uuid
import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q

from apps.companies.models import Company, UserCompany
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, InterCompanyEntry
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService
from apps.accounting.services.party_balance_service import PartyBalanceService

import logging
logger = logging.getLogger(__name__)


class InterCompanyService:
    """
    Forensic Inter-Company Accounting Engine.
    Handles:
    1. Automatic Sister Company Current Account ledger discovery/creation.
    2. Mirror Entry generation whenever Entity A posts a transaction affecting Entity B.
    3. 1-Click Approval & atomic counter-voucher generation in Entity B.
    4. Bidirectional Inter-Company Matrix Reconciliation & variance reporting.
    """

    @classmethod
    def get_or_create_intercompany_ledger(
        cls,
        company: Company,
        sister_company: Company
    ) -> Ledger:
        """
        Finds or auto-provisions a designated Inter-Company Current Account ledger
        for the given sister entity in the target company's chart of accounts.
        """
        # 1. Search by existing sister company GSTIN or name
        ledger = None
        if sister_company.gstin:
            ledger = Ledger.objects.filter(
                company=company,
                gstin__iexact=sister_company.gstin,
                is_archived=False
            ).first()

        canonical_name = f"{sister_company.name} (Inter-Company Current A/c)"

        if not ledger:
            ledger = Ledger.objects.filter(
                company=company,
                name__iexact=canonical_name,
                is_archived=False
            ).first()

        if not ledger:
            ledger = Ledger.objects.filter(
                company=company,
                name__icontains=sister_company.name,
                is_archived=False
            ).first()

        if ledger:
            return ledger

        # 2. Ensure Inter-Company group exists (under Current Assets / Loans & Advances)
        grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Inter-Company Current Accounts",
            defaults={"nature": "ASSET"}
        )

        # 3. Create fresh ledger
        new_ledger = Ledger.objects.create(
            company=company,
            group=grp,
            name=canonical_name,
            ledger_type="INTER_COMPANY",
            gstin=sister_company.gstin or "",
            state_code=sister_company.state_code or "",
            phone=sister_company.phone or "",
            email=sister_company.email or "",
            address=sister_company.address or "",
            opening_balance=Decimal("0.00"),
            opening_balance_type="DEBIT",
            is_active=True,
            is_archived=False
        )
        return new_ledger

    @classmethod
    @transaction.atomic
    def create_pending_mirror_entry(
        cls,
        source_voucher: Voucher,
        target_company: Company,
        entry_type: str = "TRANSFER",
        amount: Optional[Decimal] = None,
        narration: str = "",
        suggested_target_debit: Optional[Ledger] = None,
        suggested_target_credit: Optional[Ledger] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> InterCompanyEntry:
        """
        Creates an unconfirmed pending mirror entry in target_company's inbox.
        """
        eff_amount = amount or source_voucher.total_amount
        entry = InterCompanyEntry.objects.create(
            source_company=source_voucher.company,
            target_company=target_company,
            source_voucher=source_voucher,
            entry_type=entry_type,
            amount=eff_amount,
            entry_date=source_voucher.voucher_date,
            narration=narration or f"Mirror entry from {source_voucher.company.name} (#{source_voucher.voucher_number})",
            suggested_target_debit_ledger=suggested_target_debit,
            suggested_target_credit_ledger=suggested_target_credit,
            status="PENDING",
            metadata=metadata or {}
        )
        return entry

    @classmethod
    @transaction.atomic
    def accept_mirror_entry(
        cls,
        entry_id: str,
        user=None,
        target_debit_ledger_id: Optional[str] = None,
        target_credit_ledger_id: Optional[str] = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        1-Click Confirmation:
        Generates and posts the counterpart Voucher in target_company,
        guaranteeing Entity A Dr exactly equals Entity B Cr to the paisa.
        """
        entry = InterCompanyEntry.objects.select_for_update().get(id=entry_id)
        if entry.status == 'ACCEPTED':
            raise ValidationError("This inter-company entry has already been accepted and posted.")
        if entry.status == 'REJECTED':
            raise ValidationError("This inter-company entry was previously rejected.")

        target_company = entry.target_company
        source_company = entry.source_company
        source_vch = entry.source_voucher
        amount = entry.amount
        entry_date = entry.entry_date

        # Determine target debit and credit ledgers
        debit_ledger = None
        credit_ledger = None

        if target_debit_ledger_id:
            debit_ledger = Ledger.objects.get(id=target_debit_ledger_id, company=target_company)
        elif entry.suggested_target_debit_ledger:
            debit_ledger = entry.suggested_target_debit_ledger

        if target_credit_ledger_id:
            credit_ledger = Ledger.objects.get(id=target_credit_ledger_id, company=target_company)
        elif entry.suggested_target_credit_ledger:
            credit_ledger = entry.suggested_target_credit_ledger

        # Default fallback:
        # If source company transferred funds (source booked: Dr Sister Co B / Cr Bank A),
        # then target company B must book: Dr Bank B (or Cash B) / Cr Sister Co A Current A/c.
        sister_a_in_b = cls.get_or_create_intercompany_ledger(target_company, source_company)

        if not credit_ledger:
            credit_ledger = sister_a_in_b

        if not debit_ledger:
            # Default to primary Bank account in target company or Cash
            debit_ledger = Ledger.objects.filter(
                company=target_company,
                ledger_type='BANK',
                is_active=True
            ).first() or Ledger.objects.filter(
                company=target_company,
                ledger_type='CASH',
                is_active=True
            ).first()
            if not debit_ledger:
                raise ValidationError(f"Target company '{target_company.name}' does not have an active Bank or Cash ledger to receive funds.")

        # Determine Voucher Type:
        # If both sides are Bank/Cash/InterCompany -> CONTRA or RECEIPT
        v_type = 'CONTRA' if debit_ledger.ledger_type in ('BANK', 'CASH') and credit_ledger.ledger_type == 'INTER_COMPANY' else 'RECEIPT'
        v_num, _ = InvoiceSequenceService.get_next_number(target_company, v_type, entry_date)
        fy = InvoiceSequenceService.get_or_create_active_fy(target_company, entry_date)

        target_voucher = Voucher.objects.create(
            company=target_company,
            financial_year=fy,
            voucher_type=v_type,
            voucher_number=v_num,
            voucher_date=entry_date,
            party_ledger=credit_ledger if credit_ledger.ledger_type in ('INTER_COMPANY', 'CUSTOMER', 'SUPPLIER') else debit_ledger,
            reference_number=source_vch.voucher_number,
            status='DRAFT',
            total_amount=amount,
            narration=f"Accepted Inter-Company mirror from {source_company.name} (#{source_vch.voucher_number}). {notes}".strip(),
            created_by=user or source_vch.created_by
        )

        # Post standard double-entry lines
        LedgerEntry.objects.create(
            company=target_company,
            voucher=target_voucher,
            ledger=debit_ledger,
            debit_amount=amount,
            credit_amount=Decimal('0.00'),
            narration=f"Dr {debit_ledger.name} (Inter-company receipt from {source_company.name})"
        )
        LedgerEntry.objects.create(
            company=target_company,
            voucher=target_voucher,
            ledger=credit_ledger,
            debit_amount=Decimal('0.00'),
            credit_amount=amount,
            narration=f"Cr {credit_ledger.name} (Mirror for {source_vch.voucher_number})"
        )

        VoucherService.post_voucher(target_voucher)

        # Update InterCompanyEntry
        entry.target_voucher = target_voucher
        entry.status = 'ACCEPTED'
        entry.resolved_at = timezone.now()
        entry.resolved_by = user
        entry.save(update_fields=['target_voucher', 'status', 'resolved_at', 'resolved_by'])

        return {
            "status": "SUCCESS",
            "entry_id": str(entry.id),
            "target_voucher_id": str(target_voucher.id),
            "target_voucher_number": target_voucher.voucher_number,
            "message": f"Counter-voucher #{target_voucher.voucher_number} successfully posted in {target_company.name}."
        }

    @classmethod
    @transaction.atomic
    def reject_mirror_entry(cls, entry_id: str, user=None, reason: str = "") -> Dict[str, Any]:
        entry = InterCompanyEntry.objects.select_for_update().get(id=entry_id)
        if entry.status != 'PENDING':
            raise ValidationError(f"Cannot reject entry with status '{entry.status}'.")

        entry.status = 'REJECTED'
        entry.rejection_reason = reason or "Rejected by accountant"
        entry.resolved_at = timezone.now()
        entry.resolved_by = user
        entry.save(update_fields=['status', 'rejection_reason', 'resolved_at', 'resolved_by'])

        return {
            "status": "SUCCESS",
            "entry_id": str(entry.id),
            "message": "Inter-company entry marked as rejected."
        }

    @classmethod
    def get_reconciliation_matrix(
        cls,
        company_a: Company,
        company_b: Company,
        as_of_date: Optional[datetime.date] = None
    ) -> Dict[str, Any]:
        """
        Matrix Reconciliation between two sister companies:
        Pulls Ledger of B in A, and Ledger of A in B.
        Calculates net variance and lists un-mirrored entries.
        """
        ledger_b_in_a = cls.get_or_create_intercompany_ledger(company_a, company_b)
        ledger_a_in_b = cls.get_or_create_intercompany_ledger(company_b, company_a)

        # Balances
        date_q_a = Q(voucher__voucher_date__lte=as_of_date) if as_of_date else Q()
        date_q_b = Q(voucher__voucher_date__lte=as_of_date) if as_of_date else Q()

        qs_a = LedgerEntry.objects.filter(
            company=company_a,
            ledger=ledger_b_in_a,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
        ).filter(date_q_a)

        totals_a = qs_a.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
        dr_a = Decimal(str(totals_a['dr'] or '0.00'))
        cr_a = Decimal(str(totals_a['cr'] or '0.00'))
        net_a = dr_a - cr_a  # positive means Debit (A is owed by B), negative means Credit

        qs_b = LedgerEntry.objects.filter(
            company=company_b,
            ledger=ledger_a_in_b,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
        ).filter(date_q_b)

        totals_b = qs_b.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
        dr_b = Decimal(str(totals_b['dr'] or '0.00'))
        cr_b = Decimal(str(totals_b['cr'] or '0.00'))
        net_b = dr_b - cr_b  # in B's books: Dr means B is owed by A, Cr means B owes A

        # In a perfect mirror, Net A (Dr - Cr) + Net B (Dr - Cr) must equal 0.00!
        # If A has Net DR of 50,000, B must have Net CR of 50,000 (i.e. Net B = -50,000).
        # Variance = net_a + net_b
        variance = abs(net_a + net_b)
        is_reconciled = (variance == Decimal('0.00'))

        # Pending Mirror Entries between these two
        pending_a_to_b = InterCompanyEntry.objects.filter(
            source_company=company_a,
            target_company=company_b,
            status='PENDING'
        ).count()

        pending_b_to_a = InterCompanyEntry.objects.filter(
            source_company=company_b,
            target_company=company_a,
            status='PENDING'
        ).count()

        # Detailed entries in A
        entries_in_a = [
            {
                "id": str(e.id),
                "voucher_id": str(e.voucher_id),
                "voucher_number": e.voucher.voucher_number,
                "voucher_type": e.voucher.voucher_type,
                "voucher_date": str(e.voucher.voucher_date),
                "debit": float(e.debit_amount),
                "credit": float(e.credit_amount),
                "narration": e.narration or e.voucher.narration or "",
            }
            for e in qs_a.select_related('voucher').order_by('-voucher__voucher_date')[:50]
        ]

        # Detailed entries in B
        entries_in_b = [
            {
                "id": str(e.id),
                "voucher_id": str(e.voucher_id),
                "voucher_number": e.voucher.voucher_number,
                "voucher_type": e.voucher.voucher_type,
                "voucher_date": str(e.voucher.voucher_date),
                "debit": float(e.debit_amount),
                "credit": float(e.credit_amount),
                "narration": e.narration or e.voucher.narration or "",
            }
            for e in qs_b.select_related('voucher').order_by('-voucher__voucher_date')[:50]
        ]

        return {
            "company_a": {
                "id": str(company_a.id),
                "name": company_a.name,
                "ledger_name": ledger_b_in_a.name,
                "total_debit": float(dr_a),
                "total_credit": float(cr_a),
                "net_balance": float(net_a),
                "balance_type": "DR" if net_a >= 0 else "CR",
                "entries_count": qs_a.count(),
                "entries": entries_in_a,
            },
            "company_b": {
                "id": str(company_b.id),
                "name": company_b.name,
                "ledger_name": ledger_a_in_b.name,
                "total_debit": float(dr_b),
                "total_credit": float(cr_b),
                "net_balance": float(net_b),
                "balance_type": "DR" if net_b >= 0 else "CR",
                "entries_count": qs_b.count(),
                "entries": entries_in_b,
            },
            "net_variance": float(variance),
            "is_reconciled": is_reconciled,
            "pending_inbound_mirror_entries": pending_a_to_b + pending_b_to_a,
            "status_headline": "PERFECTLY BALANCED (₹0.00 Variance)" if is_reconciled else f"MISMATCH DETECTED (Variance: ₹{float(variance):,.2f})"
        }

import uuid
import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, BankTransaction, PartyMapping, BankStatementImport
from apps.accounting.services.voucher_service import VoucherService
from apps.accounting.services.sequence_service import InvoiceSequenceService
from apps.accounting.services.allocation_service import PaymentAllocationService
from apps.accounting.services.party_intelligence_service import PartyIntelligenceService
from apps.audit.services.audit_service import AuditService

class BankReconciliationService:
    """
    Automated and user-guided reconciliation of normalized bank transactions.
    Creates double-entry accounting vouchers (RECEIPT, PAYMENT, CONTRA),
    allocates funds against outstanding invoices, learns confirmed mappings,
    and recalculates authoritative balances.
    """

    @classmethod
    @transaction.atomic
    def resolve_transaction(
        cls,
        bank_tx: BankTransaction,
        action_type: str,
        payload: Dict[str, Any],
        user=None
    ) -> Dict[str, Any]:
        """
        Executes a deterministic resolution action on an unresolved or suggested bank transaction.
        Action types:
        - MATCH_PARTY: Link to party, auto-create voucher, allocate to invoices, learn mapping.
        - RECORD_PAYMENT: Formal payment/receipt creation with optional manual allocations.
        - RECORD_EXPENSE: Post expense against an expense ledger (e.g. Bank Charges).
        - RECORD_TRANSFER: Contra fund transfer between bank/cash ledgers.
        - OWNER_DRAWING: Equity drawings/capital transaction.
        - IGNORE: Flag as ignored with reason.
        """
        company = bank_tx.company
        amount = bank_tx.credit_amount if bank_tx.credit_amount > Decimal('0.00') else bank_tx.debit_amount
        is_money_in = bank_tx.credit_amount > Decimal('0.00')
        bank_ledger = bank_tx.bank_ledger

        if bank_tx.status == 'RECONCILED':
            v_num = bank_tx.matched_voucher.voucher_number if bank_tx.matched_voucher else 'unknown'
            raise ValidationError(
                f"Bank transaction '{bank_tx.description}' has already been reconciled into voucher #{v_num}. "
                f"One bank transaction can produce only one accounting outcome."
            )

        fy = InvoiceSequenceService.get_or_create_active_fy(company, bank_tx.transaction_date)

        if action_type == 'IGNORE':
            bank_tx.status = 'IGNORED'
            bank_tx.match_notes['ignore_reason'] = payload.get('reason', 'User marked as ignored')
            bank_tx.save(update_fields=['status', 'match_notes'])
            return {"status": "SUCCESS", "message": "Transaction marked as ignored."}

        created_voucher = None

        if action_type in ['MATCH_PARTY', 'RECORD_PAYMENT']:
            party_id = payload.get('party_id')
            if not party_id:
                raise ValidationError("Party ID is required to match transaction.")
            party = Ledger.objects.get(id=party_id, company=company)

            # Defensive double-entry guardrail:
            # If transaction is linked to a Customer, ensure it is treated as a RECEIPT (money in)
            # unless explicitly marked as a refund. If debit/credit amounts were previously flipped, fix them.
            import re
            if party.ledger_type == 'CUSTOMER' and not is_money_in:
                if not re.search(r'\bREFUND\b', bank_tx.description, re.IGNORECASE):
                    is_money_in = True
                    bank_tx.credit_amount = amount
                    bank_tx.debit_amount = Decimal('0.00')
                    bank_tx.save(update_fields=['credit_amount', 'debit_amount'])
            elif party.ledger_type == 'SUPPLIER' and is_money_in:
                if not re.search(r'\bREFUND\b', bank_tx.description, re.IGNORECASE):
                    is_money_in = False
                    bank_tx.debit_amount = amount
                    bank_tx.credit_amount = Decimal('0.00')
                    bank_tx.save(update_fields=['credit_amount', 'debit_amount'])

            v_type = 'RECEIPT' if is_money_in else 'PAYMENT'
            v_num, _ = InvoiceSequenceService.get_next_number(company, v_type, bank_tx.transaction_date)

            created_voucher = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type=v_type,
                voucher_number=v_num,
                voucher_date=bank_tx.transaction_date,
                party_ledger=party,
                reference_number=bank_tx.reference_number or "",
                status='POSTED',
                total_amount=amount,
                narration=f"Bank {v_type} via {bank_ledger.name}: {bank_tx.description}",
                created_by=user
            )

            if is_money_in:
                # Receipt: Dr Bank, Cr Customer
                LedgerEntry.objects.create(
                    company=company,
                    voucher=created_voucher,
                    ledger=bank_ledger,
                    debit_amount=amount,
                    credit_amount=Decimal('0.00'),
                    narration=f"Deposit into {bank_ledger.name}"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=created_voucher,
                    ledger=party,
                    debit_amount=Decimal('0.00'),
                    credit_amount=amount,
                    narration=f"Receipt from {party.name}"
                )
            else:
                # Payment: Dr Supplier, Cr Bank
                LedgerEntry.objects.create(
                    company=company,
                    voucher=created_voucher,
                    ledger=party,
                    debit_amount=amount,
                    credit_amount=Decimal('0.00'),
                    narration=f"Payment to {party.name}"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=created_voucher,
                    ledger=bank_ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=amount,
                    narration=f"Withdrawal from {bank_ledger.name}"
                )

            # Auto-allocate against oldest unpaid invoices/bills
            allocations = PaymentAllocationService.auto_allocate_voucher(created_voucher)

            # Recalculate balances
            VoucherService.recalculate_ledger_balance(bank_ledger)
            VoucherService.recalculate_ledger_balance(party)

            # Store learned mapping
            upi_id = PartyIntelligenceService.extract_upi_id(bank_tx.normalized_narration)
            if upi_id:
                PartyIntelligenceService.learn_mapping(
                    company=company,
                    pattern=upi_id,
                    party=party,
                    mapping_type='UPI',
                    confirmed_by_user=True
                )
            elif payload.get('learn_keyword'):
                keyword = str(payload['learn_keyword']).strip()
                if len(keyword) >= 3:
                    PartyIntelligenceService.learn_mapping(
                        company=company,
                        pattern=keyword,
                        party=party,
                        mapping_type='NARRATION',
                        confirmed_by_user=True
                    )

            bank_tx.matched_party = party
            bank_tx.matched_voucher = created_voucher
            bank_tx.status = 'RECONCILED'
            bank_tx.match_confidence = 1.0
            bank_tx.save(update_fields=['matched_party', 'matched_voucher', 'status', 'match_confidence', 'updated_at'])

            AuditService.log_action(
                company=company,
                user=user,
                action='CREATE',
                model_name='BankReconciliation',
                record_id=bank_tx.id,
                changes={
                    "action": action_type,
                    "voucher_number": v_num,
                    "party": party.name,
                    "amount": str(amount),
                    "allocations_count": len(allocations)
                }
            )

            return {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number,
                "allocations": allocations
            }

        elif action_type == 'RECORD_EXPENSE':
            expense_ledger_id = payload.get('expense_ledger_id')
            if not expense_ledger_id:
                # Default or find Bank Charges ledger
                exp_grp, _ = LedgerGroup.objects.get_or_create(
                    company=company,
                    name="Indirect Expenses",
                    defaults={"nature": "EXPENSE"}
                )
                exp_ledger, _ = Ledger.objects.get_or_create(
                    company=company,
                    name="Bank Charges & Fees",
                    defaults={"group": exp_grp, "ledger_type": "EXPENSE"}
                )
            else:
                exp_ledger = Ledger.objects.get(id=expense_ledger_id, company=company)

            v_num, _ = InvoiceSequenceService.get_next_number(company, 'PAYMENT', bank_tx.transaction_date)
            created_voucher = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type='PAYMENT',
                voucher_number=v_num,
                voucher_date=bank_tx.transaction_date,
                party_ledger=exp_ledger,
                reference_number=bank_tx.reference_number or "",
                status='POSTED',
                total_amount=amount,
                narration=f"Bank Expense via {bank_ledger.name}: {bank_tx.description}",
                created_by=user
            )

            # Dr Expense, Cr Bank
            LedgerEntry.objects.create(
                company=company, voucher=created_voucher, ledger=exp_ledger,
                debit_amount=amount, credit_amount=Decimal('0.00'), narration=bank_tx.description
            )
            LedgerEntry.objects.create(
                company=company, voucher=created_voucher, ledger=bank_ledger,
                debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Bank Charge from {bank_ledger.name}"
            )

            VoucherService.recalculate_ledger_balance(bank_ledger)
            VoucherService.recalculate_ledger_balance(exp_ledger)

            bank_tx.matched_party = exp_ledger
            bank_tx.matched_voucher = created_voucher
            bank_tx.status = 'RECONCILED'
            bank_tx.match_confidence = 1.0
            bank_tx.save(update_fields=['matched_party', 'matched_voucher', 'status', 'match_confidence', 'updated_at'])

            return {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number
            }

        elif action_type == 'RECORD_TRANSFER':
            target_ledger_id = payload.get('target_ledger_id') or payload.get('transfer_ledger_id')
            if not target_ledger_id:
                raise ValidationError("Target Bank or Cash account is required for transfer.")
            target_ledger = Ledger.objects.get(id=target_ledger_id, company=company)

            v_num, _ = InvoiceSequenceService.get_next_number(company, 'CONTRA', bank_tx.transaction_date)
            created_voucher = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type='CONTRA',
                voucher_number=v_num,
                voucher_date=bank_tx.transaction_date,
                reference_number=bank_tx.reference_number or "",
                status='POSTED',
                total_amount=amount,
                narration=f"Contra Fund Transfer: {bank_tx.description}",
                created_by=user
            )

            if is_money_in:
                # Deposit into this bank from target (e.g. Cash Deposit or Transfer in)
                # Dr Bank, Cr Target
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=bank_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=target_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)
            else:
                # Withdrawal from this bank to target (e.g. Cash Withdrawal or Transfer out)
                # Dr Target, Cr Bank
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=target_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=bank_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)

            VoucherService.recalculate_ledger_balance(bank_ledger)
            VoucherService.recalculate_ledger_balance(target_ledger)

            bank_tx.matched_voucher = created_voucher
            bank_tx.status = 'RECONCILED'
            bank_tx.save(update_fields=['matched_voucher', 'status', 'updated_at'])

            return {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number
            }

        elif action_type == 'OWNER_DRAWING':
            equity_grp, _ = LedgerGroup.objects.get_or_create(
                company=company, name="Equity Accounts", defaults={"nature": "EQUITY"}
            )
            drawings_ledger, _ = Ledger.objects.get_or_create(
                company=company, name="Owner's Capital / Drawings",
                defaults={"group": equity_grp, "ledger_type": "EQUITY", "opening_balance_type": "CREDIT"}
            )

            v_type = 'RECEIPT' if is_money_in else 'PAYMENT'
            v_num, _ = InvoiceSequenceService.get_next_number(company, v_type, bank_tx.transaction_date)
            created_voucher = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type=v_type,
                voucher_number=v_num,
                voucher_date=bank_tx.transaction_date,
                party_ledger=drawings_ledger,
                status='POSTED',
                total_amount=amount,
                narration=f"Owner {'Capital Deposit' if is_money_in else 'Personal Drawing'} via {bank_ledger.name}",
                created_by=user
            )

            if is_money_in:
                # Dr Bank, Cr Capital
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=bank_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=drawings_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)
            else:
                # Dr Drawings, Cr Bank
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=drawings_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=bank_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)

            VoucherService.recalculate_ledger_balance(bank_ledger)
            VoucherService.recalculate_ledger_balance(drawings_ledger)

            bank_tx.matched_party = drawings_ledger
            bank_tx.matched_voucher = created_voucher
            bank_tx.status = 'RECONCILED'
            bank_tx.save(update_fields=['matched_party', 'matched_voucher', 'status', 'updated_at'])

            return {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number
            }

        else:
            raise ValidationError(f"Unknown reconciliation action '{action_type}'.")

    @classmethod
    def get_reconciliation_summary(cls, company: Company, bank_ledger_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates aggregate dashboard counters for bank reconciliation."""
        from django.db.models import Sum, Count, Q

        valid_bank_id = None
        if bank_ledger_id and str(bank_ledger_id).strip().lower() not in ['null', 'undefined', 'all', 'none', '']:
            try:
                import uuid
                uuid.UUID(str(bank_ledger_id).strip())
                valid_bank_id = str(bank_ledger_id).strip()
            except (ValueError, TypeError, AttributeError):
                valid_bank_id = None

        qs = BankTransaction.objects.filter(company=company)
        if valid_bank_id:
            qs = qs.filter(bank_ledger_id=valid_bank_id)

        stats = qs.aggregate(
            total=Count('id'),
            matched_auto=Count('id', filter=Q(status='MATCHED_AUTO')),
            matched_suggested=Count('id', filter=Q(status='MATCHED_SUGGESTED')),
            unresolved=Count('id', filter=Q(status__in=['UNRESOLVED', 'UNPROCESSED'])),
            reconciled=Count('id', filter=Q(status='RECONCILED')),
            ignored=Count('id', filter=Q(status='IGNORED')),
            total_debits=Sum('debit_amount'),
            total_credits=Sum('credit_amount'),
            unrec_debit=Sum('debit_amount', filter=Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED'])),
            unrec_credit=Sum('credit_amount', filter=Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED']))
        )

        total_tx = stats['total'] or 0
        auto_matched = stats['matched_auto'] or 0
        suggested = stats['matched_suggested'] or 0
        unresolved = stats['unresolved'] or 0
        reconciled = stats['reconciled'] or 0
        ignored = stats['ignored'] or 0

        # Calculate statement closing balance (latest transaction balance if available)
        statement_closing_balance = None
        latest_tx = qs.exclude(balance__isnull=True).order_by('-transaction_date', '-created_at').first()
        if latest_tx and latest_tx.balance is not None:
            statement_closing_balance = str(latest_tx.balance)

        # Calculate book closing balance
        book_closing_balance = None
        if valid_bank_id:
            bank_ledger = Ledger.objects.filter(id=valid_bank_id, company=company).first()
            if bank_ledger:
                book_closing_balance = str(bank_ledger.current_balance or Decimal('0.00'))

        reconciliation_gap = None
        is_balanced = False
        if statement_closing_balance is not None and book_closing_balance is not None:
            gap = abs(Decimal(statement_closing_balance) - Decimal(book_closing_balance))
            reconciliation_gap = str(gap)
            is_balanced = (gap == Decimal('0.00'))
        elif unresolved == 0 and suggested == 0:
            is_balanced = True
            reconciliation_gap = "0.00"

        return {
            "total_transactions": total_tx,
            "auto_matched": auto_matched,
            "suggested": suggested,
            "unresolved": unresolved,
            "reconciled": reconciled,
            "ignored": ignored,
            "unresolved_count": unresolved,
            "needs_review_count": suggested,
            "matched_count": auto_matched + reconciled,
            "reconciled_count": reconciled,
            "ignored_count": ignored,
            "total_debits": str(stats['total_debits'] or Decimal('0.00')),
            "total_credits": str(stats['total_credits'] or Decimal('0.00')),
            "unreconciled_debit_amount": str(stats['unrec_debit'] or Decimal('0.00')),
            "unreconciled_credit_amount": str(stats['unrec_credit'] or Decimal('0.00')),
            "net_unreconciled_amount": str(Decimal(str(stats['unrec_credit'] or '0.00')) - Decimal(str(stats['unrec_debit'] or '0.00'))),
            "statement_closing_balance": statement_closing_balance or "0.00",
            "book_closing_balance": book_closing_balance or "0.00",
            "reconciliation_gap": reconciliation_gap or "0.00",
            "is_balanced": is_balanced
        }

    @classmethod
    @transaction.atomic
    def delete_transaction(cls, bank_tx: BankTransaction) -> None:
        """
        Deletes a bank transaction from the server.
        If it generated an automated reconciliation voucher, rolls back and deletes that voucher.
        """
        if bank_tx.matched_voucher:
            vch = bank_tx.matched_voucher
            # Only delete if it's an auto-generated bank voucher
            if vch.voucher_type in ['RECEIPT', 'PAYMENT', 'CONTRA']:
                entries = list(vch.ledger_entries.select_related('ledger'))
                ledgers_to_recalc = set(e.ledger for e in entries)
                vch.delete()
                for l in ledgers_to_recalc:
                    VoucherService.recalculate_ledger_balance(l)
        bank_tx.delete()

    @classmethod
    @transaction.atomic
    def delete_statement_import(cls, statement_import: BankStatementImport) -> int:
        """
        Deletes a statement import and all of its associated transactions.
        Safely rolls back any generated reconciliation vouchers.
        """
        txs = list(statement_import.transactions.select_related('matched_voucher'))
        deleted_count = len(txs)
        for tx in txs:
            cls.delete_transaction(tx)
        statement_import.delete()
        return deleted_count

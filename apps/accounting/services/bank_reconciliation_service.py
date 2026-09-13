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
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService

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
        Executes a deterministic resolution action on an bank transaction.
        Enforces immutable source direction:
        - Money IN (statement credit) can ONLY debit Bank ledger.
        - Money OUT (statement debit) can ONLY credit Bank ledger.
        """
        company = bank_tx.company
        amount = bank_tx.credit_amount if bank_tx.credit_amount > Decimal('0.00') else bank_tx.debit_amount
        is_money_in = bank_tx.credit_amount > Decimal('0.00')
        bank_ledger = bank_tx.bank_ledger

        # Strict direction invariant validation
        if is_money_in and bank_tx.credit_amount <= Decimal('0.00'):
            raise ValidationError("Invalid bank transaction: deposit must have positive credit amount.")
        if not is_money_in and bank_tx.debit_amount <= Decimal('0.00'):
            raise ValidationError("Invalid bank transaction: withdrawal must have positive debit amount.")

        if bank_tx.status == 'RECONCILED':
            if bank_tx.matched_voucher:
                return {
                    "status": "SUCCESS",
                    "voucher_id": str(bank_tx.matched_voucher.id),
                    "voucher_number": bank_tx.matched_voucher.voucher_number,
                    "message": "Transaction already reconciled.",
                    "allocations": []
                }
            raise ValidationError(
                f"Bank transaction '{bank_tx.description}' has already been reconciled. "
                f"One bank transaction can produce only one accounting outcome."
            )

        fy = InvoiceSequenceService.get_or_create_active_fy(company, bank_tx.transaction_date)

        if action_type in ['IGNORE', 'EXCLUDE']:
            reason = payload.get('reason', 'User marked as ignored/excluded')
            return cls.exclude_transaction(bank_tx, reason=reason, user=user)

        created_voucher = None

        if action_type in ['MATCH_PARTY', 'RECORD_PAYMENT', 'CONFIRM_RECEIPT', 'CONFIRM_PAYMENT', 'CONFIRM_CUSTOMER_RECEIPT', 'CONFIRM_SUPPLIER_PAYMENT', 'CONFIRM_SUPPLIER_REFUND', 'CONFIRM_CUSTOMER_REFUND']:
            party_id = payload.get('party_id')
            if not party_id:
                raise ValidationError("Party ID is required to match transaction.")
            party = Ledger.objects.get(id=party_id, company=company)

            explicit_intent = payload.get('intent') or action_type
            is_supplier = (party.canonical_role == 'SUPPLIER') or (party.ledger_type == 'SUPPLIER') or ('SUPPLIER' in explicit_intent)
            
            # Canonical voucher type based on direction
            v_type = 'RECEIPT' if is_money_in else 'PAYMENT'
            v_num, _ = InvoiceSequenceService.get_next_number(company, v_type, bank_tx.transaction_date)

            if is_money_in:
                if is_supplier or explicit_intent == 'CONFIRM_SUPPLIER_REFUND':
                    narration = f"Supplier refund / recovery from {party.name} via {bank_ledger.name}: {bank_tx.description}"
                else:
                    narration = f"Customer receipt from {party.name} via {bank_ledger.name}: {bank_tx.description}"
            else:
                if is_supplier:
                    narration = f"Payment to supplier {party.name} via {bank_ledger.name}: {bank_tx.description}"
                else:
                    narration = f"Customer refund to {party.name} via {bank_ledger.name}: {bank_tx.description}"

            created_voucher = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type=v_type,
                voucher_number=v_num,
                voucher_date=bank_tx.transaction_date,
                party_ledger=party,
                reference_number=bank_tx.reference_number or "",
                status='DRAFT',
                total_amount=amount,
                narration=narration,
                created_by=user
            )

            if is_money_in:
                # Immutable direction: Deposit ALWAYS debits Bank, credits Party
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
                    narration=f"Receipt from {party.name}" if not is_supplier else f"Refund from {party.name}"
                )
            else:
                # Immutable direction: Withdrawal ALWAYS debits Party, credits Bank
                LedgerEntry.objects.create(
                    company=company,
                    voucher=created_voucher,
                    ledger=party,
                    debit_amount=amount,
                    credit_amount=Decimal('0.00'),
                    narration=f"Payment to {party.name}" if is_supplier else f"Refund to {party.name}"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=created_voucher,
                    ledger=bank_ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=amount,
                    narration=f"Withdrawal from {bank_ledger.name}"
                )

            # Canonical posting pipeline (enforces double entry, row locks, balances)
            VoucherService.post_voucher(created_voucher)

            # Reference-aware and concurrency-safe allocation
            allocations = PaymentAllocationService.auto_allocate_voucher(
                created_voucher,
                preferred_invoice_id=payload.get('invoice_id')
            )

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

        elif action_type == 'MATCH_EXISTING_VOUCHER':
            voucher_id = payload.get('voucher_id')
            if not voucher_id:
                raise ValidationError("voucher_id is required to match an existing voucher.")
            vch = Voucher.objects.get(id=voucher_id, company=company)
            if vch.status not in EffectiveVoucherService.ACCOUNTING_STATUSES:
                raise ValidationError(f"Cannot match voucher with status '{vch.status}'. Only posted vouchers can be matched.")
            
            bank_entries = vch.ledger_entries.filter(ledger=bank_ledger)
            if not bank_entries.exists():
                raise ValidationError(f"Voucher {vch.voucher_number} does not affect bank ledger '{bank_ledger.name}'.")
            
            if is_money_in:
                if not bank_entries.filter(debit_amount__gt=Decimal('0.00')).exists():
                    raise ValidationError(
                        f"Direction mismatch: Bank transaction is a Deposit (Money IN), but voucher {vch.voucher_number} does not debit {bank_ledger.name}."
                    )
            else:
                if not bank_entries.filter(credit_amount__gt=Decimal('0.00')).exists():
                    raise ValidationError(
                        f"Direction mismatch: Bank transaction is a Withdrawal (Money OUT), but voucher {vch.voucher_number} does not credit {bank_ledger.name}."
                    )

            bank_tx.matched_voucher = vch
            if vch.party_ledger:
                bank_tx.matched_party = vch.party_ledger
            bank_tx.status = 'RECONCILED'
            bank_tx.match_confidence = 1.0
            bank_tx.save(update_fields=['matched_voucher', 'matched_party', 'status', 'match_confidence', 'updated_at'])

            return {
                "status": "SUCCESS",
                "voucher_id": str(vch.id),
                "voucher_number": vch.voucher_number,
                "message": f"Successfully matched transaction to voucher {vch.voucher_number}"
            }

        elif action_type == 'RECORD_EXPENSE':
            expense_ledger_id = payload.get('expense_ledger_id')
            if not expense_ledger_id:
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
                status='DRAFT',
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

            VoucherService.post_voucher(created_voucher)

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
                status='DRAFT',
                total_amount=amount,
                narration=f"Contra Fund Transfer: {bank_tx.description}",
                created_by=user
            )

            if is_money_in:
                # Deposit into this bank from target: Dr Bank, Cr Target
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=bank_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=target_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)
            else:
                # Withdrawal from this bank to target: Dr Target, Cr Bank
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=target_ledger, debit_amount=amount, credit_amount=Decimal('0.00'))
                LedgerEntry.objects.create(company=company, voucher=created_voucher, ledger=bank_ledger, debit_amount=Decimal('0.00'), credit_amount=amount)

            VoucherService.post_voucher(created_voucher)

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
                status='DRAFT',
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

            VoucherService.post_voucher(created_voucher)

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
    def get_bank_balance_as_of(cls, bank_ledger: Ledger, cutoff_date: Optional[datetime.date] = None) -> Decimal:
        """
        Calculates the authoritative book ledger balance for a bank account strictly as of cutoff_date.
        Includes opening balance plus all posted / reversed / corrected voucher ledger entries
        on or before cutoff_date.
        """
        from apps.accounting.models import LedgerEntry
        from django.db.models import Sum

        if not bank_ledger:
            return Decimal('0.00')

        has_opening_entries = LedgerEntry.objects.filter(
            ledger=bank_ledger,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
            voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
        ).exists()

        op_balance = Decimal('0.00') if has_opening_entries else Decimal(str(bank_ledger.opening_balance or '0.00'))

        if bank_ledger.opening_balance_type == 'CREDIT':
            op_dr = Decimal('0.00')
            op_cr = op_balance
        else:
            op_dr = op_balance
            op_cr = Decimal('0.00')

        entry_filter = {
            'ledger': bank_ledger,
            'voucher__status__in': EffectiveVoucherService.ACCOUNTING_STATUSES,
        }
        if cutoff_date:
            entry_filter['voucher__voucher_date__lte'] = cutoff_date

        totals = LedgerEntry.objects.filter(**entry_filter).aggregate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )
        total_dr = op_dr + Decimal(str(totals['total_dr'] or '0.00'))
        total_cr = op_cr + Decimal(str(totals['total_cr'] or '0.00'))

        if bank_ledger.normal_balance == 'CREDIT':
            return total_cr - total_dr
        return total_dr - total_cr

    @classmethod
    def get_reconciliation_summary(cls, company: Company, bank_ledger_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates aggregate dashboard counters and date-bound verification for bank reconciliation."""
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
            matched_auto=Count('id', filter=Q(status='MATCHED_AUTO', is_excluded=False)),
            matched_suggested=Count('id', filter=Q(status='MATCHED_SUGGESTED', is_excluded=False)),
            unresolved=Count('id', filter=Q(status__in=['UNRESOLVED', 'UNPROCESSED'], is_excluded=False)),
            reconciled=Count('id', filter=Q(status='RECONCILED', is_excluded=False)),
            ignored=Count('id', filter=Q(status='IGNORED', is_excluded=False)),
            excluded=Count('id', filter=Q(is_excluded=True)),
            total_debits=Sum('debit_amount', filter=Q(is_excluded=False)),
            total_credits=Sum('credit_amount', filter=Q(is_excluded=False)),
            unrec_debit=Sum('debit_amount', filter=Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED'], is_excluded=False)),
            unrec_credit=Sum('credit_amount', filter=Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED'], is_excluded=False))
        )

        total_tx = stats['total'] or 0
        auto_matched = stats['matched_auto'] or 0
        suggested = stats['matched_suggested'] or 0
        unresolved = stats['unresolved'] or 0
        reconciled = stats['reconciled'] or 0
        ignored = stats['ignored'] or 0
        excluded = stats['excluded'] or 0

        # Determine cutoff date:
        # 1. From latest non-excluded statement import
        # 2. From latest non-excluded transaction
        statement_cutoff_date = None
        if valid_bank_id:
            latest_import = BankStatementImport.objects.filter(
                company=company,
                bank_ledger_id=valid_bank_id,
                is_excluded=False
            ).order_by('-statement_end_date', '-created_at').first()
            if latest_import and latest_import.statement_end_date:
                statement_cutoff_date = latest_import.statement_end_date

        if not statement_cutoff_date:
            latest_tx_date = qs.filter(is_excluded=False).order_by('-transaction_date').values_list('transaction_date', flat=True).first()
            if latest_tx_date:
                statement_cutoff_date = latest_tx_date

        # Calculate statement closing balance
        statement_closing_balance = None
        latest_tx = qs.filter(is_excluded=False).exclude(balance__isnull=True).order_by('-transaction_date', '-created_at').first()
        if latest_tx and latest_tx.balance is not None:
            statement_closing_balance = str(latest_tx.balance)
        elif valid_bank_id:
            stmt = BankStatementImport.objects.filter(company=company, bank_ledger_id=valid_bank_id, is_excluded=False).order_by('-created_at').first()
            if stmt and stmt.closing_balance is not None:
                statement_closing_balance = str(stmt.closing_balance)

        # Calculate book closing balance as of statement cutoff date
        book_closing_balance = None
        uncleared_deposits = Decimal('0.00')
        unpresented_payments = Decimal('0.00')
        
        if valid_bank_id:
            bank_ledger = Ledger.objects.filter(id=valid_bank_id, company=company).first()
            if bank_ledger:
                book_bal = cls.get_bank_balance_as_of(bank_ledger, statement_cutoff_date)
                book_closing_balance = str(book_bal)

                if statement_cutoff_date:
                    rec_voucher_ids = set(
                        BankTransaction.objects.filter(
                            company=company,
                            bank_ledger_id=valid_bank_id,
                            status='RECONCILED',
                            matched_voucher__isnull=False
                        ).values_list('matched_voucher_id', flat=True)
                    )
                    unreconciled_book = LedgerEntry.objects.filter(
                        ledger=bank_ledger,
                        voucher__company=company,
                        voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
                        voucher__voucher_date__lte=statement_cutoff_date
                    ).exclude(voucher_id__in=rec_voucher_ids).exclude(
                        voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
                    ).aggregate(
                        unrec_dr=Sum('debit_amount'),
                        unrec_cr=Sum('credit_amount')
                    )
                    uncleared_deposits = Decimal(str(unreconciled_book['unrec_dr'] or '0.00'))
                    unpresented_payments = Decimal(str(unreconciled_book['unrec_cr'] or '0.00'))

        reconciliation_gap = None
        is_balanced = False
        if statement_closing_balance is not None and book_closing_balance is not None:
            gap = abs(Decimal(statement_closing_balance) - Decimal(book_closing_balance))
            reconciliation_gap = str(gap)
            is_balanced = (gap == Decimal('0.00'))

        # Classification state
        if unresolved == 0 and suggested == 0 and is_balanced:
            reconciliation_state = "FULLY_RECONCILED"
        elif unresolved == 0 and suggested == 0:
            reconciliation_state = "TRANSACTIONS_REVIEWED"
        elif is_balanced:
            reconciliation_state = "BALANCE_VERIFIED"
        else:
            reconciliation_state = "DISCREPANCY_DETECTED"

        return {
            "total_transactions": total_tx,
            "auto_matched": auto_matched,
            "suggested": suggested,
            "unresolved": unresolved,
            "reconciled": reconciled,
            "ignored": ignored,
            "excluded": excluded,
            "unresolved_count": unresolved,
            "needs_review_count": suggested,
            "matched_count": auto_matched + reconciled,
            "reconciled_count": reconciled,
            "ignored_count": ignored,
            "excluded_count": excluded,
            "total_debits": str(stats['total_debits'] or Decimal('0.00')),
            "total_credits": str(stats['total_credits'] or Decimal('0.00')),
            "unreconciled_debit_amount": str(stats['unrec_debit'] or Decimal('0.00')),
            "unreconciled_credit_amount": str(stats['unrec_credit'] or Decimal('0.00')),
            "net_unreconciled_amount": str(Decimal(str(stats['unrec_credit'] or '0.00')) - Decimal(str(stats['unrec_debit'] or '0.00'))),
            "statement_cutoff_date": statement_cutoff_date.isoformat() if statement_cutoff_date else None,
            "statement_closing_balance": statement_closing_balance or "0.00",
            "book_closing_balance": book_closing_balance or "0.00",
            "reconciliation_gap": reconciliation_gap or "0.00",
            "is_balanced": is_balanced,
            "reconciliation_state": reconciliation_state,
            "uncleared_deposits": str(uncleared_deposits),
            "unpresented_payments": str(unpresented_payments),
            "unmatched_statement_credits": str(stats['unrec_credit'] or Decimal('0.00')),
            "unmatched_statement_debits": str(stats['unrec_debit'] or Decimal('0.00'))
        }

    @classmethod
    @transaction.atomic
    def exclude_transaction(cls, bank_tx: BankTransaction, reason: str = "User excluded from books", user=None) -> Dict[str, Any]:
        """
        Audited, non-destructive exclusion of a bank transaction.
        If the transaction generated a posted voucher, canonically reverses it using VoucherService.create_reversal_voucher.
        """
        reversal_voucher = None
        if bank_tx.matched_voucher:
            vch = bank_tx.matched_voucher
            if vch.status in ['POSTED', 'VALIDATING']:
                reversal_voucher = VoucherService.create_reversal_voucher(
                    voucher=vch,
                    user=user,
                    reason=f"Bank transaction excluded: {reason}"
                )

        bank_tx.is_excluded = True
        bank_tx.status = 'EXCLUDED'
        bank_tx.exclusion_reason = reason
        bank_tx.excluded_at = timezone.now()
        bank_tx.excluded_by = user
        bank_tx.save(update_fields=['is_excluded', 'status', 'exclusion_reason', 'excluded_at', 'excluded_by', 'updated_at'])

        AuditService.log_action(
            company=bank_tx.company,
            user=user,
            action='EXCLUDE',
            model_name='BankTransaction',
            record_id=bank_tx.id,
            changes={
                "reason": reason,
                "reversal_voucher_id": str(reversal_voucher.id) if reversal_voucher else None
            }
        )
        return {
            "status": "SUCCESS",
            "message": "Transaction excluded from books.",
            "reversal_voucher_number": reversal_voucher.voucher_number if reversal_voucher else None
        }

    @classmethod
    @transaction.atomic
    def exclude_statement_import(cls, statement_import: BankStatementImport, reason: str = "User excluded statement", user=None) -> int:
        """
        Audited, non-destructive exclusion of a statement import and all of its associated transactions.
        Safely reverses any generated vouchers.
        """
        txs = list(statement_import.transactions.all())
        count = 0
        for tx in txs:
            cls.exclude_transaction(tx, reason=f"Statement '{statement_import.source_file_name}' excluded: {reason}", user=user)
            count += 1

        statement_import.is_excluded = True
        statement_import.exclusion_reason = reason
        statement_import.excluded_at = timezone.now()
        statement_import.excluded_by = user
        statement_import.save(update_fields=['is_excluded', 'exclusion_reason', 'excluded_at', 'excluded_by'])
        return count

    @classmethod
    @transaction.atomic
    def delete_transaction(cls, bank_tx: BankTransaction) -> None:
        """
        Deletes a bank transaction from the server.
        If it generated a reconciliation voucher, rolls back and cancels that voucher.
        """
        if bank_tx.matched_voucher:
            vch = bank_tx.matched_voucher
            if vch.status in ['POSTED', 'VALIDATING']:
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

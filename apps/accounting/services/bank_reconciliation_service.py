import logging
logger = logging.getLogger(__name__)
import uuid
import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, BankTransaction, PartyMapping, BankStatementImport, IdempotencyRecord
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
    def _save_idempotency_record(cls, company, user, client_key, payload, response_dict):
        """Persists database-backed idempotency record for all reconciliation resolution outcomes."""
        if not client_key:
            return
        import json
        payload_items = sorted([(k, str(v)) for k, v in payload.items() if k not in ['idempotency_key', 'client_key']])
        payload_hash = str(hash(str(payload_items)))
        IdempotencyRecord.objects.update_or_create(
            scope_key=f"recon_{company.id}_{client_key}",
            defaults={
                "company": company,
                "user": user,
                "client_key": client_key,
                "endpoint": "resolve_transaction",
                "method": "POST",
                "payload_hash": payload_hash,
                "status": "COMPLETED",
                "response_code": 200,
                "response_body": json.dumps(response_dict)
            }
        )

    @classmethod
    @transaction.atomic
    def resolve_transaction(
        cls,
        bank_tx: BankTransaction,
        action_type: str,
        payload: Dict[str, Any],
        user=None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a deterministic resolution action on a bank transaction.
        Enforces:
        - Row-level lock on bank transaction via select_for_update() inside atomic transaction.
        - Tenant isolation re-validation.
        - Idempotency via IdempotencyRecord and status check.
        - Closed financial period protection.
        - Immutable source direction:
          * Money IN (statement credit) can ONLY debit Bank ledger.
          * Money OUT (statement debit) can ONLY credit Bank ledger.
        """
        # P0 Concurrency & Integrity: Acquire exclusive row-level lock on bank transaction
        bank_tx = BankTransaction.objects.select_for_update().get(id=bank_tx.id)
        company = bank_tx.company

        # Re-verify tenant isolation
        target_company_id = payload.get('company_id')
        if target_company_id and str(target_company_id) != str(company.id):
            raise ValidationError("Tenant isolation error: Transaction belongs to a different company.")

        # Re-verify exclusion state
        if bank_tx.is_excluded:
            raise ValidationError("Cannot resolve an excluded bank transaction. Please restore it before reconciling.")

        # Check idempotency record if key provided
        client_key = idempotency_key or payload.get('idempotency_key') or payload.get('client_key')
        if client_key:
            scope_key = f"recon_{company.id}_{client_key}"
            existing_idem = IdempotencyRecord.objects.filter(scope_key=scope_key, status='COMPLETED').first()
            if existing_idem:
                payload_items = sorted([(k, str(v)) for k, v in payload.items() if k not in ['idempotency_key', 'client_key']])
                current_payload_hash = str(hash(str(payload_items)))
                if existing_idem.payload_hash and existing_idem.payload_hash != current_payload_hash:
                    raise ValidationError("Idempotency key reused with different payload.")
                if existing_idem.response_body:
                    import json
                    try:
                        return json.loads(existing_idem.response_body)
                    except Exception:
                        pass

        # Closed accounting period protection
        fy = InvoiceSequenceService.get_or_create_active_fy(company, bank_tx.transaction_date)
        if fy and fy.is_closed:
            raise ValidationError(
                f"Accounting period {fy.code} ({fy.name}) is closed. Modifications and reconciliations are not permitted in a closed period."
            )

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
                res = {
                    "status": "SUCCESS",
                    "voucher_id": str(bank_tx.matched_voucher.id),
                    "voucher_number": bank_tx.matched_voucher.voucher_number,
                    "message": "Transaction already reconciled.",
                    "allocations": []
                }
                cls._save_idempotency_record(company, user, client_key, payload, res)
                return res
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
            
            # Separate Accounting Interpretation from Immutable Source Evidence:
            # We NEVER mutate bank_tx.credit_amount or bank_tx.debit_amount.
            # Transaction direction is strictly defined by original imported evidence (is_money_in).
            # If a Customer has money out -> It is classified as a Customer Refund (Payment voucher).
            # If a Supplier has money in -> It is classified as a Supplier Refund/Rebate (Receipt voucher).
            if is_money_in:
                if is_supplier or explicit_intent in ['CONFIRM_SUPPLIER_REFUND', 'SUPPLIER_REFUND']:
                    v_classification = 'SUPPLIER_REFUND'
                    is_refund = True
                else:
                    v_classification = 'CUSTOMER_RECEIPT'
                    is_refund = False
            else:
                if is_supplier:
                    v_classification = 'SUPPLIER_PAYMENT'
                    is_refund = False
                else:
                    v_classification = 'CUSTOMER_REFUND'
                    is_refund = True

            # Canonical voucher type based on direction
            v_type = 'RECEIPT' if is_money_in else 'PAYMENT'

            # Stop Duplication Gatekeeper: Check if an existing manual voucher matches this transaction
            if not payload.get('force_new_voucher', False):
                from apps.accounting.services.deduplication_engine import TransactionDeduplicationEngine
                existing_match = TransactionDeduplicationEngine.detect_existing_voucher_for_bank_tx(
                    bank_tx=bank_tx,
                    party=party,
                    amount=amount,
                    is_money_in=is_money_in
                )
                if existing_match:
                    matched_vch = existing_match['voucher']
                    bank_tx.matched_voucher = matched_vch
                    bank_tx.matched_party = party
                    bank_tx.status = 'RECONCILED'
                    bank_tx.match_confidence = existing_match.get('confidence', 1.0)
                    bank_tx.save(update_fields=['matched_voucher', 'matched_party', 'status', 'match_confidence', 'updated_at'])

                    AuditService.log_action(
                        company=company,
                        user=user,
                        action='UPDATE',
                        model_name='BankReconciliation',
                        record_id=bank_tx.id,
                        changes={
                            "action": "AUTO_MATCH_EXISTING_DEDUPLICATED",
                            "voucher_number": matched_vch.voucher_number,
                            "party": party.name,
                            "amount": str(amount),
                            "reason": "Existing manual voucher matched to prevent duplicate voucher creation."
                        }
                    )

                    res = {
                        "status": "SUCCESS",
                        "voucher_id": str(matched_vch.id),
                        "voucher_number": matched_vch.voucher_number,
                        "message": f"Automatically linked to existing voucher #{matched_vch.voucher_number} to prevent duplicate transaction.",
                        "allocations": []
                    }
                    cls._save_idempotency_record(company, user, client_key, payload, res)
                    return res

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
            bank_tx.user_classification = v_classification
            bank_tx.is_refund = is_refund
            notes = bank_tx.match_notes if isinstance(bank_tx.match_notes, dict) else {}
            notes.setdefault('interpretation_history', []).append({
                'timestamp': timezone.now().isoformat(),
                'action_type': action_type,
                'party_id': str(party.id),
                'party_name': party.name,
                'classification': v_classification,
                'is_refund': is_refund,
                'voucher_id': str(created_voucher.id),
                'voucher_number': created_voucher.voucher_number,
                'user': user.email if user else 'SYSTEM'
            })
            bank_tx.match_notes = notes
            bank_tx.save(update_fields=['matched_party', 'matched_voucher', 'status', 'match_confidence', 'user_classification', 'is_refund', 'match_notes', 'updated_at'])

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

            res = {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number,
                "allocations": allocations
            }
            cls._save_idempotency_record(company, user, client_key, payload, res)
            return res

        elif action_type == 'MATCH_EXISTING_VOUCHER':
            voucher_id = payload.get('voucher_id')
            if not voucher_id:
                raise ValidationError("voucher_id is required to match an existing voucher.")
            vch = Voucher.objects.select_for_update().filter(id=voucher_id, company=company).first()
            if not vch:
                raise ValidationError(f"Voucher with ID {voucher_id} does not exist in this company.")
            if vch.status != 'POSTED':
                raise ValidationError(f"Cannot match voucher with status '{vch.status}'. Only active POSTED vouchers can be matched.")

            # Closed period verification on target voucher
            if vch.financial_year and vch.financial_year.is_closed:
                raise ValidationError(f"Cannot match voucher from closed accounting period {vch.financial_year.code}.")

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

            # Net Bank Movement Validation (P0 Accounting Correctness):
            # Compute net debit minus credit for deposit, or net credit minus debit for withdrawal.
            if is_money_in:
                net_bank_movement = sum(e.debit_amount - e.credit_amount for e in bank_entries)
            else:
                net_bank_movement = sum(e.credit_amount - e.debit_amount for e in bank_entries)

            if net_bank_movement <= Decimal('0.00'):
                raise ValidationError(
                    f"Direction mismatch: Net bank movement for {bank_ledger.name} is non-positive ({net_bank_movement})."
                )

            # Allow documented small currency rounding tolerance up to 0.05
            if abs(net_bank_movement - amount) > Decimal('0.05'):
                raise ValidationError(
                    f"Amount mismatch: Bank transaction amount is ₹{amount}, but voucher {vch.voucher_number} affects {bank_ledger.name} by ₹{net_bank_movement}."
                )

            # Uniqueness verification: Prevent multiple active transactions from linking to same voucher
            already_linked = BankTransaction.objects.filter(
                company=company,
                matched_voucher=vch,
                status='RECONCILED',
                is_excluded=False
            ).exclude(id=bank_tx.id).first()
            if already_linked and not payload.get('allow_split_allocation', False):
                raise ValidationError(
                    f"Voucher {vch.voucher_number} is already reconciled to another bank transaction on {already_linked.transaction_date} "
                    f"('{already_linked.description}'). A single voucher cannot be linked to multiple transactions without an explicit split allocation."
                )

            bank_tx.matched_voucher = vch
            if vch.party_ledger:
                bank_tx.matched_party = vch.party_ledger
            bank_tx.status = 'RECONCILED'
            bank_tx.match_confidence = 1.0

            notes = bank_tx.match_notes if isinstance(bank_tx.match_notes, dict) else {}
            notes['is_existing_matched'] = True
            notes['matched_voucher_number'] = vch.voucher_number
            bank_tx.match_notes = notes

            bank_tx.save(update_fields=['matched_voucher', 'matched_party', 'status', 'match_confidence', 'match_notes', 'updated_at'])

            AuditService.log_action(
                company=company,
                user=user,
                action='UPDATE',
                model_name='BankReconciliation',
                record_id=bank_tx.id,
                changes={
                    "action": "MATCH_EXISTING_VOUCHER",
                    "voucher_number": vch.voucher_number,
                    "amount": str(amount),
                    "party": vch.party_ledger.name if vch.party_ledger else None
                }
            )

            res = {
                "status": "SUCCESS",
                "voucher_id": str(vch.id),
                "voucher_number": vch.voucher_number,
                "message": f"Successfully matched transaction to voucher {vch.voucher_number}"
            }
            cls._save_idempotency_record(company, user, client_key, payload, res)
            return res

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

            res = {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number
            }
            cls._save_idempotency_record(company, user, client_key, payload, res)
            return res

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

            res = {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number
            }
            cls._save_idempotency_record(company, user, client_key, payload, res)
            return res

        elif action_type in ['TRIANGULAR_SETTLEMENT', 'SISTER_COMPANY_SETTLEMENT']:
            target_company_id = payload.get('target_company_id')
            if not target_company_id:
                raise ValidationError("Target Sister Company ID is required for triangular settlement.")

            target_company = Company.objects.get(id=target_company_id)
            if target_company.id == company.id:
                raise ValidationError("Target company cannot be the same company.")

            from apps.accounting.services.inter_company_service import InterCompanyService
            from apps.accounting.models import InterCompanyEntry

            # 1. In Current Company (Company B):
            ic_ledger_in_b = InterCompanyService.get_or_create_intercompany_ledger(company, target_company)
            v_type_b = 'RECEIPT' if is_money_in else 'PAYMENT'
            v_num_b, _ = InvoiceSequenceService.get_next_number(company, v_type_b, bank_tx.transaction_date)

            narration_b = f"Triangular settlement for {target_company.name}: {bank_tx.description}"
            voucher_b = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type=v_type_b,
                voucher_number=v_num_b,
                voucher_date=bank_tx.transaction_date,
                party_ledger=ic_ledger_in_b,
                reference_number=bank_tx.reference_number or "",
                status='DRAFT',
                total_amount=amount,
                narration=narration_b,
                created_by=user
            )

            if is_money_in:
                LedgerEntry.objects.create(company=company, voucher=voucher_b, ledger=bank_ledger, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Deposit into {bank_ledger.name}")
                LedgerEntry.objects.create(company=company, voucher=voucher_b, ledger=ic_ledger_in_b, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Cr {ic_ledger_in_b.name} (funds held for {target_company.name})")
            else:
                LedgerEntry.objects.create(company=company, voucher=voucher_b, ledger=ic_ledger_in_b, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Dr {ic_ledger_in_b.name} (paid on behalf of {target_company.name})")
                LedgerEntry.objects.create(company=company, voucher=voucher_b, ledger=bank_ledger, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Withdrawal from {bank_ledger.name}")

            VoucherService.post_voucher(voucher_b)

            # 2. In Target Sister Company (Company A):
            target_party_id = payload.get('target_party_id')
            target_party = None
            if target_party_id:
                target_party = Ledger.objects.get(id=target_party_id, company=target_company)

            ic_ledger_in_a = InterCompanyService.get_or_create_intercompany_ledger(target_company, company)
            target_fy = InvoiceSequenceService.get_or_create_active_fy(target_company, bank_tx.transaction_date)

            v_type_a = 'RECEIPT' if is_money_in else 'PAYMENT'
            v_num_a, _ = InvoiceSequenceService.get_next_number(target_company, v_type_a, bank_tx.transaction_date)

            voucher_a = Voucher.objects.create(
                company=target_company,
                financial_year=target_fy,
                voucher_type=v_type_a,
                voucher_number=v_num_a,
                voucher_date=bank_tx.transaction_date,
                party_ledger=target_party or ic_ledger_in_a,
                reference_number=f"TRIANGULAR/{voucher_b.voucher_number}",
                status='DRAFT',
                total_amount=amount,
                narration=f"Triangular settlement cleared via {company.name} Bank ({bank_ledger.name}): {bank_tx.description}",
                created_by=user
            )

            if is_money_in:
                LedgerEntry.objects.create(company=target_company, voucher=voucher_a, ledger=ic_ledger_in_a, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Dr {ic_ledger_in_a.name} (funds received in {company.name})")
                LedgerEntry.objects.create(company=target_company, voucher=voucher_a, ledger=target_party or ic_ledger_in_a, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Cr {target_party.name if target_party else 'Sister Co'} (invoice settlement)")
            else:
                LedgerEntry.objects.create(company=target_company, voucher=voucher_a, ledger=target_party or ic_ledger_in_a, debit_amount=amount, credit_amount=Decimal('0.00'), narration=f"Dr {target_party.name if target_party else 'Sister Co'} (supplier payment)")
                LedgerEntry.objects.create(company=target_company, voucher=voucher_a, ledger=ic_ledger_in_a, debit_amount=Decimal('0.00'), credit_amount=amount, narration=f"Cr {ic_ledger_in_a.name} (settled via {company.name})")

            VoucherService.post_voucher(voucher_a)

            target_allocations = []
            if payload.get('target_invoice_id') or target_party:
                try:
                    target_allocations = PaymentAllocationService.auto_allocate_voucher(
                        voucher_a,
                        preferred_invoice_id=payload.get('target_invoice_id')
                    )
                except Exception as e:
                    logger.warning(f"Allocation note during triangular settlement: {e}")

            InterCompanyEntry.objects.create(
                source_company=company,
                target_company=target_company,
                source_voucher=voucher_b,
                target_voucher=voucher_a,
                entry_type='TRIANGULAR_SETTLEMENT',
                amount=amount,
                entry_date=bank_tx.transaction_date,
                narration=f"Triangular Settlement: {company.name} <-> {target_company.name}",
                suggested_target_debit_ledger=ic_ledger_in_a if is_money_in else target_party,
                suggested_target_credit_ledger=target_party if is_money_in else ic_ledger_in_a,
                status='ACCEPTED',
                resolved_at=timezone.now(),
                resolved_by=user,
                metadata={
                    "bank_transaction_id": str(bank_tx.id),
                    "target_allocations_count": len(target_allocations) if target_allocations else 0
                }
            )

            bank_tx.matched_voucher = voucher_b
            bank_tx.matched_party = ic_ledger_in_b
            bank_tx.status = 'RECONCILED'
            bank_tx.match_confidence = 1.0
            bank_tx.save(update_fields=['matched_voucher', 'matched_party', 'status', 'match_confidence', 'updated_at'])

            res = {
                "status": "SUCCESS",
                "voucher_id": str(voucher_b.id),
                "voucher_number": voucher_b.voucher_number,
                "target_voucher_id": str(voucher_a.id),
                "target_voucher_number": voucher_a.voucher_number,
                "target_company_name": target_company.name,
                "message": f"Triangular settlement complete: Reconciled in {company.name} and posted in {target_company.name}."
            }
            cls._save_idempotency_record(company, user, client_key, payload, res)
            return res

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

            res = {
                "status": "SUCCESS",
                "voucher_id": str(created_voucher.id),
                "voucher_number": created_voucher.voucher_number
            }
            cls._save_idempotency_record(company, user, client_key, payload, res)
            return res

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
    def get_reconciliation_summary(cls, company: Company, bank_ledger_id: Optional[str] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> Dict[str, Any]:
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
        if start_date:
            qs = qs.filter(transaction_date__gte=start_date)
        if end_date:
            qs = qs.filter(transaction_date__lte=end_date)

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
            unrec_debit=Sum('debit_amount', filter=Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED', 'MATCHED_AUTO'], is_excluded=False)),
            unrec_credit=Sum('credit_amount', filter=Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED', 'MATCHED_AUTO'], is_excluded=False))
        )

        total_tx = stats['total'] or 0
        auto_matched = stats['matched_auto'] or 0
        suggested = stats['matched_suggested'] or 0
        unresolved = stats['unresolved'] or 0
        reconciled = stats['reconciled'] or 0
        ignored = stats['ignored'] or 0
        excluded = stats['excluded'] or 0

        # Determine cutoff date:
        # 1. If explicit end_date is provided, use it
        # 2. From latest non-excluded statement import within range
        # 3. From latest non-excluded transaction within range
        statement_cutoff_date = None
        if end_date:
            statement_cutoff_date = end_date
        elif valid_bank_id:
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
        # Strict rule: Missing evidence MUST remain None (never silently become 0.00)
        statement_closing_balance = None
        has_statement_evidence = False

        latest_tx_qs = BankTransaction.objects.filter(company=company, is_excluded=False).exclude(balance__isnull=True)
        if valid_bank_id:
            latest_tx_qs = latest_tx_qs.filter(bank_ledger_id=valid_bank_id)
        if end_date:
            latest_tx_qs = latest_tx_qs.filter(transaction_date__lte=end_date)
        latest_tx = latest_tx_qs.order_by('-transaction_date', '-created_at').first()

        if latest_tx and latest_tx.balance is not None:
            statement_closing_balance = str(latest_tx.balance)
            has_statement_evidence = True
        elif valid_bank_id:
            stmt_qs = BankStatementImport.objects.filter(company=company, bank_ledger_id=valid_bank_id, is_excluded=False)
            if end_date:
                stmt_qs = stmt_qs.filter(statement_end_date__lte=end_date)
            stmt = stmt_qs.order_by('-statement_end_date', '-created_at').first()
            if stmt and stmt.closing_balance is not None:
                statement_closing_balance = str(stmt.closing_balance)
                has_statement_evidence = True

        # Calculate book closing balance as of statement cutoff date or end_date
        book_closing_balance = None
        uncleared_deposits = Decimal('0.00')
        unpresented_payments = Decimal('0.00')

        if valid_bank_id:
            bank_ledger = Ledger.objects.filter(id=valid_bank_id, company=company).first()
            if bank_ledger:
                effective_as_of = end_date or statement_cutoff_date
                book_bal = cls.get_bank_balance_as_of(bank_ledger, effective_as_of)
                book_closing_balance = str(book_bal)

                if effective_as_of:
                    # Enforce cutoff integrity: Vouchers reconciled AFTER effective_as_of must NOT leak
                    rec_voucher_ids = set(
                        BankTransaction.objects.filter(
                            company=company,
                            bank_ledger_id=valid_bank_id,
                            status='RECONCILED',
                            matched_voucher__isnull=False,
                            transaction_date__lte=effective_as_of,
                            matched_voucher__voucher_date__lte=effective_as_of
                        ).values_list('matched_voucher_id', flat=True)
                    )
                    unreconciled_book = LedgerEntry.objects.filter(
                        ledger=bank_ledger,
                        voucher__company=company,
                        voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
                        voucher__voucher_date__lte=effective_as_of
                    )
                    if start_date:
                        unreconciled_book = unreconciled_book.filter(voucher__voucher_date__gte=start_date)
                    unreconciled_book = unreconciled_book.exclude(voucher_id__in=rec_voucher_ids).exclude(
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

        # Authoritative State Machine Definitions (Phase 2 & Phase 3):
        # 1. NOT_STARTED: No transactions and no statement imports recorded.
        # 2. NOT_VERIFIABLE: Transactions exist but no statement closing balance is verifiable.
        # 3. FULLY_RECONCILED: Total > 0, 0 unresolved, 0 suggestions, statement balance verifiable, and gap is 0.00.
        # 4. BALANCE_MATCHED: Balances match exactly (gap=0.00), but transactions still require review/confirmation.
        # 5. IN_PROGRESS: Some transactions reconciled, but unresolved transactions remain.
        # 6. NEEDS_ATTENTION: Discrepancy detected or unresolved transactions await user review.
        # Authoritative State Machine Definitions (Phase 2 & Phase 3):
        # 1. NOT_STARTED: No transactions and no statement imports recorded.
        # 2. NOT_VERIFIABLE: Transactions exist but no statement closing balance is verifiable.
        # 3. FULLY_RECONCILED: Statement balance verifiable, is_balanced (gap==0.00), unresolved==0, suggested==0, and auto_matched==0.
        # 4. BALANCE_MATCHED: Balances match exactly (gap==0.00), but transactions still require review/confirmation.
        # 5. IN_PROGRESS: Some transactions reconciled, but unresolved transactions or suggestions remain.
        # 6. NEEDS_ATTENTION: Discrepancy detected or unresolved transactions await user review.
        if total_tx == 0 and not has_statement_evidence:
            reconciliation_state = "NOT_STARTED"
        elif not has_statement_evidence:
            reconciliation_state = "NOT_VERIFIABLE"
        elif unresolved == 0 and suggested == 0 and auto_matched == 0 and is_balanced:
            reconciliation_state = "FULLY_RECONCILED"
        elif is_balanced and (unresolved > 0 or suggested > 0 or auto_matched > 0):
            reconciliation_state = "BALANCE_MATCHED"
        elif reconciled > 0 and (unresolved > 0 or suggested > 0 or auto_matched > 0):
            reconciliation_state = "IN_PROGRESS"
        else:
            reconciliation_state = "NEEDS_ATTENTION"

        cutoff_str = None
        if statement_cutoff_date:
            cutoff_str = statement_cutoff_date.isoformat() if hasattr(statement_cutoff_date, 'isoformat') else str(statement_cutoff_date)

        return {
            "total_transactions": total_tx,
            "auto_matched": auto_matched,
            "suggested": suggested,
            "unresolved": unresolved,
            "reconciled": reconciled,
            "ignored": ignored,
            "excluded": excluded,
            "unresolved_count": unresolved,
            "needs_review_count": suggested + auto_matched,
            "matched_count": reconciled,
            "completed_count": reconciled,
            "reconciled_count": reconciled,
            "ignored_count": ignored,
            "excluded_count": excluded,
            "total_debits": str(stats['total_debits'] or Decimal('0.00')),
            "total_credits": str(stats['total_credits'] or Decimal('0.00')),
            "unreconciled_debit_amount": str(stats['unrec_debit'] or Decimal('0.00')),
            "unreconciled_credit_amount": str(stats['unrec_credit'] or Decimal('0.00')),
            "net_unreconciled_amount": str(Decimal(str(stats['unrec_credit'] or '0.00')) - Decimal(str(stats['unrec_debit'] or '0.00'))),
            "statement_cutoff_date": cutoff_str,
            "statement_closing_balance": statement_closing_balance,
            "book_closing_balance": book_closing_balance,
            "reconciliation_gap": reconciliation_gap,
            "is_balanced": is_balanced,
            "reconciliation_state": reconciliation_state,
            "has_statement_evidence": has_statement_evidence,
            "progress_percent": round((reconciled / total_tx) * 100) if total_tx > 0 else 0,
            "uncleared_deposits": str(uncleared_deposits),
            "unpresented_payments": str(unpresented_payments),
            "unmatched_statement_credits": str(stats['unrec_credit'] or Decimal('0.00')),
            "unmatched_statement_debits": str(stats['unrec_debit'] or Decimal('0.00')),
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None
        }

    @classmethod
    def generate_statutory_brs(
        cls,
        company: Company,
        bank_ledger_id: str,
        as_of_date: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generates classical statutory Bank Reconciliation Statement (BRS) as of as_of_date.
        Strict 2-Column Format (Tally & Zoho Books Standard):
        -------------------------------------------------------------
        1. Balance as per Company Books (Ledger Balance): B_books
        2. Additions:
           - Unpresented Cheques / Outward payments in books not yet debited by bank
           - Direct Credits in bank statement not yet recorded in books
        3. Deductions:
           - Uncleared Cheques / Inward receipts in books not yet credited by bank
           - Direct Debits / bank charges in statement not yet recorded in books
        4. Reconciled Balance as per Bank Statement: B_reconciled
        5. Actual Statement Balance (Passbook): B_statement
        6. Difference / Variance: |B_reconciled - B_statement|
        -------------------------------------------------------------
        """
        d_as_of = as_of_date
        if d_as_of and not isinstance(d_as_of, datetime.date):
            d_as_of = datetime.date.fromisoformat(str(d_as_of).split('T')[0])
        elif not d_as_of:
            d_as_of = timezone.now().date()

        bank_ledger = Ledger.objects.get(id=bank_ledger_id, company=company)

        # 1. Authoritative Book Ledger Balance as of cutoff date
        book_balance = cls.get_bank_balance_as_of(bank_ledger, cutoff_date=d_as_of)

        # 2. Reconciled vouchers set up to cutoff date (P0 BRS Cutoff Strictness):
        # Must only consider vouchers whose voucher_date is on or before cutoff date, and from non-excluded items.
        rec_voucher_ids = set(
            BankTransaction.objects.filter(
                company=company,
                bank_ledger=bank_ledger,
                status='RECONCILED',
                matched_voucher__isnull=False,
                transaction_date__lte=d_as_of,
                matched_voucher__voucher_date__lte=d_as_of,
                is_excluded=False
            ).values_list('matched_voucher_id', flat=True)
        )

        # 3. Unreconciled book entries up to cutoff date
        unrec_entries = LedgerEntry.objects.filter(
            ledger=bank_ledger,
            voucher__company=company,
            voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
            voucher__voucher_date__lte=d_as_of
        ).exclude(voucher_id__in=rec_voucher_ids).exclude(
            voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
        ).select_related('voucher', 'voucher__party_ledger').order_by('voucher__voucher_date', 'voucher__voucher_number')

        unpresented_payments_list = []
        uncleared_deposits_list = []
        tot_unpresented = Decimal('0.00')
        tot_uncleared = Decimal('0.00')

        for entry in unrec_entries:
            v = entry.voucher
            party_name = v.party_ledger.name if v.party_ledger else "Direct Entry"
            # Credit to Bank in books = Money paid / Cheque issued by company
            if entry.credit_amount > Decimal('0.00'):
                unpresented_payments_list.append({
                    "voucher_id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "voucher_date": str(v.voucher_date),
                    "voucher_type": v.voucher_type,
                    "party_name": party_name,
                    "amount": str(entry.credit_amount),
                    "narration": v.narration
                })
                tot_unpresented += entry.credit_amount
            # Debit to Bank in books = Money received / Cheque deposited by company
            elif entry.debit_amount > Decimal('0.00'):
                uncleared_deposits_list.append({
                    "voucher_id": str(v.id),
                    "voucher_number": v.voucher_number,
                    "voucher_date": str(v.voucher_date),
                    "voucher_type": v.voucher_type,
                    "party_name": party_name,
                    "amount": str(entry.debit_amount),
                    "narration": v.narration
                })
                tot_uncleared += entry.debit_amount

        # 4. Unreconciled bank statement transactions up to cutoff date:
        # Includes transactions not reconciled, OR transactions reconciled to future vouchers (> d_as_of)
        unrec_statement_txs = BankTransaction.objects.filter(
            company=company,
            bank_ledger=bank_ledger,
            transaction_date__lte=d_as_of,
            is_excluded=False
        ).exclude(status='IGNORED').filter(
            Q(status__in=['UNPROCESSED', 'UNRESOLVED', 'MATCHED_SUGGESTED', 'MATCHED_AUTO']) |
            (Q(status='RECONCILED') & Q(matched_voucher__voucher_date__gt=d_as_of))
        ).order_by('transaction_date')

        unrecorded_bank_credits_list = []
        unrecorded_bank_debits_list = []
        tot_unrecorded_credits = Decimal('0.00')
        tot_unrecorded_debits = Decimal('0.00')

        for tx in unrec_statement_txs:
            # Statement credit = Money received in bank but not yet entered in books
            if tx.credit_amount > Decimal('0.00'):
                unrecorded_bank_credits_list.append({
                    "transaction_id": str(tx.id),
                    "transaction_date": str(tx.transaction_date),
                    "description": tx.description,
                    "amount": str(tx.credit_amount),
                    "reference_number": tx.reference_number
                })
                tot_unrecorded_credits += tx.credit_amount
            # Statement debit = Money deducted by bank (e.g. charges/EMI) not yet entered in books
            elif tx.debit_amount > Decimal('0.00'):
                unrecorded_bank_debits_list.append({
                    "transaction_id": str(tx.id),
                    "transaction_date": str(tx.transaction_date),
                    "description": tx.description,
                    "amount": str(tx.debit_amount),
                    "reference_number": tx.reference_number
                })
                tot_unrecorded_debits += tx.debit_amount

        # 5. Determine Actual Statement Closing Balance (Passbook)
        # Strict rule: If statement evidence is unavailable, keep None to prevent false reconciliation success
        latest_tx = BankTransaction.objects.filter(
            company=company,
            bank_ledger=bank_ledger,
            transaction_date__lte=d_as_of,
            is_excluded=False
        ).exclude(balance__isnull=True).order_by('-transaction_date', '-created_at').first()

        statement_balance = None
        if latest_tx and latest_tx.balance is not None:
            statement_balance = latest_tx.balance
        else:
            stmt = BankStatementImport.objects.filter(
                company=company,
                bank_ledger=bank_ledger,
                statement_end_date__lte=d_as_of,
                is_excluded=False
            ).order_by('-statement_end_date', '-created_at').first()
            if stmt and stmt.closing_balance is not None:
                statement_balance = stmt.closing_balance

        # 6. Compute Reconciled Balance via standard accounting bridge:
        # B_reconciled = B_books + Unpresented Payments + Unrecorded Credits - Uncleared Deposits - Unrecorded Debits
        reconciled_balance = (
            book_balance + tot_unpresented + tot_unrecorded_credits - tot_uncleared - tot_unrecorded_debits
        ).quantize(Decimal('0.01'))

        if statement_balance is not None:
            variance = abs(reconciled_balance - statement_balance).quantize(Decimal('0.01'))
            is_reconciled = (variance <= Decimal('0.01'))
            reconciliation_status = "PERFECTLY_RECONCILED" if is_reconciled else "VARIANCE_DETECTED"
        else:
            variance = None
            is_reconciled = False
            reconciliation_status = "NOT_VERIFIABLE"

        return {
            "company_name": company.name,
            "bank_account_name": bank_ledger.name,
            "bank_account_number": bank_ledger.bank_account_number or "",
            "as_of_date": d_as_of.isoformat(),
            "balance_as_per_books": str(book_balance),
            "additions": {
                "unpresented_payments": {
                    "total": str(tot_unpresented),
                    "count": len(unpresented_payments_list),
                    "items": unpresented_payments_list,
                    "description": "Cheques issued / outward payments recorded in books but not yet presented/cleared in bank."
                },
                "unrecorded_bank_credits": {
                    "total": str(tot_unrecorded_credits),
                    "count": len(unrecorded_bank_credits_list),
                    "items": unrecorded_bank_credits_list,
                    "description": "Direct customer deposits / interest credited by bank but not yet entered in books."
                },
                "total_additions": str(tot_unpresented + tot_unrecorded_credits)
            },
            "deductions": {
                "uncleared_deposits": {
                    "total": str(tot_uncleared),
                    "count": len(uncleared_deposits_list),
                    "items": uncleared_deposits_list,
                    "description": "Cheques received / inward receipts recorded in books but not yet credited/cleared by bank."
                },
                "unrecorded_bank_debits": {
                    "total": str(tot_unrecorded_debits),
                    "count": len(unrecorded_bank_debits_list),
                    "items": unrecorded_bank_debits_list,
                    "description": "Bank charges / direct debits processed by bank but not yet entered in books."
                },
                "total_deductions": str(tot_uncleared + tot_unrecorded_debits)
            },
            "reconciled_balance": str(reconciled_balance),
            "actual_statement_balance": str(statement_balance) if statement_balance is not None else None,
            "variance": str(variance) if variance is not None else None,
            "is_reconciled": is_reconciled,
            "reconciliation_status": reconciliation_status
        }

    @classmethod
    @transaction.atomic
    def unreconcile_transaction(cls, bank_tx: BankTransaction, reason: str = "User un-reconciled transaction", user=None) -> Dict[str, Any]:
        """
        Un-reconciles a reconciled bank transaction without mutating imported bank evidence.
        - Concurrency safety: Acquires row-level lock on bank_tx using select_for_update().
        - Closed financial period check: Prevents modification of closed periods.
        - Atomic financial reversal: If voucher cancellation/reversal fails, the operation raises
          and aborts entirely without modifying bank transaction status or detaching vouchers.
        - Preserves immutable bank evidence (debit_amount, credit_amount, raw amounts).
        - Records complete audit trail with reversal details.
        """
        # P0 Concurrency & Integrity: Acquire exclusive row lock
        bank_tx = BankTransaction.objects.select_for_update().get(id=bank_tx.id)
        if bank_tx.status != 'RECONCILED':
            return {"status": "NOOP", "message": "Transaction is not currently reconciled."}

        # Closed accounting period protection
        fy = InvoiceSequenceService.get_or_create_active_fy(bank_tx.company, bank_tx.transaction_date)
        if fy and fy.is_closed:
            raise ValidationError(
                f"Accounting period {fy.code} is closed. Cannot unreconcile transactions in a closed period."
            )

        notes = bank_tx.match_notes if isinstance(bank_tx.match_notes, dict) else {}
        is_existing_matched = notes.get('is_existing_matched', False)

        vch = bank_tx.matched_voucher
        vch_num = vch.voucher_number if vch else None
        reversal_voucher = None

        if vch and not is_existing_matched:
            vch = Voucher.objects.select_for_update().get(id=vch.id)
            if vch.status == 'POSTED':
                # Attempt safe cancellation; if voucher cannot be cancelled directly, create an auditable reversal
                try:
                    VoucherService.cancel_voucher(vch, user=user)
                except Exception as cancel_err:
                    logger.info(f"Direct cancellation failed on unreconcile ({cancel_err}); creating explicit reversal voucher...")
                    reversal_voucher = VoucherService.create_reversal_voucher(
                        voucher=vch,
                        user=user,
                        reason=f"Unreconcile bank transaction: {reason}"
                    )
        elif vch and is_existing_matched:
            logger.info(f"Unlinking pre-existing manual voucher #{vch.voucher_number} from bank transaction without cancellation/reversal.")

        bank_tx.matched_voucher = None
        bank_tx.matched_party = None
        bank_tx.matched_invoice = None
        bank_tx.status = 'UNRESOLVED'
        bank_tx.user_classification = ''
        bank_tx.is_refund = False
        notes.pop('is_existing_matched', None)
        notes.setdefault('interpretation_history', []).append({
            'timestamp': timezone.now().isoformat(),
            'action_type': 'UNRECONCILE',
            'reason': reason,
            'reversed_voucher_number': vch_num,
            'reversal_voucher_number': reversal_voucher.voucher_number if reversal_voucher else None,
            'user': user.email if user else 'SYSTEM'
        })
        bank_tx.match_notes = notes
        bank_tx.save(update_fields=['matched_voucher', 'matched_party', 'matched_invoice', 'status', 'user_classification', 'is_refund', 'match_notes', 'updated_at'])

        AuditService.log_action(
            company=bank_tx.company,
            user=user,
            action='UPDATE',
            model_name='BankReconciliation',
            record_id=bank_tx.id,
            changes={
                "action": "UNRECONCILE",
                "reason": reason,
                "reversed_voucher_number": vch_num,
                "reversal_voucher_number": reversal_voucher.voucher_number if reversal_voucher else None
            }
        )

        return {
            "status": "SUCCESS",
            "message": f"Transaction '{bank_tx.description}' successfully un-reconciled.",
            "transaction_id": str(bank_tx.id),
            "reversal_voucher_number": reversal_voucher.voucher_number if reversal_voucher else None
        }

    @classmethod
    @transaction.atomic
    def exclude_transaction(cls, bank_tx: BankTransaction, reason: str = "User excluded from books", user=None) -> Dict[str, Any]:
        """
        Audited, non-destructive exclusion of a bank transaction.
        If the transaction generated a posted voucher, canonically reverses it using VoucherService.create_reversal_voucher.
        """
        if not reason or not str(reason).strip():
            raise ValidationError("A meaningful reason is required to exclude a bank transaction from reconciliation.")

        clean_reason = str(reason).strip()
        bank_tx = BankTransaction.objects.select_for_update().get(id=bank_tx.id)

        reversal_voucher = None
        if bank_tx.matched_voucher:
            vch = Voucher.objects.select_for_update().get(id=bank_tx.matched_voucher_id)
            if vch.status in ['POSTED', 'VALIDATING']:
                reversal_voucher = VoucherService.create_reversal_voucher(
                    voucher=vch,
                    user=user,
                    reason=f"Bank transaction excluded: {clean_reason}"
                )

        bank_tx.is_excluded = True
        bank_tx.status = 'EXCLUDED'
        bank_tx.exclusion_reason = clean_reason
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
        if not reason or not str(reason).strip():
            raise ValidationError("A meaningful reason is required to exclude a bank statement import.")
        statement_import = BankStatementImport.objects.select_for_update().get(id=statement_import.id)
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
    def restore_transaction(cls, bank_tx: BankTransaction, user=None) -> Dict[str, Any]:
        """
        Audited restoration of a previously excluded bank transaction.
        """
        if not bank_tx.is_excluded:
            return {
                "status": "SUCCESS",
                "message": "Transaction is already active in books."
            }

        bank_tx.is_excluded = False
        bank_tx.status = 'UNRESOLVED'
        bank_tx.exclusion_reason = None
        bank_tx.excluded_at = None
        bank_tx.excluded_by = None
        bank_tx.save(update_fields=['is_excluded', 'status', 'exclusion_reason', 'excluded_at', 'excluded_by', 'updated_at'])

        AuditService.log_action(
            company=bank_tx.company,
            user=user,
            action='RESTORE',
            model_name='BankTransaction',
            record_id=bank_tx.id,
            changes={"status": "UNRESOLVED", "is_excluded": False}
        )
        return {
            "status": "SUCCESS",
            "message": "Transaction restored to books."
        }

    @classmethod
    @transaction.atomic
    def restore_statement_import(cls, statement_import: BankStatementImport, user=None) -> int:
        """
        Audited restoration of a previously excluded statement import and all associated transactions.
        """
        txs = list(statement_import.transactions.filter(is_excluded=True))
        count = 0
        for tx in txs:
            cls.restore_transaction(tx, user=user)
            count += 1

        statement_import.is_excluded = False
        statement_import.exclusion_reason = None
        statement_import.excluded_at = None
        statement_import.excluded_by = None
        statement_import.save(update_fields=['is_excluded', 'exclusion_reason', 'excluded_at', 'excluded_by'])

        AuditService.log_action(
            company=statement_import.company,
            user=user,
            action='RESTORE',
            model_name='BankStatementImport',
            record_id=statement_import.id,
            changes={"restored_count": count, "is_excluded": False}
        )
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

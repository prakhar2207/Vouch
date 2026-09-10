import datetime
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear
from apps.audit.services.audit_service import AuditService

class OpeningBalanceService:
    @staticmethod
    def get_or_create_opening_adjustment_ledger(company: Company) -> Ledger:
        """
        Retrieves or initializes the canonical double-entry equity balancing account:
        'Opening Balance Adjustment' (Nature: EQUITY).
        """
        equity_group = LedgerGroup.objects.filter(company=company, nature='EQUITY').first()
        if not equity_group:
            equity_group = LedgerGroup.objects.filter(company=company, name__icontains='Capital').first()
        if not equity_group:
            equity_group = LedgerGroup.objects.create(
                company=company,
                name="Equity Accounts",
                nature="EQUITY"
            )
            
        adj_ledger = Ledger.objects.filter(
            company=company,
            name__iexact="Opening Balance Adjustment"
        ).first()
        if not adj_ledger:
            adj_ledger = Ledger.objects.create(
                company=company,
                group=equity_group,
                name="Opening Balance Adjustment",
                ledger_type="EQUITY",
                opening_balance_type="CREDIT"
            )
        elif adj_ledger.opening_balance_type != 'CREDIT':
            adj_ledger.opening_balance_type = 'CREDIT'
            adj_ledger.save(update_fields=['opening_balance_type'])
        return adj_ledger

    @classmethod
    @transaction.atomic
    def record_opening_balance(
        cls,
        ledger: Ledger,
        amount: Decimal,
        balance_type: str,
        opening_date: datetime.date = None,
        pending_invoices: list = None,
        user=None
    ):
        """
        Records the opening balance for a party using rigorous double-entry accounting.
        If pending_invoices is provided, creates individual OPENING_INVOICE / OPENING_BILL vouchers
        whose sum must equal the opening balance.
        Otherwise creates a single OPENING voucher.
        """
        amount = Decimal(str(amount or '0.00'))
        balance_type = (balance_type or 'DEBIT').upper()
        if balance_type not in ['DEBIT', 'CREDIT']:
            balance_type = 'DEBIT'
            
        company = ledger.company
        if not opening_date:
            active_fy = FinancialYear.objects.filter(company=company, is_closed=False).order_by('-start_date').first()
            if active_fy:
                opening_date = active_fy.start_date
            else:
                today = timezone.now().date()
                year = today.year if today.month >= 4 else today.year - 1
                opening_date = datetime.date(year, 4, 1)
        elif isinstance(opening_date, str):
            opening_date = datetime.date.fromisoformat(opening_date.split('T')[0])

        ledger.opening_balance = amount
        ledger.opening_balance_type = balance_type
        ledger.opening_date = opening_date
        ledger.save(update_fields=['opening_balance', 'opening_balance_type', 'opening_date'])

        from apps.accounting.services.sequence_service import InvoiceSequenceService
        fy = InvoiceSequenceService.get_or_create_active_fy(company, opening_date)
        
        if amount == Decimal('0.00'):
            from apps.accounting.services.voucher_service import VoucherService
            VoucherService.recalculate_ledger_balance(ledger)
            return []

        adj_ledger = cls.get_or_create_opening_adjustment_ledger(company)
        created_vouchers = []
        
        if pending_invoices and len(pending_invoices) > 0:
            invoices_total = sum(Decimal(str(item.get('amount', 0))) for item in pending_invoices)
            if invoices_total != amount:
                diff = abs(amount - invoices_total)
                raise ValidationError(
                    f"You entered ₹{invoices_total} in invoices/bills, but opening balance is ₹{amount}. Difference: ₹{diff}."
                )

            is_customer = (ledger.canonical_role == 'CUSTOMER') or (balance_type == 'DEBIT')
            v_type = 'OPENING_INVOICE' if is_customer else 'OPENING_BILL'
            
            for idx, item in enumerate(pending_invoices):
                item_amt = Decimal(str(item.get('amount', 0)))
                if item_amt <= Decimal('0.00'):
                    continue
                inv_num = str(item.get('invoice_number') or item.get('bill_number') or f"OP-{ledger.name[:4]}-{idx+1}").strip()
                item_date = item.get('voucher_date') or item.get('date') or opening_date
                if isinstance(item_date, str):
                    item_date = datetime.date.fromisoformat(item_date.split('T')[0])
                due_d = item.get('due_date') or item_date
                if isinstance(due_d, str):
                    due_d = datetime.date.fromisoformat(due_d.split('T')[0])
                    
                vch = Voucher.objects.create(
                    company=company,
                    financial_year=fy,
                    voucher_type=v_type,
                    voucher_number=inv_num,
                    voucher_date=item_date,
                    due_date=due_d,
                    party_ledger=ledger,
                    status='POSTED',
                    total_amount=item_amt,
                    narration=f"Opening {'Invoice' if is_customer else 'Bill'} {inv_num} for {ledger.name}",
                    created_by=user
                )
                
                if balance_type == 'DEBIT':
                    LedgerEntry.objects.create(
                        company=company,
                        voucher=vch,
                        ledger=ledger,
                        debit_amount=item_amt,
                        credit_amount=Decimal('0.00'),
                        narration=f"Opening receivable {inv_num}"
                    )
                    LedgerEntry.objects.create(
                        company=company,
                        voucher=vch,
                        ledger=adj_ledger,
                        debit_amount=Decimal('0.00'),
                        credit_amount=item_amt,
                        narration=f"Opening balance offset for {ledger.name} ({inv_num})"
                    )
                else:
                    LedgerEntry.objects.create(
                        company=company,
                        voucher=vch,
                        ledger=adj_ledger,
                        debit_amount=item_amt,
                        credit_amount=Decimal('0.00'),
                        narration=f"Opening balance offset for {ledger.name} ({inv_num})"
                    )
                    LedgerEntry.objects.create(
                        company=company,
                        voucher=vch,
                        ledger=ledger,
                        debit_amount=Decimal('0.00'),
                        credit_amount=item_amt,
                        narration=f"Opening payable {inv_num}"
                    )
                created_vouchers.append(vch)
        else:
            v_num = f"OP-{str(ledger.id)[:8].upper()}"
            if Voucher.objects.filter(company=company, voucher_number=v_num).exists():
                v_num = f"{v_num}-{int(timezone.now().timestamp()) % 10000}"

            vch = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type='OPENING',
                voucher_number=v_num,
                voucher_date=opening_date,
                due_date=opening_date,
                party_ledger=ledger,
                status='POSTED',
                total_amount=amount,
                narration=f"Opening Balance for {ledger.name}",
                created_by=user
            )
            
            if balance_type == 'DEBIT':
                LedgerEntry.objects.create(
                    company=company,
                    voucher=vch,
                    ledger=ledger,
                    debit_amount=amount,
                    credit_amount=Decimal('0.00'),
                    narration=f"Opening Balance Dr for {ledger.name}"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=vch,
                    ledger=adj_ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=amount,
                    narration=f"Opening balance offset for {ledger.name}"
                )
            else:
                LedgerEntry.objects.create(
                    company=company,
                    voucher=vch,
                    ledger=adj_ledger,
                    debit_amount=amount,
                    credit_amount=Decimal('0.00'),
                    narration=f"Opening balance offset for {ledger.name}"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=vch,
                    ledger=ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=amount,
                    narration=f"Opening Balance Cr for {ledger.name}"
                )
            created_vouchers.append(vch)

        from apps.accounting.services.voucher_service import VoucherService
        VoucherService.recalculate_ledger_balance(ledger)
        VoucherService.recalculate_ledger_balance(adj_ledger)

        AuditService.log_action(
            company=company,
            user=user,
            action='CREATE',
            model_name='LedgerOpeningBalance',
            record_id=ledger.id,
            changes={
                'party': ledger.name,
                'opening_balance': str(amount),
                'opening_balance_type': balance_type,
                'opening_date': str(opening_date),
                'vouchers_created': [v.voucher_number for v in created_vouchers]
            }
        )
        return created_vouchers

    @classmethod
    @transaction.atomic
    def adjust_opening_balance(
        cls,
        ledger: Ledger,
        new_amount: Decimal,
        new_balance_type: str = None,
        user=None,
        reason: str = "Opening balance correction"
    ):
        """
        Edits an existing ledger's opening balance:
        - If no subsequent non-opening transactions exist: direct safe update.
        - If subsequent transactions exist: generates an explicit differential Journal Voucher
          and preserves full audit history.
        """
        new_amount = Decimal(str(new_amount or '0.00'))
        if not new_balance_type:
            new_balance_type = ledger.opening_balance_type or 'DEBIT'
        new_balance_type = new_balance_type.upper()

        old_amount = Decimal(str(ledger.opening_balance or '0.00'))
        old_type = ledger.opening_balance_type or 'DEBIT'
        company = ledger.company

        # Check if non-opening transactions exist
        has_subsequent = LedgerEntry.objects.filter(
            ledger=ledger,
            voucher__status='POSTED'
        ).exclude(
            voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
        ).exists()

        if not has_subsequent:
            # Safe direct update: delete old opening vouchers and recreate
            old_opening_vouchers = list(Voucher.objects.filter(
                party_ledger=ledger,
                voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL'],
                company=company
            ))
            for ov in old_opening_vouchers:
                ov.ledger_entries.all().delete()
                ov.delete()

            return cls.record_opening_balance(
                ledger=ledger,
                amount=new_amount,
                balance_type=new_balance_type,
                opening_date=ledger.opening_date,
                user=user
            )

        # Subsequent transactions exist: Create differential adjustment
        net_old = old_amount if old_type == 'DEBIT' else -old_amount
        net_new = new_amount if new_balance_type == 'DEBIT' else -new_amount
        diff = net_new - net_old

        if diff != Decimal('0.00'):
            from apps.accounting.services.sequence_service import InvoiceSequenceService
            adj_date = timezone.now().date()
            fy = InvoiceSequenceService.get_or_create_active_fy(company, adj_date)
            adj_ledger = cls.get_or_create_opening_adjustment_ledger(company)

            v_num = f"ADJ-OP-{str(ledger.id)[:6].upper()}-{int(timezone.now().timestamp()) % 10000}"
            adj_voucher = Voucher.objects.create(
                company=company,
                financial_year=fy,
                voucher_type='JOURNAL',
                voucher_number=v_num,
                voucher_date=adj_date,
                due_date=adj_date,
                party_ledger=ledger,
                status='POSTED',
                total_amount=abs(diff),
                narration=f"Differential Opening Balance Adjustment for {ledger.name}: {reason}",
                correction_reason=reason,
                correction_type='PAYMENT',
                created_by=user
            )

            if diff > Decimal('0.00'):
                # Net increase in Debit (Customer owes more)
                LedgerEntry.objects.create(
                    company=company,
                    voucher=adj_voucher,
                    ledger=ledger,
                    debit_amount=abs(diff),
                    credit_amount=Decimal('0.00'),
                    narration=f"Opening balance differential Dr adjustment ({reason})"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=adj_voucher,
                    ledger=adj_ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=abs(diff),
                    narration=f"Opening balance differential Cr offset ({reason})"
                )
            else:
                # Net increase in Credit (Supplier owed more or customer overpaid)
                LedgerEntry.objects.create(
                    company=company,
                    voucher=adj_voucher,
                    ledger=adj_ledger,
                    debit_amount=abs(diff),
                    credit_amount=Decimal('0.00'),
                    narration=f"Opening balance differential Dr offset ({reason})"
                )
                LedgerEntry.objects.create(
                    company=company,
                    voucher=adj_voucher,
                    ledger=ledger,
                    debit_amount=Decimal('0.00'),
                    credit_amount=abs(diff),
                    narration=f"Opening balance differential Cr adjustment ({reason})"
                )

            from apps.accounting.services.voucher_service import VoucherService
            VoucherService.recalculate_ledger_balance(adj_ledger)

        ledger.opening_balance = new_amount
        ledger.opening_balance_type = new_balance_type
        ledger.save(update_fields=['opening_balance', 'opening_balance_type'])

        from apps.accounting.services.voucher_service import VoucherService
        VoucherService.recalculate_ledger_balance(ledger)

        AuditService.log_action(
            company=company,
            user=user,
            action='UPDATE',
            model_name='LedgerOpeningBalance',
            record_id=ledger.id,
            changes={
                'party': ledger.name,
                'old_opening_balance': str(old_amount),
                'old_opening_type': old_type,
                'new_opening_balance': str(new_amount),
                'new_opening_type': new_balance_type,
                'difference': str(diff),
                'reason': reason
            }
        )
        return ledger

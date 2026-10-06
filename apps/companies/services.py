import logging
from decimal import Decimal
from apps.ledgers.models import Ledger, LedgerGroup

logger = logging.getLogger(__name__)

class CompanyBankService:
    @staticmethod
    def sync_company_bank_ledger(company):
        """
        Automatically provisions or updates a Bank Account ledger for the company
        whenever bank details (bank_name, bank_account_number, bank_ifsc, upi_id)
        are added or modified.
        
        This guarantees that the company immediately has a Bank Ledger in Chart of Accounts
        for statement reconciliation, banking transaction matching, and dynamic QR invoicing,
        eliminating the need to manually create a bank account ledger.
        """
        bank_name = str(company.bank_name or '').strip()
        account_number = str(company.bank_account_number or '').strip()
        bank_ifsc = str(company.bank_ifsc or '').strip().upper()
        upi_id = str(company.upi_id or '').strip()

        # If no bank name and no account number, nothing to sync
        if not bank_name and not account_number:
            return None

        # 1. Ensure 'Bank Accounts' ledger group exists
        bank_grp, _ = LedgerGroup.objects.get_or_create(
            company=company,
            name="Bank Accounts",
            defaults={"nature": "ASSET"}
        )

        # 2. Determine canonical display name
        if bank_name and account_number:
            last4 = account_number[-4:] if len(account_number) >= 4 else account_number
            canonical_name = f"{bank_name} (A/c ...{last4})"
        elif bank_name:
            canonical_name = bank_name
        else:
            last4 = account_number[-4:] if len(account_number) >= 4 else account_number
            canonical_name = f"Bank Account (A/c ...{last4})"

        # 3. Search for existing bank ledger
        ledger = None

        # A. Match by exact account number
        if account_number:
            ledger = Ledger.objects.filter(
                company=company,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'],
                bank_account_number__iexact=account_number
            ).first()

        # B. Match by exact or normalized canonical name
        if not ledger:
            ledger = Ledger.objects.filter(
                company=company,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'],
                name__iexact=canonical_name
            ).first()

        # C. Match by bank_name if existing bank ledger has empty account number
        if not ledger and bank_name:
            candidates = Ledger.objects.filter(
                company=company,
                ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC']
            )
            for cand in candidates:
                if (bank_name.lower() in cand.name.lower() or cand.name.lower() in bank_name.lower()) and not cand.bank_account_number:
                    ledger = cand
                    break

            # If still not found and exactly one bank ledger exists with empty/generic info
            if not ledger and candidates.count() == 1:
                single_cand = candidates.first()
                if not single_cand.bank_account_number or single_cand.name.strip().lower() in ['bank', 'bank account', 'bank a/c']:
                    ledger = single_cand

        # 4. Update or Create
        if ledger:
            updated_fields = []
            if account_number and ledger.bank_account_number != account_number:
                ledger.bank_account_number = account_number
                updated_fields.append('bank_account_number')
            if bank_ifsc and ledger.bank_ifsc != bank_ifsc:
                ledger.bank_ifsc = bank_ifsc
                updated_fields.append('bank_ifsc')
            if upi_id and ledger.upi_id != upi_id:
                ledger.upi_id = upi_id
                updated_fields.append('upi_id')
            if not ledger.is_active:
                ledger.is_active = True
                updated_fields.append('is_active')
            if ledger.is_archived:
                ledger.is_archived = False
                updated_fields.append('is_archived')

            # Upgrade generic names to canonical formatted name
            if ledger.name.strip().lower() in ['bank', 'bank account', 'bank a/c', 'main bank']:
                if not Ledger.objects.filter(company=company, name__iexact=canonical_name).exclude(id=ledger.id).exists():
                    ledger.name = canonical_name
                    updated_fields.append('name')
            elif bank_name and canonical_name and (ledger.name.strip().lower() == bank_name.lower()) and account_number:
                if not Ledger.objects.filter(company=company, name__iexact=canonical_name).exclude(id=ledger.id).exists():
                    ledger.name = canonical_name
                    updated_fields.append('name')

            if updated_fields:
                ledger.save(update_fields=updated_fields)
            return ledger
        else:
            # Check if an existing ledger with the exact canonical name exists under another type
            existing_named = Ledger.objects.filter(company=company, name__iexact=canonical_name).first()
            if existing_named:
                existing_named.ledger_type = 'BANK'
                existing_named.group = bank_grp
                existing_named.bank_account_number = account_number
                existing_named.bank_ifsc = bank_ifsc
                existing_named.upi_id = upi_id
                existing_named.is_active = True
                existing_named.is_archived = False
                existing_named.save()
                return existing_named

            # Create brand new bank ledger
            new_ledger = Ledger.objects.create(
                company=company,
                group=bank_grp,
                name=canonical_name,
                ledger_type='BANK',
                bank_account_number=account_number,
                bank_ifsc=bank_ifsc,
                upi_id=upi_id,
                opening_balance=Decimal('0.00'),
                opening_balance_type='DEBIT',
                is_active=True,
                is_archived=False
            )
            return new_ledger

from decimal import Decimal

class PartyBalanceService:
    @staticmethod
    def get_party_balance(ledger) -> dict:
        """
        Canonical party balance projection based on `ledger.current_balance` 
        and `ledger.canonical_role`.
        """
        raw_bal = Decimal(str(ledger.current_balance or '0.00'))
        role = ledger.canonical_role
        
        # Convert raw_bal (which is relative to opening_balance_type) 
        # to absolute debits minus credits (net debit).
        if ledger.opening_balance_type == 'DEBIT':
            net_dr = raw_bal
        else:
            net_dr = -raw_bal

        # Now compute canonical signed balance
        if role == 'CUSTOMER':
            signed_bal = net_dr
            state = 'TO_COLLECT' if signed_bal > 0 else 'ADVANCE_RECEIVED'
        elif role == 'SUPPLIER':
            signed_bal = -net_dr
            state = 'TO_PAY' if signed_bal > 0 else 'ADVANCE_PAID'
        else:
            signed_bal = net_dr
            state = 'TO_COLLECT' if signed_bal > 0 else 'TO_PAY'
            
        if signed_bal == Decimal('0.00'):
            state = 'SETTLED'
            
        return {
            'signed_balance': signed_bal,
            'display_amount': abs(signed_bal),
            'balance_state': state,
            'balance_direction': 'DEBIT' if net_dr > 0 else ('CREDIT' if net_dr < 0 else 'NONE')
        }

    @staticmethod
    def get_balance_direction(ledger, bal: Decimal) -> str:
        # Compatibility fallback for old code if any
        if bal == Decimal('0.00'):
            return 'NONE'
        if ledger.opening_balance_type == 'DEBIT':
            return 'DEBIT' if bal > 0 else 'CREDIT'
        else:
            return 'CREDIT' if bal > 0 else 'DEBIT'

    @staticmethod
    def get_balance_from_components(role: str, debit: Decimal, credit: Decimal) -> dict:
        """
        Calculate canonical balance directly from raw debits and credits.
        """
        debit = Decimal(str(debit or '0.00'))
        credit = Decimal(str(credit or '0.00'))
        net_dr = debit - credit
        
        if role == 'CUSTOMER':
            bal = net_dr
            state = 'TO_COLLECT' if bal > 0 else 'ADVANCE_RECEIVED'
            if bal == Decimal('0.00'): state = 'SETTLED'
        elif role == 'SUPPLIER':
            bal = -net_dr
            state = 'TO_PAY' if bal > 0 else 'ADVANCE_PAID'
            if bal == Decimal('0.00'): state = 'SETTLED'
        else:
            bal = net_dr
            state = 'TO_COLLECT' if bal > 0 else 'TO_PAY'
            if bal == Decimal('0.00'): state = 'SETTLED'
            
        direction = 'NONE'
        if net_dr > 0: direction = 'DEBIT'
        elif net_dr < 0: direction = 'CREDIT'
            
        return {
            'signed_balance': bal,
            'display_amount': abs(bal),
            'balance_state': state,
            'balance_direction': direction
        }

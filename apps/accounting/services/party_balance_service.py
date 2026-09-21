from decimal import Decimal

class PartyBalanceService:
    @staticmethod
    def get_party_balance(ledger) -> dict:
        """
        Canonical party balance projection based on `ledger.current_balance`,
        `ledger.canonical_role`, and `ledger.normal_balance`.
        """
        raw_bal = Decimal(str(ledger.current_balance or '0.00'))
        role = getattr(ledger, 'canonical_role', 'OTHER')
        normal_bal = getattr(ledger, 'normal_balance', 'DEBIT')
        
        # Calculate net_dr (Debit minus Credit)
        if normal_bal == 'CREDIT':
            # current_balance = Cr - Dr, so net_dr = -(Cr - Dr) = -raw_bal
            net_dr = -raw_bal
            signed_bal = raw_bal
        else:
            # current_balance = Dr - Cr, so net_dr = raw_bal
            net_dr = raw_bal
            signed_bal = raw_bal

        if role == 'CUSTOMER':
            if signed_bal > 0:
                state = 'TO_COLLECT'
            elif signed_bal < 0:
                state = 'ADVANCE_RECEIVED'
            else:
                state = 'SETTLED'
        elif role == 'SUPPLIER':
            if signed_bal > 0:
                state = 'TO_PAY'
            elif signed_bal < 0:
                state = 'ADVANCE_PAID'
            else:
                state = 'SETTLED'
        else:
            if signed_bal == Decimal('0.00'):
                state = 'SETTLED'
            elif net_dr > 0:
                state = 'DR'
            else:
                state = 'CR'

        disp_amt = abs(signed_bal)
        if state == 'TO_COLLECT':
            explanation = f"This customer owes you ₹{disp_amt:,.2f}"
            owner_headline = "TO COLLECT"
        elif state == 'TO_PAY':
            explanation = f"You owe this supplier ₹{disp_amt:,.2f}"
            owner_headline = "YOU NEED TO PAY"
        elif state == 'ADVANCE_RECEIVED':
            explanation = f"Customer has paid ₹{disp_amt:,.2f} more than billed"
            owner_headline = "ADVANCE RECEIVED"
        elif state == 'ADVANCE_PAID':
            explanation = f"You have paid ₹{disp_amt:,.2f} more than billed"
            owner_headline = "ADVANCE PAID"
        elif state == 'DR':
            owner_headline = "DEBIT BALANCE"
            explanation = f"Account balance is ₹{disp_amt:,.2f} Dr"
        elif state == 'CR':
            if normal_bal == 'DEBIT':
                owner_headline = "OVERDRAWN (CR)"
                explanation = f"Account is overdrawn by ₹{disp_amt:,.2f} (recorded outflows exceed inflows)"
            else:
                owner_headline = "CREDIT BALANCE"
                explanation = f"Account balance is ₹{disp_amt:,.2f} Cr"
        else:
            explanation = "Nothing outstanding. Balance is ₹0.00."
            owner_headline = "SETTLED"

        return {
            'signed_balance': signed_bal,
            'display_amount': disp_amt,
            'display_balance': disp_amt,
            'balance_state': state,
            'state': state,
            'owner_headline': owner_headline,
            'explanation': explanation,
            'normal_balance_type': normal_bal,
            'normal_balance': normal_bal,
            'balance_direction': 'DEBIT' if net_dr > 0 else ('CREDIT' if net_dr < 0 else 'NONE'),
            'canonical_role': role,
            'is_payable': (state == 'TO_PAY'),
            'is_receivable': (state == 'TO_COLLECT'),
        }

    @staticmethod
    def get_balance_direction(ledger, bal: Decimal) -> str:
        if bal == Decimal('0.00'):
            return 'NONE'
        normal_bal = getattr(ledger, 'normal_balance', 'DEBIT')
        if normal_bal == 'DEBIT':
            return 'DEBIT' if bal > 0 else 'CREDIT'
        else:
            return 'CREDIT' if bal > 0 else 'DEBIT'

    @staticmethod
    def get_balance_from_components(role: str, debit: Decimal, credit: Decimal, normal_balance: str = None) -> dict:
        """
        Calculate canonical balance directly from raw debits and credits.
        """
        debit = Decimal(str(debit or '0.00'))
        credit = Decimal(str(credit or '0.00'))
        net_dr = debit - credit
        
        if not normal_balance:
            if role == 'SUPPLIER':
                normal_balance = 'CREDIT'
            else:
                normal_balance = 'DEBIT'
                
        if role == 'CUSTOMER':
            signed_bal = net_dr
            if signed_bal > 0:
                state = 'TO_COLLECT'
            elif signed_bal < 0:
                state = 'ADVANCE_RECEIVED'
            else:
                state = 'SETTLED'
        elif role == 'SUPPLIER':
            signed_bal = -net_dr  # credits - debits
            if signed_bal > 0:
                state = 'TO_PAY'
            elif signed_bal < 0:
                state = 'ADVANCE_PAID'
            else:
                state = 'SETTLED'
        else:
            if normal_balance == 'CREDIT':
                signed_bal = -net_dr
                state = 'CR' if signed_bal > 0 else ('DR' if signed_bal < 0 else 'SETTLED')
            else:
                signed_bal = net_dr
                state = 'DR' if signed_bal > 0 else ('CR' if signed_bal < 0 else 'SETTLED')
            
        disp_amt = abs(signed_bal)
        if state == 'TO_COLLECT':
            explanation = f"This customer owes you ₹{disp_amt:,.2f}"
            owner_headline = "TO COLLECT"
        elif state == 'TO_PAY':
            explanation = f"You owe this supplier ₹{disp_amt:,.2f}"
            owner_headline = "YOU NEED TO PAY"
        elif state == 'ADVANCE_RECEIVED':
            explanation = f"Customer has paid ₹{disp_amt:,.2f} more than billed"
            owner_headline = "ADVANCE RECEIVED"
        elif state == 'ADVANCE_PAID':
            explanation = f"You have paid ₹{disp_amt:,.2f} more than billed"
            owner_headline = "ADVANCE PAID"
        elif state == 'DR':
            owner_headline = "DEBIT BALANCE"
            explanation = f"Account balance is ₹{disp_amt:,.2f} Dr"
        elif state == 'CR':
            if normal_balance == 'DEBIT':
                owner_headline = "OVERDRAWN (CR)"
                explanation = f"Account is overdrawn by ₹{disp_amt:,.2f} (recorded outflows exceed inflows)"
            else:
                owner_headline = "CREDIT BALANCE"
                explanation = f"Account balance is ₹{disp_amt:,.2f} Cr"
        else:
            explanation = "Nothing outstanding. Balance is ₹0.00."
            owner_headline = "SETTLED"

        direction = 'NONE'
        if net_dr > 0:
            direction = 'DEBIT'
        elif net_dr < 0:
            direction = 'CREDIT'
            
        return {
            'signed_balance': signed_bal,
            'display_amount': disp_amt,
            'display_balance': disp_amt,
            'balance_state': state,
            'state': state,
            'owner_headline': owner_headline,
            'explanation': explanation,
            'normal_balance_type': normal_balance,
            'normal_balance': normal_balance,
            'balance_direction': direction,
            'canonical_role': role,
            'is_payable': (state == 'TO_PAY'),
            'is_receivable': (state == 'TO_COLLECT'),
        }

    get_party_balance_interpretation = get_party_balance


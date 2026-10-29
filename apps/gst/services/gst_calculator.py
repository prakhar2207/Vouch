from decimal import Decimal
import re
from rest_framework.exceptions import ValidationError

VALID_GST_STATE_CODES = {
    '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '21', '22', '23', '24', '25', '26', '27', '28', '29', '30',
    '31', '32', '33', '34', '35', '36', '37', '38',
    '97',  # Other Territory
    '99',  # Centre / Special Economic Zone / Non-resident
}

class GSTCalculator:
    @staticmethod
    def calculate_taxes(
        company_state_code: str, 
        party_state_code: str, 
        taxable_amount: Decimal, 
        gst_rate: Decimal,
        is_exempt: bool = False,
        is_nil_rated: bool = False,
        is_zero_rated: bool = False,
        is_sez: bool = False,
        is_rcm: bool = False,
        cess_rate: Decimal = Decimal('0.00'),
        place_of_supply: str = None,
        pos_source: str = None
    ) -> dict:
        """
        Authoritative GST Calculation Engine.
        Determines intrastate (CGST+SGST) vs interstate (IGST) accurately.
        Fail-closed: Never silently assumes or guesses missing state codes for taxable transactions.

        Returns:
            dict with rates and amounts for CGST, SGST, IGST, Cess, Total Tax, and audit metadata.
        """
        taxable_amount = Decimal(str(taxable_amount or '0.00'))
        gst_rate = Decimal(str(gst_rate or '0.00'))
        cess_rate = Decimal(str(cess_rate or '0.00'))

        # Special tax treatments: Exempt, Nil-rated, Zero-rated
        if is_exempt or is_nil_rated or is_zero_rated:
            return {
                'cgst_rate': Decimal('0.00'),
                'sgst_rate': Decimal('0.00'),
                'igst_rate': Decimal('0.00'),
                'cess_rate': Decimal('0.00'),
                'cgst': Decimal('0.00'),
                'sgst': Decimal('0.00'),
                'igst': Decimal('0.00'),
                'cess': Decimal('0.00'),
                'total_tax': Decimal('0.00'),
                'treatment': 'EXEMPT' if is_exempt else ('NIL_RATED' if is_nil_rated else 'ZERO_RATED'),
                'seller_state': str(company_state_code or '').strip(),
                'buyer_state': str(place_of_supply or party_state_code or '').strip(),
                'pos_source': pos_source or 'TAX_EXEMPT_SPECIAL_TREATMENT'
            }

        c_state = (company_state_code or '').strip()
        p_state = (place_of_supply or party_state_code or '').strip()

        # Fail-closed validation for taxable transactions:
        # Neither seller location nor buyer place of supply may be omitted or silently guessed.
        if gst_rate > Decimal('0.00'):
            if not c_state and not p_state:
                raise ValidationError(
                    "GST calculation failed: Both seller and buyer state codes are missing for taxable transaction. Place of supply cannot be determined."
                )
            if not c_state:
                raise ValidationError(
                    "GST calculation failed: Seller/Company state code is missing. Authoritative supplier location is required for taxable supplies."
                )
            if not p_state:
                raise ValidationError(
                    "GST calculation failed: Buyer state code / Place of Supply (POS) is missing. Place of supply is legally required to determine IGST vs CGST/SGST."
                )

            # Normalize to 2-digit format (e.g., '9' -> '09')
            if c_state.isdigit() and len(c_state) < 2:
                c_state = c_state.zfill(2)
            if p_state.isdigit() and len(p_state) < 2:
                p_state = p_state.zfill(2)

            # Validate state code format
            if not re.match(r'^\d{2}$', c_state):
                raise ValidationError(f"Invalid seller GST state code '{c_state}'. Must be a 2-digit numerical code.")
            if not re.match(r'^\d{2}$', p_state):
                raise ValidationError(f"Invalid buyer GST state code '{p_state}'. Must be a 2-digit numerical code.")
        else:
            # 0% / Non-taxable supplies: default to '00' if unsupplied
            c_state = c_state.zfill(2) if c_state.isdigit() else (c_state or '00')
            p_state = p_state.zfill(2) if p_state.isdigit() else (p_state or '00')

        # SEZ supplies are treated as Inter-State (IGST) regardless of state codes
        is_interstate = (c_state != p_state) or is_sez

        cess_amt = (taxable_amount * cess_rate / Decimal('100')).quantize(Decimal('0.01'))

        resolved_pos_source = pos_source or ('EXPLICIT_POS' if place_of_supply else 'PARTY_STATE')

        if is_interstate:
            igst_amt = (taxable_amount * gst_rate / Decimal('100')).quantize(Decimal('0.01'))
            return {
                'cgst_rate': Decimal('0.00'),
                'sgst_rate': Decimal('0.00'),
                'igst_rate': gst_rate,
                'cess_rate': cess_rate,
                'cgst': Decimal('0.00'),
                'sgst': Decimal('0.00'),
                'igst': igst_amt,
                'cess': cess_amt,
                'total_tax': igst_amt + cess_amt,
                'is_rcm': is_rcm,
                'treatment': 'INTERSTATE',
                'seller_state': c_state,
                'buyer_state': p_state,
                'pos_source': resolved_pos_source
            }
        else:
            half_rate = (gst_rate / Decimal('2')).quantize(Decimal('0.01'))
            cgst_amt = (taxable_amount * half_rate / Decimal('100')).quantize(Decimal('0.01'))
            sgst_amt = (taxable_amount * half_rate / Decimal('100')).quantize(Decimal('0.01'))
            return {
                'cgst_rate': half_rate,
                'sgst_rate': half_rate,
                'igst_rate': Decimal('0.00'),
                'cess_rate': cess_rate,
                'cgst': cgst_amt,
                'sgst': sgst_amt,
                'igst': Decimal('0.00'),
                'cess': cess_amt,
                'total_tax': cgst_amt + sgst_amt + cess_amt,
                'is_rcm': is_rcm,
                'treatment': 'INTRASTATE',
                'seller_state': c_state,
                'buyer_state': p_state,
                'pos_source': resolved_pos_source
            }

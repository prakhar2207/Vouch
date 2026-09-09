from decimal import Decimal
from rest_framework.exceptions import ValidationError

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
        cess_rate: Decimal = Decimal('0.00')
    ) -> dict:
        """
        Authoritative GST Calculation Engine.
        Determines intrastate (CGST+SGST) vs interstate (IGST) accurately.
        Never guesses IGST when critical state information is missing.
        Returns:
            dict with rates and amounts for CGST, SGST, IGST, Cess, and Total Tax.
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
                'treatment': 'EXEMPT' if is_exempt else ('NIL_RATED' if is_nil_rated else 'ZERO_RATED')
            }

        c_state = (company_state_code or '').strip()
        p_state = (party_state_code or '').strip()

        # Guard: never guess IGST if state codes are missing
        if not c_state:
            raise ValidationError("Company state code is missing. Cannot reliably determine GST tax treatment.")
        if not p_state:
            # If counter party has no state code provided, do NOT blindly default to IGST
            raise ValidationError(
                "Party/Buyer state code is missing. State code is mandatory under Indian GST "
                "to determine whether CGST+SGST (Intra-state) or IGST (Inter-state) applies."
            )

        # SEZ supplies are treated as Inter-State (IGST) regardless of state codes
        is_interstate = (c_state != p_state) or is_sez

        cess_amt = (taxable_amount * cess_rate / Decimal('100')).quantize(Decimal('0.01'))

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
                'treatment': 'INTERSTATE'
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
                'treatment': 'INTRASTATE'
            }

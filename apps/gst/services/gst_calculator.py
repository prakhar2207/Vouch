from decimal import Decimal

class GSTCalculator:
    @staticmethod
    def calculate_taxes(company_state_code: str, party_state_code: str, taxable_amount: Decimal, gst_rate: Decimal) -> dict:
        """
        Precise GST calculation engine.
        Determines intrastate (CGST+SGST) vs interstate (IGST) based on state codes.
        Rounds to 2 decimal places to match financial constraints.
        """
        taxable_amount = Decimal(str(taxable_amount))
        gst_rate = Decimal(str(gst_rate))
        
        if not company_state_code or not party_state_code:
            # Default to IGST if state codes are missing, to be safe, or could raise Error
            # In a strict B2B system, state code is mandatory. We will assume IGST as fallback.
            igst = (taxable_amount * gst_rate / Decimal('100')).quantize(Decimal('0.01'))
            return {'cgst': Decimal('0.00'), 'sgst': Decimal('0.00'), 'igst': igst, 'total_tax': igst}

        if company_state_code.strip() == party_state_code.strip():
            # Intrastate: Split GST into CGST and SGST
            half_rate = gst_rate / Decimal('2')
            cgst = (taxable_amount * half_rate / Decimal('100')).quantize(Decimal('0.01'))
            sgst = (taxable_amount * half_rate / Decimal('100')).quantize(Decimal('0.01'))
            return {
                'cgst': cgst,
                'sgst': sgst,
                'igst': Decimal('0.00'),
                'total_tax': cgst + sgst
            }
        else:
            # Interstate: Full IGST
            igst = (taxable_amount * gst_rate / Decimal('100')).quantize(Decimal('0.01'))
            return {
                'cgst': Decimal('0.00'),
                'sgst': Decimal('0.00'),
                'igst': igst,
                'total_tax': igst
            }

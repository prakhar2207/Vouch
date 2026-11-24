# apps/payments/services/payment_matching_service.py
import logging
from typing import Optional, Tuple
from django.db.models import Q
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher
from apps.payments.models import MerchantPaymentAccount

logger = logging.getLogger(__name__)


class PaymentMatchingService:
    """
    Multi-tenant cross-company matching engine.
    Safely resolves whether the recipient or payer is a SriLekh SaaS tenant,
    matches corresponding party ledgers, and links reciprocal sales/purchase vouchers.
    """

    @classmethod
    def match_recipient_company(cls, identifier: str) -> Optional[Company]:
        """
        Attempts to match an incoming identifier (VPA, GSTIN, Phone, Virtual Account, or Name)
        to a registered SriLekh company.
        """
        if not identifier:
            return None

        clean_id = identifier.strip()

        # 1. Match by Merchant VPA
        merchant = MerchantPaymentAccount.objects.filter(vpa__iexact=clean_id, is_onboarded=True).first()
        if merchant:
            return merchant.company

        # 2. Match by GSTIN
        if len(clean_id) == 15:
            company = Company.objects.filter(gstin__iexact=clean_id).first()
            if company:
                return company

        # 3. Match by Phone
        company = Company.objects.filter(phone=clean_id).first()
        if company:
            return company

        # 4. Match by exact legal Company Name
        return Company.objects.filter(name__iexact=clean_id).first()

    @classmethod
    def match_customer_ledger(cls, recipient_company: Company, payer_company: Company) -> Optional[Ledger]:
        """
        In the recipient company's Chart of Accounts, finds the Customer ledger
        corresponding to the payer company.
        """
        if not recipient_company or not payer_company:
            return None

        # Look in Customer ledgers (Sundry Debtors)
        customer_qs = Ledger.objects.filter(
            company=recipient_company,
            ledger_type__in=['CUSTOMER', 'DEBTOR'],
            is_archived=False
        )

        # 1. Match by GSTIN (Exact tax identifier match)
        if payer_company.gstin:
            by_gstin = customer_qs.filter(gstin__iexact=payer_company.gstin).first()
            if by_gstin:
                return by_gstin

        # 2. Match by phone
        if payer_company.phone:
            by_phone = customer_qs.filter(phone=payer_company.phone).first()
            if by_phone:
                return by_phone

        # 3. Match by exact name
        by_name = customer_qs.filter(name__iexact=payer_company.name).first()
        if by_name:
            return by_name

        # 4. Partial / fuzzy name match if unambiguous
        candidates = list(customer_qs.filter(name__icontains=payer_company.name[:10]))
        if len(candidates) == 1:
            return candidates[0]

        return None

    @classmethod
    def match_reciprocal_sales_invoice(cls, recipient_company: Company, customer_ledger: Ledger, payer_purchase_bill: Optional[Voucher], amount) -> Optional[Voucher]:
        """
        When a payer pays against their purchase bill, attempts to match the recipient's
        unallocated sales invoice.
        """
        if not recipient_company or not customer_ledger:
            return None

        inv_qs = Voucher.objects.filter(
            company=recipient_company,
            party_ledger=customer_ledger,
            voucher_type='SALES',
            status='POSTED'
        )

        # Try matching by invoice number if payer provided it
        if payer_purchase_bill:
            ref_num = payer_purchase_bill.reference_number or payer_purchase_bill.voucher_number
            if ref_num:
                matched_by_num = inv_qs.filter(voucher_number__iexact=ref_num).first()
                if matched_by_num:
                    return matched_by_num

        # Try matching by exact pending amount
        matched_by_amount = inv_qs.filter(total_amount=amount).order_by('-voucher_date').first()
        return matched_by_amount

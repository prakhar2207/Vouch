# apps/payments/services/beneficiary_resolution_service.py
import re
import urllib.parse
from decimal import Decimal
from typing import Dict, Any, Optional
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.payments.models import MerchantPaymentAccount


BANK_IFSC_MAP = {
    'SBIN': 'State Bank of India',
    'HDFC': 'HDFC Bank',
    'ICIC': 'ICICI Bank',
    'PUNB': 'Punjab National Bank',
    'BARB': 'Bank of Baroda',
    'UTIB': 'Axis Bank',
    'KKBK': 'Kotak Mahindra Bank',
    'CNRB': 'Canara Bank',
    'UBIN': 'Union Bank of India',
    'IDFB': 'IDFC FIRST Bank',
    'YESB': 'Yes Bank',
    'INDB': 'IndusInd Bank',
    'BKID': 'Bank of India',
    'IOBA': 'Indian Overseas Bank',
    'CBIN': 'Central Bank of India',
    'PSIB': 'Punjab & Sind Bank',
    'MAHB': 'Bank of Maharashtra',
    'UCOB': 'UCO Bank',
}


class BeneficiaryResolutionService:
    """
    Unified Recipient & Beneficiary Discovery Engine.
    Handles:
      1. Mobile Number (UPI Number) resolution
      2. UPI VPA format validation & tenant discovery
      3. UPI QR payload parsing & sanitization
      4. Bank Account & IFSC directory lookup
    """

    MOBILE_REGEX = re.compile(r'^[6-9]\d{9}$')
    VPA_REGEX = re.compile(r'^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$')
    IFSC_REGEX = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')

    @classmethod
    def resolve_mobile_number(cls, mobile_number: str) -> Dict[str, Any]:
        """
        Resolves a 10-digit Indian mobile number to an authorized UPI recipient.
        Checks internal SriLekh merchants first, falls back to UPI Number resolution.
        """
        cleaned = re.sub(r'[\s\-+]', '', mobile_number)
        if cleaned.startswith('91') and len(cleaned) == 12:
            cleaned = cleaned[2:]
        elif cleaned.startswith('0') and len(cleaned) == 11:
            cleaned = cleaned[1:]

        if not cls.MOBILE_REGEX.match(cleaned):
            raise ValidationError("Invalid Indian mobile number. Must be a 10-digit number starting with 6-9.")

        # 1. Check if number belongs to an onboarded SriLekh company
        company = Company.objects.filter(phone=cleaned).first()
        if company:
            merchant_account = MerchantPaymentAccount.objects.filter(company=company, is_onboarded=True).first()
            vpa = merchant_account.vpa if merchant_account else f"{cleaned}@srilekh"
            return {
                "mobile_number": cleaned,
                "name": company.legal_name or company.name,
                "vpa": vpa,
                "is_srilekh_merchant": True,
                "is_verified": True,
                "source": "SRILEKH_NETWORK",
                "masked_identifier": f"••••••{cleaned[-4:]}"
            }

        # 2. UPI Number resolution simulator / Setu UPI Number contract
        # Standard synthetic mapping for sandbox testing
        default_name = f"Recipient ({cleaned[-4:]})"
        resolved_vpa = f"{cleaned}@upi"
        return {
            "mobile_number": cleaned,
            "name": default_name,
            "vpa": resolved_vpa,
            "is_srilekh_merchant": False,
            "is_verified": True,
            "source": "NPCI_UPI_NUMBER",
            "masked_identifier": f"••••••{cleaned[-4:]}"
        }

    @classmethod
    def resolve_vpa(cls, vpa: str) -> Dict[str, Any]:
        """
        Validates UPI ID syntax and checks SriLekh merchant directory.
        """
        vpa_clean = vpa.strip().lower()
        if not cls.VPA_REGEX.match(vpa_clean):
            raise ValidationError(f"Invalid UPI ID format '{vpa}'. Must follow pattern username@bank (e.g. merchant@icici).")

        merchant_acct = MerchantPaymentAccount.objects.filter(vpa__iexact=vpa_clean, is_onboarded=True).select_related('company').first()
        if merchant_acct:
            return {
                "vpa": vpa_clean,
                "name": merchant_acct.company.legal_name or merchant_acct.company.name,
                "is_srilekh_merchant": True,
                "is_verified": True,
                "source": "SRILEKH_NETWORK"
            }

        return {
            "vpa": vpa_clean,
            "name": vpa_clean.split('@')[0].replace('.', ' ').title(),
            "is_srilekh_merchant": False,
            "is_verified": False,
            "source": "VPA_SYNTAX"
        }

    @classmethod
    def parse_upi_qr(cls, qr_string: str) -> Dict[str, Any]:
        """
        Parses and validates standard NPCI UPI QR code payloads (e.g. upi://pay?pa=...&pn=...).
        Defends against injection and malicious payloads.
        """
        if not qr_string or not isinstance(qr_string, str):
            raise ValidationError("QR payload cannot be empty.")

        qr_clean = qr_string.strip()
        if not (qr_clean.startswith("upi://pay?") or qr_clean.startswith("UPI://PAY?")):
            raise ValidationError("Unsupported QR code. Only standard UPI QR codes (upi://pay?...) are accepted.")

        # Sanitize against CRLF injection
        if '\r' in qr_clean or '\n' in qr_clean:
            raise ValidationError("Malicious QR payload detected (CRLF injection).")

        parsed_url = urllib.parse.urlparse(qr_clean)
        params = urllib.parse.parse_qs(parsed_url.query)

        pa_list = params.get('pa') or params.get('PA')
        if not pa_list or not pa_list[0]:
            raise ValidationError("Invalid UPI QR: Payee Address ('pa') is missing.")
        vpa = pa_list[0].strip().lower()

        if not cls.VPA_REGEX.match(vpa):
            raise ValidationError(f"Invalid VPA '{vpa}' inside QR code.")

        pn_list = params.get('pn') or params.get('PN')
        payee_name = pn_list[0].strip() if pn_list and pn_list[0] else vpa.split('@')[0].title()

        amount_val = None
        am_list = params.get('am') or params.get('AM')
        if am_list and am_list[0]:
            try:
                amt = Decimal(am_list[0].strip())
                if amt > 0:
                    amount_val = amt
            except Exception:
                pass

        tn_list = params.get('tn') or params.get('TN')
        note = tn_list[0].strip() if tn_list and tn_list[0] else ""

        tr_list = params.get('tr') or params.get('TR')
        ref = tr_list[0].strip() if tr_list and tr_list[0] else ""

        return {
            "vpa": vpa,
            "name": payee_name,
            "amount": str(amount_val) if amount_val else None,
            "notes": note,
            "reference": ref,
            "is_verified": True,
            "source": "SCANNED_UPI_QR"
        }

    @classmethod
    def validate_ifsc(cls, ifsc_code: str) -> Dict[str, Any]:
        """
        Validates bank IFSC format and maps to bank institution name.
        """
        ifsc_clean = ifsc_code.strip().upper()
        if not cls.IFSC_REGEX.match(ifsc_clean):
            raise ValidationError(f"Invalid IFSC code '{ifsc_code}'. Must be 11 uppercase characters with 5th char '0'.")

        prefix = ifsc_clean[:4]
        bank_name = BANK_IFSC_MAP.get(prefix, f"Bank ({prefix})")

        return {
            "ifsc": ifsc_clean,
            "bank_name": bank_name,
            "is_valid": True
        }

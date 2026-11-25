import re
import uuid
import logging
from decimal import Decimal
from datetime import datetime, date, timedelta, timezone as dt_timezone
from typing import Dict, Any, Optional
from django.utils import timezone
from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import GSTRegistration, EInvoiceRecord
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.exceptions import EInvoiceEligibilityError, DuplicateSubmissionError, GSTIntegrationError

logger = logging.getLogger('apps.gst.einvoice_service')


def quantize_amount(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class EInvoiceService:
    """
    Authoritative e-Invoice (IRN) Generation, Cancellation, and Lifecycle Service.
    Conforms to Sandbox & National Informatics Centre (NIC) IRP Schema v1.1.
    INVARIANT: Strictly idempotent. Prevents double-generation and preserves accounting books.
    """

    @classmethod
    def validate_eligibility(cls, voucher: Voucher) -> Dict[str, Any]:
        """
        Validates whether a voucher is eligible for e-Invoicing.
        Rules:
        - Voucher must be POSTED
        - Voucher type must be SALES, CREDIT_NOTE, or DEBIT_NOTE
        - Seller must have valid 15-char GSTIN
        - Buyer must have valid 15-char GSTIN (B2B supply)
        - Must have at least 1 line item with valid HSN/SAC
        """
        errors = []

        if voucher.status not in ['POSTED']:
            errors.append(f"Voucher status is '{voucher.status}'. Only POSTED vouchers may be e-invoiced.")

        if voucher.voucher_type not in ['SALES', 'CREDIT_NOTE', 'DEBIT_NOTE']:
            errors.append(f"Voucher type '{voucher.voucher_type}' is not eligible for e-Invoicing.")

        seller_gstin = (voucher.company.gstin or '').strip().upper()
        if not seller_gstin or len(seller_gstin) != 15:
            errors.append("Seller company GSTIN is missing or invalid.")

        party_ledger = voucher.party_ledger
        buyer_gstin = (party_ledger.gstin if party_ledger and party_ledger.gstin else (voucher.buyer_gstin or '')).strip().upper()
        if not buyer_gstin or len(buyer_gstin) != 15:
            errors.append("Recipient GSTIN is missing or invalid (e-Invoicing applies strictly to B2B supplies).")

        items = list(voucher.items.all())
        if not items:
            errors.append("Voucher has no line items.")

        for idx, itm in enumerate(items, 1):
            hsn = (itm.hsn_code or (itm.product.hsn_code if itm.product else '') or '').strip()
            if not hsn or len(hsn) < 4:
                errors.append(f"Line item #{idx} ('{itm.product.name if itm.product else 'Item'}') lacks a valid 4-to-8 digit HSN/SAC code.")

        # Check if already generated
        existing_record = EInvoiceRecord.objects.filter(voucher=voucher).first()
        if existing_record and existing_record.status == 'GENERATED':
            errors.append(f"An active IRN has already been generated for this invoice: {existing_record.irn}")

        return {
            "eligible": len(errors) == 0,
            "errors": errors,
            "seller_gstin": seller_gstin,
            "buyer_gstin": buyer_gstin,
            "items_count": len(items)
        }

    @classmethod
    def build_irn_payload(cls, voucher: Voucher, registration: Optional[GSTRegistration] = None) -> Dict[str, Any]:
        """
        Constructs official NIC / Sandbox IRP JSON Payload v1.1 from Voucher data.
        """
        company = voucher.company
        party_ledger = voucher.party_ledger

        seller_gstin = (
            registration.gstin if registration
            else (company.gstin or '')
        ).strip().upper()

        seller_state = (
            registration.state_code if registration
            else (company.state_code or seller_gstin[:2])
        ).zfill(2)

        buyer_gstin = (
            party_ledger.gstin if party_ledger and party_ledger.gstin
            else (voucher.buyer_gstin or '')
        ).strip().upper()

        buyer_pos = (
            voucher.buyer_state_code
            or (party_ledger.state_code if party_ledger else '')
            or buyer_gstin[:2]
        ).zfill(2)

        is_interstate = (seller_state != buyer_pos)

        # Doc Type: INV, CRN, DBN
        doc_typ_map = {'SALES': 'INV', 'CREDIT_NOTE': 'CRN', 'DEBIT_NOTE': 'DBN'}
        doc_typ = doc_typ_map.get(voucher.voucher_type, 'INV')

        # Items list
        item_list = []
        tot_ass_val = Decimal('0.00')
        tot_cgst_val = Decimal('0.00')
        tot_sgst_val = Decimal('0.00')
        tot_igst_val = Decimal('0.00')
        tot_cess_val = Decimal('0.00')

        for idx, itm in enumerate(voucher.items.all(), 1):
            hsn = (itm.hsn_code or (itm.product.hsn_code if itm.product else '') or '9999').strip()
            desc = (itm.product.name if itm.product else "Goods/Services")[:100]
            qty = quantize_amount(itm.quantity or 1)
            rate = quantize_amount(getattr(itm, 'rate', getattr(itm, 'unit_price', 0)))
            tot_amt = quantize_amount(qty * rate)
            taxable = quantize_amount(itm.taxable_amount)
            gst_rate = quantize_amount(itm.gst_rate)

            igst = quantize_amount(itm.igst_amount)
            cgst = quantize_amount(itm.cgst_amount)
            sgst = quantize_amount(itm.sgst_amount)
            cess = quantize_amount(getattr(itm, 'cess_amount', 0))

            tot_item_val = taxable + igst + cgst + sgst + cess

            tot_ass_val += taxable
            tot_igst_val += igst
            tot_cgst_val += cgst
            tot_sgst_val += sgst
            tot_cess_val += cess

            item_list.append({
                "SlNo": str(idx),
                "PrdDesc": desc,
                "IsServc": "Y" if hsn.startswith('99') else "N",
                "HsnCd": hsn,
                "Qty": float(qty),
                "Unit": getattr(itm.product, 'unit', 'NOS') if itm.product else 'NOS',
                "UnitPrice": float(rate),
                "TotAmt": float(tot_amt),
                "Discount": 0.0,
                "PreTaxVal": 0.0,
                "AssAmt": float(taxable),
                "GstRt": float(gst_rate),
                "IgstAmt": float(igst),
                "CgstAmt": float(cgst),
                "SgstAmt": float(sgst),
                "CesAmt": float(cess),
                "CesNonAdvlAmt": 0.0,
                "StateCesAmt": 0.0,
                "StateCesNonAdvlAmt": 0.0,
                "OthChrg": 0.0,
                "TotItemVal": float(tot_item_val)
            })

        total_inv_val = quantize_amount(voucher.total_amount)

        payload = {
            "Version": "1.1",
            "TranDtls": {
                "TaxSch": "GST",
                "SupTyp": "B2B",
                "RegRev": "Y" if getattr(voucher, 'is_reverse_charge', False) else "N",
                "EcmGstin": None,
                "IgstOnIntra": "N"
            },
            "DocDtls": {
                "Typ": doc_typ,
                "No": voucher.voucher_number[:16],
                "Dt": voucher.voucher_date.strftime('%d/%m/%Y')
            },
            "SellerDtls": {
                "Gstin": seller_gstin,
                "LglNm": (registration.legal_name if registration else company.legal_name or company.name)[:100],
                "TrdNm": (registration.trade_name if registration else company.name)[:100],
                "Addr1": (registration.address if registration else company.address or 'Address')[:100],
                "Addr2": "",
                "Loc": (company.city or 'City')[:50],
                "Pin": int(re.sub(r'\D', '', (registration.pincode if registration else company.pincode or '110001'))[:6] or 110001),
                "Stcd": seller_state,
                "Ph": (company.phone or '9999999999')[:10],
                "Em": (company.email or 'billing@srilekh.com')[:100]
            },
            "BuyerDtls": {
                "Gstin": buyer_gstin,
                "LglNm": str(getattr(party_ledger, 'name', None) or voucher.buyer_name or 'Buyer')[:100],
                "TrdNm": str(getattr(party_ledger, 'name', None) or voucher.buyer_name or 'Buyer')[:100],
                "Pos": buyer_pos,
                "Addr1": str(getattr(party_ledger, 'address', None) or voucher.buyer_address or 'Buyer Address')[:100],
                "Addr2": "",
                "Loc": str(getattr(party_ledger, 'city', None) or getattr(voucher, 'buyer_city', None) or getattr(company, 'city', None) or 'City')[:50],
                "Pin": int(re.sub(r'\D', '', str(getattr(party_ledger, 'pincode', None) or getattr(voucher, 'buyer_pincode', None) or '110001'))[:6] or 110001),
                "Stcd": buyer_pos,
                "Ph": str(getattr(party_ledger, 'phone', None) or voucher.buyer_phone or '9999999999')[:10],
                "Em": str(getattr(party_ledger, 'email', None) or voucher.buyer_email or 'buyer@example.com')[:100]
            },
            "ItemList": item_list,
            "ValDtls": {
                "AssVal": float(tot_ass_val),
                "CgstVal": float(tot_cgst_val),
                "SgstVal": float(tot_sgst_val),
                "IgstVal": float(tot_igst_val),
                "CesVal": float(tot_cess_val),
                "StCesVal": 0.0,
                "Discount": 0.0,
                "OthChrg": 0.0,
                "RndOffAmt": 0.0,
                "TotInvVal": float(total_inv_val)
            }
        }
        return payload

    @classmethod
    def generate_irn(
        cls,
        voucher: Voucher,
        registration: Optional[GSTRegistration] = None,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Submits e-Invoice request to Sandbox and saves EInvoiceRecord.
        Guarantees idempotency: If IRN already exists, returns existing record.
        """
        # 1. Check for existing active record (Idempotent replay)
        existing = EInvoiceRecord.objects.filter(voucher=voucher, status='GENERATED').first()
        if existing:
            return {
                "success": True,
                "irn": existing.irn,
                "ack_number": existing.ack_number,
                "ack_date": existing.ack_date.isoformat() if existing.ack_date else None,
                "signed_qr_code": existing.signed_qr_code,
                "status": existing.status,
                "is_cached": True,
                "message": "IRN was already generated for this invoice."
            }

        # 2. Eligibility Check
        check = cls.validate_eligibility(voucher)
        if not check["eligible"]:
            raise EInvoiceEligibilityError("; ".join(check["errors"]))

        # 3. Build payload
        payload = cls.build_irn_payload(voucher, registration)

        # 4. Dispatch to Sandbox client
        client = SandboxGSTClient(company=voucher.company, registration=registration)
        session_token = registration.auth_token if registration else None

        if not client.is_configured():
            raise GSTIntegrationError(
                "Sandbox GST Gateway is not configured. Supply GST_SANDBOX_API_KEY and GST_SANDBOX_API_SECRET."
            )

        res = client.generate_einvoice(payload, session_token=session_token, user=user)
        if not res.get("success"):
            return {
                "success": False,
                "error": res.get("error", "Sandbox e-Invoice generation failed."),
                "correlation_id": res.get("correlation_id"),
                "raw": res.get("raw")
            }

        data = res.get("data") or {}
        irn = data.get("Irn") or data.get("irn")
        ack_no = str(data.get("AckNo") or data.get("ack_no") or '')
        ack_dt_str = data.get("AckDt") or data.get("ack_dt")
        signed_inv = data.get("SignedInvoice") or data.get("signed_invoice") or ''
        signed_qr = data.get("SignedQRCode") or data.get("signed_qr_code") or ''

        ack_dt = None
        if ack_dt_str:
            try:
                ack_dt = datetime.strptime(ack_dt_str, '%Y-%m-%d %H:%M:%S')
                if timezone.is_naive(ack_dt):
                    ack_dt = timezone.make_aware(ack_dt, dt_timezone.utc)
            except Exception:
                ack_dt = timezone.now()

        # 5. Persist EInvoiceRecord
        record, _ = EInvoiceRecord.objects.update_or_create(
            voucher=voucher,
            defaults={
                "company": voucher.company,
                "gst_registration": registration,
                "irn": irn,
                "ack_number": ack_no,
                "ack_date": ack_dt or timezone.now(),
                "signed_invoice": signed_inv,
                "signed_qr_code": signed_qr,
                "status": 'GENERATED',
                "raw_response_json": data
            }
        )

        return {
            "success": True,
            "irn": record.irn,
            "ack_number": record.ack_number,
            "ack_date": record.ack_date.isoformat() if record.ack_date else None,
            "signed_qr_code": record.signed_qr_code,
            "status": record.status,
            "correlation_id": res.get("correlation_id")
        }

    @classmethod
    def cancel_irn(
        cls,
        voucher: Voucher,
        cancel_reason: str = "1",
        cancel_remarks: str = "Order cancelled",
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Cancels an active IRN within the statutory 24-hour window.
        Reason codes: 1=Duplicate, 2=Data entry mistake, 3=Order cancelled, 4=Others.
        """
        record = EInvoiceRecord.objects.filter(voucher=voucher, status='GENERATED').first()
        if not record:
            return {"success": False, "error": "No active generated e-Invoice found for this voucher."}

        # Check 24-hour statutory window
        if record.ack_date and (timezone.now() - record.ack_date) > timedelta(hours=24):
            return {
                "success": False,
                "error": "Statutory 24-hour cancellation window has elapsed. This e-Invoice can only be cancelled via a Credit Note."
            }

        client = SandboxGSTClient(company=voucher.company, registration=record.gst_registration)
        session_token = record.gst_registration.auth_token if record.gst_registration else None

        res = client.cancel_einvoice(
            irn=record.irn,
            cancel_reason=cancel_reason,
            remarks=cancel_remarks,
            session_token=session_token,
            user=user
        )

        if not res.get("success"):
            return {
                "success": False,
                "error": res.get("error", "IRN cancellation failed on Sandbox."),
                "correlation_id": res.get("correlation_id")
            }

        record.status = 'CANCELLED'
        record.cancel_reason = cancel_reason
        record.cancel_remarks = cancel_remarks
        record.cancelled_at = timezone.now()
        record.save(update_fields=['status', 'cancel_reason', 'cancel_remarks', 'cancelled_at'])

        return {
            "success": True,
            "irn": record.irn,
            "status": 'CANCELLED',
            "cancelled_at": record.cancelled_at.isoformat()
        }

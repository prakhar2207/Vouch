import re
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from django.utils import timezone
from apps.companies.models import Company
from apps.accounting.models import Voucher
from apps.gst.models import GSTRegistration, EWayBillRecord, EInvoiceRecord
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.exceptions import GSTIntegrationError

logger = logging.getLogger('apps.gst.ewaybill_service')


def quantize_amount(val: Any) -> Decimal:
    try:
        return Decimal(str(val or '0.00')).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0.00')


class EWayBillService:
    """
    Authoritative E-Way Bill Generation, Vehicle Update, and Lifecycle Service.
    Supports both IRN-tied generation and direct standalone Part-A/Part-B generation.
    INVARIANT: ZERO mutation of vouchers, ledgers, or inventory stock levels.
    """

    @classmethod
    def generate_ewaybill(
        cls,
        voucher: Voucher,
        trans_mode: str = "1",
        distance_km: int = 10,
        transporter_id: str = "",
        transporter_name: str = "",
        vehicle_number: str = "",
        vehicle_type: str = "R",
        registration: Optional[GSTRegistration] = None,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Generates E-Way Bill for a voucher.
        If the voucher is already e-invoiced (has an IRN), generates E-Way bill via IRN endpoint.
        Otherwise, submits direct standalone consignment payload.
        """
        company = voucher.company
        client = SandboxGSTClient(company=company, registration=registration)
        session_token = registration.auth_token if registration else None

        if not client.is_configured():
            raise GSTIntegrationError(
                "Sandbox GST Gateway is not configured. Supply GST_SANDBOX_API_KEY and GST_SANDBOX_API_SECRET."
            )

        # Check if already generated
        existing = EWayBillRecord.objects.filter(voucher=voucher, status='ACTIVE').first()
        if existing:
            return {
                "success": True,
                "ewb_number": existing.ewb_number,
                "ewb_date": existing.ewb_date.isoformat(),
                "valid_until": existing.valid_until.isoformat(),
                "status": existing.status,
                "is_cached": True,
                "message": "E-Way Bill was already generated for this invoice."
            }

        # Check if e-invoiced
        einvoice = EInvoiceRecord.objects.filter(voucher=voucher, status='GENERATED').first()

        if einvoice:
            # Method A: Generate via IRN
            payload = {
                "Irn": einvoice.irn,
                "Distance": int(distance_km),
                "TransMode": str(trans_mode),
                "TransId": transporter_id.strip() or None,
                "TransName": transporter_name.strip() or None,
                "TransDocDt": voucher.voucher_date.strftime('%d/%m/%Y'),
                "TransDocNo": f"TRN/{voucher.voucher_number}",
                "VehNo": vehicle_number.strip().upper() or None,
                "VehType": vehicle_type
            }
            res = client.generate_ewaybill_for_irn(
                irn=einvoice.irn,
                payload=payload,
                session_token=session_token,
                user=user
            )
        else:
            # Method B: Generate Direct Consignment E-Way Bill
            seller_gstin = (registration.gstin if registration else company.gstin or '').strip().upper()
            buyer_gstin = (
                voucher.party_ledger.gstin if voucher.party_ledger and voucher.party_ledger.gstin
                else (voucher.buyer_gstin or '')
            ).strip().upper()

            item_list = []
            tot_taxable = Decimal('0.00')
            tot_igst = Decimal('0.00')
            tot_cgst = Decimal('0.00')
            tot_sgst = Decimal('0.00')
            tot_cess = Decimal('0.00')

            for itm in voucher.items.all():
                hsn = (itm.hsn_code or (itm.product.hsn_code if itm.product else '') or '9999').strip()
                taxable = quantize_amount(itm.taxable_amount)
                igst = quantize_amount(itm.igst_amount)
                cgst = quantize_amount(itm.cgst_amount)
                sgst = quantize_amount(itm.sgst_amount)
                cess = quantize_amount(getattr(itm, 'cess_amount', 0))

                tot_taxable += taxable
                tot_igst += igst
                tot_cgst += cgst
                tot_sgst += sgst
                tot_cess += cess

                item_list.append({
                    "productName": (itm.product.name if itm.product else "Goods")[:50],
                    "productDesc": (itm.product.name if itm.product else "Goods")[:50],
                    "hsnCode": int(re.sub(r'\D', '', hsn)[:8] or 9999),
                    "quantity": float(itm.quantity or 1),
                    "qtyUnit": getattr(itm.product, 'unit', 'NOS') if itm.product else 'NOS',
                    "taxableAmount": float(taxable),
                    "sgstRate": float(itm.gst_rate / 2 if igst == 0 else 0),
                    "cgstRate": float(itm.gst_rate / 2 if igst == 0 else 0),
                    "igstRate": float(itm.gst_rate if igst > 0 else 0),
                    "cessRate": 0.0
                })

            payload = {
                "supplyType": "O",
                "subSupplyType": "1",
                "docType": "INV",
                "docNo": voucher.voucher_number[:16],
                "docDate": voucher.voucher_date.strftime('%d/%m/%Y'),
                "fromGstin": seller_gstin,
                "fromTrdName": (company.name or 'Seller')[:100],
                "fromAddr1": (company.address or 'Address')[:100],
                "fromPlace": (company.city or 'City')[:50],
                "fromPincode": int(re.sub(r'\D', '', company.pincode or '110001')[:6] or 110001),
                "fromStateCode": int(company.state_code or seller_gstin[:2] or 9),
                "toGstin": buyer_gstin or "URP",
                "toTrdName": str(getattr(voucher.party_ledger, 'name', None) or voucher.buyer_name or 'Buyer')[:100],
                "toAddr1": str(getattr(voucher.party_ledger, 'address', None) or voucher.buyer_address or 'Buyer Address')[:100],
                "toPlace": str(getattr(voucher.party_ledger, 'city', None) or getattr(voucher, 'buyer_city', None) or company.city or 'City')[:50],
                "toPincode": int(re.sub(r'\D', '', str(getattr(voucher.party_ledger, 'pincode', None) or getattr(voucher, 'buyer_pincode', None) or '110001'))[:6] or 110001),
                "toStateCode": int(voucher.buyer_state_code or buyer_gstin[:2] or 9),
                "totalValue": float(tot_taxable),
                "cgstValue": float(tot_cgst),
                "sgstValue": float(tot_sgst),
                "igstValue": float(tot_igst),
                "cessValue": float(tot_cess),
                "totInvValue": float(voucher.total_amount),
                "transMode": str(trans_mode),
                "transDistance": str(distance_km),
                "transporterId": transporter_id.strip() or "",
                "transporterName": transporter_name.strip() or "",
                "vehicleNo": vehicle_number.strip().upper() or "",
                "vehicleType": vehicle_type,
                "itemList": item_list
            }
            res = client.generate_standalone_ewaybill(
                payload=payload,
                session_token=session_token,
                user=user
            )

        if not res.get("success"):
            return {
                "success": False,
                "error": res.get("error", "Sandbox E-Way Bill generation failed."),
                "correlation_id": res.get("correlation_id"),
                "raw": res.get("raw")
            }

        data = res.get("data") or {}
        ewb_no = str(data.get("ewayBillNo") or data.get("EwbNo") or data.get("ewb_number") or '')
        ewb_date_str = data.get("ewayBillDate") or data.get("EwbDt") or data.get("ewb_date")
        valid_until_str = data.get("validUpto") or data.get("EwbValidTill") or data.get("valid_until")

        now = timezone.now()
        ewb_date = now
        valid_until = now + timedelta(days=max(1, distance_km // 100 + 1))

        if ewb_date_str:
            try:
                ewb_date = datetime.strptime(ewb_date_str, '%d/%m/%Y %I:%M:%S %p')
            except Exception:
                pass

        if valid_until_str:
            try:
                valid_until = datetime.strptime(valid_until_str, '%d/%m/%Y %I:%M:%S %p')
            except Exception:
                pass

        record, _ = EWayBillRecord.objects.update_or_create(
            voucher=voucher,
            defaults={
                "company": company,
                "gst_registration": registration,
                "ewb_number": ewb_no,
                "ewb_date": ewb_date,
                "valid_until": valid_until,
                "status": 'ACTIVE',
                "transport_mode": trans_mode,
                "distance_km": int(distance_km),
                "transporter_id": transporter_id,
                "transporter_name": transporter_name,
                "vehicle_number": vehicle_number.upper(),
                "vehicle_type": vehicle_type,
                "raw_response_json": data
            }
        )

        return {
            "success": True,
            "ewb_number": record.ewb_number,
            "ewb_date": record.ewb_date.isoformat(),
            "valid_until": record.valid_until.isoformat(),
            "status": record.status,
            "correlation_id": res.get("correlation_id")
        }

    @classmethod
    def update_vehicle(
        cls,
        eway_bill: EWayBillRecord,
        vehicle_number: str,
        from_place: str,
        from_state: str,
        reason_code: str = "1",
        remarks: str = "",
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Updates Part-B Vehicle Details for an active E-Way Bill.
        Reason codes: 1=Due to breakdown, 2=Due to transshipment, 3=Others.
        """
        client = SandboxGSTClient(company=eway_bill.company, registration=eway_bill.gst_registration)
        session_token = eway_bill.gst_registration.auth_token if eway_bill.gst_registration else None

        payload = {
            "ewbNo": int(eway_bill.ewb_number),
            "vehicleNo": vehicle_number.strip().upper(),
            "fromPlace": from_place.strip()[:50],
            "fromState": int(from_state),
            "reasonCode": str(reason_code),
            "reasonRem": remarks.strip()[:50],
            "transDocNo": "",
            "transDocDate": timezone.now().strftime('%d/%m/%Y'),
            "transMode": "1",
            "vehicleType": eway_bill.vehicle_type
        }

        res = client.update_ewaybill_vehicle(payload, session_token=session_token, user=user)
        if not res.get("success"):
            return {
                "success": False,
                "error": res.get("error", "Failed to update vehicle details on Sandbox."),
                "correlation_id": res.get("correlation_id")
            }

        eway_bill.vehicle_number = vehicle_number.strip().upper()
        eway_bill.save(update_fields=['vehicle_number'])

        return {
            "success": True,
            "ewb_number": eway_bill.ewb_number,
            "vehicle_number": eway_bill.vehicle_number,
            "updated_at": timezone.now().isoformat()
        }

    @classmethod
    def cancel_ewaybill(
        cls,
        eway_bill: EWayBillRecord,
        cancel_reason: str = "1",
        cancel_remarks: str = "Order cancelled",
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Cancels an active E-Way bill within 24 hours of generation.
        Reason codes: 1=Duplicate, 2=Order Cancelled, 3=Data Entry Mistake, 4=Others.
        """
        client = SandboxGSTClient(company=eway_bill.company, registration=eway_bill.gst_registration)
        session_token = eway_bill.gst_registration.auth_token if eway_bill.gst_registration else None

        payload = {
            "ewbNo": int(eway_bill.ewb_number),
            "cancelRsnCode": int(cancel_reason),
            "cancelRmrk": cancel_remarks.strip()[:50]
        }

        res = client.cancel_ewaybill(payload, session_token=session_token, user=user)
        if not res.get("success"):
            return {
                "success": False,
                "error": res.get("error", "Failed to cancel E-Way Bill on Sandbox."),
                "correlation_id": res.get("correlation_id")
            }

        eway_bill.status = 'CANCELLED'
        eway_bill.cancel_reason = cancel_reason
        eway_bill.cancel_remarks = cancel_remarks
        eway_bill.cancelled_at = timezone.now()
        eway_bill.save(update_fields=['status', 'cancel_reason', 'cancel_remarks', 'cancelled_at'])

        return {
            "success": True,
            "ewb_number": eway_bill.ewb_number,
            "status": 'CANCELLED',
            "cancelled_at": eway_bill.cancelled_at.isoformat()
        }

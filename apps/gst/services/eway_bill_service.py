import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any
from django.db import transaction
from apps.accounting.models import Voucher, VoucherItem
from apps.gst.models import EWayBillRecord
from apps.gst.services.providers.factory import get_gst_provider

logger = logging.getLogger(__name__)

class EWayBillService:
    """
    Orchestration service for Indian E-Way Bill operations.
    Complies with NIC E-Way Bill Specification v1.04.
    """

    @classmethod
    @transaction.atomic
    def generate_for_voucher(cls, voucher: Voucher, transport_details: Dict[str, Any], user) -> Dict[str, Any]:
        company = voucher.company
        party = voucher.party_ledger
        
        # Calculate item aggregates
        items = voucher.items.all()
        if not items.exists():
            return {
                "success": False,
                "error": "Cannot generate E-Way bill for an invoice with no line items."
            }

        tot_taxable = sum([i.taxable_amount for i in items], Decimal('0.00'))
        tot_cgst = sum([i.cgst_amount for i in items], Decimal('0.00'))
        tot_sgst = sum([i.sgst_amount for i in items], Decimal('0.00'))
        tot_igst = sum([i.igst_amount for i in items], Decimal('0.00'))

        # Prepare NIC Payload
        is_sales = voucher.voucher_type == 'SALES'
        
        from_gstin = company.gstin or 'URP'
        from_trd_name = company.name
        from_addr1 = company.address or 'Address'
        from_place = company.city or 'City'
        from_pin = int(company.pincode) if (company.pincode and company.pincode.isdigit()) else 208001
        from_state = int(company.state_code) if (company.state_code and company.state_code.isdigit()) else 9

        to_gstin = party.gstin if (party and party.gstin) else (voucher.buyer_gstin or 'URP')
        to_trd_name = party.name if party else (voucher.buyer_name or 'Counter Buyer')
        to_addr1 = party.address if (party and party.address) else (voucher.buyer_address or 'Address')
        to_place = getattr(party, 'city', '') or company.city or 'City'
        to_pin = 208001
        if party and getattr(party, 'pincode', None) and str(party.pincode).isdigit():
            to_pin = int(party.pincode)
        to_state = int(voucher.buyer_state_code) if (voucher.buyer_state_code and voucher.buyer_state_code.isdigit()) else from_state

        item_list = []
        for idx, itm in enumerate(items, start=1):
            item_list.append({
                "itemNo": idx,
                "productName": itm.product.name if itm.product else "Goods",
                "productDesc": itm.product.name if itm.product else "Goods",
                "hsnCode": int(itm.product.hsn_code) if (itm.product and itm.product.hsn_code and itm.product.hsn_code.isdigit()) else 8483,
                "quantity": float(itm.quantity),
                "qtyUnit": itm.product.unit if itm.product else "PCS",
                "taxableAmount": float(itm.taxable_amount),
                "cgstRate": float(itm.gst_rate / 2) if tot_cgst > 0 else 0.0,
                "sgstRate": float(itm.gst_rate / 2) if tot_sgst > 0 else 0.0,
                "igstRate": float(itm.gst_rate) if tot_igst > 0 else 0.0,
                "cessRate": 0.0,
            })

        nic_payload = {
            "supplyType": "O" if is_sales else "I",
            "subSupplyType": "1",  # 1 = Supply
            "subSupplyDesc": "",
            "docType": "INV",
            "docNo": voucher.voucher_number,
            "docDate": voucher.voucher_date.strftime('%d/%m/%Y'),
            "fromGstin": from_gstin,
            "fromTrdName": from_trd_name,
            "fromAddr1": from_addr1,
            "fromAddr2": "",
            "fromPlace": from_place,
            "fromPincode": from_pin,
            "actFromStateCode": from_state,
            "fromStateCode": from_state,
            "toGstin": to_gstin,
            "toTrdName": to_trd_name,
            "toAddr1": to_addr1,
            "toAddr2": "",
            "toPlace": to_place,
            "toPincode": to_pin,
            "actToStateCode": to_state,
            "toStateCode": to_state,
            "totalValue": float(tot_taxable),
            "cgstValue": float(tot_cgst),
            "sgstValue": float(tot_sgst),
            "igstValue": float(tot_igst),
            "cessValue": 0.0,
            "totInvValue": float(voucher.total_amount),
            "transMode": transport_details.get('transport_mode', '1'),  # 1=Road
            "transDistance": str(transport_details.get('distance_km', 100)),
            "transporterId": transport_details.get('transporter_id', ''),
            "transporterName": transport_details.get('transporter_name', ''),
            "transDocNo": transport_details.get('transporter_doc_no', ''),
            "transDocDate": transport_details.get('transporter_doc_date', ''),
            "vehNo": transport_details.get('vehicle_number', ''),
            "vehType": transport_details.get('vehicle_type', 'R'),
            "itemList": item_list,
        }

        provider = get_gst_provider(company)
        res = provider.generate_eway_bill(nic_payload)

        if not res.get('success'):
            return res

        # Parse date and valid_until
        ewb_date = datetime.now(timezone.utc)
        valid_until = datetime.now(timezone.utc)
        if res.get('ewb_date'):
            try:
                ewb_date = datetime.strptime(res['ewb_date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except Exception:
                pass
        if res.get('valid_until'):
            try:
                valid_until = datetime.strptime(res['valid_until'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            except Exception:
                pass

        # Create EWayBillRecord
        record = EWayBillRecord.objects.create(
            company=company,
            voucher=voucher,
            ewb_number=str(res['ewb_number']),
            ewb_date=ewb_date,
            valid_until=valid_until,
            status='ACTIVE',
            supply_type="OUTWARD" if is_sales else "INWARD",
            sub_supply_type="SUPPLY",
            doc_type="INV",
            transport_mode=transport_details.get('transport_mode', '1'),
            distance_km=int(transport_details.get('distance_km', 100)),
            transporter_id=transport_details.get('transporter_id', ''),
            transporter_name=transport_details.get('transporter_name', ''),
            vehicle_number=transport_details.get('vehicle_number', ''),
            vehicle_type=transport_details.get('vehicle_type', 'R'),
            transporter_doc_no=transport_details.get('transporter_doc_no', ''),
            raw_response_json=res.get('raw', {}),
        )

        return {
            "success": True,
            "ewb_number": record.ewb_number,
            "ewb_date": record.ewb_date.strftime('%Y-%m-%d %H:%M:%S'),
            "valid_until": record.valid_until.strftime('%Y-%m-%d %H:%M:%S'),
            "status": record.status,
            "vehicle_number": record.vehicle_number,
            "distance_km": record.distance_km,
            "record_id": str(record.id),
        }

    @classmethod
    def update_vehicle(cls, ewb_record: EWayBillRecord, new_vehicle_number: str, reason: str = "", remarks: str = "") -> Dict[str, Any]:
        provider = get_gst_provider(ewb_record.company)
        payload = {
            "ewb_number": ewb_record.ewb_number,
            "vehicle_number": new_vehicle_number.strip().upper(),
            "reason": reason,
            "remarks": remarks,
        }
        res = provider.update_vehicle(payload)
        if res.get('success'):
            ewb_record.vehicle_number = new_vehicle_number.strip().upper()
            ewb_record.save(update_fields=['vehicle_number', 'updated_at'])
        return res

    @classmethod
    def cancel_eway_bill(cls, ewb_record: EWayBillRecord, reason: str = "1", remarks: str = "Order Cancelled") -> Dict[str, Any]:
        provider = get_gst_provider(ewb_record.company)
        payload = {
            "ewb_number": ewb_record.ewb_number,
            "cancel_reason": reason,
            "cancel_remarks": remarks,
        }
        res = provider.cancel_eway_bill(payload)
        if res.get('success'):
            ewb_record.status = 'CANCELLED'
            ewb_record.cancel_reason = reason
            ewb_record.cancel_remarks = remarks
            ewb_record.cancelled_at = datetime.now(timezone.utc)
            ewb_record.save(update_fields=['status', 'cancel_reason', 'cancel_remarks', 'cancelled_at', 'updated_at'])
        return res

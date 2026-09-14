import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from .base import GSTGatewayProvider
from apps.gst.services.gstin_validator import GSTINValidator, STATE_CODES

# Sample Mock Taxpayer Directory for deterministic sandbox testing
MOCK_DIRECTORY = {
    "09AAACB1234C1Z1": {
        "legal_name": "SHREE TIRUPATI PLASTICS PRIVATE LIMITED",
        "trade_name": "Shree Tirupati Plastics",
        "address": "Plot No. 42, Panki Industrial Area, Site-3",
        "pincode": "208022",
        "state_code": "09",
        "taxpayer_type": "Regular",
        "status": "Active",
        "registration_date": "2017-07-01",
    },
    "09AAAPL1234L1Z2": {
        "legal_name": "BHAGWANTI FOOTWEAR PRODUCTS LLP",
        "trade_name": "Bhagwanti Footwear",
        "address": "128/104, K-Block, Kidwai Nagar",
        "pincode": "208011",
        "state_code": "09",
        "taxpayer_type": "Regular",
        "status": "Active",
        "registration_date": "2018-04-15",
    },
    "27AABCT3518Q1ZV": {
        "legal_name": "TALWAR INDUSTRIES LIMITED",
        "trade_name": "Talwar Industries",
        "address": "Shop No. 12, APMC Market-1, Vashi",
        "pincode": "400703",
        "state_code": "27",
        "taxpayer_type": "Regular",
        "status": "Active",
        "registration_date": "2017-07-01",
    },
    "24AABCC1234D1Z8": {
        "legal_name": "CLASSIC PIPE ENTERPRISES",
        "trade_name": "Classic Pipe Enterprises",
        "address": "Shed 15, GIDC Estate, Vatva",
        "pincode": "382445",
        "state_code": "24",
        "taxpayer_type": "Regular",
        "status": "Active",
        "registration_date": "2019-01-10",
    },
}

class MockGSTProvider(GSTGatewayProvider):
    """
    Realistic Sandbox / Mock Provider for local development, CI testing,
    and demo environments without external API costs or NIC downtime.
    """

    def search_taxpayer(self, gstin: str) -> Dict[str, Any]:
        gstin = (gstin or '').strip().upper()
        val = GSTINValidator.validate(gstin)
        if not val['is_valid']:
            return {
                "success": False,
                "gstin": gstin,
                "error": val['error']
            }

        state_code = val['state_code']
        state_name = val['state_name']
        pan = val['pan']

        # 1. Exact match from directory
        if gstin in MOCK_DIRECTORY:
            record = MOCK_DIRECTORY[gstin]
            return {
                "success": True,
                "gstin": gstin,
                "legal_name": record['legal_name'],
                "trade_name": record['trade_name'],
                "state_code": state_code,
                "state_name": state_name,
                "address": f"{record['address']}, {state_name} - {record['pincode']}",
                "pincode": record['pincode'],
                "taxpayer_type": record['taxpayer_type'],
                "status": record['status'],
                "registration_date": record['registration_date'],
                "pan": pan,
                "is_mock": True,
            }

        # 2. Algorithmic dynamic generation for arbitrary valid GSTINs
        entity_type = pan[3] if len(pan) >= 4 else 'C'
        entity_suffix = {
            'C': "PRIVATE LIMITED",
            'P': "PROPRIETORSHIP",
            'F': "TRADING PARTNERSHIP",
            'H': "HUF",
            'A': "ASSOCIATION",
            'L': "LLP",
        }.get(entity_type, "ENTERPRISES")

        legal_name = f"ENTERPRISE {pan[:4]} {entity_suffix}"
        trade_name = f"Enterprise {pan[:4]}"
        sample_pincodes = {
            "09": "208001", "27": "400001", "07": "110001", "24": "380001",
            "29": "560001", "33": "600001", "19": "700001", "03": "141001"
        }
        pincode = sample_pincodes.get(state_code, f"{state_code}0001")
        address = f"Plot No. {random.randint(10, 999)}, Industrial Area, Phase-{random.randint(1, 4)}, {state_name} - {pincode}"

        return {
            "success": True,
            "gstin": gstin,
            "legal_name": legal_name,
            "trade_name": trade_name,
            "state_code": state_code,
            "state_name": state_name,
            "address": address,
            "pincode": pincode,
            "taxpayer_type": "Regular",
            "status": "Active",
            "registration_date": "2017-07-01",
            "pan": pan,
            "is_mock": True,
        }

    def generate_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        distance = int(payload.get('distance_km') or 100)
        # Indian E-Way bill rule: 200 km per day (min 1 day)
        validity_days = max(1, (distance + 199) // 200)
        valid_until = now + timedelta(days=validity_days)

        # 12-digit E-Way Bill Number (State Code prefix + 10 random digits)
        state_prefix = str(payload.get('from_state_code') or '09')[:2]
        random_digits = "".join([str(random.randint(0, 9)) for _ in range(10)])
        ewb_number = f"{state_prefix}{random_digits}"

        return {
            "success": True,
            "ewb_number": ewb_number,
            "ewb_date": now.strftime('%Y-%m-%d %H:%M:%S'),
            "valid_until": valid_until.strftime('%Y-%m-%d %H:%M:%S'),
            "status": "ACTIVE",
            "is_mock": True,
            "raw": {
                "ewbNo": int(ewb_number),
                "ewbDate": now.strftime('%d/%m/%Y %I:%M:%S %p'),
                "validUpto": valid_until.strftime('%d/%m/%Y %I:%M:%S %p'),
                "alert": "Generated in Sandbox / Mock Mode",
            }
        }

    def update_vehicle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "success": True,
            "ewb_number": payload.get('ewb_number'),
            "vehicle_number": payload.get('vehicle_number'),
            "updated_at": now.strftime('%Y-%m-%d %H:%M:%S'),
            "status": "UPDATED",
            "is_mock": True,
        }

    def cancel_eway_bill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "success": True,
            "ewb_number": payload.get('ewb_number'),
            "status": "CANCELLED",
            "cancelled_at": now.strftime('%Y-%m-%d %H:%M:%S'),
            "is_mock": True,
        }

    def generate_einvoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        doc_no = str(payload.get('doc_number') or 'INV-001')
        seller_gstin = str(payload.get('seller_gstin') or '09AAACB1234C1Z1')
        doc_date = str(payload.get('doc_date') or datetime.now().strftime('%Y-%m-%d'))
        
        # 64-character SHA256 IRN hash: Hash(SellerGSTIN + FY + DocType + DocNo)
        raw_key = f"{seller_gstin}:{doc_date[:4]}:INV:{doc_no}"
        irn = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
        
        now = datetime.now(timezone.utc)
        ack_no = f"12{random.randint(100000000000, 999999999999)}"

        return {
            "success": True,
            "irn": irn,
            "ack_number": ack_no,
            "ack_date": now.strftime('%Y-%m-%d %H:%M:%S'),
            "signed_invoice": f"mock_jwt_token_{irn[:16]}",
            "signed_qr_code": f"09{seller_gstin}|INV|{doc_no}|{doc_date}|{payload.get('total_amount', '0')}|{irn[:16]}",
            "status": "GENERATED",
            "is_mock": True,
        }

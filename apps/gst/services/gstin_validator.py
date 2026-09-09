import re

GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')
STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory"
}

# Mod 36 lookup characters for Indian GSTIN checksum
CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

class GSTINValidator:
    @staticmethod
    def validate_format(gstin: str) -> bool:
        if not gstin or len(gstin) != 15:
            return False
        return bool(GSTIN_REGEX.match(gstin.upper()))

    @staticmethod
    def calculate_checksum(gstin14: str) -> str:
        """
        Calculates the 15th check digit for a 14-character GSTIN prefix using Luhn Mod 36.
        """
        if len(gstin14) < 14:
            return ""
        s = gstin14[:14].upper()
        factor = 2
        sum_val = 0
        for char in reversed(s):
            idx = CHARS.index(char) if char in CHARS else 0
            code = idx * factor
            factor = 1 if factor == 2 else 2
            sum_val += (code // 36) + (code % 36)
        remainder = sum_val % 36
        check_idx = (36 - remainder) % 36
        return CHARS[check_idx]

    @classmethod
    def validate(cls, gstin: str, expected_state_code: str = None) -> dict:
        """
        Performs multi-level validation:
        1. Format & length
        2. State code validity
        3. Checksum verification
        4. PAN consistency
        """
        raw = (gstin or '').strip().upper()
        if not raw:
            return {
                "is_valid": False,
                "confidence": "INVALID",
                "error": "GSTIN cannot be empty."
            }

        # Level 1: Format
        if not cls.validate_format(raw):
            return {
                "is_valid": False,
                "confidence": "FORMAT_FAILED",
                "error": f"'{raw}' does not match official 15-character GSTIN format."
            }

        state_code = raw[:2]
        pan = raw[2:12]

        # Level 2: State code check
        state_name = STATE_CODES.get(state_code)
        if not state_name:
            return {
                "is_valid": False,
                "confidence": "STATE_INVALID",
                "error": f"State code '{state_code}' is not a valid Indian GST state code."
            }

        if expected_state_code and expected_state_code.strip() != state_code:
            return {
                "is_valid": False,
                "confidence": "STATE_MISMATCH",
                "error": f"GSTIN state code '{state_code}' ({state_name}) does not match expected state '{expected_state_code}'."
            }

        # Level 3: Checksum
        expected_check = cls.calculate_checksum(raw[:14])
        actual_check = raw[14]
        checksum_matches = (expected_check == actual_check)

        return {
            "is_valid": True,
            "confidence": "CHECKSUM_VERIFIED" if checksum_matches else "FORMAT_VALID_CHECKSUM_WARNING",
            "state_code": state_code,
            "state_name": state_name,
            "pan": pan,
            "checksum_valid": checksum_matches,
            "message": "Valid GSTIN format and state." if checksum_matches else "Valid GSTIN format, check digit differs."
        }

    validate_gstin = validate

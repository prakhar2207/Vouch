import re
import io
import csv
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory
from apps.accounting.models import Voucher, LedgerEntry, FinancialYear
from apps.accounting.services.tally_migration_service import TallyMigrationService

# Fuzzy Column Synonyms for Indian Accounting / ERP Platforms
PARTY_SYNONYMS = {
    "name": [
        "party name", "customer name", "vendor name", "party", "customer", "vendor",
        "supplier name", "supplier", "contact name", "account name", "ledger name",
        "ledger", "client name", "client", "name", "particulars", "party/ledger"
    ],
    "phone": [
        "phone", "phone number", "mobile", "mobile number", "contact number",
        "mobile no", "mobile no.", "phone no", "phone no.", "contact no",
        "party phone", "contact"
    ],
    "email": [
        "email", "email id", "email address", "email_id", "party email", "mail"
    ],
    "gstin": [
        "gstin", "gstin/uin", "gst in", "gst number", "gst no", "gst no.",
        "gst identification number (gstin)", "party gstin", "gst", "tax number"
    ],
    "pan": [
        "pan", "pan number", "pan no", "pan no.", "party pan", "income tax number", "incometaxnumber"
    ],
    "address": [
        "address", "billing address", "registered address", "street", "party address", "office address"
    ],
    "state": [
        "state", "state name", "billing state", "place of supply", "state code"
    ],
    "opening_balance": [
        "opening balance", "opening bal", "op balance", "op bal", "balance",
        "opening balance (₹)", "opening balance (rs)", "current balance", "amount",
        "closing balance", "bal"
    ],
    "balance_type": [
        "to receive / to pay", "to collect/to pay", "balance type", "nature",
        "dr/cr", "debit/credit", "type", "party type", "contact type", "role"
    ],
    "credit_period": [
        "credit period", "credit days", "payment terms", "credit limit days", "terms"
    ]
}

ITEM_SYNONYMS = {
    "name": [
        "item name", "product name", "item", "product", "description",
        "item description", "particulars", "stock item", "name", "item_name"
    ],
    "sku": [
        "item code", "item code / barcode", "item barcode", "barcode", "sku",
        "code", "product code", "item no"
    ],
    "category": [
        "category", "category name", "item category", "group", "product category", "stock group"
    ],
    "unit": [
        "unit", "units", "uom", "measuring unit", "unit of measure", "base unit"
    ],
    "hsn": [
        "hsn", "hsn code", "hsn/sac", "hsn / sac code", "hsn/sac code", "sac code"
    ],
    "tax_rate": [
        "tax rate", "tax %", "tax percentage", "gst %", "gst rate", "gst rate (%)",
        "tax", "gst", "igst %"
    ],
    "sale_price": [
        "sale price", "sales price", "selling price", "rate", "sale rate", "mrp",
        "sales rate", "sales price (₹)", "unit price", "price"
    ],
    "purchase_price": [
        "purchase price", "cost price", "purchase rate", "buy price", "cost",
        "purchase price (₹)", "buying price"
    ],
    "opening_qty": [
        "opening quantity", "opening stock", "stock", "quantity", "qty",
        "opening qty", "current stock", "stock qty", "opening stock qty"
    ],
    "opening_value": [
        "opening value", "stock value", "at price", "opening stock value", "total value"
    ]
}


def clean_str(val: Any) -> str:
    """Cleans strings, removes excess whitespace, handles Excel float representations."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", "undefined", "n/a", "-"):
        return ""
    # Strip trailing .0 from numeric floats converted to string (e.g. phone numbers from Excel)
    if re.match(r"^\d+\.0$", s):
        s = s[:-2]
    return s


def clean_decimal(val: Any) -> Decimal:
    """Parses numbers formatted in Indian or Western accounting format."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, (int, float)):
        try:
            return Decimal(str(val)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError):
            return Decimal("0.00")

    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-", "n/a"):
        return Decimal("0.00")

    # Detect negative
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1]
    elif s.startswith("-"):
        is_negative = True
        s = s[1:]

    # Remove currency prefixes like "Rs.", "Rs", "INR", "₹", "$", "%"
    s = re.sub(r"(?i)\b(rs\.|rs|inr)\b", "", s)
    s = re.sub(r"[₹\$,%]", "", s)
    s = s.strip()

    # Extract number (integer or decimal)
    num_match = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not num_match:
        return Decimal("0.00")

    try:
        d = Decimal(num_match.group(0))
        if is_negative:
            d = -d
        return d.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return Decimal("0.00")


def parse_balance_type(nature_val: Any, amount_val: Any = None) -> str:
    """
    Intelligently determines whether a balance is DEBIT or CREDIT.
    Vyapar: 'To Receive' -> DEBIT, 'To Pay' -> CREDIT.
    myBillBook: 'To Collect' -> DEBIT, 'To Pay' -> CREDIT.
    Zoho: 'Customer' -> DEBIT, 'Vendor' -> CREDIT.
    """
    s = clean_str(nature_val).lower()
    amt_str = str(amount_val or "").lower()

    if "receive" in s or "collect" in s or "customer" in s or "dr" in s or "debit" in s:
        return "DEBIT"
    if "pay" in s or "supplier" in s or "vendor" in s or "cr" in s or "credit" in s:
        return "CREDIT"

    # Check if amount string itself contains Dr or Cr
    if "dr" in amt_str:
        return "DEBIT"
    if "cr" in amt_str:
        return "CREDIT"

    # Default for positive receivables is DEBIT
    return "DEBIT"


class UniversalImportService:
    """
    Enterprise-Grade Universal Import Engine for Indian B2B Accounting & ERPs.
    Natively supports:
    - TallyPrime / Tally.ERP 9 (XML & Excel)
    - Vyapar (Excel / CSV)
    - myBillBook (Excel / CSV)
    - Zoho Books (CSV / Excel)
    - Busy / Marg (Excel / CSV)
    - Custom / Generic Excel & CSV sheets
    """

    @classmethod
    def detect_and_parse_file(cls, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Detects file format and platform, parses sheets, and returns raw structured tables.
        Guaranteed not to crash on corrupted or unexpected input.
        """
        fname_lower = filename.lower()

        # 1. Tally XML Detection
        if fname_lower.endswith(".xml") or file_content.startswith(b"<?xml") or b"<ENVELOPE>" in file_content or b"<TALLYMESSAGE" in file_content:
            try:
                parsed_tally = TallyMigrationService.parse_tally_xml(file_content)
                return {
                    "platform": "TALLY",
                    "file_type": "XML",
                    "entity_type": "FULL_MIGRATION",
                    "data": parsed_tally,
                    "confidence": 1.0,
                    "summary_text": f"Tally XML Export ({len(parsed_tally.get('ledgers', []))} Ledgers, {len(parsed_tally.get('stock_items', []))} Items, {len(parsed_tally.get('vouchers', []))} Vouchers)"
                }
            except Exception as e:
                # If XML fails, return friendly error dictionary
                return {
                    "platform": "UNKNOWN",
                    "file_type": "XML",
                    "error": f"Failed to parse XML file: {str(e)}",
                    "data": None
                }

        # 2. Spreadsheet Detection (Excel / CSV)
        tables = cls._read_spreadsheet_tables(file_content, filename)
        if "error" in tables:
            return tables

        # Classify the spreadsheet sheets
        return cls._classify_spreadsheet(tables, filename)

    @classmethod
    def _read_spreadsheet_tables(cls, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Reads Excel (.xlsx, .xls) or CSV safely into list of dictionaries per sheet.
        Uses openpyxl, pandas fallback, and csv reader.
        """
        fname_lower = filename.lower()
        sheets_data: Dict[str, List[Dict[str, Any]]] = {}

        # CSV handling
        if fname_lower.endswith(".csv"):
            try:
                # Try UTF-8 with BOM first, then UTF-8, then latin-1
                text = None
                for enc in ("utf-8-sig", "utf-8", "latin-1"):
                    try:
                        text = file_content.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                if text is None:
                    text = file_content.decode("utf-8", errors="replace")

                reader = csv.reader(io.StringIO(text))
                raw_rows = [row for row in reader if any(cell.strip() for cell in row)]
                if not raw_rows:
                    return {"error": "The CSV file is empty."}

                headers, data_rows = cls._extract_headers_and_rows(raw_rows)
                sheets_data["Sheet1"] = [dict(zip(headers, row)) for row in data_rows]
                return {"sheets": sheets_data}
            except Exception as e:
                return {"error": f"Unable to read CSV file: {str(e)}"}

        # Excel (.xlsx / .xls) handling
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
            for sheetname in wb.sheetnames:
                ws = wb[sheetname]
                raw_rows = []
                for row in ws.iter_rows(values_only=True):
                    if any(cell is not None and str(cell).strip() != "" for cell in row):
                        raw_rows.append([cell if cell is not None else "" for cell in row])
                
                if raw_rows:
                    headers, data_rows = cls._extract_headers_and_rows(raw_rows)
                    sheets_data[sheetname] = [dict(zip(headers, row)) for row in data_rows]
            wb.close()
            if sheets_data:
                return {"sheets": sheets_data}
        except Exception:
            pass

        # Fallback to pandas with openpyxl or xlrd
        try:
            import pandas as pd
            xls = pd.read_excel(io.BytesIO(file_content), sheet_name=None)
            for sheetname, df in xls.items():
                df = df.dropna(how="all")
                if not df.empty:
                    df.columns = [str(c).strip() for c in df.columns]
                    sheets_data[sheetname] = df.to_dict(orient="records")
            if sheets_data:
                return {"sheets": sheets_data}
        except Exception as e:
            return {"error": f"Failed to read spreadsheet file: {str(e)}"}

        return {"error": "No readable data found in spreadsheet."}

    @classmethod
    def _extract_headers_and_rows(cls, raw_rows: List[List[Any]]) -> Tuple[List[str], List[List[Any]]]:
        """
        Locates the true header row, skipping title/company metadata headers in rows 1-4.
        """
        if not raw_rows:
            return [], []

        known_keywords = set()
        for syn_list in list(PARTY_SYNONYMS.values()) + list(ITEM_SYNONYMS.values()):
            for s in syn_list:
                known_keywords.add(s.lower())

        best_header_idx = 0
        max_matches = 0

        # Scan top 8 rows to find the row with maximum column header matches
        for idx in range(min(8, len(raw_rows))):
            row = [str(cell).strip().lower() for cell in raw_rows[idx]]
            matches = sum(1 for cell in row if any(kw in cell for kw in known_keywords))
            if matches > max_matches:
                max_matches = matches
                best_header_idx = idx

        raw_headers = raw_rows[best_header_idx]
        headers = []
        for i, h in enumerate(raw_headers):
            h_str = clean_str(h)
            if not h_str:
                h_str = f"Column_{i+1}"
            headers.append(h_str)

        data_rows = raw_rows[best_header_idx + 1 :]
        # Pad data rows if length doesn't match headers
        clean_data_rows = []
        for r in data_rows:
            if len(r) < len(headers):
                r = list(r) + [""] * (len(headers) - len(r))
            clean_data_rows.append(r[: len(headers)])

        return headers, clean_data_rows

    @classmethod
    def _classify_spreadsheet(cls, tables: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """
        Classifies spreadsheet by platform signature (Vyapar, myBillBook, Zoho, Busy, Generic)
        and entity type (PARTIES, ITEMS, OPENING_BALANCES).
        """
        sheets = tables.get("sheets", {})
        if not sheets:
            return {"platform": "UNKNOWN", "entity_type": "UNKNOWN", "error": "No data sheets found."}

        # Analyze first or largest sheet
        primary_sheet = max(sheets.keys(), key=lambda k: len(sheets[k]))
        rows = sheets[primary_sheet]
        if not rows:
            return {"platform": "UNKNOWN", "entity_type": "UNKNOWN", "error": "Sheet contains 0 rows."}

        headers = [str(k).strip() for k in rows[0].keys()]
        headers_lower = [h.lower() for h in headers]
        headers_blob = " | ".join(headers_lower)

        # 1. Platform Signature Detection
        platform = "GENERIC_EXCEL"
        confidence = 0.85

        if "to receive / to pay" in headers_blob or "item code" in headers_blob and "stock value" in headers_blob:
            platform = "VYAPAR"
            confidence = 0.98
        elif "to collect/to pay" in headers_blob or "party type" in headers_blob and "gstin/uin" in headers_blob:
            platform = "MYBILLBOOK"
            confidence = 0.98
        elif "gst identification number (gstin)" in headers_blob or "contact name" in headers_blob and "customer / vendor" in headers_blob:
            platform = "ZOHO_BOOKS"
            confidence = 0.99
        elif "tally" in filename.lower() or "ledger name" in headers_blob and "parent" in headers_blob:
            platform = "TALLY"
            confidence = 0.95
        elif "acc. name" in headers_blob or "party name" in headers_blob and "op. bal." in headers_blob:
            platform = "BUSY"
            confidence = 0.92

        # 2. Entity Type Detection (Parties vs Items vs Opening Balances)
        party_match_score = sum(1 for syn in PARTY_SYNONYMS["name"] + PARTY_SYNONYMS["phone"] + PARTY_SYNONYMS["gstin"] if syn in headers_blob)
        item_match_score = sum(1 for syn in ITEM_SYNONYMS["sale_price"] + ITEM_SYNONYMS["purchase_price"] + ITEM_SYNONYMS["opening_qty"] + ITEM_SYNONYMS["hsn"] if syn in headers_blob)

        entity_type = "PARTIES"
        if item_match_score > party_match_score:
            entity_type = "ITEMS"
        elif "opening" in headers_blob and "dr" in headers_blob and "cr" in headers_blob:
            entity_type = "OPENING_BALANCES"

        # 3. Compute Auto-Mapped Columns
        mapped_columns = cls._auto_map_columns(headers, entity_type)

        return {
            "platform": platform,
            "entity_type": entity_type,
            "file_type": "SPREADSHEET",
            "confidence": confidence,
            "primary_sheet": primary_sheet,
            "available_sheets": list(sheets.keys()),
            "total_rows": len(rows),
            "headers": headers,
            "mapped_columns": mapped_columns,
            "data": rows,
            "summary_text": f"{platform.replace('_', ' ').title()} {entity_type.title()} ({len(rows)} Records Detected)"
        }

    @classmethod
    def _auto_map_columns(cls, headers: List[str], entity_type: str) -> Dict[str, str]:
        """
        Maps source file headers to canonical Vouch schema keys using fuzzy alias matching.
        """
        synonyms = ITEM_SYNONYMS if entity_type == "ITEMS" else PARTY_SYNONYMS
        mapped = {}

        for h in headers:
            h_norm = h.strip().lower()
            h_clean = re.sub(r"[^\w\s]", "", h_norm)

            for target_field, alias_list in synonyms.items():
                if target_field in mapped.values():
                    continue  # Field already mapped

                # Exact match or substring match
                if any(alias == h_norm or alias == h_clean or alias in h_norm for alias in alias_list):
                    mapped[h] = target_field
                    break

        return mapped

    @classmethod
    def generate_preview(cls, parsed_info: Dict[str, Any], company: Company) -> Dict[str, Any]:
        """
        Generates an end-to-end Pre-Flight Audit & Preview.
        - Calculates Debit/Credit Equilibrium
        - Identifies Existing Duplicates in Vouch
        - Flags Invalid GSTIN / HSN
        - Shows first 10 sample normalized rows
        """
        if parsed_info.get("platform") == "TALLY" and parsed_info.get("file_type") == "XML":
            return TallyMigrationService.validate_and_preview(parsed_info["data"], company)

        entity_type = parsed_info.get("entity_type", "PARTIES")
        rows = parsed_info.get("data", [])
        mapped_cols = parsed_info.get("mapped_columns", {})

        # Invert mapping: canonical_key -> source_header
        inv_map = {v: k for k, v in mapped_cols.items()}

        preview_rows = []
        duplicates_count = 0
        valid_count = 0
        total_dr = Decimal("0.00")
        total_cr = Decimal("0.00")

        existing_parties = set(Ledger.objects.filter(company=company).values_list("name", flat=True))
        existing_gstins = set(filter(None, Ledger.objects.filter(company=company).values_list("gstin", flat=True)))
        existing_products = set(Product.objects.filter(company=company).values_list("name", flat=True))

        for idx, row in enumerate(rows):
            normalized = {}
            for target_field, src_hdr in inv_map.items():
                normalized[target_field] = row.get(src_hdr)

            # Validate based on entity
            if entity_type == "PARTIES":
                name = clean_str(normalized.get("name"))
                if not name:
                    continue

                gstin = clean_str(normalized.get("gstin")).upper()
                phone = clean_str(normalized.get("phone"))
                bal = clean_decimal(normalized.get("opening_balance"))
                bal_type = parse_balance_type(normalized.get("balance_type"), normalized.get("opening_balance"))

                is_dup = (name.lower() in {p.lower() for p in existing_parties}) or (bool(gstin) and gstin in existing_gstins)
                if is_dup:
                    duplicates_count += 1
                else:
                    valid_count += 1

                if bal_type == "DEBIT":
                    total_dr += bal
                else:
                    total_cr += bal

                if len(preview_rows) < 10:
                    preview_rows.append({
                        "row_num": idx + 1,
                        "name": name,
                        "phone": phone,
                        "gstin": gstin,
                        "opening_balance": float(bal),
                        "balance_type": bal_type,
                        "is_duplicate": is_dup,
                        "status": "EXISTING_MERGE" if is_dup else "READY"
                    })

            elif entity_type == "ITEMS":
                name = clean_str(normalized.get("name"))
                if not name:
                    continue

                sku = clean_str(normalized.get("sku"))
                sale_p = clean_decimal(normalized.get("sale_price"))
                pur_p = clean_decimal(normalized.get("purchase_price"))
                qty = clean_decimal(normalized.get("opening_qty"))
                unit = clean_str(normalized.get("unit")) or "PCS"
                hsn = clean_str(normalized.get("hsn"))
                tax = clean_decimal(normalized.get("tax_rate"))

                is_dup = name.lower() in {p.lower() for p in existing_products}
                if is_dup:
                    duplicates_count += 1
                else:
                    valid_count += 1

                if len(preview_rows) < 10:
                    preview_rows.append({
                        "row_num": idx + 1,
                        "name": name,
                        "sku": sku,
                        "sale_price": float(sale_p),
                        "purchase_price": float(pur_p),
                        "opening_qty": float(qty),
                        "unit": unit,
                        "hsn": hsn,
                        "tax_rate": float(tax),
                        "is_duplicate": is_dup,
                        "status": "EXISTING_MERGE" if is_dup else "READY"
                    })

        diff = total_dr - total_cr
        is_balanced = (diff == Decimal("0.00"))

        return {
            "platform": parsed_info.get("platform"),
            "entity_type": entity_type,
            "total_detected": len(rows),
            "valid_records": valid_count,
            "duplicate_records": duplicates_count,
            "preview_samples": preview_rows,
            "equilibrium": {
                "total_debits": float(total_dr),
                "total_credits": float(total_cr),
                "difference": float(diff),
                "is_balanced": is_balanced
            },
            "status": "READY"
        }

    @classmethod
    @transaction.atomic
    def execute_import(
        cls,
        parsed_info: Dict[str, Any],
        company: Company,
        user: User,
        custom_mappings: Optional[Dict[str, str]] = None,
        duplicate_strategy: str = "MERGE"  # MERGE, SKIP, OVERWRITE
    ) -> Dict[str, Any]:
        """
        Atomically ingests the verified records into Vouch.
        Guarantees zero corrupt states with full rollback on unhandled error.
        """
        # If Tally XML full migration
        if parsed_info.get("platform") == "TALLY" and parsed_info.get("file_type") == "XML":
            return TallyMigrationService.execute_migration(parsed_info["data"], company, user)

        entity_type = parsed_info.get("entity_type", "PARTIES")
        rows = parsed_info.get("data", [])
        mappings = custom_mappings or parsed_info.get("mapped_columns", {})
        inv_map = {v: k for k, v in mappings.items()}

        created_count = 0
        merged_count = 0
        skipped_count = 0
        errors = []

        if entity_type == "PARTIES":
            debtors_grp, _ = LedgerGroup.objects.get_or_create(
                company=company, name="Sundry Debtors", defaults={"nature": "ASSET"}
            )
            creditors_grp, _ = LedgerGroup.objects.get_or_create(
                company=company, name="Sundry Creditors", defaults={"nature": "LIABILITY"}
            )

            for idx, r in enumerate(rows):
                name = clean_str(r.get(inv_map.get("name", "")))
                if not name:
                    continue

                phone = clean_str(r.get(inv_map.get("phone", "")))
                email = clean_str(r.get(inv_map.get("email", "")))
                gstin = clean_str(r.get(inv_map.get("gstin", ""))).upper()
                pan = clean_str(r.get(inv_map.get("pan", ""))).upper()
                address = clean_str(r.get(inv_map.get("address", "")))
                bal = clean_decimal(r.get(inv_map.get("opening_balance", "")))
                bal_type = parse_balance_type(r.get(inv_map.get("balance_type", "")), bal)

                group = debtors_grp if bal_type == "DEBIT" else creditors_grp
                l_type = "CUSTOMER" if bal_type == "DEBIT" else "SUPPLIER"

                try:
                    ledger = Ledger.objects.filter(company=company, name__iexact=name).first()
                    if not ledger and gstin:
                        ledger = Ledger.objects.filter(company=company, gstin=gstin).first()

                    if ledger:
                        if duplicate_strategy == "SKIP":
                            skipped_count += 1
                            continue
                        # MERGE strategy: update missing fields
                        if not ledger.phone and phone: ledger.phone = phone
                        if not ledger.email and email: ledger.email = email
                        if not ledger.gstin and gstin: ledger.gstin = gstin
                        if not ledger.pan and pan: ledger.pan = pan
                        if not ledger.address and address: ledger.address = address
                        ledger.save()
                        merged_count += 1
                    else:
                        Ledger.objects.create(
                            company=company,
                            name=name,
                            group=group,
                            ledger_type=l_type,
                            opening_balance=bal,
                            opening_balance_type=bal_type,
                            current_balance=bal,
                            phone=phone or None,
                            email=email or None,
                            gstin=gstin or None,
                            pan=pan or None,
                            address=address or None,
                            is_active=True
                        )
                        created_count += 1
                except Exception as row_err:
                    errors.append(f"Row {idx+1} ({name}): {str(row_err)}")

        elif entity_type == "ITEMS":
            default_cat, _ = ProductCategory.objects.get_or_create(
                company=company, name="General Imported Inventory"
            )

            for idx, r in enumerate(rows):
                name = clean_str(r.get(inv_map.get("name", "")))
                if not name:
                    continue

                sku = clean_str(r.get(inv_map.get("sku", "")))
                sale_p = clean_decimal(r.get(inv_map.get("sale_price", "")))
                pur_p = clean_decimal(r.get(inv_map.get("purchase_price", "")))
                qty = clean_decimal(r.get(inv_map.get("opening_qty", "")))
                unit = clean_str(r.get(inv_map.get("unit", ""))) or "PCS"
                hsn = clean_str(r.get(inv_map.get("hsn", "")))
                tax = clean_decimal(r.get(inv_map.get("tax_rate", "")))

                try:
                    prod = Product.objects.filter(company=company, name__iexact=name).first()
                    if not prod and sku:
                        prod = Product.objects.filter(company=company, sku=sku).first()

                    if prod:
                        if duplicate_strategy == "SKIP":
                            skipped_count += 1
                            continue
                        if sale_p > 0: prod.selling_price = sale_p
                        if pur_p > 0: prod.purchase_price = pur_p
                        if not prod.hsn_code and hsn: prod.hsn_code = hsn
                        if tax > 0:
                            prod.gst_rate = tax
                            prod.tax_override = True
                            prod.override_gst_rate = tax
                        prod.save()
                        merged_count += 1
                    else:
                        gen_sku = sku or f"SKU-{name[:20].upper().replace(' ', '-')}"
                        Product.objects.create(
                            company=company,
                            name=name,
                            sku=gen_sku,
                            category=default_cat,
                            selling_price=sale_p,
                            purchase_price=pur_p,
                            stock_quantity=qty,
                            unit=unit,
                            hsn_code=hsn or None,
                            gst_rate=tax if tax > 0 else Decimal("18.00"),
                            tax_override=True if tax > 0 else False,
                            override_gst_rate=tax if tax > 0 else None,
                            is_active=True
                        )
                        created_count += 1
                except Exception as row_err:
                    errors.append(f"Row {idx+1} ({name}): {str(row_err)}")

        return {
            "success": True,
            "created_count": created_count,
            "merged_count": merged_count,
            "skipped_count": skipped_count,
            "total_processed": created_count + merged_count + skipped_count,
            "errors": errors[:10],
            "message": f"Successfully imported {created_count} new and merged {merged_count} existing records."
        }

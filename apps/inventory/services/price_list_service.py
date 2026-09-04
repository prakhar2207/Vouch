import os
import re
import uuid
import json
from decimal import Decimal
from django.db import transaction
from apps.companies.models import Company
from apps.inventory.models import Product, ProductCategory

CID_MAP = str.maketrans({
    'Ϭ': '0', 'ϭ': '1', 'Ϯ': '2', 'ϯ': '3', 'ϰ': '4',
    'ϱ': '5', 'ϲ': '6', 'ϳ': '7', 'ϴ': '8', 'ϵ': '9',
    '͘': '.', 'Ͳ': '-', 'ͬ': '/', 'н': '+',
})

class PriceListService:
    @staticmethod
    @transaction.atomic
    def bulk_import_price_list(company: Company, category_id: str, brand: str, items_data: list):
        """
        Bulk creates or updates products under a specific category and brand from a price list.
        """
        category = ProductCategory.objects.get(id=category_id, company=company)
        brand_clean = (brand or "").strip()
        
        created_count = 0
        updated_count = 0
        
        for item in items_data:
            raw_name = str(item.get("name") or item.get("item_name") or "").strip()
            if not raw_name:
                continue
                
            selling_price = Decimal(str(item.get("selling_price") or item.get("mrp") or item.get("price") or "0.00"))
            purchase_price = Decimal(str(item.get("purchase_price") or item.get("rate") or "0.00"))
            opening_qty = Decimal(str(item.get("opening_qty") or item.get("stock") or "0.00"))
            unit = (item.get("unit") or "PCS").strip().upper()
            section = (item.get("section") or item.get("description") or "").strip()
            case_qty = item.get("case_qty")
            
            desc_parts = []
            if section:
                desc_parts.append(section)
            if case_qty and int(case_qty) > 1:
                desc_parts.append(f"Case Qty: {case_qty}")
            final_desc = " | ".join(desc_parts)

            existing = Product.objects.filter(
                company=company,
                category=category,
                name__iexact=raw_name,
                brand__iexact=brand_clean
            ).first()
            
            if existing:
                existing.selling_price = selling_price
                # Prioritise purchase price from purchase invoice instead of price list
                if not getattr(existing, 'purchase_price_from_invoice', False):
                    if purchase_price > Decimal("0.00"):
                        existing.purchase_price = purchase_price
                # IMPORTANT: Never touch existing.stock_quantity when re-uploading a price list!
                if final_desc:
                    existing.description = final_desc
                existing.save()
                updated_count += 1
            else:
                clean_name = re.sub(r'[^A-Za-z0-9]', '', raw_name)[:6].upper()
                clean_b = re.sub(r'[^A-Za-z0-9]', '', brand_clean)[:4].upper()
                sku = f"{clean_name}-{clean_b}-{uuid.uuid4().hex[:6].upper()}"
                
                Product.objects.create(
                    company=company,
                    category=category,
                    name=raw_name,
                    brand=brand_clean,
                    sku=sku,
                    unit=unit,
                    selling_price=selling_price,
                    purchase_price=purchase_price,
                    purchase_price_from_invoice=False,
                    stock_quantity=Decimal("0.00"),
                    description=final_desc,
                    hsn_code=category.hsn_code or "",
                    gst_rate=category.gst_rate or Decimal("18.00")
                )
                created_count += 1
                
        return {
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "total": created_count + updated_count,
            "category_name": category.name,
            "brand": brand_clean
        }

    @staticmethod
    def infer_belt_or_bearing_section(item_name: str, active_section: str = "") -> str:
        n = item_name.upper().strip()
        if n.startswith("A ") or n.startswith("A-"):
            return 'A SECTION (13 x 8 mm)'
        elif n.startswith("B ") or n.startswith("B-"):
            return 'B SECTION (17 x 11 mm)'
        elif n.startswith("C ") or n.startswith("C-"):
            return 'C SECTION (22 x 14 mm)'
        elif n.startswith("D ") or n.startswith("D-"):
            return 'D SECTION (32 x 19 mm)'
        elif n.startswith("BB ") or n.startswith("BB-") or n.startswith("BB"):
            return 'BB SECTION (17 x 14 mm)'
        elif n.startswith("FHP"):
            return 'FHP SECTION'
        elif n.startswith("SPZ"):
            return 'SPZ SECTION (10 x 8 mm)'
        elif n.startswith("SPA"):
            return 'SPA SECTION (13 x 10 mm)'
        elif n.startswith("SPB"):
            return 'SPB SECTION (17 x 14 mm)'
        elif n.startswith("SPC"):
            return 'SPC SECTION (22 x 18 mm)'
        return active_section or "Standard"

    @staticmethod
    def parse_pdf_price_list(file_obj, custom_api_key: str = None, filename: str = ""):
        """
        Parses manufacturer/distributor price list PDFs.
        Supports both:
        1. Gemini Vision AI OCR (when key is available)
        2. High-speed multi-column deterministic tokenizer with custom CID font decoding (works offline)
        """
        raw_bytes = file_obj.read()
        file_obj.seek(0)
        fname = filename or getattr(file_obj, "name", "")
        
        # Tier 1: Try Gemini Vision AI if API key is provided or set in environment
        active_key = custom_api_key or os.environ.get("GEMINI_API_KEY")
        if active_key and len(raw_bytes) < 20 * 1024 * 1024:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=active_key)
                
                prompt = (
                    "You are an expert industrial catalog AI. Analyze this manufacturer price list PDF. "
                    "Extract the Brand Name, Effective Date (w.e.f.), and ALL items across all columns and pages. "
                    "For each item extract: "
                    "- item_name: (clean title, bearing number, or belt size e.g. 'A 18', '6204', 'NBC AP3 GREASE 100GM') "
                    "- mrp: (numerical price in INR) "
                    "- case_qty: (packaging quantity or MOQ if given, default 1) "
                    "- section: (section or category e.g. 'Deep Groove Ball Bearings', 'A SECTION (13 x 8 mm)') "
                    "- unit: (default 'PCS') "
                    "Return strict JSON matching: "
                    "{\"brand\": string, \"effective_date\": string, \"items\": [{\"item_name\": string, \"mrp\": number, \"case_qty\": number, \"section\": string, \"unit\": string}]}"
                )
                
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[
                        types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf"),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0
                    )
                )
                
                parsed_json = json.loads(response.text)
                if isinstance(parsed_json, dict) and "items" in parsed_json and len(parsed_json["items"]) > 0:
                    formatted_items = []
                    for it in parsed_json["items"]:
                        mrp = float(it.get("mrp") or 0)
                        formatted_items.append({
                            "name": str(it.get("item_name") or "").strip(),
                            "mrp": mrp,
                            "purchase_price": round(mrp * 0.70, 2),
                            "case_qty": int(it.get("case_qty") or 1),
                            "section": str(it.get("section") or "").strip(),
                            "unit": str(it.get("unit") or "PCS").strip().upper(),
                            "opening_qty": 0
                        })
                    return {
                        "success": True,
                        "brand": parsed_json.get("brand") or "",
                        "effective_date": parsed_json.get("effective_date") or "",
                        "source": "AI_GEMINI_VISION",
                        "items": formatted_items,
                        "total_extracted": len(formatted_items)
                    }
            except Exception as e:
                print(f"[PriceListService] Gemini Vision fallback: {e}")

        # Tier 2: Deterministic Multi-Column Tokenizer with CID Font Decoding
        import pypdf
        import io
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        extracted_items = []
        seen_names = set()
        
        detected_brand = ""
        effective_date = ""
        current_section = ""

        brand_candidates = ["PIX", "NBC", "SKF", "FENNER", "GATES", "TIMKEN", "FAG", "NTN", "KOYO", "SCHAEFFLER"]

        # Check filename for brand
        for b in brand_candidates:
            if re.search(r'\b' + b + r'\b', fname, re.IGNORECASE):
                detected_brand = b
                break

        full_text_sample = ""
        for page_idx in range(min(5, len(reader.pages))):
            raw_t = reader.pages[page_idx].extract_text() or ""
            full_text_sample += " " + raw_t.translate(CID_MAP)

        if not detected_brand:
            for b in brand_candidates:
                if re.search(r'\b' + b + r'\b', full_text_sample, re.IGNORECASE):
                    detected_brand = b
                    break

        wef_match = re.search(r'w\.?e\.?f\.?[:\s]+([^\n\r,]+(?:,\s*\d{4})?)', full_text_sample, re.IGNORECASE)
        if wef_match:
            effective_date = wef_match.group(1).strip()

        for page in reader.pages:
            raw_page_text = page.extract_text() or ""
            # Apply CID font decoding to translate custom encoded digits & symbols
            page_text = raw_page_text.translate(CID_MAP)
            lines = page_text.split("\n")
            
            for line in lines:
                line_clean = line.strip()
                if not line_clean:
                    continue

                # Section headers
                if any(sec in line_clean.upper() for sec in ["SECTION", "BEARING", "SLEEVE", "GREASE", "TOOL", "SERIES", "INDEX"]):
                    if not re.search(r'\d+\.\d{2}', line_clean) and len(line_clean) < 100:
                        current_section = line_clean
                        continue

                # Strategy 1: [Item] [Price] [CaseQty] multi-column (e.g. NBC Bearings)
                three_col = re.findall(
                    r'([A-Za-z0-9<>\-\/\.\s]{2,30}?)\s+([0-9]+(?:\.[0-9]{1,2})?)\s+([0-9]{1,4})(?=\s+[A-Za-z0-9<>]|\s*$)',
                    line_clean
                )
                if three_col and len(three_col) > 0:
                    for m in three_col:
                        name = m[0].strip()
                        try:
                            price = float(m[1])
                            case_qty = int(m[2])
                        except:
                            continue
                        if len(name) >= 2 and price > 0 and name not in seen_names:
                            seen_names.add(name)
                            extracted_items.append({
                                "name": name,
                                "mrp": price,
                                "purchase_price": round(price * 0.70, 2),
                                "case_qty": case_qty,
                                "section": PriceListService.infer_belt_or_bearing_section(name, current_section),
                                "unit": "PCS",
                                "opening_qty": 0
                            })
                    continue

                # Strategy 2: [Item] [Price] multi-column (e.g. PIX V-Belts)
                two_col = re.findall(
                    r'([A-Za-z0-9\-\/\.]{1,15}(?:\s+[A-Za-z0-9\-\/\.]{1,10})?)\s+([0-9]+(?:\.[0-9]{1,2})?)(?=\s+[A-Za-z]|\s*$)',
                    line_clean
                )
                if two_col and len(two_col) > 0:
                    for m in two_col:
                        name = m[0].strip()
                        try:
                            price = float(m[1])
                        except:
                            continue
                        if len(name) >= 2 and price > 0 and name not in seen_names:
                            seen_names.add(name)
                            extracted_items.append({
                                "name": name,
                                "mrp": price,
                                "purchase_price": round(price * 0.70, 2),
                                "case_qty": 1,
                                "section": PriceListService.infer_belt_or_bearing_section(name, current_section),
                                "unit": "PCS",
                                "opening_qty": 0
                            })
                    continue

        return {
            "success": True,
            "brand": detected_brand,
            "effective_date": effective_date,
            "source": "MULTI_COLUMN_DETERMINISTIC",
            "items": extracted_items,
            "total_extracted": len(extracted_items)
        }

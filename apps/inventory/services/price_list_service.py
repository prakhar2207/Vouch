import os
import re
import uuid
import json
from decimal import Decimal
from django.db import transaction
from apps.companies.models import Company
from apps.inventory.models import Product, ProductCategory

class PriceListService:
    @staticmethod
    @transaction.atomic
    def bulk_import_price_list(company: Company, category_id: str, brand: str, items_data: list):
        """
        Bulk creates or updates products under a specific category and brand from a price list.
        Preserves single item name identity while attaching brand-specific MRP, purchase price,
        and description/section notes.
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

            # Check if this exact item name + brand already exists
            existing = Product.objects.filter(
                company=company,
                category=category,
                name__iexact=raw_name,
                brand__iexact=brand_clean
            ).first()
            
            if existing:
                existing.selling_price = selling_price
                if purchase_price > Decimal("0.00"):
                    existing.purchase_price = purchase_price
                if opening_qty > Decimal("0.00") and existing.stock_quantity == Decimal("0.00"):
                    existing.stock_quantity = opening_qty
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
                    stock_quantity=opening_qty,
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
    def parse_pdf_price_list(file_obj):
        """
        Parses PDF price lists (both multi-column like PIX/NBC and standard table lists).
        Attempts Gemini AI first if configured, then falls back to intelligent multi-column regex parsing.
        """
        raw_bytes = file_obj.read()
        file_obj.seek(0)
        
        # Tier 1: Try Gemini AI Vision/Document Parser if GEMINI_API_KEY is configured
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key and len(raw_bytes) < 15 * 1024 * 1024:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                
                prompt = (
                    "You are an expert product catalog AI. Analyze this manufacturer/distributor price list PDF. "
                    "Extract the Brand Name, Effective Date (w.e.f.), and a clean list of all items with their "
                    "Item Name/Bearing No./Size, MRP / List Price (in INR), Case Quantity / MOQ (if mentioned), "
                    "Section/Category (e.g. 'Deep Groove Ball Bearings', 'A Section 13x8mm'), and Unit (default PCS). "
                    "Output JSON matching: "
                    "{\"brand\": string, \"effective_date\": string, \"items\": [{\"item_name\": string, \"mrp\": number, \"case_qty\": number, \"section\": string, \"unit\": string}]}"
                )
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
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
                            "purchase_price": round(mrp * 0.70, 2), # Default 30% trade discount
                            "case_qty": it.get("case_qty") or 1,
                            "section": str(it.get("section") or "").strip(),
                            "unit": str(it.get("unit") or "PCS").strip().upper(),
                            "opening_qty": 0
                        })
                    return {
                        "success": True,
                        "brand": parsed_json.get("brand") or "",
                        "effective_date": parsed_json.get("effective_date") or "",
                        "source": "AI_GEMINI",
                        "items": formatted_items,
                        "total_extracted": len(formatted_items)
                    }
            except Exception as e:
                print(f"[PriceListService] Gemini parsing fallback: {e}")

        # Tier 2: Deterministic High-Precision Multi-Column Parser using pypdf
        import pypdf
        import io
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        extracted_items = []
        seen_names = set()
        
        detected_brand = ""
        effective_date = ""
        current_section = ""

        full_text_sample = ""
        for page_idx in range(min(5, len(reader.pages))):
            full_text_sample += " " + (reader.pages[page_idx].extract_text() or "")

        # Detect brand from header
        brand_candidates = ["PIX", "NBC", "SKF", "FENNER", "GATES", "TIMKEN", "FAG", "NTN", "KOYO", "SCHAEFFLER"]
        for b in brand_candidates:
            if re.search(r'\b' + b + r'\b', full_text_sample, re.IGNORECASE):
                detected_brand = b
                break

        # Detect effective date (w.e.f.)
        wef_match = re.search(r'w\.?e\.?f\.?[:\s]+([^\n\r,]+(?:,\s*\d{4})?)', full_text_sample, re.IGNORECASE)
        if wef_match:
            effective_date = wef_match.group(1).strip()

        for page in reader.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")
            
            for line in lines:
                line_clean = line.strip()
                if not line_clean:
                    continue

                # Detect section headers
                if any(sec in line_clean.upper() for sec in ["SECTION", "BEARINGS", "SLEEVE", "GREASE", "TOOLS", "SERIES", "INDEX"]):
                    if not re.search(r'\d+\.\d{2}', line_clean):
                        current_section = line_clean
                        continue

                # Strategy 1: [Item] [Price] [CaseQty] multi-column (e.g. NBC Bearings)
                three_col_matches = re.findall(
                    r'([A-Za-z0-9\-\/\.\s]{2,30}?)\s+([0-9]+(?:\.[0-9]{1,2})?)\s+([0-9]{1,4})(?=\s+[A-Za-z0-9]|\s*$)',
                    line_clean
                )
                if three_col_matches and len(three_col_matches) > 0:
                    for m in three_col_matches:
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
                                "section": current_section,
                                "unit": "PCS",
                                "opening_qty": 0
                            })
                    continue

                # Strategy 2: [Item] [Price] multi-column (e.g. PIX V-Belts)
                two_col_matches = re.findall(
                    r'([A-Za-z0-9\-\/\.]{1,15}(?:\s+[A-Za-z0-9\-\/\.]{1,10})?)\s+([0-9]+(?:\.[0-9]{1,2})?)(?=\s+[A-Za-z]|\s*$)',
                    line_clean
                )
                if two_col_matches and len(two_col_matches) > 0:
                    for m in two_col_matches:
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
                                "section": current_section,
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

import os
import io
import re
import json
import base64
from datetime import datetime
from django.conf import settings
from pydantic import BaseModel, Field
from typing import List, Optional

class InvoiceItemSchema(BaseModel):
    description: str = Field(description="Description or size/model number of the product without redundant category prefix, e.g. 'B 34', 'iPhone 15 128GB Black', 'Galaxy S24 Ultra'")
    category: Optional[str] = Field(default="", description="Inferred category for this specific item if identifiable, e.g. 'V Belts', 'Bearings', 'Smartphones', 'Electronics', 'Laptops'")
    brand: Optional[str] = Field(default="", description="Brand, make, or manufacturer of the item if mentioned on the bill, e.g. Samsung, Apple, Xiaomi, HP, Lenovo, Fenner, SKF, Havells")
    color: Optional[str] = Field(default="", description="Color of the product if mentioned on the invoice, e.g. Titanium Gray, Space Black, Starlight, Midnight Blue, Silver, Gold")
    imei_numbers: List[str] = Field(default_factory=list, description="List of unique 15-digit IMEI numbers or serial numbers for this product")
    serial_numbers: Optional[str] = Field(default="", description="Comma-separated IMEI numbers, serial numbers, or unique device identifiers")
    storage: Optional[str] = Field(default="", description="Internal storage capacity if mentioned, e.g. 128GB, 256GB, 512GB, 1TB")
    ram: Optional[str] = Field(default="", description="RAM capacity if mentioned, e.g. 8GB, 12GB, 16GB")
    warranty: Optional[str] = Field(default="", description="Warranty terms if stated, e.g. 1 Year, 6 Months")
    specifications: Optional[str] = Field(default="", description="Other key specifications, dimensions, or features")
    barcode: Optional[str] = Field(default="", description="Product barcode, EAN, UPC, or printed article code if present on the invoice for this item")
    hsn_code: Optional[str] = Field(default="", description="HSN or SAC code")
    quantity: float = Field(default=1.0, description="Quantity")
    unit: Optional[str] = Field(default="PCS", description="Unit of measurement, e.g., PCS, KG, NOS")
    rate: float = Field(default=0.0, description="Price or unit rate per item (before discount)")
    discount_percent: float = Field(default=0.0, description="Discount percentage applied to this item, e.g. 62 for 62%")
    amount: float = Field(default=0.0, description="Taxable amount for this line item (after discount)")
    gst_rate: Optional[float] = Field(default=18.0, description="GST rate percentage, e.g., 5, 12, 18, 28")

class InvoiceExtractionSchema(BaseModel):
    supplier_name: str = Field(description="Name of the supplier or vendor firm")
    supplier_gstin: Optional[str] = Field(default="", description="GSTIN / UIN of the supplier")
    invoice_number: Optional[str] = Field(default="", description="Invoice or bill number")
    invoice_date: Optional[str] = Field(default="", description="Date of the invoice in YYYY-MM-DD format")
    state_code: Optional[str] = Field(default="", description="2-digit state code of the supplier or place of supply")
    subtotal: float = Field(default=0.0, description="Taxable subtotal amount before tax")
    cgst_amount: Optional[float] = Field(default=0.0, description="CGST amount if applicable")
    sgst_amount: Optional[float] = Field(default=0.0, description="SGST amount if applicable")
    igst_amount: Optional[float] = Field(default=0.0, description="IGST amount if applicable")
    round_off: Optional[float] = Field(default=0.0, description="Round-off amount (+/-) if total differs from subtotal plus taxes")
    total_amount: float = Field(default=0.0, description="Grand total invoice amount")
    category_detected: Optional[str] = Field(default="", description="Dominant item category clearly stated or indicated on the bill (e.g., 'V Belts', 'Bearings', 'Pulleys', 'Hardware'). Empty if not clearly determinable.")
    requires_category_confirmation: bool = Field(default=False, description="Set to True if the bill does not clearly state a category, or if items might belong to multiple or ambiguous categories, so user confirmation is needed.")
    categories_found: List[str] = Field(default_factory=list, description="List of any distinct product categories mentioned or inferred from the document")
    line_items: List[InvoiceItemSchema] = Field(default_factory=list, description="List of invoiced items")

def parse_words_to_number(text: str) -> float:
    """Converts Indian English number words (e.g. 'Thirty Six Thousand Two Hundred Fifty') to a numeric float."""
    try:
        text = text.lower()
        units = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
        tens = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
        scales = {'crore': 10000000, 'crores': 10000000, 'lakh': 100000, 'lakhs': 100000, 'thousand': 1000, 'thousands': 1000, 'hundred': 100, 'hundreds': 100}

        clean = re.sub(r'[^a-z\s]', ' ', text)
        tokens = clean.split()
        total = 0
        sub_total = 0
        for tok in tokens:
            if tok in units:
                sub_total += units[tok]
            elif tok in tens:
                sub_total += tens[tok]
            elif tok in scales:
                mult = scales[tok]
                if sub_total == 0:
                    sub_total = 1
                if mult >= 1000:
                    total += sub_total * mult
                    sub_total = 0
                else:
                    sub_total *= mult
        total += sub_total
        return float(total)
    except Exception:
        return 0.0


class InvoiceOCRService:
    _DEPRECATED_MODELS = {
        "gemini-2.0-flash", 
        "gemini-2.0-flash-lite", 
        "gemini-2-flash", 
        "gemini-2-flash-lite", 
        "gemini-2.5-pro", 
        "gemini-3.1-pro", 
        "gemini-4-argon",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    }

    @classmethod
    def get_candidate_models(cls, scan_mode: str = "auto") -> List[str]:
        """
        Dynamically yields available vision models ordered by active quota,
        filtering out any 0-quota or deprecated models permanently.
        """
        if scan_mode == "handwritten":
            preferred = [
                "gemini-3.6-flash",
                "gemini-3.7-flash",
                "gemini-3-flash",
                "gemini-2.5-flash",
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash-lite",
                "gemini-2.5-flash-lite",
                "gemini-3.8-flash",
            ]
        else:
            # "printed" or "auto": Prioritize 500 RPD / 15 RPM high-quota models first
            preferred = [
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash-lite",
                "gemini-3.6-flash",
                "gemini-3.7-flash",
                "gemini-3-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-3.8-flash",
            ]
        return [m for m in preferred if m not in cls._DEPRECATED_MODELS]

    @staticmethod
    def extract_from_base64(base64_data: str, mime_type: str = "image/png", scan_mode: str = "auto", buyer_state_code: str = "") -> dict:
        """
        Extracts invoice header & line-item details using a Smart Hybrid Multi-Tier architecture:
        Tier 1: Google Gemini Dual-Engine:
                - gemini-3.1-flash-lite / gemini-3.5-flash-lite (high quota 500 RPD, high speed GA)
                - gemini-3.6-flash / gemini-3.8-flash (deep vision reasoning for handwritten, faint, or irregular tables)
        Tier 2: PDF text stream tokenizer using PyPDF (for digital vector PDFs)
        Tier 3: Graceful fallback error reporting
        """
        if "," in base64_data:
            header, base64_data = base64_data.split(",", 1)
            if "pdf" in header:
                mime_type = "application/pdf"
            elif "jpeg" in header or "jpg" in header:
                mime_type = "image/jpeg"
            elif "png" in header:
                mime_type = "image/png"
            elif "webp" in header:
                mime_type = "image/webp"

        try:
            missing_padding = len(base64_data) % 4
            if missing_padding:
                base64_data += '=' * (4 - missing_padding)
            raw_bytes = base64.b64decode(base64_data)
        except Exception:
            raw_bytes = b''

        if raw_bytes:
            if raw_bytes[:4] == b'%PDF':
                mime_type = "application/pdf"
            elif raw_bytes[:4].startswith(b'\x89PNG'):
                mime_type = "image/png"
            elif raw_bytes[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            elif raw_bytes[:4] == b'RIFF' and len(raw_bytes) > 12 and raw_bytes[8:12] == b'WEBP':
                mime_type = "image/webp"

        is_pdf = bool(raw_bytes and ("pdf" in mime_type or raw_bytes[:4] == b'%PDF'))
        last_gemini_error = ""

        # Pre-render PDF pages to high-resolution images for split-view preview
        pdf_preview_images = []
        if is_pdf and raw_bytes:
            try:
                import pymupdf
                doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
                for page_num in range(min(len(doc), 5)):
                    page = doc[page_num]
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("jpeg")
                    b64_img = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode("utf-8")
                    pdf_preview_images.append(b64_img)
            except Exception as pdf_img_err:
                print(f"[PDF Preview Render Warning]: {pdf_img_err}")

        def _attach_pdf_previews(res_dict):
            if pdf_preview_images and isinstance(res_dict, dict):
                res_dict["preview_images"] = pdf_preview_images
                res_dict["preview_image"] = pdf_preview_images[0]
            return res_dict

        # -------------------------------------------------------------
        # TIER 1: Try Gemini Vision AI Dual-Engine
        # -------------------------------------------------------------
        active_key = os.environ.get("GEMINI_API_KEY", "").strip() or getattr(settings, "GEMINI_API_KEY", "")
        if active_key and raw_bytes:
            import time
            import random

            buyer_context = f" The Buyer / Consignee state code is '{buyer_state_code}'." if buyer_state_code else ""
            prompt = (
                "You are an expert accounts payable AI specialized in Indian GST tax invoices, bills of supply, and handwritten or printed purchase receipts."
                f"{buyer_context} "
                "Carefully analyze this entire document image or PDF in-memory. "
                "Key parsing rules: "
                "1. SMART CATEGORY DIFFERENTIATION: Many handwritten or printed bills write a category header at the top or repeat it on lines (e.g. 'V BELT', 'V Belts', 'Bearings', 'Pulleys'). "
                "   DO NOT include the category inside the item description! For example: "
                "   - If the bill heading says 'V BELTS' with items 'B 34', 'B 79', 'C 120', or writes 'V BELT B34': "
                "     Set category_detected = 'V Belts', and set the line item description to clean size/item code: 'B 34' (NOT 'V Belt B34'). "
                "   - If the category cannot be determined with certainty, or if items are mixed/unknown, set requires_category_confirmation = True. "
                "2. Resolve ditto marks (\", '', do, as above) by carrying forward values, rates, or descriptions from the preceding line. "
                "3. Interpret handwriting shorthand, abbreviations (e.g., 'pkg', 'bx', 'mtr', 'nos'), and handwritten digits accurately. "
                "4. Extract the exact Supplier Name, Supplier GSTIN, Invoice/Bill Number, Invoice Date (in YYYY-MM-DD format), Place of Supply / State Code (first 2 digits of supplier GSTIN). "
                "5. Accurately extract all itemized line items: clean Description, Category, Brand (e.g. Samsung, Apple, Xiaomi, HP, Lenovo, Fenner, SKF, PIX), Color (e.g. Titanium Gray, Space Black, Starlight, Midnight Blue, Silver, Gold), HSN code, Quantity, Unit, Rate (MRP or price before discount), Discount Percentage, and Taxable Amount. "
                "   CRITICAL FOR ELECTRONICS, SMARTPHONES, LAPTOPS & APPLIANCES: "
                "   - Extract Color: If color is mentioned (e.g. 'Silver', 'Black', 'Blue', 'Titanium Gray', 'Gold', 'Purple'), populate 'color'. "
                "   - Extract Specifications: Populate 'storage' (e.g. '128GB', '256GB'), 'ram' (e.g. '8GB', '12GB'), 'warranty' (e.g. '1 Year', '6 Months'), and 'specifications'. "
                "   - Extract All IMEI / Serial Numbers: In electronics shops, 1 product line item may have quantity 1, 2, or 5 with distinct 15-digit IMEI numbers (IMEI 1, IMEI 2) or Serial Numbers (S/N) listed on the line or below it. Extract all individual 15-digit IMEI numbers into 'imei_numbers' array AND list them comma-separated in 'serial_numbers'. "
                "   - In 'description', include the clean product name with specifications (e.g. 'Samsung S24 Ultra 256GB (Titanium Gray)'). "
                "   - If Barcode / EAN / UPC is printed, extract into 'barcode'."
                "6. TAX BREAKDOWN & GST DETECTION: Carefully inspect the bottom tax summary box, handwritten tax rows, or stamps. "
                "   - If Supplier State != Buyer State (or different states), this is an INTER-STATE supply -> ALL tax is IGST. Set igst_amount to the full tax amount, and set cgst_amount = 0, sgst_amount = 0. "
                "   - If Supplier State == Buyer State, this is an INTRA-STATE supply -> Split tax equally into CGST and SGST (and set igst_amount = 0). "
                "   - Extract Subtotal, CGST, SGST, IGST, Round Off, and Grand Total Amount. Verify mathematics: Subtotal + CGST + SGST + IGST + Round Off = Grand Total. "
                "Output strict JSON following the schema."
            )

            # Dynamically fetch available models with deprecated/sunset models filtered out
            candidate_models = InvoiceOCRService.get_candidate_models(scan_mode)

            max_retries = 2
            last_gemini_error = ""

            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=active_key)
                attempted_errors = []

                for attempt in range(max_retries):
                    # Filter out models that failed with 404 / NOT_FOUND during runtime
                    models_to_try = [m for m in candidate_models if m not in InvoiceOCRService._DEPRECATED_MODELS]
                    if not models_to_try:
                        break

                    for model_name in models_to_try:
                        try:
                            try:
                                response = client.models.generate_content(
                                    model=model_name,
                                    contents=[
                                        types.Part.from_bytes(data=raw_bytes, mime_type=mime_type),
                                        prompt
                                    ],
                                    config=types.GenerateContentConfig(
                                        response_mime_type="application/json",
                                        response_schema=InvoiceExtractionSchema,
                                        temperature=0.1,
                                    )
                                )
                            except Exception as schema_err:
                                s_err = str(schema_err).lower()
                                if any(kw in s_err for kw in ["schema", "not supported", "response_schema", "additionalproperties", "invalid argument", "400"]):
                                    print(f"[Gemini Schema Fallback] Retrying {model_name} in pure JSON mode due to: {schema_err}")
                                    response = client.models.generate_content(
                                        model=model_name,
                                        contents=[
                                            types.Part.from_bytes(data=raw_bytes, mime_type=mime_type),
                                            prompt
                                        ],
                                        config=types.GenerateContentConfig(
                                            response_mime_type="application/json",
                                            temperature=0.1,
                                        )
                                    )
                                else:
                                    raise schema_err

                            resp_text = response.text or ""
                            # Extract JSON if wrapped in markdown code blocks
                            if "```json" in resp_text:
                                resp_text = resp_text.split("```json", 1)[1].split("```", 1)[0].strip()
                            elif "```" in resp_text:
                                resp_text = resp_text.split("```", 1)[1].split("```", 1)[0].strip()
                            result = json.loads(resp_text)
                            items = result.get("line_items", []) if isinstance(result, dict) else []

                            # Smart Auto-Promotion: If Flash-Lite parsed 0 items, auto-promote to deep vision
                            if "lite" in model_name.lower() and (not items or len(items) == 0) and any("flash" in m and "lite" not in m for m in models_to_try):
                                print(f"[Hybrid OCR Engine] {model_name} parsed 0 items. Auto-promoting for deeper vision...")
                                continue

                            if result and (result.get("invoice_number") or result.get("supplier_name") or items):
                                result["is_mock"] = False
                                result["source"] = f"AI_GEMINI_VISION ({model_name})"
                                result["model_used"] = model_name
                                result["scan_mode"] = scan_mode
                                from apps.inventory.services.normalization_service import strip_category_prefix
                                cat_detected = result.get("category_detected") or ""
                                for it in items:
                                    u = str(it.get("unit") or "PCS").strip().upper()
                                    if u in ["PCS", "PIECES", "NOS", "NO", "PC", "PKT", "PACKET", "BOX", "BAG", "SET", "DOZ", "CAN", "BTL"]:
                                        it["quantity"] = int(round(float(it.get("quantity", 1))))
                                    desc = it.get("description", "")
                                    item_cat = it.get("category") or cat_detected
                                    cleaned_desc = strip_category_prefix(desc, item_cat)
                                    if cleaned_desc:
                                        it["description"] = cleaned_desc

                                    # Consolidate attributes for inventory & voucher synchronization
                                    attrs = it.get("attributes") or {}
                                    if not isinstance(attrs, dict):
                                        attrs = {}
                                    for attr_key in ["color", "storage", "ram", "warranty", "specifications"]:
                                        val = it.get(attr_key)
                                        if val and str(val).strip() and attr_key not in attrs:
                                            attrs[attr_key] = str(val).strip()
                                    if it.get("imei_numbers") and "imei_numbers" not in attrs:
                                        attrs["imei_numbers"] = it["imei_numbers"]
                                    it["attributes"] = attrs

                            result["validation"] = InvoiceOCRService.validate_invoice_math(result, buyer_state_code=buyer_state_code)
                            return _attach_pdf_previews(result)
                        except Exception as gemini_err:
                            err_str = str(gemini_err).lower()
                            clean_err_msg = str(gemini_err)[:180].replace("\n", " ")
                            attempted_errors.append(f"{model_name}: {clean_err_msg}")

                            # 404 / Decommissioned / Model Not Found guard: permanently blacklist & immediately try next model
                            if "404" in err_str or "not found" in err_str or "no longer available" in err_str or "not_found" in err_str:
                                print(f"[Gemini Deprecation Guard] Model {model_name} is no longer available. Blacklisting from rotation.")
                                InvoiceOCRService._DEPRECATED_MODELS.add(model_name)
                                continue

                            last_gemini_error = f"{model_name}: {clean_err_msg}"
                            if "429" in err_str or "quota" in err_str or "exhausted" in err_str or "rate" in err_str:
                                print(f"[Gemini Rate Limit] Hit on {model_name}. Failing over immediately to next model...")
                                # Do NOT break; seamlessly fall through to next available model with quota
                                continue
                            else:
                                print(f"[Gemini Error] Model {model_name} attempt error: {gemini_err}")
                                continue

                    if attempt < max_retries - 1:
                        sleep_seconds = 1.0 * (attempt + 1)
                        time.sleep(sleep_seconds)
            except Exception as e:
                last_gemini_error = str(e)
                print(f"Gemini SDK invocation failed: {e}")

        # -------------------------------------------------------------
        # TIER 2: If PDF, attempt PyPDF text stream extraction
        # -------------------------------------------------------------
        if is_pdf:
            pdf_parsed_data = InvoiceOCRService._extract_from_pdf(raw_bytes)
            if pdf_parsed_data and (pdf_parsed_data.get("invoice_number") or pdf_parsed_data.get("supplier_name")):
                pdf_parsed_data["source"] = "PDF_TEXT_STREAM"
                pdf_parsed_data["is_mock"] = False
                pdf_parsed_data["validation"] = InvoiceOCRService.validate_invoice_math(pdf_parsed_data, buyer_state_code=buyer_state_code)
                return _attach_pdf_previews(pdf_parsed_data)

        if last_gemini_error:
            # Avoid confusing the user when key is present but model was rate limited or failed
            clean_err = last_gemini_error[:160].replace("\n", " ")
            return _attach_pdf_previews(InvoiceOCRService._fallback_mock(error=f"Gemini AI issue: {clean_err}. Please verify fields manually."))

        return _attach_pdf_previews(InvoiceOCRService._fallback_mock(error="Unable to detect readable invoice text from this photo."))

    @staticmethod
    def _extract_from_pdf(raw_bytes: bytes) -> Optional[dict]:
        """Extracts text stream from digital PDF and parses invoice structure."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw_bytes))
            if not reader.pages:
                return None

            page_1_text = reader.pages[0].extract_text() or ""
            full_text = ""
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    full_text += txt + "\n"

            search_text = page_1_text if len(page_1_text.strip()) > 50 else full_text
            lines = [l.strip() for l in search_text.split('\n') if l.strip()]
            return InvoiceOCRService._parse_invoice_lines(lines)
        except Exception as e:
            print(f"Error parsing PDF text stream: {e}")
            return None

    @staticmethod
    def _parse_invoice_lines(lines: List[str]) -> dict:
        """Parses extracted lines into a structured GST invoice dictionary."""
        full_text = "\n".join(lines)

        # 1. Invoice Number (handle multi-line label & OCR typos like 'awoice', 'inv no', 'bill no')
        invoice_number = ""
        for i, l in enumerate(lines):
            if re.search(r'[ai]nvoic|[ai]woic|bill\s*no|inv\s*no|vide\s*bi|bill\s*#|invoice\s*#', l, re.IGNORECASE):
                # Try next line first (frequent in multi-column tables)
                if i + 1 < len(lines):
                    m2 = re.search(r'[:.\-\s]*([A-Za-z0-9]+[\/\-_][A-Za-z0-9]+|[A-Za-z0-9]{4,20})', lines[i+1])
                    if m2 and not re.search(r'date|tax|supply|name|state|pan|shop|ph', m2.group(1), re.IGNORECASE):
                        invoice_number = m2.group(1).strip()
                        break
                # Try same line
                m = re.search(r'[:.\-]\s*([A-Za-z0-9]+[\/\-_][A-Za-z0-9]+|[A-Za-z0-9]{4,15})', l)
                if m and not any(kw in m.group(1).lower() for kw in ["date", "tax", "gst", "name", "no", "inio"]):
                    invoice_number = m.group(1).strip()
                    break

        if not invoice_number:
            # Look for general slash or dash voucher format e.g. G/0023689
            for l in lines:
                if any(kw in l.lower() for kw in ["ph", "phone", "mob", "tel", "account", "bank", "ifsc"]):
                    continue
                m = re.search(r'\b([A-Za-z0-9]{1,8}[\/\-][0-9]{3,8})\b', l)
                if m:
                    invoice_number = m.group(1).strip()
                    break

        # 2. Invoice Date (handle multi-line label like 'Dated\n... 06/03/2026')
        invoice_date = ""
        for i, l in enumerate(lines):
            if re.search(r'\b(?:Dated?|Invoice\s*Date|Bill\s*Date|Date)\b', l, re.IGNORECASE):
                candidate_text = " ".join(lines[i:min(i+4, len(lines))])
                candidate_text = candidate_text.replace('%', '6')
                dm = re.search(r'(\d{1,2})[\s/.\-](\d{1,2})[\s/.\-](\d{2,4})', candidate_text)
                if dm:
                    d, m_month, y = dm.group(1), dm.group(2), dm.group(3)
                    if len(y) == 2:
                        y = "20" + y
                    elif len(y) == 3:
                        y = "20" + y[-2:]
                    invoice_date = f"{y}-{m_month.zfill(2)}-{d.zfill(2)}"
                    break

        if not invoice_date:
            date_match = re.search(
                r'(?:Dated?|Invoice\s*Date|Bill\s*Date|Date\s*of\s*Invoice|Date)\s*[:.\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',
                full_text,
                re.IGNORECASE
            )
            if date_match:
                raw_date = date_match.group(1).strip()
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
                    try:
                        dt = datetime.strptime(raw_date, fmt)
                        invoice_date = dt.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        pass
                if not invoice_date:
                    invoice_date = raw_date

        # 3. GSTINs (Distinguish Supplier GSTIN vs Buyer GSTIN)
        raw_gst_candidates = re.findall(r'\b([0-9O]{2}[A-Z]{5}[0-9O]{4}[A-Z]{1}[1-9A-Z]{1}[Z2][0-9A-Z]{1})\b', full_text)
        all_gstins = []
        for g in raw_gst_candidates:
            clean_g = (
                g[:2].replace('O', '0') +
                g[2:7] +
                g[7:11].replace('O', '0') +
                g[11:13] +
                'Z' +
                g[14]
            )
            all_gstins.append(clean_g)

        supplier_gstin = ""
        buyer_gstin = ""

        billed_to_idx = -1
        for idx, l in enumerate(lines):
            if re.search(r'Billed\s*to|Shipped\s*to|Buyer|Consignee', l, re.IGNORECASE):
                billed_to_idx = idx
                break

        for idx, l in enumerate(lines):
            m = re.search(r'\b([0-9O]{2}[A-Z]{5}[0-9O]{4}[A-Z]{1}[1-9A-Z]{1}[Z2][0-9A-Z]{1})\b', l)
            if m:
                raw = m.group(1)
                clean_g = raw[:2].replace('O', '0') + raw[2:7] + raw[7:11].replace('O', '0') + raw[11:13] + 'Z' + raw[14]
                if billed_to_idx != -1 and idx >= billed_to_idx and not buyer_gstin:
                    buyer_gstin = clean_g
                elif not supplier_gstin:
                    supplier_gstin = clean_g

        if not supplier_gstin and all_gstins:
            supplier_gstin = all_gstins[0]

        # Fallback for GSTIN: check if PAN is present near top or preceded by state code
        if not supplier_gstin:
            pan_match = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b', full_text)
            if pan_match:
                pan_val = pan_match.group(1)
                gst_pan_match = re.search(r'\b([0-9]{2}' + pan_val + r'[0-9A-Z]{1,3})\b', full_text)
                if gst_pan_match:
                    cand = gst_pan_match.group(1)
                    if len(cand) >= 14:
                        supplier_gstin = cand[:15]
                elif state_code:
                    supplier_gstin = f"{state_code}{pan_val}1Z5"

        # 4. State Code / Place of Supply
        state_code = ""
        state_match = re.search(
            r'\(([0-9]{2})\)',
            full_text
        )
        if state_match:
            state_code = state_match.group(1)
        elif supplier_gstin:
            state_code = supplier_gstin[:2]

        # 5. Supplier Name
        supplier_name = ""
        for i, line in enumerate(lines):
            if "TAX INVOICE" in line.upper() or "TAX INNVORCE" in line.upper():
                # Check previous line
                if i > 0 and len(lines[i-1].strip()) > 3 and not re.search(r'GSTIN|ORIGINAL|DUPLICATE|TRIPLICATE', lines[i-1], re.IGNORECASE):
                    supplier_name = lines[i-1].strip()
                    break
                # Check next line
                if i + 1 < len(lines):
                    candidate = lines[i+1].strip()
                    if not any(candidate.lower().startswith(x) for x in ["shop", "gstin", "invoice", "original", "pan", "phone", "ph"]):
                        supplier_name = candidate
                        break

        if not supplier_name:
            for line in lines:
                m = re.search(r'for\s+([A-Za-z0-9\s&.,\'-]+)', line, re.IGNORECASE)
                if m:
                    cand = m.group(1).strip()
                    if len(cand) > 3 and "authorised" not in cand.lower() and "signatory" not in cand.lower():
                        supplier_name = cand
                        break

        if not supplier_name:
            for line in lines:
                if any(kw in line for kw in ["& Co", "& COMPANY", "Pvt Ltd", "Private Limited", "Limited", "Enterprise", "Enterprises", "Traders", "Industries", "Store", "Stores", "Belting", "Motors", "Engineering", "Corporation", "Agencies"]):
                    cand = line.strip()
                    if not re.search(r'Billed\s*to|Shipped\s*to|Buyer|Consignee', cand, re.IGNORECASE):
                        supplier_name = cand
                        break

        if supplier_name:
            supplier_name = re.sub(r'\b([aA])\s+([cC][oO])\b', r'&\g<2>', supplier_name)

        # 6. Taxes & Totals
        cgst = 0.0
        sgst = 0.0
        igst = 0.0
        grand_total = 0.0

        for line in lines:
            if "CGST" in line.upper():
                m = re.search(r'([0-9,]+\.[0-9]{2})\s*$', line)
                if m:
                    cgst = float(m.group(1).replace(',', ''))
            elif "SGST" in line.upper():
                m = re.search(r'([0-9,]+\.[0-9]{2})\s*$', line)
                if m:
                    sgst = float(m.group(1).replace(',', ''))
            elif "IGST" in line.upper():
                m = re.search(r'([0-9,]+\.[0-9]{2})\s*$', line)
                if m:
                    igst = float(m.group(1).replace(',', ''))
            elif any(k in line.upper() for k in ["GRAND TOTAL", "TOTAL AMOUNT", "NET AMOUNT"]):
                m = re.search(r'([0-9,]+\.[0-9]{2})\s*$', line)
                if m:
                    grand_total = float(m.group(1).replace(',', ''))

        # Check for word amounts with OCR typo replacements
        words_match = re.search(r'(?:Rupees|Rupeas)\s+([A-Za-z\s]+?)(?:Only|\.\s*$|$)', full_text, re.IGNORECASE)
        if words_match and grand_total == 0.0:
            raw_words = words_match.group(1)
            converted = parse_words_to_number(raw_words)
            if converted > 0:
                grand_total = converted

        # 7. Line Items
        line_items = []
        for i, line in enumerate(lines):
            m = re.match(r'^\s*(\d+)\.\s+(.+?)\s+([0-9]{4,8})\s+([0-9.]+)\s+([A-Za-z]+)\s+([0-9.,]+)\s+.*?([0-9,]+\.[0-9]{2})$', line)
            if m:
                desc_p1 = m.group(2).strip()
                hsn = m.group(3).strip()
                qty = float(m.group(4))
                unit = m.group(5).strip().upper()
                rate = float(m.group(6).replace(',', ''))
                amt = float(m.group(7).replace(',', ''))

                desc = desc_p1
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if not re.search(r'Add\s*:|Grand\s*Total|Tax\s*Rate|Total\s*Amount|\d+\.\s+', next_line) and len(next_line) > 0:
                        desc = f"{desc_p1} {next_line}".strip()

                desc = re.sub(r'\s+', ' ', desc)

                if unit in ["PCS", "PIECES", "NOS", "NO", "PC", "PKT", "PACKET", "BOX", "BAG", "SET", "DOZ", "CAN", "BTL"]:
                    qty = float(int(round(qty)))

                barcode_val = ""
                serial_val = ""
                imei_m = re.search(r'\b(?:IMEI|S/?N|Serial|Sr\.?\s*No\.?)[:\s]+([A-Za-z0-9,\s\-_/]+)', desc, re.IGNORECASE)
                if imei_m:
                    serial_val = imei_m.group(1).strip()
                barcode_m = re.search(r'\b(?:Barcode|EAN|UPC)[:\s]+([0-9]{8,14})', desc, re.IGNORECASE)
                if barcode_m:
                    barcode_val = barcode_m.group(1).strip()

                line_items.append({
                    "description": desc,
                    "barcode": barcode_val,
                    "serial_numbers": serial_val,
                    "hsn_code": hsn,
                    "quantity": qty,
                    "unit": unit,
                    "rate": rate,
                    "discount_percent": 0.0,
                    "amount": amt,
                    "gst_rate": 18.0
                })

        if not line_items:
            summary_match = re.search(r'(Being\s+Goods\s+Sold[^\n]+)', full_text, re.IGNORECASE)
            item_desc = summary_match.group(1).strip() if summary_match else ""
            if not item_desc:
                item_desc = f"Goods per {invoice_number}" if invoice_number else "Taxable Goods & Supplies"

            item_amount = grand_total if grand_total > 0 else (cgst + sgst + igst)
            if item_amount > 0 and (cgst > 0 or sgst > 0):
                tax_sum = cgst + sgst + igst
                subtotal_calc = round(item_amount - tax_sum, 2)
            else:
                subtotal_calc = round(item_amount, 2)

            line_items.append({
                "description": item_desc,
                "barcode": "",
                "serial_numbers": "",
                "hsn_code": "8482",
                "quantity": 1.0,
                "unit": "NOS",
                "rate": subtotal_calc,
                "discount_percent": 0.0,
                "amount": subtotal_calc,
                "gst_rate": 18.0
            })

        subtotal = sum(i["amount"] for i in line_items)
        if grand_total == 0.0:
            grand_total = subtotal + cgst + sgst + igst

        return {
            "supplier_name": supplier_name,
            "supplier_gstin": supplier_gstin,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "state_code": state_code,
            "subtotal": round(subtotal, 2),
            "cgst_amount": round(cgst, 2),
            "sgst_amount": round(sgst, 2),
            "igst_amount": round(igst, 2),
            "total_amount": round(grand_total, 2),
            "line_items": line_items,
            "is_mock": False
        }

    @staticmethod
    def validate_gstin(gstin: str) -> bool:
        """Validates standard Indian 15-character GSTIN format and state code."""
        if not gstin:
            return False
        pat = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
        clean = str(gstin).strip().upper()
        if not re.match(pat, clean):
            return False
        try:
            state_code_int = int(clean[:2])
            if not (1 <= state_code_int <= 38 or state_code_int in [97, 99]):
                return False
        except ValueError:
            return False
        return True

    @staticmethod
    def validate_invoice_math(data: dict, buyer_state_code: str = "") -> dict:
        """
        Deterministic mathematical reconciliation & GST validation for invoices (Phases 10 & 11).
        1. Reconciles: sum(items.amount) == subtotal
        2. Reconciles: subtotal + cgst + sgst + igst == grand_total
        3. Recovers missing taxes if grand_total > subtotal or line items specify GST rates.
        4. Validates 15-char GSTIN format and state code.
        5. Calculates field confidence scores and overall risk tier.
        """
        items = data.get("line_items", [])
        calc_sub = round(sum(float(i.get("amount", 0.0) or 0.0) for i in items), 2)
        ext_sub = round(float(data.get("subtotal", 0.0) or 0.0), 2)
        subtotal_base = calc_sub if calc_sub > 0 else ext_sub
        if subtotal_base > 0 and ext_sub == 0.0:
            data["subtotal"] = subtotal_base

        cgst = round(float(data.get("cgst_amount", 0.0) or 0.0), 2)
        sgst = round(float(data.get("sgst_amount", 0.0) or 0.0), 2)
        igst = round(float(data.get("igst_amount", 0.0) or 0.0), 2)
        ext_total = round(float(data.get("total_amount", 0.0) or 0.0), 2)
        ro_val = round(float(data.get("round_off", 0.0) or 0.0), 2)

        gstin = (data.get("supplier_gstin") or "").strip().upper()
        supp_state = (data.get("state_code") or "").strip()
        if not supp_state and len(gstin) >= 2 and gstin[:2].isdigit():
            supp_state = gstin[:2]
            data["state_code"] = supp_state

        buyer_state = str(buyer_state_code or "").strip()
        is_interstate = (supp_state and buyer_state and supp_state != buyer_state)

        # -------------------------------------------------------------
        # Deterministic GST Reconciliation:
        # If AI returned 0 taxes but the bill has line-item taxes or ext_total > subtotal_base
        # -------------------------------------------------------------
        if cgst == 0.0 and sgst == 0.0 and igst == 0.0 and subtotal_base > 0:
            # Calculate itemized tax expectation
            total_item_tax = 0.0
            for item in items:
                amt = float(item.get("amount", 0.0) or 0.0)
                gst_r = float(item.get("gst_rate", 18.0) or 18.0)
                total_item_tax += round(amt * (gst_r / 100.0), 2)
            total_item_tax = round(total_item_tax, 2)
            if total_item_tax == 0.0:
                total_item_tax = round(subtotal_base * 0.18, 2)

            if ext_total > subtotal_base:
                tax_diff = round(ext_total - subtotal_base, 2)
                # If difference matches line item tax within round-off tolerance (<= 3.00)
                if abs(tax_diff - total_item_tax) <= 3.0:
                    recovered_tax = total_item_tax
                else:
                    recovered_tax = tax_diff

                if is_interstate:
                    igst = recovered_tax
                    cgst = 0.0
                    sgst = 0.0
                else:
                    half_tax = round(recovered_tax / 2.0, 2)
                    cgst = half_tax
                    sgst = round(recovered_tax - half_tax, 2)
                    igst = 0.0

                data["cgst_amount"] = cgst
                data["sgst_amount"] = sgst
                data["igst_amount"] = igst

                unrounded = round(subtotal_base + cgst + sgst + igst, 2)
                ro_val = round(ext_total - unrounded, 2)
                data["round_off"] = ro_val
                expected_total = ext_total
                data["total_amount"] = ext_total
            else:
                # ext_total is 0 or equal to subtotal: infer tax from items
                if is_interstate:
                    igst = total_item_tax
                    cgst = 0.0
                    sgst = 0.0
                else:
                    half_tax = round(total_item_tax / 2.0, 2)
                    cgst = half_tax
                    sgst = round(total_item_tax - half_tax, 2)
                    igst = 0.0

                data["cgst_amount"] = cgst
                data["sgst_amount"] = sgst
                data["igst_amount"] = igst

                unrounded = round(subtotal_base + cgst + sgst + igst, 2)
                rounded_tot = round(unrounded)
                ro_val = round(rounded_tot - unrounded, 2)
                data["round_off"] = ro_val
                expected_total = float(rounded_tot)
                data["total_amount"] = expected_total
        else:
            # Taxes were present in extraction
            unrounded_expected = round(subtotal_base + cgst + sgst + igst, 2)
            if ext_total > 0 and abs(ext_total - unrounded_expected) <= 2.50:
                ro_val = round(ext_total - unrounded_expected, 2)
                data["round_off"] = ro_val
                expected_total = ext_total
                data["total_amount"] = ext_total
            elif ro_val != 0.0:
                expected_total = round(unrounded_expected + ro_val, 2)
                data["total_amount"] = expected_total
            else:
                rounded_tot = round(unrounded_expected)
                ro_val = round(rounded_tot - unrounded_expected, 2)
                data["round_off"] = ro_val
                expected_total = float(rounded_tot)
                data["total_amount"] = expected_total

        diff = round(abs(expected_total - ext_total), 2) if ext_total > 0 else 0.0
        math_valid = (diff <= 1.0) and (ext_total > 0 or expected_total > 0)

        gstin = (data.get("supplier_gstin") or "").strip().upper()
        gstin_valid = InvoiceOCRService.validate_gstin(gstin)
        inv_num = (data.get("invoice_number") or "").strip()
        inv_date = (data.get("invoice_date") or "").strip()

        conf = {}
        conf["invoice_number"] = 98 if inv_num else 30
        conf["invoice_date"] = 95 if inv_date else 40
        conf["supplier_gstin"] = 99 if gstin_valid else (60 if gstin else 10)
        conf["totals"] = 99 if math_valid else (60 if diff <= 5.0 else 25)

        overall_conf = round(sum(conf.values()) / len(conf), 1)

        if math_valid and gstin_valid and inv_num:
            risk = "HIGH_CONFIDENCE"
        elif diff <= 5.0 and inv_num:
            risk = "NEEDS_REVIEW"
        else:
            risk = "HIGH_RISK"

        msg = None
        if not math_valid and (ext_total > 0 or expected_total > 0):
            msg = f"Vouch found a ₹{diff:.2f} difference in the extracted totals."

        tax_warnings = []
        if cgst > 0 and sgst > 0:
            if abs(cgst - sgst) > 1.0:
                tax_warnings.append(f"CGST (₹{cgst:.2f}) and SGST (₹{sgst:.2f}) should be equal for intra-state supply.")
            if igst > 0:
                tax_warnings.append("Invoice contains both CGST/SGST and IGST.")
        elif igst > 0:
            if cgst > 0 or sgst > 0:
                tax_warnings.append("Invoice contains both CGST/SGST and IGST.")

        return {
            "math_valid": math_valid,
            "difference": diff,
            "discrepancy_message": msg,
            "calculated_subtotal": calc_sub,
            "expected_total": expected_total,
            "gstin_valid": gstin_valid,
            "tax_warnings": tax_warnings,
            "risk_level": risk,
            "confidence": overall_conf,
            "field_confidence": conf
        }

    @staticmethod
    def _fallback_mock(error: Optional[str] = None) -> dict:
        """Returns clean empty structure marked as mock with clear reason and validation status."""
        base = {
            "supplier_name": "",
            "supplier_gstin": "",
            "invoice_number": "",
            "invoice_date": datetime.today().strftime("%Y-%m-%d"),
            "state_code": "",
            "subtotal": 0.00,
            "cgst_amount": 0.00,
            "sgst_amount": 0.00,
            "igst_amount": 0.00,
            "round_off": 0.00,
            "total_amount": 0.00,
            "category_detected": "",
            "requires_category_confirmation": True,
            "categories_found": [],
            "line_items": [],
            "is_mock": True,
            "mock_reason": error or "Could not extract readable invoice data from this file."
        }
        base["validation"] = InvoiceOCRService.validate_invoice_math(base)
        return base

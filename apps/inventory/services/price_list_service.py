import re
import uuid
from decimal import Decimal
from django.db import transaction
from apps.companies.models import Company
from apps.inventory.models import Product, ProductCategory, Warehouse, InventoryEntry

class PriceListService:
    @staticmethod
    @transaction.atomic
    def bulk_import_price_list(company: Company, category_id: str, brand: str, items_data: list):
        """
        Bulk creates or updates products under a specific category and brand from a price list.
        Preserves single item name identity while attaching brand-specific MRP and purchase price.
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
                existing.save()
                updated_count += 1
            else:
                # Generate unique clean SKU
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
        Parses PDF file text using pypdf and extracts (item_name, mrp) candidates.
        """
        import pypdf
        reader = pypdf.PdfReader(file_obj)
        extracted_items = []
        seen_names = set()
        
        # Regex matching patterns like "A-18   132.00" or "A-18   ₹ 132" or "6204 2RS   185.50"
        pattern = re.compile(r'([A-Za-z0-9\-\.\/]{2,30})\s+(?:₹|Rs\.?)?\s*([0-9]+(?:\.[0-9]{1,2})?)')
        
        for page in reader.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")
            for line in lines:
                line_clean = line.strip()
                if not line_clean:
                    continue
                match = pattern.search(line_clean)
                if match:
                    name_candidate = match.group(1).strip()
                    price_str = match.group(2).strip()
                    
                    # Ignore common header text
                    if name_candidate.lower() in ['page', 'total', 's.no', 'sr.no', 'item', 'code', 'date', 'price', 'mrp']:
                        continue
                        
                    if name_candidate.upper() not in seen_names:
                        seen_names.add(name_candidate.upper())
                        try:
                            price_val = float(price_str)
                            if price_val > 0:
                                extracted_items.append({
                                    "name": name_candidate,
                                    "selling_price": price_val,
                                    "purchase_price": 0.00,
                                    "opening_qty": 0,
                                    "unit": "PCS"
                                })
                        except ValueError:
                            pass
                            
        return extracted_items

import re
import logging
from decimal import Decimal
from django.db import transaction

logger = logging.getLogger(__name__)


def strip_category_prefix(raw_name: str, category_name: str = None) -> str:
    """
    Strips redundant category prefixes from item names.
    Examples:
      'V Belt B34' -> 'B34'
      'V-Belt B79' -> 'B79'
      'V BELTS B 72' -> 'B 72'
      'BELT C 120' -> 'C 120'
      'FAN BELT SPA 1250' -> 'SPA 1250'
    """
    if not raw_name:
        return ""

    name = str(raw_name).strip()

    # 1. If explicit category_name is provided, match dynamic prefix
    if category_name:
        cat_clean = str(category_name).strip()
        if cat_clean:
            words = re.split(r'[\s\-_]+', cat_clean)
            cat_pattern = r'[\s\-_]*'.join(re.escape(w) for w in words if w)
            if cat_pattern.lower().endswith('es'):
                cat_pattern = cat_pattern[:-2] + r'(?:es)?'
            elif cat_pattern.lower().endswith('s'):
                cat_pattern = cat_pattern[:-1] + r's?'
            regex = rf'^{cat_pattern}\s*[:\-_]?\s*'
            stripped = re.sub(regex, '', name, flags=re.IGNORECASE).strip()
            if stripped:
                name = stripped

    # 2. Match common industrial categories (especially belts)
    common_prefixes = [
        r'^(?:(?:V[\s\-_]*)?BELTS?|FAN[\s\-_]*BELTS?|TIMING[\s\-_]*BELTS?|CONVEYOR[\s\-_]*BELTS?)\s*[:\-_]?\s*',
        r'^(?:BEARINGS?|PULLEYS?|OIL[\s\-_]*SEALS?)\s*[:\-_]?\s*'
    ]
    for pattern in common_prefixes:
        candidate = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
        if candidate:
            name = candidate
            break

    return name


def normalize_product_name(raw_name: str, category_name: str = None) -> str:
    """
    Standardizes item names to the format without hyphen and with a single space,
    stripping redundant category prefixes if present.
    Examples:
      'V Belt B34', 'V-BELT B-34' -> 'B 34'
      'V BELTS B 72' -> 'B 72'
      'A-31', 'A 31', 'A31' -> 'A 31'
      'A-32', 'A 32', 'A32' -> 'A 32'
      'B-92', 'B 92', 'B92' -> 'B 92'
      'C-120', 'C 120', 'C120' -> 'C 120'
      'SPA-1250', 'SPA 1250', 'SPA1250' -> 'SPA 1250'
      'SPB-2000', 'SPB 2000', 'SPB2000' -> 'SPB 2000'
      'SPC-3000', 'SPC 3000', 'SPC3000' -> 'SPC 3000'
      'AX-31', 'AX 31', 'AX31' -> 'AX 31'
      '5V-1000', '5V 1000', '5V1000' -> '5V 1000'
    """
    if not raw_name:
        return ""

    # Strip redundant category prefix first
    name = strip_category_prefix(raw_name, category_name)

    # 1. Replace hyphens and underscores with a space
    name = re.sub(r'[\-_]+', ' ', name)

    # 2. Insert space between Section prefix and size number if directly connected
    # Case A: Leading digit belt sections like 3V, 5V, 8V, 3L, 4L, 5L followed immediately by digits
    name = re.sub(r'^([358][VLvl])(\d+)', r'\1 \2', name)

    # Case B: Standard alpha letters followed immediately by digits (e.g. A31 -> A 31, B92 -> B 92, SPA1250 -> SPA 1250)
    name = re.sub(r'^([A-Za-z]+)(\d+)', r'\1 \2', name)

    # 3. Collapse multiple whitespace into a single space
    name = re.sub(r'\s+', ' ', name).strip()

    # 4. Standardize capitalization of the prefix
    parts = name.split(' ', 1)
    if len(parts) == 2:
        prefix, rest = parts
        if re.match(r'^[A-Za-z0-9]+$', prefix):
            name = f"{prefix.upper()} {rest}"
    else:
        name = name.upper()

    return name


def get_canonical_key(name: str, category_name: str = None) -> str:
    """
    Returns an alphanumeric canonical key used to match identical items:
    'V Belt B34', 'V-Belt B-34', 'B 34', 'B-34', 'B34' -> 'b34'
    'V BELTS B 72', 'B 72', 'B-72' -> 'b72'
    'A 31', 'A-31', 'A31', 'a 31' -> 'a31'
    'B92', 'B-92', 'B 92' -> 'b92'
    'SPA 1250', 'SPA-1250' -> 'spa1250'
    """
    if not name:
        return ""
    clean_name = strip_category_prefix(name, category_name)
    return re.sub(r'[\s\-_\./\\]+', '', str(clean_name)).lower()


def combine_and_deduplicate_inventory(company_id=None, company_name=None, dry_run=False):
    """
    Combines duplicate items within a company's inventory, standardizes names
    without hyphens and with a single space (e.g. A 32, B 92), aggregates stock,
    re-links all voucher items and inventory entries, and ensures the green Invoice
    tag (purchase_price_from_invoice=True) is applied to any item from an invoice.
    """
    from apps.companies.models import Company
    from apps.inventory.models import Product, InventoryEntry
    from apps.accounting.models import VoucherItem

    # Locate target companies
    companies = Company.objects.none()
    if company_id:
        companies = Company.objects.filter(id=company_id)
    elif company_name:
        companies = Company.objects.filter(name__icontains=company_name)
    else:
        # Default: search for Maa Annapurna Belting Store or any company with annapurna, else all companies
        annapurna_companies = Company.objects.filter(name__icontains='annapurna')
        if annapurna_companies.exists():
            companies = annapurna_companies
        else:
            companies = Company.objects.all()

    report = {
        "success": True,
        "dry_run": dry_run,
        "companies_processed": [],
        "total_merged_groups": 0,
        "total_deleted_duplicates": 0,
        "total_renamed_items": 0,
        "total_invoice_tags_set": 0,
    }

    for comp in companies:
        comp_summary = {
            "company_id": str(comp.id),
            "company_name": comp.name,
            "merged_groups": 0,
            "deleted_duplicates": 0,
            "renamed_items": 0,
            "invoice_tags_set": 0,
            "details": []
        }

        # Find all product IDs referenced by PURCHASE vouchers for this company
        purchase_voucher_product_ids = set(
            VoucherItem.objects.filter(
                voucher__company=comp,
                voucher__voucher_type='PURCHASE'
            ).values_list('product_id', flat=True)
        )

        all_products = list(Product.objects.filter(company=comp).select_related('category'))

        # Group products by (category_id, brand_normalized, canonical_key)
        # First pass: map categorized products
        groups = {}
        for p in all_products:
            cat_id = str(p.category_id) if p.category_id else "none"
            cat_name = p.category.name if p.category else None
            brand_norm = (p.brand or "").strip().lower()
            key = get_canonical_key(p.name, cat_name)
            group_key = (cat_id, brand_norm, key)
            groups.setdefault(group_key, []).append(p)

        # Merge unassigned ("none") products into categorized group if matching brand and key
        unassigned_keys = [gk for gk in groups.keys() if gk[0] == "none"]
        for u_gk in unassigned_keys:
            _, brand_norm, key = u_gk
            if not key:
                continue
            matching_cat_gk = next((gk for gk in groups.keys() if gk[0] != "none" and gk[1] == brand_norm and gk[2] == key), None)
            if matching_cat_gk:
                groups[matching_cat_gk].extend(groups.pop(u_gk))

        for (cat_id, brand_norm, key), prods in groups.items():
            if not key:
                continue

            # Determine the target standardized name
            cat_name = next((p.category.name for p in prods if p.category), None)
            sample_name = prods[0].name
            for p in prods:
                clean_cand = strip_category_prefix(p.name, cat_name)
                if clean_cand.lower() == p.name.strip().lower():
                    sample_name = p.name
                    break
            target_name = normalize_product_name(sample_name, cat_name)

            # Check if any product in the group was uploaded or billed from an invoice
            has_invoice_origin = any(
                p.purchase_price_from_invoice or (p.id in purchase_voucher_product_ids)
                for p in prods
            )

            # If there are multiple duplicate products in the cluster, merge them!
            if len(prods) > 1:
                comp_summary["merged_groups"] += 1
                report["total_merged_groups"] += 1

                # Select primary product
                # 1. Prefer product whose name didn't have redundant category prefix (e.g. B 34 over V Belt B34)
                # 2. Prefer product already assigned to a category
                # 3. Prefer product already marked purchase_price_from_invoice
                # 4. Or product present in purchase vouchers
                # 5. Or product with positive stock / purchase price
                def sort_priority(p):
                    score = 0
                    p_cat_name = p.category.name if p.category else cat_name
                    clean_name = strip_category_prefix(p.name, p_cat_name)
                    if clean_name.lower() == p.name.strip().lower():
                        score += 200
                    if p.category_id:
                        score += 150
                    if p.purchase_price_from_invoice:
                        score += 100
                    if p.id in purchase_voucher_product_ids:
                        score += 50
                    if (p.stock_quantity or Decimal("0.00")) > 0:
                        score += 20
                    if (p.purchase_price or Decimal("0.00")) > 0:
                        score += 10
                    return score

                sorted_prods = sorted(prods, key=sort_priority, reverse=True)
                primary = sorted_prods[0]
                duplicates = sorted_prods[1:]

                # Aggregate stock quantity
                total_stock = sum((p.stock_quantity or Decimal("0.00")) for p in prods)

                # Resolve best purchase price
                best_purchase_price = Decimal("0.00")
                # Look for invoice purchase prices first
                for p in sorted_prods:
                    if (p.purchase_price_from_invoice or p.id in purchase_voucher_product_ids) and p.purchase_price > Decimal("0.00"):
                        best_purchase_price = p.purchase_price
                        break
                if best_purchase_price == Decimal("0.00"):
                    for p in sorted_prods:
                        if p.purchase_price > Decimal("0.00"):
                            best_purchase_price = p.purchase_price
                            break

                # Resolve selling price, HSN, GST, Unit, Category
                best_selling_price = max((p.selling_price or Decimal("0.00") for p in prods), default=Decimal("0.00"))
                best_category = next((p.category for p in sorted_prods if p.category), primary.category)
                best_hsn = next((p.hsn_code for p in sorted_prods if p.hsn_code), primary.hsn_code)
                best_gst = next((p.gst_rate for p in sorted_prods if p.gst_rate and p.gst_rate > 0), primary.gst_rate)
                best_unit = next((p.unit for p in sorted_prods if p.unit), primary.unit or "PCS")
                best_brand = next((p.brand for p in sorted_prods if p.brand), primary.brand)

                detail_msg = (
                    f"Merged {len(prods)} items {[p.name for p in prods]} -> '{target_name}' "
                    f"(Total Stock: {total_stock}, Invoice Tag: {has_invoice_origin})"
                )
                comp_summary["details"].append(detail_msg)
                logger.info(detail_msg)

                if not dry_run:
                    with transaction.atomic():
                        # Update primary
                        was_tagged = primary.purchase_price_from_invoice
                        primary.name = target_name
                        primary.stock_quantity = total_stock
                        if best_category and not primary.category:
                            primary.category = best_category
                        if best_purchase_price > Decimal("0.00"):
                            primary.purchase_price = best_purchase_price
                        if best_selling_price > Decimal("0.00"):
                            primary.selling_price = best_selling_price
                        if best_hsn:
                            primary.hsn_code = best_hsn
                        if best_gst:
                            primary.gst_rate = best_gst
                        if best_unit:
                            primary.unit = best_unit
                        if best_brand:
                            primary.brand = best_brand
                        if has_invoice_origin:
                            primary.purchase_price_from_invoice = True
                            if not was_tagged:
                                comp_summary["invoice_tags_set"] += 1
                                report["total_invoice_tags_set"] += 1

                        primary.save()

                        # Re-link and delete duplicates
                        for dup in duplicates:
                            VoucherItem.objects.filter(product=dup).update(product=primary)
                            InventoryEntry.objects.filter(product=dup).update(product=primary)
                            dup.delete()
                            comp_summary["deleted_duplicates"] += 1
                            report["total_deleted_duplicates"] += 1

            elif len(prods) == 1:
                # Single product in group: ensure clean name and invoice tag if from purchase voucher
                single_p = prods[0]
                needs_name_update = single_p.name != target_name
                needs_invoice_tag = has_invoice_origin and not single_p.purchase_price_from_invoice

                if needs_name_update or needs_invoice_tag:
                    if needs_name_update:
                        comp_summary["renamed_items"] += 1
                        report["total_renamed_items"] += 1
                    if needs_invoice_tag:
                        comp_summary["invoice_tags_set"] += 1
                        report["total_invoice_tags_set"] += 1

                    if not dry_run:
                        if needs_name_update:
                            single_p.name = target_name
                        if needs_invoice_tag:
                            single_p.purchase_price_from_invoice = True
                        single_p.save(update_fields=['name', 'purchase_price_from_invoice'])

        report["companies_processed"].append(comp_summary)

    return report

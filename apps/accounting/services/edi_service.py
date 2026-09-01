import json
import hashlib
from typing import Optional, Dict, Any
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.companies.models import Company
from apps.ledgers.models import Ledger, LedgerGroup
from apps.inventory.models import Product, Warehouse, ProductCategory
from apps.accounting.models import Voucher, VoucherItem, InwardVoucherRequest
from apps.accounting.services.purchase_service import PurchaseInvoiceService
from apps.accounting.services.voucher_service import VoucherService


class EDIService:
    @staticmethod
    def create_inward_request_for_sales_voucher(voucher: Voucher) -> Optional[InwardVoucherRequest]:
        """
        Extracts buyer GSTIN from sales voucher party_ledger.
        If a registered Company in the system matches the GSTIN (excluding the seller),
        generates an InwardVoucherRequest in PENDING status.
        """
        if voucher.voucher_type != 'SALES' or not voucher.party_ledger:
            return None

        buyer_gstin = (voucher.party_ledger.gstin or "").strip().upper()
        if not buyer_gstin:
            return None

        target_company = Company.objects.filter(gstin__iexact=buyer_gstin).exclude(id=voucher.company_id).first()
        if not target_company:
            return None

        # Build comprehensive invoice payload snapshot
        items_snapshot = []
        for item in voucher.items.select_related('product', 'product__category').all():
            items_snapshot.append({
                "source_product_id": str(item.product.id),
                "product_name": item.product.name,
                "brand": item.product.brand or "",
                "sku": item.product.sku,
                "hsn_code": item.product.hsn_code or "",
                "unit": item.product.unit or "PCS",
                "quantity": float(item.quantity),
                "rate": float(item.rate),
                "discount_percent": float(item.discount_percent),
                "discount_amount": float(item.discount_amount),
                "taxable_amount": float(item.taxable_amount),
                "gst_rate": float(item.gst_rate),
                "total_amount": float(item.total_amount),
            })

        payload = {
            "source_company_id": str(voucher.company.id),
            "source_company_name": voucher.company.name,
            "source_company_legal_name": voucher.company.legal_name,
            "source_company_gstin": voucher.company.gstin,
            "source_company_state_code": voucher.company.state_code,
            "source_company_address": voucher.company.address,
            "source_company_city": voucher.company.city,
            "source_company_phone": voucher.company.phone,
            "source_company_email": voucher.company.email,
            "voucher_id": str(voucher.id),
            "voucher_number": voucher.voucher_number,
            "voucher_date": voucher.voucher_date.isoformat(),
            "reference_number": voucher.reference_number or "",
            "narration": voucher.narration or "",
            "total_amount": float(voucher.total_amount),
            "items": items_snapshot,
            "dispatched_at": timezone.now().isoformat(),
        }

        # Avoid duplicate PENDING requests for the exact same source voucher
        inward_req, _ = InwardVoucherRequest.objects.update_or_create(
            source_voucher=voucher,
            target_company=target_company,
            defaults={
                "source_company": voucher.company,
                "payload": payload,
                "status": "PENDING",
            }
        )

        return inward_req

    @staticmethod
    @transaction.atomic
    def accept_inward_request(inward_req: InwardVoucherRequest, user, item_mappings: Optional[Dict[str, Any]] = None) -> Voucher:
        """
        Digitally signs and accepts an InwardVoucherRequest:
        1. Generates SHA-256 digital signature hash.
        2. Auto-matches or creates Supplier Ledger for Seller in Buyer's tenant.
        3. Auto-matches or creates Product records in Buyer's tenant.
        4. Creates & Posts verified Purchase Voucher (with InventoryEntry stock updates).
        5. Updates InwardVoucherRequest to ACCEPTED.
        """
        if inward_req.status != 'PENDING':
            raise ValidationError(f"Request cannot be accepted in '{inward_req.status}' status.")

        target_company = inward_req.target_company
        source_company = inward_req.source_company
        payload = inward_req.payload

        # 1. Generate SHA-256 Digital Signature Hash
        timestamp_str = timezone.now().isoformat()
        canonical_str = f"{target_company.id}:{json.dumps(payload, sort_keys=True)}:{timestamp_str}"
        sig_hash = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()

        # 2. Match or Auto-Create Supplier Ledger for Seller in Buyer's tenant
        seller_gstin = payload.get("source_company_gstin", source_company.gstin).strip().upper()
        supplier_ledger = Ledger.objects.filter(
            company=target_company,
            gstin__iexact=seller_gstin
        ).first()

        if not supplier_ledger:
            creditors_group = LedgerGroup.objects.filter(
                company=target_company,
                name__icontains="Creditor"
            ).first()
            if not creditors_group:
                creditors_group = LedgerGroup.objects.create(
                    company=target_company,
                    name="Sundry Creditors",
                    nature="LIABILITY"
                )

            supplier_ledger = Ledger.objects.create(
                company=target_company,
                group=creditors_group,
                name=payload.get("source_company_name", source_company.name),
                gstin=seller_gstin,
                state_code=payload.get("source_company_state_code", source_company.state_code),
                address=payload.get("source_company_address", source_company.address),
                phone=payload.get("source_company_phone", source_company.phone),
                email=payload.get("source_company_email", source_company.email),
                ledger_type="SUPPLIER"
            )

        # 3. Locate or Create Purchase and Tax Ledgers
        purchase_group = LedgerGroup.objects.filter(
            company=target_company,
            name__icontains="Purchase"
        ).first()
        if not purchase_group:
            purchase_group = LedgerGroup.objects.create(
                company=target_company,
                name="Purchase Accounts",
                nature="EXPENSE"
            )

        purchase_ledger = Ledger.objects.filter(
            company=target_company,
            ledger_type="PURCHASE"
        ).first()
        if not purchase_ledger:
            purchase_ledger = Ledger.objects.create(
                company=target_company,
                group=purchase_group,
                name="Purchase Account",
                ledger_type="PURCHASE"
            )

        duties_group = LedgerGroup.objects.filter(
            company=target_company,
            name__icontains="Duties"
        ).first()
        if not duties_group:
            duties_group = LedgerGroup.objects.create(
                company=target_company,
                name="Duties & Taxes",
                nature="ASSET"
            )

        input_cgst, _ = Ledger.objects.get_or_create(
            company=target_company,
            name="Input CGST",
            defaults={"group": duties_group, "ledger_type": "TAX"}
        )
        input_sgst, _ = Ledger.objects.get_or_create(
            company=target_company,
            name="Input SGST",
            defaults={"group": duties_group, "ledger_type": "TAX"}
        )
        input_igst, _ = Ledger.objects.get_or_create(
            company=target_company,
            name="Input IGST",
            defaults={"group": duties_group, "ledger_type": "TAX"}
        )

        # 4. Prepare Line Items & Match/Create Products in Buyer's tenant
        items_data = []
        item_mappings = item_mappings or {}

        for raw_item in payload.get("items", []):
            product_name = raw_item["product_name"]
            sku = raw_item.get("sku") or product_name.upper()[:4] + "-001"
            hsn_code = raw_item.get("hsn_code", "")
            rate = Decimal(str(raw_item["rate"]))
            gst_rate = Decimal(str(raw_item.get("gst_rate", 18.0)))
            qty = Decimal(str(raw_item["quantity"]))
            discount_pct = Decimal(str(raw_item.get("discount_percent", 0.0)))

            # Check if user explicitly mapped this item to a product ID
            mapped_product_id = item_mappings.get(raw_item.get("source_product_id")) or item_mappings.get(product_name)
            product = None
            if mapped_product_id:
                product = Product.objects.filter(company=target_company, id=mapped_product_id).first()

            if not product:
                # Try finding by exact name or SKU or HSN
                product = Product.objects.filter(company=target_company, name__iexact=product_name).first()
                if not product and sku:
                    product = Product.objects.filter(company=target_company, sku__iexact=sku).first()

            if not product:
                # Auto-create product in Buyer's catalog
                import uuid
                unique_sku = f"{sku[:10]}-{str(uuid.uuid4())[:4].upper()}" if Product.objects.filter(company=target_company, sku=sku).exists() else sku
                product = Product.objects.create(
                    company=target_company,
                    name=product_name,
                    sku=unique_sku,
                    hsn_code=hsn_code,
                    gst_rate=gst_rate,
                    unit=raw_item.get("unit", "PCS"),
                    purchase_price=rate,
                    selling_price=rate * Decimal('1.25') # 25% default markup for resale
                )

            items_data.append({
                "product_id": str(product.id),
                "quantity": qty,
                "rate": rate,
                "discount_percent": discount_pct,
                "hsn_code": hsn_code,
                "gst_rate": gst_rate
            })

        # 5. Ensure Buyer has at least one active Warehouse for stock receipt
        warehouse = Warehouse.objects.filter(company=target_company, is_active=True).first()
        if not warehouse:
            Warehouse.objects.create(
                company=target_company,
                name="Main Godown",
                address=target_company.address
            )

        # 6. Generate Purchase Invoice
        purchase_voucher = PurchaseInvoiceService.generate_purchase_invoice(
            company=target_company,
            user=user,
            party_ledger=supplier_ledger,
            items_data=items_data,
            purchase_ledger=purchase_ledger,
            input_cgst_ledger=input_cgst,
            input_sgst_ledger=input_sgst,
            input_igst_ledger=input_igst,
            supplier_invoice_number=payload.get("voucher_number", f"EDI-IN-{int(timezone.now().timestamp())}"),
            voucher_date=timezone.now().date()
        )

        # 7. Post the Voucher (creates inventory movements & ledger entries atomically)
        VoucherService.post_voucher(purchase_voucher)

        # 8. Mark InwardVoucherRequest as ACCEPTED with digital signature
        inward_req.status = 'ACCEPTED'
        inward_req.digital_signature_hash = sig_hash
        inward_req.signed_at = timezone.now()
        inward_req.created_purchase_voucher = purchase_voucher
        inward_req.save(update_fields=['status', 'digital_signature_hash', 'signed_at', 'created_purchase_voucher', 'updated_at'])

        return purchase_voucher

    @staticmethod
    def reject_inward_request(inward_req: InwardVoucherRequest, reason: str = "") -> InwardVoucherRequest:
        if inward_req.status != 'PENDING':
            raise ValidationError(f"Cannot reject a request in '{inward_req.status}' status.")

        inward_req.status = 'REJECTED'
        inward_req.rejection_reason = reason.strip() or "Rejected by recipient."
        inward_req.save(update_fields=['status', 'rejection_reason', 'updated_at'])
        return inward_req

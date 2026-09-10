from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Product, ProductCategory
from apps.companies.models import Company
from apps.accounts.permissions import IsCompanyMember, CanManageInventory

class ProductCategoryListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageInventory()]
    
    def get(self, request, company_id):
        try:
            from django.db.models import F, Sum, ExpressionWrapper, DecimalField
            from decimal import Decimal
            company = Company.objects.get(id=company_id, users__user=request.user)
            categories = ProductCategory.objects.filter(company=company).order_by('name')
            
            stock_val_expr = ExpressionWrapper(F('stock_quantity') * F('purchase_price'), output_field=DecimalField(max_digits=15, decimal_places=2))
            retail_val_expr = ExpressionWrapper(F('stock_quantity') * F('selling_price'), output_field=DecimalField(max_digits=15, decimal_places=2))
            
            data = []
            overall_stock_value = Decimal('0.00')
            overall_retail_value = Decimal('0.00')
            overall_stock_qty = Decimal('0.00')
            overall_items_count = 0
            
            for c in categories:
                cat_prods = c.products.all()
                cat_stock_val = cat_prods.filter(stock_quantity__gt=0).annotate(v=stock_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
                cat_retail_val = cat_prods.filter(stock_quantity__gt=0).annotate(v=retail_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
                cat_stock_qty = cat_prods.filter(stock_quantity__gt=0).aggregate(Sum('stock_quantity'))['stock_quantity__sum'] or Decimal('0.00')
                item_count = cat_prods.count()
                
                overall_stock_value += cat_stock_val
                overall_retail_value += cat_retail_val
                overall_stock_qty += cat_stock_qty
                overall_items_count += item_count
                
                data.append({
                    "id": str(c.id), 
                    "name": c.name,
                    "hsn_code": c.hsn_code or "",
                    "gst_rate": str(c.gst_rate),
                    "item_count": item_count,
                    "stock_quantity": str(cat_stock_qty),
                    "stock_value": str(cat_stock_val),
                    "retail_value": str(cat_retail_val),
                })
                
            # Also account for unassigned products
            unassigned_prods = Product.objects.filter(company=company, category__isnull=True)
            if unassigned_prods.exists():
                un_stock_val = unassigned_prods.filter(stock_quantity__gt=0).annotate(v=stock_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
                un_retail_val = unassigned_prods.filter(stock_quantity__gt=0).annotate(v=retail_val_expr).aggregate(Sum('v'))['v__sum'] or Decimal('0.00')
                un_stock_qty = unassigned_prods.filter(stock_quantity__gt=0).aggregate(Sum('stock_quantity'))['stock_quantity__sum'] or Decimal('0.00')
                overall_stock_value += un_stock_val
                overall_retail_value += un_retail_val
                overall_stock_qty += un_stock_qty
                overall_items_count += unassigned_prods.count()

            return Response({
                "success": True, 
                "data": data,
                "summary": {
                    "total_stock_value": str(overall_stock_value),
                    "total_retail_value": str(overall_retail_value),
                    "total_stock_quantity": str(overall_stock_qty),
                    "total_items": overall_items_count,
                    "total_categories": categories.count(),
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)
            
    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            d = request.data
            
            from apps.ledgers.models import Ledger
            sales_ledger = None
            purchase_ledger = None
            if d.get('sales_ledger_id'):
                sales_ledger = Ledger.objects.get(id=d['sales_ledger_id'], company=company)
            if d.get('purchase_ledger_id'):
                purchase_ledger = Ledger.objects.get(id=d['purchase_ledger_id'], company=company)

            category = ProductCategory.objects.create(
                company=company,
                name=d.get('name'),
                hsn_code=d.get('hsn_code', ''),
                gst_rate=d.get('gst_rate', 18.00),
                sales_ledger=sales_ledger,
                purchase_ledger=purchase_ledger
            )

            # Auto-update complexity
            cat_count = ProductCategory.objects.filter(company=company).count()
            if cat_count >= 10 and company.settings.complexity_level < 3:
                company.settings.complexity_level = 3
                company.settings.enable_ledger_mapping = True
                company.settings.save()
            elif cat_count >= 6 and company.settings.complexity_level < 2:
                company.settings.complexity_level = 2
                company.settings.save()

            return Response({"success": True, "data": {"id": str(category.id), "name": category.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class ProductCategoryDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageInventory()]

    def patch(self, request, company_id, category_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            category = ProductCategory.objects.get(id=category_id, company=company)
            data = request.data

            if 'name' in data: category.name = data['name']
            if 'hsn_code' in data: category.hsn_code = data['hsn_code']
            if 'gst_rate' in data: category.gst_rate = data['gst_rate']

            category.save()
            return Response({"success": True, "data": {"id": str(category.id), "name": category.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def delete(self, request, company_id, category_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            category = ProductCategory.objects.get(id=category_id, company=company)
            category.delete()
            return Response({"success": True})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

def is_integer_unit(unit_str):
    if not unit_str:
        return True # Default unit is PCS
    u = str(unit_str).strip().upper()
    fractional_units = ['KG', 'KGS', 'KILOGRAM', 'KILOGRAMS', 'LTR', 'LTRS', 'LITRE', 'LITRES', 'LITER', 'LITERS', 'MTR', 'MTRS', 'METER', 'METERS', 'METRE', 'METRES']
    return u not in fractional_units

class ProductListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageInventory()]
    
    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            category_id = request.query_params.get('category')
            
            from django.db.models import Exists, OuterRef
            from apps.accounting.models import VoucherItem

            has_posted_purchase_subquery = VoucherItem.objects.filter(
                product=OuterRef('pk'),
                voucher__voucher_type='PURCHASE',
                voucher__status='POSTED'
            )

            qs = Product.objects.filter(company=company).select_related('category').annotate(
                has_posted_purchase=Exists(has_posted_purchase_subquery)
            ).only(
                'id', 'name', 'alias', 'brand', 'sku', 'category_id', 'category__name', 'category__hsn_code', 'category__gst_rate',
                'hsn_code', 'unit', 'alternate_unit', 'conversion_factor', 'gst_rate', 'tax_override',
                'selling_price', 'wholesaler_price', 'min_selling_price', 'purchase_price',
                'purchase_price_from_invoice', 'stock_quantity', 'costing_method', 'track_batches', 'track_serial_numbers', 'created_at'
            ).order_by('-created_at')

            if category_id:
                if category_id == 'unassigned':
                    qs = qs.filter(category__isnull=True)
                else:
                    qs = qs.filter(category_id=category_id)
                
            data = []
            for p in qs:
                has_posted_purchase = bool(getattr(p, 'has_posted_purchase', False))
                data.append({
                    "id": str(p.id),
                    "name": p.name,
                    "alias": p.alias or "",
                    "brand": p.brand or "",
                    "sku": p.sku,
                    "barcode": p.barcode or "",
                    "category": p.category.name if p.category else "Unassigned",
                    "category_id": str(p.category.id) if p.category else None,
                    "hsn_code": p.hsn_code if p.tax_override else (p.category.hsn_code if p.category and p.category.hsn_code else (p.hsn_code or "")),
                    "unit": p.unit,
                    "alternate_unit": p.alternate_unit or "",
                    "conversion_factor": str(p.conversion_factor),
                    "gst_rate": str(p.gst_rate) if p.tax_override else (str(p.category.gst_rate) if p.category else str(p.gst_rate)),
                    "tax_override": p.tax_override,
                    "selling_price": p.selling_price,
                    "wholesaler_price": p.wholesaler_price,
                    "min_selling_price": p.min_selling_price,
                    "purchase_price": p.purchase_price,
                    "purchase_price_from_invoice": getattr(p, 'purchase_price_from_invoice', False) and has_posted_purchase,
                    "stock_quantity": int(round(p.stock_quantity)) if is_integer_unit(p.unit) else p.stock_quantity,
                    "has_invoice_stock": has_posted_purchase,
                    "costing_method": getattr(p, 'costing_method', 'AVG_COST') or 'AVG_COST',
                    "track_batches": p.track_batches,
                    "track_serial_numbers": p.track_serial_numbers
                })
            category_stock_val = sum((p.stock_quantity * p.purchase_price) for p in qs if p.stock_quantity > Decimal('0.00'))
            category_retail_val = sum((p.stock_quantity * p.selling_price) for p in qs if p.stock_quantity > Decimal('0.00'))
            category_stock_qty = sum(p.stock_quantity for p in qs if p.stock_quantity > Decimal('0.00'))
            
            return Response({
                "success": True, 
                "data": data,
                "summary": {
                    "total_stock_value": str(category_stock_val.quantize(Decimal('0.01'))),
                    "total_retail_value": str(category_retail_val.quantize(Decimal('0.01'))),
                    "total_stock_quantity": str(category_stock_qty),
                    "total_items": len(data),
                }
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            data = request.data
            
            import uuid
            sku = data.get('sku') or data.get('name', 'UNKNOWN').upper()[:3] + '-' + str(uuid.uuid4())[:6]

            category = None
            if data.get('category_id'):
                category = ProductCategory.objects.get(id=data['category_id'], company=company)
            elif data.get('category_name'):
                category, _ = ProductCategory.objects.get_or_create(
                    company=company, 
                    name=data.get('category_name')
                )

            # Feature 3: Tax Overrides logic
            tax_override = data.get('tax_override', False)
            if tax_override:
                active_hsn = data.get('override_hsn_code', '')
                active_gst = data.get('override_gst_rate', 0.00)
            else:
                active_hsn = category.hsn_code if category else data.get('hsn_code', '')
                active_gst = category.gst_rate if category else data.get('gst_rate', 18.00)

            product = Product.objects.create(
                company=company,
                category=category,
                name=data.get('name'),
                brand=data.get('brand', ''),
                alias=data.get('alias', ''),
                sku=sku,
                barcode=data.get('barcode', ''),
                description=data.get('description', ''),
                unit=data.get('unit', 'PCS'),
                alternate_unit=data.get('alternate_unit', ''),
                conversion_factor=data.get('conversion_factor', 1.0000),
                hsn_code=active_hsn,
                gst_rate=active_gst,
                tax_override=tax_override,
                override_hsn_code=data.get('override_hsn_code', ''),
                override_gst_rate=data.get('override_gst_rate', 0.00) if data.get('override_gst_rate') else None,
                selling_price=data.get('selling_price', 0.00),
                wholesaler_price=data.get('wholesaler_price', 0.00),
                min_selling_price=data.get('min_selling_price', 0.00),
                purchase_price=data.get('purchase_price', 0.00),
                reorder_level=data.get('reorder_level', 0.00),
                costing_method=data.get('costing_method', 'AVG_COST'),
                track_batches=data.get('track_batches', False),
                track_serial_numbers=data.get('track_serial_numbers', False)
            )

            # Handle Opening Stock (Feature 7)
            from apps.common.money import to_decimal
            opening_qty = to_decimal(data.get('opening_qty', '0.00'))
            if is_integer_unit(product.unit):
                opening_qty = Decimal(int(round(opening_qty)))
            if opening_qty > Decimal('0.00'):
                from apps.inventory.models import Warehouse, InventoryEntry
                # Find default warehouse or use provided
                warehouse_id = data.get('warehouse_id')
                if warehouse_id:
                    warehouse = Warehouse.objects.get(id=warehouse_id, company=company)
                else:
                    warehouse = Warehouse.objects.filter(company=company).first()
                    if not warehouse:
                        warehouse = Warehouse.objects.create(company=company, name="Main Warehouse")
                
                InventoryEntry.objects.create(
                    company=company,
                    product=product,
                    warehouse=warehouse,
                    movement_type='IN',
                    quantity=opening_qty,
                    rate=product.purchase_price,
                    total_value=(opening_qty * product.purchase_price).quantize(Decimal('0.01')),
                    batch_number=data.get('opening_batch_number', ''),
                    expiry_date=data.get('opening_expiry_date', None) or None,
                    serial_number=data.get('opening_serial_number', '')
                )
                
                # Update product stock
                product.stock_quantity = opening_qty
                product.save(update_fields=['stock_quantity'])

            return Response({
                "success": True, 
                "data": {
                    "id": str(product.id), 
                    "name": product.name,
                    "sku": product.sku
                }
            }, status=201)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)



class ProductDetailView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageInventory()]

    def patch(self, request, company_id, product_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            product = Product.objects.get(id=product_id, company=company)
            data = request.data

            if 'name' in data: product.name = data['name']
            if 'alias' in data: product.alias = data['alias']
            if 'brand' in data: product.brand = data['brand']
            if 'selling_price' in data: product.selling_price = data['selling_price']
            if 'wholesaler_price' in data: product.wholesaler_price = data['wholesaler_price']
            if 'min_selling_price' in data: product.min_selling_price = data['min_selling_price']
            if 'purchase_price' in data: 
                product.purchase_price = data['purchase_price']
                product.purchase_price_from_invoice = False
            if 'sku' in data: product.sku = data['sku']
            if 'unit' in data: product.unit = data['unit']
            if 'costing_method' in data: product.costing_method = data['costing_method']
            
            if 'stock_quantity' in data:
                from apps.common.money import to_decimal
                new_stock = to_decimal(data['stock_quantity'])
                if is_integer_unit(product.unit):
                    new_stock = Decimal(int(round(new_stock)))
                product.stock_quantity = new_stock
                
                # Also update the Opening Stock InventoryEntry
                from apps.inventory.models import InventoryEntry, Warehouse
                opening_entry = InventoryEntry.objects.filter(product=product, voucher_id__isnull=True).first()
                if opening_entry:
                    if new_stock == Decimal('0.00'):
                        opening_entry.delete()
                    else:
                        opening_entry.quantity = new_stock
                        opening_entry.rate = product.purchase_price
                        opening_entry.total_value = (new_stock * product.purchase_price).quantize(Decimal('0.01'))
                        opening_entry.save()
                elif new_stock > Decimal('0.00'):
                    warehouse = Warehouse.objects.filter(company=company).first()
                    if not warehouse:
                        warehouse = Warehouse.objects.create(company=company, name="Main Warehouse")
                    InventoryEntry.objects.create(
                        company=company,
                        product=product,
                        warehouse=warehouse,
                        movement_type='IN',
                        quantity=new_stock,
                        rate=product.purchase_price,
                        total_value=(new_stock * product.purchase_price).quantize(Decimal('0.01'))
                    )

            product.save()
            return Response({"success": True, "data": {"id": str(product.id), "name": product.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

    def delete(self, request, company_id, product_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            product = Product.objects.get(id=product_id, company=company)
            
            # Check if product is used in vouchers
            from apps.accounting.models import VoucherItem
            if VoucherItem.objects.filter(product=product).exists():
                return Response({
                    "success": False, 
                    "error": f"Cannot delete {product.name} because it is used in one or more vouchers. Please delete the vouchers first or just rename this item."
                }, status=400)
                
            # Check if product has inventory entries (opening stock, etc.)
            from apps.inventory.models import InventoryEntry
            if InventoryEntry.objects.filter(product=product).exists():
                return Response({
                    "success": False, 
                    "error": f"Cannot delete {product.name} because it has active stock entries. Please clear its stock first or just rename this item."
                }, status=400)
                
            product.delete()
            return Response({"success": True, "message": "Product deleted successfully"})
        except Exception as e:
            # Generic fallback for ProtectedError
            if 'ProtectedError' in type(e).__name__ or 'protected foreign keys' in str(e):
                return Response({
                    "success": False, 
                    "error": f"Cannot delete {product.name} because it is being used by other records in the system."
                }, status=400)
            return Response({"success": False, "error": str(e)}, status=400)


class WarehouseListView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [IsAuthenticated(), IsCompanyMember()]
        return [IsAuthenticated(), CanManageInventory()]
    
    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            from .models import Warehouse
            warehouses = Warehouse.objects.filter(company=company)
            data = [
                {
                    "id": str(w.id),
                    "name": w.name,
                } for w in warehouses
            ]
            return Response({"success": True, "data": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class BulkBrandDiscountUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageInventory]

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            category_id = request.data.get('category_id')
            brand = request.data.get('brand')
            discount_percent = request.data.get('discount_percent')
            
            if not category_id or not brand or discount_percent is None:
                return Response({"success": False, "error": "category_id, brand, and discount_percent are required"}, status=400)
                
            discount_factor = (100 - float(discount_percent)) / 100.0
            
            # Get products
            products = Product.objects.filter(company=company, category_id=category_id, brand=brand)
            updated_count = 0
            for p in products:
                new_purchase_price = float(p.selling_price) * discount_factor
                p.purchase_price = new_purchase_price
                p.purchase_price_from_invoice = False
                p.save(update_fields=['purchase_price', 'purchase_price_from_invoice'])
                updated_count += 1
                
            return Response({
                "success": True, 
                "message": f"Updated purchase price for {updated_count} items."
            })
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

class PriceListBulkImportAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageInventory]

    def post(self, request, company_id):
        try:
            from apps.companies.models import Company
            from .services.price_list_service import PriceListService
            company = Company.objects.get(id=company_id, users__user=request.user)
            category_id = request.data.get('category_id')
            brand = request.data.get('brand', '')
            items = request.data.get('items', [])

            if not category_id:
                return Response({"success": False, "error": "Category is required."}, status=400)
            if not items:
                return Response({"success": False, "error": "No items provided for import."}, status=400)

            result = PriceListService.bulk_import_price_list(
                company=company,
                category_id=category_id,
                brand=brand,
                items_data=items
            )
            return Response(result)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class ParsePriceListPdfAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageInventory]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, company_id):
        try:
            import base64
            from apps.companies.models import Company
            from .services.price_list_service import PriceListService
            company = Company.objects.filter(id=company_id).first()
            if not company:
                return Response({"success": False, "error": "Company not found."}, status=404)

            if not request.user.is_superuser:
                has_access = company.users.filter(user=request.user).exists()
                if not has_access:
                    return Response({"success": False, "error": "Unauthorized access to this company."}, status=403)

            custom_api_key = request.headers.get('X-Gemini-Key') or request.data.get('gemini_api_key')
            filename = request.data.get('filename', '')
            brand = request.data.get('brand', '')
            scan_mode = request.data.get('scan_mode', 'auto')

            file_obj = request.FILES.get('file')
            file_base64 = request.data.get('file_base64')

            if not file_obj and not file_base64:
                return Response({"success": False, "error": "PDF file or file_base64 is required."}, status=400)

            if file_obj:
                raw_bytes = file_obj.read()
                filename = filename or getattr(file_obj, 'name', '')
            else:
                b64 = file_base64
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                missing_padding = len(b64) % 4
                if missing_padding:
                    b64 += '=' * (4 - missing_padding)
                raw_bytes = base64.b64decode(b64)

            result = PriceListService.parse_pdf_price_list(
                raw_bytes, 
                custom_api_key=custom_api_key, 
                filename=filename, 
                user_brand=brand,
                scan_mode=scan_mode
            )
            return Response(result)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class CombineInventoryItemsAPIView(APIView):
    permission_classes = [IsAuthenticated, CanManageInventory]

    def post(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            from apps.inventory.services.normalization_service import combine_and_deduplicate_inventory
            dry_run = request.data.get('dry_run', False)
            report = combine_and_deduplicate_inventory(company_id=company.id, dry_run=dry_run)
            return Response(report, status=200)
        except Company.DoesNotExist:
            return Response({"success": False, "error": "Company not found or unauthorized."}, status=404)
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=500)


class ProductHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id, product_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            from apps.inventory.services.item_analytics_service import ItemAnalyticsService
            result = ItemAnalyticsService.get_product_invoice_history(product_id=product_id, company=company)
            if not result:
                return Response({"success": False, "error": "Product not found."}, status=404)
            return Response({"success": True, "data": result})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class InventoryItemAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            category_id = request.query_params.get('category_id')
            limit = int(request.query_params.get('limit', 10))
            from apps.inventory.services.item_analytics_service import ItemAnalyticsService
            result = ItemAnalyticsService.get_top_moving_items(company=company, category_id=category_id, limit=limit)
            return Response({"success": True, "data": result})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


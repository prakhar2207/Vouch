from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Product, ProductCategory
from apps.companies.models import Company

class ProductCategoryListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            categories = ProductCategory.objects.filter(company=company).order_by('name')
            data = [
                {
                    "id": str(c.id), 
                    "name": c.name,
                    "hsn_code": c.hsn_code or "",
                    "gst_rate": str(c.gst_rate),
                    "item_count": c.products.count(),
                } for c in categories
            ]
            return Response({"success": True, "data": data})
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
    permission_classes = [IsAuthenticated]

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

class ProductListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, company_id):
        try:
            company = Company.objects.get(id=company_id, users__user=request.user)
            category_id = request.query_params.get('category')
            
            qs = Product.objects.filter(company=company).select_related('category').order_by('-created_at')
            if category_id:
                if category_id == 'unassigned':
                    qs = qs.filter(category__isnull=True)
                else:
                    qs = qs.filter(category_id=category_id)
                
            data = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "alias": p.alias or "",
                    "brand": p.brand or "",
                    "sku": p.sku,
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
                    "stock_quantity": p.stock_quantity,
                    "track_batches": p.track_batches,
                    "track_serial_numbers": p.track_serial_numbers
                } for p in qs
            ]
            return Response({"success": True, "data": data})
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
                track_batches=data.get('track_batches', False),
                track_serial_numbers=data.get('track_serial_numbers', False)
            )

            # Handle Opening Stock (Feature 7)
            opening_qty = float(data.get('opening_qty', 0))
            if opening_qty > 0:
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
                    total_value=opening_qty * float(product.purchase_price),
                    batch_number=data.get('opening_batch_number', ''),
                    expiry_date=data.get('opening_expiry_date', None) or None,
                    serial_number=data.get('opening_serial_number', '')
                )
                
                # Update product stock
                product.stock_quantity = opening_qty
                product.save()

            return Response({"success": True, "data": {"id": str(product.id), "name": product.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)



class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated]

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
            if 'purchase_price' in data: product.purchase_price = data['purchase_price']
            if 'sku' in data: product.sku = data['sku']
            if 'unit' in data: product.unit = data['unit']

            product.save()
            return Response({"success": True, "data": {"id": str(product.id), "name": product.name}})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)


class WarehouseListView(APIView):
    permission_classes = [IsAuthenticated]
    
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


class PriceListBulkImportAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def post(self, request, company_id):
        try:
            from apps.companies.models import Company
            from .services.price_list_service import PriceListService
            company = Company.objects.get(id=company_id, users__user=request.user)
            file_obj = request.FILES.get('file')
            if not file_obj:
                return Response({"success": False, "error": "PDF file is required."}, status=400)

            items = PriceListService.parse_pdf_price_list(file_obj)
            return Response({"success": True, "count": len(items), "items": items})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=400)

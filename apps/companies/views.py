from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Company, UserCompany
from .serializers import CompanySerializer
from apps.accounts.permissions import user_has_company_roles, get_user_company_role

def process_and_compress_image(file_obj, max_width=600, max_height=300, quality=85):
    """
    Compresses and normalizes an uploaded image using PIL/Pillow.
    Resizes proportionally if dimensions exceed max_width/max_height.
    Returns compressed base64 data URI for instant DB storage and offline rendering.
    """
    from PIL import Image
    import io
    import base64

    file_obj.seek(0)
    img = Image.open(file_obj)

    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        save_format = 'PNG'
        mime = 'image/png'
    else:
        img = img.convert('RGB')
        save_format = 'WEBP'
        mime = 'image/webp'

    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    if save_format == 'WEBP':
        img.save(buf, format='WEBP', quality=quality, method=6)
    else:
        img.save(buf, format='PNG', optimize=True)

    buf.seek(0)
    raw = buf.read()
    b64 = base64.b64encode(raw).decode('utf-8')
    return f"data:{mime};base64,{b64}"


def provision_company_defaults(company):
    import datetime
    from .models import CompanySettings
    from apps.inventory.models import Warehouse
    from apps.ledgers.models import LedgerGroup, Ledger
    from apps.accounting.models import FinancialYear

    # 1. Company Settings
    CompanySettings.objects.get_or_create(company=company)

    # 2. Main Godown / Warehouse
    Warehouse.objects.get_or_create(
        company=company,
        name="Main Godown",
        defaults={"address": company.address or ""}
    )

    # 3. Core Chart of Accounts (Ledger Groups)
    debtors_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Sundry Debtors", defaults={"nature": "ASSET"}
    )
    creditors_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Sundry Creditors", defaults={"nature": "LIABILITY"}
    )
    sales_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Sales Accounts", defaults={"nature": "INCOME"}
    )
    purchase_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Purchase Accounts", defaults={"nature": "EXPENSE"}
    )
    duties_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Duties & Taxes", defaults={"nature": "LIABILITY"}
    )
    bank_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Bank Accounts", defaults={"nature": "ASSET"}
    )
    cash_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Cash-in-Hand", defaults={"nature": "ASSET"}
    )
    indirect_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Indirect Expenses", defaults={"nature": "EXPENSE"}
    )
    direct_grp, _ = LedgerGroup.objects.get_or_create(
        company=company, name="Direct Expenses", defaults={"nature": "EXPENSE"}
    )

    # 4. Standard Ledgers
    Ledger.objects.get_or_create(company=company, name="Sales Account", defaults={"group": sales_grp, "ledger_type": "SALES"})
    Ledger.objects.get_or_create(company=company, name="Purchase Account", defaults={"group": purchase_grp, "ledger_type": "PURCHASE"})
    Ledger.objects.get_or_create(company=company, name="Cash", defaults={"group": cash_grp, "ledger_type": "CASH"})
    Ledger.objects.get_or_create(company=company, name="Round Off", defaults={"group": indirect_grp, "ledger_type": "ROUND_OFF"})
    Ledger.objects.get_or_create(company=company, name="Cartage Outward", defaults={"group": indirect_grp, "ledger_type": "EXPENSE"})
    Ledger.objects.get_or_create(company=company, name="Cartage Inward", defaults={"group": direct_grp, "ledger_type": "EXPENSE"})
    Ledger.objects.get_or_create(company=company, name="Output CGST", defaults={"group": duties_grp, "ledger_type": "TAX"})
    Ledger.objects.get_or_create(company=company, name="Output SGST", defaults={"group": duties_grp, "ledger_type": "TAX"})
    Ledger.objects.get_or_create(company=company, name="Output IGST", defaults={"group": duties_grp, "ledger_type": "TAX"})
    Ledger.objects.get_or_create(company=company, name="Input CGST", defaults={"group": duties_grp, "ledger_type": "TAX"})
    Ledger.objects.get_or_create(company=company, name="Input SGST", defaults={"group": duties_grp, "ledger_type": "TAX"})
    Ledger.objects.get_or_create(company=company, name="Input IGST", defaults={"group": duties_grp, "ledger_type": "TAX"})

    # 5. Financial Year (Current Indian FY)
    today = datetime.date.today()
    if today.month >= 4:
        start_year = today.year
        end_year = today.year + 1
    else:
        start_year = today.year - 1
        end_year = today.year
    code = f"{str(start_year)[-2:]}-{str(end_year)[-2:]}"
    FinancialYear.objects.get_or_create(
        company=company,
        code=code,
        defaults={
            "name": f"FY {code}",
            "start_date": datetime.date(start_year, 4, 1),
            "end_date": datetime.date(end_year, 3, 31),
            "is_closed": False,
        }
    )

    # 6. Auto-sync Bank Account Ledger (if bank details exist)
    from apps.companies.services import CompanyBankService
    CompanyBankService.sync_company_bank_ledger(company)


class CompanyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CompanySerializer

    def get_queryset(self):
        # Only return active companies the user belongs to with pre-fetched settings
        return Company.objects.filter(users__user=self.request.user, is_active=True).select_related('settings')

    def perform_create(self, serializer):
        import base64
        # Create the company
        company = serializer.save()

        # Handle Logo compression and storage
        logo_file = self.request.FILES.get('logo')
        if logo_file:
            try:
                company.logo_data = process_and_compress_image(logo_file, max_width=600, max_height=300)
                company.save(update_fields=['logo_data'])
            except Exception as e:
                print(f"Error compressing company logo: {e}")
        elif 'logo_data' in self.request.data and self.request.data['logo_data']:
            company.logo_data = self.request.data['logo_data']
            company.save(update_fields=['logo_data'])

        # Handle Signature
        sig_file = self.request.FILES.get('proprietor_signature')
        if sig_file:
            try:
                company.signature_data = process_and_compress_image(sig_file, max_width=400, max_height=180)
                company.save(update_fields=['signature_data'])
            except Exception as e:
                print(f"Error encoding signature: {e}")
        elif 'signature_data' in self.request.data and self.request.data['signature_data']:
            company.signature_data = self.request.data['signature_data']
            company.save(update_fields=['signature_data'])

        if getattr(self.request.user, 'is_superuser', False) or self.request.user.email.strip().lower() == 'prakharssa@gmail.com':
            raise PermissionDenied("Platform administrators cannot create or own tenant business companies.")

        # Automatically map the user as the OWNER of the newly created company
        UserCompany.objects.create(
            user=self.request.user,
            company=company,
            role='OWNER'
        )
        if self.request.user.role != 'OWNER':
            self.request.user.role = 'OWNER'
            self.request.user.save(update_fields=['role'])

        # Auto-provision complete chart of accounts, warehouse, and financial year
        provision_company_defaults(company)

    def perform_update(self, serializer):
        company = self.get_object()
        if not user_has_company_roles(self.request.user, company, ['OWNER']):
            raise PermissionDenied("Only Company Owners can modify company details.")

        import base64
        instance = serializer.save()

        # Handle Logo: Upload, update or deletion
        logo_file = self.request.FILES.get('logo')
        if logo_file:
            try:
                instance.logo_data = process_and_compress_image(logo_file, max_width=600, max_height=300)
                instance.save(update_fields=['logo_data'])
            except Exception as e:
                print(f"Error compressing company logo: {e}")
        elif self.request.data.get('remove_logo') in [True, 'true', '1'] or (
            'logo_data' in self.request.data and not self.request.data.get('logo_data')
        ):
            instance.logo = None
            instance.logo_data = None
            instance.save(update_fields=['logo', 'logo_data'])
        elif 'logo_data' in self.request.data and self.request.data['logo_data']:
            instance.logo_data = self.request.data['logo_data']
            instance.save(update_fields=['logo_data'])

        # Handle Signature: Upload, update or deletion
        sig_file = self.request.FILES.get('proprietor_signature')
        if sig_file:
            try:
                instance.signature_data = process_and_compress_image(sig_file, max_width=400, max_height=180)
                instance.save(update_fields=['signature_data'])
            except Exception as e:
                print(f"Error encoding signature: {e}")
        elif self.request.data.get('remove_signature') in [True, 'true', '1'] or (
            'signature_data' in self.request.data and not self.request.data.get('signature_data')
        ):
            instance.proprietor_signature = None
            instance.signature_data = None
            instance.save(update_fields=['proprietor_signature', 'signature_data'])
        elif 'signature_data' in self.request.data and self.request.data['signature_data']:
            instance.signature_data = self.request.data['signature_data']
            instance.save(update_fields=['signature_data'])

        # Handle Stamp: Upload, update or deletion
        stamp_file = self.request.FILES.get('stamp')
        if stamp_file:
            try:
                instance.stamp_data = process_and_compress_image(stamp_file, max_width=300, max_height=300)
                instance.save(update_fields=['stamp_data'])
            except Exception as e:
                print(f"Error encoding stamp: {e}")
        elif self.request.data.get('remove_stamp') in [True, 'true', '1'] or (
            'stamp_data' in self.request.data and not self.request.data.get('stamp_data')
        ):
            instance.stamp = None
            instance.stamp_data = None
            instance.save(update_fields=['stamp', 'stamp_data'])
        elif 'stamp_data' in self.request.data and self.request.data['stamp_data']:
            instance.stamp_data = self.request.data['stamp_data']
            instance.save(update_fields=['stamp_data'])

        # Auto-sync Bank Account Ledger in Chart of Accounts
        from apps.companies.services import CompanyBankService
        CompanyBankService.sync_company_bank_ledger(instance)


    def destroy(self, request, *args, **kwargs):
        company = self.get_object()
        
        # 1. Strict Admin / Owner Authorization
        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER']):
            return Response({
                "success": False,
                "error": "Only Administrators and Company Owners can delete or archive the company."
            }, status=status.HTTP_403_FORBIDDEN)

        # 2. Re-authentication password check
        password = request.data.get('password') or request.headers.get('X-Confirmation-Password')
        if not password or not request.user.check_password(password):
            return Response({
                "success": False,
                "error": "Password re-authentication required for company deletion confirmation."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Soft-delete archive
        company.is_active = False
        company.deleted_at = timezone.now()
        company.save(update_fields=['is_active', 'deleted_at'])

        # 4. Audit Log
        from apps.audit.services.audit_service import AuditService
        AuditService.log_action(
            company=company,
            user=request.user,
            action='DELETE',
            model_name='Company',
            record_id=company.id,
            changes={"is_active": False, "deleted_at": str(company.deleted_at)}
        )

        return Response({
            "success": True,
            "message": f"Company '{company.name}' has been safely archived."
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "success": True,
            "data": response.data,
            "message": "Company created successfully"
        })

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "success": True,
            "data": response.data
        })

    @action(detail=True, methods=['patch'])
    def update_settings(self, request, pk=None):
        company = self.get_object()
        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER']):
            return Response({
                "success": False,
                "error": "Only Administrators and Company Owners are permitted to modify company settings."
            }, status=status.HTTP_403_FORBIDDEN)

        from .models import CompanySettings
        try:
            settings = company.settings
        except CompanySettings.DoesNotExist:
            settings = CompanySettings.objects.create(company=company)
            
        # Update allowed fields
        if 'enable_ledger_mapping' in request.data:
            settings.enable_ledger_mapping = request.data['enable_ledger_mapping']
        if 'enable_manual_invoice_number' in request.data:
            settings.enable_manual_invoice_number = request.data['enable_manual_invoice_number']
        if 'enable_advanced_item_creation' in request.data:
            settings.enable_advanced_item_creation = request.data['enable_advanced_item_creation']
        if 'complexity_level' in request.data:
            settings.complexity_level = request.data['complexity_level']
        if 'allow_negative_stock' in request.data:
            settings.allow_negative_stock = bool(request.data['allow_negative_stock'])
        if 'sales_invoice_prefix' in request.data:
            settings.sales_invoice_prefix = str(request.data['sales_invoice_prefix']).strip()[:10]
        if 'purchase_invoice_prefix' in request.data:
            settings.purchase_invoice_prefix = str(request.data['purchase_invoice_prefix']).strip()[:10]
        if 'document_branding' in request.data:
            incoming_branding = request.data['document_branding']
            if isinstance(incoming_branding, dict):
                current_branding = dict(settings.document_branding or {})
                current_branding.update(incoming_branding)
                settings.document_branding = current_branding
            elif isinstance(incoming_branding, str):
                import json
                try:
                    current_branding = dict(settings.document_branding or {})
                    current_branding.update(json.loads(incoming_branding))
                    settings.document_branding = current_branding
                except Exception:
                    pass
            
        settings.save()
        return Response({"success": True, "message": "Settings updated"})

    @action(detail=True, methods=['get', 'post'])
    def members(self, request, pk=None):
        company = self.get_object()
        from apps.accounts.models import User
        from .models import UserCompany

        if request.method == 'GET':
            user_companies = UserCompany.objects.filter(company=company).select_related('user').order_by('created_at')
            data = [
                {
                    "id": str(uc.id),
                    "user_id": str(uc.user.id),
                    "email": uc.user.email,
                    "name": uc.user.first_name or uc.user.email.split('@')[0],
                    "role": uc.role,
                    "is_current_user": uc.user_id == request.user.id,
                    "created_at": uc.created_at.strftime('%Y-%m-%d')
                }
                for uc in user_companies
            ]
            return Response({"success": True, "data": data})

        # POST: Invite or add member
        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER']):
            return Response({"success": False, "error": "Only Administrators and Owners can invite team members."}, status=status.HTTP_403_FORBIDDEN)

        email = (request.data.get('email') or '').strip().lower()
        role = (request.data.get('role') or 'VIEWER').strip().upper()
        if not email:
            return Response({"success": False, "error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE', 'VIEWER']
        if role not in allowed_roles:
            return Response({"success": False, "error": f"Invalid role. Allowed roles: {', '.join(allowed_roles)}"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            import secrets
            temp_pass = secrets.token_urlsafe(12) + "A1!"
            user = User.objects.create_user(email=email, password=temp_pass, role=role)

        uc, created = UserCompany.objects.get_or_create(
            company=company,
            user=user,
            defaults={'role': role}
        )
        if not created:
            uc.role = role
            uc.save(update_fields=['role'])

        return Response({
            "success": True,
            "message": f"User '{email}' assigned role '{role}'.",
            "data": {
                "id": str(uc.id),
                "user_id": str(user.id),
                "email": user.email,
                "role": uc.role
            }
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'members/(?P<member_id>[^/.]+)')
    def member_detail(self, request, pk=None, member_id=None):
        company = self.get_object()
        from .models import UserCompany

        if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER']):
            return Response({"success": False, "error": "Only Administrators and Owners can manage team members."}, status=status.HTTP_403_FORBIDDEN)

        uc = UserCompany.objects.filter(id=member_id, company=company).first()
        if not uc:
            return Response({"success": False, "error": "Member not found in this company."}, status=status.HTTP_404_NOT_FOUND)

        requester_role = get_user_company_role(request.user, company)
        if uc.role == 'OWNER' and requester_role != 'OWNER':
            return Response({"success": False, "error": "Company Owner roles can only be modified or removed by other Owners of this company."}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'DELETE':
            uc.delete()
            return Response({"success": True, "message": "Member removed from company."})

        new_role = (request.data.get('role') or '').strip().upper()
        allowed_roles = ['ADMIN', 'OWNER', 'CA', 'EMPLOYEE', 'VIEWER']
        if new_role not in allowed_roles:
            return Response({"success": False, "error": f"Invalid role: {new_role}"}, status=status.HTTP_400_BAD_REQUEST)

        uc.role = new_role
        uc.save(update_fields=['role'])
        return Response({"success": True, "message": f"Role updated to {new_role}."})

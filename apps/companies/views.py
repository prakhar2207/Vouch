from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Company, UserCompany
from .serializers import CompanySerializer
from apps.accounts.permissions import user_has_company_roles, get_user_company_role

class CompanyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CompanySerializer

    def get_queryset(self):
        # Only return active companies the user belongs to
        user_companies = UserCompany.objects.filter(user=self.request.user).values_list('company_id', flat=True)
        return Company.objects.filter(id__in=user_companies, is_active=True)

    def perform_create(self, serializer):
        import base64
        # Create the company
        company = serializer.save()
        sig_file = self.request.FILES.get('proprietor_signature')
        if sig_file:
            try:
                sig_file.seek(0)
                raw = sig_file.read()
                mime = getattr(sig_file, 'content_type', 'image/png')
                company.signature_data = f"data:{mime};base64,{base64.b64encode(raw).decode('utf-8')}"
                company.save(update_fields=['signature_data'])
            except Exception as e:
                print(f"Error encoding signature: {e}")
        elif 'signature_data' in self.request.data and self.request.data['signature_data']:
            company.signature_data = self.request.data['signature_data']
            company.save(update_fields=['signature_data'])

        # Automatically map the user as the OWNER of the newly created company
        UserCompany.objects.create(
            user=self.request.user,
            company=company,
            role='OWNER'
        )
        # Create default settings
        from .models import CompanySettings
        CompanySettings.objects.create(company=company)

    def perform_update(self, serializer):
        company = self.get_object()
        if not user_has_company_roles(self.request.user, company, ['OWNER', 'ADMIN']):
            raise PermissionDenied("Only Company Owners or Admins can modify company details.")

        import base64
        instance = serializer.save()
        sig_file = self.request.FILES.get('proprietor_signature')
        if sig_file:
            try:
                sig_file.seek(0)
                raw = sig_file.read()
                mime = getattr(sig_file, 'content_type', 'image/png')
                instance.signature_data = f"data:{mime};base64,{base64.b64encode(raw).decode('utf-8')}"
                instance.save(update_fields=['signature_data'])
            except Exception as e:
                print(f"Error encoding signature: {e}")
        elif 'signature_data' in self.request.data and self.request.data['signature_data']:
            instance.signature_data = self.request.data['signature_data']
            instance.save(update_fields=['signature_data'])

    def destroy(self, request, *args, **kwargs):
        company = self.get_object()
        
        # 1. Strict Owner Authorization
        if not user_has_company_roles(request.user, company, ['OWNER']):
            return Response({
                "success": False,
                "error": "Only the Company Owner can delete or archive the company."
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
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            return Response({
                "success": False,
                "error": "Only Company Owners and Admins are permitted to modify company settings."
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
        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            return Response({"success": False, "error": "Only Owners and Admins can invite team members."}, status=status.HTTP_403_FORBIDDEN)

        email = (request.data.get('email') or '').strip().lower()
        role = (request.data.get('role') or 'VIEWER').strip().upper()
        if not email:
            return Response({"success": False, "error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        allowed_roles = ['ADMIN', 'ACCOUNTANT', 'SALES', 'PURCHASE', 'VIEWER']
        if role not in allowed_roles:
            return Response({"success": False, "error": f"Invalid role. Allowed roles: {', '.join(allowed_roles)}"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            import secrets
            temp_pass = secrets.token_urlsafe(12) + "A1!"
            user = User.objects.create_user(email=email, password=temp_pass)

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

        if not user_has_company_roles(request.user, company, ['OWNER', 'ADMIN']):
            return Response({"success": False, "error": "Only Owners and Admins can manage team members."}, status=status.HTTP_403_FORBIDDEN)

        uc = UserCompany.objects.filter(id=member_id, company=company).first()
        if not uc:
            return Response({"success": False, "error": "Member not found in this company."}, status=status.HTTP_404_NOT_FOUND)

        if uc.role == 'OWNER' and not getattr(request.user, 'is_superuser', False):
            return Response({"success": False, "error": "Company Owner cannot be modified or removed."}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'DELETE':
            uc.delete()
            return Response({"success": True, "message": "Member removed from company."})

        new_role = (request.data.get('role') or '').strip().upper()
        allowed_roles = ['ADMIN', 'ACCOUNTANT', 'SALES', 'PURCHASE', 'VIEWER']
        if new_role not in allowed_roles:
            return Response({"success": False, "error": f"Invalid role: {new_role}"}, status=status.HTTP_400_BAD_REQUEST)

        uc.role = new_role
        uc.save(update_fields=['role'])
        return Response({"success": True, "message": f"Role updated to {new_role}."})

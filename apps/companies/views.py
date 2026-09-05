from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Company, UserCompany
from .serializers import CompanySerializer

class CompanyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CompanySerializer

    def get_queryset(self):
        # Only return companies the user belongs to
        user_companies = UserCompany.objects.filter(user=self.request.user).values_list('company_id', flat=True)
        return Company.objects.filter(id__in=user_companies)

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
            
        settings.save()
        return Response({"success": True, "message": "Settings updated"})

from rest_framework import serializers
from .models import Company, UserCompany, CompanySettings

class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    settings = CompanySettingsSerializer(read_only=True)
    linked_bank_ledger_id = serializers.SerializerMethodField()
    linked_bank_ledger_name = serializers.SerializerMethodField()

    def get_linked_bank_ledger_id(self, obj):
        from apps.ledgers.models import Ledger
        if not obj.bank_account_number and not obj.bank_name:
            return None
        if obj.bank_account_number:
            l = Ledger.objects.filter(company=obj, ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'], bank_account_number__iexact=obj.bank_account_number).first()
            if l:
                return str(l.id)
        if obj.bank_name:
            l = Ledger.objects.filter(company=obj, ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'], name__icontains=obj.bank_name).first()
            if l:
                return str(l.id)
        return None

    def get_linked_bank_ledger_name(self, obj):
        from apps.ledgers.models import Ledger
        if not obj.bank_account_number and not obj.bank_name:
            return None
        if obj.bank_account_number:
            l = Ledger.objects.filter(company=obj, ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'], bank_account_number__iexact=obj.bank_account_number).first()
            if l:
                return l.name
        if obj.bank_name:
            l = Ledger.objects.filter(company=obj, ledger_type__in=['BANK', 'BANK_OD', 'BANK_OCC'], name__icontains=obj.bank_name).first()
            if l:
                return l.name
        return None

    class Meta:
        model = Company
        fields = '__all__'

class UserCompanySerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    
    class Meta:
        model = UserCompany
        fields = ['id', 'company', 'role', 'created_at']

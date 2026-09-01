from rest_framework import serializers
from .models import Company, UserCompany, CompanySettings

class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    settings = CompanySettingsSerializer(read_only=True)
    class Meta:
        model = Company
        fields = '__all__'

class UserCompanySerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    
    class Meta:
        model = UserCompany
        fields = ['id', 'company', 'role', 'created_at']

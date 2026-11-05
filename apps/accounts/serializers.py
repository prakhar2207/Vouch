from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role', 'is_active', 'is_staff', 'is_superuser', 'email_verified', 'created_at']

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        token['email_verified'] = getattr(user, 'email_verified', True)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if hasattr(self.user, 'email_verified') and not self.user.email_verified:
            raise serializers.ValidationError({"email": "Your email address is not verified. Please verify your email to log in."})

        data['user'] = {
            'id': str(self.user.id),
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'role': self.user.role,
            'is_staff': self.user.is_staff,
            'is_superuser': self.user.is_superuser,
            'email_verified': getattr(self.user, 'email_verified', True),
        }
        return data

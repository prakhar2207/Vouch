from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'role',
            'is_active',
            'is_staff',
            'is_superuser',
            'email_verified',
            'created_at',
        ]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        token['email_verified'] = getattr(user, 'email_verified', True)
        token['token_version'] = int(getattr(user, 'token_version', 0) or 0)
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


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    refresh = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        request = self.context.get('request')
        if not attrs.get('refresh') and request is not None:
            from .cookies import get_refresh_cookie_name
            cookie_refresh = request.COOKIES.get(get_refresh_cookie_name())
            if cookie_refresh:
                attrs['refresh'] = cookie_refresh
        if not attrs.get('refresh'):
            raise InvalidToken('No valid refresh token provided.')

        refresh = self.token_class(attrs['refresh'])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        user = None
        if user_id:
            user = get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
        if user is None or not api_settings.USER_AUTHENTICATION_RULE(user):
            raise InvalidToken('User account is inactive or no longer exists.')

        current_version = int(getattr(user, 'token_version', 0) or 0)
        token_version = refresh.payload.get('token_version', None)
        if token_version is None and current_version > 0:
            raise InvalidToken('Session revoked. Please sign in again.')
        if token_version is not None and int(token_version) != current_version:
            raise InvalidToken('Session revoked. Please sign in again.')

        data = super().validate({'refresh': attrs['refresh']})

        # Ensure freshly issued access token carries latest user claims + token_version
        access_token = refresh.access_token
        access_token['email'] = user.email
        access_token['role'] = user.role
        access_token['is_staff'] = user.is_staff
        access_token['is_superuser'] = user.is_superuser
        access_token['email_verified'] = getattr(user, 'email_verified', True)
        access_token['token_version'] = current_version
        data['access'] = str(access_token)
        data['user'] = {
            'id': str(user.id),
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'email_verified': getattr(user, 'email_verified', True),
        }
        return data

from django.urls import path
from .views import (
    CurrentUserView,
    RegisterView,
    RegisterInitiateView,
    RegisterVerifyOtpView,
    RegisterResendOtpView,
    RegisterCompleteView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
)

urlpatterns = [
    # Login & Profile
    path('login/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='current_user'),

    # Multi-step OTP Registration
    path('register/', RegisterView.as_view(), name='register'),
    path('register/initiate/', RegisterInitiateView.as_view(), name='register_initiate'),
    path('register/verify-otp/', RegisterVerifyOtpView.as_view(), name='register_verify_otp'),
    path('register/resend-otp/', RegisterResendOtpView.as_view(), name='register_resend_otp'),
    path('register/complete/', RegisterCompleteView.as_view(), name='register_complete'),

    # Password Recovery
    path('password/reset/request/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
]

from django.urls import path
from .views import (
    CsrfCookieView,
    CurrentUserView,
    LogoutView,
    RegisterView,
    RegisterInitiateView,
    RegisterVerifyOtpView,
    RegisterResendOtpView,
    RegisterCompleteView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
    AccountDeletionView,
    AccountDeletionStatusView,
)

urlpatterns = [
    # Login, Refresh, Logout, CSRF & Profile
    path('csrf/', CsrfCookieView.as_view(), name='csrf_cookie'),
    path('login/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
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

    # Self-Service Account Deletion & Status Receipt
    path('account/delete-request/', AccountDeletionView.as_view(), name='account_delete_request'),
    path('account/delete-status/', AccountDeletionStatusView.as_view(), name='account_delete_status'),
]

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CurrentUserView, RegisterView, ThrottledTokenObtainPairView

urlpatterns = [
    path('login/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('register/', RegisterView.as_view(), name='register'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='current_user'),
]

from django.urls import path
from .views import CurrentUserView, RegisterView, ThrottledTokenObtainPairView, ThrottledTokenRefreshView

urlpatterns = [
    path('login/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('register/', RegisterView.as_view(), name='register'),
    path('refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='current_user'),
]

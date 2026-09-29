
from django.urls import path
from .views import PushSubscriptionAPIView, NotificationListAPIView, NotificationMarkReadAPIView

urlpatterns = [
    path('subscribe/', PushSubscriptionAPIView.as_view(), name='push_subscribe'),
    path('', NotificationListAPIView.as_view(), name='notification_list'),
    path('mark-read/', NotificationMarkReadAPIView.as_view(), name='notification_mark_read_all'),
    path('<int:pk>/mark-read/', NotificationMarkReadAPIView.as_view(), name='notification_mark_read'),
]

from django.urls import path
from .views import (
    PushSubscriptionAPIView,
    NotificationListAPIView,
    NotificationMarkReadAPIView,
    NotificationPreferencesAPIView,
    SecureInvoicePublicView,
    EmailDeliveryLogListView,
)

urlpatterns = [
    # Push & In-App Notifications
    path('subscribe/', PushSubscriptionAPIView.as_view(), name='push_subscribe'),
    path('', NotificationListAPIView.as_view(), name='notification_list'),
    path('mark-read/', NotificationMarkReadAPIView.as_view(), name='notification_mark_read_all'),
    path('<int:pk>/mark-read/', NotificationMarkReadAPIView.as_view(), name='notification_mark_read'),

    # Company Notification Preferences
    path('preferences/', NotificationPreferencesAPIView.as_view(), name='notification_preferences'),

    # Public Secure Invoice View & Download (Tokenized)
    path('invoices/public/view/', SecureInvoicePublicView.as_view(), name='secure_invoice_public_view'),

    # Delivery Logs Forensics
    path('logs/', EmailDeliveryLogListView.as_view(), name='email_delivery_logs'),
]

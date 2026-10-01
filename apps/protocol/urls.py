from django.urls import path
from .views import (
    ProtocolSyncAPIView,
    ProtocolHandshakeAPIView,
    ProtocolCommitmentAPIView,
    ProtocolDeviceRegistrationAPIView
)

urlpatterns = [
    path('sync/', ProtocolSyncAPIView.as_view(), name='protocol_sync'),
    path('handshake/', ProtocolHandshakeAPIView.as_view(), name='protocol_handshake'),
    path('commitment/<str:tx_id>/', ProtocolCommitmentAPIView.as_view(), name='protocol_commitment'),
    path('devices/register/', ProtocolDeviceRegistrationAPIView.as_view(), name='protocol_device_register'),
]

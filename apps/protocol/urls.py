from django.urls import path
from .views import (
    ProtocolSyncAPIView,
    ProtocolHandshakeAPIView,
    ProtocolCommitmentAPIView,
    ProtocolDeviceRegistrationAPIView,
    ProtocolDeviceRotationAPIView,
    ProtocolDeviceRevocationAPIView,
    ProtocolPendingMappingsAPIView,
    ProtocolMappingApprovalAPIView
)

urlpatterns = [
    path('sync/', ProtocolSyncAPIView.as_view(), name='protocol_sync'),
    path('handshake/', ProtocolHandshakeAPIView.as_view(), name='protocol_handshake'),
    path('commitment/<str:tx_id>/', ProtocolCommitmentAPIView.as_view(), name='protocol_commitment'),
    path('devices/register/', ProtocolDeviceRegistrationAPIView.as_view(), name='protocol_device_register'),
    path('devices/rotate/', ProtocolDeviceRotationAPIView.as_view(), name='protocol_device_rotate'),
    path('devices/revoke/', ProtocolDeviceRevocationAPIView.as_view(), name='protocol_device_revoke'),
    path('mappings/pending/', ProtocolPendingMappingsAPIView.as_view(), name='protocol_pending_mappings'),
    path('mappings/approve/', ProtocolMappingApprovalAPIView.as_view(), name='protocol_mapping_approval'),
]

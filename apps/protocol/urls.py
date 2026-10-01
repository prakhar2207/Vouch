from django.urls import path
from .views import ProtocolSyncAPIView, ProtocolHandshakeAPIView, ProtocolCommitmentAPIView

urlpatterns = [
    path('sync/', ProtocolSyncAPIView.as_view(), name='protocol_sync'),
    path('handshake/', ProtocolHandshakeAPIView.as_view(), name='protocol_handshake'),
    path('commitment/<str:tx_id>/', ProtocolCommitmentAPIView.as_view(), name='protocol_commitment'),
]

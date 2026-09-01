"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from django.conf import settings
from django.conf.urls.static import static

from apps.accounting.views import UniversalVoucherAPIView, VoucherDetailAPIView
from apps.accounting.ocr_views import OCRExtractAPIView
from apps.analytics.views import InsightsAPIView
from apps.accounting.b2b_views import (
    InwardVoucherInboxView, InwardVoucherDetailView, InwardVoucherAcceptView, InwardVoucherRejectView
)
from apps.accounting.tally_views import TallyExportAPIView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Top-Level Direct API Endpoints
    path('api/vouchers/', UniversalVoucherAPIView.as_view(), name='api_vouchers_root'),
    path('api/vouchers/<uuid:voucher_id>/', VoucherDetailAPIView.as_view(), name='api_voucher_detail_root'),
    path('api/ocr/extract/', OCRExtractAPIView.as_view(), name='api_ocr_extract_root'),
    path('api/insights/', InsightsAPIView.as_view(), name='api_insights_root'),
    
    # B2B EDI Network Handshake Endpoints
    path('api/b2b/inbox/', InwardVoucherInboxView.as_view(), name='api_b2b_inbox'),
    path('api/b2b/inbox/<uuid:pk>/', InwardVoucherDetailView.as_view(), name='api_b2b_inbox_detail'),
    path('api/b2b/inbox/<uuid:pk>/accept/', InwardVoucherAcceptView.as_view(), name='api_b2b_inbox_accept'),
    path('api/b2b/inbox/<uuid:pk>/reject/', InwardVoucherRejectView.as_view(), name='api_b2b_inbox_reject'),

    # Tally XML Export Bridge
    path('api/export/tally/xml/', TallyExportAPIView.as_view(), name='api_tally_export_xml'),
    
    # Standard v1 Namespaced Endpoints
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/companies/', include('apps.companies.urls')),
    path('api/v1/accounting/', include('apps.accounting.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),
    path('api/v1/inventory/', include('apps.inventory.urls')),
    path('api/v1/ledgers/', include('apps.ledgers.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

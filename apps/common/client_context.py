import logging
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger(__name__)

class ClientContextMiddleware(MiddlewareMixin):
    """
    Identifies and attaches client context (platform, version, device)
    from request headers for Web, Desktop (Tauri/Electron), and Mobile (React Native/Flutter).
    
    Supported headers:
    - X-Client-Type: web | mobile_android | mobile_ios | desktop_windows | desktop_macos | desktop_linux | pos
    - X-App-Version: Semver string (e.g. 1.2.0)
    - X-Device-Id: Hardware or installation UUID
    """

    DEFAULT_CLIENT_TYPE = 'web'

    def process_request(self, request):
        client_type = (
            request.META.get('HTTP_X_CLIENT_TYPE') or
            request.META.get('HTTP_CLIENT_TYPE') or
            self.DEFAULT_CLIENT_TYPE
        ).lower().strip()

        app_version = (
            request.META.get('HTTP_X_APP_VERSION') or
            request.META.get('HTTP_APP_VERSION') or
            '1.0.0'
        ).strip()

        device_id = (
            request.META.get('HTTP_X_DEVICE_ID') or
            request.META.get('HTTP_DEVICE_ID') or
            'browser'
        ).strip()

        request.client_context = {
            'client_type': client_type,
            'app_version': app_version,
            'device_id': device_id,
            'is_mobile': client_type in ('mobile_android', 'mobile_ios', 'mobile'),
            'is_desktop': client_type.startswith('desktop_') or client_type in ('desktop', 'pos'),
            'is_web': client_type == 'web',
        }

    def process_response(self, request, response):
        # Expose server version and supported API level
        response['X-Server-Version'] = '1.0.2'
        response['X-API-Contract'] = 'v1'
        return response

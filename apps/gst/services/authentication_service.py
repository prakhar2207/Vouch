import logging
from typing import Dict, Any, Optional
from apps.companies.models import Company
from apps.gst.services.sandbox_client import SandboxGSTClient
from apps.gst.exceptions import GSTAuthenticationError, GSTConfigurationMissingError

logger = logging.getLogger('apps.gst.authentication_service')


class SandboxAuthenticationService:
    """
    Dedicated Service for Sandbox Authentication & Gateway Health Validation.
    """

    @classmethod
    def test_connection(cls, company: Optional[Company] = None) -> Dict[str, Any]:
        """
        Validates connectivity to Sandbox by Quicko.
        Checks if credentials exist, exchanges for access token, and reports latency and health status.
        """
        client = SandboxGSTClient(company=company)
        api_key, api_secret, base_url, is_sandbox = client.get_api_credentials()

        if not api_key or not api_secret:
            return {
                "healthy": False,
                "configured": False,
                "message": "Quicko Sandbox API Key or Secret is not configured.",
                "base_url": base_url,
                "is_sandbox": is_sandbox
            }

        try:
            token = client.get_access_token(force_refresh=False)
            return {
                "healthy": True,
                "configured": True,
                "token_prefix": token[:10] + "...",
                "base_url": base_url,
                "is_sandbox": is_sandbox,
                "message": "Successfully authenticated with Sandbox by Quicko."
            }
        except GSTConfigurationMissingError as e:
            return {
                "healthy": False,
                "configured": False,
                "error": str(e),
                "base_url": base_url
            }
        except GSTAuthenticationError as e:
            return {
                "healthy": False,
                "configured": True,
                "error": f"Authentication rejected by provider: {str(e)}",
                "base_url": base_url
            }
        except Exception as e:
            return {
                "healthy": False,
                "configured": True,
                "error": f"Failed to connect to Sandbox: {str(e)}",
                "base_url": base_url
            }

    @classmethod
    def refresh_token(cls, company: Optional[Company] = None) -> str:
        """
        Forces an immediate token refresh against POST /authenticate.
        """
        client = SandboxGSTClient(company=company)
        return client.get_access_token(force_refresh=True)

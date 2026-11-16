"""
Custom Exceptions for Indian GST Compliance and Sandbox API Integration.
"""
from rest_framework.exceptions import APIException
from rest_framework import status


class GSTIntegrationError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "GST Gateway Provider communication failed."
    default_code = "gst_provider_error"

    def __init__(self, detail=None, code=None, status_code=None, raw_response=None):
        if status_code:
            self.status_code = status_code
        super().__init__(detail=detail, code=code)
        self.raw_response = raw_response or {}


class GSTConfigurationMissingError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "GST Sandbox integration is not configured for this organization. API Key and Secret are required."
    default_code = "gst_unconfigured"


class GSTAuthenticationError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Failed to authenticate with Sandbox GST API. Check API credentials or session token."
    default_code = "gst_authentication_failed"


class GSTRateLimitExceededError(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Sandbox GST rate limit exceeded. Please retry after a brief pause."
    default_code = "gst_rate_limited"


class GSTINValidationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The provided GSTIN is invalid in format, state code, or checksum."
    default_code = "invalid_gstin"


class GSTRegistrationAccessDenied(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to access or perform operations on this GST registration."
    default_code = "gst_registration_forbidden"


class EInvoiceEligibilityError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invoice is not eligible for e-Invoicing (IRN generation)."
    default_code = "einvoice_ineligible"


class DuplicateSubmissionError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A submission or IRN generation has already been completed or is currently pending for this document."
    default_code = "duplicate_submission"

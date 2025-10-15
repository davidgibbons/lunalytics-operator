"""
Custom exceptions for Lunalytics API operations.
"""


class LunalyticsAPIError(Exception):
    """Base exception for Lunalytics API errors."""
    
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class LunalyticsAuthenticationError(LunalyticsAPIError):
    """Raised when authentication fails."""
    pass


class LunalyticsNotFoundError(LunalyticsAPIError):
    """Raised when a monitor is not found."""
    pass


class LunalyticsValidationError(LunalyticsAPIError):
    """Raised when request validation fails."""
    pass


class LunalyticsServerError(LunalyticsAPIError):
    """Raised when server returns 5xx error."""
    pass


class LunalyticsRateLimitError(LunalyticsAPIError):
    """Raised when rate limit is exceeded."""
    pass


class LunalyticsRetryExhaustedError(LunalyticsAPIError):
    """Raised when all retry attempts are exhausted."""
    pass

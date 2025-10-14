"""
Exception classes for HERMES acquisition services.

Defines a hierarchy of exceptions for different service error conditions,
enabling proper error handling and recovery strategies.
"""


class ServiceError(Exception):
    """Base exception for all service-related errors."""
    pass


class ConnectionError(ServiceError):
    """Raised when service cannot establish or maintain connection."""
    pass


class TimeoutError(ServiceError):
    """Raised when service operations exceed timeout limits."""
    pass


class ServiceNotAvailableError(ServiceError):
    """Raised when service is not available or not running."""
    pass


class ConfigurationError(ServiceError):
    """Raised when service configuration is invalid or cannot be applied."""
    pass


class AuthenticationError(ServiceError):
    """Raised when service authentication fails."""
    pass


# SERVAL-specific exceptions
class ServalError(ServiceError):
    """Base exception for SERVAL-related errors."""
    pass


class ServalAPIError(ServalError):
    """Raised when SERVAL API returns an error response."""
    
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class ServalProcessError(ServalError):
    """Raised when SERVAL process management fails."""
    pass


class ServalDetectorError(ServalError):
    """Raised when SERVAL detector operations fail."""
    pass


class ServalAcquisitionError(ServalError):
    """Raised when SERVAL acquisition operations fail."""
    pass


# EPICS-specific exceptions
class EPICSError(ServiceError):
    """Base exception for EPICS-related errors."""
    pass


class EPICSConnectionError(EPICSError):
    """Raised when EPICS PV connection fails."""
    pass


class EPICSReadError(EPICSError):
    """Raised when EPICS PV read operation fails."""
    pass


class EPICSWriteError(EPICSError):
    """Raised when EPICS PV write operation fails."""
    pass


class EPICSTimeoutError(EPICSError):
    """Raised when EPICS operations timeout."""
    pass


# Motion control exceptions (for future Zaber implementation)
class MotionControlError(ServiceError):
    """Base exception for motion control errors."""
    pass


class ZaberError(MotionControlError):
    """Base exception for Zaber motion controller errors."""
    pass


class ZaberConnectionError(ZaberError):
    """Raised when Zaber connection fails."""
    pass


class ZaberMotionError(ZaberError):
    """Raised when Zaber motion operations fail."""
    pass


class ZaberLimitError(ZaberError):
    """Raised when Zaber motion hits limits or constraints."""
    pass
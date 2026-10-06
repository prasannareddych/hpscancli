"""Custom exceptions for HPScanCLI."""


class ScannerException(Exception):
    """Base exception for scanner operations."""
    pass


class ScannerConnectionError(ScannerException):
    """Raised when connecting to the scanner fails or times out."""
    pass


class ScannerJobError(ScannerException):
    """Raised when scanner encounters an error during job creation or scanning."""
    pass


class ScannerDiscoveryError(ScannerException):
    """Raised when network scanning or discovery encounters an error."""
    pass


class FileExistsError(ScannerException):
    """Raised when destination file already exists and overwrite is not permitted."""
    pass


class InvalidParameterError(ScannerException):
    """Raised when requested scan parameters (e.g. DPI) are unsupported."""
    pass


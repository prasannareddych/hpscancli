"""HPScanCLI: Modern CLI tool for HP Network Scanners via eSCL."""

from hpscancli.client import HPScannerClient
from hpscancli.config import AppConfig
from hpscancli.exceptions import ScannerException
from hpscancli.models import ScannerCapabilities, ScanOptions

__version__ = "1.1.0"
__all__ = [
    "HPScannerClient",
    "AppConfig",
    "ScannerException",
    "ScannerCapabilities",
    "ScanOptions",
]

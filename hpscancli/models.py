"""Data models for HP eSCL scanner capabilities, jobs, and settings."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScannerCapabilities:
    make_and_model: str = "Unknown"
    serial_number: str = "Unknown"
    manufacturer: str = "HP"
    firmware_version: str = "Unknown"
    min_width: int = 0
    max_width: int = 2550
    min_height: int = 0
    max_height: int = 3508
    color_modes: List[str] = field(default_factory=lambda: ["RGB24", "Grayscale8"])
    document_formats: List[str] = field(default_factory=lambda: ["application/pdf", "image/jpeg", "image/png"])
    supported_resolutions: List[int] = field(default_factory=lambda: [75, 150, 200, 300, 600])
    adf_supported: bool = False


@dataclass
class ScanOptions:
    ip: str
    dpi: int = 300
    width: Optional[int] = None
    height: Optional[int] = None
    color_mode: str = "RGB24"
    format: str = "application/pdf"
    output_path: Optional[str] = None
    input_source: str = "Platen"
    overwrite: bool = False

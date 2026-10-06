"""eSCL Client implementation for HP Network Scanners."""

import datetime
import logging
import time
from pathlib import Path
from typing import Optional

import requests

from hpscancli.exceptions import (
    FileExistsError,
    InvalidParameterError,
    ScannerConnectionError,
    ScannerJobError,
)
from hpscancli.models import ScannerCapabilities, ScanOptions
from hpscancli.schema import (
    build_scan_xml,
    parse_detailed_scanner_status,
    parse_job_status,
    parse_scanner_capabilities,
)

logger = logging.getLogger(__name__)


class HPScannerClient:
    """Client for communicating with HP scanners via eSCL/AirScan protocol."""

    def __init__(self, host: str, timeout: float = 10.0, session: Optional[requests.Session] = None):
        self.host = host
        self.timeout = timeout
        self.session = session or requests.Session()
        self.base_url = f"http://{self.host}"

    def get_capabilities(self) -> ScannerCapabilities:
        """Fetch and parse scanner capabilities."""
        url = f"{self.base_url}/eSCL/ScannerCapabilities"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return parse_scanner_capabilities(response.text)
        except requests.exceptions.RequestException as e:
            raise ScannerConnectionError(f"Failed to fetch capabilities from {self.host}: {e}") from e

    def get_scanner_status(self, job_url: Optional[str] = None) -> str:
        """Query current scanner/job status."""
        try:
            url = f"{self.base_url}/eSCL/ScannerStatus"
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                return parse_detailed_scanner_status(response.text, job_url=job_url)
        except Exception:
            pass
        return "Scanning"

    def create_scan_job(self, options: ScanOptions, capabilities: Optional[ScannerCapabilities] = None) -> str:
        """Create a scan job and return the job URI/path."""
        caps = capabilities or self.get_capabilities()

        # Validate requested DPI strictly against scanner hardware capabilities
        dpi = options.dpi
        if caps.supported_resolutions and dpi not in caps.supported_resolutions:
            supported = ", ".join(str(r) for r in caps.supported_resolutions)
            raise InvalidParameterError(
                f"Requested DPI '{dpi}' is not supported by this scanner. Supported resolutions: {supported}"
            )

        # Validate / normalize options against capabilities
        width = options.width or caps.max_width
        height = options.height or caps.max_height

        colormode = options.color_mode
        if colormode not in caps.color_modes:
            colormode = caps.color_modes[0] if caps.color_modes else "RGB24"

        format_type = options.format
        if format_type not in caps.document_formats:
            # Fallback if format is not advertised in Platen capabilities
            format_type = caps.document_formats[0] if caps.document_formats else "application/pdf"

        payload = build_scan_xml(
            width=width,
            height=height,
            xdpi=dpi,
            ydpi=dpi,
            colormode=colormode,
            format_type=format_type,
            input_source=options.input_source,
        )

        url = f"{self.base_url}/eSCL/ScanJobs"
        headers = {"Content-Type": "text/xml"}
        try:
            response = self.session.post(url, data=payload, headers=headers, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise ScannerConnectionError(f"Error communicating with scanner at {self.host}: {e}") from e

        if response.status_code == 201:
            # Check standard Location header
            location = response.headers.get("Location")
            if location:
                # May be full URL or relative path
                if location.startswith("http"):
                    return location
                return f"{self.base_url}{location}" if location.startswith("/") else f"{self.base_url}/{location}"

            # Fallback to polling /eSCL/ScannerStatus
            return self._poll_for_job_location()
        elif response.status_code == 503:
            raise ScannerJobError("Scanner is busy or offline. Please wait and try again.")
        else:
            raise ScannerJobError(f"Failed to create scan job: HTTP {response.status_code} - {response.text}")

    def _poll_for_job_location(self, max_retries: int = 5, retry_interval: float = 0.5) -> str:
        """Poll /eSCL/ScannerStatus to discover active job URI if Location header was absent."""
        status_url = f"{self.base_url}/eSCL/ScannerStatus"
        for _ in range(max_retries):
            try:
                resp = self.session.get(status_url, timeout=self.timeout)
                if resp.status_code == 200:
                    job_uri = parse_job_status(resp.text)
                    if job_uri:
                        return f"{self.base_url}{job_uri}"
            except Exception:
                pass
            time.sleep(retry_interval)
        raise ScannerJobError("Scan job was accepted, but job URI could not be resolved from ScannerStatus.")

    def resolve_output_path(
        self,
        output_path: Optional[str],
        format_type: str,
        overwrite: bool = False,
    ) -> Path:
        """Determine target file path, applying appropriate extension and checking collisions."""
        ext_map = {
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }
        ext = ext_map.get(format_type, ".pdf")

        if not output_path:
            now_str = datetime.datetime.now().strftime("SCAN_%Y%m%d_%H%M%S")
            target = Path(f"{now_str}{ext}")
            # Auto-increment default timestamped filenames if needed
            counter = 1
            base = target
            while target.exists() and not overwrite:
                target = base.parent / f"{base.stem}_{counter}{base.suffix}"
                counter += 1
            return target

        p = Path(output_path)
        # Append extension if not explicitly provided
        target = p if p.suffix else Path(f"{output_path}{ext}")

        if target.exists() and not overwrite:
            raise FileExistsError(
                f"Destination file '{target}' already exists. Specify a different name or use '--overwrite'."
            )

        return target

    def download_scanned_document(
        self,
        job_url: str,
        destination: Path,
        convert_to_png: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Path:
        """Download document data from job endpoint and save to disk."""
        if not job_url.endswith("/NextDocument"):
            doc_url = f"{job_url.rstrip('/')}/NextDocument"
        else:
            doc_url = job_url

        try:
            response = self.session.get(doc_url, stream=True, timeout=30.0)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ScannerJobError(f"Failed to download scanned document from {doc_url}: {e}") from e

        # Ensure parent directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)

        downloaded_chunks = []
        total_downloaded = 0
        chunk_size = 32768

        if not convert_to_png:
            f = open(destination, "wb")
        else:
            f = None

        try:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    total_downloaded += len(chunk)
                    if f:
                        f.write(chunk)
                    else:
                        downloaded_chunks.append(chunk)

                    if progress_callback:
                        progress_callback(total_downloaded, "Transferring")
        finally:
            if f:
                f.close()

        if convert_to_png:
            if progress_callback:
                progress_callback(total_downloaded, "Converting")

            import io
            from PIL import Image

            data = b"".join(downloaded_chunks)
            try:
                img = Image.open(io.BytesIO(data))
                img.save(destination, format="PNG")
            except Exception as e:
                raise ScannerJobError(f"Failed to convert scanned image to PNG: {e}") from e

        return destination

    def scan(self, options: ScanOptions, progress_callback: Optional[callable] = None) -> Path:
        """Orchestrate entire scan lifecycle: validate path -> create job -> download document."""
        # 1. Resolve path before taking hardware lock / starting scan
        target_path = self.resolve_output_path(
            output_path=options.output_path,
            format_type=options.format,
            overwrite=options.overwrite,
        )

        caps = self.get_capabilities()

        # If PNG format is requested but not natively supported by scanner hardware:
        # Check if scanner supports native image/png; if not, request image/jpeg from hardware
        # and convert to PNG via Pillow during download.
        needs_png_conversion = False
        scan_format = options.format
        if scan_format == "image/png" and "image/png" not in caps.document_formats:
            needs_png_conversion = True
            # Prefer JPEG for scanning from hardware before converting to PNG
            if "image/jpeg" in caps.document_formats:
                scan_format = "image/jpeg"
            else:
                scan_format = caps.document_formats[0] if caps.document_formats else "image/jpeg"

        # Create temporary options with the adapted hardware scan format
        hardware_options = ScanOptions(
            ip=options.ip,
            dpi=options.dpi,
            width=options.width,
            height=options.height,
            color_mode=options.color_mode,
            format=scan_format,
            output_path=options.output_path,
            input_source=options.input_source,
            overwrite=options.overwrite,
        )

        job_url = self.create_scan_job(hardware_options, capabilities=caps)
        return self.download_scanned_document(
            job_url,
            destination=target_path,
            convert_to_png=needs_png_conversion,
            progress_callback=progress_callback,
        )

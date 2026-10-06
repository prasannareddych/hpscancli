"""eSCL XML templates and XML parsing helpers for HPScanCLI."""

import xml.etree.ElementTree as ET
from typing import List, Optional

from hpscancli.models import ScannerCapabilities

# Standard XML namespaces used across eSCL
NAMESPACES = {
    "scan": "http://schemas.hp.com/imaging/escl/2011/05/03",
    "pwg": "http://www.pwg.org/schemas/2010/12/sm",
}

SCAN_XML_TEMPLATE = """\
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
\t<pwg:Version>2.1</pwg:Version>
\t<scan:Intent>Photo</scan:Intent>
\t<pwg:ScanRegions>
\t\t<pwg:ScanRegion>
\t\t\t<pwg:Height>{height}</pwg:Height>
\t\t\t<pwg:Width>{width}</pwg:Width>
\t\t\t<pwg:XOffset>0</pwg:XOffset>
\t\t\t<pwg:YOffset>0</pwg:YOffset>
\t\t</pwg:ScanRegion>
\t</pwg:ScanRegions>
\t<pwg:InputSource>{input_source}</pwg:InputSource>
\t<scan:DocumentFormatExt>{format}</scan:DocumentFormatExt>
\t<scan:XResolution>{xdpi}</scan:XResolution>
\t<scan:YResolution>{ydpi}</scan:YResolution>
\t<scan:ColorMode>{colormode}</scan:ColorMode>
\t<scan:CompressionFactor>0</scan:CompressionFactor>
\t<scan:Brightness>1000</scan:Brightness>
\t<scan:Contrast>1000</scan:Contrast>
</scan:ScanSettings>
"""


def build_scan_xml(
    width: int,
    height: int,
    xdpi: int,
    ydpi: int,
    colormode: str,
    format_type: str,
    input_source: str = "Platen",
) -> str:
    """Generate the eSCL XML payload for a scan job."""
    return SCAN_XML_TEMPLATE.format(
        width=width,
        height=height,
        xdpi=xdpi,
        ydpi=ydpi,
        colormode=colormode,
        format=format_type,
        input_source=input_source,
    )


def _find_text(element: ET.Element, path: str, default: str = "") -> str:
    found = element.find(path, NAMESPACES)
    if found is not None and found.text:
        return found.text.strip()
    # Try finding without namespace prefix if default namespace is omitted
    tag = path.split(":")[-1]
    for child in element.iter():
        if child.tag.endswith(f"}}{tag}") or child.tag == tag:
            if child.text:
                return child.text.strip()
    return default


def parse_scanner_capabilities(xml_content: str) -> ScannerCapabilities:
    """Parse ScannerCapabilities XML response from eSCL endpoint."""
    root = ET.fromstring(xml_content)

    cap = ScannerCapabilities()
    cap.make_and_model = _find_text(root, "pwg:MakeAndModel", "Unknown")
    cap.serial_number = _find_text(root, "pwg:SerialNumber", "Unknown")
    cap.manufacturer = _find_text(root, "scan:Manufacturer", "HP")
    cap.firmware_version = _find_text(root, "pwg:Version", "Unknown")

    platen = root.find("scan:Platen", NAMESPACES)
    if platen is None:
        for child in root.iter():
            if child.tag.endswith("}Platen") or child.tag == "Platen":
                platen = child
                break

    if platen is not None:
        min_w = _find_text(platen, "scan:MinWidth")
        max_w = _find_text(platen, "scan:MaxWidth")
        min_h = _find_text(platen, "scan:MinHeight")
        max_h = _find_text(platen, "scan:MaxHeight")

        if min_w.isdigit():
            cap.min_width = int(min_w)
        if max_w.isdigit():
            cap.max_width = int(max_w)
        if min_h.isdigit():
            cap.min_height = int(min_h)
        if max_h.isdigit():
            cap.max_height = int(max_h)

        color_modes = []
        for elem in platen.iter():
            if elem.tag.endswith("}ColorMode") or elem.tag == "ColorMode":
                if elem.text:
                    color_modes.append(elem.text.strip())
        if color_modes:
            cap.color_modes = list(dict.fromkeys(color_modes))

        formats = []
        for elem in platen.iter():
            if elem.tag.endswith("}DocumentFormat") or elem.tag == "DocumentFormat":
                if elem.text:
                    formats.append(elem.text.strip())
        if formats:
            cap.document_formats = list(dict.fromkeys(formats))

        resolutions = []
        for elem in platen.iter():
            if elem.tag.endswith("}XResolution") or elem.tag == "XResolution":
                if elem.text and elem.text.strip().isdigit():
                    resolutions.append(int(elem.text.strip()))
        if resolutions:
            cap.supported_resolutions = sorted(list(set(resolutions)))

    # Check ADF
    adf = root.find("scan:Adf", NAMESPACES)
    if adf is not None:
        cap.adf_supported = True

    return cap


def parse_job_status(xml_content: str) -> Optional[str]:
    """Parse ScannerStatus XML to find any active job URI in Processing state."""
    root = ET.fromstring(xml_content)
    for job_info in root.iter():
        if job_info.tag.endswith("}JobInfo") or job_info.tag == "JobInfo":
            uri = _find_text(job_info, "pwg:JobUri")
            state = _find_text(job_info, "pwg:JobState")
            if state.lower() == "processing" and uri:
                return uri
    return None


def parse_detailed_scanner_status(xml_content: str, job_url: Optional[str] = None) -> str:
    """Extract human-readable scanner/job status from ScannerStatus XML."""
    try:
        root = ET.fromstring(xml_content)
    except Exception:
        return "Scanning"

    # Check for specific job or any active job
    for job_info in root.iter():
        if job_info.tag.endswith("}JobInfo") or job_info.tag == "JobInfo":
            uri = _find_text(job_info, "pwg:JobUri")
            if job_url and uri and not (job_url.endswith(uri) or uri in job_url):
                continue

            reasons = []
            for child in job_info.iter():
                if child.tag.endswith("}JobStateReason") or child.tag == "JobStateReason":
                    if child.text:
                        reasons.append(child.text.strip())

            if reasons:
                # E.g., 'JobScanning' -> 'Scanning', 'JobCompletedSuccessfully' -> 'Completed'
                reason = reasons[0]
                if reason.startswith("Job"):
                    reason = reason[3:]
                return reason

            state = _find_text(job_info, "pwg:JobState")
            if state:
                return state

    # Fallback to general scanner state
    state = _find_text(root, "pwg:State")
    return state or "Scanning"
"""Network scanner discovery for HP/eSCL devices.

Uses concurrent socket probing across local subnet with fallback detection.
"""

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional


def get_local_ip() -> Optional[str]:
    """Retrieve the primary local IPv4 address of this machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Connecting to a public IP doesn't actually send packets but selects the correct outbound interface
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def probe_printer_port(ip: str, timeout: float = 0.3) -> bool:
    """Check if host is listening on printer / eSCL ports (9100, 80, 8080)."""
    # Probe port 9100 (JetDirect) or port 80 (HTTP eSCL)
    for port in (9100, 80):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                if sock.connect_ex((ip, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def discover_printers(
    max_workers: int = 50,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[str]:
    """Discover available printers across the local /24 subnet using concurrent workers."""
    local_ip = get_local_ip()
    if not local_ip:
        return []

    try:
        # Determine /24 subnet
        network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        hosts = [str(ip) for ip in network.hosts() if str(ip) != local_ip]
    except ValueError:
        # Fallback manual extraction
        match = re.match(r"^(\d+\.\d+\.\d+\.)", local_ip)
        if not match:
            return []
        prefix = match.group(1)
        hosts = [f"{prefix}{i}" for i in range(1, 255) if f"{prefix}{i}" != local_ip]

    total = len(hosts)
    scanned = 0
    discovered = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(probe_printer_port, ip): ip for ip in hosts}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            scanned += 1
            if progress_callback:
                progress_callback(scanned, total)
            try:
                if future.result():
                    discovered.append(ip)
            except Exception:
                pass

    return sorted(discovered, key=lambda ip: [int(p) for p in ip.split(".") if p.isdigit()])

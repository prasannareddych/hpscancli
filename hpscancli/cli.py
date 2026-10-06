"""Command Line Interface for HPScanCLI."""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from hpscancli.client import HPScannerClient
from hpscancli.config import AppConfig, get_default_config_dir
from hpscancli.discovery import discover_printers
from hpscancli.exceptions import FileExistsError, InvalidParameterError, ScannerException
from hpscancli.models import ScanOptions

COLORMODE_CHOICES = ["color", "bw", "RGB24", "Grayscale8"]
COLORMODE_MAP = {
    "color": "RGB24",
    "rgb24": "RGB24",
    "bw": "Grayscale8",
    "grayscale8": "Grayscale8",
}


def normalize_colormode(mode: Optional[str]) -> str:
    """Normalize user-friendly color mode alias ('color', 'bw') to eSCL standard."""
    if not mode:
        return "RGB24"
    return COLORMODE_MAP.get(mode.lower(), mode)


def _add_common_scan_arguments(parser: argparse.ArgumentParser):
    """Attach shared scan configuration flags to a parser or subparser."""
    # Common flags
    parser.add_argument("-i", "--ip", help="IP address of the HP scanner")

    # Output file configuration
    file_group = parser.add_argument_group("Output File")
    file_group.add_argument(
        "-o", "--output", "--filename", "--file-name",
        dest="output",
        help="Destination filename / path (e.g. 'doc1' or 'doc1.png'). Fails if already exists unless --overwrite is set.",
    )
    file_group.add_argument(
        "-w", "--overwrite",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )

    # Format flags
    fmt_group = parser.add_argument_group("Formats")
    fmt_group.add_argument("--pdf", action="store_true", help="Save output document as PDF (default)")
    fmt_group.add_argument("--png", action="store_true", help="Save output document as PNG image")
    fmt_group.add_argument("--jpeg", "--jpg", action="store_true", help="Save output document as JPEG image")

    # Scan parameter flags
    param_group = parser.add_argument_group("Scan Parameters")
    param_group.add_argument("--height", type=int, help="Scan area height in pixels/units")
    param_group.add_argument("--width", type=int, help="Scan area width in pixels/units")
    param_group.add_argument("--dpi", type=int, help="Scan resolution in DPI (e.g. 75, 150, 300, 600)")
    param_group.add_argument(
        "--colormode",
        choices=COLORMODE_CHOICES,
        help="Scan color mode: 'color' (RGB24) or 'bw' (Grayscale8)",
    )


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hpscancli",
        description="Modern CLI tool to interact with HP scanners over the network via eSCL.",
    )

    # Global / common flags
    parser.add_argument("-i", "--ip", help="IP address of the HP scanner")
    parser.add_argument("-s", "--search", "--searchprinter", action="store_true", help="Search for available scanners on local network")
    parser.add_argument("-c", "--capabilities", action="store_true", help="Display scanner capabilities and exit")

    # Output file configuration
    file_group = parser.add_argument_group("Output File")
    file_group.add_argument(
        "-o", "--output", "--filename", "--file-name",
        dest="output",
        help="Destination filename / path (e.g. 'doc1' or 'doc1.png'). Fails if already exists unless --overwrite is set.",
    )
    file_group.add_argument(
        "-w", "--overwrite",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )

    # Format flags
    fmt_group = parser.add_argument_group("Formats")
    fmt_group.add_argument("--pdf", action="store_true", help="Save output document as PDF (default)")
    fmt_group.add_argument("--png", action="store_true", help="Save output document as PNG image")
    fmt_group.add_argument("--jpeg", "--jpg", action="store_true", help="Save output document as JPEG image")

    # Scan parameter flags
    param_group = parser.add_argument_group("Scan Parameters")
    param_group.add_argument("--height", type=int, help="Scan area height in pixels/units")
    param_group.add_argument("--width", type=int, help="Scan area width in pixels/units")
    param_group.add_argument("--dpi", type=int, help="Scan resolution in DPI (e.g. 75, 150, 300, 600)")
    param_group.add_argument(
        "--colormode",
        choices=COLORMODE_CHOICES,
        help="Scan color mode: 'color' (RGB24) or 'bw' (Grayscale8)",
    )
    param_group.add_argument("-b", "--bulk", "--bulkscan", action="store_true", help="Continuous bulk scanning mode")
    param_group.add_argument("--split", "--separate", action="store_true", help="Save bulk scan pages as separate files instead of merging into a single PDF")

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Scan a document or image")
    _add_common_scan_arguments(scan_parser)

    # Command: bulkscan
    bulk_parser = subparsers.add_parser("bulkscan", help="Continuously scan multiple sequential pages")
    _add_common_scan_arguments(bulk_parser)
    bulk_parser.add_argument("--split", "--separate", action="store_true", help="Save bulk scan pages as separate files instead of merging into a single PDF")

    # Command: config
    cfg_parser = subparsers.add_parser("config", help="Manage persistent scanner configuration")
    cfg_subparsers = cfg_parser.add_subparsers(dest="config_action", help="Config actions")

    # config show / list
    cfg_subparsers.add_parser("show", help="Display saved configuration settings")
    cfg_subparsers.add_parser("list", help="Display saved configuration settings")

    # config get <key>
    get_parser = cfg_subparsers.add_parser("get", help="Get value of a specific config key")
    get_parser.add_argument("key", help="Key name ('ip', 'dpi', 'format', 'colormode')")

    # config set <key> <value>
    set_parser = cfg_subparsers.add_parser("set", help="Set a persistent configuration value")
    set_parser.add_argument("key", help="Key name ('ip', 'dpi', 'format', 'colormode')")
    set_parser.add_argument("value", help="Value to persist")

    # config reset
    cfg_subparsers.add_parser("reset", help="Reset configuration back to defaults")

    return parser.parse_args(argv)


def handle_search():
    print("Searching for scanners on local network...")

    def progress_callback(scanned, total):
        pct = scanned / total
        bar = "=" * int(pct * 40)
        sys.stdout.write(f"\rScanning Network: [{bar:<40}] {scanned}/{total} ({pct:.0%})")
        sys.stdout.flush()

    found = discover_printers(progress_callback=progress_callback)
    print("\n")
    if not found:
        print("No scanners found on the local network.")
        return

    print(f"Found {len(found)} candidate device(s):")
    for ip in found:
        print(f"  • {ip}")
    print("\nTip: Run 'hpscancli --set-ip <ip>' to set your default scanner.")


def print_capabilities(ip: str):
    client = HPScannerClient(ip)
    print(f"Connecting to scanner at {ip}...")
    caps = client.get_capabilities()

    print("\n" + "=" * 45)
    print(" SCANNER CAPABILITIES")
    print("=" * 45)
    print(f" Make & Model      : {caps.make_and_model}")
    print(f" Manufacturer      : {caps.manufacturer}")
    print(f" Serial Number     : {caps.serial_number}")
    print(f" Firmware Version  : {caps.firmware_version}")
    print(f" ADF Supported     : {'Yes' if caps.adf_supported else 'No'}")
    print(f" Printable Area    : {caps.min_width}x{caps.min_height} min, {caps.max_width}x{caps.max_height} max")
    print(f" Color Modes       : {', '.join(caps.color_modes)} (aliases: color, bw)")
    print(f" Resolutions (DPI) : {', '.join(str(r) for r in caps.supported_resolutions)}")
    print(f" Document Formats  : {', '.join(caps.document_formats)}")
    print("=" * 45 + "\n")


def execute_scan(client: HPScannerClient, options: ScanOptions):
    fmt_display = {
        "application/pdf": "PDF",
        "image/png": "PNG",
        "image/jpeg": "JPEG",
    }.get(options.format, options.format)

    print(f"Scanner IP      : {options.ip}")
    print(f"Initiating scan : {options.dpi} DPI, {options.color_mode}, {fmt_display}")

    spin_chars = ["|", "/", "-", "\\"]
    spin_idx = 0
    start_time = time.time()
    last_update = [0.0]

    def scan_progress(bytes_received: int, stage: str):
        nonlocal spin_idx
        now = time.time()
        # Throttle progress updates to ~15fps for smooth rendering
        if now - last_update[0] < 0.06 and stage == "Transferring":
            return
        last_update[0] = now

        spin = spin_chars[spin_idx % len(spin_chars)]
        spin_idx += 1

        elapsed = max(now - start_time, 0.1)
        speed_kb = (bytes_received / 1024.0) / elapsed
        mb_rec = bytes_received / (1024.0 * 1024.0)

        # Dynamic bar visualization
        bar_len = 24
        fill_len = (int(now * 6)) % bar_len
        bar = " " * fill_len + "<=>" + " " * max(0, bar_len - fill_len - 3)
        bar = bar[:bar_len]

        if stage == "Converting":
            sys.stdout.write(f"\r[{spin}] Converting image to PNG...                           ")
        else:
            sys.stdout.write(f"\r[{spin}] Scanning [{bar}] {mb_rec:4.2f} MB ({speed_kb:5.1f} KB/s)")
        sys.stdout.flush()

    try:
        saved_file = client.scan(options, progress_callback=scan_progress)
        # Clear progress line and show final success
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()
        print(f"Scan complete! Saved to: {saved_file.resolve()}")
        return saved_file
    except Exception:
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()
        raise


def determine_format(args: argparse.Namespace, config: AppConfig) -> str:
    """Determine scan format from CLI args, falling back to config or PDF."""
    if args.png:
        return "image/png"
    if args.jpeg:
        return "image/jpeg"
    if args.pdf:
        return "application/pdf"

    cfg_fmt = config.default_format.lower()
    if cfg_fmt in ("png", "image/png"):
        return "image/png"
    if cfg_fmt in ("jpeg", "jpg", "image/jpeg"):
        return "image/jpeg"
    return "application/pdf"


def handle_config(args: argparse.Namespace, config: AppConfig) -> int:
    """Handle interactions with persistent configuration."""
    action = getattr(args, "config_action", None)
    cfg_file = get_default_config_dir() / "config.json"

    if action in (None, "show", "list"):
        print(f"Configuration file: {cfg_file}")
        print(f"  ip        : {config.ip or '(none)'}")
        print(f"  dpi       : {config.default_dpi}")
        print(f"  format    : {config.default_format}")
        print(f"  colormode : {config.default_colormode}")
        return 0

    if action == "get":
        key = args.key.lower().strip()
        key_map = {
            "ip": config.ip,
            "dpi": config.default_dpi,
            "format": config.default_format,
            "colormode": config.default_colormode,
            "color_mode": config.default_colormode,
        }
        if key in key_map:
            val = key_map[key]
            print(val if val is not None else "(none)")
            return 0
        print(f"Error: Unknown configuration key '{args.key}'. Valid keys: ip, dpi, format, colormode", file=sys.stderr)
        return 1

    if action == "set":
        key = args.key.lower().strip()
        val = args.value.strip()

        if key == "ip":
            config.ip = val
        elif key in ("dpi", "default_dpi"):
            if not val.isdigit() or int(val) <= 0:
                print(f"Error: DPI must be a positive integer, got '{val}'.", file=sys.stderr)
                return 1
            config.default_dpi = int(val)
        elif key in ("format", "default_format"):
            fmt = val.lower()
            if fmt in ("pdf", "application/pdf"):
                config.default_format = "pdf"
            elif fmt in ("png", "image/png"):
                config.default_format = "png"
            elif fmt in ("jpeg", "jpg", "image/jpeg"):
                config.default_format = "jpeg"
            else:
                print(f"Error: Unsupported format '{val}'. Valid options: pdf, png, jpeg", file=sys.stderr)
                return 1
        elif key in ("colormode", "color_mode", "default_colormode"):
            mode = normalize_colormode(val)
            config.default_colormode = mode
        else:
            print(f"Error: Unknown configuration key '{args.key}'. Valid keys: ip, dpi, format, colormode", file=sys.stderr)
            return 1

        path = config.save()
        print(f"Saved '{key}' = '{val}' to {path}")
        return 0

    if action == "reset":
        reset_cfg = AppConfig()
        path = reset_cfg.save()
        print(f"Configuration reset to defaults at {path}")
        return 0

    return 0


def main(argv=None):
    args = parse_args(argv)
    config = AppConfig.load()

    # Route config subcommand
    if getattr(args, "command", None) == "config":
        return handle_config(args, config)

    if getattr(args, "search", False):
        handle_search()
        return 0

    # Determine IP: flag takes precedence over persisted config
    target_ip = args.ip or config.ip
    if not target_ip:
        print("Error: Scanner IP address is required.", file=sys.stderr)
        print("Provide via '-i <ip>' or configure default via 'hpscancli config set ip <ip>'", file=sys.stderr)
        return 1

    try:
        if getattr(args, "capabilities", False):
            print_capabilities(target_ip)
            return 0

        # Build scan options
        dpi = args.dpi or config.default_dpi
        raw_colormode = args.colormode or config.default_colormode
        colormode = normalize_colormode(raw_colormode)
        fmt = determine_format(args, config)

        client = HPScannerClient(target_ip)
        scan_opts = ScanOptions(
            ip=target_ip,
            dpi=dpi,
            width=args.width,
            height=args.height,
            color_mode=colormode,
            format=fmt,
            output_path=args.output,
            overwrite=args.overwrite,
        )

        is_bulk = (args.command == "bulkscan") or getattr(args, "bulk", False)
        split_pages = getattr(args, "split", False)

        if not is_bulk:
            execute_scan(client, scan_opts)
            return 0

        # Bulk scanning mode
        is_pdf = (fmt == "application/pdf")
        merge_pdf = is_pdf and not split_pages

        # In merge mode, track all scanned page files
        scanned_pages = []

        import tempfile
        temp_dir = tempfile.TemporaryDirectory() if merge_pdf else None

        try:
            # First page
            if merge_pdf:
                # Target final output path
                final_output_path = client.resolve_output_path(
                    output_path=args.output,
                    format_type=fmt,
                    overwrite=args.overwrite,
                )
                page_1_target = Path(temp_dir.name) / "page_1.pdf"
                scan_opts.output_path = str(page_1_target)
                scan_opts.overwrite = True
                saved_first = execute_scan(client, scan_opts)
                scanned_pages.append(saved_first)
            else:
                saved_first = execute_scan(client, scan_opts)
                scanned_pages.append(saved_first)

            page_index = 2
            base_output = args.output

            while True:
                choice = input("\nContinue scan next page? [Y/n]: ").strip().lower()
                if choice in ("n", "no", "q"):
                    print("Bulk scan finished.")
                    break
                elif choice in ("", "y", "yes"):
                    if merge_pdf:
                        next_page_target = Path(temp_dir.name) / f"page_{page_index}.pdf"
                        scan_opts.output_path = str(next_page_target)
                        scan_opts.overwrite = True
                    elif base_output:
                        p = Path(base_output)
                        scan_opts.output_path = str(p.parent / f"{p.stem}_{page_index}{p.suffix}")
                    else:
                        scan_opts.output_path = None

                    page_index += 1
                    saved_page = execute_scan(client, scan_opts)
                    scanned_pages.append(saved_page)
                else:
                    print("Please enter 'y' or 'n'.")

            # Merge all PDF pages if in merge mode
            if merge_pdf and scanned_pages:
                import pypdf
                merger = pypdf.PdfWriter()
                for p in scanned_pages:
                    merger.append(str(p))

                with open(final_output_path, "wb") as f_out:
                    merger.write(f_out)

                print(f"\nSuccessfully merged {len(scanned_pages)} pages into: {final_output_path.resolve()}")

        finally:
            if temp_dir:
                temp_dir.cleanup()

        return 0

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130
    except (FileExistsError, InvalidParameterError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except ScannerException as e:
        print(f"\nScanner Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

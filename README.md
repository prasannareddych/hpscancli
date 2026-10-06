# HPScanCLI

A modern, fast CLI tool for interacting with HP network scanners via standard eSCL (Apple AirScan) web protocol.

## Features

- **Device Discovery**: Fast concurrent scanning across the local network to find active eSCL-compatible scanners.
- **Config Persistence**: Save your default scanner IP and scan preferences (`~/.config/hpscancli/config.json`) so you don't need to specify `--ip` every time.
- **Detailed Capabilities**: Inspect supported color modes, resolutions (DPI), document formats, and ADF support.
- **Multi-Format Scanning**: Scan directly to **PDF**, **PNG**, or **JPEG** with configurable dimensions, resolution, and color modes.
- **File Safety**: Pre-flight checks prevent accidental file overwrites (override with `-w` / `--overwrite`).
- **Bulk Scanning**: Continuously scan sequential pages (`doc_1`, `doc_2`, ...) without re-invoking the command.
- **Zero Heavy XML Dependencies**: Uses Python's built-in `xml.etree.ElementTree` instead of `bs4`.
- **Modern Standards**: Built with PEP 621 (`pyproject.toml`) and managed via `pipx`.

---

## Installation

Install globally in an isolated environment using [`pipx`](https://pypa.github.io/pipx/):

```bash
pipx install git+https://github.com/prasannareddych/hpscancli.git
```

Or install from a local clone:

```bash
git clone https://github.com/prasannareddych/hpscancli.git
cd hpscancli
pipx install .
```

---

## Configuration

You can persist your default scanner IP and scan preferences (`~/.config/hpscancli/config.json`) so you don't need to specify them every time:

```bash
# View all current settings
hpscancli config show

# Set scanner IP
hpscancli config set ip 192.168.0.105

# Set default scan resolution, format, and color mode
hpscancli config set dpi 300
hpscancli config set format pdf         # pdf, png, jpeg
hpscancli config set colormode color    # color, bw

# Read a specific key
hpscancli config get ip

# Reset settings to defaults
hpscancli config reset
```

---

## Usage

```bash
hpscancli [command] [options]
```

### Commands

| Command | Description |
| :--- | :--- |
| `scan` | Execute a single scan job |
| `bulkscan` | Continuously scan multiple pages interactively |
| `config` | Manage persistent scanner configuration (`show`, `get`, `set`, `reset`) |

### Options

| Flag / Option | Description |
| :--- | :--- |
| `-i, --ip <IP>` | Target scanner IP (overrides persisted config) |
| `-s, --search` | Search for candidate scanners on the local subnet |
| `-c, --capabilities` | Show scanner hardware capabilities and exit |
| `-o, --output, --filename <PATH>` | Output file name / path (e.g. `doc1` or `doc1.png`) |
| `-w, --overwrite` | Overwrite destination file if it already exists |
| `--pdf` | Save scan as PDF document (default) |
| `--png` | Save scan as PNG image (converts with Pillow if device lacks native PNG) |
| `--jpeg` / `--jpg` | Save scan as JPEG image |
| `--dpi <DPI>` | Scan resolution (e.g., `75`, `150`, `300`, `600`). Fails if unsupported. |
| `--colormode <MODE>` | `color` (RGB24) or `bw` (Grayscale8) |
| `--width <WIDTH>` | Custom scan width in pixels/units |
| `--height <HEIGHT>` | Custom scan height in pixels/units |
| `-b, --bulk` | Enable interactive bulk/continuous scanning |
| `--split` | Save bulk scan pages as separate files instead of merging into a single PDF |

---

## Examples

1. **Discover scanners on the network:**
   ```bash
   hpscancli -s
   ```

2. **Save scanner IP and preferences:**
   ```bash
   hpscancli config set ip 192.168.0.105
   hpscancli config set dpi 300
   ```

3. **Check scanner capabilities:**
   ```bash
   hpscancli -c
   ```

4. **Scan to PDF (default settings):**
   ```bash
   hpscancli scan -o invoice
   ```

5. **Scan to PNG (safe overwrite protection):**
   ```bash
   hpscancli scan --png -o photo
   # If photo.png already exists, it errors safely.
   # To force overwrite:
   hpscancli scan --png -o photo --overwrite
   ```

6. **Scan high-res color photo to JPEG:**
   ```bash
   hpscancli scan --dpi 600 --colormode color --jpeg -o portrait
   ```

7. **Continuous multi-page bulk scan (merged into a single PDF):**
   ```bash
   hpscancli bulkscan -o contract
   # Prompts after each page and merges all pages into contract.pdf
   ```

8. **Bulk scan saved as separate individual files:**
   ```bash
   hpscancli bulkscan -o contract --split
   # Saves contract.pdf, contract_2.pdf, contract_3.pdf...
   ```

---

## Architecture & Codebase

- [`hpscancli/config.py`](file:///home/ubuntu/other-projects/HPScanCLI/hpscancli/config.py): Persistent JSON configuration manager.
- [`hpscancli/client.py`](file:///home/ubuntu/other-projects/HPScanCLI/hpscancli/client.py): eSCL client handling scan jobs, status polling, and stream downloads.
- [`hpscancli/discovery.py`](file:///home/ubuntu/other-projects/HPScanCLI/hpscancli/discovery.py): Concurrent network device discovery.
- [`hpscancli/schema.py`](file:///home/ubuntu/other-projects/HPScanCLI/hpscancli/schema.py): Standard library ElementTree XML parser and eSCL payload generator.
- [`hpscancli/models.py`](file:///home/ubuntu/other-projects/HPScanCLI/hpscancli/models.py): Clean dataclasses for capabilities and scan options.
- [`hpscancli/cli.py`](file:///home/ubuntu/other-projects/HPScanCLI/hpscancli/cli.py): Modern command line interface.
- [`tests/test_scanner.py`](file:///home/ubuntu/other-projects/HPScanCLI/tests/test_scanner.py): Pytest unit test suite.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

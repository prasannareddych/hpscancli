"""Backward-compatible entry point for HPScanCLI."""

import sys
from hpscancli.cli import main

if __name__ == "__main__":
    sys.exit(main())
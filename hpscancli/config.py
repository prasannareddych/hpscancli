"""Configuration management for HPScanCLI.

Handles loading, storing, and persisting scanner settings (IP, DPI, output format, etc.).
Default path follows XDG Base Directory Specification: ~/.config/hpscancli/config.json
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


def get_default_config_dir() -> Path:
    """Return platform-standard configuration directory."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        base_dir = Path(xdg_config_home)
    else:
        base_dir = Path.home() / ".config"
    return base_dir / "hpscancli"


@dataclass
class AppConfig:
    ip: Optional[str] = None
    default_dpi: int = 300
    default_format: str = "pdf"
    default_colormode: str = "RGB24"

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppConfig":
        path = config_path or (get_default_config_dir() / "config.json")
        if not path.is_file():
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return cls(
                        ip=data.get("ip"),
                        default_dpi=int(data.get("default_dpi", 300)),
                        default_format=str(data.get("default_format", "pdf")),
                        default_colormode=str(data.get("default_colormode", "RGB24")),
                    )
        except Exception:
            # Fallback gracefully if config is corrupted or unreadable
            pass
        return cls()

    def save(self, config_path: Optional[Path] = None) -> Path:
        path = config_path or (get_default_config_dir() / "config.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        return path

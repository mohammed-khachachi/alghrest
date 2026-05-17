"""Compatibility exports for legacy utility imports."""

import sys
from pathlib import Path

from src.core.dependencies import check_dependencies
from src.core.logging import log, section
from src.core.paths import get_output_path as _get_output_path
from src.reporting.exporter import save_dataframe, save_json, save_metrics


__all__ = [
    "get_output_path",
    "save_dataframe",
    "save_metrics",
    "save_json",
    "log",
    "section",
    "check_dependencies",
]


def get_output_path(subdir: str, filename: str) -> Path:
    """Return absolute path inside outputs/<subdir>/."""
    return _get_output_path(subdir, filename)


if __name__ == "__main__":
    section("Dependency Check")
    all_ok = check_dependencies()
    if all_ok:
        print("\nAll dependencies satisfied.")
    else:
        print("\nSome dependencies are missing. Run: pip install -r requirements.txt")
        sys.exit(1)

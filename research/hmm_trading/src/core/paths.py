"""Project path helpers."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

CONFIGS_DIR = PROJECT_ROOT / "configs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
RESULTS_DIR = OUTPUTS_DIR / "results"
THEORY_DIR = OUTPUTS_DIR / "theory"
REFERENCES_DIR = PROJECT_ROOT / "references"


def ensure_dir(path: Path) -> Path:
    """Create a directory if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_output_path(subdir: str, filename: str = "") -> Path:
    """Return a path inside outputs, creating the requested subdirectory."""
    output_dir = ensure_dir(OUTPUTS_DIR / subdir)
    if filename:
        return output_dir / filename
    return output_dir

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"


def get_output_path(subdir: str, filename: str = "") -> Path:
    path = PROJECT_ROOT / "outputs" / subdir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path(name: str = "default.json") -> Path:
    return PROJECT_ROOT / "configs" / name


def get_references_path() -> Path:
    return PROJECT_ROOT / "references"

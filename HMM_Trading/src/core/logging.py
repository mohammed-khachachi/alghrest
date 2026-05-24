"""Console logging helpers."""

from datetime import datetime


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def section(title: str) -> None:
    """Print a formatted section header."""
    line = "=" * 60
    print(f"\n{line}")
    print(f"  {title}")
    print(f"{line}")

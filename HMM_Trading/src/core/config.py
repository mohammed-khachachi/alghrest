import json
from pathlib import Path

from src.core.paths import get_config_path


def load_config(path: Path | str | None = None) -> dict:
    if path is None:
        path = get_config_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_config(config: dict) -> bool:
    required = ["ticker", "start", "end", "n_states", "feature_cols", "random_state"]
    missing = [k for k in required if k not in config]
    if missing:
        raise ValueError(f"Config missing keys: {missing}")
    return True

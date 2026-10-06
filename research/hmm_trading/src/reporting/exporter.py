"""Output export helpers."""

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from src.core.paths import get_output_path


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def save_dataframe(df: pd.DataFrame, subdir: str, filename: str) -> Path:
    """Save a DataFrame as CSV to outputs/<subdir>/<filename>."""
    path = get_output_path(subdir, filename)
    df.to_csv(path)
    print(f"[SAVE] {path}")
    return path


def save_metrics(metrics: Dict[str, Any], filename: str = "backtest_metrics.csv") -> Path:
    """Save metrics dictionary as a two-column CSV."""
    path = get_output_path("results", filename)
    rows = [{"metric": k, "value": v} for k, v in metrics.items()]
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"[SAVE] {path}")
    return path


def save_json(data: Dict, filename: str) -> Path:
    """Save a dictionary as JSON."""
    path = get_output_path("results", filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, cls=_Encoder, ensure_ascii=False)
    print(f"[SAVE] {path}")
    return path

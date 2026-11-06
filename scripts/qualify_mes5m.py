"""Pinned local MES development preflight. No strategy, fill or account runner."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from backtesting.mes5m_data import preflight_development
from backtesting.mes5m_spec import ResearchSpec, Safety, canonical_json
from scripts.advisory_firstrate_intake import _normalize

ROOT = Path(__file__).resolve().parents[1]
SPECIFICATION = ROOT / "research/mes5m/mes5m-h26-v1.json"
SOURCE = ROOT / "data/private/firstrate/2026-10-09-free-samples/MES_H26_1min.csv"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        super().error("Invalid arguments; only DEVELOPMENT preflight is available")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate specification key")
        result[key] = value
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--partition", choices=("development",), default="development")
    parser.parse_args(argv)  # Deny requests before any source/configuration access.
    try:
        if any(
            p.is_symlink()
            for path in (SPECIFICATION, SOURCE)
            for p in (path, *path.parents)
            if p != ROOT.parent
        ):
            raise PermissionError("Pinned inputs cannot be redirected")
        spec = ResearchSpec.model_validate(
            json.loads(SPECIFICATION.read_bytes(), object_pairs_hook=_unique)
        )
        result = preflight_development(
            SOURCE.read_bytes(),
            expected_sha256=spec.source_csv_sha256,
            normalizer=_normalize,
            origin="real_provider_sample",
            spec=spec,
        )
    except (ValueError, OSError):
        # Never echo supplied paths, source rows, credentials or exception contents.
        print(
            canonical_json(
                {
                    **Safety().model_dump(mode="json"),
                    "status": "BLOCKED",
                    "reason": "preflight_rejected",
                }
            ),
            file=sys.stderr,
        )
        return 2
    print(canonical_json(result))
    return 0  # Structural preflight completed; data/firm status remains PARTIAL/BLOCKED.


if __name__ == "__main__":
    raise SystemExit(main())

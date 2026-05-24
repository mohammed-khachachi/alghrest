"""
file_finder.py
==============
Responsible for locating the Stanford Hidden Markov Models PDF
throughout the repository, ignoring virtual environments and build artifacts.

Based on the theoretical framework of Stanford HMM materials (CS229 / CS228).
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple


# Keywords that indicate this is the Stanford HMM reference file
PRIORITY_KEYWORDS = [
    "stanford", "hidden", "markov", "hmm", "cs228", "cs229", "cs221"
]

# Directories to always skip during search
SKIP_DIRS = {
    ".venv", "venv", "env", ".env",
    "node_modules", ".git", "__pycache__",
    "outputs", "dist", "build", ".tox",
    ".mypy_cache", ".pytest_cache"
}


def find_repo_root(start_path: Optional[Path] = None) -> Path:
    """
    Walk upward from start_path until we find a git root, pyproject.toml,
    or setup.py — or simply return the top-most reachable parent.
    """
    if start_path is None:
        start_path = Path(__file__).resolve().parent

    current = start_path
    for _ in range(10):  # max depth
        if (current / ".git").exists():
            return current
        if (current / "pyproject.toml").exists():
            return current
        if (current / "setup.py").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start_path


def _should_skip(path: Path) -> bool:
    """Return True if this path (or any ancestor) should be excluded."""
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False


def _score_pdf(pdf_path: Path) -> int:
    """
    Score a PDF by how likely it is to be the Stanford HMM reference.
    Higher score = better candidate.
    """
    name_lower = pdf_path.name.lower()
    score = 0
    for kw in PRIORITY_KEYWORDS:
        if kw in name_lower:
            score += 10
    # Penalise files that look like our own generated report
    if "trading_report" in name_lower or "backtest" in name_lower:
        score -= 50
    # Bonus if it sits inside a 'references' folder
    if "references" in str(pdf_path).lower():
        score += 5
    return score


def find_all_pdfs(root: Path) -> List[Tuple[Path, int]]:
    """
    Recursively find every PDF under *root*, excluding SKIP_DIRS.
    Returns list of (path, score) tuples, sorted by score descending.
    """
    results: List[Tuple[Path, int]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories we should skip (modifies dirnames in place)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for fname in filenames:
            if not fname.lower().endswith(".pdf"):
                continue
            full_path = Path(dirpath) / fname
            if _should_skip(full_path):
                continue
            score = _score_pdf(full_path)
            results.append((full_path, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def find_stanford_hmm_pdf(root: Optional[Path] = None) -> Optional[Path]:
    """
    Main entry point: return the best-matching Stanford HMM PDF, or None.
    """
    if root is None:
        root = find_repo_root()

    all_pdfs = find_all_pdfs(root)

    if not all_pdfs:
        return None

    best_path, best_score = all_pdfs[0]

    # Only accept if the score is positive (at least one keyword matched)
    if best_score > 0:
        return best_path

    return None


def print_search_report(root: Optional[Path] = None) -> Optional[Path]:
    """
    Print a human-readable discovery report and return the best PDF path.
    """
    if root is None:
        root = find_repo_root()

    print("=" * 60)
    print("  HMM PDF FILE FINDER")
    print("  Stanford Hidden Markov Models Reference Locator")
    print("=" * 60)
    print(f"\n[ROOT] Searching from: {root}\n")

    all_pdfs = find_all_pdfs(root)

    if not all_pdfs:
        print("[INFO] No PDF files found in the repository.")
        print("[INFO] The Stanford HMM PDF was not uploaded to the project.")
        print("[INFO] The project will use embedded theoretical knowledge")
        print("       based on Stanford CS229 / CS228 HMM lecture notes.")
        print("       Reference: https://cs229.stanford.edu/section/cs229-hmm.pdf")
        print("=" * 60)
        return None

    print(f"[INFO] Found {len(all_pdfs)} PDF file(s):\n")
    for i, (path, score) in enumerate(all_pdfs, 1):
        marker = " <-- BEST CANDIDATE" if i == 1 and score > 0 else ""
        print(f"  [{i}] Score={score:+d}  {path.name}")
        print(f"       Path: {path}{marker}\n")

    best_path, best_score = all_pdfs[0]

    if best_score > 0:
        print(f"[SELECTED] {best_path.name}")
        print(f"[PATH]     {best_path}")
        print("\nThis file will be used as the theoretical source for HMM concepts.")
    else:
        print("[INFO] No PDF matched the Stanford HMM keywords.")
        print("[INFO] Proceeding with embedded theoretical knowledge.")
        best_path = None

    print("=" * 60)
    return best_path if best_score > 0 else None


__all__ = ["find_stanford_hmm_pdf", "print_search_report", "find_repo_root"]


if __name__ == "__main__":
    found = print_search_report()
    if found:
        print(f"\n[OK] Stanford HMM PDF located at:\n     {found}")
        sys.exit(0)
    else:
        print("\n[OK] No PDF found — project uses built-in Stanford HMM knowledge.")
        sys.exit(0)

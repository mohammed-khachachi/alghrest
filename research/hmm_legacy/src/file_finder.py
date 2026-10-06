"""Find local Stanford/HMM reference files for the research project.

The search is intentionally conservative: generated project files are skipped so
the report and notebook created by this project do not get mistaken for an
external Stanford source. This module never changes the report; it only reports
whether a Stanford Hidden Markov Models PDF is available in the
project/references/ folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


KEYWORDS = [
    "stanford",
    "hidden markov models",
    "hidden markov model",
    "hidden markov",
    "hmm",
    "markov",
    "cs228",
    "cs229",
    "cs221",
    "lecture",
    "notes",
    "slides",
]

SEARCH_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".doc",
    ".docx",
    ".md",
    ".txt",
    ".ipynb",
}

NO_STANFORD_PDF_MESSAGE = (
    "No Stanford Hidden Markov Models PDF was found. "
    "The project will continue using standard HMM theory."
)

TEXT_EXTENSIONS = {".md", ".txt", ".ipynb"}
SKIP_DIRECTORIES = {
    "outputs",
    "__pycache__",
    ".git",
    ".ipynb_checkpoints",
    ".venv",
    "venv",
    "venv-lite",
    "node_modules",
}
SKIP_GENERATED_FILES = {
    "HMM_Trading_Report.md",
    "README.md",
    "requirements.txt",
    "hmm_market_regime_detection.ipynb",
}

REFERENCE_DIR_NAME = "references"


@dataclass(frozen=True)
class SearchResult:
    path: Path
    score: int
    matched_keywords: tuple[str, ...]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", text.casefold())).strip()


def _is_skipped(path: Path) -> bool:
    if path.name in SKIP_GENERATED_FILES:
        return True
    return any(part in SKIP_DIRECTORIES for part in path.parts)


def _score_text(text: str) -> tuple[int, tuple[str, ...]]:
    normalised = _normalise(text)
    matches: list[str] = []
    score = 0
    for keyword in KEYWORDS:
        if keyword in normalised:
            matches.append(keyword)
            score += 10 if keyword == "stanford" else 5
    if "stanford" in matches and (
        "hmm" in matches or "hidden markov" in matches or "hidden markov models" in matches
    ):
        score += 30
    if "hidden markov models" in matches:
        score += 15
    return score, tuple(matches)


def _read_text(path: Path, max_chars: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError:
        return ""


def iter_candidate_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SEARCH_EXTENSIONS:
            continue
        if _is_skipped(path.relative_to(root)):
            continue
        yield path


def resolve_search_root(root: str | Path = ".") -> Path:
    """Use project/references/ as the official optional reference location."""

    root_path = Path(root).resolve()
    reference_root = root_path / REFERENCE_DIR_NAME
    if reference_root.is_dir():
        return reference_root
    return root_path


def find_hmm_files(root: str | Path = ".") -> list[SearchResult]:
    """Return ranked files that look related to Stanford/HMM."""

    root_path = resolve_search_root(root)
    results: list[SearchResult] = []
    for path in iter_candidate_files(root_path):
        name_score, name_matches = _score_text(path.name)
        content_score = 0
        content_matches: tuple[str, ...] = ()
        if path.suffix.lower() in TEXT_EXTENSIONS:
            content_score, content_matches = _score_text(_read_text(path))

        score = name_score * 3 + content_score
        matched = tuple(dict.fromkeys((*name_matches, *content_matches)))
        if score > 0:
            results.append(SearchResult(path=path, score=score, matched_keywords=matched))

    return sorted(results, key=lambda item: item.score, reverse=True)


def best_candidate(root: str | Path = ".") -> SearchResult | None:
    results = find_hmm_files(root)
    if not results:
        return None
    return results[0]


def is_stanford_hmm_pdf(result: SearchResult) -> bool:
    """Return True only for a PDF whose name indicates a Stanford HMM source."""

    keywords = set(result.matched_keywords)
    has_hmm_keyword = bool(
        {"hmm", "hidden markov", "hidden markov models", "hidden markov model"} & keywords
    )
    return result.path.suffix.lower() == ".pdf" and "stanford" in keywords and has_hmm_keyword


def find_stanford_hmm_pdfs(root: str | Path = ".") -> list[SearchResult]:
    """Return ranked Stanford Hidden Markov Models PDF candidates, if present."""

    return [result for result in find_hmm_files(root) if is_stanford_hmm_pdf(result)]


def best_stanford_hmm_pdf(root: str | Path = ".") -> SearchResult | None:
    """Return the strongest optional Stanford HMM PDF candidate, if present."""

    results = find_stanford_hmm_pdfs(root)
    if not results:
        return None
    return results[0]


def print_results(results: list[SearchResult]) -> None:
    if not results:
        print(NO_STANFORD_PDF_MESSAGE)
        return

    print("Ranked optional Stanford/HMM candidate files:")
    for result in results:
        keywords = ", ".join(result.matched_keywords)
        print(f"- score={result.score:03d} | {result.path} | keywords: {keywords}")


if __name__ == "__main__":
    search_root = Path(__file__).resolve().parents[1]
    ranked = find_hmm_files(search_root)
    print_results(ranked)
    selected_pdf = best_stanford_hmm_pdf(search_root)
    if selected_pdf:
        print(f"\nOptional Stanford Hidden Markov Models PDF found: {selected_pdf.path}")
    elif ranked:
        print(f"\n{NO_STANFORD_PDF_MESSAGE}")

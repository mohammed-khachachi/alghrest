"""
pdf_reader.py
=============
Responsible for extracting text from the Stanford HMM PDF reference file.

Attempts extraction using pypdf first, then pymupdf (fitz) as fallback.
If neither library is available, it prints clear instructions and continues.

Output is saved to: outputs/theory/stanford_hmm_extracted.txt
"""

import sys
from pathlib import Path
from typing import Optional

from src.core.paths import get_output_path


__all__ = [
    "OUTPUT_FILE",
    "extract_text_pypdf",
    "extract_text_pymupdf",
    "save_extracted_text",
    "extract_pdf_text",
]


OUTPUT_FILE = get_output_path("theory", "stanford_hmm_extracted.txt")


def _load_embedded_summary() -> str:
    path = get_output_path("theory", "embedded_hmm_theory.txt")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Stanford HMM embedded theory not found."


def extract_text_pypdf(pdf_path: Path) -> Optional[str]:
    """Try extracting text using the pypdf library."""
    try:
        import pypdf  # noqa: PLC0415
        reader = pypdf.PdfReader(str(pdf_path))
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages_text.append(f"--- Page {i+1} ---\n{text}")
        full_text = "\n\n".join(pages_text)
        if full_text.strip():
            return full_text
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"[WARNING] pypdf extraction failed: {e}")
        return None


def extract_text_pymupdf(pdf_path: Path) -> Optional[str]:
    """Try extracting text using PyMuPDF (fitz)."""
    try:
        import fitz  # noqa: PLC0415  (PyMuPDF)
        doc = fitz.open(str(pdf_path))
        pages_text = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages_text.append(f"--- Page {i+1} ---\n{text}")
        full_text = "\n\n".join(pages_text)
        if full_text.strip():
            return full_text
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"[WARNING] PyMuPDF extraction failed: {e}")
        return None


def save_extracted_text(text: str, output_path: Path = OUTPUT_FILE) -> None:
    """Save extracted text to the output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[SAVED] Extracted text saved to: {output_path}")


def extract_pdf_text(pdf_path: Optional[Path]) -> str:
    """
    Main entry point.
    If pdf_path is None or extraction fails, return the embedded summary.
    """
    if pdf_path is None:
        print("[INFO] No Stanford HMM PDF provided. Using embedded theoretical summary.")
        embedded_summary = _load_embedded_summary()
        save_extracted_text(embedded_summary)
        return embedded_summary

    print(f"[INFO] Attempting text extraction from: {pdf_path.name}")

    # Try pypdf first
    text = extract_text_pypdf(pdf_path)
    if text:
        print(f"[OK]   Text extracted with pypdf ({len(text):,} characters)")
        header = f"Source: {pdf_path}\nExtracted with: pypdf\n{'='*60}\n\n"
        full_text = header + text
        save_extracted_text(full_text)
        return full_text

    # Try PyMuPDF
    text = extract_text_pymupdf(pdf_path)
    if text:
        print(f"[OK]   Text extracted with PyMuPDF ({len(text):,} characters)")
        header = f"Source: {pdf_path}\nExtracted with: PyMuPDF (fitz)\n{'='*60}\n\n"
        full_text = header + text
        save_extracted_text(full_text)
        return full_text

    # Both failed
    print("[WARNING] PDF text extraction failed (possibly a scanned/image PDF).")
    print("[INFO]    Install pypdf:  pip install pypdf")
    print("[INFO]    Install fitz:   pip install pymupdf")
    print("[INFO]    Falling back to embedded Stanford HMM theoretical summary.")
    embedded_summary = _load_embedded_summary()
    save_extracted_text(embedded_summary)
    return embedded_summary


if __name__ == "__main__":
    from src.references.finder import find_stanford_hmm_pdf, find_repo_root
    root = find_repo_root()
    pdf = find_stanford_hmm_pdf(root)
    text = extract_pdf_text(pdf)
    print(f"\n[PREVIEW] First 500 characters:\n{text[:500]}")

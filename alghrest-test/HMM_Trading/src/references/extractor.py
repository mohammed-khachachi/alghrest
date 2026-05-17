"""
pdf_reader.py
=============
Responsible for extracting text from the Stanford HMM PDF reference file.

Attempts extraction using pypdf first, then pymupdf (fitz) as fallback.
If neither library is available, it prints clear instructions and continues.

Output is saved to: outputs/extracted_text/stanford_hmm_extracted.txt
"""

import os
import sys
from pathlib import Path
from typing import Optional

from src.core.paths import OUTPUTS_DIR


__all__ = [
    "OUTPUT_FILE",
    "EMBEDDED_STANFORD_SUMMARY",
    "extract_text_pypdf",
    "extract_text_pymupdf",
    "save_extracted_text",
    "extract_pdf_text",
]


OUTPUT_FILE = OUTPUTS_DIR / "extracted_text" / "stanford_hmm_extracted.txt"

# Embedded theoretical summary used when no PDF is available
EMBEDDED_STANFORD_SUMMARY = """
================================================================================
  STANFORD HIDDEN MARKOV MODELS — THEORETICAL SUMMARY
  Source: Stanford CS229 / CS228 Lecture Notes on HMM
  (Embedded knowledge — PDF not found in project directory)
================================================================================

1. DEFINITION
-------------
A Hidden Markov Model (HMM) is a statistical model for sequential data where
the system is assumed to be a Markov process with unobserved (hidden) states.

Formally, an HMM is defined by the 5-tuple (S, O, π, A, B):
  - S = {s_1, ..., s_N}  : finite set of hidden states
  - O = {o_1, ..., o_M}  : finite set of possible observations (or continuous)
  - π_i = P(q_1 = s_i)   : initial state distribution
  - A_{ij} = P(q_{t+1} = s_j | q_t = s_i)  : state transition probabilities
  - B_i(o_t) = P(o_t | q_t = s_i)          : emission probabilities

2. MARKOV ASSUMPTION
--------------------
P(q_t | q_{t-1}, q_{t-2}, ..., q_1) = P(q_t | q_{t-1})
The future state depends only on the current state, not on history.

3. THREE FUNDAMENTAL PROBLEMS (Rabiner, 1989)
---------------------------------------------
Problem 1 — EVALUATION (Forward Algorithm):
  Given model λ=(A,B,π) and observation sequence O, compute P(O|λ).
  Uses dynamic programming: α_t(i) = P(o_1,...,o_t, q_t=s_i | λ)
  Forward variable: α_t(i) = [Σ_j α_{t-1}(j) · A_{ji}] · B_i(o_t)

Problem 2 — DECODING (Viterbi Algorithm):
  Find the most likely state sequence Q* = argmax_Q P(Q|O,λ).
  Dynamic programming: δ_t(i) = max_{q_1,...,q_{t-1}} P(q_1,...,q_t=s_i, o_1,...,o_t | λ)
  Recurrence: δ_t(j) = [max_i δ_{t-1}(i) · A_{ij}] · B_j(o_t)

Problem 3 — LEARNING (Baum-Welch / EM Algorithm):
  Find model parameters λ=(A,B,π) that maximize P(O|λ).
  Uses Expectation-Maximization:
    E-step: compute forward (α) and backward (β) variables
    M-step: update A, B, π using γ_t(i) and ξ_t(i,j)
  γ_t(i)   = P(q_t = s_i | O, λ)
  ξ_t(i,j) = P(q_t=s_i, q_{t+1}=s_j | O, λ)

4. BACKWARD ALGORITHM
---------------------
  β_t(i) = P(o_{t+1}, ..., o_T | q_t = s_i, λ)
  β_T(i) = 1  (initialization)
  β_t(i) = Σ_j A_{ij} · B_j(o_{t+1}) · β_{t+1}(j)

5. GAUSSIAN HMM
---------------
  For continuous observations, B_i(o_t) = N(o_t; μ_i, Σ_i)
  where μ_i is the mean vector and Σ_i is the covariance matrix for state i.
  This is the variant used in this project via hmmlearn.GaussianHMM.

6. KEY PROPERTIES
-----------------
  - First-order Markov: memory-less transitions
  - Stationarity assumption (in basic HMM)
  - Number of states N is a hyperparameter
  - Parameters are learned via Baum-Welch (unsupervised)

================================================================================
  MAPPING TO QUANTITATIVE TRADING
================================================================================

  HMM Concept          | Financial Interpretation
  ---------------------|--------------------------------------------------
  Hidden State         | Market Regime (Bull, Bear, Sideways, High-Vol)
  Observation          | Daily return, volatility, volume change, MA ratio
  Transition Matrix    | Probability of regime change (e.g. Bull→Bear)
  Emission (Gaussian)  | Return distribution within each regime
  Viterbi Sequence     | Historical regime labels for each trading day
  Baum-Welch           | Unsupervised training on market data
  Forward Algorithm    | Probability of observed data under current model

================================================================================
"""


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
        save_extracted_text(EMBEDDED_STANFORD_SUMMARY)
        return EMBEDDED_STANFORD_SUMMARY

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
    save_extracted_text(EMBEDDED_STANFORD_SUMMARY)
    return EMBEDDED_STANFORD_SUMMARY


if __name__ == "__main__":
    from file_finder import find_stanford_hmm_pdf, find_repo_root
    root = find_repo_root()
    pdf = find_stanford_hmm_pdf(root)
    text = extract_pdf_text(pdf)
    print(f"\n[PREVIEW] First 500 characters:\n{text[:500]}")

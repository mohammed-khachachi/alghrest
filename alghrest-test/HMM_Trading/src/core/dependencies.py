"""Dependency checks for the HMM Trading project."""


def check_dependencies() -> bool:
    """Verify that all required packages are importable."""
    deps = {
        "pandas":    "pd",
        "numpy":     "np",
        "sklearn":   "scikit-learn",
        "hmmlearn":  "hmmlearn",
        "yfinance":  "yfinance",
        "matplotlib": "matplotlib",
    }
    ok = True
    for module, label in deps.items():
        try:
            __import__(module)
            print(f"  [OK] {label}")
        except ImportError:
            print(f"  [MISSING] {label}  →  pip install {label}")
            ok = False
    return ok

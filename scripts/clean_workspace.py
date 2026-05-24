"""
clean_workspace.py
==================
Cleans up temporary files, build caches, and test artifacts across the workspace.
Works natively on Windows (PowerShell/CMD) and Unix (Linux/macOS).
"""

import os
import shutil
from pathlib import Path

# Target directories to recursively delete
CACHE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    "dist",
    "build",
}

# Directories to entirely purge if present (e.g. temporary backups)
TEMP_DIRS = {
    "XXsabo",
}

# File extensions to purge recursively
TEMP_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
}

def clean_project():
    root = Path(__file__).resolve().parent.parent
    print("=" * 60)
    print("  WORKSPACE CLEANUP & OPTIMIZATION")
    print(f"  Root: {root}")
    print("=" * 60)

    cleaned_dirs = 0
    cleaned_files = 0
    freed_space = 0

    # 1. Walk directory tree and collect paths to remove
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dirpath_path = Path(dirpath)
        
        # Don't clean virtual environment files
        if ".venv" in dirpath_path.parts or "venv" in dirpath_path.parts:
            continue

        # Check for target cache or temporary directories
        for d in list(dirnames):
            if d in CACHE_DIRS or d in TEMP_DIRS:
                target_dir = dirpath_path / d
                try:
                    # Calculate directory size before deleting
                    dir_size = sum(f.stat().st_size for f in target_dir.glob('**/*') if f.is_file())
                    shutil.rmtree(target_dir)
                    dirnames.remove(d)  # Prevents os.walk from trying to traverse it
                    print(f"  [DELETED DIR]  {target_dir.relative_to(root)} ({dir_size / 1024:.1f} KB)")
                    cleaned_dirs += 1
                    freed_space += dir_size
                except Exception as e:
                    print(f"  [ERROR DIR]    Failed to delete {target_dir.relative_to(root)}: {e}")

        # Check for temporary file extensions
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in TEMP_EXTENSIONS or f == ".coverage":
                target_file = dirpath_path / f
                try:
                    file_size = target_file.stat().st_size
                    target_file.unlink()
                    print(f"  [DELETED FILE] {target_file.relative_to(root)} ({file_size / 1024:.1f} KB)")
                    cleaned_files += 1
                    freed_space += file_size
                except Exception as e:
                    print(f"  [ERROR FILE]   Failed to delete {target_file.relative_to(root)}: {e}")

    print("-" * 60)
    print("  SUMMARY:")
    print(f"    Directories deleted : {cleaned_dirs}")
    print(f"    Files deleted       : {cleaned_files}")
    print(f"    Total space freed   : {freed_space / (1024 * 1024):.2f} MB")
    print("=" * 60)
    print("  Workspace clean and running at maximum efficiency!")
    print("=" * 60)

if __name__ == "__main__":
    clean_project()

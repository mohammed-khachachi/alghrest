# HMM_Trading - Codex Instructions

## Working directory

Always work inside:

D:\My_PTOJECT\alghrest-test\alghrest-test\HMM_Trading\

Never work from:

D:\My_PTOJECT\alghrest-test\

## Project status

This project is a Python research project for applying Hidden Markov Models to market regime detection.

Current stable state:
- main.py is a thin entrypoint.
- src/pipeline/runner.py is the orchestrator.
- configs/default.json is the configuration source.
- Stanford PDF is located at:
  references/Stanford_Hidden_Markov_Models.pdf
- pytest works from the local pyproject.toml.
- Current expected test result:
  python -m pytest tests/
  should pass.

## Safety rules

Do not modify multiple phases at once.

For every change:
1. Modify only the requested file or phase.
2. Run py_compile for touched Python files.
3. Run:
   python -m pytest tests/
4. Run:
   python main.py
5. Report results.

Do not:
- change mathematical HMM logic unless explicitly requested
- delete wrappers unless explicitly requested
- delete outputs, reports, references, or configs
- work from the parent directory
- install unrelated dependencies
- refactor broadly without approval

## Current architecture

main.py
-> src/pipeline/runner.py
-> src/data/
-> src/models/
-> src/analysis/
-> src/reporting/
-> src/references/
-> src/core/

## Current phase policy

Work phase by phase.
If uncertain, stop and report instead of guessing.

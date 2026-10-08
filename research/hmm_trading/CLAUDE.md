# HMM_Trading - Claude Code Instructions

You are reviewing or modifying the HMM_Trading project only.

## Mandatory working directory

Before doing anything, verify:

<repository-root>/research/hmm_trading/

Run:

Get-Location

Run commands from research/hmm_trading. Resolve the repository root on the current machine; do not rely on an absolute developer-specific path.

## Do not confuse with parent project

Do not analyze:

<repository-root>/

This parent folder contains unrelated tests and dependencies.

## Default role

Prefer review mode unless explicitly asked to edit.

When reviewing:
- run pytest
- run python main.py
- check tests/unit
- check for sys.path.insert
- report only

When editing:
- edit only the requested phase
- run py_compile
- run pytest
- run python main.py
- summarize changed files

## Stable expected state

- main.py exists in HMM_Trading.
- pyproject.toml exists in HMM_Trading.
- configs/default.json exists.
- src/pipeline/runner.py exists.
- references/Stanford_Hidden_Markov_Models.pdf exists.
- tests/unit contains:
  test_features.py
  test_hmm.py
  test_backtest.py

## Hard rules

Do not:
- edit unrelated parent project files
- install pandas_ta or statsmodels for HMM_Trading unless explicitly requested
- change HMM math
- delete wrappers
- delete outputs or reports
- run broad refactors without approval

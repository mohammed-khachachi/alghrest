# ADR 0001: Separate runtime source, research, and generated assets

- Status: accepted
- Date: 2026-09-26

## Context

Application packages, two distinct HMM projects, static previews, generated files, and historical reports shared the root directory. Root execution could hide package installation mistakes. A second pytest configuration under `tests/` also conflicted with the application configuration.

## Decision

Use `src/` for the six existing Python runtime packages, preserving their public import names. Keep the dashboard independent. Move HMM projects into `research/`, previews into `examples/`, model assets into `artifacts/`, and historical root reports into `docs/archive/`. Keep operational entry points and Compose manifests at the root to preserve established launch paths. Use one root pytest configuration; HMM keeps its separate project configuration.

The Python Packaging Authority explains that [src layout separates importable code from the working directory and requires an installation](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/). Pytest documents [editable installation and separate test directories](https://docs.pytest.org/en/stable/explanation/goodpractices.html). Docker documents how [build context and dockerignore control files available to a build](https://docs.docker.com/build/concepts/context/). These sources guide this repository-specific choice; there is no universal layout that fits every project.

## Consequences

Developers reinstall the editable package after moving a checkout. Shell commands that used physical package paths use `src/...` for analysis and `python -m ...` for execution. Existing imports, topics, account scopes, and risk rails are unchanged. Build validation must inspect the wheel and verify imports outside the checkout. Independent research dependencies and generated artifacts stay out of runtime distributions.

The older HMM project has unique code, so it is retained as a legacy reference. Only confirmed duplicate or obsolete files are removed, with a verified backup and migration record.

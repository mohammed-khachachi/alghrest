# ALGHREST Monorepo Workflow

This document describes how the ALGHREST monorepo is laid out and the rules that keep its subprojects from drifting into each other.

It is documentation only. It does not change build, runtime, or test behavior.

## 1. What lives in this repository

The repository at `D:\My_PTOJECT\alghrest-test\` (Git root) contains two distinct projects:

1. **ALGHREST** — the root multi-agent trading platform. Source lives in `agents/`, `core/`, `api/`, `connectors/`, `dashboard/`, `ml/`, `backtesting/`, `infra/`, `scripts/`, and `tests/`. Configured by `pyproject.toml`, `docker-compose.yml`, and `.env` at the repo root.
2. **HMM_Trading** — an independent educational/research subproject for market-regime detection with Hidden Markov Models. Lives entirely under `HMM_Trading/` and has been stabilized as a standalone project.

```text
D:\My_PTOJECT\alghrest-test\          <- Git root (ALGHREST)
├── agents/                            <- ALGHREST runtime
├── core/
├── api/
├── connectors/
├── dashboard/
├── ml/
├── backtesting/
├── infra/
├── scripts/
├── tests/
├── docs/                              <- ALGHREST root docs (this file)
├── pyproject.toml                     <- ALGHREST deps (Poetry, Python 3.12)
├── docker-compose.yml
├── .env
└── HMM_Trading/                       <- Independent subproject
    ├── main.py
    ├── pyproject.toml                 <- Separate deps
    ├── requirements.txt
    ├── configs/
    ├── src/
    ├── tests/
    ├── docs/                          <- HMM_Trading-internal docs
    ├── references/
    ├── outputs/                       <- Generated, gitignored
    └── reports/
```

HMM_Trading is **not** a separate Git repository and **not** a Git submodule. It is a self-contained project that lives inside the same working tree but does not share runtime, dependencies, virtual environment, or tests with the root ALGHREST application.

## 2. Why we keep them separate

ALGHREST is a production-oriented trading platform with Kafka, Redis, TimescaleDB, async agents, ML inference, and Anthropic Claude reasoning. It moves fast and changes shape often.

HMM_Trading is intentionally smaller, educational, and reproducible. It must stay easy to run from a fresh checkout, on a fresh venv, with no infrastructure. Tying it to ALGHREST's dependency graph or runtime would break that property.

The separation also gives us a clean **integration boundary** to design against later — see `docs/integration-roadmap.md`. Until that boundary is implemented and tested, the two projects remain independent.

## 3. Working in the root ALGHREST project

The root project is documented end-to-end in `README.md` and `CLAUDE.md`. The short version:

- Working directory: `D:\My_PTOJECT\alghrest-test\`
- Python: 3.12 via Poetry (`poetry install`) or the lightweight venv path (`venv-lite\`)
- Tests: `pytest -m unit` (no infrastructure) or `pytest -m integration` (requires `docker compose up -d`)
- Lint / format / type-check: `ruff check .`, `black .`, `isort .`, `mypy agents/ core/`
- Coverage gate: `--cov-fail-under=70` is enforced

Do **not** run ALGHREST tests, lint, or type checks from inside `HMM_Trading/`. The ALGHREST tooling is configured at the repo root and expects to discover ALGHREST source.

## 4. Working in the HMM_Trading subproject

When working on HMM_Trading, change directory into it first and treat it as the project root:

```powershell
cd D:\My_PTOJECT\alghrest-test\HMM_Trading
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m pytest tests/
python main.py
```

Rules (also documented in `HMM_Trading/README.md` and `HMM_Trading/CLAUDE.md`):

- Always work from the HMM_Trading directory when editing this subproject.
- Use a separate virtual environment for HMM_Trading. Do **not** use the root ALGHREST venv.
- Do **not** place an HMM_Trading virtual environment inside the root ALGHREST tree.
- Do **not** run HMM tests from the root project.
- Do **not** commit generated artifacts (`outputs/`), virtual environments (`.venv/`), or caches from HMM_Trading.

HMM_Trading owns its own `tests/` directory, its own configuration in `configs/default.json`, its own dependencies in `requirements.txt` and `pyproject.toml`, and its own generated outputs in `outputs/` (which is gitignored).

## 5. Branching and commit hygiene

Each commit and each pull request should touch **one** project, not both, unless there is an explicit integration task that requires crossing the boundary.

Recommended commit prefixes:

- Root ALGHREST changes: `feat(agents): ...`, `fix(api): ...`, `docs: ...`, `test(integration): ...`
- HMM_Trading changes: `feat(hmm): ...`, `fix(hmm): ...`, `docs(hmm): ...`, `test(hmm): ...`

If a change genuinely spans both projects (for example, a future CSV adapter that lives in ALGHREST and reads HMM_Trading outputs), keep it in a dedicated branch and call it out in the PR description so reviewers know to read both sides.

## 6. CI considerations

The current CI workflow at `.github/workflows/tests.yml` runs ALGHREST lint and tests on push and PR. HMM_Trading does **not** yet have its own CI workflow. When one is added it should:

- Run only when files under `HMM_Trading/**` change (path filter).
- Use a separate Python setup and install from `HMM_Trading/requirements.txt`.
- Run `python -m pytest tests/` from inside `HMM_Trading/`.
- **Not** install ALGHREST dependencies.

Keep the two CI surfaces independent so a break in one project does not block the other.

## 7. Dependency policy

- Root ALGHREST dependencies are managed by `pyproject.toml` (Poetry) at the repo root.
- HMM_Trading dependencies are managed by `HMM_Trading/requirements.txt` and its own `pyproject.toml`.
- Do **not** add HMM_Trading-only dependencies (for example, `hmmlearn`) to the root `pyproject.toml`.
- Do **not** add ALGHREST runtime dependencies (for example, `aiokafka`, `redis`, `web3`) to HMM_Trading.

If both projects end up needing the same library, they may still pin different versions — that is fine and intentional, because each project has its own virtual environment.

## 8. Documentation locations

- Root ALGHREST documentation: `README.md`, `CLAUDE.md`, `AGENTS.md`, and files under `docs/` at the repo root.
- HMM_Trading documentation: `HMM_Trading/README.md`, `HMM_Trading/CLAUDE.md`, `HMM_Trading/AGENTS.md`, and `HMM_Trading/docs/`.

This file (`docs/monorepo-workflow.md`) and `docs/integration-roadmap.md` are the two root-level documents that describe how the monorepo as a whole is organized and how the two projects will eventually connect. They are intentionally short. Detailed architecture for HMM_Trading lives inside the subproject at `HMM_Trading/docs/architecture.md`.

## 9. Future-maintainer checklist

Before making a change that crosses the ALGHREST ↔ HMM_Trading boundary, confirm:

- [ ] The change is documented in `docs/integration-roadmap.md` and matches the current integration level.
- [ ] HMM_Trading still runs standalone with its own venv (`python -m pytest tests/` and `python main.py` from inside the subproject).
- [ ] No HMM_Trading dependency has leaked into the root `pyproject.toml`.
- [ ] No ALGHREST runtime dependency has leaked into HMM_Trading.
- [ ] Generated HMM outputs are still ignored by Git.
- [ ] The branch and PR clearly indicate that both projects are touched.

If any of these fails, the change is probably trying to integrate the two projects ahead of the roadmap. Stop and revisit `docs/integration-roadmap.md`.

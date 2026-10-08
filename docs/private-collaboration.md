# Developing ALGHREST in a private repository

The repository is https://github.com/mohammed-khachachi/alghrest. Keep it private.
The owner can invite GitHub accounts under **Settings → Collaborators → Add people**.
Invitees must accept the invitation before cloning or contributing. Personal private
repositories grant collaborators read/write access; use branches and pull requests
for review. No collaborator invitation is implied by this document.

Official reference: [GitHub collaborator invitations](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository).

## Clone and install

Authenticate Git or GitHub CLI with the invited account. Never put access tokens
in clone URLs, commits or configuration files committed to this repository.

```powershell
git clone https://github.com/mohammed-khachachi/alghrest.git
Set-Location alghrest
poetry env use 3.12
poetry install --all-groups
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Use Python 3.12, Poetry, Node.js/npm for the dashboard, and Docker only for the
isolated-service integration tests or development infrastructure. Dependencies
are declared in `pyproject.toml` / `poetry.lock` and `dashboard/package.json` /
`dashboard/package-lock.json`; the environments themselves are not committed.
See [quality checks](maintenance/quality-checks.md), [monorepo workflow](monorepo-workflow.md),
and the root README for commands. HMM research maintains separate environments
and tests under `research/`.

Start with unit tests and a dashboard mock, without broker access:

```powershell
poetry run python -m pytest -m unit --no-cov
poetry run python scripts/check_architecture.py
poetry run python -m api.mock_server
# In another terminal:
Set-Location dashboard
npm ci
npm run dev
```

For the independent advisory API, use `poetry run python -m api.advisor` on
loopback port 8011, then open the dashboard's `/assistant` page. The general API
and mock share port 8000; the advisory service has its separate port.
Follow [manual assistant](manual-assistant.md) for explicit imported market/account
state and advisory-only operation. Missing market entitlements or account evidence
must remain NO TRADE/UNKNOWN; fixtures are not permission to trade.

## Contents and external inputs

The source, application/research tests, dashboard, infrastructure definitions,
lockfiles, example environment, documentation, and selected synthetic verification
records are committed. Existing local model assets are included at
`artifacts/models/cnn_btc_usdt.pth` and `artifacts/models/ppo_position_sizer.zip`.
Their presence does not certify their training provenance, strategy edge, safety,
or production readiness. The current inference server remains experimental;
including these assets does not enable execution or strategy promotion.

Real `.env` values, passwords, API keys, private keys, operational financial stores,
private market datasets, raw operational logs and local caches/builds are excluded.
Each developer supplies their own permitted local configuration. Licensed market
history, exchange/API entitlement and real account policy evidence are separate
inputs; do not scrape or infer missing access. Do not share owner credentials
with collaborators.

## Current tree and archived history

`main` contains the active application, tests, dashboard, current HMM study,
model assets and developer/runbook documentation. Retired `hmm_legacy` code,
old root summaries, dated raw recovery outputs and a past paper-readiness result
are preserved in [the immutable private snapshot](https://github.com/mohammed-khachachi/alghrest/tree/f88e63be74c2f64ca68c5564c20863f97ca980c8) and the branch
`archive/pre-current-project-cleanup-20261006`. They are not current setup inputs.
See [current project files](maintenance/current-project-files.md) for the audit.
Meaningful regression fixtures and selected synthetic verification records remain
because current tests and safety/research documentation use them.

## Make reviewed changes

```powershell
git switch -c fix/short-description
# Edit the responsible package and its relevant tests.
git add path/to/changed-file
git commit -m "fix: describe the behavior changed"
git push -u origin fix/short-description
```

Open a pull request against `main`. Read `CLAUDE.md`, `AGENTS.md` and scoped
research instructions before changes. Preserve deterministic risk, financial
provenance and advisory-only boundaries. Changes to strategy, policy or risk
require appropriate meaningful regression/boundary tests. Never activate live
trading or DeFi as part of setup.

GitHub Actions is configured in `.github/workflows/tests.yml`. Local passing tests
do not prove that a remote Actions run passed; inspect the actual run result.
Do not bypass a failed check by making the repository public or exposing secrets.

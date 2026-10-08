# Model assets and research evidence

This directory separates included development assets from generated local state.
It is excluded from the runtime wheel and Docker application build context.

## Included in the private repository

| Path | Contents |
| --- | --- |
| `models/cnn_btc_usdt.pth` | Existing CNN checkpoint |
| `models/ppo_position_sizer.zip` | Existing PPO archive |
| `tcp25-goal/` | Selected synthetic examples and verification summaries for advisory, risk, replay and research work |

Training code writes CNN/PPO files to `models/`. The current experimental
inference server creates a CNN in memory and does not automatically load these
assets; its RL action is still a placeholder. Existing file bytes are preserved,
but their presence does not establish training provenance, predictive edge or
production readiness. Only load trusted serialized model files.

The before-code snapshot under `tcp25-goal/trade-management/before/` is a fixture
for an explicit opt-in regression comparison, not a second runtime agent.
Synthetic evaluation PASS examples are conditional calculations, not proof of a
completed official evaluation. Saved research results are pinned to code/input
fingerprints and must be verified with the matching implementation.

## Generated local files

`.gitignore` excludes other generated models, checkpoints, test reports, datasets,
logs and SQLite/account state. `artifacts/advisory/research.sqlite3` is the local
research journal; use SQLite backup for an active journal, never commit it.
The two model assets and selected evidence were intentionally tracked despite
broader generated-file ignore rules.

Keep important model versions and evaluation provenance in durable backed-up
storage before cleanup. Do not publish secrets, private licensed data, financial
stores or raw operational logs. See [current project files](../docs/maintenance/current-project-files.md)
and [private development](../docs/private-collaboration.md).

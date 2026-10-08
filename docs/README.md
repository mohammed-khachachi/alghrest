# ALGHREST documentation

Current development uses the private repository's `main` branch. Start with the
[root README](../README.md), [current project inventory](maintenance/current-project-files.md)
and [private collaborator setup](private-collaboration.md).

## Architecture and development

- [Architecture and advisory boundaries](architecture.md)
- [Application/dashboard/research workflow](monorepo-workflow.md)
- [Quality checks and dated verification evidence](maintenance/quality-checks.md)
- [Source-layout decision](decisions/0001-source-layout.md)
- [Runtime-boundary decision](decisions/0002-runtime-boundaries.md)
- [Layout migration record](maintenance/structure-migration.md)
- [Migration validation scope](maintenance/structure-validation.md)
- [Current advisory/TCP25 migration evidence and unresolved gates](maintenance/tcp25-migration.md)

## Operation and research

- [Manual assistant, imported data and evaluation journal](manual-assistant.md): advisory API on 8011; Vite `/assistant` on 5173.
- [Durable accounting and explicit opening balances/deposits](accounting.md)
- [Execution recovery and isolated local test services](execution-recovery.md)
- [Backtesting calculations and validation](backtesting.md)
- [Dashboard-only lightweight development](LIGHTWEIGHT_DEV.md)
- [Local access keys and AI limits](maintenance/access-and-ai-limits.md)
- [Kill-switch testing](kill_switch_testing_guide.md)
- [Deployment runbook](runbooks/deployment.md): review profile and environment prerequisites.
- [Research integration roadmap](integration-roadmap.md)
- [Current HMM study](../research/hmm_trading/README.md)

## Evidence and limits

Dated test/verification sections describe their original code and environment.
Local passing tests do not certify hosted CI, complete TCP25 evaluation, a live
feed or real-account readiness. Synthetic strategy/evaluation records remain
experiments. Current source and selected verification records stay in `main`;
real credentials, financial stores, licensed/private datasets and raw operational
logs are not shared through Git.

Retired reports, raw recovery outputs, old paper-readiness data and the older HMM
implementation remain in the private archive branch
`archive/pre-current-project-cleanup-20261006` and
[its immutable snapshot](https://github.com/mohammed-khachachi/alghrest/tree/f88e63be74c2f64ca68c5564c20863f97ca980c8).
Their original paths and results are historical evidence, not current setup inputs.

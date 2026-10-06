# Documentation

## Start here

- [Repository overview](../README.md)
- [Architecture and module boundaries](architecture.md)
- [Development and subproject workflow](monorepo-workflow.md)
- [Decision: adopt the src layout](decisions/0001-source-layout.md)
- [Layout migration and cleanup record](maintenance/structure-migration.md)
- [Migration validation results](maintenance/structure-validation.md)
- [Quality checks and verified results](maintenance/quality-checks.md)

## Operating the application

- [Durable accounting, paper deposits and performance](accounting.md)
- [Backtest calculations and validation](backtesting.md)
- [Execution recovery and paper setup](execution-recovery.md)
- [Lightweight dashboard development](LIGHTWEIGHT_DEV.md)
- [Kill-switch testing](kill_switch_testing_guide.md)
- [Deployment guide](runbooks/deployment.md) — review environment-specific commands before use
- [Research integration roadmap](integration-roadmap.md)

## Historical evidence

[archive/](archive/) holds prior audits, implementation summaries, and old project descriptions. Their paths, counts, and test results describe the versions that produced them. [recovery/](recovery/) holds dated recovery evidence; neither collection is the current architecture specification. `paper-activation-status.json` is a point-in-time local readiness result, not proof of live readiness.

- [Manual Nasdaq assistant and evaluation journal](manual-assistant.md)

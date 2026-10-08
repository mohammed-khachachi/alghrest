# Research

The current independent study is [hmm_trading/](hmm_trading/README.md). It has its
own configuration, references, tests and dependencies. Work inside that directory
with a separate environment; its local Python package named `src` must not be
mixed with the root application import environment.

The HMM pipeline tries Yahoo Finance and falls back to synthetic Markov data on
failure. Label synthetic results explicitly. Its educational in-sample backtest
is not an approved trading strategy or TCP25 pass evidence. Root futures/edge,
bootstrap, walk-forward and evaluation-event tools live in `src/backtesting/`;
[advisory research evidence](../docs/maintenance/tcp25-migration.md) tracks their
limits and validation scope.

The retired `hmm_legacy` study is preserved in the private archive branch
`archive/pre-current-project-cleanup-20261006` and
[immutable snapshot](https://github.com/mohammed-khachachi/alghrest/tree/f88e63be74c2f64ca68c5564c20863f97ca980c8/research/hmm_legacy).
It is outside the current working tree. Keep any root integration explicit and
tested; see [development workflow](../docs/monorepo-workflow.md) and
[integration roadmap](../docs/integration-roadmap.md).

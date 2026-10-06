# ALGHREST recovery checkpoint — 2026-09-23

Phase 0 remains incomplete. The project is not ready to advance to the next phase, paper trading, or live trading.

## State preservation

The surviving pre-edit recovery inventory matches its four source/document entries. That older inventory predates model restoration, so it does not prove every historical edit. Git history is unavailable. The session-start SHA-256 inventory is saved in `alghrest-session-start.json`.

The restored models, model contract tests, and Monte Carlo/validate_all repair are present and remain byte-for-byte unchanged in this continuation. The repository pyproject.toml and poetry.lock also remain byte-for-byte unchanged. The original 70% coverage gate, risk limits, validation and security settings were not relaxed.

The earlier temporary test environment was absent after the reset. Recreated `/tmp/alghrest-recovery-venv` from the saved `docs/recovery-environment.txt` using Python 3.12.14; pip check passes. This is a diagnostic subset, not a complete Poetry installation.

## Verification

| Check | Result |
|---|---|
| Focused model contracts before edits | 22 passed; command failed its whole-project coverage gate (15.49%) |
| Unit baseline before edits | 117 passed, 0 failed; coverage 28.94%; gate failed |
| Integration collection before edits | All 80 collected |
| Integration baseline before edits | 33 passed, 27 failed, 20 setup errors |
| Runtime imports | 65/65 under agents, core, connectors, api and backtesting, including api.mock_server; ML training/inference is not included |
| Final unit assertions | 117 passed, 0 failed |
| Final integration assertions | 42 passed, 26 failed, 12 setup errors; no skips/xfails |
| Final combined run | 159 passed, 26 failed, 12 setup errors (197 tests) |
| Combined branch coverage | 32.89% across agents/core/connectors; required 70%; gate FAILED |
| Both edited integration files | 7/7 execution pipeline and 7/7 crash/kill-switch tests pass |
| Ruff | Pass on both edited test files plus restored models and model contract tests |
| Mypy | Pass on core/data/models.py |
| Compose configuration | `docker compose --env-file .env.example config --no-env-resolution --quiet` passes |
| Docker daemon | Available (29.7.2); access required running outside the sandbox |

The API TestClient stalled under sandbox restrictions; the bounded run outside the sandbox completed. All test invocations explicitly used development mode. Passing API integration checks exercise a FastAPI app defined inside the test file, not the production application, and cannot establish production API readiness.

`test_agent_failure_cascade_prevention` passed the initial baseline and failed the combined run. Its random failure injection does not guarantee use of the final fallback, yet the assertion requires it. This is tracked as a nondeterministic harness defect, not hidden by a rerun.

## Files changed

Existing files changed in this continuation:

- `tests/integration/test_execution_pipeline.py`
- `tests/integration/test_market_crash_kill_switch.py`

- Execution pipeline: replace stale contracts with current producer/consumer contracts; await finite streams instead of cancelling unchecked tasks; require explicit rejection alerts, actual fill publication, preservation of order linkage, and all ten batch approvals. No real exchange calls.
- Crash/kill-switch: complete model fixtures; patch dependencies in the module that uses them; measure drawdown cumulatively; assert the documented weekly halt instead of a nonexistent daily full-halt reason; verify reset propagation. No threshold changed.
- New evidence/report files are contained in `docs/recovery/2026-09-23/`. Local `.coverage` and `htmlcov/` are generated test artifacts.

## Temporary dependency resolution (repository files untouched)

Executed with an explicit directory change:

```bash
cd /tmp/alghrest-lock-check && \
POETRY_CACHE_DIR=/tmp/alghrest-poetry-cache \
POETRY_KEYRING_ENABLED=false \
/tmp/alghrest-tools/bin/poetry lock --no-interaction \
> /tmp/alghrest-lock-update.log 2>&1
```

Poetry 2.4.1 resolution succeeded (exit 0), wrote the temporary lock, and `poetry check --lock` succeeded. No dependency-solving errors. Poetry automatically selected Python 3.12.14 after detecting that shell Python 3.14.7 was incompatible.

Warnings: source-package build metadata reported deprecated license classifiers and unknown `test_suite`; check reported legacy tool.poetry metadata fields (name, version, description, readme, authors). These warnings did not prevent resolution.

| Dependency | Temporary result |
|---|---|
| asyncpraw | Added 8.0.3 |
| asyncprawcore | Added 4.0.0 |
| aiofiles | Added 25.1.0 |
| aiokafka[lz4] | aiokafka remains 0.11.0; LZ4 extra adds cramjam 2.12.1 |
| psutil | Newly declared direct dependency; already locked at 7.2.2, version unchanged |
| update-checker | 0.18.0 → 1.0.0, required by asyncpraw; async extra selects aiohttp |
| onnxruntime | Remains 1.26.0; one macOS ARM64 wheel/hash added by Poetry metadata refresh |

No packages removed. No other existing package versions changed. A fresh `/tmp/alghrest-dependency-probe` installed asyncpraw, psutil and aiokafka[lz4] with constraints exported from the temporary main lock. All imports, Kafka LZ4 encode/decode round trip, and pip check passed. This proves those packages and their transitive dependencies install together; it does not prove installation or runtime compatibility of the entire large Poetry dependency graph.

Full diffs: [manifest](pyproject.toml.diff), [lock](poetry.lock.diff). Full logs: [resolution](alghrest-lock-update.log), [check](alghrest-temp-check.log), [targeted installation](alghrest-dependency-probe-install.log). Repository manifest/lock hashes still equal the session-start hashes. Temporary changes have not been promoted.

## Remaining Phase 0 / readiness blockers

1. Apply only a reviewed, verified dependency candidate, then establish a clean installation of the full intended environment. The verified candidate has not been promoted; this checkpoint leaves the repository manifests untouched and records the full diffs for review.
2. Root Dockerfile still installs the separate unpinned requirements.txt, which omits runtime imports such as pandas-ta, arch, statsmodels, feedparser and asyncpraw. The API Compose command still runs pip install at startup. Root/dashboard image builds were not run or validated in this continuation; dashboard has not been compiled.
3. 38 integration failures/setup errors remain, individually classified below. Several tests target features that do not exist, and other passing tests only validate locally defined mocks. No old model aliases or fabricated runtime compatibility methods were added.
4. Coverage is below 70%; the required gate remains red. Full repository lint/type checks and CI are not certified by the focused checks.
5. No Kafka/Redis/TimescaleDB end-to-end topology, broker retry/durability/deduplication, real exchange paper execution, ML weights, or live strategy qualification has passed here. Docker daemon availability and valid Compose syntax are not service readiness.
6. Review runtime execution risks in a subsequent contract-focused change: fee optimization and execution independently consume the same pending topic; algorithmic children currently use LIMIT with no price, which ExchangeExecutor rejects. These are static findings, not repaired or certified in this checkpoint. Kill-switch and failure recovery need validation through actual infrastructure.

## Failure ledger

Every failing baseline test, plus the newly observed nondeterministic failure, is listed. Details and original exceptions are machine-readable in [failure-classification.json](failure-classification.json). Full final results: [JUnit](final-tests.xml), [log](final-tests.log), [coverage](final-coverage.json).

| Test | Baseline → final | Root cause / status |
|---|---|---|
| `test_agent_coordination.TestAgentCoordination::test_agent_failure_cascade_prevention` | passed → failure | **Nondeterministic test**: Random failures do not guarantee that the final stable fallback executes. Passed the baseline but failed the combined run. No production change in between. |
| `test_agent_coordination.TestAgentCoordination::test_message_ordering_and_causality` | failure → failure | **Stale topic/API**: KafkaTopic.MARKET_DATA is absent; current producers use PRICES_REALTIME/OHLCV. Mock agents also use legacy publishing/consumer conventions. |
| `test_agent_coordination.TestAgentCoordination::test_multi_tier_signal_propagation` | error → error | **Stale fixture/API**: Mock BaseStrategy supplies unsupported tier argument and omits current strategy constructor fields; mock publishers also use removed topics and await synchronous make_consumer. |
| `test_agent_coordination.TestAgentCoordination::test_risk_governor_emergency_coordination` | error → error | **Stale fixture/API**: Same invalid MockTrendStrategy constructor; test exercises mock orchestration, not the production RiskGovernor. |
| `test_agent_coordination.TestAgentRecoveryAndRebalancing::test_workload_rebalancing` | failure → failure | **Test simulation defect / missing real integration**: Fixed capacity of the local fake agents yields exactly five unprocessed items; assertion requires fewer than five. No runtime rebalancer is exercised. |
| `test_api_dashboard_integration.TestAPIDashboardIntegration::test_dashboard_error_handling` | failure → failure | **Wrong patch target / missing assertion**: patch(app.get_portfolio) targets a nonexistent Python module; even a corrected patch would need to target the registered dependency/route and assert the 500 response. |
| `test_api_dashboard_integration.TestAPIEndpoints::test_api_cors_headers` | failure → failure | **Test app configuration**: Locally defined FastAPI test app has no CORS middleware; bare OPTIONS receives 405. It is not api.main.app. |
| `test_api_dashboard_integration.TestWebSocketFeeds::test_websocket_connection_handling` | failure → failure | **TestClient misuse**: websocket_connect returns a context manager; the nonexistent endpoint connection is never entered, so no exception is raised. |
| `test_api_dashboard_integration.TestWebSocketFeeds::test_websocket_message_rate` | failure → failure | **TestClient misuse / swallowed error**: receive_json has no timeout keyword. A bare except hides the resulting TypeError, leaving zero received messages. |
| `test_backtesting_validation.TestBacktestingValidation::test_complete_backtesting_pipeline` | failure → failure | **Mock arithmetic and stale result contracts**: Local MockBacktestEngine multiplies Decimal OHLC prices by floats. Further code uses stale BacktestResult/WalkForwardResult contracts; it does not invoke backtesting.engine.BacktestEngine. |
| `test_backtesting_validation.TestBacktestingValidation::test_data_quality_validation` | failure → failure | **Mock arithmetic and stale result contracts**: Local MockBacktestEngine multiplies Decimal OHLC prices by floats. Further code uses stale BacktestResult/WalkForwardResult contracts; it does not invoke backtesting.engine.BacktestEngine. |
| `test_backtesting_validation.TestBacktestingValidation::test_monte_carlo_risk_assessment` | failure → failure | **Stale mock result contract**: Local MockBacktestEngine constructs MonteCarloResult with legacy fields, not the production engine contract. Do not add model aliases to accommodate it. |
| `test_backtesting_validation.TestBacktestingValidation::test_performance_metrics_calculation` | failure → failure | **Mock arithmetic and stale result contracts**: Local MockBacktestEngine multiplies Decimal OHLC prices by floats. Further code uses stale BacktestResult/WalkForwardResult contracts; it does not invoke backtesting.engine.BacktestEngine. |
| `test_backtesting_validation.TestBacktestingValidation::test_strategy_approval_workflow` | failure → failure | **Mock arithmetic and stale result contracts**: Local MockBacktestEngine multiplies Decimal OHLC prices by floats. Further code uses stale BacktestResult/WalkForwardResult contracts; it does not invoke backtesting.engine.BacktestEngine. |
| `test_backtesting_validation.TestBacktestingValidation::test_strategy_qualification_thresholds` | failure → failure | **Mock arithmetic and stale result contracts**: Local MockBacktestEngine multiplies Decimal OHLC prices by floats. Further code uses stale BacktestResult/WalkForwardResult contracts; it does not invoke backtesting.engine.BacktestEngine. |
| `test_backtesting_validation.TestBacktestingValidation::test_walk_forward_analysis_degradation` | failure → failure | **Mock arithmetic and stale result contracts**: Local MockBacktestEngine multiplies Decimal OHLC prices by floats. Further code uses stale BacktestResult/WalkForwardResult contracts; it does not invoke backtesting.engine.BacktestEngine. |
| `test_execution_pipeline.TestExecutionPipeline::test_execution_pipeline_performance` | error → passed | **Repaired fixture and assertions**: Current typed Portfolio/TradeProposal/AgentMessage, finite awaited streams, precise risk rejection assertions, optimization flags, and actual executor fill publication with mocked external I/O. |
| `test_execution_pipeline.TestExecutionPipeline::test_happy_path_execution` | error → passed | **Repaired fixture and assertions**: Current typed Portfolio/TradeProposal/AgentMessage, finite awaited streams, precise risk rejection assertions, optimization flags, and actual executor fill publication with mocked external I/O. |
| `test_execution_pipeline.TestExecutionPipeline::test_kill_switch_halts_pipeline` | error → passed | **Repaired fixture and assertions**: Current typed Portfolio/TradeProposal/AgentMessage, finite awaited streams, precise risk rejection assertions, optimization flags, and actual executor fill publication with mocked external I/O. |
| `test_execution_pipeline.TestExecutionPipeline::test_optimization_flags_prevent_reentry` | error → passed | **Repaired fixture and assertions**: Current typed Portfolio/TradeProposal/AgentMessage, finite awaited streams, precise risk rejection assertions, optimization flags, and actual executor fill publication with mocked external I/O. |
| `test_execution_pipeline.TestExecutionPipeline::test_pipeline_with_ml_predictor_fallback` | error → passed | **Repaired fixture and assertions**: Current typed Portfolio/TradeProposal/AgentMessage, finite awaited streams, precise risk rejection assertions, optimization flags, and actual executor fill publication with mocked external I/O. |
| `test_execution_pipeline.TestExecutionPipeline::test_position_limit_rejection` | error → passed | **Repaired fixture and assertions**: Current typed Portfolio/TradeProposal/AgentMessage, finite awaited streams, precise risk rejection assertions, optimization flags, and actual executor fill publication with mocked external I/O. |
| `test_kafka_messaging.TestKafkaMessaging::test_consumer_error_handling` | failure → failure | **Stale wrapper API / reliability gap**: Consumer takes agent_name, not group_id/bootstrap_servers. Mock dict records differ from Kafka records; the test also expects three failures from a one-pass stream. Handler acknowledgements need independent real-broker validation. |
| `test_kafka_messaging.TestKafkaMessaging::test_consumer_group_load_balancing` | failure → failure | **Stale API / missing real integration**: MARKET_DATA and consumer constructor are stale; the test merely increments local counters and cannot validate group assignment or rebalance. |
| `test_kafka_messaging.TestKafkaMessaging::test_dead_letter_queue_handling` | failure → failure | **Stale API / unimplemented feature**: Automatic DLQ routing and DLQ provisioning are absent. Test manually sends a dict to an invented topic; adapting the constructor alone would not test recovery. |
| `test_kafka_messaging.TestKafkaMessaging::test_high_throughput_message_processing` | failure → failure | **Stale wrapper/topic API**: Uses unsupported constructor, MARKET_DATA, and dict send API. Mock throughput would not establish broker throughput. |
| `test_kafka_messaging.TestKafkaMessaging::test_message_ordering_guarantee` | failure → failure | **Stale wrapper API**: Producer is settings-driven, send expects AgentMessage, low-level method is send_and_wait, and MARKET_DATA is not a provisioned topic. |
| `test_kafka_messaging.TestKafkaMessaging::test_producer_consumer_roundtrip` | error → error | **Stale fixture/API**: Proposal omits agent_id, exchange, asset_class, size_usd, confidence_score; wrapper constructors and wire expectations are also stale. |
| `test_kafka_messaging.TestKafkaMessaging::test_schema_validation_and_evolution` | failure → failure | **Stale wrapper/model contract**: Wrapper does not take bootstrap_servers or serialize arbitrary proposal dicts through send; tests need real AgentMessage and current required proposal fields. |
| `test_kafka_messaging.TestMessageBusReliability::test_connection_recovery` | failure → failure | **Wrong patch target**: No producer _connect method; initialize retries AIOKafkaProducer.start using tenacity. Test patches an API that does not exist. |
| `test_kafka_messaging.TestMessageBusReliability::test_exactly_once_semantics` | failure → failure | **Stale API / unsupported guarantee**: Setting an arbitrary _enable_idempotence attribute does not configure Kafka. Three explicit sends are not application deduplication or exactly-once processing. |
| `test_kafka_messaging.TestMessageBusReliability::test_message_durability` | failure → failure | **Stale configuration boundary**: acks and enable_idempotence belong to AIOKafkaProducer construction, not wrapper.send. Real broker acknowledgement/durability remains unverified. |
| `test_market_crash_kill_switch.TestKillSwitchPerformance::test_kill_switch_latency_benchmark` | failure → passed | **Repaired fixture and accounting**: Complete Position/OHLCV contracts, patch imported state/alerts at lookup sites, cumulative drawdown from initial capital, assert the actual 7% weekly halt, and verify Redis activation/reset calls. |
| `test_market_crash_kill_switch.TestMarketCrashKillSwitch::test_flash_crash_kill_switch_activation` | error → passed | **Repaired fixture and accounting**: Complete Position/OHLCV contracts, patch imported state/alerts at lookup sites, cumulative drawdown from initial capital, assert the actual 7% weekly halt, and verify Redis activation/reset calls. |
| `test_market_crash_kill_switch.TestMarketCrashKillSwitch::test_kill_switch_escalation_levels` | error → passed | **Repaired fixture and accounting**: Complete Position/OHLCV contracts, patch imported state/alerts at lookup sites, cumulative drawdown from initial capital, assert the actual 7% weekly halt, and verify Redis activation/reset calls. |
| `test_market_crash_kill_switch.TestMarketCrashKillSwitch::test_kill_switch_recovery_procedures` | failure → passed | **Repaired fixture and accounting**: Complete Position/OHLCV contracts, patch imported state/alerts at lookup sites, cumulative drawdown from initial capital, assert the actual 7% weekly halt, and verify Redis activation/reset calls. |
| `test_ml_failover.TestMLPredictorFailover::test_technical_analysis_fallback_accuracy` | failure → failure | **Fixture/strategy expectation mismatch**: Monotonic rising closes produce overbought RSI (>70), which the implemented fallback treats as bearish. The test assumes trend-following behavior; changing trading logic or accepting every signal would conceal the mismatch. |
| `test_redis_state_management.TestCrossAgentStateSync::test_state_consistency_across_agents` | failure → failure | **Stale API / invalid shared-state harness**: Uses nonexistent constructor/setter and store_shared_state/get_shared_state. Independent mocks configured with identical return values do not test Redis consistency. |
| `test_redis_state_management.TestCrossAgentStateSync::test_state_version_conflicts` | failure → failure | **Stale API / unimplemented feature**: No store_versioned_state/CAS API exists. No compatibility method was added just to satisfy this test. |
| `test_redis_state_management.TestRedisStateManagement::test_agent_heartbeat_tracking` | error → error | **Stale StateManager API/fixture**: Constructor takes no redis_url and redis is read-only. Runtime uses set_agent_health/get_all_agent_healths and expiring per-agent keys, not heartbeat hashes. |
| `test_redis_state_management.TestRedisStateManagement::test_connection_pool_management` | error → error | **Stale API / mock cannot prove pooling**: Constructor fails first; store_agent_state does not exist. Mock call counts cannot establish real pool exhaustion behavior. |
| `test_redis_state_management.TestRedisStateManagement::test_kill_switch_state_propagation` | error → error | **Wrong patch target / stale API**: Constructor fails first; KillSwitch uses imported module singleton, is_active is a property, and state key is alghrest:kill_switch:active via setex. |
| `test_redis_state_management.TestRedisStateManagement::test_memory_usage_optimization` | error → error | **Stale API / unimplemented feature**: Constructor fails first; store_compressed_data is not implemented and has no current runtime consumer. |
| `test_redis_state_management.TestRedisStateManagement::test_portfolio_state_persistence` | error → error | **Stale API/storage contract**: Constructor fails first; runtime set_portfolio/get_portfolio uses a serialized Portfolio in one string key, not hashes or an untyped dict. Position fixture is incomplete. |
| `test_redis_state_management.TestRedisStateManagement::test_price_cache_performance` | error → error | **Stale API / unsupported bulk helper**: Constructor fails first; PricePublisher uses set_json(prices:{symbol}, ttl=60), not store_price_data/get_multiple_prices. |
| `test_redis_state_management.TestRedisStateManagement::test_redis_failover_handling` | error → error | **Stale API / unimplemented feature**: Constructor fails first; no StateManager.health_check or Sentinel failover integration is implemented. |
| `test_redis_state_management.TestRedisStateManagement::test_state_corruption_recovery` | error → error | **Stale API / unimplemented feature**: Constructor fails first; get_agent_state_with_backup and automatic backup recovery do not exist. JSON parsing currently raises on corruption. |
| `test_redis_state_management.TestRedisStateManagement::test_unhealthy_agent_detection` | error → error | **Stale API / unimplemented feature**: Constructor fails first; StateManager has no get_unhealthy_agents timeout-scanning API. Agent health keys instead expire. |

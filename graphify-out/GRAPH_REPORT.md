# Graph Report - alghrest-main  (2026-10-31)

## Corpus Check
- 457 files · ~348,348 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 4, .conf 3, .properties 2)

## Summary
- 6573 nodes · 19478 edges · 231 communities (156 shown, 75 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 2024 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `030f7457`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- asyncio
- ResearchJournal
- terminalResearch.ts
- advisory.py
- userPolicy.ts
- OpenBBAdapter
- useLanguage
- ProposalApprover
- test_evaluation_events.py
- TestLiveTradingPreflightGate
- MomentumStrategy
- Valuation
- AdvisoryStore
- newsEvents.ts
- Quote
- test_tcp25_personal.py
- ws.ts
- ._get_ml_prediction
- BacktestEngine
- package.json
- test_economic_events.py
- VolatilityForecaster
- kill_switch.py
- profile
- test_advisory_briefings.py
- test_evaluation_policy.py
- TestRunner
- ObservationPanel
- test_advisory_risk.py
- TelegramBotManager
- test_advisory_observations.py
- EvaluationSession
- core.ts
- advisor.py
- Any
- test_telegram_and_audit.py
- AssetClass
- unittest_mock
- pytest
- test_futures_validation.py
- test_path_risk.py
- ExchangeConnector
- ExternalSandboxBroker
- request
- test_market_selection.py
- StateManager
- App.tsx
- MarketDataPanel.tsx
- strategy_signals.py
- pydantic
- research_pdf.py
- .test_kill_switch_escalation_levels
- MacroRotator
- validation.py
- RiskEngine
- TrendFollower
- advisory_firstrate_intake.py
- test_advisory_context.py
- test_model_contracts.py
- core/advisory/openterminal_research.py
- test_advisory_api.py
- test_monitoring_contracts.py
- openbb_adapter.py
- test_strategy_registry.py
- build_report
- briefing.py
- test_writer_lease.py
- utcnow
- briefing_store.py
- test_account_profiles.py
- test_portfolio_tracker.py
- mock_ml_server.py
- futures.py
- test_advisory_firstrate_intake.py
- test_openterminal_research.py
- test_risk_engine.py
- re
- json
- DashboardWebSocketManager
- time
- main.py
- train.py
- RiskGovernor
- message_bus.py
- test_architecture.py
- test_accounting_pipeline.py
- MarketSnapshot
- test_research_backup.py
- test_execution_adapters.py
- .redis
- ExchangeExecutor
- StatArb
- test_advisory_capabilities.py
- compilerOptions
- test_execution_recovery.py
- api/security.py
- news_analyst.py
- SentimentAnalyst
- CorrelationEngine
- AlertManager
- json
- demo_messages
- RecoveryBlockedError
- KillSwitchStressTester
- test_price_publisher.py
- GeopoliticalWatcher
- openterminal-service.mjs
- test_intelligence_agents.py
- test_api_dashboard_integration.py
- test_prompt_caching.py
- MLPredictorAgent
- test_trade_management.py
- BookState
- dependencies
- OpenBBIngestionPipeline
- KillSwitch
- NewsAnalyst
- OnChainSleuth
- CrossExchangeArb
- mes5m_data.py
- .lock
- test_research_quality.py
- test_funding_postgres.py
- ComplianceAgent
- CopyTradingAgent
- KafkaMetricsCollector
- PricePublisher
- advisory/models.py
- test_research_monitor.py
- test_durable_fill_survives_real_kafka_consumer_restart
- test_research_journal.py
- test_strategy_behavior.py
- test_access_security.py
- BreakoutHunter
- httpx
- .publish
- LifecycleAgent
- .is_strategy_paused
- performance.py
- test_strategy_signals.py
- compilerOptions
- KillSwitchDemo
- AuditReporter
- test_openterminal_context.py
- Workload
- kill_switch_io
- account.py
- test_mes5m_data.py
- tests.yml
- docker-compose.yml
- MacroEconomist
- PnlHistoryWriter
- BridgeStrategistAgent
- api-deployment.yaml
- prometheus/prometheus.yml
- agents-deployment.yaml
- YieldFarmerAgent
- _FakePool
- test_research_freshness.py
- docker-compose.advisor.yml
- docker-compose.paper.yml
- test_quant_agents.py
- CCXTFeePayload
- ExclusiveConnection
- datasources/prometheus.yml
- dashboards.yml
- MeanReversion
- alghrest.yml
- test_models.py
- test_accounting_postgres.py
- test_advisory_intake.py
- test_paper_setup.py
- HedgeManager
- MarketCrashSimulator
- DashboardWebSocketClient
- TechnicalAnalyst
- tcp25Personal.ts
- is_str_object_dict
- kafka-init.sh
- alghrest
- userRisk.ts
- PaperVenue
- capability_registry.py
- PositionSizer
- tcp25-personal.test.ts
- datetime
- _hurst_exponent
- kafka-acls.sh
- advisory_massive_intake.py
- test_runtime_efficiency.py
- MockMLServer
- approver
- .run_risk_alerts_pubsub
- advisory
- test_advisory_capability_registry.py
- test_exchange_executor.py
- EvaluationPanel.tsx
- Header.tsx
- DEXArbitrageurAgent
- Any
- ProviderDiagnostics.tsx
- state
- EvaluationPanel
- importlib
- build_sandbox_adapter

## God Nodes (most connected - your core abstractions)
1. `AdvisoryStore` - 126 edges
2. `useLanguage()` - 109 edges
3. `tr()` - 105 edges
4. `Strict` - 87 edges
5. `RecoveryBlockedError` - 76 edges
6. `BaseAgent` - 72 edges
7. `Ledger` - 67 edges
8. `ExecutionStore` - 63 edges
9. `utc_instant()` - 60 edges
10. `OpenBBAdapter` - 59 edges

## Surprising Connections (you probably didn't know these)
- `test_strategy_risk_cap_and_pause_requires_explicit_resume()` --uses--> `TrendFollower`  [INFERRED]
  tests/integration/test_agent_coordination.py → src/agents/tier4_strategies/trend_follower.py
- `test_supported_spot_venues_and_identity()` --uses--> `ExchangeExecutor`  [INFERRED]
  tests/unit/test_exchange_executor.py → src/agents/tier5_execution/exchange_executor.py
- `test_real_backtest_result_contracts_round_trip()` --uses--> `BacktestEngine`  [INFERRED]
  tests/unit/test_model_contracts.py → src/backtesting/engine.py
- `test_render_failure_is_reported_without_filesystem_details()` --uses--> `ResearchJournal`  [INFERRED]
  tests/unit/test_research_brief.py → src/connectors/advisory/research_journal.py
- `test_live_ambiguous_create_is_never_retried()` --uses--> `ExchangeConnector`  [INFERRED]
  tests/unit/test_execution_adapters.py → src/connectors/exchanges/ccxt_connector.py

## Import Cycles
- None detected.

## Communities (231 total, 75 thin omitted)

### Community 0 - "asyncio"
Cohesion: 0.06
Nodes (6): BaseAgent, BaseStrategy, require_performance(), AlghrestConsumer, prices(), sample_ohlcv_data()

### Community 1 - "ResearchJournal"
Cohesion: 0.09
Nodes (17): research_brief_pdf(), create(), backup_download(), backup_preview(), backup_restore(), call(), run(), capture() (+9 more)

### Community 2 - "terminalResearch.ts"
Cohesion: 0.04
Nodes (92): ResearchAlerts(), ResearchComparison(), ResearchJournalPanel(), capture(), failure(), loadHistory(), loadWatches(), reload() (+84 more)

### Community 3 - "advisory.py"
Cohesion: 0.07
Nodes (28): AdvisoryService, journal_revision(), average_true_range(), assess_event_risk(), DataHealthPolicy, EconomicCalendar, EventRiskAssessment, EventRiskPolicy (+20 more)

### Community 4 - "userPolicy.ts"
Cohesion: 0.13
Nodes (24): requestSchema, buildObservation(), datedMicro(), exposure, instant, integerQuantity(), money, observation (+16 more)

### Community 5 - "OpenBBAdapter"
Cohesion: 0.07
Nodes (11): OpenBBAdapter, get_settings(), Settings, _make_fake_obb(), _make_endpoint(), TestFastAPIOpenBBRoutesAndMacroIntegration, TestOpenBBAdapterConfiguration, TestOpenBBCommandRunnerAndExecutionSafety (+3 more)

### Community 6 - "useLanguage"
Cohesion: 0.06
Nodes (82): AgentDetailModal(), AgentDetailModalProps, DrawdownGauge(), DrawdownGaugeProps, ExposureBar(), ExposureBarProps, fmtUsd(), HoldingsPanel() (+74 more)

### Community 7 - "ProposalApprover"
Cohesion: 0.09
Nodes (14): ProposalApprover, FeeOptimizer, OrderRouter, SlippageMinimizer, authorizations(), consume(), envelope(), FiniteConsumer (+6 more)

### Community 8 - "test_evaluation_events.py"
Cohesion: 0.07
Nodes (64): EvaluationEvent, EvaluationSimulation, EvaluationStep, EvaluationTape, _exposure_checks(), MarginCapacity, _replay(), _shared_sources() (+56 more)

### Community 9 - "TestLiveTradingPreflightGate"
Cohesion: 0.05
Nodes (23): _default_kafka_admin_factory(), enforce_live_trading_gate(), KafkaAdminProbe, LivePreflightReport, LiveTradingGateError, PreflightCheckResult, verify_account_balances(), verify_db_latency() (+15 more)

### Community 11 - "Valuation"
Cohesion: 0.10
Nodes (9): PortfolioAccountant, Deposit, PaperDeposits, MissingValuationError, Valuation, test_mark_order_precision_venue_isolation_and_staleness(), test_canonical_fingerprint_preserves_reference_but_ignores_decimal_spelling(), test_cli_dry_validation_and_apply_are_explicit_and_close_resources() (+1 more)

### Community 12 - "AdvisoryStore"
Cohesion: 0.09
Nodes (10): AdvisoryStore, AccountPlan, Watchlist, StrategyLifecycleEvent, StrategyRecord, StrategyRegistry, test_positive_risk_role_record_rejects_hidden_assignment_loss(), test_storage_watchlist_reports_and_imports_survive_reopen() (+2 more)

### Community 13 - "newsEvents.ts"
Cohesion: 0.17
Nodes (17): NewsEventsPanel(), stamp(), ageLabel(), contextRequests(), ContextSource, date, event, headline (+9 more)

### Community 14 - "Quote"
Cohesion: 0.10
Nodes (17): AssetClass, HistoricalBar, Quote, QuoteProvider, random_walk_history(), _seed_for(), _anchor(), MockCryptoProvider (+9 more)

### Community 15 - "test_tcp25_personal.py"
Cohesion: 0.10
Nodes (39): _calculate(), capacity(), plan(), rules(), status(), assess(), CapacityRequest, PersonalEvidence (+31 more)

### Community 16 - "ws.ts"
Cohesion: 0.06
Nodes (45): DummyWebSocketClient, wsClient, socket, defaultUrl, wsClient, TopicCardProps, DashboardState, WsStatus (+37 more)

### Community 18 - "BacktestEngine"
Cohesion: 0.10
Nodes (10): BacktestEngine, engine(), signals(), test_all_validation_stages_must_pass(), test_each_hard_threshold_blocks_qualification(), test_empty_trade_distribution_never_passes_monte_carlo(), test_monte_carlo_is_repeatable_and_reports_ordered_quantiles(), test_real_vectorbt_metrics_roundtrip_and_short_history_rejected() (+2 more)

### Community 19 - "package.json"
Cohesion: 0.06
Nodes (33): devDependencies, autoprefixer, postcss, tailwindcss, @types/react, @types/react-dom, typescript, vite (+25 more)

### Community 20 - "test_economic_events.py"
Cohesion: 0.17
Nodes (27): assess(), calendar(), event(), test_blackout_includes_exact_endpoints(), test_blocking_evidence_dominates_unknown_and_reason_order_is_deterministic(), test_cached_clear_report_is_blocked_when_blackout_begins(), test_calendar_freshness_exact_boundary(), test_calendar_reader_latency_cannot_reuse_cached_clear_scenarios() (+19 more)

### Community 22 - "kill_switch.py"
Cohesion: 0.06
Nodes (8): LimitCheckResult, PositionLimitChecker, send_kill_switch_alert(), send_pagerduty_alert(), send_telegram_alert(), configure_logging(), get_logger(), start_metrics_server()

### Community 23 - "profile"
Cohesion: 0.09
Nodes (50): observation(), observed_session(), test_account_guard_rejects_bypassed_model_validation_and_invalid_age_configuration(), test_account_guard_rejects_identity_or_financial_disagreement(), test_account_observation_cannot_make_future_journal_rows_current(), test_account_snapshot_is_immutable_and_position_pnl_reconciles(), test_complete_reconciled_state_reaches_existing_risk_limits(), test_corrupt_internal_model_copy_cannot_reach_risk() (+42 more)

### Community 24 - "test_advisory_briefings.py"
Cohesion: 0.09
Nodes (33): BriefingStore, Briefing, build_briefing(), verify_briefing(), api_client(), clock(), joined(), raw() (+25 more)

### Community 25 - "test_evaluation_policy.py"
Cohesion: 0.10
Nodes (51): EODPolicy, PolicyControls, TCP25Policy, tcp50_rules(), TradingWindow, test_api_policy_default_is_versioned_and_missing_evidence_is_unknown(), allowance(), assess() (+43 more)

### Community 27 - "ObservationPanel"
Cohesion: 0.05
Nodes (66): BriefingPanel(), create(), load(), loadHistory(), open(), work(), ObservationPanel(), apply() (+58 more)

### Community 28 - "test_advisory_risk.py"
Cohesion: 0.11
Nodes (51): test_api_synthetic_qualified_risk_is_wait_and_can_be_reproduced(), test_client_cannot_supply_registry_approval_or_disable_its_gate(), allowance(), config(), decision(), history(), inputs(), make_service() (+43 more)

### Community 29 - "TelegramBotManager"
Cohesion: 0.15
Nodes (4): _api(), _fmt_pct(), _fmt_status(), TelegramBotManager

### Community 30 - "test_advisory_observations.py"
Cohesion: 0.16
Nodes (21): parse_observation(), client(), packet(), raw(), store(), test_api_auth_invalid_missing_and_self_approval(), test_api_workflow_and_revision_history(), test_append_review_edit_reopen_and_legacy_rows_preserved() (+13 more)

### Community 31 - "EvaluationSession"
Cohesion: 0.10
Nodes (45): assess_user_policy(), UserPolicyAssessment, verify_user_policy_assessment(), assess_user_risk(), UserRiskRequest, fixed_clock(), make_request(), test_confirmed_flat_mes_uses_costs_and_exact_risk_budget() (+37 more)

### Community 32 - "core.ts"
Cohesion: 0.07
Nodes (43): directions, OpenTerminalContextPanel(), refresh(), TerminalDataStatus(), number(), TerminalResearchPanel(), refresh(), applyLanguage() (+35 more)

### Community 33 - "advisor.py"
Cohesion: 0.15
Nodes (33): account_plan(), catalog(), create_evaluation(), evaluation(), evaluation_policy(), evaluations(), health(), history() (+25 more)

### Community 35 - "test_telegram_and_audit.py"
Cohesion: 0.13
Nodes (7): test_alert_pubsub_ignores_subscription_messages(), test_command_responses_use_domain_state(), test_commands_handle_missing_domain_state(), test_control_commands_store_expiring_intent(), test_copy_signal_formats_prices_and_handles_transport_failure(), test_polling_advances_offset_after_handling(), test_watchdog_only_notifies_on_meaningful_status_change()

### Community 36 - "AssetClass"
Cohesion: 0.10
Nodes (14): get_history(), get_holdings_route(), get_openbb_historical(), get_openbb_providers(), get_quotes(), list_symbols(), _openbb(), _router() (+6 more)

### Community 37 - "unittest_mock"
Cohesion: 0.04
Nodes (35): health(), proposal(), risk(), client(), test_classifies_rejection_only_after_checking_execution_records(), route_approval(), test_approval_replay_after_router_restart_has_one_stable_intent(), test_configured_twap_cadence_survives_approval_routing() (+27 more)

### Community 38 - "pytest"
Cohesion: 0.24
Nodes (19): engine(), frame(), signals(), test_both_backends_have_matching_trade_and_equity_metrics(), test_drawdown_duration_counts_recovery_and_unrecovered_periods(), test_elapsed_calendar_years_and_cagr_use_timestamps_not_number_of_bars(), test_empirical_bootstrap_uses_observed_support_and_ignores_summary_estimates(), test_fees_slippage_size_and_closed_return_have_exact_cash_arithmetic() (+11 more)

### Community 39 - "test_futures_validation.py"
Cohesion: 0.10
Nodes (41): verify_walk(), walk(), paired_block_bootstrap_means(), futures_expectancy_uncertainty(), FuturesWalkPlan, FuturesWalkStudy, verify_futures_walk(), walk_forward_futures() (+33 more)

### Community 40 - "test_path_risk.py"
Cohesion: 0.14
Nodes (33): iid_loss_run_probability(), loss_streak_analysis(), LossStreakStudy, observed_result(), brute_probability(), config(), longest(), test_absorbing_recurrence_matches_exhaustive_sequence_enumeration() (+25 more)

### Community 43 - "request"
Cohesion: 0.09
Nodes (49): futures_edge_analysis(), FuturesResearchInput, run_futures_research(), configuration(), metrics(), observations(), research_input(), test_adjusted_skew_matches_independent_float_moment_formula() (+41 more)

### Community 44 - "test_market_selection.py"
Cohesion: 0.17
Nodes (33): test_reported_historical_labels_are_metadata_not_authenticated_validation(), test_missing_book_side_is_not_assumed_zero_entry_deviation(), candidate(), context(), edge(), fit(), policy(), select() (+25 more)

### Community 45 - "StateManager"
Cohesion: 0.11
Nodes (10): operate(), StateManager, test_snapshot_cache_is_recreatable_and_short_lived(), test_trade_gate_requires_fresh_matching_revision_and_book(), test_portfolio_publication_and_invalidation_are_book_local(), test_health_roundtrip_expiry_and_missing_records(), test_initialize_and_shutdown_release_connections(), test_kill_switch_reason_and_atomic_dedup() (+2 more)

### Community 46 - "App.tsx"
Cohesion: 0.12
Nodes (25): Agents, App(), AuditorDashboard, BacktestSimulation, InvestorPitch, Kafka, ManualAssistant, Overview (+17 more)

### Community 47 - "MarketDataPanel.tsx"
Cohesion: 0.08
Nodes (45): ASSET_HINT, BrokerGroup, BrokerSection(), EnrichedHolding, fmtPct(), fmtUsd(), PnlText(), priceFmt() (+37 more)

### Community 48 - "strategy_signals.py"
Cohesion: 0.18
Nodes (9): atr_trailing_step(), ATRTradeStep, close_crossed_stop(), _decimal_price(), DirectionalKernel, _entry_levels(), PriceBar, _trailing_step() (+1 more)

### Community 49 - "pydantic"
Cohesion: 0.06
Nodes (46): AccountState, risk_worksheet(), evaluation_plan(), evaluation_risk_blocks(), evaluation_status(), EvaluationPlan, EvaluationProfile, EvaluationSession (+38 more)

### Community 50 - "research_pdf.py"
Cohesion: 0.06
Nodes (37): ArabicText, _font(), _headlines(), render_research_pdf(), _render_research_pdf(), heading(), page(), text() (+29 more)

### Community 53 - "validation.py"
Cohesion: 0.11
Nodes (21): _uncertainty(), uncertainty_analysis(), verify_edge(), verify_uncertainty(), futures_dataset_digest(), FuturesEdgeStudy, _sha(), strategy_source_digest() (+13 more)

### Community 54 - "RiskEngine"
Cohesion: 0.15
Nodes (3): RiskEngine, test_diversification_and_concentration_aggregate_venues(), test_var_cvar_and_ratios_against_independent_calculations()

### Community 55 - "TrendFollower"
Cohesion: 0.15
Nodes (3): TrendFollower, test_halted_strategy_never_evaluates_incoming_prices(), test_tier2_envelope_is_consumed_by_real_strategy()

### Community 56 - "advisory_firstrate_intake.py"
Cohesion: 0.21
Nodes (6): _ArgumentParser, _identity(), _normalize(), flush(), _number(), _opened()

### Community 57 - "test_advisory_context.py"
Cohesion: 0.07
Nodes (30): api_client(), events(), news(), clock(), ics(), rss(), source(), test_ambiguous_nonexistent_or_unspecified_zone_is_not_invented() (+22 more)

### Community 58 - "test_model_contracts.py"
Cohesion: 0.12
Nodes (8): proposal_data(), test_approval_and_routing_preserve_contract(), test_confidence_must_be_a_probability(), test_legacy_proposal_cannot_silently_supply_missing_contract(), test_ml_producer_emits_its_actual_confidence(), test_order_book_price_publisher_contract(), test_real_backtest_result_contracts_round_trip(), test_seeded_runtime_payloads_parse_without_contacts()

### Community 59 - "core/advisory/openterminal_research.py"
Cohesion: 0.09
Nodes (23): collect_terminal_context(), _number(), parse_headlines(), parse_quote(), _read(), collect_terminal_research(), parse_candles(), _stamp() (+15 more)

### Community 60 - "test_advisory_api.py"
Cohesion: 0.07
Nodes (20): test_service_roles_hold_with_other_financial_gates_ready(), client(), test_api_account_role_snapshot_and_forbidden_assignment_inputs(), test_api_evaluation_persists_and_never_invents_a_profile(), test_api_monthly_contract_import_persists_without_execution(), test_api_persists_blocked_health_and_cannot_override_it(), test_api_policy_timeout_and_corruption_are_explicit(), test_api_profile_selects_policy_without_creating_accounts() (+12 more)

### Community 61 - "test_monitoring_contracts.py"
Cohesion: 0.14
Nodes (4): AuditorAgent, collector(), test_audit_demo_is_labelled_and_never_halts_trading(), test_auditor_refuses_synthetic_validation_outside_development()

### Community 62 - "openbb_adapter.py"
Cohesion: 0.08
Nodes (7): _extract_records(), MacroObservation, normalize_provider_symbol(), _normalize_timestamp_utc(), OpenBBDataValidationError, OpenBBProviderError, _to_finite_decimal()

### Community 63 - "test_strategy_registry.py"
Cohesion: 0.08
Nodes (33): FuturesWalkWindow, _approval_reasons(), assess_strategy_approval(), _digest(), ResearchPartition, StrategyApprovalCheck, StrategyDefinition, StrategyResearchPlan (+25 more)

### Community 64 - "build_report"
Cohesion: 0.07
Nodes (65): relevant(), ReplayProvider, build_report(), assess_market_data(), result(), MarketDataHealth, test_report_features_are_identical_for_equivalent_clock_offsets(), market() (+57 more)

### Community 65 - "briefing.py"
Cohesion: 0.13
Nodes (16): _collect_context(), context(), collect_context(), guarded_briefing_save(), BriefingInputs, BriefingResult, BriefModel, Capability (+8 more)

### Community 66 - "test_writer_lease.py"
Cohesion: 0.07
Nodes (5): CircuitState, DatabaseCircuitBreaker, ExponentialBackoffPolicy, test_circuit_breaker_transitions_closed_open_half_open_closed(), test_exponential_backoff_retries_transient_errors_and_trips_breaker()

### Community 67 - "utcnow"
Cohesion: 0.10
Nodes (28): _call(), run(), create(), edit(), history(), read(), review(), validate() (+20 more)

### Community 68 - "briefing_store.py"
Cohesion: 0.09
Nodes (14): create(), history(), read(), _workflow(), BriefingSaveOutcomeError, BriefingWorkflow, _consume_save_result(), BriefingConflictError (+6 more)

### Community 69 - "test_account_profiles.py"
Cohesion: 0.15
Nodes (18): configuration(), plan(), role_check(), store_with_plan_sources(), test_corrupted_stored_plan_or_missing_bound_journal_never_falls_back(), test_final_risk_role_gate_cannot_increase_size_or_borrow_an_account(), test_initial_roles_are_explicit_distinct_and_never_trade_permission(), test_invalid_role_topology_and_forged_positive_results_are_rejected() (+10 more)

### Community 70 - "test_portfolio_tracker.py"
Cohesion: 0.14
Nodes (14): PortfolioTracker, portfolio(), with_performance(), test_daily_report_uses_actual_portfolio_and_tracker(), sample(), test_funding_does_not_change_drawdown_or_daily_returns(), test_gap_does_not_become_a_daily_return(), test_metrics_sample_threshold_and_calendar_sharpe() (+6 more)

### Community 71 - "mock_ml_server.py"
Cohesion: 0.16
Nodes (8): sources(), _generate_mock_prediction(), health_check(), predict(), PredictionRequest, PredictionResponse, root(), set_server_mode()

### Community 72 - "futures.py"
Cohesion: 0.09
Nodes (32): CensoredFuturesPosition, _drawdown_path(), DrawdownRecovery, _edge_partitions(), _edge(), edge_analysis(), research(), verify_run() (+24 more)

### Community 73 - "test_advisory_firstrate_intake.py"
Cohesion: 0.20
Nodes (26): inspect_firstrate(), main(), assert_closed(), fixture(), inspect(), query(), test_all_incomplete_rows_and_gaps_remain_visible_without_filling(), test_all_rows_checked_after_selection_and_maximum_window_is_reported() (+18 more)

### Community 74 - "test_openterminal_research.py"
Cohesion: 0.13
Nodes (23): analyze_candles(), bars(), clocks(), collect(), transport(), history_envelope(), quote(), test_arbitrary_urls_path_traversal_or_multi_symbol_requests_are_refused() (+15 more)

### Community 75 - "test_risk_engine.py"
Cohesion: 0.16
Nodes (8): _portfolio(), _proposal(), test_drawdown_correct_when_below_baseline(), test_drawdown_zero_when_capital_above_baseline(), test_position_limit_approves_small_proposal(), test_position_limit_rejects_oversized_single_asset(), test_var_positive_for_long_history(), test_var_zero_for_short_history()

### Community 76 - "re"
Cohesion: 0.07
Nodes (21): extract_agent_ids_from_code(), extract_docker_ports_and_ips(), validate_agent_ids(), CalendarCache, _eastern(), _entry(), _ics(), Node (+13 more)

### Community 77 - "json"
Cohesion: 0.21
Nodes (24): inspect_massive(), main(), arguments(), assert_closed(), convert(), fixture(), inspected(), test_bad_or_oversized_json_is_rejected() (+16 more)

### Community 78 - "DashboardWebSocketManager"
Cohesion: 0.18
Nodes (3): DashboardWebSocketManager, test_broadcast_survives_connections_changing_during_send(), test_display_loops_wait_for_viewer_then_resume_and_cancel_cleanly()

### Community 79 - "time"
Cohesion: 0.25
Nodes (4): main(), print_results(), test_feed(), validate_all_feeds()

### Community 80 - "main.py"
Cohesion: 0.07
Nodes (19): ConnectionManager, get_agent_health(), get_all_agents(), get_kill_switch_status(), get_macro_regime(), get_portfolio(), get_positions(), get_risk_metrics() (+11 more)

### Community 81 - "train.py"
Cohesion: 0.07
Nodes (8): predict(), PredictionRequest, PredictionResponse, CandlestickCNN, PositionSizingEnv, MLDataLoader, train_cnn(), train_rl_agent()

### Community 82 - "RiskGovernor"
Cohesion: 0.11
Nodes (6): RiskGovernor, test_governor_absent_state_leverage_and_concentration(), test_governor_cancels_sibling_loops_when_consumer_fails(), test_governor_thresholds_and_kill_switch_latch(), test_governor_uses_durable_index_and_ignores_legacy_redis_baselines(), test_weekly_halt_persists_before_event_delivery()

### Community 83 - "message_bus.py"
Cohesion: 0.05
Nodes (19): aiokafka_security(), confluent_security(), KafkaRoleACL, scram_jaas_config(), AlghrestProducer, _deserialize(), _serialize(), test_real_broker_rejects_anonymous_and_wrong_key_allows_authenticated_bus() (+11 more)

### Community 84 - "test_architecture.py"
Cohesion: 0.10
Nodes (19): main(), references(), qualified(), violations(), source_tree(), test_advisory_boundary_prevents_trading_state_access(), test_advisory_rejects_aliased_producer_capabilities(), test_advisory_rejects_dynamic_execution_imports() (+11 more)

### Community 85 - "test_accounting_pipeline.py"
Cohesion: 0.18
Nodes (15): accountant(), test_accounting_marks_do_not_merge_venues_or_refresh_old_price_time(), test_cache_expires_quickly_if_process_dies(), test_connector_does_not_silently_drop_an_unbookable_fill(), test_connector_preserves_stable_identity_and_all_fees(), test_empty_ccxt_fee_list_does_not_discard_known_primary_fee(), test_failed_writer_claim_does_not_clear_another_accountants_cache(), test_fill_accounting_continues_while_trading_is_halted() (+7 more)

### Community 86 - "MarketSnapshot"
Cohesion: 0.05
Nodes (22): PaperMarketFeed, AdvisoryMarketData, PublicMarkets, bounded_snapshot(), MarketDataProvider, MarketDataQuery, CSVImport, Candle (+14 more)

### Community 87 - "test_research_backup.py"
Cohesion: 0.11
Nodes (21): main(), run(), sample(), main(), export_research(), restore_research(), backup_checksum(), BackupRecord (+13 more)

### Community 88 - "test_execution_adapters.py"
Cohesion: 0.14
Nodes (20): adapter(), order(), test_adapter_passes_stable_submission_id_and_cancel_failure_is_not_success(), test_ambiguous_lookup_requires_matching_client_id(), test_binance_single_timestamp_saturation_or_outside_window_blocks(), test_binance_subdivides_saturated_window_without_advancing_past_timestamp_ties(), test_coinbase_client_lookup_paginates_closed_history(), test_kraken_counts_unfiltered_account_history_and_preserves_other_symbols() (+12 more)

### Community 89 - ".redis"
Cohesion: 0.17
Nodes (4): test_legacy_subscribers_cannot_receive_private_broadcasts(), halt_control(), test_configured_admin_can_control_from_private_chat(), test_untrusted_control_command_cannot_change_state()

### Community 90 - "ExchangeExecutor"
Cohesion: 0.17
Nodes (5): ExchangeExecutor, handle(), test_foreign_or_unscoped_order_cannot_touch_execution_store(), test_malformed_delivery_does_not_stop_order_consumer(), test_kill_events_fence_risk_then_recover_durable_orders()

### Community 92 - "test_advisory_capabilities.py"
Cohesion: 0.13
Nodes (16): OrderExecutionDisabledError, InertAgent, test_agent_publish_denied_even_with_replaced_producer(), test_agent_start_denied_before_any_initialization(), test_direct_broker_mutation_denied_on_existing_client(), test_exchange_connection_denied_before_credentials_or_network(), test_executor_denied_before_store_or_venue_contact(), test_launcher_denies_before_subprocess_start() (+8 more)

### Community 93 - "compilerOptions"
Cohesion: 0.10
Nodes (20): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleResolution (+12 more)

### Community 94 - "test_execution_recovery.py"
Cohesion: 0.06
Nodes (48): ApprovalStore, AuthorizationError, digest(), validate_authorization(), TwapScheduler, RiskHaltStore, authorized_order(), approve() (+40 more)

### Community 96 - "news_analyst.py"
Cohesion: 0.07
Nodes (15): CIOAgent, BudgetUnavailableError, estimate_cost(), reserve(), CacheControl, cached_system(), CachedTextBlock, test_daily_budget_concurrent_restart_and_dollar_limits() (+7 more)

### Community 100 - "json"
Cohesion: 0.04
Nodes (41): main(), main(), run(), configure(), _ensure_tls_artifacts(), main(), atomic_json(), child_env() (+33 more)

### Community 101 - "demo_messages"
Cohesion: 0.14
Nodes (4): lifespan(), MockDashboardManager, websocket_dashboard(), demo_messages()

### Community 102 - "RecoveryBlockedError"
Cohesion: 0.06
Nodes (24): run(), migrate(), preflight(), provision(), block(), FillConflictError, Ledger, OrderConflictError (+16 more)

### Community 103 - "KillSwitchStressTester"
Cohesion: 0.11
Nodes (3): KillSwitchStressTester, mock_close_positions(), main()

### Community 104 - "test_price_publisher.py"
Cohesion: 0.29
Nodes (11): _build_publisher(), _ohlcv_payload(), _orderbook_payload(), test_h4_ohlcv_is_skipped(), test_invalid_ohlcv_payload_silently_dropped(), test_m1_ohlcv_writes_to_redis(), test_ohlcv_then_orderbook_merges_fields(), test_orderbook_with_no_levels_skipped() (+3 more)

### Community 106 - "openterminal-service.mjs"
Cohesion: 0.06
Nodes (53): checkPlan(), delay(), main(), command(), json(), ready(), response(), start() (+45 more)

### Community 107 - "test_intelligence_agents.py"
Cohesion: 0.18
Nodes (3): MarketDataHub, test_market_data_normalization_rejects_bad_candles(), test_orderbook_normalization_caps_depth_and_rejects_malformed()

### Community 108 - "test_api_dashboard_integration.py"
Cohesion: 0.12
Nodes (3): test_history_is_deterministic_ordered_and_valid(), test_history_rejects_unknown_symbols_and_invalid_windows(), test_lifespan_cancels_and_awaits_background_tasks()

### Community 109 - "test_prompt_caching.py"
Cohesion: 0.19
Nodes (7): _fake_response(), test_cio_passes_cache_control_in_system_prompt(), test_cio_records_cache_read_when_response_has_cache_hit(), test_cio_system_prompt_meets_caching_minimum_for_opus(), test_news_analyst_passes_cache_control_in_system_prompt(), test_news_classifier_system_meets_caching_minimum_for_sonnet(), test_news_records_cache_create_then_read()

### Community 111 - "test_trade_management.py"
Cohesion: 0.18
Nodes (17): management(), test_actual_agent_indicator_bridge_uses_pinned_atr_and_preserves_input_frame(), test_agent_entry_and_stop_ratchet_match_shared_plan(), test_entry_geometry_precedes_size_and_has_no_execution_or_quantity(), test_exit_checks_existing_stop_first_and_touch_preserves_legacy_strict_comparison(), test_geometry_is_symmetric_and_ratchet_monotone_without_quantity_or_global_precision(), test_independent_hand_calculation_pins_seed_and_recursive_updates(), test_invalid_atr_input_cannot_produce_geometry() (+9 more)

### Community 112 - "BookState"
Cohesion: 0.06
Nodes (30): BrokerConformanceSuite, ConformanceReport, apply_fill(), fees(), fingerprint(), identity(), DepositReceipt, BookState (+22 more)

### Community 113 - "dependencies"
Cohesion: 0.12
Nodes (17): dependencies, class-variance-authority, clsx, lucide-react, @radix-ui/react-collapsible, @radix-ui/react-dialog, @radix-ui/react-tabs, @radix-ui/react-toast (+9 more)

### Community 114 - "OpenBBIngestionPipeline"
Cohesion: 0.09
Nodes (3): _ensure_utc(), IngestionSummary, OpenBBIngestionPipeline

### Community 119 - "mes5m_data.py"
Cohesion: 0.05
Nodes (51): main(), _Parser, _unique(), _cut(), development_snapshot(), DevelopmentSlice, FiveMinuteNormalizer, MissingInterval (+43 more)

### Community 120 - ".lock"
Cohesion: 0.29
Nodes (3): test_domain_snapshots_roundtrip_and_reject_corruption(), test_lock_releases_on_failure_and_fails_if_contended(), test_trading_gate_requires_matching_fresh_evidence()

### Community 121 - "test_research_quality.py"
Cohesion: 0.22
Nodes (15): collect(), transport(), series(), test_clean_continuous_series_has_supporting_counts_and_keeps_freshness_unknown(), test_continuous_irregular_timestamp_spacing_blocks_affected_windows(), test_contradictory_quality_or_exposed_blocked_metrics_are_rejected(), test_defects_expose_counts_without_sorting_or_repair_and_keep_other_feeds(), test_fetch_clock_cannot_precede_a_returned_candle() (+7 more)

### Community 122 - "test_funding_postgres.py"
Cohesion: 0.26
Nodes (17): persist_snapshot(), deposit(), make_ready(), order(), test_cache_failure_after_commit_keeps_receipt_and_durable_gate(), test_concurrent_distinct_deposits_add_without_lost_update(), test_concurrent_duplicate_receipts_and_conflicting_reference(), test_dry_run_then_atomic_cash_and_performance_with_no_pnl() (+9 more)

### Community 124 - "CopyTradingAgent"
Cohesion: 0.18
Nodes (4): CopyTradingAgent, TelegramBroadcaster, test_copy_trading_rejects_malformed_and_halted_messages(), test_copy_trading_uses_actual_price_and_filters_unusable_proposals()

### Community 127 - "advisory/models.py"
Cohesion: 0.07
Nodes (20): breakout_research_check(), ema(), EODProjection, FuturesSpec, Instrument, Report, Scenario, StrategyResearchCheck (+12 more)

### Community 128 - "test_research_monitor.py"
Cohesion: 0.12
Nodes (19): append_json(), health(), main(), reading(), run(), collect(), sample_gap(), source_manifest() (+11 more)

### Community 130 - "test_durable_fill_survives_real_kafka_consumer_restart"
Cohesion: 0.10
Nodes (12): fetch_live_account_balances(), _has_exchange_credentials(), main(), run_preflight(), RecoveryCoordinator, TestKillSwitchPerformance, test_durable_fill_survives_real_kafka_consumer_restart(), crash_after_commit() (+4 more)

### Community 131 - "test_research_journal.py"
Cohesion: 0.13
Nodes (16): client(), journal(), report(), snapshot(), test_bounded_overview_history_preserves_full_history(), test_capture_refuses_wrong_provider_symbol(), test_capture_uses_server_data_retry_and_history_api(), test_concurrent_retries_have_one_durable_result() (+8 more)

### Community 132 - "test_strategy_behavior.py"
Cohesion: 0.14
Nodes (23): bar(), position(), candle_window(), test_defi_skeletons_never_emit_orders_or_pass_backtests(), test_macro_reads_nested_signals_and_real_price_cache(), test_mean_reversion_evaluation_respects_bands_and_hurst(), test_mean_reversion_open_close_and_loss_tracking(), test_momentum_position_sizing_and_exit() (+15 more)

### Community 133 - "test_access_security.py"
Cohesion: 0.16
Nodes (5): test_advisory_write_intent_header_cannot_replace_authentication(), test_all_real_ws_routes_reject_before_acceptance_or_state_access(), test_browser_handshake_authorized_control(), test_http_auth_fail_closed_and_separate_keys(), test_private_reads_and_subscriptions_reject_non_admin()

### Community 135 - "httpx"
Cohesion: 0.08
Nodes (19): research_diagnostics(), terminal_context(), terminal_research(), collect_diagnostics(), valid_symbol(), DiagnosticResult, ProviderClock, ProviderObservation (+11 more)

### Community 137 - "LifecycleAgent"
Cohesion: 0.14
Nodes (5): agent(), LifecycleAgent, test_cancelled_agent_closes_resources_even_if_custom_shutdown_fails(), test_run_failure_cancels_heartbeat_before_closing_connections(), test_strategy_risk_cap_and_pause_requires_explicit_resume()

### Community 139 - "performance.py"
Cohesion: 0.23
Nodes (7): load(), observe(), PerformanceUnavailableError, save(), snapshot(), test_legacy_history_clock_reversal_and_foreign_history_are_not_reset(), test_restart_and_period_rollovers_keep_last_close_reference()

### Community 140 - "test_strategy_signals.py"
Cohesion: 0.16
Nodes (26): VolumeBreakoutKernel, clear_event_context(), daily_market(), parameters(), prices(), research(), test_agent_entry_uses_the_shared_kernel_without_sizing_in_it(), test_copied_positive_experiment_cannot_keep_guards_after_source_changes() (+18 more)

### Community 141 - "compilerOptions"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include

### Community 144 - "test_openterminal_context.py"
Cohesion: 0.24
Nodes (13): collect(), transport(), headlines(), quote(), test_empty_news_does_not_clear_events_and_duplicates_are_collapsed(), test_endpoint_retains_existing_authentication_and_no_store(), test_envelope_rejects_identity_changes_and_execution_flags(), test_failed_or_redirected_sources_remain_unknown() (+5 more)

### Community 145 - "Workload"
Cohesion: 0.15
Nodes (8): compose(), run(), TransientProposalRejectionError, Workload, test_bounded_transient_retry_is_reported(), test_foreign_review_never_authorizes_retry(), test_timeout_identifies_proposal_and_is_not_retried(), worker()

### Community 146 - "kill_switch_io"
Cohesion: 0.25
Nodes (4): crash_simulator(), kill_switch_io(), mock_open_orders(), mock_portfolio_with_positions()

### Community 147 - "account.py"
Cohesion: 0.14
Nodes (11): account_state(), AccountBinding, AccountConfiguration, AccountObservation, AccountRoleCheck, assess_account_role(), _Evidence, OpenPosition (+3 more)

### Community 148 - "test_mes5m_data.py"
Cohesion: 0.29
Nodes (13): fixture(), snapshot(), test_cut_must_be_aware_and_inside_development_window(), test_dst_ambiguous_and_nonexistent_timestamps_are_rejected(), test_duplicate_source_timestamps_rejected_without_sorting(), test_excluded_day_and_asof_future_ohlcv_are_never_decoded(), test_missing_minute_is_explicit_and_not_a_zero_volume_candle(), test_partition_and_asof_isolation_precede_ohlcv_parsing() (+5 more)

### Community 149 - "tests.yml"
Cohesion: 0.33
Nodes (5): permissions, jobs, name, env, on

### Community 150 - "docker-compose.yml"
Cohesion: 0.33
Nodes (5): volumes, name, x-runtime-environment, networks, services

### Community 154 - "api-deployment.yaml"
Cohesion: 0.40
Nodes (4): kind, apiVersion, metadata, spec

### Community 155 - "prometheus/prometheus.yml"
Cohesion: 0.40
Nodes (4): scrape_configs, alerting, global, rule_files

### Community 156 - "agents-deployment.yaml"
Cohesion: 0.40
Nodes (4): kind, apiVersion, metadata, spec

### Community 158 - "_FakePool"
Cohesion: 0.13
Nodes (3): _FakeConn, _FakePool, _FakeTx

### Community 159 - "test_research_freshness.py"
Cohesion: 0.29
Nodes (7): quote_freshness(), report(), test_adapter_assumption_and_legacy_snapshots_cannot_become_provider_reports(), test_display_threshold_does_not_certify_realtime_or_source_latency(), test_provider_state_is_reported_without_inventing_a_calendar(), test_stale_cache_and_old_session_declarations_cannot_describe_current_session(), test_unknown_price_clock_cannot_become_fresh_because_the_source_was_just_fetched()

### Community 160 - "docker-compose.advisor.yml"
Cohesion: 0.50
Nodes (3): volumes, name, services

### Community 161 - "docker-compose.paper.yml"
Cohesion: 0.50
Nodes (3): volumes, name, services

### Community 162 - "test_quant_agents.py"
Cohesion: 0.12
Nodes (10): FiniteConsumer, test_alerts_continue_while_halted_and_escalate_only_critical(), test_correlation_daily_ingestion_replaces_same_day_and_filters(), test_garch_forecast_converts_variance_and_handles_failure(), test_indicator_extremes_and_crossovers(), test_no_signal_for_missing_nan_or_neutral_values(), test_technical_stream_filters_and_deduplicates_bars(), test_volatility_direction() (+2 more)

### Community 163 - "CCXTFeePayload"
Cohesion: 0.24
Nodes (3): CCXTFeePayload, CCXTOrderPayload, CCXTTradePayload

### Community 164 - "ExclusiveConnection"
Cohesion: 0.24
Nodes (3): ExclusiveConnection, test_ensure_writer_automatically_recovers_dropped_session_lease(), release()

### Community 174 - "test_models.py"
Cohesion: 0.26
Nodes (7): test_fill_uses_fill_size_fill_price(), test_kafka_topic_enum_includes_new_pipeline_topics(), test_ohlcv_bar_uses_time_field(), test_order_uses_size_not_quantity(), test_position_sizing_result_full_schema(), test_signal_direction_enum_does_not_have_long_short(), test_trade_proposal_uses_correct_field_names()

### Community 175 - "test_accounting_postgres.py"
Cohesion: 0.21
Nodes (13): fill(), test_concurrent_duplicates_and_reconnect(), test_conflicting_identity_and_reseed_cannot_change_book(), test_cutoff_accounts_for_replay_without_booking_opening_twice(), test_distinct_concurrent_partial_fills_are_not_lost(), test_failure_after_database_commit_before_kafka_ack_replays_safely(), __aiter__(), test_failure_after_journal_insert_rolls_back_everything() (+5 more)

### Community 176 - "test_advisory_intake.py"
Cohesion: 0.29
Nodes (18): inspect_snapshot(), main(), arguments(), assert_abstains(), inspect(), query(), snapshot(), test_bad_structures_and_injected_permission_are_rejected() (+10 more)

### Community 185 - "test_paper_setup.py"
Cohesion: 0.39
Nodes (4): validate(), manifests(), test_dry_run_never_connects_or_invents_opening_cash(), test_preparation_requires_explicit_paper_environment()

### Community 191 - "tcp25Personal.ts"
Cohesion: 0.11
Nodes (18): accountSchema, accountState, capSchema, common, CurrentResult, envelope, instant, money (+10 more)

### Community 193 - "is_str_object_dict"
Cohesion: 0.21
Nodes (4): is_dict_list(), is_str_object_dict(), _require_list_response(), test_ccxt_type_guards_and_disconnected_client_rejection()

### Community 194 - "kafka-init.sh"
Cohesion: 0.83
Nodes (3): create_topic(), kafka-init.sh script, wait_for_kafka()

### Community 200 - "userRisk.ts"
Cohesion: 0.13
Nodes (19): Snapshot, decimalIdentity(), instant, money, nonnegative, personalRiskCurrent(), personalRiskRequest(), PersonalSnapshot (+11 more)

### Community 201 - "PaperVenue"
Cohesion: 0.09
Nodes (5): PaperVenue, SpotRecoveryAdapter, currencies(), TradePage, history()

### Community 203 - "capability_registry.py"
Cohesion: 0.13
Nodes (10): capabilities(), normalize(), capability_registry(), CapabilityDefinition, CapabilityRegistry, _source_hashes(), verify_capability_registry(), utcnow() (+2 more)

### Community 207 - "tcp25-personal.test.ts"
Cohesion: 0.16
Nodes (19): check(), checked(), freshAccount(), identity(), join(), personalRequest(), personalRiskCurrent(), personalRiskRequest() (+11 more)

### Community 208 - "datetime"
Cohesion: 0.05
Nodes (8): key(), AccountScope, balance_differences(), InstrumentRules, native_balances(), DatabaseCircuitOpenError, is_transient_db_error(), halted()

### Community 212 - "kafka-acls.sh"
Cohesion: 0.60
Nodes (5): deny_write_topics(), grant_read_topics(), grant_write_topics(), provision_scram_user(), kafka-acls.sh script

### Community 213 - "advisory_massive_intake.py"
Cohesion: 0.18
Nodes (8): _clock(), _unique_keys(), _ArgumentParser, _contract(), _date(), _invalid_constant(), normalize_massive(), _response()

### Community 214 - "test_runtime_efficiency.py"
Cohesion: 0.15
Nodes (17): commands(), contains_live_services(), main(), test_read_only_launch_plan_remains_available(), test_trading_api_denied_before_redis_background_tasks_or_telegram(), feed(), test_cached_news_still_expires_by_publication_age(), test_cancelled_feed_refresh_can_retry_and_oversize_is_not_cached_as_success() (+9 more)

### Community 219 - "test_advisory_capability_registry.py"
Cohesion: 0.14
Nodes (6): source_copy(), test_altered_definitions_or_confirmed_hypotheses_remain_insufficient(), test_constructed_or_serialized_permission_flags_cannot_unlock_registry(), test_missing_inconsistent_source_evidence_is_rejected(), test_missing_unmapped_or_redirected_source_cannot_yield_a_registry(), test_runtime_readiness_and_probability_cannot_be_inferred()

### Community 220 - "test_exchange_executor.py"
Cohesion: 0.26
Nodes (14): executor(), order(), test_algo_parents_are_not_submitted(), test_disconnect_after_prepare_before_venue_place_aborts_unattempted(), test_disconnect_during_observe_flushes_on_recovery_without_duplicate_venue_place(), test_disconnect_during_prepare_aborts_unattempted_and_never_calls_venue(), test_durable_gate_closes_between_cache_check_and_claim(), test_history_polling_continues_during_halt() (+6 more)

### Community 221 - "EvaluationPanel.tsx"
Cohesion: 0.19
Nodes (12): blank, Evaluation, labels, Profile, reasons, UserPolicyPanel(), resultCurrent, TCP25Capacity (+4 more)

### Community 222 - "Header.tsx"
Cohesion: 0.09
Nodes (27): ResearchBackup(), download(), restore(), select(), ResearchBriefExport(), generate(), AccessGate(), connect() (+19 more)

### Community 225 - "Any"
Cohesion: 0.14
Nodes (3): _CommandRunnerOBBClient, _get_default_obb_client(), _RouteNamespace

### Community 226 - "ProviderDiagnostics.tsx"
Cohesion: 0.21
Nodes (10): ProviderDiagnostics(), clock, diagnosticClock, diagnosticFailure, DiagnosticResult, observation, provider, researchDiagnostics() (+2 more)

### Community 228 - "EvaluationPanel"
Cohesion: 0.38
Nodes (11): EvaluationPanel(), accept(), create(), dirty(), load(), readStatus(), save(), updateOrder() (+3 more)

### Community 229 - "importlib"
Cohesion: 0.29
Nodes (4): test_agent_class_imports(), test_position_sizer_constructs(), test_proposal_approver_imports(), test_strategy_class_implements_abstract_interface()

### Community 230 - "build_sandbox_adapter"
Cohesion: 0.26
Nodes (5): build_sandbox_adapter(), _scope(), test_external_sandbox_duplicate_flatten_and_client_id_idempotency(), test_external_sandbox_flatten_safety_gates(), test_external_sandbox_twap_and_flatten_matches_synthetic_book()

## Knowledge Gaps
- **13 isolated node(s):** `@radix-ui/react-collapsible`, `@radix-ui/react-tabs`, `@radix-ui/react-toast`, `class-variance-authority`, `socket.io-client` (+8 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 1876 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **75 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BaseAgent` connect `asyncio` to `.__init__`, `ProposalApprover`, `.publish`, `Valuation`, `VolatilityForecaster`, `kill_switch.py`, `MacroEconomist`, `HedgeManager`, `TechnicalAnalyst`, `test_monitoring_contracts.py`, `test_portfolio_tracker.py`, `datetime`, `RiskGovernor`, `message_bus.py`, `MarketSnapshot`, `ExchangeExecutor`, `news_analyst.py`, `SentimentAnalyst`, `CorrelationEngine`, `AlertManager`, `GeopoliticalWatcher`, `test_intelligence_agents.py`, `KillSwitch`, `NewsAnalyst`, `OnChainSleuth`, `ComplianceAgent`, `CopyTradingAgent`, `PricePublisher`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 79 inferred relationships involving `AdvisoryStore` (e.g. with `run()` and `main()`) actually correct?**
  _`AdvisoryStore` has 79 INFERRED edges - model-reasoned connections that need verification._
- **What connects `@radix-ui/react-collapsible`, `@radix-ui/react-tabs`, `@radix-ui/react-toast` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `asyncio` be split into smaller, more focused modules?**
  _Cohesion score 0.05833848690991548 - nodes in this community are weakly interconnected._
- **Why does `OpenBBAdapter` connect `OpenBBAdapter` to `asyncio`, `Any`, `AssetClass`, `Quote`, `OpenBBIngestionPipeline`, `MarketSnapshot`, `MacroEconomist`, `core/advisory/openterminal_research.py`, `openbb_adapter.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Should `ResearchJournal` be split into smaller, more focused modules?**
  _Cohesion score 0.09224489795918367 - nodes in this community are weakly interconnected._
- **Why does `Ledger` connect `RecoveryBlockedError` to `test_durable_fill_survives_real_kafka_consumer_restart`, `test_writer_lease.py`, `json`, `test_funding_postgres.py`, `ProposalApprover`, `TestLiveTradingPreflightGate`, `Valuation`, `test_accounting_postgres.py`, `datetime`, `Workload`, `BookState`, `test_accounting_pipeline.py`, `test_paper_setup.py`, `ExchangeExecutor`, `test_execution_recovery.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
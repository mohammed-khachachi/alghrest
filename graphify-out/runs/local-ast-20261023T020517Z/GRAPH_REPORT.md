# Graph Report - alghrest-main  (2026-10-23)

## Corpus Check
- 410 files · ~295,463 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 5569 nodes · 17598 edges · 185 communities (141 shown, 44 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 2220 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Trading Messages and Agents
- Advisory Research Contracts
- Research Journal Interface
- Advisory Reports and Clocks
- Personal Evaluation Interface
- Market Data Quality Tests
- Dashboard Charts and Translation
- Proposal Approval and Execution
- Evaluation Event Simulation
- Advisory Service and Risk
- Strategy and DeFi Configuration
- Durable Execution Recovery
- Advisory Persistence and Strategies
- Application State and Localization
- Dashboard Market Data Providers
- Personal TCP25 Assessment
- Dashboard WebSocket State
- ML Strategy and Failover
- Backtest Validation Engine
- Dashboard Routing and Build
- Research Data Provenance
- Quantitative Signals and Volatility
- OHLCV Strategy Implementations
- Evaluation Account Tests
- Observation Storage and Briefings
- Evaluation Policy Tests
- Kafka Messaging Infrastructure
- Observation and Briefing Interface
- Advisory Risk Tests
- Telegram Messaging and Access
- Briefing Persistence Tests
- User Policy and Briefings
- User Policy Risk Tests
- Advisory HTTP API
- HTTP Clients and Utilities
- Dashboard API Integration Tests
- Research Terminal Localization
- PostgreSQL Accounting Tests
- Funding and Portfolio Valuation
- Futures Validation Tests
- Path Risk Analysis Tests
- Exchange Adapter Contracts
- Fill Accounting and Persistence
- Futures Research Tests
- Market Selection Tests
- Redis State and Gates
- Access and Backup Interface
- Market Quotes Interface
- Futures Research Engine
- Trade Management Tests
- Research Document Rendering
- Kill Switch Integration
- Macro Strategy Intelligence
- Research Validation Protocol
- Risk Engine Metrics
- Trend and Price Coordination
- Strategy Signal Tests
- Advisory Context Tests
- Portfolio and Order Contracts
- Quant and Monitoring Tests
- Advisory API Tests
- Agent Lifecycle and Copying
- MES5m Signal Research
- Strategy Registry Tests
- Futures Evidence and Streaks
- Accounting Book State Tests
- Research Journal Tests
- Observation Parsing Tests
- Briefing API Workflow
- Proposal and Deployment Tests
- Portfolio Risk Behavior Tests
- Economic Calendar Cache
- Account Profile Tests
- FirstRate Data Intake Tests
- OpenTerminal Research Tests
- Writer Lease and Specifications
- News Feed Cache
- Massive Data Intake Tests
- Dashboard WebSocket Manager
- MES5m Research Specification
- Production REST API
- ML Models and Inference
- Risk Governor Enforcement
- Portfolio Performance Metrics
- Architecture Boundary Tests
- Accounting Pipeline Tests
- Backtest Mathematics Tests
- Research Backup and Restore
- Execution Adapter Tests
- Execution Recovery Tests
- Strategy Behavior Tests
- Research Brief Tests
- Execution Capability Tests
- Dashboard TypeScript Configuration
- Path Risk Statistics
- Market Data Intake Tests
- CIO Decision Agent
- Sentiment Intelligence
- Correlation Analysis
- Contract Risk Worksheets
- Infrastructure Access Tests
- Mock Dashboard API
- Audit Monitoring Tests
- News Context Briefings
- PostgreSQL Funding Tests
- Geopolitical Intelligence
- Service Lifecycle Tests
- Capability Registry Tests
- OpenTerminal Context Tests
- Prompt Cache Tests
- Runtime Efficiency Tests
- Futures Edge Tests
- Intelligence Agent Tests
- Dashboard Runtime Dependencies
- MES5m Data Tests
- Market Data Hub
- News Analysis Agent
- OnChain Intelligence
- Cross Exchange Arbitrage
- Research Journal Exports
- AI Budget Controls
- Research Quality Tests
- Alert Dispatch Agent
- Compliance Monitoring Agent
- Capability Registry API
- Kafka Metrics Collection
- Price Publisher Tests
- Agent Runner Imports
- Research Monitor Tests
- Executor Kill Switch Handling
- Research Freshness Tests
- Exchange Executor Tests
- API Access Middleware
- Runtime Safety Configuration
- Briefing Commit Guard
- Research Diagnostics Tests
- Live Feed Connections
- Agent Lifecycle Integration
- Redis State Integration
- Paper Runtime Tests
- Dashboard Build Dependencies
- Build TypeScript Configuration
- Reinforcement Position Sizing
- Audit Report Persistence
- Paper Setup Tests
- ML Historical Data Loader
- MES5m Qualification Tests
- Paper Market Feed
- Exclusive Database Connection
- Continuous Integration Configuration
- Container Stack Configuration
- News Classification Metrics
- PnL History Writer
- Kubernetes API Manifest
- Prometheus Monitoring Configuration
- Kubernetes Agent Manifest
- API Background Lifecycle
- Evaluation Probability Evidence
- Agent Capability Guard Tests
- Advisory Container Configuration
- Paper Container Configuration
- Advisory Identity Validation
- Python Project Configuration
- Grafana Datasource Configuration
- Grafana Dashboard Configuration
- Risk Alert WebSocket Forwarding
- Prometheus Alert Rules
- Advisory Fixture
- Research Walk Fixtures

## God Nodes (most connected - your core abstractions)
1. `AdvisoryStore` - 124 edges
2. `useLanguage()` - 109 edges
3. `KafkaTopic` - 107 edges
4. `tr()` - 105 edges
5. `Exchange` - 98 edges
6. `TradeProposal` - 90 edges
7. `Strict` - 87 edges
8. `AgentConfig` - 87 edges
9. `OrderSide` - 79 edges
10. `BaseAgent` - 77 edges

## Surprising Connections

- `test_pinned_configuration_exists_and_matches_the_frozen_protocol()` --uses--> `ResearchSpec` [INFERRED]
  `tests/unit/test_mes5m_qualification_cli.py` → `src/backtesting/mes5m_spec.py`
- `test_render_failure_is_reported_without_filesystem_details()` --uses--> `ResearchJournal` [INFERRED]
  `tests/unit/test_research_brief.py` → `src/connectors/advisory/research_journal.py`
- `test_full_compose_binds_local_and_authenticates_every_broker_listener()` --uses--> `Settings` [INFERRED]
  `tests/unit/test_infrastructure_access.py` → `src/core/config.py`

## Import Cycles
- None detected.

## Communities (185 total, 44 thin omitted)

### Community 0 - "Trading Messages and Agents"
Cohesion: 0.04
Nodes (35): BaseStrategy, AgentStatus, AlertType, AssetClass, Chain, Exchange, KafkaTopic, MarketState (+27 more)

### Community 1 - "Advisory Research Contracts"
Cohesion: 0.04
Nodes (58): EODProjection, Strict, OpenTerminalContext, PublicHeadline, PublicQuote, TerminalSource, CandleAnalysis, HistoryMetadata (+50 more)

### Community 2 - "Research Journal Interface"
Cohesion: 0.04
Nodes (103): ResearchAlert, ResearchChange, researchSnapshot, ResearchWatchEntry, DataStatusCard, CandleQuality, terminalResearch, ResearchExplanation (+95 more)

### Community 3 - "Advisory Reports and Clocks"
Cohesion: 0.04
Nodes (36): PublicMarkets, DataHealthPolicy, Candle, EconomicCalendar, EventRiskAssessment, EventRiskPolicy, FuturesSpec, MarketDataEvidence (+28 more)

### Community 4 - "Personal Evaluation Interface"
Cohesion: 0.03
Nodes (103): Evaluation, Profile, CurrentResult, envelope, TCP25Capacity, TCP25PlanRequest, TCP25Snapshot, AccountObservation (+95 more)

### Community 5 - "Market Data Quality Tests"
Cohesion: 0.05
Nodes (86): ReplayProvider, market(), test_csv_rejects_ambiguous_dates_unfinished_duplicate_and_invalid_prices(), test_futures_closed_bars_only_and_optional_derivatives_fail_explicitly(), test_import_identity_contract_and_duration_are_checked(), test_intelligence_allowlist_freshness_deduplication_and_redaction(), test_missing_stale_short_data_never_generates_price_scenarios(), test_news_returns_headlines_provenance_and_source_outages() (+78 more)

### Community 6 - "Dashboard Charts and Translation"
Cohesion: 0.06
Nodes (88): DrawdownGaugeProps, ExposureBarProps, BrokerGroup, Props, MiniSparklineProps, TooltipProps, KpiProps, ErrorBoundary (+80 more)

### Community 7 - "Proposal Approval and Execution"
Cohesion: 0.04
Nodes (26): ProposalApprover, FeeOptimizer, HedgeManager, LiquidationGuard, OrderRouter, _ExecutionState, SlippageMinimizer, AgentMessage (+18 more)

### Community 8 - "Evaluation Event Simulation"
Cohesion: 0.06
Nodes (70): EvaluationEvent, EvaluationSimulation, EvaluationStep, EvaluationTape, MarginCapacity, SimulatedPosition, EODFinancialState, EODTerms (+62 more)

### Community 9 - "Advisory Service and Risk"
Cohesion: 0.07
Nodes (39): AdvisoryService, AccountConfiguration, AccountObservation, AccountRoleCheck, AccountState, _Evidence, OpenPosition, ResearchAssignment (+31 more)

### Community 10 - "Strategy and DeFi Configuration"
Cohesion: 0.03
Nodes (8): MomentumStrategy, BridgeStrategistAgent, DEXArbitrageurAgent, MEVHunterAgent, YieldFarmerAgent, AgentConfig, AgentHeartbeat, _momentum_score()

### Community 11 - "Durable Execution Recovery"
Cohesion: 0.06
Nodes (21): PaperVenue, AccountScope, OrderConflictError, RecoveryBlockedError, RecoveryCoordinator, ExecutionStore, recovery(), funded() (+13 more)

### Community 12 - "Advisory Persistence and Strategies"
Cohesion: 0.06
Nodes (17): AdvisoryStore, AccountPlan, Watchlist, MarketLimits, MarketSelection, TradingEdgeEvidence, StrategyApprovalCheck, StrategyDefinition (+9 more)

### Community 13 - "Application State and Localization"
Cohesion: 0.06
Nodes (53): ContextSource, newsContext, DiagnosticResult, TCP25Plan, linkedInstrument, terminalContext, Candle, Instrument (+45 more)

### Community 14 - "Dashboard Market Data Providers"
Cohesion: 0.08
Nodes (24): AssetClass, HistoricalBar, Quote, QuoteProvider, MockCryptoProvider, MockEquityProvider, MockForexProvider, Holding (+16 more)

### Community 15 - "Personal TCP25 Assessment"
Cohesion: 0.08
Nodes (47): CapacityRequest, PersonalEvidence, PlanRequest, RevisionConflictError, account(), _calculate(), capacity(), plan() (+39 more)

### Community 16 - "Dashboard WebSocket State"
Cohesion: 0.05
Nodes (51): DashboardWebSocketClient, AgentDetailModalProps, DummyWebSocketClient, TopicCardProps, DashboardState, ToastItem, WsStatus, AgentDef (+43 more)

### Community 17 - "ML Strategy and Failover"
Cohesion: 0.04
Nodes (5): MLPredictorAgent, MockMLServer, TestMLPredictorFailover, ml_predictor_agent(), mock_ml_server()

### Community 18 - "Backtest Validation Engine"
Cohesion: 0.06
Nodes (18): BacktestEngine, BacktestResult, ClosedTrade, MonteCarloResult, PerformanceMetrics, WalkForwardResult, WalkForwardWindow, engine() (+10 more)

### Community 19 - "Dashboard Routing and Build"
Cohesion: 0.05
Nodes (52): SidebarProps, NavigationId, App(), Sidebar(), accessScopeForPath(), navigationForScope(), name, private (+44 more)

### Community 20 - "Research Data Provenance"
Cohesion: 0.06
Nodes (28): DevelopmentSlice, FiveMinuteNormalizer, MissingInterval, AdvisoryMarketData, MarketDataProvider, MarketDataQuery, relevant(), _cut() (+20 more)

### Community 21 - "Quantitative Signals and Volatility"
Cohesion: 0.06
Nodes (11): TechnicalAnalyst, VolatilityForecaster, PositionSizer, PositionSizingResult, RiskLimits, SignalDirection, TechnicalSignal, VolatilityRegime (+3 more)

### Community 22 - "OHLCV Strategy Implementations"
Cohesion: 0.05
Nodes (9): BreakoutHunter, MeanReversion, StatArb, OHLCVBar, MarketCrashSimulator, kill_switch_io(), crash_simulator(), _hurst_exponent() (+1 more)

### Community 23 - "Evaluation Account Tests"
Cohesion: 0.09
Nodes (50): clock(), observation(), observed_session(), test_account_guard_rejects_bypassed_model_validation_and_invalid_age_configuration(), test_account_guard_rejects_identity_or_financial_disagreement(), test_account_observation_cannot_make_future_journal_rows_current(), test_account_snapshot_is_immutable_and_position_pnl_reconciles(), test_complete_reconciled_state_reaches_existing_risk_limits() (+42 more)

### Community 24 - "Observation Storage and Briefings"
Cohesion: 0.09
Nodes (27): ObservationConflictError, ObservationStore, ObservationFrame, ObservationModel, ObservationPacket, ObservationReview, ObservationRevision, ObservationView (+19 more)

### Community 25 - "Evaluation Policy Tests"
Cohesion: 0.11
Nodes (51): TCP25Policy, TradingWindow, clock(), tcp50_rules(), test_service_roles_hold_with_other_financial_gates_ready(), test_api_account_role_snapshot_and_forbidden_assignment_inputs(), test_legacy_planner_cannot_bypass_strategy_registry_with_roles_disabled(), allowance() (+43 more)

### Community 26 - "Kafka Messaging Infrastructure"
Cohesion: 0.06
Nodes (17): AlghrestConsumer, AlghrestProducer, broker(), aiokafka_security(), confluent_security(), _deserialize(), _serialize(), test_real_broker_rejects_anonymous_and_wrong_key_allows_authenticated_bus() (+9 more)

### Community 27 - "Observation and Briefing Interface"
Cohesion: 0.07
Nodes (52): BriefingRequest, BriefingView, ObservationPacket, observationView, BriefingPanel(), create(), load(), loadHistory() (+44 more)

### Community 28 - "Advisory Risk Tests"
Cohesion: 0.10
Nodes (50): test_api_synthetic_qualified_risk_is_wait_and_can_be_reproduced(), test_client_cannot_supply_registry_approval_or_disable_its_gate(), allowance(), config(), decision(), history(), inputs(), make_service() (+42 more)

### Community 29 - "Telegram Messaging and Access"
Cohesion: 0.07
Nodes (12): TelegramBotManager, _api(), _fmt_pct(), _fmt_status(), test_advisory_write_intent_header_cannot_replace_authentication(), test_all_real_ws_routes_reject_before_acceptance_or_state_access(), test_browser_handshake_authorized_control(), test_http_auth_fail_closed_and_separate_keys() (+4 more)

### Community 30 - "Briefing Persistence Tests"
Cohesion: 0.09
Nodes (32): BriefingConflictError, BriefingStore, Briefing, BriefingRequest, api_client(), clock(), store(), build_briefing() (+24 more)

### Community 31 - "User Policy and Briefings"
Cohesion: 0.08
Nodes (20): BriefingInputs, BriefingResult, BriefModel, Capability, UserPolicyAssessment, UserPolicyRequest, UserRiskAssessment, UserRiskRequest (+12 more)

### Community 32 - "User Policy Risk Tests"
Cohesion: 0.12
Nodes (40): fixed_clock(), clock(), assess_user_risk(), make_request(), test_confirmed_flat_mes_uses_costs_and_exact_risk_budget(), test_expiry_revision_and_hash_verification_replays_serialized_evidence(), test_incomplete_and_breached_evidence_never_sizes(), test_invalid_or_incomplete_request_is_rejected() (+32 more)

### Community 33 - "Advisory HTTP API"
Cohesion: 0.13
Nodes (33): EvaluationPlan, CSVImport, account_plan(), catalog(), create_evaluation(), evaluation(), evaluation_policy(), evaluations() (+25 more)

### Community 34 - "HTTP Clients and Utilities"
Cohesion: 0.07
Nodes (11): CacheControl, CachedTextBlock, NewsItem, NewsSignal, cached_system(), send_kill_switch_alert(), send_pagerduty_alert(), send_telegram_alert() (+3 more)

### Community 35 - "Dashboard API Integration Tests"
Cohesion: 0.06
Nodes (14): client(), bot(), health(), risk(), test_history_is_deterministic_ordered_and_valid(), test_history_rejects_unknown_symbols_and_invalid_windows(), test_lifespan_cancels_and_awaits_background_tasks(), test_alert_pubsub_ignores_subscription_messages() (+6 more)

### Community 36 - "Research Terminal Localization"
Cohesion: 0.08
Nodes (19): Language, applyLanguage(), formatMessage(), getLanguage(), initializeLanguage(), isLanguage(), languageMessage(), setLanguage() (+11 more)

### Community 37 - "PostgreSQL Accounting Tests"
Cohesion: 0.08
Nodes (18): OpeningBalances, Ledger, ledger(), writer(), fill(), test_concurrent_duplicates_and_reconnect(), test_conflicting_identity_and_reseed_cannot_change_book(), test_cutoff_accounts_for_replay_without_booking_opening_twice() (+10 more)

### Community 38 - "Funding and Portfolio Valuation"
Cohesion: 0.08
Nodes (12): PortfolioAccountant, Deposit, DepositReceipt, PaperDeposits, CashBalance, StrictModel, MissingValuationError, Valuation (+4 more)

### Community 39 - "Futures Validation Tests"
Cohesion: 0.13
Nodes (36): FuturesWalkPlan, FuturesWalkStudy, verify_walk(), futures_expectancy_uncertainty(), verify_futures_walk(), walk_forward_futures(), test_evidence_without_the_internal_module_hash_is_rejected(), test_fresh_walk_runs_each_fold_once_and_reopened_requests_replay_every_fold() (+28 more)

### Community 40 - "Path Risk Analysis Tests"
Cohesion: 0.14
Nodes (32): LossStreakStudy, iid_loss_run_probability(), loss_streak_analysis(), observed_result(), brute_probability(), config(), longest(), test_absorbing_recurrence_matches_exhaustive_sequence_enumeration() (+24 more)

### Community 41 - "Exchange Adapter Contracts"
Cohesion: 0.10
Nodes (3): ExchangeConnector, SpotRecoveryAdapter, Order

### Community 42 - "Fill Accounting and Persistence"
Cohesion: 0.11
Nodes (11): LedgerPosition, FillConflictError, Fill, FillFee, apply_fill(), fees(), fingerprint(), identity() (+3 more)

### Community 43 - "Futures Research Tests"
Cohesion: 0.14
Nodes (30): run_futures_research(), verify_futures_run(), test_complete_no_trade_history_has_unknown_metrics_and_no_probabilities(), test_internal_module_source_changes_invalidate_saved_evidence(), changed(), chunks(), request(), test_adverse_entry_slippage_cannot_rescue_an_already_invalid_raw_open() (+22 more)

### Community 44 - "Market Selection Tests"
Cohesion: 0.16
Nodes (34): MarketMeasurement, test_reported_historical_labels_are_metadata_not_authenticated_validation(), test_missing_book_side_is_not_assumed_zero_entry_deviation(), candidate(), context(), edge(), fit(), policy() (+26 more)

### Community 45 - "Redis State and Gates"
Cohesion: 0.11
Nodes (8): StateManager, state(), test_snapshot_cache_is_recreatable_and_short_lived(), test_trade_gate_requires_fresh_matching_revision_and_book(), test_health_roundtrip_expiry_and_missing_records(), test_initialize_and_shutdown_release_connections(), test_kill_switch_reason_and_atomic_dedup(), test_signals_json_and_pubsub_preserve_payloads()

### Community 46 - "Access and Backup Interface"
Cohesion: 0.09
Nodes (26): HeaderProps, AccessScope, RestoreResult, ResearchBackup(), download(), restore(), select(), ResearchBriefExport() (+18 more)

### Community 47 - "Market Quotes Interface"
Cohesion: 0.11
Nodes (33): EnrichedHolding, Props, Props, QuotesResult, LiveQuotes, AssetClass, HistoricalBar, Holding (+25 more)

### Community 48 - "Futures Research Engine"
Cohesion: 0.11
Nodes (23): CensoredFuturesPosition, DrawdownRecovery, FuturesDecision, FuturesEntry, FuturesEventCheck, FuturesFillModel, FuturesFillObservation, FuturesLossRuns (+15 more)

### Community 49 - "Trade Management Tests"
Cohesion: 0.12
Nodes (32): atr_trailing_step(), bar(), frame(), test_agent_entry_uses_the_shared_kernel_without_sizing_in_it(), test_backtest_cannot_skip_the_immediately_preceding_high(), test_backtest_signals_use_shared_prefix_rule_and_next_close_proxy(), test_shared_entry_rule_does_not_replace_legacy_position_exits(), test_zero_baseline_volume_cannot_confirm_an_agent_breakout() (+24 more)

### Community 50 - "Research Document Rendering"
Cohesion: 0.10
Nodes (14): ArabicText, _font(), render_research_pdf(), _render_research_pdf(), heading(), page(), _shape(), comparison_lines() (+6 more)

### Community 51 - "Kill Switch Integration"
Cohesion: 0.10
Nodes (5): KillSwitchEvent, RiskMetrics, KillSwitch, TestMarketCrashKillSwitch, mock_close_positions()

### Community 52 - "Macro Strategy Intelligence"
Cohesion: 0.08
Nodes (7): MacroEconomist, MacroRotator, MacroSignal, MarketRegime, SentimentSignal, _Signal, test_actual_agent_envelopes_supply_legacy_utc_signal_time_and_market_scope()

### Community 53 - "Research Validation Protocol"
Cohesion: 0.13
Nodes (23): FuturesResearchInput, FuturesUncertaintyStudy, FuturesWalkFold, FuturesWalkWindow, MeanBootstrapConfig, MeanInterval, PartitionUncertainty, ResearchPartition (+15 more)

### Community 54 - "Risk Engine Metrics"
Cohesion: 0.11
Nodes (9): RiskEngine, test_diversification_and_concentration_aggregate_venues(), test_var_cvar_and_ratios_against_independent_calculations(), _portfolio(), test_drawdown_correct_when_below_baseline(), test_drawdown_zero_when_capital_above_baseline(), test_position_limit_approves_small_proposal(), test_var_positive_for_long_history() (+1 more)

### Community 55 - "Trend and Price Coordination"
Cohesion: 0.10
Nodes (6): PricePublisher, TrendFollower, test_envelope_identity_and_error_counters(), test_halted_strategy_never_evaluates_incoming_prices(), test_strategy_risk_cap_and_pause_requires_explicit_resume(), test_tier2_envelope_is_consumed_by_real_strategy()

### Community 56 - "Strategy Signal Tests"
Cohesion: 0.17
Nodes (27): StrategyResearchCheck, VolumeBreakoutKernel, clear_event_context(), daily_market(), parameters(), prices(), research(), test_copied_positive_experiment_cannot_keep_guards_after_source_changes() (+19 more)

### Community 57 - "Advisory Context Tests"
Cohesion: 0.09
Nodes (25): ics(), rss(), source(), test_ambiguous_nonexistent_or_unspecified_zone_is_not_invented(), test_application_collector_cancellation_releases_all_source_reads(), test_authenticated_context_no_price_report_storage_write_or_order_path(), test_calendar_failure_no_stale_fallback_cache_and_source_edit(), test_cancelled_date_only_utc_and_unsupported_recurring_events() (+17 more)

### Community 58 - "Portfolio and Order Contracts"
Cohesion: 0.11
Nodes (13): OrderBook, Portfolio, proposal_data(), test_bar_requires_time_and_exchange(), test_confidence_must_be_a_probability(), test_legacy_proposal_cannot_silently_supply_missing_contract(), test_order_book_price_publisher_contract(), test_per_message_ids_and_metadata_are_independent() (+5 more)

### Community 59 - "Quant and Monitoring Tests"
Cohesion: 0.08
Nodes (16): FiniteConsumer, fill(), test_alert_transport_retries_and_escalation_responses(), test_alerts_continue_while_halted_and_escalate_only_critical(), test_compliance_logs_halted_fills_and_flags_wash_trades_and_limits(), test_compliance_skips_missing_or_unrelated_positions(), test_daily_report_uses_actual_portfolio_and_tracker(), test_copy_trading_rejects_malformed_and_halted_messages() (+8 more)

### Community 60 - "Advisory API Tests"
Cohesion: 0.08
Nodes (15): client(), test_api_evaluation_persists_and_never_invents_a_profile(), test_api_monthly_contract_import_persists_without_execution(), test_api_persists_blocked_health_and_cannot_override_it(), test_api_policy_default_is_versioned_and_missing_evidence_is_unknown(), test_api_policy_timeout_and_corruption_are_explicit(), test_api_profile_selects_policy_without_creating_accounts(), test_api_risk_decision_requires_server_state_and_disallows_budget_overrides() (+7 more)

### Community 61 - "Agent Lifecycle and Copying"
Cohesion: 0.10
Nodes (5): BaseAgent, CopyTradingAgent, AgentHealth, TelegramBroadcaster, test_copy_trading_uses_actual_price_and_filters_unusable_proposals()

### Community 62 - "MES5m Signal Research"
Cohesion: 0.20
Nodes (20): ExposurePath, ResearchState, SignalPlan, SyntheticWindow, ResearchSpec, Safety, entry_timing_status(), propose_signal() (+12 more)

### Community 63 - "Strategy Registry Tests"
Cohesion: 0.17
Nodes (25): check(), definition(), event(), plan(), record(), test_concurrent_registration_cas_cannot_overwrite_another_version(), submit(), test_corrupt_registry_never_repairs_or_silently_drops_records() (+17 more)

### Community 64 - "Futures Evidence and Streaks"
Cohesion: 0.16
Nodes (20): FuturesEdgeStudy, FuturesResearchRun, LossStreakConfig, _edge_partitions(), _edge(), edge_analysis(), research(), verify_edge() (+12 more)

### Community 65 - "Accounting Book State Tests"
Cohesion: 0.17
Nodes (17): BookState, Records, cash(), fill(), opening(), position(), test_commit_is_after_success_and_scoped_to_processed_partition(), test_daily_weekly_pnl_and_short_collateral() (+9 more)

### Community 66 - "Research Journal Tests"
Cohesion: 0.11
Nodes (16): journal(), client(), report(), snapshot(), test_bounded_overview_history_preserves_full_history(), test_capture_refuses_wrong_provider_symbol(), test_capture_uses_server_data_retry_and_history_api(), test_concurrent_retries_have_one_durable_result() (+8 more)

### Community 67 - "Observation Parsing Tests"
Cohesion: 0.15
Nodes (23): store(), client(), parse_observation(), packet(), raw(), test_api_auth_invalid_missing_and_self_approval(), test_api_workflow_and_revision_history(), test_append_review_edit_reopen_and_legacy_rows_preserved() (+15 more)

### Community 68 - "Briefing API Workflow"
Cohesion: 0.14
Nodes (12): BriefingSaveOutcomeError, BriefingWorkflow, BriefingView, create(), history(), read(), _workflow(), _consume_save_result() (+4 more)

### Community 69 - "Proposal and Deployment Tests"
Cohesion: 0.11
Nodes (13): approver(), worker(), proposal(), test_classifies_rejection_only_after_checking_execution_records(), test_foreign_review_never_authorizes_retry(), test_timeout_identifies_proposal_and_is_not_retried(), now(), test_concentration_reduction_scales_executable_quantity() (+5 more)

### Community 70 - "Portfolio Risk Behavior Tests"
Cohesion: 0.16
Nodes (14): PortfolioTracker, governor(), portfolio(), with_performance(), sample(), test_funding_does_not_change_drawdown_or_daily_returns(), test_gap_does_not_become_a_daily_return(), test_metrics_sample_threshold_and_calendar_sharpe() (+6 more)

### Community 71 - "Economic Calendar Cache"
Cohesion: 0.13
Nodes (10): CalendarCache, Node, ScheduleHTML, EconomicEvent, ScheduledContext, _eastern(), _entry(), _ics() (+2 more)

### Community 72 - "Account Profile Tests"
Cohesion: 0.15
Nodes (20): AccountBinding, configuration(), plan(), role_check(), store_with_plan_sources(), test_corrupted_stored_plan_or_missing_bound_journal_never_falls_back(), test_final_risk_role_gate_cannot_increase_size_or_borrow_an_account(), test_initial_roles_are_explicit_distinct_and_never_trade_permission() (+12 more)

### Community 73 - "FirstRate Data Intake Tests"
Cohesion: 0.22
Nodes (24): assert_closed(), fixture(), inspect(), query(), test_all_incomplete_rows_and_gaps_remain_visible_without_filling(), test_all_rows_checked_after_selection_and_maximum_window_is_reported(), test_bad_encoding_schema_and_chronology_are_not_repaired(), test_bom_and_crlf_have_exact_complete_source_identities() (+16 more)

### Community 74 - "OpenTerminal Research Tests"
Cohesion: 0.15
Nodes (22): clocks(), bars(), collect(), transport(), history_envelope(), quote(), test_arbitrary_urls_path_traversal_or_multi_symbol_requests_are_refused(), test_bad_history_metadata_is_rejected_without_losing_other_feeds() (+14 more)

### Community 75 - "Writer Lease and Specifications"
Cohesion: 0.12
Nodes (17): test_tier_membership_and_shared_equity_exposure_are_explicit(), test_frozen_spec_rejects_parameter_and_permission_changes(), test_model_copy_cannot_authorize_a_holdout_day(), test_partitions_and_costs_cannot_be_reordered_or_relabelled(), test_specification_freezes_parameters_and_denies_non_development_access(), test_histogram_rejects_negative_wrong_length_or_boolean_counts(), test_reported_approved_edge_cannot_qualify_default_risk_without_registry(), test_cancelled_check_releases_mutex_for_next_check() (+9 more)

### Community 76 - "News Feed Cache"
Cohesion: 0.14
Nodes (10): FeedCache, PlainText, News, SourceStatus, clock(), api_client(), download(), headlines() (+2 more)

### Community 77 - "Massive Data Intake Tests"
Cohesion: 0.22
Nodes (22): arguments(), assert_closed(), convert(), fixture(), inspected(), test_bad_or_oversized_json_is_rejected(), test_candle_boundaries_reject_duplicates_overlaps_and_unfinished_intervals(), test_cli_has_no_execution_or_credential_options() (+14 more)

### Community 78 - "Dashboard WebSocket Manager"
Cohesion: 0.17
Nodes (3): DashboardWebSocketManager, test_broadcast_survives_connections_changing_during_send(), test_display_loops_wait_for_viewer_then_resume_and_cancel_cleanly()

### Community 79 - "MES5m Research Specification"
Cohesion: 0.13
Nodes (13): CostScenario, Partition, RegistryEvent, ResearchModel, SourceIdentity, canonical_json(), _costs(), _decimal() (+5 more)

### Community 80 - "Production REST API"
Cohesion: 0.12
Nodes (12): get_agent_health(), get_all_agents(), get_kill_switch_status(), get_macro_regime(), get_portfolio(), get_positions(), get_risk_metrics(), get_sentiment() (+4 more)

### Community 81 - "ML Models and Inference"
Cohesion: 0.14
Nodes (6): PredictionRequest, PredictionResponse, CandlestickCNN, predict(), train_cnn(), train_rl_agent()

### Community 82 - "Risk Governor Enforcement"
Cohesion: 0.15
Nodes (4): RiskGovernor, test_governor_absent_state_leverage_and_concentration(), test_governor_cancels_sibling_loops_when_consumer_fails(), test_governor_thresholds_and_kill_switch_latch()

### Community 83 - "Portfolio Performance Metrics"
Cohesion: 0.16
Nodes (10): PerformanceUnavailableError, Performance, PeriodReference, load(), observe(), save(), snapshot(), period_starts() (+2 more)

### Community 84 - "Architecture Boundary Tests"
Cohesion: 0.16
Nodes (15): source_tree(), test_advisory_boundary_prevents_trading_state_access(), test_advisory_rejects_aliased_producer_capabilities(), test_advisory_rejects_dynamic_execution_imports(), test_advisory_rejects_relative_and_absolute_execution_imports(), test_advisory_rejects_transitive_io_and_reports_import_chain(), test_advisory_unknown_dynamic_import_fails_closed(), test_advisory_wildcard_import_cannot_hide_capabilities() (+7 more)

### Community 85 - "Accounting Pipeline Tests"
Cohesion: 0.18
Nodes (15): accountant(), test_accounting_marks_do_not_merge_venues_or_refresh_old_price_time(), test_cache_expires_quickly_if_process_dies(), test_connector_does_not_silently_drop_an_unbookable_fill(), test_connector_preserves_stable_identity_and_all_fees(), test_empty_ccxt_fee_list_does_not_discard_known_primary_fee(), test_failed_writer_claim_does_not_clear_another_accountants_cache(), test_fill_accounting_continues_while_trading_is_halted() (+7 more)

### Community 86 - "Backtest Mathematics Tests"
Cohesion: 0.25
Nodes (17): engine(), frame(), signals(), test_both_backends_have_matching_trade_and_equity_metrics(), test_drawdown_duration_counts_recovery_and_unrecovered_periods(), test_elapsed_calendar_years_and_cagr_use_timestamps_not_number_of_bars(), test_empirical_bootstrap_uses_observed_support_and_ignores_summary_estimates(), test_fees_slippage_size_and_closed_return_have_exact_cash_arithmetic() (+9 more)

### Community 87 - "Research Backup and Restore"
Cohesion: 0.27
Nodes (14): export_research(), restore_research(), read_backup(), journal(), payloads(), rehash(), save(), test_backup_api_auth_preview_restore_and_body_limits() (+6 more)

### Community 88 - "Execution Adapter Tests"
Cohesion: 0.19
Nodes (16): adapter(), order(), test_adapter_passes_stable_submission_id_and_cancel_failure_is_not_success(), test_ambiguous_lookup_requires_matching_client_id(), test_binance_single_timestamp_saturation_or_outside_window_blocks(), test_binance_subdivides_saturated_window_without_advancing_past_timestamp_ties(), test_coinbase_client_lookup_paginates_closed_history(), test_kraken_counts_unfiltered_account_history_and_preserves_other_symbols() (+8 more)

### Community 89 - "Execution Recovery Tests"
Cohesion: 0.19
Nodes (17): TradePage, fill(), order(), ready(), test_balance_drift_and_unknown_open_orders_block(), test_cancelled_partial_order_waits_for_delayed_fill(), test_changed_ledger_revision_blocks_previously_verified_gate(), test_crash_before_network_call_remains_unresolved_never_resubmitted() (+9 more)

### Community 90 - "Strategy Behavior Tests"
Cohesion: 0.18
Nodes (14): candidate(), position(), candle_window(), test_defi_skeletons_never_emit_orders_or_pass_backtests(), test_macro_reads_nested_signals_and_real_price_cache(), test_mean_reversion_evaluation_respects_bands_and_hurst(), test_mean_reversion_open_close_and_loss_tracking(), test_momentum_position_sizing_and_exit() (+6 more)

### Community 91 - "Research Brief Tests"
Cohesion: 0.16
Nodes (17): ResearchBrief, journal(), client(), report(), saved(), test_brief_is_read_only_and_includes_symbols_with_no_snapshot(), test_brief_rejects_wrong_symbol_future_clock_and_duplicate_symbols(), test_comparison_has_numbers_but_no_delta_for_unknown_timeframe() (+9 more)

### Community 92 - "Execution Capability Tests"
Cohesion: 0.19
Nodes (14): OrderExecutionDisabledError, test_direct_broker_mutation_denied_on_existing_client(), test_exchange_connection_denied_before_credentials_or_network(), test_executor_denied_before_store_or_venue_contact(), test_launcher_denies_before_subprocess_start(), test_paper_mutations_and_matching_lookup_denied(), test_producer_blocks_all_legacy_topics_and_raw_publication(), test_producer_denied_before_client_construction() (+6 more)

### Community 93 - "Dashboard TypeScript Configuration"
Cohesion: 0.10
Nodes (20): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleResolution (+12 more)

### Community 94 - "Path Risk Statistics"
Cohesion: 0.13
Nodes (7): _block_starts(), _compute(), paired_block_bootstrap_means(), recorded_loss_run_tables(), _source_error(), test_paired_samples_keep_channel_alignment_and_observed_mean_support(), test_paired_sampling_block_and_work_limits()

### Community 95 - "Market Data Intake Tests"
Cohesion: 0.27
Nodes (16): arguments(), assert_abstains(), inspect(), query(), snapshot(), test_bad_structures_and_injected_permission_are_rejected(), test_cli_exit_codes_and_read_only_output(), test_cli_missing_file_and_naive_clock_are_errors() (+8 more)

### Community 96 - "CIO Decision Agent"
Cohesion: 0.15
Nodes (4): CIOAgent, test_invalid_allocations_are_not_repaired_into_decisions(), test_timeout_has_one_reservation_one_request_and_keeps_weights(), test_unchanged_context_skips_call_but_changed_and_expired_inputs_do_not()

### Community 99 - "Contract Risk Worksheets"
Cohesion: 0.16
Nodes (12): Instrument, RiskWorksheet, worksheet(), risk_worksheet(), test_worksheet_contract_point_values_fees_and_no_index_orders(), test_dated_contract_accepts_each_family_month_and_rejects_aliases(), test_internal_copies_cannot_bypass_risk_input_bounds(), test_invalid_spec_and_legacy_report_compatibility() (+4 more)

### Community 100 - "Infrastructure Access Tests"
Cohesion: 0.11
Nodes (5): test_advisory_kafka_credentials_are_independent(), test_bad_existing_key_is_not_silently_rotated(), test_full_compose_binds_local_and_authenticates_every_broker_listener(), test_generate_independent_credentials_once_without_replacing_existing(), test_unsupported_platform_fails_before_touching_env()

### Community 101 - "Mock Dashboard API"
Cohesion: 0.14
Nodes (4): MockDashboardManager, demo_messages(), lifespan(), websocket_dashboard()

### Community 102 - "Audit Monitoring Tests"
Cohesion: 0.14
Nodes (4): AuditorAgent, collector(), test_audit_demo_is_labelled_and_never_halts_trading(), test_auditor_refuses_synthetic_validation_outside_development()

### Community 103 - "News Context Briefings"
Cohesion: 0.21
Nodes (10): ContextHeadline, ContextModel, NewsContext, _collect_context(), context(), collect_context(), build_context(), relevance() (+2 more)

### Community 104 - "PostgreSQL Funding Tests"
Cohesion: 0.26
Nodes (17): persist_snapshot(), deposit(), make_ready(), order(), test_cache_failure_after_commit_keeps_receipt_and_durable_gate(), test_concurrent_distinct_deposits_add_without_lost_update(), test_concurrent_duplicate_receipts_and_conflicting_reference(), test_dry_run_then_atomic_cash_and_performance_with_no_pnl() (+9 more)

### Community 106 - "Service Lifecycle Tests"
Cohesion: 0.12
Nodes (4): run(), start(), until(), wait()

### Community 107 - "Capability Registry Tests"
Cohesion: 0.13
Nodes (6): source_copy(), test_altered_definitions_or_confirmed_hypotheses_remain_insufficient(), test_constructed_or_serialized_permission_flags_cannot_unlock_registry(), test_missing_inconsistent_source_evidence_is_rejected(), test_missing_unmapped_or_redirected_source_cannot_yield_a_registry(), test_runtime_readiness_and_probability_cannot_be_inferred()

### Community 108 - "OpenTerminal Context Tests"
Cohesion: 0.20
Nodes (14): fixed_clock(), collect(), transport(), headlines(), quote(), test_empty_news_does_not_clear_events_and_duplicates_are_collapsed(), test_endpoint_retains_existing_authentication_and_no_store(), test_envelope_rejects_identity_changes_and_execution_flags() (+6 more)

### Community 109 - "Prompt Cache Tests"
Cohesion: 0.18
Nodes (8): reserve_without_paid_api(), _fake_response(), test_cio_passes_cache_control_in_system_prompt(), test_cio_records_cache_read_when_response_has_cache_hit(), test_cio_system_prompt_meets_caching_minimum_for_opus(), test_news_analyst_passes_cache_control_in_system_prompt(), test_news_classifier_system_meets_caching_minimum_for_sonnet(), test_news_records_cache_create_then_read()

### Community 110 - "Runtime Efficiency Tests"
Cohesion: 0.14
Nodes (7): feed(), test_cached_news_still_expires_by_publication_age(), test_cancelled_feed_refresh_can_retry_and_oversize_is_not_cached_as_success(), test_concurrent_markets_share_downloads_but_keep_independent_filtering(), respond(), test_feed_ttl_outages_and_recovery_never_relabel_stale_success(), respond()

### Community 111 - "Futures Edge Tests"
Cohesion: 0.18
Nodes (10): metrics(), observations(), test_adjusted_skew_matches_independent_float_moment_formula(), test_fractional_tail_mass_not_ceiling_sample_average(), test_hand_derived_mean_variance_skew_tail_profit_factor_and_recovery(), test_initial_and_unrecovered_underwater_episodes_keep_peak_and_duration(), test_no_loss_flat_single_observation_and_zero_variance_are_explicit(), test_nonpositive_boundaries_and_distinct_dollar_r_profit_factors() (+2 more)

### Community 112 - "Intelligence Agent Tests"
Cohesion: 0.16
Nodes (10): news(), response(), test_fred_parses_missing_and_zero_observations(), test_geo_region_lookup(), test_geo_rss_filters_stale_irrelevant_and_duplicate_articles(), test_geopolitical_risk_classification(), test_macro_regimes_publish_and_cache_consistent_direction(), test_news_feed_dedup_expiry_and_failure_tracking() (+2 more)

### Community 113 - "Dashboard Runtime Dependencies"
Cohesion: 0.12
Nodes (17): dependencies, class-variance-authority, clsx, lucide-react, @radix-ui/react-collapsible, @radix-ui/react-dialog, @radix-ui/react-tabs, @radix-ui/react-toast (+9 more)

### Community 114 - "MES5m Data Tests"
Cohesion: 0.26
Nodes (13): fixture(), snapshot(), test_cut_must_be_aware_and_inside_development_window(), test_dst_ambiguous_and_nonexistent_timestamps_are_rejected(), test_duplicate_source_timestamps_rejected_without_sorting(), test_excluded_day_and_asof_future_ohlcv_are_never_decoded(), test_missing_minute_is_explicit_and_not_a_zero_volume_candle(), test_partition_and_asof_isolation_precede_ohlcv_parsing() (+5 more)

### Community 115 - "Market Data Hub"
Cohesion: 0.21
Nodes (4): MarketDataHub, OrderBookLevel, test_market_data_normalization_rejects_bad_candles(), test_orderbook_normalization_caps_depth_and_rejects_malformed()

### Community 117 - "OnChain Intelligence"
Cohesion: 0.18
Nodes (3): OnChainSleuth, OnChainSignal, WhaleAlert

### Community 119 - "Research Journal Exports"
Cohesion: 0.19
Nodes (3): ResearchJournal, research_brief_pdf(), create()

### Community 120 - "AI Budget Controls"
Cohesion: 0.22
Nodes (8): BudgetUnavailableError, estimate_cost(), reserve(), test_daily_budget_concurrent_restart_and_dollar_limits(), test_budget_unavailable_never_calls_paid_api(), test_conservative_reservation_and_input_limits(), test_driver_failure_is_redacted_and_fail_closed(), test_rejected_atomic_reservation_still_closes_connection()

### Community 121 - "Research Quality Tests"
Cohesion: 0.32
Nodes (14): collect(), series(), test_clean_continuous_series_has_supporting_counts_and_keeps_freshness_unknown(), test_continuous_irregular_timestamp_spacing_blocks_affected_windows(), test_contradictory_quality_or_exposed_blocked_metrics_are_rejected(), test_defects_expose_counts_without_sorting_or_repair_and_keep_other_feeds(), test_fetch_clock_cannot_precede_a_returned_candle(), test_gaps_only_block_conclusions_whose_exact_trailing_window_is_affected() (+6 more)

### Community 124 - "Capability Registry API"
Cohesion: 0.21
Nodes (7): CapabilityDefinition, CapabilityRegistry, capabilities(), capability_registry(), _source_hashes(), verify_capability_registry(), test_capability_registry_is_authenticated_read_only_and_never_runtime_evidence()

### Community 126 - "Price Publisher Tests"
Cohesion: 0.34
Nodes (11): _build_publisher(), _ohlcv_payload(), _orderbook_payload(), test_h4_ohlcv_is_skipped(), test_invalid_ohlcv_payload_silently_dropped(), test_m1_ohlcv_writes_to_redis(), test_ohlcv_then_orderbook_merges_fields(), test_orderbook_with_no_levels_skipped() (+3 more)

### Community 127 - "Agent Runner Imports"
Cohesion: 0.21
Nodes (5): main(), test_agent_class_imports(), test_position_sizer_constructs(), test_proposal_approver_imports(), test_strategy_class_implements_abstract_interface()

### Community 128 - "Research Monitor Tests"
Cohesion: 0.17
Nodes (7): report(), test_assumed_crypto_session_does_not_count_as_a_provider_report(), test_invalid_gap_never_passes(), test_old_or_future_report_is_rejected(), test_only_assistant_receives_the_credential(), respond(), test_service_failures_and_changed_boundaries_abort()

### Community 130 - "Research Freshness Tests"
Cohesion: 0.24
Nodes (8): quote_freshness(), report(), test_adapter_assumption_and_legacy_snapshots_cannot_become_provider_reports(), test_adapter_preserves_quote_observation_and_rejects_future_fetch_clock_independently(), test_display_threshold_does_not_certify_realtime_or_source_latency(), test_provider_state_is_reported_without_inventing_a_calendar(), test_stale_cache_and_old_session_declarations_cannot_describe_current_session(), test_unknown_price_clock_cannot_become_fresh_because_the_source_was_just_fetched()

### Community 131 - "Exchange Executor Tests"
Cohesion: 0.30
Nodes (11): executor(), order(), test_algo_parents_are_not_submitted(), test_durable_gate_closes_between_cache_check_and_claim(), test_history_polling_continues_during_halt(), test_intent_commits_before_http_and_response_failure_never_resubmits(), test_invalid_order_durably_rejected_without_contacting_venue(), test_missing_risk_evidence_blocks_submission() (+3 more)

### Community 133 - "Runtime Safety Configuration"
Cohesion: 0.16
Nodes (3): Settings, get_settings(), test_profile_capability_is_independent_of_environment()

### Community 134 - "Briefing Commit Guard"
Cohesion: 0.15
Nodes (4): BriefingSaveGuard, guarded_briefing_save(), test_deadline_on_both_sides_of_commit_decision(), test_expired_guard_rolls_back_and_does_not_leak_to_direct_save()

### Community 135 - "Research Diagnostics Tests"
Cohesion: 0.24
Nodes (7): payload(), test_diagnostic_route_auth_no_store_and_symbol_validation(), fake(), test_failed_or_large_response_is_explicit_and_sanitized(), test_fixed_local_endpoint_without_forwarded_credentials(), handle(), test_invalid_diagnostics_never_pass_to_ui()

### Community 136 - "Live Feed Connections"
Cohesion: 0.20
Nodes (4): ConnectionManager, websocket_dashboard(), websocket_live_feed(), websocket_prices()

### Community 137 - "Agent Lifecycle Integration"
Cohesion: 0.17
Nodes (4): LifecycleAgent, agent(), test_cancelled_agent_closes_resources_even_if_custom_shutdown_fails(), test_run_failure_cancels_heartbeat_before_closing_connections()

### Community 138 - "Redis State Integration"
Cohesion: 0.22
Nodes (4): state(), test_domain_snapshots_roundtrip_and_reject_corruption(), test_lock_releases_on_failure_and_fails_if_contended(), test_trading_gate_requires_matching_fresh_evidence()

### Community 139 - "Paper Runtime Tests"
Cohesion: 0.31
Nodes (5): local(), test_preflight_collects_failure_types_without_leaking_connection_secrets(), test_provision_refuses_unrelated_environment_before_connecting(), test_quality_runner_isolates_storage_and_closes_connection(), test_quality_runner_refuses_live_environment_before_connecting()

### Community 140 - "Dashboard Build Dependencies"
Cohesion: 0.22
Nodes (9): devDependencies, autoprefixer, postcss, tailwindcss, @types/react, @types/react-dom, typescript, vite (+1 more)

### Community 141 - "Build TypeScript Configuration"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include

### Community 144 - "Paper Setup Tests"
Cohesion: 0.32
Nodes (3): manifests(), test_dry_run_never_connects_or_invents_opening_cash(), test_preparation_requires_explicit_paper_environment()

### Community 149 - "Continuous Integration Configuration"
Cohesion: 0.33
Nodes (5): permissions, jobs, name, env, on

### Community 150 - "Container Stack Configuration"
Cohesion: 0.33
Nodes (5): volumes, name, x-runtime-environment, networks, services

### Community 154 - "Kubernetes API Manifest"
Cohesion: 0.40
Nodes (4): kind, apiVersion, metadata, spec

### Community 155 - "Prometheus Monitoring Configuration"
Cohesion: 0.40
Nodes (4): scrape_configs, alerting, global, rule_files

### Community 156 - "Kubernetes Agent Manifest"
Cohesion: 0.40
Nodes (4): kind, apiVersion, metadata, spec

### Community 159 - "Agent Capability Guard Tests"
Cohesion: 0.40
Nodes (3): InertAgent, test_agent_publish_denied_even_with_replaced_producer(), test_agent_start_denied_before_any_initialization()

### Community 160 - "Advisory Container Configuration"
Cohesion: 0.50
Nodes (3): volumes, name, services

### Community 161 - "Paper Container Configuration"
Cohesion: 0.50
Nodes (3): volumes, name, services

## Knowledge Gaps
- **12 isolated node(s):** `@radix-ui/react-collapsible`, `@radix-ui/react-tabs`, `@radix-ui/react-toast`, `class-variance-authority`, `socket.io-client` (+7 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 1485 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **44 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions

- How does `KafkaTopic` connect proposal approval, execution recovery, and kill-switch handling?
- Which `AdvisoryStore` dependencies enforce account revisions and research provenance?
- Where do `BaseAgent`, Kafka messaging, and Redis state enforce execution capability checks?

## Local AST Run Audit

- Files selected: 410 (397 native AST inputs; 13 configuration inventories).
- Exported graph: **5,569 nodes, 17,598 edges, 185 communities**.
- Extraction, clustering, and initial export elapsed time: **17.438 seconds**. Label curation and review are separate.
- Actual extraction LLM usage: **0 input tokens, 0 output tokens, 0 external AI API calls**. Conversation tokens are outside this measurement.
- Native extraction was serial, with sorted inputs; clustering uses Graphify fixed random seeds. Reproducibility is bounded by installed parser and Graphify versions.
- Network connections and DNS were disabled in the extraction process. No dependencies were installed.
- All selected input SHA-256 hashes and project Git status were unchanged except for output files.
- HTML skipped because the graph has more than 5,000 nodes.

### Extraction Warnings and Limits

- warning: 5 .sql file(s) contributed nothing to the graph because a dependency is missing: tree_sitter_sql not installed. Install it with: pip install "graphifyy[sql]" (#1745)
- warning: 2 .tf file(s) contributed nothing to the graph because a dependency is missing: tree_sitter_hcl not installed. Install it with: pip install "graphifyy[terraform]" (#1745)
- warning: 16 code file(s) yielded no symbols (0.01 MB) — a data file, or source this extractor models no symbols for: dashboard/postcss.config.js, dashboard/tests/navigation.test.ts, dashboard/vite.config.ts, src/agents/__init__.py, src/agents/tier3_quant/__init__.py (+11 more)
- YAML is a top-level key inventory only; Dockerfiles are file inventory only. No YAML parser was installed.
- Raw extraction: 1,617 dangling-endpoint edges, 66 external-reference edges, 5 self-loops, and 749 collapsed undirected endpoint pairs. See diagnostics.md and extraction.json.
- Final graph endpoint verification: zero dangling edges. This does not validate correctness of resolved or inferred relationships.
- Static AST relationships do not establish runtime Kafka topic flow, Redis state behavior, or trading readiness.
- No PDF, image, document-semantic, vendor, dependency, agent-history, or memory processing was performed.

### Failed Native Extraction Files

- `infra/init/timescale-init.sql`
- `infra/migrations/001_accounting.sql`
- `infra/migrations/002_execution_recovery.sql`
- `infra/migrations/003_funding_performance.sql`
- `infra/migrations/004_ai_budget.sql`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`

- Intentionally skipped by native extraction: `dashboard/src/i18n/messages.json`.
- Working tree note: `graphify-out/` contains generated output; no Git ignore settings were changed. Share or commit only selected outputs.

## Architecture and Next Investigations

The static graph separates an agent/message fabric from an advisory research surface and a React dashboard. Shared Pydantic data contracts and `KafkaTopic` bridge intelligence, strategies, execution, monitoring, and their tests (`src/core/data/models.py:L24`). `BaseAgent` supplies lifecycle and capability checks (`src/agents/base_agent.py:L54`), with Kafka producer/consumer wrappers (`src/core/orchestrator/message_bus.py:L61,L147`) and Redis state (`src/core/orchestrator/state_manager.py:L35`). Risk and execution recovery form separate clusters. These are static relationships, not evidence that services are currently running or that Kafka delivery is correct.

The advisory API service assembles market data, account/evaluation policy, risk inputs, and research evidence (`src/api/services/advisory.py:L63`). Its SQLite `AdvisoryStore` is the most connected application abstraction (124 graph edges; `src/connectors/advisory/storage.py:L24`). The dashboard connects HTTP clients, WebSocket state, shared quote polling (`dashboard/src/lib/useLiveQuotes.ts:L26`), and localization. Backtesting, MES5m research, ML inference, and unit/integration suites form additional communities. Vendor implementation internals were excluded.

Five modules to investigate next, chosen for architectural reach and safety relevance rather than degree alone:

1. `src/core/data/models.py:L24` — central message/data contracts; `KafkaTopic` has 107 graph edges. Check schema and producer/consumer compatibility.
2. `src/agents/base_agent.py:L54` — shared lifecycle, capability guard, heartbeat, and shutdown behavior; `BaseAgent` has 77 graph edges.
3. `src/core/orchestrator/` — Kafka messaging and Redis health/trade gates. Trace freshness, retries, idempotence, and failure handling across both adapters.
4. `src/core/risk/` — risk metrics, position limits, and kill switch. Trace halt propagation into executor cancellation and recovery paths; AST alone cannot prove this behavior.
5. `src/connectors/advisory/storage.py:L24` — highest application coupling (124 graph edges). Verify account revisions, transactions, research evidence, and API consumers; 77 relationships involving `AdvisoryStore` are AST-inferred and need confirmation.

All INFERRED confidence labels in this run come from deterministic structural resolution. No semantic LLM extraction ran. Community names and this written review do not add entities or edges to the graph.

## Local Query Size Benchmark

The selected corpus contains 295,463 words. The local heuristic estimates 393,950 tokens for the full corpus versus 1,605 tokens per budgeted sample graph query. This is a text-size estimate, not measured LLM usage or evidence of complete answers. Actual extraction LLM usage remains zero.

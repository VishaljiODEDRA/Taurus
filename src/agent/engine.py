from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.allocation import AllocationDecision, CapitalAllocator, apply_planned_exits, reserve_trade_notional
from agent.broker import build_broker
from agent.committee import CommitteeResult, DecisionCommittee
from agent.config import AppConfig
from agent.data import build_market_data_provider
from agent.execution import ExecutionSimulator
from agent.exits import ExitManager
from agent.ledger import Ledger
from agent.llm import OpenAIContextAnalyzer
from agent.ml import OutcomeMemoryBuilder
from agent.monitoring import HealthMonitor
from agent.news import NewsEntityResolver, NewsProvider, NewsScorer
from agent.order_policy import ImmutablePreTradePolicy
from agent.portfolio import PortfolioOverlayReport, PortfolioRiskAnalyzer, PortfolioRiskReport
from agent.regime import MarketRegimeEngine
from agent.reliability import classify_trade_root_cause, veto_patterns_from_features
from agent.risk import RiskEngine, is_kill_switch_active
from agent.signals import SignalEngine
from etoro_api import EtoroApiError, EtoroClient
from models import (
    AgentCycleResult,
    MarketSnapshot,
    NewsContext,
    OrderRequest,
    OrderResult,
    PortfolioState,
    RiskDecision,
    SignalDecision,
)


class TradingAgent:
    def __init__(self, config: AppConfig, *, allow_live_cli: bool = False) -> None:
        self.config = config
        self.allow_live_cli = allow_live_cli
        self.ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        self.market_data = build_market_data_provider(config)
        self.news_provider = NewsProvider(config.news)
        self.news_scorer = NewsScorer(NewsEntityResolver.from_settings(config.news))
        self.signal_engine = SignalEngine(config.strategy, config.universe)
        self.regime_engine = MarketRegimeEngine(config.strategy)
        self.risk_engine = RiskEngine(config.risk, config.strategy, config.universe, self.ledger)
        self.portfolio_risk = PortfolioRiskAnalyzer(config.risk, config.strategy, config.universe)
        self.capital_allocator = CapitalAllocator(config.risk, config.strategy, config.universe)
        self.exit_manager = ExitManager(config.exits, config.strategy)
        self.monitor = HealthMonitor(config.monitoring, config.risk, self.ledger)
        self.pre_trade_policy = ImmutablePreTradePolicy(config.risk)
        self.outcome_memory = OutcomeMemoryBuilder()
        self.execution_simulator = ExecutionSimulator()
        self.committee = DecisionCommittee()
        self.llm = (
            OpenAIContextAnalyzer(
                config.secrets.openai_api_key,
                model=config.secrets.openai_model,
            )
            if config.news.use_openai_context
            else None
        )

    def scan(self) -> list[SignalDecision]:
        snapshots = self.market_data.snapshots(self._symbols_for_cycle(advance_cursor=False))
        contexts = self._news_contexts(snapshots)
        benchmark_symbol = self.config.universe.benchmark_symbol.upper()
        regime = self.regime_engine.classify(
            snapshots.get(benchmark_symbol),
            contexts.get(benchmark_symbol, NewsContext(symbol=benchmark_symbol)),
        )
        decisions = self.signal_engine.rank(
            snapshots,
            contexts,
            regime,
            outcome_profile=self._outcome_profile(),
        )
        return decisions[: self.config.agent.max_candidates_per_cycle]

    def run_once(self) -> AgentCycleResult:
        started_at = datetime.now(tz=UTC)
        if is_kill_switch_active(self.config.risk.kill_switch_path):
            finished_at = datetime.now(tz=UTC)
            return self._record_result(
                AgentCycleResult(
                started_at=started_at,
                finished_at=finished_at,
                decisions=(),
                position_reviews=(),
                risk_decisions=(),
                orders=(),
                halted=True,
                halt_reason="kill_switch_active",
                )
            )

        try:
            broker = build_broker(self.config, allow_live_cli=self.allow_live_cli)
        except (PermissionError, ValueError) as exc:
            finished_at = datetime.now(tz=UTC)
            return self._record_result(
                AgentCycleResult(
                started_at=started_at,
                finished_at=finished_at,
                decisions=(),
                position_reviews=(),
                risk_decisions=(),
                orders=(),
                halted=True,
                halt_reason=str(exc),
                )
            )

        try:
            snapshots = self.market_data.snapshots(self._symbols_for_cycle(advance_cursor=True))
            if not snapshots:
                raise EtoroApiError("no market snapshots available")
            contexts = self._news_contexts(snapshots)
            benchmark_symbol = self.config.universe.benchmark_symbol.upper()
            market_regime = self.regime_engine.classify(
                snapshots.get(benchmark_symbol),
                contexts.get(benchmark_symbol, NewsContext(symbol=benchmark_symbol)),
            )
            outcome_profile = self._outcome_profile()
            decisions = self.signal_engine.rank(snapshots, contexts, market_regime, outcome_profile)[
                : self.config.agent.max_candidates_per_cycle
            ]
            portfolio = self._portfolio_state(snapshots)
            self.ledger.record_cycle_data_history(
                cycle_id=started_at.isoformat(),
                snapshots=snapshots,
                contexts=contexts,
                portfolio=portfolio,
                market_regime=market_regime,
            )
            portfolio_risk_report = self.portfolio_risk.evaluate(
                portfolio=portfolio,
                all_snapshots=snapshots,
                benchmark_symbol=benchmark_symbol,
                market_regime=market_regime,
            )
            self.ledger.record_portfolio_risk_report(
                var_pct=portfolio_risk_report.var_95_pct,
                cvar_pct=portfolio_risk_report.cvar_95_pct,
                var_99_pct=portfolio_risk_report.var_99_pct,
                cvar_99_pct=portfolio_risk_report.cvar_99_pct,
                expected_shortfall_pct=portfolio_risk_report.expected_shortfall_95_pct,
                expected_shortfall_usd=portfolio_risk_report.expected_shortfall_95_usd,
                factors=portfolio_risk_report.factor_exposures,
                scenarios=portfolio_risk_report.scenario_losses,
                raw=portfolio_risk_report.as_dict(),
            )
        except EtoroApiError as exc:
            finished_at = datetime.now(tz=UTC)
            return self._record_result(
                AgentCycleResult(
                started_at=started_at,
                finished_at=finished_at,
                decisions=(),
                position_reviews=(),
                risk_decisions=(),
                orders=(),
                halted=True,
                halt_reason=f"data_or_portfolio_error: {exc}",
                )
            )
        risk_decisions: list[RiskDecision] = []
        orders: list[OrderResult] = []
        risk_by_symbol: dict[str, RiskDecision] = {}

        position_reviews, exit_decisions = self._position_reviews_and_exit_decisions(
            portfolio, snapshots, contexts
        )
        for review in position_reviews:
            self.ledger.record_position_review(review)
        planned_buy_portfolio = apply_planned_exits(portfolio, exit_decisions)
        allocation_plan = self.capital_allocator.allocate(
            decisions,
            planned_buy_portfolio,
            snapshots,
            benchmark_symbol=self.config.universe.benchmark_symbol,
            market_regime=market_regime,
        )
        decisions = self._attach_allocation_features(decisions, allocation_plan)
        exit_decisions = self._attach_execution_simulations(exit_decisions, {}, snapshots, portfolio)
        exit_decisions = self._attach_veto_memory_features(exit_decisions)
        exit_decisions, exit_committee_by_symbol = self._attach_committee_features(exit_decisions)
        decisions = self._attach_execution_simulations(decisions, allocation_plan, snapshots, planned_buy_portfolio)
        decisions = self._attach_veto_memory_features(decisions)
        decisions, committee_by_symbol = self._attach_committee_features(decisions)
        committee_by_symbol.update(exit_committee_by_symbol)
        buy_execution_portfolio = planned_buy_portfolio
        all_decisions = tuple(exit_decisions) + tuple(decisions)
        benchmark_symbol = self.config.universe.benchmark_symbol.upper()
        benchmark_snapshot = snapshots.get(benchmark_symbol)
        benchmark_context = contexts.get(benchmark_symbol, NewsContext(symbol=benchmark_symbol))

        for decision in all_decisions:
            self.ledger.record_decision(decision)
            if not decision.is_trade:
                continue
            snapshot = snapshots.get(decision.symbol)
            if not snapshot:
                continue
            allocation = self._allocation_for_decision(decision, allocation_plan)
            risk_portfolio = buy_execution_portfolio if decision.action == "BUY" else portfolio
            if decision.action == "BUY" and allocation is not None and not allocation.approved:
                risk = RiskDecision.reject(allocation.reason)
                risk_decisions.append(risk)
                risk_by_symbol[decision.symbol.upper()] = risk
                self.ledger.record_risk(decision.symbol, risk)
                continue
            committee_result = committee_by_symbol.get(decision.symbol.upper())
            if committee_result is not None and not committee_result.approved:
                risk = RiskDecision.reject("committee_rejected")
                risk_decisions.append(risk)
                risk_by_symbol[decision.symbol.upper()] = risk
                self.ledger.record_risk(decision.symbol, risk)
                continue
            risk = self.risk_engine.evaluate(
                decision,
                snapshot,
                risk_portfolio,
                cycle_started_at=started_at,
                benchmark_snapshot=benchmark_snapshot,
                benchmark_news_context=benchmark_context,
                all_snapshots=snapshots,
                market_regime=market_regime,
                proposed_target_notional_usd=(
                    allocation.target_notional_usd if allocation is not None and allocation.approved else None
                ),
                portfolio_overlay_report=(
                    self._portfolio_overlay_report(allocation)
                ),
            )
            risk_decisions.append(risk)
            risk_by_symbol[decision.symbol.upper()] = risk
            self.ledger.record_risk(decision.symbol, risk)
            if not risk.approved:
                continue
            order = self._order_request(decision, risk, snapshot, portfolio)
            policy = self.pre_trade_policy.evaluate(order=order, snapshot=snapshot, portfolio=portfolio)
            if not policy.approved:
                result = OrderResult(
                    accepted=False,
                    mode=self.config.execution.normalized_mode(),  # type: ignore[arg-type]
                    symbol=order.symbol,
                    action=order.action,
                    message=policy.reason,
                    raw={"policy_reason": policy.reason, "order": order.metadata},
                )
                orders.append(result)
                self.ledger.record_order(result)
                continue
            result = broker.execute(order)
            orders.append(result)
            self.ledger.record_order(result)
            self._record_execution_actual(decision=decision, snapshot=snapshot, result=result)
            if result.accepted and decision.action == "BUY":
                self.ledger.record_open_trade_context(
                    symbol=decision.symbol,
                    broker_order_id=result.broker_order_id,
                    entry_time=started_at.isoformat(),
                    entry_price=snapshot.rate.mid,
                    entry_notional_usd=risk.target_notional_usd,
                    features=decision.features,
                    risk_details={
                        **risk.details,
                        "stop_loss_rate": risk.stop_loss_rate,
                        "take_profit_rate": risk.take_profit_rate,
                    },
                )
            if result.accepted and decision.action == "SELL":
                self._record_closed_trade_outcome(
                    decision=decision,
                    risk=risk,
                    snapshot=snapshot,
                    portfolio=portfolio,
                    closed_at=started_at.isoformat(),
                )
            if decision.action == "BUY" and result.accepted:
                buy_execution_portfolio = reserve_trade_notional(
                    buy_execution_portfolio,
                    symbol=decision.symbol,
                    instrument_id=snapshot.instrument.instrument_id,
                    notional_usd=risk.target_notional_usd,
                )

        finished_at = datetime.now(tz=UTC)
        decorated_decisions = tuple(self._attach_risk_features(all_decisions, risk_by_symbol))
        self._record_feature_snapshots(
            decorated_decisions,
            cycle_id=started_at.isoformat(),
            snapshots=snapshots,
            contexts=contexts,
            market_regime=market_regime,
            benchmark_symbol=benchmark_symbol,
        )
        return self._record_result(
            AgentCycleResult(
            started_at=started_at,
            finished_at=finished_at,
            decisions=decorated_decisions,
            position_reviews=tuple(position_reviews),
            risk_decisions=tuple(risk_decisions),
            orders=tuple(orders),
            dashboard=self._build_dashboard(
                market_regime=market_regime,
                outcome_profile=outcome_profile,
                decisions=decorated_decisions,
                portfolio_risk_report=portfolio_risk_report,
            ),
            halted=False,
            )
        )

    def _news_contexts(self, snapshots: dict[str, MarketSnapshot]) -> dict[str, NewsContext]:
        items = self.news_provider.load_items()
        self.news_scorer.source_credibility = self.ledger.news_source_credibility_profiles()
        for row in self.news_scorer.source_quality_report(items)[:25]:
            self.ledger.record_news_source_stat(
                source=str(row["source"]),
                mentions=int(row["mentions"]),
                avg_sentiment=float(row["avg_sentiment"]),
                avg_catalyst=float(row["avg_catalyst"]),
                credibility_score=float(row["credibility_score"]),
                raw=dict(row),
            )
        contexts: dict[str, NewsContext] = {}
        for symbol in snapshots:
            context = self.news_scorer.context_for_symbol(symbol, items)
            if self.llm and self.llm.configured and context.items:
                llm_context = self.llm.analyze(symbol, context.items)
                if llm_context:
                    context = llm_context
            contexts[symbol] = context
        return contexts

    def _portfolio_state(self, snapshots: dict[str, MarketSnapshot]) -> PortfolioState:
        if self.config.secrets.etoro_api_key and self.config.secrets.etoro_user_key:
            client = EtoroClient(
                api_key=self.config.secrets.etoro_api_key,
                user_key=self.config.secrets.etoro_user_key,
                base_url=self.config.secrets.etoro_base_url,
                user_agent=self.config.secrets.etoro_user_agent,
            )
            environment = self._portfolio_environment()
            symbol_map = {
                snapshot.instrument.instrument_id: symbol for symbol, snapshot in snapshots.items()
            }
            try:
                return client.get_portfolio_state(environment, symbol_map)
            except EtoroApiError:
                if self.config.execution.normalized_mode() != "shadow":
                    raise

        return PortfolioState(nav_usd=10_000.0, available_cash_usd=10_000.0)

    def _portfolio_environment(self) -> str:
        mode = self.config.execution.normalized_mode()
        if mode == "live":
            return "real"
        if mode == "demo":
            return "demo"
        return self.config.execution.normalized_environment()

    def _order_request(
        self,
        decision: SignalDecision,
        risk: RiskDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
    ) -> OrderRequest:
        position = portfolio.position_for_symbol(decision.symbol)
        return OrderRequest(
            symbol=decision.symbol,
            instrument_id=snapshot.instrument.instrument_id,
            action=decision.action,
            amount_usd=risk.target_notional_usd,
            leverage=self.config.risk.max_leverage,
            stop_loss_rate=risk.stop_loss_rate,
            take_profit_rate=risk.take_profit_rate,
            trailing_stop=self.config.strategy.trailing_stop,
            position_id=position.position_id if position else None,
            dry_run=self.config.execution.normalized_mode() == "shadow",
            metadata={
                "score": decision.score,
                "confidence": decision.confidence,
                "reasons": decision.reasons,
                "features": decision.features,
                "risk_reason": risk.reason,
                "risk_details": risk.details,
            },
        )

    def _position_reviews_and_exit_decisions(
        self,
        portfolio: PortfolioState,
        snapshots: dict[str, MarketSnapshot],
        contexts: dict[str, NewsContext],
    ) -> tuple[list[SignalDecision], list[SignalDecision]]:
        position_reviews: list[SignalDecision] = []
        exit_decisions: list[SignalDecision] = []
        benchmark_symbol = self.config.universe.benchmark_symbol.upper()
        benchmark_snapshot = snapshots.get(benchmark_symbol)
        benchmark_context = contexts.get(benchmark_symbol, NewsContext(symbol=benchmark_symbol))
        for position in portfolio.positions:
            snapshot = snapshots.get(position.symbol.upper())
            if not snapshot:
                continue
            context = contexts.get(position.symbol.upper(), NewsContext(symbol=position.symbol))
            review = self.exit_manager.review_position(
                position,
                snapshot,
                context,
                benchmark_snapshot=benchmark_snapshot,
                benchmark_news_context=benchmark_context,
            )
            position_reviews.append(review)
            decision = self.exit_manager.evaluate(
                position,
                snapshot,
                context,
                benchmark_snapshot=benchmark_snapshot,
                benchmark_news_context=benchmark_context,
            )
            if decision:
                exit_decisions.append(decision)
        position_reviews.sort(
            key=lambda review: float(review.features.get("urgency_score", review.score)),
            reverse=True,
        )
        return position_reviews, exit_decisions

    def _record_result(self, result: AgentCycleResult) -> AgentCycleResult:
        self.monitor.record_cycle(result)
        return result

    def _attach_risk_features(
        self,
        decisions: tuple[SignalDecision, ...],
        risk_by_symbol: dict[str, RiskDecision],
    ) -> list[SignalDecision]:
        enriched: list[SignalDecision] = []
        for decision in decisions:
            risk = risk_by_symbol.get(decision.symbol.upper())
            if risk is None:
                enriched.append(decision)
                continue
            features = dict(decision.features)
            for key, value in risk.details.items():
                features[f"risk_{key}"] = value
            features["risk_approved"] = risk.approved
            features["risk_reason"] = risk.reason
            features["risk_target_notional_usd"] = risk.target_notional_usd
            enriched.append(replace(decision, features=features))
        return enriched

    def _allocation_for_decision(
        self,
        decision: SignalDecision,
        allocation_plan: dict[str, AllocationDecision],
    ) -> AllocationDecision | None:
        if decision.action != "BUY":
            return None
        return allocation_plan.get(decision.symbol.upper())

    def _attach_allocation_features(
        self,
        decisions: tuple[SignalDecision, ...] | list[SignalDecision],
        allocation_plan: dict[str, AllocationDecision],
    ) -> list[SignalDecision]:
        enriched: list[SignalDecision] = []
        for decision in decisions:
            allocation = allocation_plan.get(decision.symbol.upper())
            if decision.action != "BUY" or allocation is None:
                enriched.append(decision)
                continue
            features = dict(decision.features)
            features.update(
                {
                    "allocation_approved": allocation.approved,
                    "allocation_target_notional_usd": allocation.target_notional_usd,
                    "allocation_reason": allocation.reason,
                    "allocation_hhi": allocation.hhi,
                    "allocation_diversification_score": allocation.diversification_score,
                    "allocation_var_95_pct": allocation.var_95_pct,
                    "allocation_cvar_95_pct": allocation.cvar_95_pct,
                    "allocation_expected_shortfall_95_pct": allocation.expected_shortfall_95_pct,
                    "allocation_max_stress_loss_pct": allocation.max_stress_loss_pct,
                    "allocation_edge_size_multiplier": allocation.edge_size_multiplier,
                    "allocation_priority_score": allocation.priority_score,
                }
            )
            if allocation.scenario_losses:
                worst_name, worst_loss = max(
                    allocation.scenario_losses.items(),
                    key=lambda item: item[1],
                )
                features["allocation_worst_scenario"] = worst_name
                features["allocation_worst_scenario_loss_pct"] = worst_loss
            enriched.append(replace(decision, features=features))
        return enriched

    def _attach_execution_simulations(
        self,
        decisions: list[SignalDecision],
        allocation_plan: dict[str, AllocationDecision],
        snapshots: dict[str, MarketSnapshot],
        portfolio: PortfolioState,
    ) -> list[SignalDecision]:
        enriched: list[SignalDecision] = []
        for decision in decisions:
            snapshot = snapshots.get(decision.symbol.upper())
            if snapshot is None or not decision.is_trade:
                enriched.append(decision)
                continue
            allocation = allocation_plan.get(decision.symbol.upper())
            position = portfolio.position_for_symbol(decision.symbol)
            target = allocation.target_notional_usd if allocation and allocation.approved else 0.0
            if decision.action == "SELL" and position is not None:
                target = position.current_value_usd
            simulation = self.execution_simulator.simulate(
                decision=decision,
                snapshot=snapshot,
                portfolio=portfolio,
                target_notional_usd=target,
                historical_profile=self.ledger.execution_slippage_profile(
                    symbol=decision.symbol,
                    action=decision.action,
                    mode=self.config.execution.normalized_mode(),
                ),
            )
            self.ledger.record_execution_simulation(
                simulation_id=simulation.simulation_id,
                symbol=simulation.symbol,
                action=simulation.action,
                quality_score=simulation.quality_score,
                expected_slippage_bps=simulation.expected_slippage_bps,
                fill_probability=simulation.fill_probability,
                target_notional_usd=simulation.target_notional_usd,
                raw=simulation.as_dict(),
            )
            features = dict(decision.features)
            features.update(simulation.as_features())
            enriched.append(replace(decision, features=features))
        return enriched

    def _attach_veto_memory_features(self, decisions: list[SignalDecision]) -> list[SignalDecision]:
        enriched: list[SignalDecision] = []
        for decision in decisions:
            if not decision.is_trade:
                enriched.append(decision)
                continue
            veto = self.ledger.veto_memory_for_features(decision.features)
            if not veto:
                enriched.append(decision)
                continue
            features = dict(decision.features)
            features.update(
                {
                    "veto_memory_score": float(veto.get("veto_score", 0.0) or 0.0),
                    "veto_memory_pattern": str(veto.get("pattern_label", "")),
                    "veto_memory_loss_count": int(veto.get("loss_count", 0) or 0),
                }
            )
            enriched.append(replace(decision, features=features))
        return enriched

    def _record_execution_actual(
        self,
        *,
        decision: SignalDecision,
        snapshot: MarketSnapshot,
        result: OrderResult,
    ) -> None:
        simulation_id = decision.features.get("execution_simulation_id")
        if not isinstance(simulation_id, str) or not simulation_id:
            return
        actual_fill_price = _extract_fill_price(result.raw)
        actual_slippage_bps = _actual_slippage_bps(
            action=decision.action,
            reference_price=_as_float(decision.features.get("execution_sim_reference_price"), snapshot.rate.mid),
            actual_fill_price=actual_fill_price,
        )
        raw = {
            "mode": result.mode,
            "accepted": result.accepted,
            "broker_order_id": result.broker_order_id,
            "message": result.message,
            "actual_fill_price": actual_fill_price,
            "actual_slippage_bps": actual_slippage_bps,
        }
        self.ledger.record_execution_actual(
            simulation_id=simulation_id,
            filled=result.accepted,
            actual_fill_price=actual_fill_price,
            actual_slippage_bps=actual_slippage_bps,
            mode=result.mode,
            raw=raw,
        )

    def _attach_committee_features(
        self,
        decisions: list[SignalDecision],
    ) -> tuple[list[SignalDecision], dict[str, CommitteeResult]]:
        enriched: list[SignalDecision] = []
        committee_by_symbol: dict[str, CommitteeResult] = {}
        for decision in decisions:
            result = self.committee.evaluate(decision)
            committee_by_symbol[decision.symbol.upper()] = result
            self.ledger.record_committee_vote(
                symbol=decision.symbol,
                final_action=decision.action,
                consensus_score=result.consensus_score,
                approved=result.approved,
                votes=result.as_dict(),
            )
            features = dict(decision.features)
            features.update(result.as_features())
            enriched.append(replace(decision, features=features))
        return enriched, committee_by_symbol

    def _record_feature_snapshots(
        self,
        decisions: tuple[SignalDecision, ...],
        *,
        cycle_id: str,
        snapshots: dict[str, MarketSnapshot],
        contexts: dict[str, NewsContext],
        market_regime,
        benchmark_symbol: str,
    ) -> None:
        benchmark_snapshot = snapshots.get(benchmark_symbol.upper())
        for decision in decisions:
            self.ledger.record_feature_snapshot(
                symbol=decision.symbol,
                action=decision.action,
                score=decision.score,
                confidence=decision.confidence,
                features=decision.features,
                cycle_id=cycle_id,
                feature_set="cycle_decision",
            )
            self.ledger.record_cycle_features(
                _cycle_feature_row(
                    decision=decision,
                    cycle_id=cycle_id,
                    snapshot=snapshots.get(decision.symbol.upper()),
                    benchmark_snapshot=benchmark_snapshot,
                    context=contexts.get(decision.symbol.upper(), NewsContext(symbol=decision.symbol)),
                    benchmark_symbol=benchmark_symbol,
                    market_regime=market_regime,
                )
            )

    def _portfolio_overlay_report(
        self,
        allocation: AllocationDecision | None,
    ) -> PortfolioOverlayReport | None:
        if allocation is None or not allocation.approved:
            return None
        return PortfolioOverlayReport(
            approved=True,
            adjusted_notional_usd=allocation.target_notional_usd,
            reason=allocation.reason,
            hhi=allocation.hhi,
            diversification_score=allocation.diversification_score,
            var_95_pct=allocation.var_95_pct,
            cvar_95_pct=allocation.cvar_95_pct,
            expected_shortfall_95_pct=allocation.expected_shortfall_95_pct,
            max_stress_loss_pct=allocation.max_stress_loss_pct,
            scenario_losses=allocation.scenario_losses or {},
        )

    def _symbols_for_cycle(self, *, advance_cursor: bool) -> tuple[str, ...]:
        symbols = list(self.config.universe.symbols)
        benchmark = self.config.universe.benchmark_symbol.upper()
        max_symbols = self.config.universe.max_symbols_per_cycle
        if max_symbols <= 0 or max_symbols >= len(symbols):
            return self.config.universe.all_symbols

        tradable_symbols = [symbol.upper() for symbol in symbols if symbol.upper() != benchmark]
        if not tradable_symbols:
            return (benchmark,)

        cursor_path = Path(self.config.universe.cursor_path)
        cursor = _read_cursor(cursor_path)
        take = max(max_symbols - 1, 1)
        selected = [
            tradable_symbols[(cursor + offset) % len(tradable_symbols)]
            for offset in range(min(take, len(tradable_symbols)))
        ]
        if advance_cursor:
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            cursor_path.write_text(str((cursor + take) % len(tradable_symbols)), encoding="utf-8")
        return tuple(selected + [benchmark])

    def _outcome_profile(self):
        return self.outcome_memory.build(self.ledger.trade_outcomes(limit=500))

    def _build_dashboard(
        self,
        *,
        market_regime,
        outcome_profile,
        decisions: tuple[SignalDecision, ...],
        portfolio_risk_report: PortfolioRiskReport | None = None,
    ) -> dict[str, object]:
        buy_decisions = [decision for decision in decisions if decision.action == "BUY"]
        execution_scores = [
            float(decision.features.get("risk_execution_quality_score", 0.0))
            for decision in buy_decisions
            if isinstance(decision.features.get("risk_execution_quality_score"), (int, float))
        ]
        average_execution_quality = (
            sum(execution_scores) / len(execution_scores) if execution_scores else 0.0
        )
        dashboard = {
            "regime_probabilities": dict(getattr(market_regime, "probabilities", {}) or {}),
            "learning_summary": {
                "sample_count": outcome_profile.sample_count,
                "win_rate": outcome_profile.global_stats.win_rate,
                "average_return": outcome_profile.global_stats.average_return,
                "average_holding_days": outcome_profile.global_stats.average_holding_days,
            },
            "execution_summary": {
                "buy_candidates": len(buy_decisions),
                "average_execution_quality_score": average_execution_quality,
                "min_execution_quality_score": min(execution_scores) if execution_scores else 0.0,
            },
            "committee_summary": _committee_summary(decisions),
            "tradability_summary": _tradability_summary(decisions),
        }
        if portfolio_risk_report is not None:
            dashboard["portfolio_risk"] = portfolio_risk_report.as_dict()
        return dashboard

    def _record_closed_trade_outcome(
        self,
        *,
        decision: SignalDecision,
        risk: RiskDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        closed_at: str,
    ) -> None:
        position = portfolio.position_for_symbol(decision.symbol)
        if position is None:
            return
        entry_context = self.ledger.consume_open_trade_context(decision.symbol)
        invested_usd = max(position.invested_usd, 0.0)
        pnl_usd = position.current_value_usd - invested_usd
        return_pct = pnl_usd / invested_usd if invested_usd > 0 else 0.0
        entry_time = entry_context.get("entry_time") if entry_context else None
        holding_days = 0
        if entry_time:
            holding_days = max(
                0,
                (datetime.fromisoformat(closed_at) - datetime.fromisoformat(entry_time)).days,
            )
        self.ledger.record_trade_outcome(
            symbol=decision.symbol,
            pnl_usd=pnl_usd,
            return_pct=return_pct,
            holding_days=holding_days,
            source="closed_position_order",
            entry_order_id=(entry_context or {}).get("broker_order_id"),
            exit_order_id=None,
            entry_time=entry_time,
            exit_time=closed_at,
            raw={
                "entry_context": entry_context or {},
                "exit_features": decision.features,
                "exit_risk_details": risk.details,
                "exit_price": snapshot.rate.mid,
                "position_snapshot": position.__dict__,
            },
        )
        raw = {
            "entry_context": entry_context or {},
            "exit_features": decision.features,
            "exit_risk_details": risk.details,
            "exit_price": snapshot.rate.mid,
            "position_snapshot": position.__dict__,
        }
        cause = classify_trade_root_cause(raw, return_pct)
        self.ledger.record_trade_root_cause(
            symbol=decision.symbol,
            outcome_label=1 if return_pct > 0 else 0,
            primary_cause=str(cause["primary_cause"]),
            severity=float(cause["severity"]),
            raw=cause,
        )
        entry_features = (entry_context or {}).get("features_json", {})
        if isinstance(entry_features, dict):
            for pattern_key, pattern_label in veto_patterns_from_features(entry_features):
                self.ledger.update_decision_veto_memory(
                    pattern_key=pattern_key,
                    symbol=decision.symbol,
                    pattern_label=pattern_label,
                    return_pct=return_pct,
                    raw={"root_cause": cause},
                )


def _read_cursor(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return 0


def _committee_summary(decisions: tuple[SignalDecision, ...]) -> dict[str, object]:
    trade_scored = [
        float(decision.features.get("committee_consensus_score", 0.0))
        for decision in decisions
        if decision.is_trade
        and isinstance(decision.features.get("committee_consensus_score"), (int, float))
    ]
    automatic_hold_approvals = [
        decision
        for decision in decisions
        if decision.action == "HOLD"
        and decision.features.get("committee_reason") == "hold_decision_no_order_risk"
    ]
    all_scored = [
        float(decision.features.get("committee_consensus_score", 0.0))
        for decision in decisions
        if isinstance(decision.features.get("committee_consensus_score"), (int, float))
    ]
    rejected = [
        decision.symbol
        for decision in decisions
        if decision.features.get("committee_approved") is False and decision.action == "BUY"
    ]
    return {
        "reviewed": len(trade_scored),
        "total_decisions": len(decisions),
        "automatic_hold_approvals": len(automatic_hold_approvals),
        "average_consensus": sum(trade_scored) / len(trade_scored) if trade_scored else 0.0,
        "average_all_consensus": sum(all_scored) / len(all_scored) if all_scored else 0.0,
        "rejected_symbols": rejected,
    }


def _tradability_summary(decisions: tuple[SignalDecision, ...]) -> dict[str, object]:
    reason_counts = {
        "not_currently_tradable": 0,
        "exchange_closed": 0,
        "buying_disabled": 0,
    }
    blocked_symbols: list[str] = []
    for decision in decisions:
        if decision.action != "HOLD":
            continue
        reason_text = " ".join(decision.reasons).lower()
        blocked = False
        if "not currently tradable" in reason_text:
            reason_counts["not_currently_tradable"] += 1
            blocked = True
        if "exchange closed" in reason_text:
            reason_counts["exchange_closed"] += 1
            blocked = True
        if "buying disabled" in reason_text:
            reason_counts["buying_disabled"] += 1
            blocked = True
        if blocked:
            blocked_symbols.append(decision.symbol)

    blocked_count = len(blocked_symbols)
    cycle_blocked = bool(decisions) and blocked_count == len(decisions)
    return {
        "blocked_count": blocked_count,
        "total_decisions": len(decisions),
        "cycle_classification": (
            "market_closed_or_tradability_blocked" if cycle_blocked else "mixed_or_tradeable"
        ),
        "not_currently_tradable": reason_counts["not_currently_tradable"],
        "exchange_closed": reason_counts["exchange_closed"],
        "buying_disabled": reason_counts["buying_disabled"],
        "sample_symbols": blocked_symbols[:10],
    }


def _cycle_feature_row(
    *,
    decision: SignalDecision,
    cycle_id: str,
    snapshot: MarketSnapshot | None,
    benchmark_snapshot: MarketSnapshot | None,
    context: NewsContext,
    benchmark_symbol: str,
    market_regime,
) -> dict[str, object]:
    features = decision.features
    symbol_return_21d = _snapshot_return(snapshot, 21)
    benchmark_return_21d = _snapshot_return(benchmark_snapshot, 21)
    probabilities = dict(getattr(market_regime, "probabilities", {}) or {})
    return {
        "cycle_id": cycle_id,
        "symbol": decision.symbol,
        "benchmark_symbol": benchmark_symbol,
        "action": decision.action,
        "is_trade": decision.is_trade,
        "decision_score": decision.score,
        "decision_confidence": decision.confidence,
        "symbol_last_price": snapshot.rate.mid if snapshot else 0.0,
        "symbol_spread_bps": snapshot.rate.spread_bps if snapshot else 0.0,
        "symbol_return_1d_pct": _snapshot_return(snapshot, 1),
        "symbol_return_5d_pct": _snapshot_return(snapshot, 5),
        "symbol_return_21d_pct": symbol_return_21d,
        "symbol_volatility_20d": _snapshot_volatility(snapshot, 20),
        "benchmark_last_price": benchmark_snapshot.rate.mid if benchmark_snapshot else 0.0,
        "benchmark_return_1d_pct": _snapshot_return(benchmark_snapshot, 1),
        "benchmark_return_5d_pct": _snapshot_return(benchmark_snapshot, 5),
        "benchmark_return_21d_pct": benchmark_return_21d,
        "benchmark_volatility_20d": _snapshot_volatility(benchmark_snapshot, 20),
        "relative_strength_21d": symbol_return_21d - benchmark_return_21d,
        "news_sentiment": context.sentiment_score,
        "news_catalyst": context.catalyst_score,
        "news_item_count": len(context.items),
        "news_source_count": len({item.source for item in context.items if item.source}),
        "regime_name": getattr(market_regime, "name", ""),
        "regime_confidence": getattr(market_regime, "confidence", 0.0),
        "regime_stress_score": getattr(market_regime, "stress_score", 0.0),
        "regime_size_multiplier": getattr(market_regime, "size_multiplier", 1.0),
        "regime_bullish_probability": _probability(probabilities, "bullish"),
        "regime_weak_probability": _probability(probabilities, "weak"),
        "regime_volatile_probability": _probability(probabilities, "volatile"),
        "regime_risk_off_probability": _probability(probabilities, "risk_off"),
        "regime_event_driven_probability": _probability(probabilities, "event_driven"),
        "allocation_approved": features.get("allocation_approved"),
        "allocation_target_notional_usd": features.get("allocation_target_notional_usd", 0.0),
        "allocation_hhi": features.get("allocation_hhi", 0.0),
        "allocation_diversification_score": features.get("allocation_diversification_score", 0.0),
        "allocation_max_stress_loss_pct": features.get("allocation_max_stress_loss_pct", 0.0),
        "allocation_priority_score": features.get("allocation_priority_score", 0.0),
        "timing_confidence": features.get("timing_confidence", 0.0),
        "timing_earliest_days": features.get("timing_earliest_days", 0.0),
        "timing_likely_days": features.get("timing_likely_days", 0.0),
        "timing_latest_days": features.get("timing_latest_days", 0.0),
        "timing_invalidation_days": features.get("timing_invalidation_days", 0.0),
        "execution_quality_score": features.get(
            "execution_sim_quality_score",
            features.get("risk_execution_quality_score", 0.0),
        ),
        "expected_slippage_bps": features.get(
            "execution_sim_expected_slippage_bps",
            features.get("risk_expected_slippage_bps", 0.0),
        ),
        "fill_probability": features.get("execution_sim_fill_probability", 0.0),
        "liquidity_score": features.get("execution_sim_liquidity_score", 0.0),
        "committee_approved": features.get("committee_approved"),
        "committee_consensus_score": features.get("committee_consensus_score", 0.0),
        "risk_approved": features.get("risk_approved"),
        "risk_target_notional_usd": features.get("risk_target_notional_usd", 0.0),
        "risk_stop_loss_pct": features.get("adaptive_stop_loss_pct", 0.0),
        "risk_take_profit_pct": features.get("adaptive_take_profit_pct", 0.0),
        "raw_features": features,
    }


def _snapshot_return(snapshot: MarketSnapshot | None, periods: int) -> float:
    if snapshot is None or len(snapshot.candles) <= periods:
        return 0.0
    start = snapshot.candles[-periods - 1].close
    end = snapshot.candles[-1].close
    if start <= 0:
        return 0.0
    return (end - start) / start


def _snapshot_volatility(snapshot: MarketSnapshot | None, periods: int) -> float:
    if snapshot is None or len(snapshot.candles) < 3:
        return 0.0
    selected = snapshot.candles[-periods - 1 :] if len(snapshot.candles) > periods else snapshot.candles
    returns: list[float] = []
    for previous, current in zip(selected, selected[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return variance ** 0.5


def _probability(probabilities: dict[str, object], key: str) -> float:
    try:
        return float(probabilities.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _extract_fill_price(payload: Any) -> float | None:
    price_keys = {
        "executionrate",
        "execution_rate",
        "openrate",
        "open_rate",
        "closerate",
        "close_rate",
        "averageprice",
        "average_price",
        "fillprice",
        "filledprice",
        "dealrate",
        "price",
        "rate",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in price_keys:
                parsed = _as_float(value, 0.0)
                if parsed > 0:
                    return parsed
        for value in payload.values():
            nested = _extract_fill_price(value)
            if nested is not None:
                return nested
    if isinstance(payload, (list, tuple)):
        for item in payload:
            nested = _extract_fill_price(item)
            if nested is not None:
                return nested
    return None


def _actual_slippage_bps(*, action: str, reference_price: float, actual_fill_price: float | None) -> float | None:
    if actual_fill_price is None or reference_price <= 0:
        return None
    if action == "SELL":
        return ((reference_price - actual_fill_price) / reference_price) * 10_000
    return ((actual_fill_price - reference_price) / reference_price) * 10_000


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

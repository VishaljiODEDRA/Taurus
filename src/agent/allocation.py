from __future__ import annotations

from dataclasses import dataclass

from agent.config import RiskSettings, StrategySettings, UniverseSettings
from agent.portfolio import PortfolioOptimizer
from agent.regime import MarketRegime
from models import MarketSnapshot, PortfolioPosition, PortfolioState, SignalDecision


@dataclass(frozen=True)
class AllocationDecision:
    symbol: str
    approved: bool
    target_notional_usd: float
    reason: str
    hhi: float = 0.0
    diversification_score: float = 1.0
    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0
    expected_shortfall_95_pct: float = 0.0
    max_stress_loss_pct: float = 0.0
    scenario_losses: dict[str, float] | None = None
    edge_size_multiplier: float = 1.0
    priority_score: float = 0.0


class CapitalAllocator:
    def __init__(self, risk: RiskSettings, strategy: StrategySettings, universe: UniverseSettings) -> None:
        self.risk = risk
        self.strategy = strategy
        self.universe = universe
        self.portfolio_optimizer = PortfolioOptimizer(risk, strategy, universe)

    def allocate(
        self,
        decisions: tuple[SignalDecision, ...] | list[SignalDecision],
        portfolio: PortfolioState,
        all_snapshots: dict[str, MarketSnapshot],
        *,
        benchmark_symbol: str,
        market_regime: MarketRegime | None,
    ) -> dict[str, AllocationDecision]:
        allocations: dict[str, AllocationDecision] = {}
        working_portfolio = portfolio
        buy_candidates = [decision for decision in decisions if decision.action == "BUY"]
        target_plan = self._target_plan(buy_candidates, portfolio, market_regime)
        priorities = {
            decision.symbol.upper(): self._priority_score(decision, portfolio)
            for decision in buy_candidates
        }
        edge_size_multipliers = {
            decision.symbol.upper(): self._edge_size_multiplier(decision)
            for decision in buy_candidates
        }

        for decision in buy_candidates:
            symbol = decision.symbol.upper()
            if symbol in allocations:
                allocations[symbol] = AllocationDecision(
                    symbol=symbol,
                    approved=False,
                    target_notional_usd=0.0,
                    reason="duplicate_buy_candidate",
                )
                continue

            snapshot = all_snapshots.get(symbol)
            if snapshot is None:
                allocations[symbol] = AllocationDecision(
                    symbol=symbol,
                    approved=False,
                    target_notional_usd=0.0,
                    reason="allocation_snapshot_missing",
                )
                continue

            base_target = round(target_plan.get(symbol, 0.0), 2)

            if base_target < self.risk.min_order_usd:
                allocations[symbol] = AllocationDecision(
                    symbol=symbol,
                    approved=False,
                    target_notional_usd=0.0,
                    reason="allocation_target_too_small",
                )
                continue

            overlay = self.portfolio_optimizer.evaluate_candidate(
                symbol=symbol,
                target_notional_usd=base_target,
                portfolio=working_portfolio,
                all_snapshots=all_snapshots,
                benchmark_symbol=benchmark_symbol,
                market_regime=market_regime,
            )
            allocations[symbol] = AllocationDecision(
                symbol=symbol,
                approved=overlay.approved,
                target_notional_usd=overlay.adjusted_notional_usd,
                reason=overlay.reason,
                hhi=overlay.hhi,
                diversification_score=overlay.diversification_score,
                var_95_pct=overlay.var_95_pct,
                cvar_95_pct=overlay.cvar_95_pct,
                expected_shortfall_95_pct=overlay.expected_shortfall_95_pct,
                max_stress_loss_pct=overlay.max_stress_loss_pct,
                scenario_losses=overlay.scenario_losses,
                edge_size_multiplier=edge_size_multipliers.get(symbol, 1.0),
                priority_score=priorities.get(symbol, 0.0),
            )
            if overlay.approved and overlay.adjusted_notional_usd > 0:
                working_portfolio = reserve_trade_notional(
                    working_portfolio,
                    symbol=symbol,
                    instrument_id=snapshot.instrument.instrument_id,
                    notional_usd=overlay.adjusted_notional_usd,
                )

        return allocations

    def _target_plan(
        self,
        decisions: list[SignalDecision],
        portfolio: PortfolioState,
        market_regime: MarketRegime | None,
    ) -> dict[str, float]:
        if not decisions:
            return {}

        regime_multiplier = (
            _regime_size_multiplier(self.risk, market_regime) if market_regime is not None else 1.0
        )
        base_position_cap = self.risk.max_position_pct_nav * portfolio.nav_usd * regime_multiplier
        available_budget = max(portfolio.available_cash_usd * 0.95, 0.0)
        priorities = {
            decision.symbol.upper(): self._priority_score(decision, portfolio)
            for decision in decisions
        }
        position_caps = {
            decision.symbol.upper(): base_position_cap * self._edge_size_multiplier(decision)
            for decision in decisions
        }
        remaining_budget = available_budget
        remaining_symbols = {
            decision.symbol.upper()
            for decision in sorted(
                decisions,
                key=lambda item: priorities[item.symbol.upper()],
                reverse=True,
            )
        }
        targets = {symbol: 0.0 for symbol in priorities}

        while remaining_budget >= self.risk.min_order_usd and remaining_symbols:
            total_priority = sum(priorities[symbol] for symbol in remaining_symbols)
            if total_priority <= 0:
                break

            allocated_this_round = 0.0
            saturated: set[str] = set()
            for symbol in tuple(remaining_symbols):
                share = remaining_budget * (priorities[symbol] / total_priority)
                existing = portfolio.position_for_symbol(symbol)
                existing_value = max(existing.current_value_usd, 0.0) if existing else 0.0
                remaining_cap = max(position_caps[symbol] - existing_value - targets[symbol], 0.0)
                increment = min(share, remaining_cap)
                if increment < self.risk.min_order_usd:
                    saturated.add(symbol)
                    continue
                targets[symbol] += increment
                allocated_this_round += increment
                if remaining_cap - increment < self.risk.min_order_usd:
                    saturated.add(symbol)
            if allocated_this_round < self.risk.min_order_usd:
                break
            remaining_budget = max(remaining_budget - allocated_this_round, 0.0)
            remaining_symbols -= saturated

        return {symbol: round(notional, 2) for symbol, notional in targets.items()}

    def _priority_score(self, decision: SignalDecision, portfolio: PortfolioState) -> float:
        score_component = max(decision.score, 0.0)
        confidence_component = max(decision.confidence, 0.0)
        momentum_component = float(decision.features.get("momentum_strength", 0.5))
        market_component = float(decision.features.get("market_regime_strength", 0.5))
        catalyst_component = float(decision.features.get("news_catalyst", 0.5))
        edge_component = float(decision.features.get("meta_learned_edge", 0.5))
        expected_return_component = _clamp(0.5 + float(decision.features.get("meta_expected_return", 0.0)) * 20)
        sector_penalty = self._sector_penalty(decision.symbol, portfolio)
        crowding_penalty = 0.35 if portfolio.position_for_symbol(decision.symbol) else 0.0
        raw_priority = (
            0.28 * score_component
            + 0.18 * confidence_component
            + 0.15 * momentum_component
            + 0.10 * market_component
            + 0.09 * catalyst_component
            + 0.14 * edge_component
            + 0.06 * expected_return_component
        )
        adjusted_priority = raw_priority * max(0.15, 1.0 - sector_penalty - crowding_penalty)
        return max(adjusted_priority, 0.01)

    def _edge_size_multiplier(self, decision: SignalDecision) -> float:
        if not self.strategy.edge_sizing_enabled:
            return 1.0
        learned_edge = _clamp(float(decision.features.get("meta_learned_edge", 0.5)))
        expected_return = float(decision.features.get("meta_expected_return", 0.0))
        approval = _clamp(float(decision.features.get("meta_approval_score", 0.5)))
        edge_strength = _clamp(
            0.58 * learned_edge
            + 0.22 * _clamp(0.5 + expected_return * 18)
            + 0.20 * approval
        )
        uncertainty = _uncertainty_penalty(decision.features)
        raw_multiplier = 1.0 + ((edge_strength - 0.5) * 0.9)
        return _clamp(
            raw_multiplier * (1.0 - uncertainty),
            self.strategy.min_edge_size_multiplier,
            self.strategy.max_edge_size_multiplier,
        )

    def _sector_penalty(self, symbol: str, portfolio: PortfolioState) -> float:
        sector = self.universe.sector_map.get(symbol.upper(), "").lower()
        if not sector:
            return 0.0
        if self.risk.max_sector_exposure_pct <= 0:
            return 0.0
        sector_value = sum(
            max(position.current_value_usd, 0.0)
            for position in portfolio.positions
            if self.universe.sector_map.get(position.symbol.upper(), "").lower() == sector
        )
        sector_exposure = sector_value / max(portfolio.nav_usd, 1.0)
        return min(sector_exposure / self.risk.max_sector_exposure_pct, 0.55)


def apply_planned_exits(
    portfolio: PortfolioState,
    exit_decisions: tuple[SignalDecision, ...] | list[SignalDecision],
) -> PortfolioState:
    exit_symbols = {decision.symbol.upper() for decision in exit_decisions if decision.action == "SELL"}
    if not exit_symbols:
        return portfolio

    released_cash = 0.0
    remaining_positions: list[PortfolioPosition] = []
    for position in portfolio.positions:
        if position.symbol.upper() in exit_symbols:
            released_cash += max(position.current_value_usd, 0.0)
            continue
        remaining_positions.append(position)

    return PortfolioState(
        nav_usd=portfolio.nav_usd,
        available_cash_usd=portfolio.available_cash_usd + released_cash,
        daily_pnl_pct=portfolio.daily_pnl_pct,
        rolling_drawdown_pct=portfolio.rolling_drawdown_pct,
        positions=tuple(remaining_positions),
        open_order_symbols=portfolio.open_order_symbols,
    )


def reserve_trade_notional(
    portfolio: PortfolioState,
    *,
    symbol: str,
    instrument_id: int,
    notional_usd: float,
) -> PortfolioState:
    symbol_upper = symbol.upper()
    updated_positions: list[PortfolioPosition] = []
    matched = False
    for position in portfolio.positions:
        if position.symbol.upper() != symbol_upper:
            updated_positions.append(position)
            continue
        matched = True
        updated_positions.append(
            PortfolioPosition(
                symbol=position.symbol,
                instrument_id=position.instrument_id,
                position_id=position.position_id,
                units=position.units,
                invested_usd=position.invested_usd + notional_usd,
                current_value_usd=position.current_value_usd + notional_usd,
                pnl_usd=position.pnl_usd,
                open_rate=position.open_rate,
            )
        )
    if not matched:
        updated_positions.append(
            PortfolioPosition(
                symbol=symbol_upper,
                instrument_id=instrument_id,
                position_id=f"allocation-{symbol_upper}",
                units=0.0,
                invested_usd=notional_usd,
                current_value_usd=notional_usd,
            )
        )

    return PortfolioState(
        nav_usd=portfolio.nav_usd,
        available_cash_usd=max(portfolio.available_cash_usd - notional_usd, 0.0),
        daily_pnl_pct=portfolio.daily_pnl_pct,
        rolling_drawdown_pct=portfolio.rolling_drawdown_pct,
        positions=tuple(updated_positions),
        open_order_symbols=portfolio.open_order_symbols,
    )


def _regime_size_multiplier(risk: RiskSettings, market_regime: MarketRegime) -> float:
    if market_regime.name == "volatile":
        return risk.regime_volatile_size_multiplier
    if market_regime.name == "weak":
        return risk.regime_weak_size_multiplier
    if market_regime.name == "bullish":
        return risk.regime_bullish_size_multiplier
    return market_regime.size_multiplier


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)


def _uncertainty_penalty(features: dict[str, object]) -> float:
    data_quality = 0.18 if not bool(features.get("has_sufficient_chart_history", True)) else 0.0
    regime_confidence = float(features.get("regime_confidence", features.get("market_regime_strength", 0.6)) or 0.6)
    regime_penalty = max(0.0, 0.55 - regime_confidence) * 0.35
    news_noise = max(0.0, 0.5 - float(features.get("news_source_credibility", 0.75) or 0.75)) * 0.20
    execution_penalty = max(0.0, 0.70 - float(features.get("execution_sim_fill_probability", 0.75) or 0.75)) * 0.20
    committee_penalty = max(0.0, 0.60 - float(features.get("committee_consensus_score", 0.65) or 0.65)) * 0.15
    return _clamp(data_quality + regime_penalty + news_noise + execution_penalty + committee_penalty, 0.0, 0.45)

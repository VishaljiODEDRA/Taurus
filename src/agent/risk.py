from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent.allocation import _regime_size_multiplier
from agent.chart import ChartAnalyzer
from agent.config import RiskSettings, StrategySettings, UniverseSettings
from agent.ledger import Ledger
from agent.portfolio import PortfolioOverlayReport, PortfolioOptimizer
from agent.regime import MarketRegime
from models import MarketSnapshot, NewsContext, PortfolioState, RiskDecision, SignalDecision


class RiskEngine:
    def __init__(
        self,
        risk: RiskSettings,
        strategy: StrategySettings,
        universe: UniverseSettings,
        ledger: Ledger | None = None,
    ) -> None:
        self.risk = risk
        self.strategy = strategy
        self.universe = universe
        self.ledger = ledger
        self.chart_analyzer = ChartAnalyzer(strategy)
        self.portfolio_optimizer = PortfolioOptimizer(risk, strategy, universe)

    def evaluate(
        self,
        signal: SignalDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        *,
        cycle_started_at: datetime | None = None,
        benchmark_snapshot: MarketSnapshot | None = None,
        benchmark_news_context: NewsContext | None = None,
        all_snapshots: dict[str, MarketSnapshot] | None = None,
        market_regime: MarketRegime | None = None,
        proposed_target_notional_usd: float | None = None,
        portfolio_overlay_report: PortfolioOverlayReport | None = None,
    ) -> RiskDecision:
        if is_kill_switch_active(self.risk.kill_switch_path):
            return RiskDecision.reject("kill_switch_active")

        if signal.action == "HOLD":
            return RiskDecision.reject("hold_signal")

        if signal.action == "SELL":
            return self._evaluate_exit(signal, portfolio)

        if self.universe.long_only and signal.action != "BUY":
            return RiskDecision.reject("shorting_disabled")

        if not _asset_type_allowed(snapshot.instrument.asset_type, self.universe.allowed_asset_types):
            return RiskDecision.reject("asset_type_not_allowed")

        if portfolio.daily_pnl_pct <= -self.risk.max_daily_loss_pct:
            return RiskDecision.reject("daily_loss_limit")

        if portfolio.rolling_drawdown_pct <= -self.risk.max_rolling_drawdown_pct:
            return RiskDecision.reject("rolling_drawdown_limit")

        staleness_reference = cycle_started_at or datetime.now(tz=UTC)
        if snapshot.rate.age_seconds(staleness_reference) > self.risk.max_data_staleness_seconds:
            return RiskDecision.reject("stale_market_data")

        if snapshot.rate.spread_bps > self.risk.max_spread_bps:
            return RiskDecision.reject("spread_too_wide")

        if not snapshot.instrument.is_currently_tradable:
            return RiskDecision.reject("instrument_not_tradable")

        if not snapshot.instrument.is_exchange_open:
            return RiskDecision.reject("exchange_closed")

        if not snapshot.instrument.is_buy_enabled:
            return RiskDecision.reject("buy_disabled")

        if self.risk.max_leverage > 1:
            return RiskDecision.reject("live_leverage_disabled_for_phase_one")

        if market_regime is not None:
            if signal.action == "BUY" and market_regime.name == "risk_off" and self.risk.regime_risk_off_buy_block:
                return RiskDecision.reject("regime_risk_off_buy_block")
            if (
                signal.action == "BUY"
                and market_regime.name == "event_driven"
                and self.risk.regime_event_driven_buy_block
            ):
                return RiskDecision.reject("regime_event_driven_buy_block")

        existing = portfolio.position_for_symbol(signal.symbol)
        if existing and not self.risk.allow_averaging_down:
            return RiskDecision.reject("averaging_down_disabled")

        if signal.symbol in portfolio.open_order_symbols:
            return RiskDecision.reject("open_order_exists")

        open_positions = len(portfolio.positions)
        if existing is None and open_positions >= self.risk.max_positions:
            return RiskDecision.reject("max_positions_reached")

        if self._cooldown_active():
            return RiskDecision.reject("cooldown_after_loss")

        if self.risk.one_order_per_symbol_per_cycle and self.ledger and cycle_started_at:
            if self.ledger.recent_orders_for_symbol(signal.symbol, cycle_started_at.isoformat()) > 0:
                return RiskDecision.reject("one_order_per_symbol_per_cycle")

        target_notional = proposed_target_notional_usd
        if target_notional is None:
            target_notional = min(
                self.risk.max_position_pct_nav * portfolio.nav_usd,
                portfolio.available_cash_usd * 0.95,
            )
            target_notional = round(
                target_notional * self._edge_size_multiplier(signal),
                2,
            )

        if target_notional < self.risk.min_order_usd:
            return RiskDecision.reject("order_too_small")

        chart = self.chart_analyzer.analyze(snapshot.candles)
        avg_dollar_volume = _average_dollar_volume(snapshot.candles, 20)
        expected_slippage_bps = _expected_slippage_bps(snapshot, chart, avg_dollar_volume)
        execution_quality_score = _execution_quality_score(
            snapshot,
            chart,
            avg_dollar_volume=avg_dollar_volume,
            expected_slippage_bps=expected_slippage_bps,
        )
        if avg_dollar_volume < self.risk.min_avg_daily_dollar_volume:
            return RiskDecision.reject("liquidity_too_thin")
        if expected_slippage_bps > self.risk.max_expected_slippage_bps:
            return RiskDecision.reject("expected_slippage_too_high")
        if execution_quality_score < self.risk.min_execution_quality_score:
            return RiskDecision.reject("execution_quality_too_low")
        if chart.close_location_1d < self.risk.minimum_close_location_for_entry:
            return RiskDecision.reject("trade_timing_unfavorable")
        if chart.range_pct_1d > self.risk.unstable_gap_threshold_pct and chart.volatility_1m > 0.025:
            return RiskDecision.reject("unstable_market_structure")

        sector = _symbol_sector(signal.symbol, self.universe)
        if sector != "unknown":
            sector_exposure = _sector_exposure_pct(sector, portfolio, self.universe)
            projected_sector = sector_exposure + (target_notional / max(portfolio.nav_usd, 1.0))
            if projected_sector > self.risk.max_sector_exposure_pct:
                return RiskDecision.reject("sector_exposure_limit")
            if _sector_position_count(sector, portfolio, self.universe) >= self.risk.max_sector_positions:
                return RiskDecision.reject("sector_position_limit")

        peer_group = _peer_group_name(signal.symbol, self.strategy)
        if peer_group and _peer_group_position_count(peer_group, portfolio, self.strategy) >= self.risk.max_peer_group_positions:
            return RiskDecision.reject("peer_group_crowding_limit")

        if all_snapshots:
            max_corr, avg_corr = _portfolio_correlation(signal.symbol, all_snapshots, portfolio)
            if max_corr > self.risk.max_symbol_correlation:
                return RiskDecision.reject("symbol_correlation_limit")
            if avg_corr > self.risk.max_average_correlation:
                return RiskDecision.reject("average_correlation_limit")

        mid = snapshot.rate.mid
        stop_loss_pct, take_profit_pct, protection_reason = self._adaptive_protection(
            signal,
            snapshot,
            benchmark_snapshot,
            benchmark_news_context,
            market_regime,
        )
        if market_regime is not None and proposed_target_notional_usd is None:
            size_multiplier = self._regime_size_multiplier(market_regime)
            target_notional = round(target_notional * size_multiplier, 2)
            if target_notional < self.risk.min_order_usd:
                return RiskDecision.reject("regime_size_too_small")
        if portfolio_overlay_report is not None:
            if not portfolio_overlay_report.approved:
                return RiskDecision.reject(portfolio_overlay_report.reason)
            target_notional = portfolio_overlay_report.adjusted_notional_usd
            protection_reason = (
                f"{protection_reason} overlay_hhi={portfolio_overlay_report.hhi:.3f} "
                f"overlay_diversification={portfolio_overlay_report.diversification_score:.3f} "
                f"overlay_stress={portfolio_overlay_report.max_stress_loss_pct:.3%}"
            )
        elif all_snapshots:
            overlay = self.portfolio_optimizer.evaluate_candidate(
                symbol=signal.symbol,
                target_notional_usd=target_notional,
                portfolio=portfolio,
                all_snapshots=all_snapshots,
                benchmark_symbol=self.universe.benchmark_symbol,
                market_regime=market_regime,
            )
            if not overlay.approved:
                return RiskDecision.reject(overlay.reason)
            target_notional = overlay.adjusted_notional_usd
            protection_reason = (
                f"{protection_reason} overlay_hhi={overlay.hhi:.3f} "
                f"overlay_diversification={overlay.diversification_score:.3f} "
                f"overlay_stress={overlay.max_stress_loss_pct:.3%}"
            )
        projected_gross = portfolio.gross_exposure_pct + (target_notional / max(portfolio.nav_usd, 1.0))
        if projected_gross > self.risk.max_gross_exposure_pct:
            return RiskDecision.reject("gross_exposure_limit")
        stop_loss_rate = round(mid * (1 - stop_loss_pct), 4)
        take_profit_rate = round(mid * (1 + take_profit_pct), 4)
        return RiskDecision(
            approved=True,
            reason=(
                f"{protection_reason} avg_dollar_volume={avg_dollar_volume:.0f} "
                f"expected_slippage_bps={expected_slippage_bps:.1f} "
                f"execution_quality={execution_quality_score:.3f}"
            ),
            target_notional_usd=round(target_notional, 2),
            stop_loss_rate=stop_loss_rate,
            take_profit_rate=take_profit_rate,
            details={
                "avg_dollar_volume": avg_dollar_volume,
                "expected_slippage_bps": expected_slippage_bps,
                "execution_quality_score": execution_quality_score,
                "micro_volatility_burst": chart.micro_volatility_burst,
                "micro_liquidity_stress": chart.micro_liquidity_stress,
                "micro_range_expansion": chart.micro_range_expansion,
                "micro_gap_pressure": chart.micro_gap_pressure,
            },
        )

    def _evaluate_exit(self, signal: SignalDecision, portfolio: PortfolioState) -> RiskDecision:
        position = portfolio.position_for_symbol(signal.symbol)
        if position is None:
            return RiskDecision.reject("no_position_to_close")
        return RiskDecision(
            approved=True,
            reason="approved_exit",
            target_notional_usd=position.current_value_usd,
        )

    def _cooldown_active(self) -> bool:
        if not self.ledger or self.risk.cooldown_after_loss_minutes <= 0:
            return False
        since = datetime.now(tz=UTC) - timedelta(minutes=self.risk.cooldown_after_loss_minutes)
        return self.ledger.recent_loss_event_count(since.isoformat()) > 0

    def _adaptive_protection(
        self,
        signal: SignalDecision,
        snapshot: MarketSnapshot,
        benchmark_snapshot: MarketSnapshot | None,
        benchmark_news_context: NewsContext | None,
        market_regime: MarketRegime | None,
    ) -> tuple[float, float, str]:
        if not self.risk.adaptive_protection_enabled:
            return (
                self.strategy.stop_loss_pct,
                self.strategy.take_profit_pct,
                "approved fixed_protection",
            )

        chart = self.chart_analyzer.analyze(snapshot.candles)
        benchmark_chart = (
            self.chart_analyzer.analyze(benchmark_snapshot.candles)
            if benchmark_snapshot is not None
            else None
        )
        news = signal.news_context or NewsContext(symbol=signal.symbol)
        benchmark_news = benchmark_news_context or NewsContext(symbol=self.universe.benchmark_symbol.upper())

        technical_quality = _clamp(
            0.24 * chart.chart_score
            + 0.20 * chart.momentum_strength
            + 0.12 * _clamp(0.5 + chart.ema_gap_pct * 10)
            + 0.10 * _clamp(chart.adx_14 / 35)
            + 0.10 * _clamp(0.5 + chart.vwap_distance_pct * 8)
            + 0.08 * _clamp(0.5 + chart.obv_slope * 25)
            + 0.08 * _clamp(0.5 + chart.macd_histogram * 25)
            + 0.08 * _clamp(chart.trend_quality)
        )
        indicator_risk = _clamp(
            0.32 * chart.downtrend_penalty
            + 0.20 * chart.overextension_penalty
            + 0.18 * _clamp(chart.atr_14_pct / max(self.risk.max_stop_loss_pct, 0.0001))
            + 0.15 * _clamp((45 - chart.rsi_14) / 20)
            + 0.15 * _clamp(-chart.vwap_distance_pct / 0.03)
        )
        news_quality = _clamp(
            0.55 * (0.5 + news.sentiment_score / 2)
            + 0.45 * news.catalyst_score
        )
        market_quality = _clamp(
            0.40 * _clamp(0.5 + ((benchmark_chart.return_1m if benchmark_chart else 0.0) * 6))
            + 0.30 * (benchmark_chart.momentum_strength if benchmark_chart else 0.5)
            + 0.15 * _clamp(0.5 + ((benchmark_chart.ema_gap_pct if benchmark_chart else 0.0) * 10))
            + 0.15 * (0.5 + benchmark_news.sentiment_score / 2)
        )
        overall_quality = _clamp(
            0.42 * technical_quality
            + 0.23 * news_quality
            + 0.20 * market_quality
            + 0.15 * signal.confidence
        )
        regime_stress = market_regime.stress_score if market_regime is not None else 0.45

        atr_anchor = max(chart.atr_14_pct * 1.35, self.risk.min_stop_loss_pct)
        stop_loss_pct = _clamp(
            atr_anchor
            + 0.007 * overall_quality
            - 0.010 * indicator_risk
            - 0.005 * regime_stress
            - 0.004 * _clamp(-news.sentiment_score)
            - 0.004 * _clamp(0.5 - market_quality),
            self.risk.min_stop_loss_pct,
            self.risk.max_stop_loss_pct,
        )
        reward_multiple = _clamp(
            self.risk.min_reward_to_risk
            + 0.90 * overall_quality
            + 0.55 * news.catalyst_score
            + 0.40 * _clamp(market_quality - 0.45)
            - 0.60 * indicator_risk
            - 0.40 * regime_stress,
            self.risk.min_reward_to_risk,
            self.risk.max_reward_to_risk,
        )
        take_profit_pct = _clamp(
            stop_loss_pct * reward_multiple
            + 0.012 * news.catalyst_score
            + 0.010 * _clamp(chart.breakout_1m),
            self.risk.min_take_profit_pct,
            self.risk.max_take_profit_pct,
        )
        reason = (
            "approved adaptive_protection "
            f"sl={stop_loss_pct:.2%} tp={take_profit_pct:.2%} "
            f"technical={technical_quality:.3f} indicator_risk={indicator_risk:.3f} "
            f"news={news_quality:.3f} market={market_quality:.3f} overall={overall_quality:.3f}"
        )
        return stop_loss_pct, take_profit_pct, reason

    def _regime_size_multiplier(self, market_regime: MarketRegime) -> float:
        return _regime_size_multiplier(self.risk, market_regime)

    def _edge_size_multiplier(self, signal: SignalDecision) -> float:
        if not self.strategy.edge_sizing_enabled:
            return 1.0
        learned_edge = _clamp(float(signal.features.get("meta_learned_edge", 0.5)))
        expected_return = float(signal.features.get("meta_expected_return", 0.0))
        approval = _clamp(float(signal.features.get("meta_approval_score", 0.5)))
        edge_strength = _clamp(
            0.58 * learned_edge
            + 0.22 * _clamp(0.5 + expected_return * 18)
            + 0.20 * approval
        )
        raw_multiplier = 1.0 + ((edge_strength - 0.5) * 0.9)
        return _clamp(
            raw_multiplier,
            self.strategy.min_edge_size_multiplier,
            self.strategy.max_edge_size_multiplier,
        )


def is_kill_switch_active(path: str) -> bool:
    return Path(path).exists()


def set_kill_switch(path: str, active: bool, reason: str = "") -> None:
    kill_path = Path(path)
    if active:
        kill_path.parent.mkdir(parents=True, exist_ok=True)
        kill_path.write_text(reason or "manual halt", encoding="utf-8")
        return
    if kill_path.exists():
        kill_path.unlink()


def _asset_type_allowed(asset_type: str, allowed: tuple[str, ...]) -> bool:
    normalized = asset_type.lower()
    return any(item.lower() in normalized or normalized in item.lower() for item in allowed)


def _average_dollar_volume(candles, window: int) -> float:
    if not candles:
        return 0.0
    selected = candles[-window:] if len(candles) >= window else candles
    return sum(candle.close * candle.volume for candle in selected) / max(len(selected), 1)


def _expected_slippage_bps(snapshot: MarketSnapshot, chart, avg_dollar_volume: float) -> float:
    liquidity_penalty = 0.0 if avg_dollar_volume <= 0 else min(40.0, 250_000_000 / avg_dollar_volume)
    volatility_penalty = min(chart.atr_14_pct * 10_000 * 0.03, 12.0)
    return snapshot.rate.spread_bps + liquidity_penalty + volatility_penalty


def _execution_quality_score(
    snapshot: MarketSnapshot,
    chart,
    *,
    avg_dollar_volume: float,
    expected_slippage_bps: float,
) -> float:
    liquidity_component = _clamp(avg_dollar_volume / max(75_000_000.0, avg_dollar_volume))
    spread_component = _clamp(1 - snapshot.rate.spread_bps / 30.0)
    slippage_component = _clamp(1 - expected_slippage_bps / 30.0)
    volatility_component = _clamp(1 - chart.micro_volatility_burst)
    structure_component = _clamp(
        0.45 * chart.close_location_1d
        + 0.25 * (1 - chart.micro_gap_pressure)
        + 0.15 * (1 - chart.micro_liquidity_stress)
        + 0.15 * _clamp(0.5 + chart.micro_order_flow_bias)
    )
    return _clamp(
        0.22 * liquidity_component
        + 0.22 * spread_component
        + 0.20 * slippage_component
        + 0.16 * volatility_component
        + 0.20 * structure_component
    )


def _symbol_sector(symbol: str, universe: UniverseSettings) -> str:
    if symbol.upper() in universe.sector_map:
        return universe.sector_map[symbol.upper()].strip().lower()
    return "unknown"


def _sector_exposure_pct(sector: str, portfolio: PortfolioState, universe: UniverseSettings) -> float:
    if portfolio.nav_usd <= 0:
        return 0.0
    exposure = sum(
        position.current_value_usd
        for position in portfolio.positions
        if _symbol_sector(position.symbol, universe) == sector
    )
    return exposure / portfolio.nav_usd


def _sector_position_count(sector: str, portfolio: PortfolioState, universe: UniverseSettings) -> int:
    return sum(1 for position in portfolio.positions if _symbol_sector(position.symbol, universe) == sector)


def _peer_group_name(symbol: str, strategy: StrategySettings) -> str | None:
    for name, group in strategy.peer_groups.items():
        if symbol.upper() in group.symbols:
            return name
    return None


def _peer_group_position_count(peer_group: str, portfolio: PortfolioState, strategy: StrategySettings) -> int:
    symbols = strategy.peer_groups[peer_group].symbols
    return sum(1 for position in portfolio.positions if position.symbol.upper() in symbols)


def _portfolio_correlation(
    symbol: str,
    snapshots: dict[str, MarketSnapshot],
    portfolio: PortfolioState,
) -> tuple[float, float]:
    target = snapshots.get(symbol.upper())
    if target is None:
        return 0.0, 0.0
    target_returns = _recent_returns(target.candles, 20)
    if not target_returns:
        return 0.0, 0.0
    correlations: list[float] = []
    for position in portfolio.positions:
        other = snapshots.get(position.symbol.upper())
        if other is None or other.symbol.upper() == symbol.upper():
            continue
        corr = _correlation(target_returns, _recent_returns(other.candles, 20))
        correlations.append(corr)
    if not correlations:
        return 0.0, 0.0
    return max(correlations), sum(correlations) / len(correlations)


def _recent_returns(candles, window: int) -> list[float]:
    if len(candles) < 3:
        return []
    selected = candles[-window - 1 :] if len(candles) >= window + 1 else candles
    returns: list[float] = []
    for previous, current in zip(selected, selected[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    return returns


def _correlation(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n < 3:
        return 0.0
    left = left[-n:]
    right = right[-n:]
    left_mean = sum(left) / n
    right_mean = sum(right) / n
    cov = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_var = sum((a - left_mean) ** 2 for a in left)
    right_var = sum((b - right_mean) ** 2 for b in right)
    if left_var <= 0 or right_var <= 0:
        return 0.0
    return cov / ((left_var * right_var) ** 0.5)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)

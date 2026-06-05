from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, time
from typing import Any
from uuid import uuid4

from models import MarketSnapshot, PortfolioState, SignalDecision


@dataclass(frozen=True)
class ExecutionSimulation:
    simulation_id: str
    symbol: str
    action: str
    quality_score: float
    expected_slippage_bps: float
    fill_probability: float
    liquidity_score: float
    target_notional_usd: float
    reference_price: float
    expected_fill_price: float
    spread_bps: float
    volatility_bps: float
    size_impact_bps: float
    timing_penalty_bps: float
    market_timing_score: float
    historical_slippage_bps: float
    historical_fill_rate: float
    reason: str

    def as_features(self) -> dict[str, float | str]:
        return {
            "execution_simulation_id": self.simulation_id,
            "execution_sim_quality_score": self.quality_score,
            "execution_sim_expected_slippage_bps": self.expected_slippage_bps,
            "execution_sim_fill_probability": self.fill_probability,
            "execution_sim_liquidity_score": self.liquidity_score,
            "execution_sim_target_notional_usd": self.target_notional_usd,
            "execution_sim_reference_price": self.reference_price,
            "execution_sim_expected_fill_price": self.expected_fill_price,
            "execution_sim_spread_bps": self.spread_bps,
            "execution_sim_volatility_bps": self.volatility_bps,
            "execution_sim_size_impact_bps": self.size_impact_bps,
            "execution_sim_timing_penalty_bps": self.timing_penalty_bps,
            "execution_sim_market_timing_score": self.market_timing_score,
            "execution_sim_historical_slippage_bps": self.historical_slippage_bps,
            "execution_sim_historical_fill_rate": self.historical_fill_rate,
            "execution_sim_reason": self.reason,
        }

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


class ExecutionSimulator:
    def simulate(
        self,
        *,
        decision: SignalDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        target_notional_usd: float,
        historical_profile: dict[str, Any] | None = None,
    ) -> ExecutionSimulation:
        candles = snapshot.candles[-20:]
        avg_dollar_volume = _avg_dollar_volume(candles)
        liquidity_score = min(avg_dollar_volume / max(target_notional_usd * 100, 1.0), 1.0) if target_notional_usd > 0 else 0.8
        volatility_bps = _short_volatility(candles) * 10_000
        spread_bps = max(snapshot.rate.spread_bps, 0.0)
        size_impact_bps = (target_notional_usd / max(avg_dollar_volume, 1.0)) * 10_000
        timing_score, timing_penalty_bps, timing_label = _market_timing(snapshot)
        profile = historical_profile or {}
        historical_slippage_bps = max(_float(profile.get("avg_actual_slippage_bps"), 0.0), 0.0)
        prediction_error_bps = _clamp(_float(profile.get("avg_prediction_error_bps"), 0.0), -20.0, 60.0)
        historical_fill_rate = _clamp(_float(profile.get("fill_rate"), 0.85), 0.05, 0.99)
        expected_slippage = min(
            max(
                spread_bps * 0.55
                + volatility_bps * 0.20
                + size_impact_bps
                + timing_penalty_bps
                + historical_slippage_bps * 0.35
                + prediction_error_bps,
                0.0,
            ),
            300.0,
        )
        base_fill_probability = 1.0 - expected_slippage / 190 - (1 - liquidity_score) * 0.25 - (1 - timing_score) * 0.10
        fill_probability = _clamp(base_fill_probability * 0.75 + historical_fill_rate * 0.25, 0.05, 0.99)
        quality = _clamp(
            fill_probability * 0.62
            + liquidity_score * 0.18
            + max(0.0, 1 - spread_bps / 80) * 0.10
            + timing_score * 0.10,
            0.0,
            1.0,
        )
        reference_price = max(snapshot.rate.mid, 0.0)
        expected_fill_price = _expected_fill_price(reference_price, decision.action, expected_slippage)
        reason = (
            f"spread={spread_bps:.1f}bps liquidity={liquidity_score:.2f} timing={timing_label} "
            f"hist_slippage={historical_slippage_bps:.1f}bps expected_slippage={expected_slippage:.1f}bps "
            f"fill={fill_probability:.2f}"
        )
        return ExecutionSimulation(
            simulation_id=f"exec-{uuid4()}",
            symbol=decision.symbol,
            action=decision.action,
            quality_score=quality,
            expected_slippage_bps=expected_slippage,
            fill_probability=fill_probability,
            liquidity_score=liquidity_score,
            target_notional_usd=target_notional_usd,
            reference_price=reference_price,
            expected_fill_price=expected_fill_price,
            spread_bps=spread_bps,
            volatility_bps=volatility_bps,
            size_impact_bps=size_impact_bps,
            timing_penalty_bps=timing_penalty_bps,
            market_timing_score=timing_score,
            historical_slippage_bps=historical_slippage_bps,
            historical_fill_rate=historical_fill_rate,
            reason=reason,
        )


def _avg_dollar_volume(candles) -> float:
    if not candles:
        return 1.0
    return sum(max(candle.close, 0.0) * max(candle.volume, 0.0) for candle in candles) / len(candles)


def _short_volatility(candles) -> float:
    if len(candles) < 3:
        return 0.01
    returns: list[float] = []
    for previous, current in zip(candles, candles[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return 0.01
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return variance ** 0.5


def _market_timing(snapshot: MarketSnapshot) -> tuple[float, float, str]:
    if not snapshot.instrument.is_exchange_open:
        return 0.25, 35.0, "exchange_closed"
    current = snapshot.rate.timestamp.astimezone(UTC).time()
    regular_open = time(14, 30)
    regular_close = time(21, 0)
    minutes_from_open = _minutes_between(regular_open, current)
    minutes_to_close = _minutes_between(current, regular_close)
    if minutes_from_open is None or minutes_to_close is None:
        return 0.70, 6.0, "outside_regular_window"
    edge_minutes = min(minutes_from_open, minutes_to_close)
    if edge_minutes <= 15:
        return 0.55, 12.0, "near_open_or_close"
    if edge_minutes <= 30:
        return 0.72, 6.0, "open_close_buffer"
    return 0.95, 0.0, "stable_session"


def _minutes_between(start: time, end: time) -> float | None:
    start_minutes = start.hour * 60 + start.minute + start.second / 60
    end_minutes = end.hour * 60 + end.minute + end.second / 60
    if end_minutes < start_minutes:
        return None
    return end_minutes - start_minutes


def _expected_fill_price(reference_price: float, action: str, slippage_bps: float) -> float:
    if reference_price <= 0:
        return 0.0
    multiplier = slippage_bps / 10_000
    if action == "SELL":
        return max(reference_price * (1 - multiplier), 0.0)
    return reference_price * (1 + multiplier)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(min(value, maximum), minimum)

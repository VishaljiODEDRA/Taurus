from __future__ import annotations

from dataclasses import dataclass

from agent.chart import ChartAnalysis
from agent.ml import OutcomeLearningProfile
from agent.regime import MarketRegime
from models import NewsContext


@dataclass(frozen=True)
class TimingForecast:
    close_action: str
    earliest_days: int
    likely_days: int
    latest_days: int
    invalidation_days: int
    confidence: float
    expected_move_pct: float
    reason: str

    def as_features(self) -> dict[str, float | str | bool]:
        return {
            "timing_close_action": self.close_action,
            "timing_earliest_days": self.earliest_days,
            "timing_likely_days": self.likely_days,
            "timing_latest_days": self.latest_days,
            "timing_invalidation_days": self.invalidation_days,
            "timing_confidence": self.confidence,
            "timing_expected_move_pct": self.expected_move_pct,
            "timing_reason": self.reason,
        }


class TradeTimingForecaster:
    def forecast_entry(
        self,
        *,
        symbol: str,
        action: str,
        chart: ChartAnalysis,
        news_context: NewsContext,
        market_regime: MarketRegime | None,
        outcome_profile: OutcomeLearningProfile | None,
        score: float,
        confidence: float,
    ) -> TimingForecast:
        close_action = "SELL" if action == "BUY" else "BUY_TO_CLOSE"
        direction = 1.0 if action == "BUY" else -1.0
        speed = self._move_speed(chart, direction)
        edge = self._learned_edge(symbol, outcome_profile)
        market_stress = market_regime.stress_score if market_regime is not None else 0.45
        regime_multiplier = market_regime.size_multiplier if market_regime is not None else 0.85
        catalyst_boost = 1.0 + 0.30 * news_context.catalyst_score + 0.16 * max(news_context.sentiment_score * direction, 0.0)
        quality = _clamp(
            0.32 * chart.momentum_strength
            + 0.22 * chart.chart_score
            + 0.18 * confidence
            + 0.16 * edge
            + 0.12 * _clamp(regime_multiplier)
        )
        target_move = _clamp(
            0.018
            + 0.028 * quality
            + 0.012 * news_context.catalyst_score
            - 0.014 * market_stress,
            0.012,
            0.075,
        )
        expected_move = target_move * direction
        likely_days = _clamp_int(round(target_move / max(speed * catalyst_boost, 0.002)), 1, 20)
        earliest_days = _clamp_int(max(1, round(likely_days * 0.45)), 1, likely_days)
        latest_days = _clamp_int(round(likely_days * (1.55 + 0.70 * market_stress)), likely_days, 35)
        invalidation_days = _clamp_int(round(max(1.0, likely_days * (0.45 + 0.55 * market_stress))), 1, latest_days)
        forecast_confidence = _clamp(
            0.25
            + 0.32 * confidence
            + 0.18 * edge
            + 0.15 * chart.trend_quality
            + 0.10 * (1 - chart.micro_liquidity_stress)
            - 0.16 * market_stress
        )
        reason = (
            f"{close_action} {symbol} is most likely in {earliest_days}-{latest_days} trading days, "
            f"with day {likely_days} as the center estimate, because momentum, regime risk, news catalyst, "
            f"and learned trade edge imply a {abs(expected_move):.2%} target move."
        )
        return TimingForecast(
            close_action=close_action,
            earliest_days=earliest_days,
            likely_days=likely_days,
            latest_days=latest_days,
            invalidation_days=invalidation_days,
            confidence=forecast_confidence,
            expected_move_pct=expected_move,
            reason=reason,
        )

    def forecast_position(
        self,
        *,
        symbol: str,
        chart: ChartAnalysis,
        news_context: NewsContext,
        benchmark_chart: ChartAnalysis | None,
        pnl_pct: float,
        exit_pressure: float,
        dynamic_take_profit_pct: float,
        action: str,
    ) -> TimingForecast:
        if action == "SELL":
            return TimingForecast(
                close_action="SELL",
                earliest_days=0,
                likely_days=0,
                latest_days=1,
                invalidation_days=0,
                confidence=_clamp(0.72 + 0.24 * exit_pressure),
                expected_move_pct=pnl_pct,
                reason=(
                    f"SELL {symbol} now or by the next trading session because exit pressure is high enough "
                    f"that protecting capital matters more than waiting for a cleaner rebound."
                ),
            )

        remaining_to_target = max(dynamic_take_profit_pct - pnl_pct, 0.004)
        market_strength = benchmark_chart.momentum_strength if benchmark_chart else 0.5
        speed = max(
            abs(chart.return_5d) / 5,
            chart.atr_14_pct * 0.36,
            chart.volatility_1m * 0.18,
            0.002,
        )
        support = _clamp(
            0.34 * chart.momentum_strength
            + 0.20 * chart.chart_score
            + 0.16 * market_strength
            + 0.15 * _clamp(0.5 + news_context.sentiment_score / 2)
            + 0.15 * (1 - exit_pressure)
        )
        likely_days = _clamp_int(round(remaining_to_target / max(speed * (0.75 + support), 0.002)), 1, 20)
        earliest_days = _clamp_int(max(1, round(likely_days * 0.5)), 1, likely_days)
        latest_days = _clamp_int(round(likely_days * (1.6 + exit_pressure)), likely_days, 35)
        invalidation_days = _clamp_int(round(max(1.0, likely_days * (0.35 + exit_pressure))), 1, latest_days)
        confidence = _clamp(0.30 + 0.34 * support + 0.18 * (1 - exit_pressure) + 0.12 * market_strength)
        reason = (
            f"SELL {symbol} is most likely in {earliest_days}-{latest_days} trading days, with day {likely_days} "
            f"as the center estimate, if momentum keeps helping the position reach the adaptive profit zone."
        )
        return TimingForecast(
            close_action="SELL",
            earliest_days=earliest_days,
            likely_days=likely_days,
            latest_days=latest_days,
            invalidation_days=invalidation_days,
            confidence=confidence,
            expected_move_pct=remaining_to_target,
            reason=reason,
        )

    def _move_speed(self, chart: ChartAnalysis, direction: float) -> float:
        directional_speed = max((chart.return_5d * direction) / 5, (chart.return_1m * direction) / 21, 0.0)
        volatility_speed = max(chart.atr_14_pct * 0.35, chart.volatility_1m * 0.18)
        micro_speed = 0.002 * (1 + chart.micro_volatility_burst + chart.micro_range_expansion)
        return max(directional_speed, volatility_speed, micro_speed, 0.002)

    def _learned_edge(self, symbol: str, outcome_profile: OutcomeLearningProfile | None) -> float:
        if outcome_profile is None or outcome_profile.sample_count <= 0:
            return 0.50
        stats = outcome_profile.stats_for_symbol(symbol) or outcome_profile.global_stats
        return _clamp(0.46 + 1.05 * (stats.win_rate - 0.50) + 16.0 * stats.average_return)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(min(value, high), low)

from __future__ import annotations

import math
from dataclasses import dataclass, field

from agent.chart import ChartAnalyzer
from agent.config import StrategySettings
from models import MarketSnapshot, NewsContext


@dataclass(frozen=True)
class MarketRegime:
    name: str
    confidence: float
    stress_score: float
    size_multiplier: float
    summary: str
    probabilities: dict[str, float] = field(default_factory=dict)
    features: dict[str, float | str] = field(default_factory=dict)


class MarketRegimeEngine:
    def __init__(self, strategy: StrategySettings) -> None:
        self.chart_analyzer = ChartAnalyzer(strategy)
        self.previous_probabilities: dict[str, float] | None = None

    def classify(
        self,
        benchmark_snapshot: MarketSnapshot | None,
        benchmark_news: NewsContext | None,
    ) -> MarketRegime:
        if benchmark_snapshot is None:
            probabilities = {
                "bullish": 0.10,
                "weak": 0.55,
                "volatile": 0.15,
                "risk_off": 0.15,
                "event_driven": 0.05,
            }
            self.previous_probabilities = probabilities
            return self._finalize_regime(
                probabilities=probabilities,
                chart=None,
                news=NewsContext(symbol="SPY"),
                summary_override="Benchmark data is limited, so the regime is treated cautiously.",
            )

        chart = self.chart_analyzer.analyze(benchmark_snapshot.candles)
        news = benchmark_news or NewsContext(symbol=benchmark_snapshot.symbol)
        logits = self._regime_logits(chart, news)
        probabilities = _softmax(logits)
        probabilities = self._apply_transition_prior(probabilities)
        self.previous_probabilities = probabilities
        return self._finalize_regime(probabilities=probabilities, chart=chart, news=news)

    def _regime_logits(self, chart, news: NewsContext) -> dict[str, float]:
        range_risk = chart.range_pct_1d
        volatility = chart.volatility_1m
        negative_news = max(-news.sentiment_score, 0.0)
        positive_news = max(news.sentiment_score, 0.0)
        return {
            "event_driven": (
                -0.25
                + 1.90 * news.catalyst_score
                + 1.00 * abs(news.sentiment_score)
                + 1.10 * _clamp(range_risk / 0.04)
                + 0.90 * _clamp(volatility / 0.03)
            ),
            "risk_off": (
                -0.30
                + 0.75 * _clamp(-chart.return_5d / 0.04)
                + 1.15 * _clamp(-chart.return_1m / 0.08)
                + 0.80 * _clamp(0.5 - chart.momentum_strength)
                + 0.65 * negative_news
                + 0.55 * _clamp(volatility / 0.03)
            ),
            "volatile": (
                -0.20
                + 1.25 * _clamp(volatility / 0.03)
                + 0.95 * _clamp(range_risk / 0.04)
                + 0.55 * chart.overextension_penalty
                + 0.40 * abs(news.sentiment_score)
                + 0.35 * chart.micro_volatility_burst
            ),
            "bullish": (
                -0.15
                + 0.95 * _clamp(chart.return_5d / 0.04)
                + 1.10 * _clamp(chart.return_1m / 0.08)
                + 1.00 * chart.momentum_strength
                + 0.55 * _clamp(chart.trend_quality)
                + 0.55 * positive_news
                + 0.25 * _clamp(0.5 + chart.micro_order_flow_bias * 1.5)
            ),
            "weak": (
                0.15
                + 0.55 * _clamp(1 - abs(chart.return_1m / 0.05))
                + 0.50 * _clamp(0.6 - chart.momentum_strength)
                + 0.45 * _clamp(volatility / 0.03)
                + 0.35 * _clamp(abs(news.sentiment_score))
            ),
        }

    def _apply_transition_prior(self, probabilities: dict[str, float]) -> dict[str, float]:
        if not self.previous_probabilities:
            return probabilities
        blended = {}
        for regime_name, probability in probabilities.items():
            prior = self.previous_probabilities.get(regime_name, 0.0)
            blended[regime_name] = 0.72 * probability + 0.28 * prior
        total = sum(blended.values())
        if total <= 0:
            return probabilities
        return {name: value / total for name, value in blended.items()}

    def _finalize_regime(
        self,
        *,
        probabilities: dict[str, float],
        chart,
        news: NewsContext,
        summary_override: str | None = None,
    ) -> MarketRegime:
        dominant_name = max(probabilities, key=probabilities.get)
        dominant_probability = probabilities[dominant_name]
        stress_score = _clamp(
            0.75 * probabilities.get("risk_off", 0.0)
            + 0.65 * probabilities.get("volatile", 0.0)
            + 0.55 * probabilities.get("event_driven", 0.0)
            + 0.30 * probabilities.get("weak", 0.0)
        )
        size_multiplier = (
            1.05 * probabilities.get("bullish", 0.0)
            + 0.78 * probabilities.get("weak", 0.0)
            + 0.60 * probabilities.get("volatile", 0.0)
            + 0.45 * probabilities.get("risk_off", 0.0)
            + 0.55 * probabilities.get("event_driven", 0.0)
        )
        size_multiplier = _clamp(size_multiplier, 0.40, 1.05)
        if dominant_name in {"risk_off", "volatile", "event_driven"}:
            size_multiplier = min(size_multiplier, 0.60 if dominant_name != "risk_off" else 0.50)
        summary = summary_override or self._summary(dominant_name, probabilities)
        chart_features = {}
        if chart is not None:
            chart_features = {
                "benchmark_return_1d": chart.return_1d,
                "benchmark_return_5d": chart.return_5d,
                "benchmark_return_1m": chart.return_1m,
                "benchmark_momentum_strength": chart.momentum_strength,
                "benchmark_volatility_1m": chart.volatility_1m,
                "benchmark_micro_volatility_burst": chart.micro_volatility_burst,
                "benchmark_micro_liquidity_stress": chart.micro_liquidity_stress,
            }
        probability_features = {
            f"regime_probability_{name}": value for name, value in probabilities.items()
        }
        features = {
            "regime_name": dominant_name,
            "regime_confidence": dominant_probability,
            "regime_stress_score": stress_score,
            "regime_size_multiplier": size_multiplier,
            "benchmark_news_sentiment": news.sentiment_score,
            "benchmark_news_catalyst": news.catalyst_score,
            **chart_features,
            **probability_features,
        }
        return MarketRegime(
            name=dominant_name,
            confidence=dominant_probability,
            stress_score=stress_score,
            size_multiplier=size_multiplier,
            summary=summary,
            probabilities=probabilities,
            features=features,
        )

    def _summary(self, name: str, probabilities: dict[str, float]) -> str:
        if name == "bullish":
            return "The benchmark looks broadly supportive, but the agent still sizes by how dominant that bullish regime actually is."
        if name == "risk_off":
            return "Defensive conditions dominate the regime mix, so capital preservation should outweigh aggressive entry hunting."
        if name == "volatile":
            return "Volatility is elevated enough that execution quality and selective sizing matter more than signal frequency."
        if name == "event_driven":
            return "Event pressure is dominating the tape, so moves may be less reliable and more sensitive to news shocks."
        weak_prob = probabilities.get("weak", 0.0)
        return (
            "The backdrop is mixed and only partly supportive, so the agent should stay selective and avoid forcing exposure."
            if weak_prob >= 0.40
            else "The market is transitioning between states, so conviction should stay moderate."
        )


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    max_logit = max(logits.values()) if logits else 0.0
    exp_values = {name: math.exp(value - max_logit) for name, value in logits.items()}
    total = sum(exp_values.values())
    if total <= 0:
        count = max(len(logits), 1)
        return {name: 1 / count for name in logits}
    return {name: value / total for name, value in exp_values.items()}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)

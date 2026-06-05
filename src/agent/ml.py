from __future__ import annotations

import math
from dataclasses import dataclass, field

from agent.chart import ChartAnalysis
from agent.regime import MarketRegime
from models import NewsContext


@dataclass(frozen=True)
class AlphaModelOutput:
    probability: float
    regime_score: float
    catalyst_alignment: float
    risk_score: float
    news_source_breadth: float = 0.0

    def as_features(self) -> dict[str, float]:
        return {
            "ml_alpha_probability": self.probability,
            "ml_regime_score": self.regime_score,
            "ml_catalyst_alignment": self.catalyst_alignment,
            "ml_risk_score": self.risk_score,
            "ml_news_source_breadth": self.news_source_breadth,
        }


@dataclass(frozen=True)
class OutcomeStats:
    sample_count: int
    win_rate: float
    average_return: float
    average_pnl: float
    average_holding_days: float


@dataclass(frozen=True)
class OutcomeLearningProfile:
    sample_count: int
    global_stats: OutcomeStats
    symbol_stats: dict[str, OutcomeStats] = field(default_factory=dict)

    def stats_for_symbol(self, symbol: str) -> OutcomeStats | None:
        return self.symbol_stats.get(symbol.upper())


@dataclass(frozen=True)
class MetaLabelOutput:
    take_trade: bool
    approval_score: float
    expected_return: float
    learned_edge: float
    caution_penalty: float
    source_sample_count: int
    reason: str

    def as_features(self) -> dict[str, float | str | bool]:
        return {
            "meta_take_trade": self.take_trade,
            "meta_approval_score": self.approval_score,
            "meta_expected_return": self.expected_return,
            "meta_learned_edge": self.learned_edge,
            "meta_caution_penalty": self.caution_penalty,
            "meta_source_sample_count": self.source_sample_count,
            "meta_reason": self.reason,
        }


class LightweightAlphaModel:
    """Dependency-free ensemble model for chart/news features.

    This is intentionally transparent. The coefficients are conservative starter
    weights that can later be replaced by a trained model after collecting enough
    local shadow/demo outcomes.
    """

    def predict(
        self,
        *,
        chart: ChartAnalysis,
        relative_strength_1m: float,
        news_context: NewsContext,
        peer_lag_score: float,
        spread_bps: float,
    ) -> AlphaModelOutput:
        chart_evidence = _has_chart_evidence(chart)
        news_source_breadth = _news_source_breadth(news_context)
        regime_score = _clamp(
            0.42
            + 2.8 * chart.ma_alignment
            + 42 * chart.trend_slope_1m
            + 0.20 * chart.trend_quality
            + 4.0 * relative_strength_1m
        )
        catalyst_alignment = _clamp(
            0.35
            + 0.28 * news_context.catalyst_score
            + 0.18 * max(news_context.sentiment_score, 0.0)
            + 0.08 * news_source_breadth
            + 0.20 * peer_lag_score
            + 0.17 * max(chart.breakout_1m, chart.support_bounce)
        )
        risk_score = _clamp(
            0.15
            + 4.5 * chart.volatility_1m
            + 0.35 * chart.overextension_penalty
            + 0.45 * chart.downtrend_penalty
            + spread_bps / 120
        )

        if not chart_evidence:
            limited_probability = _clamp(
                0.46
                + 0.06 * news_context.catalyst_score
                + 0.04 * max(news_context.sentiment_score, 0.0)
                + 0.02 * news_source_breadth
                + 0.03 * peer_lag_score
                - 0.08 * risk_score,
                low=0.20,
                high=0.58,
            )
            return AlphaModelOutput(
                probability=limited_probability,
                regime_score=regime_score,
                catalyst_alignment=catalyst_alignment,
                risk_score=risk_score,
                news_source_breadth=news_source_breadth,
            )

        relative_strength_component = _clamp(0.5 + relative_strength_1m * 5)
        volume_component = _clamp((chart.volume_ratio_5_30 - 0.85) / 1.25)
        logit = (
            -0.10
            + 2.60 * (chart.chart_score - 0.50)
            + 1.25 * (regime_score - 0.45)
            + 1.15 * (catalyst_alignment - 0.35)
            + 0.85 * (relative_strength_component - 0.50)
            + 0.35 * (volume_component - 0.40)
            + 0.18 * news_source_breadth
            - 0.65 * risk_score
        )
        return AlphaModelOutput(
            probability=_sigmoid(logit),
            regime_score=regime_score,
            catalyst_alignment=catalyst_alignment,
            risk_score=risk_score,
            news_source_breadth=news_source_breadth,
        )


class OutcomeMemoryBuilder:
    def build(self, outcomes: list[dict]) -> OutcomeLearningProfile:
        rows = [row for row in outcomes if row.get("symbol")]
        global_stats = _stats_from_rows(rows)
        symbol_rows: dict[str, list[dict]] = {}
        for row in rows:
            symbol = str(row.get("symbol", "")).upper()
            if not symbol:
                continue
            symbol_rows.setdefault(symbol, []).append(row)
        symbol_stats = {
            symbol: _stats_from_rows(group_rows)
            for symbol, group_rows in symbol_rows.items()
        }
        return OutcomeLearningProfile(
            sample_count=len(rows),
            global_stats=global_stats,
            symbol_stats=symbol_stats,
        )


class MetaLabeler:
    def predict(
        self,
        *,
        symbol: str,
        score: float,
        alpha: AlphaModelOutput,
        chart: ChartAnalysis,
        news_context: NewsContext,
        relative_strength_1m: float,
        risk_penalty: float,
        spread_bps: float,
        market_regime: MarketRegime | None,
        outcome_profile: OutcomeLearningProfile | None,
        min_samples: int,
        take_threshold: float,
        block_threshold: float,
    ) -> MetaLabelOutput:
        setup_quality = _clamp(
            0.30 * score
            + 0.24 * alpha.probability
            + 0.16 * chart.chart_score
            + 0.10 * chart.momentum_strength
            + 0.08 * _clamp(0.5 + relative_strength_1m * 8)
            + 0.07 * news_context.catalyst_score
            + 0.05 * _clamp(0.5 + news_context.sentiment_score / 2)
        )
        caution_penalty = _clamp(
            0.34 * risk_penalty
            + 0.18 * _clamp(spread_bps / 30)
            + 0.14 * chart.downtrend_penalty
            + 0.12 * chart.overextension_penalty
            + 0.10 * _clamp(-news_context.sentiment_score)
            + 0.12 * (market_regime.stress_score if market_regime is not None else 0.40)
        )

        learned_edge, expected_return, source_sample_count = self._learned_edge(
            symbol=symbol,
            outcome_profile=outcome_profile,
            min_samples=min_samples,
        )
        approval_score = _clamp(
            0.60 * setup_quality
            + 0.28 * learned_edge
            + 0.12 * _clamp(0.5 + expected_return * 25)
            - 0.34 * caution_penalty
        )
        take_trade = approval_score >= take_threshold and expected_return > -0.001
        if source_sample_count >= min_samples and approval_score < block_threshold:
            take_trade = False

        reason = _meta_reason(
            take_trade=take_trade,
            learned_edge=learned_edge,
            expected_return=expected_return,
            caution_penalty=caution_penalty,
            sample_count=source_sample_count,
        )
        return MetaLabelOutput(
            take_trade=take_trade,
            approval_score=approval_score,
            expected_return=expected_return,
            learned_edge=learned_edge,
            caution_penalty=caution_penalty,
            source_sample_count=source_sample_count,
            reason=reason,
        )

    def _learned_edge(
        self,
        *,
        symbol: str,
        outcome_profile: OutcomeLearningProfile | None,
        min_samples: int,
    ) -> tuple[float, float, int]:
        if outcome_profile is None or outcome_profile.sample_count <= 0:
            return 0.50, 0.0, 0

        global_stats = outcome_profile.global_stats
        symbol_stats = outcome_profile.stats_for_symbol(symbol)
        use_symbol = symbol_stats is not None and symbol_stats.sample_count >= max(3, min_samples // 2)
        primary = symbol_stats if use_symbol else global_stats
        secondary = global_stats
        primary_weight = 0.68 if use_symbol else 1.0
        if primary.sample_count < min_samples and secondary.sample_count > primary.sample_count and use_symbol:
            primary_weight = 0.45

        primary_edge = _edge_from_stats(primary)
        secondary_edge = _edge_from_stats(secondary)
        learned_edge = _clamp(primary_weight * primary_edge + (1 - primary_weight) * secondary_edge)
        expected_return = (
            primary_weight * primary.average_return + (1 - primary_weight) * secondary.average_return
        )
        return learned_edge, expected_return, primary.sample_count


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)


def _has_chart_evidence(chart: ChartAnalysis) -> bool:
    return (
        abs(chart.return_1d)
        + abs(chart.return_5d)
        + abs(chart.return_1m)
        + abs(chart.trend_slope_5d)
        + abs(chart.trend_slope_1m)
        + abs(chart.ma_alignment)
        + abs(chart.macd_histogram)
        + abs(chart.volatility_1m)
    ) > 0.000001


def _news_source_breadth(news_context: NewsContext) -> float:
    sources = {
        item.source.strip().lower()
        for item in news_context.items
        if item.source and item.source.strip()
    }
    return _clamp(len(sources) / 4)


def _stats_from_rows(rows: list[dict]) -> OutcomeStats:
    if not rows:
        return OutcomeStats(0, 0.5, 0.0, 0.0, 0.0)
    returns = [float(row.get("return_pct", 0.0) or 0.0) for row in rows]
    pnls = [float(row.get("pnl_usd", 0.0) or 0.0) for row in rows]
    holding_days = [float(row.get("holding_days", 0.0) or 0.0) for row in rows]
    win_rate = sum(1 for value in returns if value > 0) / len(returns)
    return OutcomeStats(
        sample_count=len(rows),
        win_rate=win_rate,
        average_return=sum(returns) / len(returns),
        average_pnl=sum(pnls) / len(pnls) if pnls else 0.0,
        average_holding_days=sum(holding_days) / len(holding_days) if holding_days else 0.0,
    )


def _edge_from_stats(stats: OutcomeStats) -> float:
    return _clamp(
        0.46
        + 1.10 * (stats.win_rate - 0.50)
        + 18.0 * stats.average_return
        - 0.012 * max(stats.average_holding_days - 6.0, 0.0),
        low=0.05,
        high=0.95,
    )


def _meta_reason(
    *,
    take_trade: bool,
    learned_edge: float,
    expected_return: float,
    caution_penalty: float,
    sample_count: int,
) -> str:
    edge_phrase = "supportive" if learned_edge >= 0.58 else "mixed" if learned_edge >= 0.48 else "weak"
    risk_phrase = "contained" if caution_penalty <= 0.32 else "elevated"
    action_phrase = "allowing the trade" if take_trade else "holding back the trade"
    return (
        f"Meta filter is {action_phrase} because recent outcomes look {edge_phrase}, "
        f"expected edge is {expected_return:.2%}, live risk looks {risk_phrase}, "
        f"and the decision is backed by {sample_count} comparable outcomes."
    )

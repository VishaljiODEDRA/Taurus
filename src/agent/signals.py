from __future__ import annotations

import math
from datetime import UTC, datetime

from agent.chart import ChartAnalyzer
from agent.config import StrategySettings, UniverseSettings
from agent.ml import LightweightAlphaModel, MetaLabeler, OutcomeLearningProfile
from agent.regime import MarketRegime
from agent.timing import TradeTimingForecaster
from models import Candle, MarketSnapshot, NewsContext, SignalDecision


class SignalEngine:
    def __init__(self, strategy: StrategySettings, universe: UniverseSettings) -> None:
        self.strategy = strategy
        self.universe = universe
        self.chart_analyzer = ChartAnalyzer(strategy)
        self.alpha_model = LightweightAlphaModel()
        self.meta_labeler = MetaLabeler()
        self.timing_forecaster = TradeTimingForecaster()

    def rank(
        self,
        snapshots: dict[str, MarketSnapshot],
        news_contexts: dict[str, NewsContext],
        market_regime: MarketRegime | None = None,
        outcome_profile: OutcomeLearningProfile | None = None,
    ) -> list[SignalDecision]:
        benchmark_symbol = self.universe.benchmark_symbol.upper()
        benchmark_return_1m = _window_return(
            snapshots.get(benchmark_symbol).candles if snapshots.get(benchmark_symbol) else [],
            self.strategy.previous_month_window,
        )

        peer_moves = {
            symbol: _window_return(snapshot.candles, 1)
            for symbol, snapshot in snapshots.items()
        }

        decisions: list[SignalDecision] = []
        for symbol, snapshot in snapshots.items():
            if symbol == benchmark_symbol:
                continue
            decision = self._decision_for_snapshot(
                snapshot=snapshot,
                benchmark_return_1m=benchmark_return_1m,
                news_context=news_contexts.get(symbol, NewsContext(symbol=symbol)),
                peer_moves=peer_moves,
                market_regime=market_regime,
                outcome_profile=outcome_profile,
            )
            decisions.append(decision)
        return sorted(decisions, key=lambda item: item.score, reverse=True)

    def _decision_for_snapshot(
        self,
        *,
        snapshot: MarketSnapshot,
        benchmark_return_1m: float,
        news_context: NewsContext,
        peer_moves: dict[str, float],
        market_regime: MarketRegime | None,
        outcome_profile: OutcomeLearningProfile | None,
    ) -> SignalDecision:
        symbol = snapshot.symbol
        reasons: list[str] = []

        if not snapshot.instrument.is_currently_tradable:
            return SignalDecision(symbol, "HOLD", 1.0, 0.0, ("not currently tradable",))
        if not snapshot.instrument.is_buy_enabled and self.universe.long_only:
            return SignalDecision(symbol, "HOLD", 1.0, 0.0, ("buying disabled",))
        if not snapshot.instrument.is_exchange_open:
            reasons.append("exchange closed")

        has_sufficient_chart_history = len(snapshot.candles) >= self._minimum_candle_count()
        if not has_sufficient_chart_history:
            reasons.append("insufficient candle history")

        chart = self.chart_analyzer.analyze(snapshot.candles)
        relative_strength_1m = chart.return_1m - benchmark_return_1m
        peer_lag_score = self._peer_lag_score(symbol, peer_moves)
        news_source_count = len(
            {
                item.source.strip().lower()
                for item in news_context.items
                if item.source and item.source.strip()
            }
        )
        news_sources = sorted(
            {
                item.source.strip().lower()
                for item in news_context.items
                if item.source and item.source.strip()
            }
        )
        news_avg_item_age_hours = _average_news_age_hours(news_context)
        alpha = self.alpha_model.predict(
            chart=chart,
            relative_strength_1m=relative_strength_1m,
            news_context=news_context,
            peer_lag_score=peer_lag_score,
            spread_bps=snapshot.rate.spread_bps,
        )

        momentum_component = _clamp(
            (math.tanh((chart.return_1m * 5) + (chart.return_5d * 10) + (chart.return_1d * 3)) + 1)
            / 2
        )
        relative_strength_component = _clamp(0.5 + relative_strength_1m * 8)
        volume_component = _clamp((chart.volume_ratio_5_30 - 0.8) / 1.2)
        news_component = _clamp(0.5 + (news_context.sentiment_score / 2))
        catalyst_component = _clamp(news_context.catalyst_score + peer_lag_score)
        risk_penalty = _clamp(
            ((chart.volatility_1m - 0.025) / 0.075)
            + chart.overextension_penalty * 0.25
            + chart.downtrend_penalty * 0.35
        )

        positive_weights = (
            self.strategy.momentum_weight
            + self.strategy.relative_strength_weight
            + self.strategy.volume_weight
            + self.strategy.news_weight
            + self.strategy.catalyst_weight
            + self.strategy.chart_weight
            + self.strategy.ml_weight
        )
        gross_score = (
            self.strategy.momentum_weight * momentum_component
            + self.strategy.relative_strength_weight * relative_strength_component
            + self.strategy.volume_weight * volume_component
            + self.strategy.news_weight * news_component
            + self.strategy.catalyst_weight * catalyst_component
            + self.strategy.chart_weight * chart.chart_score
            + self.strategy.ml_weight * alpha.probability
        ) / max(positive_weights, 0.0001)
        score = _clamp(gross_score - self.strategy.risk_penalty_weight * risk_penalty)
        regime_penalty = 0.0
        if market_regime is not None:
            if market_regime.name in {"risk_off", "event_driven"}:
                regime_penalty = 0.10
            elif market_regime.name == "volatile":
                regime_penalty = 0.06
            elif market_regime.name == "weak":
                regime_penalty = 0.03
            score = _clamp(score - regime_penalty + (0.02 if market_regime.name == "bullish" else 0.0))
        if not has_sufficient_chart_history:
            score = min(score, max(self.strategy.buy_threshold - 0.001, 0.0))

        if chart.return_1d > 0:
            reasons.append(f"1d chart {chart.return_1d:.2%}")
        if chart.return_5d > 0:
            reasons.append(f"5d cycle {chart.return_5d:.2%}")
        if chart.return_1m > 0:
            reasons.append(f"1m cycle {chart.return_1m:.2%}")
        if relative_strength_1m > 0:
            reasons.append(f"beating benchmark by {relative_strength_1m:.2%}")
        if chart.volume_ratio_5_30 > 1.15:
            reasons.append(f"volume expansion {chart.volume_ratio_5_30:.2f}x")
        if chart.breakout_1m > 0.2:
            reasons.append("1m breakout pressure")
        if chart.support_bounce > 0.4:
            reasons.append("support bounce setup")
        if chart.ema_gap_pct > 0:
            reasons.append("EMA stack bullish")
        if chart.adx_14 >= 20:
            reasons.append(f"trend strength ADX {chart.adx_14:.1f}")
        if chart.stochastic_k >= chart.stochastic_d and chart.stochastic_k >= 55:
            reasons.append("stochastic momentum rising")
        if chart.vwap_distance_pct > 0:
            reasons.append("holding above rolling VWAP")
        if chart.obv_slope > 0:
            reasons.append("OBV accumulation")
        if has_sufficient_chart_history and alpha.probability > 0.68:
            reasons.append(f"ML alpha {alpha.probability:.2f}")
        if news_context.sentiment_score > 0.25:
            reasons.append("positive news sentiment")
        if news_context.catalyst_score > 0.2:
            reasons.append("30d news catalyst detected")
        if news_source_count >= 2:
            reasons.append(f"news breadth {news_source_count} sources")
        if peer_lag_score > 0:
            reasons.append("peer-laggard setup")
        if chart.rsi_14 >= 72:
            reasons.append("RSI overextension warning")
        if risk_penalty > 0.5:
            reasons.append("volatility penalty applied")
        if market_regime is not None and market_regime.name != "bullish":
            reasons.append(f"market regime {market_regime.name}")
        if not reasons:
            reasons.append("mixed or weak signal")

        meta = self.meta_labeler.predict(
            symbol=symbol,
            score=score,
            alpha=alpha,
            chart=chart,
            news_context=news_context,
            relative_strength_1m=relative_strength_1m,
            risk_penalty=risk_penalty,
            spread_bps=snapshot.rate.spread_bps,
            market_regime=market_regime,
            outcome_profile=outcome_profile,
            min_samples=self.strategy.meta_label_min_samples,
            take_threshold=self.strategy.meta_label_take_threshold,
            block_threshold=self.strategy.meta_label_block_threshold,
        )

        if score >= self.strategy.buy_threshold:
            action = "BUY"
            confidence = score
        elif score <= self.strategy.sell_threshold:
            action = "SELL"
            confidence = 1 - score
        else:
            action = "HOLD"
            confidence = _clamp(abs(score - 0.5) * 2)
        if (
            self.strategy.meta_labeling_enabled
            and action == "BUY"
            and not meta.take_trade
            and meta.source_sample_count >= max(3, self.strategy.meta_label_min_samples // 2)
        ):
            reasons.append("meta filter blocked trade")
            action = "HOLD"
            confidence = _clamp(max(meta.approval_score - 0.40, 0.0) * 1.6)

        features = {
            "return_1d": chart.return_1d,
            "return_5d": chart.return_5d,
            "return_1m": chart.return_1m,
            "relative_strength_1m": relative_strength_1m,
            "volume_ratio_5_30": chart.volume_ratio_5_30,
            "volatility_1m": chart.volatility_1m,
            "spread_bps": snapshot.rate.spread_bps,
            "news_sentiment": news_context.sentiment_score,
            "news_catalyst": news_context.catalyst_score,
            "news_item_count": len(news_context.items),
            "news_source_count": news_source_count,
            "news_sources": ",".join(news_sources),
            "news_avg_item_age_hours": news_avg_item_age_hours,
            "peer_lag_score": peer_lag_score,
            "risk_penalty": risk_penalty,
            "momentum_strength": chart.momentum_strength,
            "regime_penalty": regime_penalty,
            "has_sufficient_chart_history": has_sufficient_chart_history,
            "candle_count": len(snapshot.candles),
        }
        if market_regime is not None:
            features.update(market_regime.features)
        features.update(chart.as_features())
        features.update(alpha.as_features())
        features.update(meta.as_features())
        if action in {"BUY", "SELL"}:
            features.update(
                self.timing_forecaster.forecast_entry(
                    symbol=symbol,
                    action=action,
                    chart=chart,
                    news_context=news_context,
                    market_regime=market_regime,
                    outcome_profile=outcome_profile,
                    score=score,
                    confidence=confidence,
                ).as_features()
            )
        features.update(
            self._reasoning_features(
                symbol=symbol,
                action=action,
                score=score,
                chart=chart,
                alpha_probability=alpha.probability,
                relative_strength_1m=relative_strength_1m,
                news_context=news_context,
                peer_lag_score=peer_lag_score,
                risk_penalty=risk_penalty,
                benchmark_return_1m=benchmark_return_1m,
                meta_reason=meta.reason,
                meta_approval_score=meta.approval_score,
                expected_return=meta.expected_return,
                learned_edge=meta.learned_edge,
            )
        )
        return SignalDecision(
            symbol=symbol,
            action=action,
            confidence=confidence,
            score=score,
            reasons=tuple(reasons),
            features=features,
            news_context=news_context,
        )

    def _reasoning_features(
        self,
        *,
        symbol: str,
        action: str,
        score: float,
        chart,
        alpha_probability: float,
        relative_strength_1m: float,
        news_context: NewsContext,
        peer_lag_score: float,
        risk_penalty: float,
        benchmark_return_1m: float,
        meta_reason: str,
        meta_approval_score: float,
        expected_return: float,
        learned_edge: float,
    ) -> dict[str, str]:
        indicator_summary = (
            f"RSI={chart.rsi_14:.1f}, MACD_hist={chart.macd_histogram:.4f}, "
            f"EMA20={chart.ema_20:.2f}, EMA50={chart.ema_50:.2f}, "
            f"StochK={chart.stochastic_k:.1f}, ADX={chart.adx_14:.1f}, "
            f"CCI20={chart.cci_20:.1f}, ATR%={chart.atr_14_pct:.2%}, "
            f"VWAP_dist={chart.vwap_distance_pct:.2%}, OBV_slope={chart.obv_slope:.4f}"
        )
        market_summary = (
            f"1d={chart.return_1d:.2%}, 5d={chart.return_5d:.2%}, 1m={chart.return_1m:.2%}, "
            f"benchmark_1m={benchmark_return_1m:.2%}, rel_strength={relative_strength_1m:.2%}, "
            f"ma_alignment={chart.ma_alignment:.2%}, momentum_strength={chart.momentum_strength:.3f}, "
            f"chart_score={chart.chart_score:.3f}, risk_penalty={risk_penalty:.3f}"
        )
        news_summary = (
            f"sentiment={news_context.sentiment_score:.3f}, catalyst={news_context.catalyst_score:.3f}, "
            f"items={len(news_context.items)}, peer_lag={peer_lag_score:.3f}, ml_alpha={alpha_probability:.3f}"
        )
        meta_summary = (
            f"approval={meta_approval_score:.3f}, expected_return={expected_return:.2%}, "
            f"learned_edge={learned_edge:.3f}"
        )
        reasoning_summary = (
            f"{action} {symbol} because the trend is "
            f"{self._trend_phrase(chart, relative_strength_1m)}, the market backdrop is "
            f"{self._market_phrase(relative_strength_1m)}, news support is {self._news_phrase(news_context, peer_lag_score)}, "
            f"and overall risk looks {self._risk_phrase(risk_penalty)}."
        )
        return {
            "reasoning_summary": reasoning_summary,
            "indicator_summary": indicator_summary,
            "market_summary": market_summary,
            "news_summary": news_summary,
            "meta_summary": meta_summary,
            "meta_reasoning_summary": meta_reason,
        }

    def _trend_phrase(self, chart, relative_strength_1m: float) -> str:
        if chart.momentum_strength >= 0.65 and chart.chart_score >= 0.6:
            return "firmly constructive"
        if chart.momentum_strength <= 0.38 or chart.chart_score <= 0.4:
            return "soft and losing conviction"
        if abs(relative_strength_1m) < 0.01:
            return "mixed rather than decisive"
        return "moderately supportive"

    def _market_phrase(self, relative_strength_1m: float) -> str:
        if relative_strength_1m >= 0.03:
            return "stronger than the broader market"
        if relative_strength_1m <= -0.03:
            return "weaker than the broader market"
        return "roughly in line with the broader market"

    def _news_phrase(self, news_context: NewsContext, peer_lag_score: float) -> str:
        if news_context.catalyst_score >= 0.35 and news_context.sentiment_score >= 0.15:
            return "clearly positive"
        if news_context.sentiment_score <= -0.2:
            return "not supportive"
        if peer_lag_score > 0.15:
            return "helped by sector catch-up potential"
        return "limited but not harmful"

    def _risk_phrase(self, risk_penalty: float) -> str:
        if risk_penalty >= 0.55:
            return "elevated"
        if risk_penalty <= 0.25:
            return "reasonable"
        return "manageable"

    def _peer_lag_score(self, symbol: str, peer_moves: dict[str, float]) -> float:
        for group in self.strategy.peer_groups.values():
            if symbol.upper() not in group.symbols:
                continue
            current_move = peer_moves.get(symbol.upper(), 0.0)
            leader_move = max((peer_moves.get(peer, 0.0) for peer in group.symbols), default=0.0)
            if (
                leader_move >= group.leader_move_threshold_pct
                and current_move <= group.laggard_max_move_pct
                and current_move > -0.02
            ):
                return _clamp((leader_move - current_move) / group.leader_move_threshold_pct) * 0.4
        return 0.0

    def _minimum_candle_count(self) -> int:
        return max(
            self.strategy.previous_month_window + 1,
            self.strategy.slow_ma_period,
            self.strategy.volatility_window + 1,
            35,
        )


def _window_return(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    start = candles[-window - 1].close
    end = candles[-1].close
    if start <= 0:
        return 0.0
    return (end - start) / start


def _volume_ratio(candles: list[Candle], *, short: int, long: int) -> float:
    if len(candles) < long:
        return 1.0
    short_avg = sum(candle.volume for candle in candles[-short:]) / short
    long_avg = sum(candle.volume for candle in candles[-long:]) / long
    if long_avg <= 0:
        return 1.0
    return short_avg / long_avg


def _volatility(candles: list[Candle], window: int) -> float:
    if len(candles) < window + 1:
        return 0.0
    returns = []
    selected = candles[-window - 1 :]
    for previous, current in zip(selected, selected[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def _average_news_age_hours(news_context: NewsContext) -> float:
    ages: list[float] = []
    now = datetime.now(tz=UTC)
    for item in news_context.items:
        if item.published_at is None:
            continue
        ages.append(max((now - item.published_at.astimezone(UTC)).total_seconds() / 3600, 0.0))
    return sum(ages) / len(ages) if ages else 999.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)

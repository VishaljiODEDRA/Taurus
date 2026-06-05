from __future__ import annotations

from agent.chart import ChartAnalysis, ChartAnalyzer
from agent.config import ExitSettings, StrategySettings
from agent.timing import TradeTimingForecaster
from models import MarketSnapshot, NewsContext, PortfolioPosition, SignalDecision


class ExitManager:
    def __init__(self, exits: ExitSettings, strategy: StrategySettings) -> None:
        self.exits = exits
        self.chart_analyzer = ChartAnalyzer(strategy)
        self.timing_forecaster = TradeTimingForecaster()

    def evaluate(
        self,
        position: PortfolioPosition,
        snapshot: MarketSnapshot,
        news_context: NewsContext,
        benchmark_snapshot: MarketSnapshot | None = None,
        benchmark_news_context: NewsContext | None = None,
    ) -> SignalDecision | None:
        if not self.exits.enabled:
            return None
        current = snapshot.rate.mid
        if current <= 0:
            return None

        reasons: list[str] = []
        score = 0.5
        chart = self.chart_analyzer.analyze(snapshot.candles)
        effective_open_rate, open_rate_source = self._effective_open_rate(position)
        benchmark_chart = (
            self.chart_analyzer.analyze(benchmark_snapshot.candles)
            if benchmark_snapshot is not None
            else None
        )
        benchmark_news = (
            benchmark_news_context
            or NewsContext(symbol=benchmark_snapshot.symbol)
            if benchmark_snapshot is not None
            else None
        )

        if effective_open_rate > 0:
            pnl_pct = (current - effective_open_rate) / effective_open_rate
            dynamic_stop_pct, dynamic_take_profit_pct = self._dynamic_exit_thresholds(
                chart,
                benchmark_chart,
                news_context,
                benchmark_news,
            )
            if pnl_pct <= -self.exits.hard_stop_loss_pct:
                reasons.append(f"hard stop loss {pnl_pct:.2%}")
                score = 0.05
            if pnl_pct <= -dynamic_stop_pct:
                reasons.append(f"adaptive stop loss {pnl_pct:.2%} vs {dynamic_stop_pct:.2%}")
                score = min(score, 0.06)
            take_profit_hold = self._should_hold_winner(chart, benchmark_chart, news_context, benchmark_news)
            if self.exits.momentum_take_profit_min_pct <= pnl_pct < self.exits.momentum_take_profit_max_pct:
                if take_profit_hold:
                    reasons.append(f"profit {pnl_pct:.2%} but momentum still supportive")
                else:
                    reasons.append(f"profit window reached {pnl_pct:.2%}")
                    score = min(score, 0.18)
            elif pnl_pct >= self.exits.momentum_take_profit_max_pct and not take_profit_hold:
                reasons.append(f"momentum take profit {pnl_pct:.2%}")
                score = min(score, 0.16)
            if pnl_pct >= dynamic_take_profit_pct and not take_profit_hold:
                reasons.append(
                    f"adaptive take profit {pnl_pct:.2%} vs {dynamic_take_profit_pct:.2%}"
                )
                score = min(score, 0.14)
            if pnl_pct >= self.exits.take_profit_pct:
                reasons.append(f"take profit {pnl_pct:.2%}")
                score = min(score, 0.22)

        exit_pressure = self._exit_pressure(chart, benchmark_chart, news_context, benchmark_news)
        if self.exits.exit_on_ma_break and chart.ma_alignment < -0.005 and chart.return_5d < 0:
            reasons.append("MA break with weak 5d cycle")
            score = min(score, 0.25)
        if chart.downtrend_penalty > 0.65:
            reasons.append("downtrend regime")
            score = min(score, 0.28)
        if chart.momentum_strength < 0.42 and chart.ema_gap_pct < 0 and chart.vwap_distance_pct < 0:
            reasons.append("momentum rolled over")
            score = min(score, 0.24)
        if self.exits.exit_on_negative_news and news_context.sentiment_score <= -0.45:
            reasons.append("negative news context")
            score = min(score, 0.24)
        if benchmark_chart and benchmark_chart.momentum_strength < 0.38 and benchmark_chart.return_5d < 0:
            reasons.append("market regime weakening")
            score = min(score, 0.27)
        if exit_pressure >= self.exits.exit_pressure_threshold:
            reasons.append(f"multi-factor exit pressure {exit_pressure:.3f}")
            score = min(score, 0.15)

        if score > self.exits.min_exit_score or not reasons:
            return None
        timing = self.timing_forecaster.forecast_position(
            symbol=position.symbol,
            chart=chart,
            news_context=news_context,
            benchmark_chart=benchmark_chart,
            pnl_pct=(
                (current - effective_open_rate) / effective_open_rate
                if effective_open_rate > 0 and current > 0
                else position.pnl_pct
            ),
            exit_pressure=exit_pressure,
            dynamic_take_profit_pct=dynamic_take_profit_pct if effective_open_rate > 0 else self.exits.take_profit_pct,
            action="SELL",
        )
        features = {
            "exit_score": score,
            "exit_chart_score": chart.chart_score,
            "exit_ma_alignment": chart.ma_alignment,
            "exit_downtrend_penalty": chart.downtrend_penalty,
            "exit_momentum_strength": chart.momentum_strength,
            "exit_benchmark_momentum_strength": benchmark_chart.momentum_strength if benchmark_chart else 0.0,
            "exit_pressure": exit_pressure,
            "adaptive_stop_loss_pct": dynamic_stop_pct if effective_open_rate > 0 else 0.0,
            "adaptive_take_profit_pct": dynamic_take_profit_pct if effective_open_rate > 0 else 0.0,
            "existing_position_rule_applied": effective_open_rate > 0,
            "open_rate_source": open_rate_source,
            "exit_news_sentiment": news_context.sentiment_score,
            "reasoning_summary": self._exit_reasoning_summary(
                position=position,
                score=score,
                reasons=reasons,
                chart=chart,
                benchmark_chart=benchmark_chart,
                news_context=news_context,
                effective_open_rate=effective_open_rate,
                open_rate_source=open_rate_source,
                dynamic_stop_pct=dynamic_stop_pct if effective_open_rate > 0 else 0.0,
                dynamic_take_profit_pct=dynamic_take_profit_pct if effective_open_rate > 0 else 0.0,
            ),
            "indicator_summary": (
                f"RSI={chart.rsi_14:.1f}, MACD_hist={chart.macd_histogram:.4f}, "
                f"EMA_gap={chart.ema_gap_pct:.2%}, StochK={chart.stochastic_k:.1f}, "
                f"ADX={chart.adx_14:.1f}, VWAP_dist={chart.vwap_distance_pct:.2%}, "
                f"momentum_strength={chart.momentum_strength:.3f}"
            ),
            "market_summary": (
                f"symbol_5d={chart.return_5d:.2%}, symbol_1m={chart.return_1m:.2%}, "
                f"benchmark_momentum={benchmark_chart.momentum_strength:.3f}"
                if benchmark_chart
                else f"symbol_5d={chart.return_5d:.2%}, symbol_1m={chart.return_1m:.2%}, benchmark_momentum=n/a"
            ),
            "news_summary": (
                f"sentiment={news_context.sentiment_score:.3f}, catalyst={news_context.catalyst_score:.3f}, "
                f"items={len(news_context.items)}"
            ),
        }
        features.update(timing.as_features())
        return SignalDecision(
            symbol=position.symbol,
            action="SELL",
            confidence=1 - score,
            score=score,
            reasons=tuple(reasons),
            features=features,
            news_context=news_context,
        )

    def review_position(
        self,
        position: PortfolioPosition,
        snapshot: MarketSnapshot,
        news_context: NewsContext,
        benchmark_snapshot: MarketSnapshot | None = None,
        benchmark_news_context: NewsContext | None = None,
    ) -> SignalDecision:
        current = snapshot.rate.mid
        chart = self.chart_analyzer.analyze(snapshot.candles)
        benchmark_chart = (
            self.chart_analyzer.analyze(benchmark_snapshot.candles)
            if benchmark_snapshot is not None
            else None
        )
        benchmark_news = (
            benchmark_news_context
            or NewsContext(symbol=benchmark_snapshot.symbol)
            if benchmark_snapshot is not None
            else None
        )
        effective_open_rate, open_rate_source = self._effective_open_rate(position)
        pnl_pct = (
            (current - effective_open_rate) / effective_open_rate
            if effective_open_rate > 0 and current > 0
            else position.pnl_pct
        )
        dynamic_stop_pct, dynamic_take_profit_pct = self._dynamic_exit_thresholds(
            chart,
            benchmark_chart,
            news_context,
            benchmark_news,
        )
        exit_pressure = self._exit_pressure(chart, benchmark_chart, news_context, benchmark_news)
        should_hold = self._should_hold_winner(chart, benchmark_chart, news_context, benchmark_news)
        close_decision = self.evaluate(
            position,
            snapshot,
            news_context,
            benchmark_snapshot=benchmark_snapshot,
            benchmark_news_context=benchmark_news_context,
        )
        action = "SELL" if close_decision else "HOLD"
        headline = "close recommended" if close_decision else "hold and monitor"
        urgency_score = close_decision.confidence if close_decision else _clamp(
            0.55 * exit_pressure
            + 0.20 * _clamp(-pnl_pct * 8)
            + 0.15 * _clamp(0.5 - chart.momentum_strength)
            + 0.10 * _clamp(-news_context.sentiment_score)
        )
        reasons = close_decision.reasons if close_decision else (
            headline,
            f"adaptive stop {dynamic_stop_pct:.2%}",
            f"adaptive take profit {dynamic_take_profit_pct:.2%}",
        )
        confidence = close_decision.confidence if close_decision else max(exit_pressure, chart.momentum_strength)
        score = close_decision.score if close_decision else exit_pressure
        reasoning_summary = (
            f"{action} {position.symbol} for now because the position review sees "
            f"{'enough strength to stay patient' if should_hold else 'growing warning signs'}, "
            f"while market tone, recent news, and live protection levels guide whether holding still makes sense."
        )
        timing = self.timing_forecaster.forecast_position(
            symbol=position.symbol,
            chart=chart,
            news_context=news_context,
            benchmark_chart=benchmark_chart,
            pnl_pct=pnl_pct,
            exit_pressure=exit_pressure,
            dynamic_take_profit_pct=dynamic_take_profit_pct,
            action=action,
        )
        features = {
            "position_review": True,
            "existing_position_rule_applied": effective_open_rate > 0,
            "open_rate_source": open_rate_source,
            "review_current_price": current,
            "review_open_rate": effective_open_rate,
            "review_pnl_pct": pnl_pct,
            "adaptive_stop_loss_pct": dynamic_stop_pct,
            "adaptive_take_profit_pct": dynamic_take_profit_pct,
            "exit_pressure": exit_pressure,
            "hold_strength": chart.momentum_strength,
            "market_regime_strength": benchmark_chart.momentum_strength if benchmark_chart else 0.5,
            "urgency_score": urgency_score,
            "reasoning_summary": reasoning_summary,
            "indicator_summary": (
                f"RSI={chart.rsi_14:.1f}, MACD_hist={chart.macd_histogram:.4f}, "
                f"EMA_gap={chart.ema_gap_pct:.2%}, StochK={chart.stochastic_k:.1f}, "
                f"ADX={chart.adx_14:.1f}, ATR%={chart.atr_14_pct:.2%}, "
                f"VWAP_dist={chart.vwap_distance_pct:.2%}, momentum_strength={chart.momentum_strength:.3f}"
            ),
            "market_summary": (
                f"benchmark_5d={(benchmark_chart.return_5d if benchmark_chart else 0.0):.2%}, "
                f"benchmark_1m={(benchmark_chart.return_1m if benchmark_chart else 0.0):.2%}, "
                f"benchmark_momentum={(benchmark_chart.momentum_strength if benchmark_chart else 0.5):.3f}"
            ),
            "news_summary": (
                f"sentiment={news_context.sentiment_score:.3f}, catalyst={news_context.catalyst_score:.3f}, "
                f"items={len(news_context.items)}, benchmark_sentiment={(benchmark_news.sentiment_score if benchmark_news else 0.0):.3f}"
            ),
        }
        features.update(timing.as_features())
        return SignalDecision(
            symbol=position.symbol,
            action=action,
            confidence=confidence,
            score=score,
            reasons=reasons,
            features=features,
            news_context=news_context,
        )

    def _should_hold_winner(
        self,
        chart: ChartAnalysis,
        benchmark_chart: ChartAnalysis | None,
        news_context: NewsContext,
        benchmark_news_context: NewsContext | None,
    ) -> bool:
        strong_symbol_momentum = (
            chart.momentum_strength >= self.exits.momentum_hold_threshold
            and chart.ma_alignment > 0
            and chart.ema_gap_pct >= 0
            and chart.vwap_distance_pct >= -0.002
        )
        if not self.exits.hold_on_positive_momentum:
            strong_symbol_momentum = False

        strong_market = True
        if self.exits.require_market_confirmation_for_take_profit:
            strong_market = bool(
                benchmark_chart
                and benchmark_chart.momentum_strength >= self.exits.market_hold_threshold
                and benchmark_chart.return_5d >= -0.002
                and benchmark_chart.ema_gap_pct >= -0.002
            )

        supportive_news = True
        if self.exits.require_news_confirmation_for_take_profit:
            benchmark_sentiment = benchmark_news_context.sentiment_score if benchmark_news_context else 0.0
            supportive_news = (
                news_context.sentiment_score >= self.exits.news_hold_sentiment_floor
                and benchmark_sentiment >= -0.15
            )

        return strong_symbol_momentum and strong_market and supportive_news

    def _effective_open_rate(self, position: PortfolioPosition) -> tuple[float, str]:
        if position.open_rate > 0:
            return position.open_rate, "broker_open_rate"
        if position.units > 0 and position.invested_usd > 0:
            return position.invested_usd / position.units, "derived_from_invested_usd"
        return 0.0, "missing"

    def _dynamic_exit_thresholds(
        self,
        chart: ChartAnalysis,
        benchmark_chart: ChartAnalysis | None,
        news_context: NewsContext,
        benchmark_news_context: NewsContext | None,
    ) -> tuple[float, float]:
        market_strength = benchmark_chart.momentum_strength if benchmark_chart else 0.5
        benchmark_sentiment = benchmark_news_context.sentiment_score if benchmark_news_context else 0.0
        quality = _clamp(
            0.45 * chart.momentum_strength
            + 0.20 * chart.chart_score
            + 0.15 * _clamp(0.5 + news_context.sentiment_score / 2)
            + 0.10 * market_strength
            + 0.10 * (0.5 + benchmark_sentiment / 2)
        )
        risk = _clamp(
            0.40 * chart.downtrend_penalty
            + 0.20 * chart.overextension_penalty
            + 0.20 * _clamp(chart.atr_14_pct / max(self.exits.max_dynamic_stop_loss_pct, 0.0001))
            + 0.20 * _clamp(0.5 - market_strength)
        )
        stop_pct = _clamp(
            max(chart.atr_14_pct * 1.20, self.exits.min_dynamic_stop_loss_pct)
            + 0.006 * quality
            - 0.008 * risk,
            self.exits.min_dynamic_stop_loss_pct,
            self.exits.max_dynamic_stop_loss_pct,
        )
        take_profit_pct = _clamp(
            stop_pct
            * _clamp(1.25 + 0.90 * quality - 0.60 * risk, 1.15, 3.0)
            + 0.010 * news_context.catalyst_score,
            self.exits.min_dynamic_take_profit_pct,
            self.exits.max_dynamic_take_profit_pct,
        )
        return stop_pct, take_profit_pct

    def _exit_pressure(
        self,
        chart: ChartAnalysis,
        benchmark_chart: ChartAnalysis | None,
        news_context: NewsContext,
        benchmark_news_context: NewsContext | None,
    ) -> float:
        market_momentum = benchmark_chart.momentum_strength if benchmark_chart else 0.5
        market_return = benchmark_chart.return_5d if benchmark_chart else 0.0
        market_news = benchmark_news_context.sentiment_score if benchmark_news_context else 0.0
        return _clamp(
            0.28 * chart.downtrend_penalty
            + 0.16 * _clamp(-chart.ema_gap_pct / 0.03)
            + 0.12 * _clamp(-chart.vwap_distance_pct / 0.03)
            + 0.12 * _clamp((45 - chart.rsi_14) / 20)
            + 0.10 * _clamp(-chart.macd_histogram * 25)
            + 0.08 * _clamp(-news_context.sentiment_score)
            + 0.06 * _clamp(0.5 - market_momentum)
            + 0.04 * _clamp(-market_return * 8)
            + 0.04 * _clamp(-market_news)
        )

    def _exit_reasoning_summary(
        self,
        *,
        position: PortfolioPosition,
        score: float,
        reasons: list[str],
        chart: ChartAnalysis,
        benchmark_chart: ChartAnalysis | None,
        news_context: NewsContext,
        effective_open_rate: float,
        open_rate_source: str,
        dynamic_stop_pct: float,
        dynamic_take_profit_pct: float,
    ) -> str:
        return (
            f"SELL {position.symbol} because the position is under pressure, "
            f"market support is fading, and the live review says protecting capital now is safer than waiting for the setup to recover."
        )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(min(value, high), low)

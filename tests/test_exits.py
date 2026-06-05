from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import ExitSettings, StrategySettings
from agent.exits import ExitManager
from models import Candle, Instrument, MarketSnapshot, NewsContext, PortfolioPosition, Rate


class ExitManagerTest(unittest.TestCase):
    def test_holds_profit_when_symbol_and_market_momentum_stay_positive(self) -> None:
        manager = ExitManager(
            ExitSettings(
                momentum_take_profit_min_pct=0.01,
                momentum_take_profit_max_pct=0.015,
                momentum_hold_threshold=0.45,
                market_hold_threshold=0.45,
            ),
            StrategySettings(),
        )
        snapshot = _snapshot("AAPL", start=100, daily_returns=[0.002] * 54 + [-0.001] * 5 + [0.0008])
        decision = manager.evaluate(
            _position("AAPL", snapshot=snapshot, pnl_pct=0.012),
            snapshot,
            NewsContext("AAPL", sentiment_score=0.4),
            benchmark_snapshot=_snapshot("SPY", start=100, daily_returns=[0.002] * 60),
            benchmark_news_context=NewsContext("SPY", sentiment_score=0.2),
        )

        self.assertIsNone(decision)

    def test_closes_profit_window_when_momentum_weakens(self) -> None:
        manager = ExitManager(
            ExitSettings(
                momentum_take_profit_min_pct=0.01,
                momentum_take_profit_max_pct=0.015,
            ),
            StrategySettings(),
        )
        snapshot = _snapshot("AAPL", start=100, daily_returns=[0.0025] * 50 + [-0.004] * 9 + [0.008])
        decision = manager.evaluate(
            _position("AAPL", snapshot=snapshot, pnl_pct=0.012),
            snapshot,
            NewsContext("AAPL", sentiment_score=-0.2),
            benchmark_snapshot=_snapshot("SPY", start=100, daily_returns=[-0.002] * 60),
            benchmark_news_context=NewsContext("SPY", sentiment_score=-0.3),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.action, "SELL")
        self.assertIn("profit window reached", " ".join(decision.reasons))
        self.assertEqual(decision.features["timing_close_action"], "SELL")
        self.assertEqual(decision.features["timing_likely_days"], 0)

    def test_existing_position_without_open_rate_still_gets_adaptive_rules(self) -> None:
        manager = ExitManager(ExitSettings(), StrategySettings())
        snapshot = _snapshot("AAPL", start=100, daily_returns=[0.0025] * 50 + [-0.004] * 9 + [0.008])
        position = PortfolioPosition(
            symbol="AAPL",
            instrument_id=1,
            position_id="AAPL-legacy",
            units=10,
            invested_usd=1_000.0,
            current_value_usd=950.0,
            pnl_usd=-50.0,
            open_rate=0.0,
        )
        decision = manager.evaluate(
            position,
            snapshot,
            NewsContext("AAPL", sentiment_score=-0.3),
            benchmark_snapshot=_snapshot("SPY", start=100, daily_returns=[-0.002] * 60),
            benchmark_news_context=NewsContext("SPY", sentiment_score=-0.2),
        )

        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertTrue(decision.features["existing_position_rule_applied"])
        self.assertEqual(decision.features["open_rate_source"], "derived_from_invested_usd")
        self.assertGreater(decision.features["adaptive_stop_loss_pct"], 0.0)

    def test_review_position_returns_dashboard_for_hold_case(self) -> None:
        manager = ExitManager(
            ExitSettings(momentum_hold_threshold=0.45, market_hold_threshold=0.45),
            StrategySettings(),
        )
        snapshot = _snapshot("AAPL", start=100, daily_returns=[0.002] * 54 + [-0.001] * 5 + [0.0008])
        review = manager.review_position(
            _position("AAPL", snapshot=snapshot, pnl_pct=0.012),
            snapshot,
            NewsContext("AAPL", sentiment_score=0.4, catalyst_score=0.3),
            benchmark_snapshot=_snapshot("SPY", start=100, daily_returns=[0.002] * 60),
            benchmark_news_context=NewsContext("SPY", sentiment_score=0.2),
        )

        self.assertEqual(review.action, "HOLD")
        self.assertTrue(review.features["position_review"])
        self.assertIn("position review sees enough strength to stay patient", review.features["reasoning_summary"])
        self.assertEqual(review.features["timing_close_action"], "SELL")
        self.assertGreaterEqual(review.features["timing_likely_days"], 1)
        self.assertIn("SELL AAPL is most likely", review.features["timing_reason"])


def _position(symbol: str, *, snapshot: MarketSnapshot, pnl_pct: float) -> PortfolioPosition:
    invested = 1_000.0
    pnl_usd = invested * pnl_pct
    current_price = snapshot.rate.mid
    open_rate = current_price / (1 + pnl_pct)
    return PortfolioPosition(
        symbol=symbol,
        instrument_id=1,
        position_id=f"{symbol}-1",
        units=10,
        invested_usd=invested,
        current_value_usd=invested + pnl_usd,
        pnl_usd=pnl_usd,
        open_rate=open_rate,
    )


def _snapshot(symbol: str, *, start: float, daily_returns: list[float]) -> MarketSnapshot:
    now = datetime.now(tz=UTC)
    candles = []
    price = start
    for index, daily_return in enumerate(daily_returns):
        close = max(price * (1 + daily_return), 1.0)
        candles.append(
            Candle(
                timestamp=now - timedelta(days=len(daily_returns) - index),
                open=price,
                high=max(price, close) * 1.01,
                low=min(price, close) * 0.99,
                close=close,
                volume=1_000_000 + index * 20_000,
            )
        )
        price = close
    instrument = Instrument(symbol=symbol, instrument_id=1, asset_type="Stock")
    rate = Rate(1, bid=price * 0.999, ask=price * 1.001, last_execution=price, timestamp=now)
    return MarketSnapshot(instrument, rate, candles)


if __name__ == "__main__":
    unittest.main()

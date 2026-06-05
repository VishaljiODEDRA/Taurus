from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import StrategySettings, UniverseSettings
from agent.ml import OutcomeMemoryBuilder
from agent.signals import SignalEngine
from models import Candle, Instrument, MarketSnapshot, NewsContext, NewsItem, Rate


class SignalEngineTest(unittest.TestCase):
    def test_positive_momentum_and_news_can_rank_buy(self) -> None:
        strategy = StrategySettings(buy_threshold=0.65)
        universe = UniverseSettings(symbols=("AAPL", "SPY"), benchmark_symbol="SPY")
        engine = SignalEngine(strategy, universe)
        snapshots = {
            "AAPL": _snapshot("AAPL", start=100, daily_return=0.01),
            "SPY": _snapshot("SPY", start=100, daily_return=0.001),
        }
        news = {"AAPL": NewsContext("AAPL", sentiment_score=0.9, catalyst_score=0.8)}

        decisions = engine.rank(snapshots, news)

        self.assertEqual(decisions[0].symbol, "AAPL")
        self.assertEqual(decisions[0].action, "BUY")
        self.assertGreaterEqual(decisions[0].score, 0.65)
        self.assertEqual(decisions[0].features["timing_close_action"], "SELL")
        self.assertGreaterEqual(decisions[0].features["timing_likely_days"], 1)
        self.assertIn("SELL AAPL is most likely", decisions[0].features["timing_reason"])

    def test_missing_candles_hold_with_low_directional_confidence(self) -> None:
        strategy = StrategySettings(buy_threshold=0.65)
        universe = UniverseSettings(symbols=("AAPL", "SPY"), benchmark_symbol="SPY")
        engine = SignalEngine(strategy, universe)
        snapshots = {
            "AAPL": _snapshot("AAPL", start=100, daily_return=0.01, candle_count=0),
            "SPY": _snapshot("SPY", start=100, daily_return=0.001, candle_count=0),
        }
        news = {"AAPL": NewsContext("AAPL", sentiment_score=0.9, catalyst_score=0.8)}

        decisions = engine.rank(snapshots, news)

        self.assertEqual(decisions[0].action, "HOLD")
        self.assertIn("insufficient candle history", decisions[0].reasons)
        self.assertLess(decisions[0].confidence, 0.4)
        self.assertFalse(decisions[0].features["has_sufficient_chart_history"])

    def test_news_source_breadth_feeds_signal_features(self) -> None:
        strategy = StrategySettings(buy_threshold=0.65)
        universe = UniverseSettings(symbols=("AAPL", "SPY"), benchmark_symbol="SPY")
        engine = SignalEngine(strategy, universe)
        snapshots = {
            "AAPL": _snapshot("AAPL", start=100, daily_return=0.01),
            "SPY": _snapshot("SPY", start=100, daily_return=0.001),
        }
        news = {
            "AAPL": NewsContext(
                "AAPL",
                sentiment_score=0.6,
                catalyst_score=0.5,
                items=(
                    NewsItem("AAPL raises guidance", source="reuters.com"),
                    NewsItem("AAPL gets analyst upgrade", source="marketwatch.com"),
                ),
            )
        }

        decision = engine.rank(snapshots, news)[0]

        self.assertEqual(decision.features["news_source_count"], 2)
        self.assertIn("news breadth 2 sources", decision.reasons)
        self.assertGreater(decision.features["ml_news_source_breadth"], 0.0)
        self.assertIn("BUY AAPL because the trend is", decision.features["reasoning_summary"])
        self.assertIn("RSI=", decision.features["indicator_summary"])
        self.assertIn("sentiment=", decision.features["news_summary"])

    def test_sell_signal_gets_buy_to_close_timing_forecast_when_shorting_enabled(self) -> None:
        strategy = StrategySettings(buy_threshold=0.75, sell_threshold=0.35)
        universe = UniverseSettings(symbols=("AAPL", "SPY"), benchmark_symbol="SPY", long_only=False)
        engine = SignalEngine(strategy, universe)
        snapshots = {
            "AAPL": _snapshot("AAPL", start=100, daily_return=-0.012),
            "SPY": _snapshot("SPY", start=100, daily_return=0.002),
        }
        news = {"AAPL": NewsContext("AAPL", sentiment_score=-0.7, catalyst_score=0.3)}

        decision = engine.rank(snapshots, news)[0]

        self.assertEqual(decision.action, "SELL")
        self.assertEqual(decision.features["timing_close_action"], "BUY_TO_CLOSE")
        self.assertGreaterEqual(decision.features["timing_likely_days"], 1)

    def test_meta_label_can_block_buy_after_poor_outcomes(self) -> None:
        strategy = StrategySettings(
            buy_threshold=0.65,
            meta_labeling_enabled=True,
            meta_label_min_samples=6,
            meta_label_take_threshold=0.57,
            meta_label_block_threshold=0.50,
        )
        universe = UniverseSettings(symbols=("AAPL", "SPY"), benchmark_symbol="SPY")
        engine = SignalEngine(strategy, universe)
        snapshots = {
            "AAPL": _snapshot("AAPL", start=100, daily_return=0.01),
            "SPY": _snapshot("SPY", start=100, daily_return=0.001),
        }
        news = {"AAPL": NewsContext("AAPL", sentiment_score=0.9, catalyst_score=0.8)}
        outcome_profile = OutcomeMemoryBuilder().build(
            [
                {"symbol": "AAPL", "return_pct": -0.025, "pnl_usd": -25, "holding_days": 5},
                {"symbol": "AAPL", "return_pct": -0.021, "pnl_usd": -21, "holding_days": 6},
                {"symbol": "AAPL", "return_pct": -0.018, "pnl_usd": -18, "holding_days": 4},
                {"symbol": "AAPL", "return_pct": -0.017, "pnl_usd": -17, "holding_days": 5},
                {"symbol": "AAPL", "return_pct": -0.022, "pnl_usd": -22, "holding_days": 7},
                {"symbol": "AAPL", "return_pct": -0.020, "pnl_usd": -20, "holding_days": 4},
            ]
        )

        decision = engine.rank(snapshots, news, outcome_profile=outcome_profile)[0]

        self.assertEqual(decision.action, "HOLD")
        self.assertIn("meta filter blocked trade", decision.reasons)
        self.assertFalse(decision.features["meta_take_trade"])
        self.assertIn("Meta filter is holding back the trade", decision.features["meta_reasoning_summary"])


def _snapshot(
    symbol: str,
    *,
    start: float,
    daily_return: float,
    candle_count: int = 80,
) -> MarketSnapshot:
    now = datetime.now(tz=UTC)
    candles = []
    price = start
    for days_ago in range(candle_count, 0, -1):
        close = price * (1 + daily_return)
        candles.append(
            Candle(
                timestamp=now - timedelta(days=days_ago),
                open=price,
                high=max(price, close) * 1.01,
                low=min(price, close) * 0.99,
                close=close,
                volume=1_000_000 + (80 - days_ago) * 10_000,
            )
        )
        price = close
    instrument = Instrument(symbol=symbol, instrument_id=1, asset_type="Stock")
    rate = Rate(1, bid=price * 0.999, ask=price * 1.001, last_execution=price, timestamp=now)
    return MarketSnapshot(instrument, rate, candles)


if __name__ == "__main__":
    unittest.main()

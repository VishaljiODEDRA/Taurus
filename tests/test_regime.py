from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import StrategySettings
from agent.regime import MarketRegimeEngine
from models import Candle, Instrument, MarketSnapshot, NewsContext, Rate


class MarketRegimeEngineTest(unittest.TestCase):
    def test_classifies_bullish_market(self) -> None:
        regime = MarketRegimeEngine(StrategySettings()).classify(
            _snapshot("SPY", 100, [0.003] * 60),
            NewsContext("SPY", sentiment_score=0.2, catalyst_score=0.1),
        )

        self.assertEqual(regime.name, "bullish")
        self.assertGreaterEqual(regime.size_multiplier, 0.9)
        self.assertAlmostEqual(sum(regime.probabilities.values()), 1.0, places=4)
        self.assertIn("regime_probability_bullish", regime.features)

    def test_classifies_risk_off_market(self) -> None:
        regime = MarketRegimeEngine(StrategySettings()).classify(
            _snapshot("SPY", 100, [-0.004] * 55 + [0.0005] * 5),
            NewsContext("SPY", sentiment_score=-0.4, catalyst_score=0.2),
        )

        self.assertIn(regime.name, {"risk_off", "volatile", "event_driven"})
        self.assertLessEqual(regime.size_multiplier, 0.6)

    def test_transition_prior_keeps_probabilities_stable_across_similar_cycles(self) -> None:
        engine = MarketRegimeEngine(StrategySettings())
        first = engine.classify(
            _snapshot("SPY", 100, [0.002] * 60),
            NewsContext("SPY", sentiment_score=0.1, catalyst_score=0.1),
        )
        second = engine.classify(
            _snapshot("SPY", 100, [0.0022] * 60),
            NewsContext("SPY", sentiment_score=0.12, catalyst_score=0.08),
        )

        self.assertLess(abs(first.probabilities["bullish"] - second.probabilities["bullish"]), 0.15)


def _snapshot(symbol: str, start: float, daily_returns: list[float]) -> MarketSnapshot:
    now = datetime.now(tz=UTC)
    candles: list[Candle] = []
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
                volume=5_000_000 + index * 30_000,
            )
        )
        price = close
    instrument = Instrument(symbol=symbol, instrument_id=1, asset_type="ETF")
    rate = Rate(1, bid=price * 0.999, ask=price * 1.001, last_execution=price, timestamp=now)
    return MarketSnapshot(instrument, rate, candles)


if __name__ == "__main__":
    unittest.main()

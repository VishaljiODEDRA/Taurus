from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.chart import ChartAnalyzer
from agent.config import StrategySettings
from agent.ml import LightweightAlphaModel
from models import Candle, NewsContext


class ChartAnalysisTest(unittest.TestCase):
    def test_chart_analyzer_detects_multi_window_uptrend(self) -> None:
        candles = _candles(
            start=100,
            daily_returns=([0.004, -0.003, 0.005, 0.001, -0.002] * 7)
            + [0.004, -0.002, 0.005, -0.001, 0.004],
        )
        analysis = ChartAnalyzer(StrategySettings()).analyze(candles)

        self.assertGreater(analysis.return_1d, 0)
        self.assertGreater(analysis.return_5d, 0)
        self.assertGreater(analysis.return_1m, 0)
        self.assertGreater(analysis.ma_alignment, 0)
        self.assertGreater(analysis.chart_score, 0.55)

    def test_alpha_model_uses_chart_and_news_alignment(self) -> None:
        candles = _candles(start=100, daily_returns=[0.002] * 30 + [0.006] * 10)
        analysis = ChartAnalyzer(StrategySettings()).analyze(candles)
        output = LightweightAlphaModel().predict(
            chart=analysis,
            relative_strength_1m=0.04,
            news_context=NewsContext("AAPL", sentiment_score=0.7, catalyst_score=0.8),
            peer_lag_score=0.2,
            spread_bps=5,
        )

        self.assertGreater(output.probability, 0.65)
        self.assertGreater(output.catalyst_alignment, 0.6)

    def test_alpha_model_stays_neutral_without_chart_evidence(self) -> None:
        analysis = ChartAnalyzer(StrategySettings()).analyze([])
        output = LightweightAlphaModel().predict(
            chart=analysis,
            relative_strength_1m=0.0,
            news_context=NewsContext("F"),
            peer_lag_score=0.0,
            spread_bps=5,
        )

        self.assertLess(output.probability, 0.55)

    def test_chart_analyzer_populates_extended_indicator_pack(self) -> None:
        candles = _candles(start=100, daily_returns=[0.003, 0.002, -0.001, 0.004, 0.003] * 12)
        analysis = ChartAnalyzer(StrategySettings()).analyze(candles)

        self.assertGreater(analysis.ema_20, 0)
        self.assertGreater(analysis.ema_50, 0)
        self.assertGreaterEqual(analysis.stochastic_k, 0)
        self.assertLessEqual(analysis.stochastic_k, 100)
        self.assertGreaterEqual(analysis.bollinger_percent_b, 0)
        self.assertLessEqual(analysis.bollinger_percent_b, 1)
        self.assertGreaterEqual(analysis.momentum_strength, 0)
        self.assertLessEqual(analysis.momentum_strength, 1)
        self.assertGreaterEqual(analysis.micro_volatility_burst, 0)
        self.assertLessEqual(analysis.micro_liquidity_stress, 1)


def _candles(*, start: float, daily_returns: list[float]) -> list[Candle]:
    now = datetime.now(tz=UTC)
    candles = []
    price = start
    for index, daily_return in enumerate(daily_returns):
        close = price * (1 + daily_return)
        high = max(price, close) * 1.01
        low = min(price, close) * 0.99
        candles.append(
            Candle(
                timestamp=now - timedelta(days=len(daily_returns) - index),
                open=price,
                high=high,
                low=low,
                close=close,
                volume=1_000_000 + index * 20_000,
            )
        )
        price = close
    return candles


if __name__ == "__main__":
    unittest.main()

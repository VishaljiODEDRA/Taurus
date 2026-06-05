from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.allocation import CapitalAllocator, apply_planned_exits, reserve_trade_notional
from agent.config import RiskSettings, StrategySettings, UniverseSettings
from agent.portfolio import PortfolioOptimizer
from agent.regime import MarketRegime
from models import Candle, Instrument, MarketSnapshot, PortfolioPosition, PortfolioState, Rate, SignalDecision


class PortfolioOptimizerTest(unittest.TestCase):
    def test_optimizer_can_resize_candidate_to_fit_constraints(self) -> None:
        optimizer = PortfolioOptimizer(
            RiskSettings(max_portfolio_hhi=0.14, max_projected_stress_loss_pct=0.04),
            StrategySettings(),
            UniverseSettings(symbols=("AAPL", "MSFT", "SPY")),
        )
        portfolio = PortfolioState(
            nav_usd=10_000,
            available_cash_usd=8_000,
            positions=(PortfolioPosition("MSFT", 2, "p1", 1, 1_800, 1_900),),
        )
        snapshots = {
            "AAPL": _snapshot("AAPL", 100, [0.002] * 60),
            "MSFT": _snapshot("MSFT", 100, [0.002] * 60),
            "SPY": _snapshot("SPY", 100, [0.0015] * 60),
        }
        regime = MarketRegime("weak", 0.7, 0.55, 0.75, "weak", {})

        report = optimizer.evaluate_candidate(
            symbol="AAPL",
            target_notional_usd=500,
            portfolio=portfolio,
            all_snapshots=snapshots,
            benchmark_symbol="SPY",
            market_regime=regime,
        )

        self.assertTrue(report.approved)
        self.assertLessEqual(report.adjusted_notional_usd, 500)

    def test_allocator_reserves_cash_and_prioritizes_ranked_candidates(self) -> None:
        allocator = CapitalAllocator(
            RiskSettings(
                max_position_pct_nav=0.05,
                min_order_usd=25,
                max_portfolio_hhi=0.30,
                max_projected_stress_loss_pct=0.08,
            ),
            StrategySettings(),
            UniverseSettings(symbols=("AAPL", "MSFT", "NVDA", "SPY")),
        )
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=700)
        snapshots = {
            "AAPL": _snapshot("AAPL", 100, [0.002] * 60),
            "MSFT": _snapshot("MSFT", 100, [0.0015] * 60),
            "NVDA": _snapshot("NVDA", 100, [0.001] * 60),
            "SPY": _snapshot("SPY", 100, [0.001] * 60),
        }
        decisions = [
            SignalDecision("AAPL", "BUY", confidence=0.9, score=0.92),
            SignalDecision("MSFT", "BUY", confidence=0.8, score=0.86),
            SignalDecision("NVDA", "BUY", confidence=0.7, score=0.78),
        ]
        regime = MarketRegime("bullish", 0.8, 0.35, 1.05, "bullish", {})

        allocations = allocator.allocate(
            decisions,
            portfolio,
            snapshots,
            benchmark_symbol="SPY",
            market_regime=regime,
        )

        self.assertTrue(allocations["AAPL"].approved)
        self.assertTrue(allocations["MSFT"].approved)
        self.assertTrue(allocations["NVDA"].approved)
        self.assertGreater(allocations["AAPL"].target_notional_usd, allocations["MSFT"].target_notional_usd)
        self.assertGreater(allocations["MSFT"].target_notional_usd, allocations["NVDA"].target_notional_usd)
        total_allocated = sum(item.target_notional_usd for item in allocations.values() if item.approved)
        self.assertLessEqual(total_allocated, portfolio.available_cash_usd * 0.95 + 0.01)

    def test_allocator_gives_more_room_to_higher_learned_edge(self) -> None:
        allocator = CapitalAllocator(
            RiskSettings(
                max_position_pct_nav=0.05,
                min_order_usd=25,
                max_portfolio_hhi=0.30,
                max_projected_stress_loss_pct=0.08,
            ),
            StrategySettings(),
            UniverseSettings(symbols=("AAPL", "MSFT", "SPY")),
        )
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=700)
        snapshots = {
            "AAPL": _snapshot("AAPL", 100, [0.002] * 60),
            "MSFT": _snapshot("MSFT", 100, [0.002] * 60),
            "SPY": _snapshot("SPY", 100, [0.001] * 60),
        }
        decisions = [
            SignalDecision(
                "AAPL",
                "BUY",
                confidence=0.8,
                score=0.8,
                features={
                    "momentum_strength": 0.7,
                    "market_regime_strength": 0.6,
                    "news_catalyst": 0.5,
                    "meta_learned_edge": 0.82,
                    "meta_expected_return": 0.018,
                    "meta_approval_score": 0.80,
                },
            ),
            SignalDecision(
                "MSFT",
                "BUY",
                confidence=0.8,
                score=0.8,
                features={
                    "momentum_strength": 0.7,
                    "market_regime_strength": 0.6,
                    "news_catalyst": 0.5,
                    "meta_learned_edge": 0.28,
                    "meta_expected_return": -0.004,
                    "meta_approval_score": 0.54,
                },
            ),
        ]

        allocations = allocator.allocate(
            decisions,
            portfolio,
            snapshots,
            benchmark_symbol="SPY",
            market_regime=None,
        )

        self.assertGreater(allocations["AAPL"].target_notional_usd, allocations["MSFT"].target_notional_usd)

    def test_allocator_drops_candidate_when_weight_is_below_minimum_order(self) -> None:
        allocator = CapitalAllocator(
            RiskSettings(
                max_position_pct_nav=0.05,
                min_order_usd=100,
                max_portfolio_hhi=0.30,
                max_projected_stress_loss_pct=0.08,
            ),
            StrategySettings(),
            UniverseSettings(symbols=("AAPL", "MSFT", "NVDA", "SPY")),
        )
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=320)
        snapshots = {
            "AAPL": _snapshot("AAPL", 100, [0.002] * 60),
            "MSFT": _snapshot("MSFT", 100, [0.0015] * 60),
            "NVDA": _snapshot("NVDA", 100, [0.001] * 60),
            "SPY": _snapshot("SPY", 100, [0.001] * 60),
        }
        decisions = [
            SignalDecision("AAPL", "BUY", confidence=0.95, score=0.95),
            SignalDecision("MSFT", "BUY", confidence=0.7, score=0.75),
            SignalDecision("NVDA", "BUY", confidence=0.55, score=0.62),
        ]

        allocations = allocator.allocate(
            decisions,
            portfolio,
            snapshots,
            benchmark_symbol="SPY",
            market_regime=None,
        )

        approved = [item for item in allocations.values() if item.approved]
        rejected = [item for item in allocations.values() if not item.approved]
        self.assertEqual(len(approved), 1)
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(item.reason == "allocation_target_too_small" for item in rejected))

    def test_apply_planned_exits_releases_cash_before_buy_planning(self) -> None:
        portfolio = PortfolioState(
            nav_usd=10_000,
            available_cash_usd=500,
            positions=(
                PortfolioPosition("AAPL", 1, "p1", 1, 400, 450),
                PortfolioPosition("MSFT", 2, "p2", 1, 500, 520),
            ),
        )
        planned = apply_planned_exits(
            portfolio,
            [SignalDecision("AAPL", "SELL", confidence=0.8, score=0.2)],
        )

        self.assertEqual(len(planned.positions), 1)
        self.assertEqual(planned.positions[0].symbol, "MSFT")
        self.assertEqual(planned.available_cash_usd, 950)

    def test_reserve_trade_notional_updates_shadow_portfolio(self) -> None:
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=1_000)

        reserved = reserve_trade_notional(portfolio, symbol="AAPL", instrument_id=1, notional_usd=350)

        self.assertEqual(reserved.available_cash_usd, 650)
        self.assertEqual(len(reserved.positions), 1)
        self.assertEqual(reserved.positions[0].symbol, "AAPL")
        self.assertEqual(reserved.positions[0].current_value_usd, 350)


def _snapshot(symbol: str, start: float, daily_returns: list[float]) -> MarketSnapshot:
    now = datetime.now(tz=UTC)
    candles: list[Candle] = []
    price = start
    for index, daily_return in enumerate(daily_returns):
        close = price * (1 + daily_return)
        candles.append(
            Candle(
                timestamp=now - timedelta(days=len(daily_returns) - index),
                open=price,
                high=max(price, close) * 1.01,
                low=min(price, close) * 0.99,
                close=close,
                volume=2_000_000 + index * 30_000,
            )
        )
        price = close
    instrument = Instrument(symbol=symbol, instrument_id=1, asset_type="Stock")
    rate = Rate(1, bid=price * 0.999, ask=price * 1.001, last_execution=price, timestamp=now)
    return MarketSnapshot(instrument, rate, candles)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import RiskSettings, StrategySettings, UniverseSettings
from agent.portfolio import PortfolioOverlayReport
from agent.regime import MarketRegime
from agent.risk import RiskEngine, set_kill_switch
from models import Candle, Instrument, MarketSnapshot, PortfolioPosition, PortfolioState, Rate, SignalDecision


class RiskEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.kill_path = str(Path(self.tmp.name) / "KILL_SWITCH")
        self.risk = RiskSettings(kill_switch_path=self.kill_path)
        self.engine = RiskEngine(self.risk, StrategySettings(), UniverseSettings(symbols=("AAPL",)))
        self.snapshot = MarketSnapshot(
            instrument=Instrument(symbol="AAPL", instrument_id=1, asset_type="Stock"),
            rate=Rate(1, bid=99.95, ask=100.05, last_execution=100.0, timestamp=datetime.now(tz=UTC)),
            candles=_candles(100, [0.003] * 60),
        )
        self.signal = SignalDecision("AAPL", "BUY", confidence=0.8, score=0.8)
        self.portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=9_000)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_approves_clean_buy(self) -> None:
        decision = self.engine.evaluate(self.signal, self.snapshot, self.portfolio)
        self.assertTrue(decision.approved)
        self.assertEqual(decision.target_notional_usd, 500)
        self.assertIn("adaptive_protection", decision.reason)
        self.assertIsNotNone(decision.stop_loss_rate)
        self.assertIsNotNone(decision.take_profit_rate)
        assert decision.stop_loss_rate is not None
        assert decision.take_profit_rate is not None
        self.assertLess(decision.stop_loss_rate, self.snapshot.rate.mid)
        self.assertGreater(decision.take_profit_rate, self.snapshot.rate.mid)

    def test_rejects_wide_spread(self) -> None:
        snapshot = MarketSnapshot(
            instrument=self.snapshot.instrument,
            rate=Rate(1, bid=90, ask=110, last_execution=100, timestamp=datetime.now(tz=UTC)),
            candles=[],
        )
        decision = self.engine.evaluate(self.signal, snapshot, self.portfolio)
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "spread_too_wide")

    def test_staleness_uses_cycle_reference_time(self) -> None:
        rate_time = datetime.now(tz=UTC) - timedelta(seconds=120)
        snapshot = MarketSnapshot(
            instrument=self.snapshot.instrument,
            rate=Rate(1, bid=99.95, ask=100.05, last_execution=100, timestamp=rate_time),
            candles=self.snapshot.candles,
        )

        without_reference = self.engine.evaluate(self.signal, snapshot, self.portfolio)
        with_reference = self.engine.evaluate(
            self.signal,
            snapshot,
            self.portfolio,
            cycle_started_at=rate_time + timedelta(seconds=10),
        )

        self.assertFalse(without_reference.approved)
        self.assertEqual(without_reference.reason, "stale_market_data")
        self.assertTrue(with_reference.approved)

    def test_rejects_max_positions(self) -> None:
        positions = (
            PortfolioPosition("MSFT", 2, "p1", 1, 500, 520),
            PortfolioPosition("NVDA", 3, "p2", 1, 500, 520),
        )
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=9_000, positions=positions)
        decision = self.engine.evaluate(self.signal, self.snapshot, portfolio)
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "max_positions_reached")

    def test_kill_switch_blocks(self) -> None:
        set_kill_switch(self.kill_path, True, "test halt")
        decision = self.engine.evaluate(self.signal, self.snapshot, self.portfolio)
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "kill_switch_active")

    def test_sector_exposure_overlay_blocks_crowded_entry(self) -> None:
        risk = RiskSettings(kill_switch_path=self.kill_path, max_sector_exposure_pct=0.09)
        universe = UniverseSettings(symbols=("AAPL", "MSFT"), sector_map={"AAPL": "tech", "MSFT": "tech"})
        engine = RiskEngine(risk, StrategySettings(), universe)
        positions = (PortfolioPosition("MSFT", 2, "p1", 1, 900, 950),)
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=9_000, positions=positions)

        decision = engine.evaluate(self.signal, self.snapshot, portfolio)

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "sector_exposure_limit")

    def test_risk_off_regime_blocks_new_buy(self) -> None:
        regime = MarketRegime(
            name="risk_off",
            confidence=0.8,
            stress_score=0.8,
            size_multiplier=0.45,
            summary="risk off",
            features={},
        )

        decision = self.engine.evaluate(
            self.signal,
            self.snapshot,
            self.portfolio,
            market_regime=regime,
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "regime_risk_off_buy_block")

    def test_portfolio_optimizer_overlay_can_adjust_order(self) -> None:
        risk = RiskSettings(
            kill_switch_path=self.kill_path,
            max_portfolio_hhi=0.14,
            max_projected_stress_loss_pct=0.04,
        )
        engine = RiskEngine(risk, StrategySettings(), UniverseSettings(symbols=("AAPL", "MSFT", "SPY")))
        positions = (PortfolioPosition("MSFT", 2, "p1", 1, 1_800, 1_900),)
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=9_000, positions=positions)
        snapshots = {
            "AAPL": self.snapshot,
            "MSFT": MarketSnapshot(
                instrument=Instrument(symbol="MSFT", instrument_id=2, asset_type="Stock"),
                rate=Rate(2, bid=99.95, ask=100.05, last_execution=100.0, timestamp=datetime.now(tz=UTC)),
                candles=_candles(100, [0.002, -0.001, 0.0015, -0.0005] * 15),
            ),
            "SPY": MarketSnapshot(
                instrument=Instrument(symbol="SPY", instrument_id=3, asset_type="ETF"),
                rate=Rate(3, bid=99.95, ask=100.05, last_execution=100.0, timestamp=datetime.now(tz=UTC)),
                candles=_candles(100, [0.002] * 60),
            ),
        }

        decision = engine.evaluate(
            self.signal,
            self.snapshot,
            portfolio,
            all_snapshots=snapshots,
        )

        self.assertTrue(decision.approved)
        self.assertLessEqual(decision.target_notional_usd, 500)

    def test_precomputed_overlay_target_flows_through_risk(self) -> None:
        overlay = PortfolioOverlayReport(
            approved=True,
            adjusted_notional_usd=275.0,
            reason="cycle_allocation_ok",
            hhi=0.12,
            diversification_score=0.88,
            var_95_pct=0.012,
            cvar_95_pct=0.018,
            expected_shortfall_95_pct=0.018,
            max_stress_loss_pct=0.031,
            scenario_losses={"risk_off": 0.031},
        )

        decision = self.engine.evaluate(
            self.signal,
            self.snapshot,
            self.portfolio,
            proposed_target_notional_usd=275.0,
            portfolio_overlay_report=overlay,
        )

        self.assertTrue(decision.approved)
        self.assertEqual(decision.target_notional_usd, 275.0)
        self.assertIn("overlay_hhi=0.120", decision.reason)

    def test_learned_edge_can_reduce_position_size(self) -> None:
        weak_signal = SignalDecision(
            "AAPL",
            "BUY",
            confidence=0.8,
            score=0.8,
            features={
                "meta_learned_edge": 0.18,
                "meta_expected_return": -0.01,
                "meta_approval_score": 0.42,
            },
        )

        decision = self.engine.evaluate(weak_signal, self.snapshot, self.portfolio)

        self.assertTrue(decision.approved)
        self.assertLess(decision.target_notional_usd, 500)


if __name__ == "__main__":
    unittest.main()


def _candles(start: float, daily_returns: list[float]) -> list[Candle]:
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
                volume=1_000_000 + index * 20_000,
            )
        )
        price = close
    return candles

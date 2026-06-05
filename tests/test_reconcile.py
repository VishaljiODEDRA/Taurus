from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.reconcile import analyze_reconciliation
from models import PortfolioPosition, PortfolioState


class ReconciliationTest(unittest.TestCase):
    def test_aligned_broker_and_ledger_reconciliation_is_ok(self) -> None:
        portfolio = PortfolioState(
            nav_usd=10_000,
            available_cash_usd=8_900,
            positions=(
                PortfolioPosition(
                    symbol="AAPL",
                    instrument_id=1,
                    position_id="p1",
                    units=10,
                    invested_usd=1_000,
                    current_value_usd=1_040,
                    pnl_usd=40,
                    open_rate=100,
                ),
            ),
        )
        report = analyze_reconciliation(
            portfolio=portfolio,
            local_orders=[
                {
                    "symbol": "AAPL",
                    "action": "BUY",
                    "accepted": 1,
                    "raw_json": "{}",
                }
            ],
            open_contexts=[
                {
                    "symbol": "AAPL",
                    "entry_notional_usd": 1_000,
                    "risk_details_json": {"stop_loss_rate": 95, "take_profit_rate": 110},
                }
            ],
        )

        self.assertEqual(report.status, "ok")
        self.assertEqual(report.alert_count, 0)

    def test_reconciliation_flags_duplicate_drift_stale_missing_and_pnl_mismatch(self) -> None:
        portfolio = PortfolioState(
            nav_usd=10_000,
            available_cash_usd=7_000,
            positions=(
                PortfolioPosition(
                    symbol="AAPL",
                    instrument_id=1,
                    position_id="p1",
                    units=10,
                    invested_usd=1_000,
                    current_value_usd=1_050,
                    pnl_usd=50,
                    open_rate=100,
                ),
                PortfolioPosition(
                    symbol="AAPL",
                    instrument_id=1,
                    position_id="p2",
                    units=5,
                    invested_usd=500,
                    current_value_usd=525,
                    pnl_usd=25,
                    open_rate=100,
                ),
                PortfolioPosition(
                    symbol="TSLA",
                    instrument_id=2,
                    position_id="p3",
                    units=2,
                    invested_usd=600,
                    current_value_usd=580,
                    pnl_usd=-20,
                    open_rate=300,
                ),
            ),
        )
        report = analyze_reconciliation(
            portfolio=portfolio,
            local_orders=[
                {"symbol": "MSFT", "action": "BUY", "accepted": 1, "raw_json": "{}"},
            ],
            open_contexts=[
                {
                    "symbol": "AAPL",
                    "entry_notional_usd": 1_000,
                    "risk_details_json": {},
                }
            ],
        )
        codes = {alert.code for alert in report.alerts}

        self.assertEqual(report.status, "alert")
        self.assertIn("duplicate_exposure", codes)
        self.assertIn("position_level_drift", codes)
        self.assertIn("stale_protection", codes)
        self.assertIn("missing_local_order", codes)
        self.assertIn("missing_broker_position", codes)
        self.assertIn("broker_ledger_pnl_mismatch", codes)


if __name__ == "__main__":
    unittest.main()

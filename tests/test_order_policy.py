from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import RiskSettings
from agent.order_policy import ImmutablePreTradePolicy
from models import Instrument, MarketSnapshot, OrderRequest, PortfolioState, Rate


class ImmutablePreTradePolicyTest(unittest.TestCase):
    def test_blocks_buy_without_protection(self) -> None:
        policy = ImmutablePreTradePolicy(RiskSettings())
        order = OrderRequest(
            symbol="AAPL",
            instrument_id=1,
            action="BUY",
            amount_usd=100,
            leverage=1,
        )

        result = policy.evaluate(order=order, snapshot=_snapshot(), portfolio=PortfolioState(10_000, 5_000))

        self.assertFalse(result.approved)
        self.assertEqual(result.reason, "policy_missing_protection")

    def test_approves_protected_buy_within_limits(self) -> None:
        policy = ImmutablePreTradePolicy(RiskSettings())
        order = OrderRequest(
            symbol="AAPL",
            instrument_id=1,
            action="BUY",
            amount_usd=100,
            leverage=1,
            stop_loss_rate=95,
            take_profit_rate=110,
        )

        result = policy.evaluate(order=order, snapshot=_snapshot(), portfolio=PortfolioState(10_000, 5_000))

        self.assertTrue(result.approved)


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        instrument=Instrument(symbol="AAPL", instrument_id=1),
        rate=Rate(
            instrument_id=1,
            bid=99.95,
            ask=100.05,
            last_execution=100,
            timestamp=datetime.now(tz=UTC),
        ),
    )


if __name__ == "__main__":
    unittest.main()

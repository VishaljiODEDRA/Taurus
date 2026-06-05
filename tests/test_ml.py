from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.ml import MetaLabeler, OutcomeMemoryBuilder


class OutcomeMemoryTest(unittest.TestCase):
    def test_builder_creates_symbol_and_global_stats(self) -> None:
        profile = OutcomeMemoryBuilder().build(
            [
                {"symbol": "AAPL", "return_pct": 0.03, "pnl_usd": 30, "holding_days": 4},
                {"symbol": "AAPL", "return_pct": -0.01, "pnl_usd": -10, "holding_days": 5},
                {"symbol": "MSFT", "return_pct": 0.02, "pnl_usd": 20, "holding_days": 3},
            ]
        )

        self.assertEqual(profile.sample_count, 3)
        self.assertEqual(profile.global_stats.sample_count, 3)
        self.assertEqual(profile.stats_for_symbol("AAPL").sample_count, 2)
        self.assertAlmostEqual(profile.stats_for_symbol("AAPL").average_return, 0.01)

    def test_meta_labeler_uses_outcomes_to_reduce_approval(self) -> None:
        profile = OutcomeMemoryBuilder().build(
            [
                {"symbol": "AAPL", "return_pct": -0.03, "pnl_usd": -30, "holding_days": 6},
                {"symbol": "AAPL", "return_pct": -0.02, "pnl_usd": -20, "holding_days": 5},
                {"symbol": "AAPL", "return_pct": -0.015, "pnl_usd": -15, "holding_days": 4},
                {"symbol": "AAPL", "return_pct": -0.025, "pnl_usd": -25, "holding_days": 5},
                {"symbol": "AAPL", "return_pct": -0.01, "pnl_usd": -10, "holding_days": 3},
                {"symbol": "AAPL", "return_pct": -0.018, "pnl_usd": -18, "holding_days": 4},
            ]
        )
        learned_edge, expected_return, source_sample_count = MetaLabeler()._learned_edge(
            symbol="AAPL",
            outcome_profile=profile,
            min_samples=6,
        )

        self.assertLess(learned_edge, 0.45)
        self.assertLess(expected_return, 0.0)
        self.assertEqual(source_sample_count, 6)


if __name__ == "__main__":
    unittest.main()

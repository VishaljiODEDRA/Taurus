from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.ledger import Ledger
from agent.reliability import ReliabilityAnalyzer, classify_trade_root_cause


class ReliabilityLayerTest(unittest.TestCase):
    def test_reliability_reports_use_outcome_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            for index in range(12):
                winner = index % 2 == 0
                ledger.record_cycle_features(
                    {
                        "cycle_id": f"cycle-{index}",
                        "symbol": "AAPL",
                        "benchmark_symbol": "SPY",
                        "action": "OUTCOME",
                        "is_trade": True,
                        "decision_score": 0.8 if winner else 0.4,
                        "decision_confidence": 0.8 if winner else 0.35,
                        "news_sentiment": 0.4 if winner else -0.4,
                        "news_catalyst": 0.6,
                        "regime_confidence": 0.7,
                        "execution_quality_score": 0.8,
                        "fill_probability": 0.8,
                        "outcome_label": 1 if winner else 0,
                        "outcome_return_pct": 0.02 if winner else -0.015,
                        "outcome_pnl_usd": 20 if winner else -15,
                        "raw_features": {
                            "meta_approval_score": 0.8 if winner else 0.35,
                            "execution_sim_fill_probability": 0.8,
                        },
                    }
                )

            analyzer = ReliabilityAnalyzer(ledger)
            ablation = analyzer.feature_ablation_report()
            calibration = analyzer.calibration_report()
            scorecard = analyzer.paper_scorecard()
            dataset = analyzer.labeled_dataset_report()
            governance = analyzer.governance_dashboard()

            self.assertEqual(ablation.status, "ok")
            self.assertEqual(calibration.status, "ok")
            self.assertIn(scorecard.status, {"pass", "not_ready"})
            self.assertIn(dataset.status, {"ok", "needs_more_clean_labels"})
            self.assertIn(governance.status, {"ok", "review"})

    def test_root_cause_classifies_losing_trade(self) -> None:
        cause = classify_trade_root_cause(
            {
                "entry_context": {
                    "features": {
                        "timing_confidence": 0.2,
                        "news_sentiment": 0.7,
                        "execution_sim_expected_slippage_bps": 35,
                    }
                },
                "exit_features": {"regime_stress_score": 0.8},
            },
            return_pct=-0.03,
        )

        self.assertIn(cause["primary_cause"], cause["causes"])
        self.assertGreaterEqual(cause["severity"], 0.0)


if __name__ == "__main__":
    unittest.main()

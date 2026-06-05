from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.config import (
    AgentSettings,
    AppConfig,
    ExecutionSettings,
    ExitSettings,
    MonitoringSettings,
    NewsSettings,
    RiskSettings,
    Secrets,
    StorageSettings,
    StrategySettings,
    UniverseSettings,
    ValidationSettings,
)
from agent.engine import TradingAgent, _committee_summary, _tradability_summary
from models import SignalDecision


class TradingAgentShadowTest(unittest.TestCase):
    def test_committee_summary_excludes_automatic_hold_approvals(self) -> None:
        hold = SignalDecision(
            "AAPL",
            "HOLD",
            confidence=1.0,
            score=0.0,
            reasons=("not currently tradable",),
            features={
                "committee_reason": "hold_decision_no_order_risk",
                "committee_consensus_score": 1.0,
            },
        )
        buy = SignalDecision(
            "MSFT",
            "BUY",
            confidence=0.8,
            score=0.7,
            features={"committee_consensus_score": 0.6},
        )

        summary = _committee_summary((hold, buy))

        self.assertEqual(summary["reviewed"], 1)
        self.assertEqual(summary["total_decisions"], 2)
        self.assertEqual(summary["automatic_hold_approvals"], 1)
        self.assertAlmostEqual(summary["average_consensus"], 0.6)

    def test_tradability_summary_classifies_blocked_cycle(self) -> None:
        decisions = (
            SignalDecision("AAPL", "HOLD", confidence=1.0, score=0.0, reasons=("not currently tradable",)),
            SignalDecision("MSFT", "HOLD", confidence=1.0, score=0.0, reasons=("exchange closed",)),
        )

        summary = _tradability_summary(decisions)

        self.assertEqual(summary["cycle_classification"], "market_closed_or_tradability_blocked")
        self.assertEqual(summary["blocked_count"], 2)
        self.assertEqual(summary["not_currently_tradable"], 1)
        self.assertEqual(summary["exchange_closed"], 1)

    def test_shadow_cycle_runs_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig(
                agent=AgentSettings(max_candidates_per_cycle=5),
                execution=ExecutionSettings(mode="shadow", environment="demo"),
                universe=UniverseSettings(symbols=("AAPL", "MSFT", "SPY"), benchmark_symbol="SPY"),
                risk=RiskSettings(kill_switch_path=str(Path(tmp) / "KILL_SWITCH")),
                exits=ExitSettings(),
                monitoring=MonitoringSettings(alert_log_path=str(Path(tmp) / "alerts.jsonl")),
                validation=ValidationSettings(),
                strategy=StrategySettings(buy_threshold=0.6),
                news=NewsSettings(enabled=False),
                storage=StorageSettings(
                    sqlite_path=str(Path(tmp) / "ledger.sqlite3"),
                    audit_log_path=str(Path(tmp) / "audit.jsonl"),
                ),
                secrets=Secrets(),
            )
            result = TradingAgent(config).run_once()

            self.assertFalse(result.halted)
            self.assertGreater(len(result.decisions), 0)
            self.assertTrue(Path(tmp, "ledger.sqlite3").exists())
            self.assertIn("regime_probabilities", result.dashboard)
            self.assertIn("execution_summary", result.dashboard)
            self.assertIn("learning_summary", result.dashboard)
            buy_decisions = [decision for decision in result.decisions if decision.action == "BUY"]
            if buy_decisions:
                self.assertTrue(
                    all("allocation_target_notional_usd" in decision.features for decision in buy_decisions)
                )
                self.assertTrue(
                    all("risk_execution_quality_score" in decision.features for decision in buy_decisions)
                )


if __name__ == "__main__":
    unittest.main()

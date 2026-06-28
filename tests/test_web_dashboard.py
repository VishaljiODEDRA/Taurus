from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

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
from agent.demo_data import create_demo_config_and_ledger
from agent.export_pack import build_audit_export_pack
from agent.ledger import Ledger
from agent.web.app import create_app_from_config
from agent.web.service import SAFETY_NOTICE
from models import OrderResult, SignalDecision


class WebDashboardTest(unittest.TestCase):
    def test_app_creation_and_key_routes_render_seeded_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config, ledger = _config_and_ledger(tmpdir)
            _seed_ledger(ledger)
            client = TestClient(create_app_from_config(config, ledger))

            for route in ("/", "/decisions", "/risk", "/models", "/reliability", "/reconciliation", "/audit"):
                response = client.get(route)
                self.assertEqual(response.status_code, 200, route)
                self.assertIn(SAFETY_NOTICE, response.text)

            overview = client.get("/")
            self.assertIn("Dashboard Overview", overview.text)
            self.assertIn("operational", overview.text)
            self.assertIn("AAPL", overview.text)

    def test_empty_ledger_routes_render_empty_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config, ledger = _config_and_ledger(tmpdir)
            client = TestClient(create_app_from_config(config, ledger))

            response = client.get("/models")

            self.assertEqual(response.status_code, 200)
            self.assertIn("No model training runs recorded yet.", response.text)
            self.assertIn(SAFETY_NOTICE, response.text)

    def test_dashboard_does_not_expose_private_paths_or_raw_payload_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config, ledger = _config_and_ledger(tmpdir)
            ledger.record_order(
                OrderResult(
                    accepted=True,
                    mode="shadow",
                    symbol="MSFT",
                    action="BUY",
                    broker_order_id="private-order-123456789",
                    message="shadow order recorded",
                    raw={"api_key": "SECRET_API_KEY", "account_id": "ACCOUNT-123"},
                )
            )
            ledger.record_broker_account_snapshot(
                environment="demo",
                nav_usd=10_000,
                available_cash_usd=9_500,
                daily_pnl_pct=0.0,
                rolling_drawdown_pct=0.0,
                gross_exposure_pct=0.05,
                open_positions=1,
                raw={"account_id": "ACCOUNT-123", "token": "SECRET_TOKEN"},
            )
            client = TestClient(create_app_from_config(config, ledger))

            html = client.get("/reconciliation").text + client.get("/audit").text

            self.assertNotIn(tmpdir, html)
            self.assertNotIn("SECRET_API_KEY", html)
            self.assertNotIn("SECRET_TOKEN", html)
            self.assertNotIn("ACCOUNT-123", html)
            self.assertIn("priv...6789", html)

    def test_demo_data_generator_creates_governance_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _config, ledger = create_demo_config_and_ledger(tmpdir)

            self.assertGreaterEqual(ledger.table_count("decisions"), 2)
            self.assertGreaterEqual(ledger.table_count("risk_checks"), 2)
            self.assertGreaterEqual(ledger.table_count("orders"), 1)
            self.assertGreaterEqual(ledger.table_count("cycle_health"), 2)
            self.assertGreaterEqual(ledger.table_count("model_registry"), 2)
            self.assertGreaterEqual(ledger.table_count("reliability_reports"), 2)
            self.assertGreaterEqual(ledger.table_count("reconciliations"), 1)

    def test_governance_cockpit_routes_render_with_demo_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config, ledger = create_demo_config_and_ledger(tmpdir)
            client = TestClient(create_app_from_config(config, ledger, demo_data=True))
            feature_id = ledger.latest_feature_snapshots(limit=1)[0]["id"]
            model_version = ledger.latest_model_versions(limit=1)[0]["model_version"]
            routes = (
                "/timeline",
                f"/decisions/{feature_id}",
                "/risk/controls",
                f"/models/{model_version}",
                "/incidents",
                "/governance/roles",
                "/replay",
                f"/replay/decision/{feature_id}",
            )

            for route in routes:
                response = client.get(route)
                self.assertEqual(response.status_code, 200, route)
                self.assertIn(SAFETY_NOTICE, response.text)

            self.assertIn("Demo data", client.get("/").text)
            self.assertIn("Risk Control Matrix", client.get("/risk/controls").text)
            self.assertIn("Governed Agent Roles", client.get("/governance/roles").text)
            self.assertIn("Replay This Decision", client.get(f"/replay/decision/{feature_id}").text)

    def test_audit_export_pack_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config, ledger = create_demo_config_and_ledger(Path(tmpdir) / "demo")
            ledger.record_order(
                OrderResult(
                    accepted=False,
                    mode="shadow",
                    symbol="NVDA",
                    action="BUY",
                    broker_order_id="private-order-987654321",
                    message="synthetic rejected order",
                    raw={"api_key": "SECRET_API_KEY", "account_id": "ACCOUNT-123"},
                )
            )
            output = Path(tmpdir) / "exports" / "audit-pack.zip"

            build_audit_export_pack(config, ledger, output)

            self.assertTrue(output.exists())
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertEqual(
                    {"summary.json", "report.html", "manifest.json", "checksums.sha256", "README.txt"},
                    names,
                )
                combined = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in sorted(names)
                )
            self.assertNotIn("SECRET_API_KEY", combined)
            self.assertNotIn("ACCOUNT-123", combined)
            self.assertNotIn(tmpdir, combined)
            self.assertIn("redaction", combined.lower())


def _config_and_ledger(tmpdir: str) -> tuple[AppConfig, Ledger]:
    sqlite_path = str(Path(tmpdir) / "agent_ledger.sqlite3")
    audit_log_path = str(Path(tmpdir) / "audit.jsonl")
    config = AppConfig(
        agent=AgentSettings(),
        execution=ExecutionSettings(mode="shadow", environment="demo"),
        universe=UniverseSettings(),
        risk=RiskSettings(kill_switch_path=str(Path(tmpdir) / "KILL_SWITCH")),
        exits=ExitSettings(),
        monitoring=MonitoringSettings(),
        validation=ValidationSettings(),
        strategy=StrategySettings(),
        news=NewsSettings(),
        storage=StorageSettings(sqlite_path=sqlite_path, audit_log_path=audit_log_path),
        secrets=Secrets(),
    )
    return config, Ledger(sqlite_path, audit_log_path)


def _seed_ledger(ledger: Ledger) -> None:
    ledger.record_cycle_health(
        halted=False,
        halt_reason="",
        decision_count=2,
        risk_check_count=2,
        order_count=1,
        rejected_order_count=1,
    )
    ledger.record_feature_snapshot(
        symbol="AAPL",
        action="BUY",
        score=0.82,
        confidence=0.74,
        cycle_id="cycle-1",
        features={
            "reasoning_summary": "Momentum and relative strength are constructive.",
            "risk_approved": True,
            "committee_approved": True,
        },
    )
    ledger.record_cycle_features(
        {
            "cycle_id": "cycle-1",
            "symbol": "AAPL",
            "benchmark_symbol": "SPY",
            "action": "BUY",
            "is_trade": True,
            "decision_score": 0.82,
            "decision_confidence": 0.74,
            "symbol_last_price": 190.0,
            "symbol_spread_bps": 5.0,
            "relative_strength_21d": 0.04,
            "news_sentiment": 0.2,
            "news_catalyst": 0.4,
            "regime_name": "bullish",
            "regime_confidence": 0.8,
            "allocation_approved": True,
            "allocation_target_notional_usd": 500.0,
            "execution_quality_score": 0.85,
            "expected_slippage_bps": 4.0,
            "fill_probability": 0.92,
            "committee_approved": True,
            "committee_consensus_score": 0.76,
            "risk_approved": True,
            "risk_target_notional_usd": 500.0,
            "raw_features": {"reasoning_summary": "test"},
        }
    )
    ledger.record_cycle_features(
        {
            "cycle_id": "cycle-1",
            "symbol": "TSLA",
            "benchmark_symbol": "SPY",
            "action": "BUY",
            "is_trade": True,
            "decision_score": 0.71,
            "decision_confidence": 0.6,
            "risk_approved": False,
            "risk_target_notional_usd": 0.0,
        }
    )
    ledger.record_order(
        OrderResult(
            accepted=True,
            mode="shadow",
            symbol="AAPL",
            action="BUY",
            broker_order_id="shadow-123456789",
            message="shadow order recorded",
            raw={"order": {"account_id": "hidden"}},
        )
    )
    ledger.record_position_review(
        SignalDecision(
            symbol="AAPL",
            action="HOLD",
            score=0.55,
            confidence=0.62,
            reasons=("Hold position while governance checks remain stable.",),
            features={"urgency_score": 0.2},
        )
    )
    ledger.record_portfolio_risk_report(
        var_pct=0.012,
        cvar_pct=0.021,
        expected_shortfall_pct=0.024,
        expected_shortfall_usd=240.0,
        factors={"hhi": 0.12, "diversification_score": 0.81},
        scenarios={"market_shock": {"loss_pct": -0.035}, "liquidity_stress": {"loss_pct": -0.018}},
    )
    ledger.record_model_training_run(
        model_name="supervised_meta_label_filter",
        sample_count=44,
        train_window="2026-01-01/2026-05-01",
        test_window="2026-05-01/2026-06-01",
        metrics={"status": "trained", "holdout_accuracy": 0.62},
        parameters={"model_version": "model-v1", "artifact_path": "/private/tmp/model-v1.json"},
    )
    ledger.register_model_version(
        model_name="supervised_meta_label_filter",
        model_version="model-v1",
        artifact_path="/private/tmp/model-v1.json",
        status="active",
        trained_until="2026-06-01",
        feature_names=["decision_score", "news_sentiment"],
        metrics={"holdout_accuracy": 0.62},
        parameters={},
    )
    ledger.promote_model_version(
        model_name="supervised_meta_label_filter",
        model_version="model-v1",
        reason="first governed model",
    )
    ledger.record_reliability_report(
        report_type="governance",
        status="ok",
        summary="No critical reliability drift detected.",
        raw={"feature_drift": "stable", "sample_count": 44},
    )
    ledger.record_reconciliation(
        status="ok",
        message="Broker and local expected state are aligned.",
        raw={"alerts": []},
    )
    ledger.record_broker_account_snapshot(
        environment="demo",
        nav_usd=10_000,
        available_cash_usd=9_500,
        daily_pnl_pct=0.001,
        rolling_drawdown_pct=0.002,
        gross_exposure_pct=0.05,
        open_positions=1,
        raw={"account_id": "hidden"},
    )
    ledger.record_committee_vote(
        symbol="AAPL",
        final_action="BUY",
        consensus_score=0.76,
        approved=True,
        votes={"trend": "yes", "risk": "yes"},
    )
    ledger.record_execution_simulation(
        simulation_id="sim-1",
        symbol="AAPL",
        action="BUY",
        quality_score=0.88,
        expected_slippage_bps=4.5,
        fill_probability=0.93,
        target_notional_usd=500,
    )


if __name__ == "__main__":
    unittest.main()

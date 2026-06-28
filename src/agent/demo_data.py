from __future__ import annotations

import tempfile
from pathlib import Path

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
from agent.ledger import Ledger
from models import OrderResult, RiskDecision, SignalDecision


def create_demo_config_and_ledger(base_dir: str | Path | None = None) -> tuple[AppConfig, Ledger]:
    root = Path(base_dir) if base_dir else Path(tempfile.mkdtemp(prefix="taurus-demo-dashboard-"))
    root.mkdir(parents=True, exist_ok=True)
    sqlite_path = root / "demo_dashboard.sqlite3"
    audit_log_path = root / "demo_audit.jsonl"
    config = AppConfig(
        agent=AgentSettings(name="taurus-demo-dashboard"),
        execution=ExecutionSettings(mode="shadow", environment="demo"),
        universe=UniverseSettings(symbols=("AAPL", "MSFT", "NVDA", "TSLA"), benchmark_symbol="SPY"),
        risk=RiskSettings(kill_switch_path=str(root / "KILL_SWITCH")),
        exits=ExitSettings(),
        monitoring=MonitoringSettings(alert_log_path=str(root / "alerts.jsonl")),
        validation=ValidationSettings(),
        strategy=StrategySettings(),
        news=NewsSettings(),
        storage=StorageSettings(sqlite_path=str(sqlite_path), audit_log_path=str(audit_log_path)),
        secrets=Secrets(),
    )
    ledger = Ledger(str(sqlite_path), str(audit_log_path))
    seed_demo_ledger(ledger)
    return config, ledger


def seed_demo_ledger(ledger: Ledger) -> None:
    ledger.record_cycle_health(
        halted=False,
        halt_reason="",
        decision_count=3,
        risk_check_count=3,
        order_count=1,
        rejected_order_count=1,
    )
    ledger.record_cycle_health(
        halted=True,
        halt_reason="synthetic_demo_kill_switch_review",
        decision_count=0,
        risk_check_count=0,
        order_count=0,
        rejected_order_count=0,
    )
    ledger.record_decision(
        SignalDecision(
            symbol="AAPL",
            action="BUY",
            confidence=0.78,
            score=0.84,
            reasons=(
                "Synthetic momentum and relative strength are constructive.",
                "Paper/demo governance approved the decision for review.",
            ),
            features={
                "reasoning_summary": "Synthetic AAPL decision passed committee and risk gates.",
                "news_summary": "Synthetic product catalyst with credible source mix.",
                "risk_approved": True,
                "committee_approved": True,
                "model_version": "demo-model-v1",
                "regime_name": "constructive",
                "timing_confidence": 0.71,
            },
        )
    )
    ledger.record_decision(
        SignalDecision(
            symbol="TSLA",
            action="BUY",
            confidence=0.62,
            score=0.73,
            reasons=("Synthetic spread and volatility risk blocked the decision.",),
            features={
                "reasoning_summary": "Synthetic TSLA proposal was blocked by deterministic controls.",
                "risk_approved": False,
                "committee_approved": False,
                "risk_reason": "expected_slippage_too_high",
                "model_version": "demo-model-v1",
            },
        )
    )
    ledger.record_risk(
        "AAPL",
        RiskDecision(
            approved=True,
            reason="approved",
            target_notional_usd=500,
            stop_loss_rate=185.0,
            take_profit_rate=205.0,
        ),
    )
    ledger.record_risk(
        "TSLA",
        RiskDecision.reject("expected_slippage_too_high"),
    )
    ledger.record_feature_snapshot(
        symbol="AAPL",
        action="BUY",
        score=0.84,
        confidence=0.78,
        cycle_id="demo-cycle-1",
        features={
            "reasoning_summary": "Synthetic AAPL decision passed committee and risk gates.",
            "news_summary": "Synthetic catalyst evidence was positive.",
            "market_summary": "Synthetic market structure was liquid enough for paper review.",
            "risk_approved": True,
            "committee_approved": True,
            "model_version": "demo-model-v1",
            "timing_reason": "Synthetic timing window is 2-5 trading days.",
        },
    )
    ledger.record_feature_snapshot(
        symbol="TSLA",
        action="BUY",
        score=0.73,
        confidence=0.62,
        cycle_id="demo-cycle-1",
        features={
            "reasoning_summary": "Synthetic decision blocked due to execution quality.",
            "risk_approved": False,
            "committee_approved": False,
            "risk_reason": "expected_slippage_too_high",
            "model_version": "demo-model-v1",
        },
    )
    for symbol, approved, score, target in (("AAPL", True, 0.84, 500.0), ("TSLA", False, 0.73, 0.0)):
        ledger.record_cycle_features(
            {
                "cycle_id": "demo-cycle-1",
                "symbol": symbol,
                "benchmark_symbol": "SPY",
                "action": "BUY",
                "is_trade": True,
                "decision_score": score,
                "decision_confidence": 0.78 if approved else 0.62,
                "symbol_last_price": 190.0 if symbol == "AAPL" else 230.0,
                "symbol_spread_bps": 4.5 if approved else 38.0,
                "symbol_return_21d_pct": 0.05,
                "benchmark_return_21d_pct": 0.02,
                "relative_strength_21d": 0.03,
                "news_sentiment": 0.22 if approved else -0.05,
                "news_catalyst": 0.44,
                "news_item_count": 4,
                "news_source_count": 3,
                "regime_name": "constructive",
                "regime_confidence": 0.76,
                "allocation_approved": approved,
                "allocation_target_notional_usd": target,
                "timing_confidence": 0.71 if approved else 0.34,
                "execution_quality_score": 0.86 if approved else 0.31,
                "expected_slippage_bps": 4.0 if approved else 31.0,
                "fill_probability": 0.93 if approved else 0.52,
                "committee_approved": approved,
                "committee_consensus_score": 0.79 if approved else 0.41,
                "risk_approved": approved,
                "risk_target_notional_usd": target,
                "raw_features": {"synthetic": True, "risk_reason": "" if approved else "expected_slippage_too_high"},
            }
        )
    ledger.record_order(
        OrderResult(
            accepted=True,
            mode="shadow",
            symbol="AAPL",
            action="BUY",
            broker_order_id="synthetic-shadow-order-0001",
            message="Synthetic shadow order recorded; no broker call.",
            raw={"synthetic": True, "redaction_note": "No real account payload."},
        )
    )
    ledger.record_portfolio_risk_report(
        var_pct=0.013,
        cvar_pct=0.024,
        var_99_pct=0.021,
        cvar_99_pct=0.034,
        expected_shortfall_pct=0.027,
        expected_shortfall_usd=270.0,
        factors={"hhi": 0.14, "diversification_score": 0.78, "gross_exposure_pct": 0.12},
        scenarios={
            "market_shock": {"loss_pct": -0.036, "status": "within_limit"},
            "liquidity_stress": {"loss_pct": -0.019, "status": "watch"},
        },
        raw={"synthetic": True},
    )
    ledger.record_model_training_run(
        model_name="supervised_meta_label_filter",
        sample_count=64,
        train_window="2026-01-01/2026-05-15",
        test_window="2026-05-16/2026-06-15",
        metrics={"status": "trained", "holdout_accuracy": 0.64, "walk_forward_windows": 3},
        parameters={"model_version": "demo-model-v1", "artifact_path": "synthetic/demo-model-v1.json"},
    )
    ledger.register_model_version(
        model_name="supervised_meta_label_filter",
        model_version="demo-model-v1",
        artifact_path="synthetic/demo-model-v1.json",
        status="active",
        trained_until="2026-06-15",
        feature_names=["decision_score", "news_sentiment", "execution_quality_score"],
        metrics={"holdout_accuracy": 0.64, "brier_score": 0.19},
        parameters={"synthetic": True},
    )
    ledger.promote_model_version(
        model_name="supervised_meta_label_filter",
        model_version="demo-model-v1",
        reason="Synthetic first active governed model.",
    )
    ledger.register_model_version(
        model_name="supervised_meta_label_filter",
        model_version="demo-model-v2",
        artifact_path="synthetic/demo-model-v2.json",
        status="candidate",
        trained_until="2026-06-20",
        feature_names=["decision_score", "news_sentiment"],
        metrics={"holdout_accuracy": 0.51, "brier_score": 0.31},
        parameters={"synthetic": True},
    )
    ledger.record_model_promotion_rejection(
        model_name="supervised_meta_label_filter",
        model_version="demo-model-v2",
        reason="candidate_did_not_clear_promotion_gate",
        raw={"synthetic": True},
    )
    ledger.record_reliability_report(
        report_type="governance",
        status="ok",
        summary="Synthetic governance report: controls are operating as expected.",
        raw={"synthetic": True, "feature_drift": "stable", "sample_count": 64},
    )
    ledger.record_reliability_report(
        report_type="calibration",
        status="review",
        summary="Synthetic calibration report: more labeled outcomes are needed.",
        raw={"synthetic": True, "expected_calibration_error": 0.18},
    )
    ledger.record_reconciliation(
        status="warning",
        message="Synthetic reconciliation warning: one local order has no matching demo broker fill yet.",
        raw={
            "synthetic": True,
            "alerts": [
                {
                    "level": "warning",
                    "code": "missing_broker_position",
                    "symbol": "AAPL",
                    "message": "Synthetic demo broker position not found for local shadow order.",
                }
            ],
        },
    )
    ledger.record_broker_account_snapshot(
        environment="demo",
        nav_usd=10_000,
        available_cash_usd=9_500,
        daily_pnl_pct=0.0,
        rolling_drawdown_pct=0.004,
        gross_exposure_pct=0.12,
        open_positions=1,
        raw={"synthetic": True},
    )
    ledger.record_committee_vote(
        symbol="AAPL",
        final_action="BUY",
        consensus_score=0.79,
        approved=True,
        votes={"trend": "approve", "risk": "approve", "news": "approve"},
    )
    ledger.record_execution_simulation(
        simulation_id="demo-sim-aapl-1",
        symbol="AAPL",
        action="BUY",
        quality_score=0.86,
        expected_slippage_bps=4.0,
        fill_probability=0.93,
        target_notional_usd=500,
        raw={"synthetic": True},
    )
    ledger.record_news_source_stat(
        source="Synthetic Market Brief",
        mentions=4,
        avg_sentiment=0.22,
        avg_catalyst=0.44,
        credibility_score=0.71,
        raw={"synthetic": True},
    )
    ledger.record_news_source_outcome(
        source="Synthetic Market Brief",
        symbol="AAPL",
        return_pct=0.012,
        sentiment_score=0.22,
        catalyst_score=0.44,
        item_age_hours=3,
        raw={"synthetic": True},
    )


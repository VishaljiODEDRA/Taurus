from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models import OrderResult, RiskDecision, SignalDecision


CYCLE_FEATURE_COLUMNS = (
    "created_at",
    "cycle_id",
    "symbol",
    "benchmark_symbol",
    "action",
    "is_trade",
    "decision_score",
    "decision_confidence",
    "symbol_last_price",
    "symbol_spread_bps",
    "symbol_return_1d_pct",
    "symbol_return_5d_pct",
    "symbol_return_21d_pct",
    "symbol_volatility_20d",
    "benchmark_last_price",
    "benchmark_return_1d_pct",
    "benchmark_return_5d_pct",
    "benchmark_return_21d_pct",
    "benchmark_volatility_20d",
    "relative_strength_21d",
    "news_sentiment",
    "news_catalyst",
    "news_item_count",
    "news_source_count",
    "regime_name",
    "regime_confidence",
    "regime_stress_score",
    "regime_size_multiplier",
    "regime_bullish_probability",
    "regime_weak_probability",
    "regime_volatile_probability",
    "regime_risk_off_probability",
    "regime_event_driven_probability",
    "allocation_approved",
    "allocation_target_notional_usd",
    "allocation_hhi",
    "allocation_diversification_score",
    "allocation_max_stress_loss_pct",
    "allocation_priority_score",
    "timing_confidence",
    "timing_earliest_days",
    "timing_likely_days",
    "timing_latest_days",
    "timing_invalidation_days",
    "execution_quality_score",
    "expected_slippage_bps",
    "fill_probability",
    "liquidity_score",
    "committee_approved",
    "committee_consensus_score",
    "risk_approved",
    "risk_target_notional_usd",
    "risk_stop_loss_pct",
    "risk_take_profit_pct",
    "outcome_label",
    "outcome_return_pct",
    "outcome_pnl_usd",
    "outcome_holding_days",
    "raw_features_json",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return str(value)


class Ledger:
    def __init__(self, sqlite_path: str, audit_log_path: str) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.audit_log_path = Path(audit_log_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    score REAL NOT NULL,
                    reasons_json TEXT NOT NULL,
                    features_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS risk_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    target_notional_usd REAL NOT NULL,
                    stop_loss_rate REAL,
                    take_profit_rate REAL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    broker_order_id TEXT,
                    message TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS loss_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT,
                    pnl_usd REAL NOT NULL,
                    note TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trade_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    entry_order_id TEXT,
                    exit_order_id TEXT,
                    entry_time TEXT,
                    exit_time TEXT,
                    pnl_usd REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    holding_days INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS broker_account_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    nav_usd REAL NOT NULL,
                    available_cash_usd REAL NOT NULL,
                    daily_pnl_pct REAL NOT NULL,
                    rolling_drawdown_pct REAL NOT NULL,
                    gross_exposure_pct REAL NOT NULL,
                    open_positions INTEGER NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reconciliations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_calibrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    suggested_buy_threshold REAL NOT NULL,
                    suggested_sell_threshold REAL NOT NULL,
                    metrics_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cycle_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    halted INTEGER NOT NULL,
                    halt_reason TEXT NOT NULL,
                    decision_count INTEGER NOT NULL,
                    risk_check_count INTEGER NOT NULL,
                    order_count INTEGER NOT NULL,
                    rejected_order_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS position_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    score REAL NOT NULL,
                    urgency_score REAL NOT NULL,
                    reasons_json TEXT NOT NULL,
                    features_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS open_trade_contexts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    broker_order_id TEXT,
                    entry_time TEXT,
                    entry_price REAL,
                    entry_notional_usd REAL NOT NULL,
                    features_json TEXT NOT NULL,
                    risk_details_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feature_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    feature_set TEXT NOT NULL,
                    features_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feature_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    feature_name TEXT NOT NULL,
                    numeric_value REAL,
                    text_value TEXT,
                    FOREIGN KEY(snapshot_id) REFERENCES feature_snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS cycle_feature_store (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    benchmark_symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    is_trade INTEGER NOT NULL,
                    decision_score REAL NOT NULL,
                    decision_confidence REAL NOT NULL,
                    symbol_last_price REAL NOT NULL,
                    symbol_spread_bps REAL NOT NULL,
                    symbol_return_1d_pct REAL NOT NULL,
                    symbol_return_5d_pct REAL NOT NULL,
                    symbol_return_21d_pct REAL NOT NULL,
                    symbol_volatility_20d REAL NOT NULL,
                    benchmark_last_price REAL NOT NULL,
                    benchmark_return_1d_pct REAL NOT NULL,
                    benchmark_return_5d_pct REAL NOT NULL,
                    benchmark_return_21d_pct REAL NOT NULL,
                    benchmark_volatility_20d REAL NOT NULL,
                    relative_strength_21d REAL NOT NULL,
                    news_sentiment REAL NOT NULL,
                    news_catalyst REAL NOT NULL,
                    news_item_count INTEGER NOT NULL,
                    news_source_count INTEGER NOT NULL,
                    regime_name TEXT NOT NULL,
                    regime_confidence REAL NOT NULL,
                    regime_stress_score REAL NOT NULL,
                    regime_size_multiplier REAL NOT NULL,
                    regime_bullish_probability REAL NOT NULL,
                    regime_weak_probability REAL NOT NULL,
                    regime_volatile_probability REAL NOT NULL,
                    regime_risk_off_probability REAL NOT NULL,
                    regime_event_driven_probability REAL NOT NULL,
                    allocation_approved INTEGER,
                    allocation_target_notional_usd REAL NOT NULL,
                    allocation_hhi REAL NOT NULL,
                    allocation_diversification_score REAL NOT NULL,
                    allocation_max_stress_loss_pct REAL NOT NULL,
                    allocation_priority_score REAL NOT NULL,
                    timing_confidence REAL NOT NULL,
                    timing_earliest_days REAL NOT NULL,
                    timing_likely_days REAL NOT NULL,
                    timing_latest_days REAL NOT NULL,
                    timing_invalidation_days REAL NOT NULL,
                    execution_quality_score REAL NOT NULL,
                    expected_slippage_bps REAL NOT NULL,
                    fill_probability REAL NOT NULL,
                    liquidity_score REAL NOT NULL,
                    committee_approved INTEGER,
                    committee_consensus_score REAL NOT NULL,
                    risk_approved INTEGER,
                    risk_target_notional_usd REAL NOT NULL,
                    risk_stop_loss_pct REAL NOT NULL,
                    risk_take_profit_pct REAL NOT NULL,
                    outcome_label INTEGER,
                    outcome_return_pct REAL,
                    outcome_pnl_usd REAL,
                    outcome_holding_days INTEGER,
                    raw_features_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cycle_feature_store_symbol_created
                ON cycle_feature_store(symbol, created_at);

                CREATE INDEX IF NOT EXISTS idx_cycle_feature_store_cycle
                ON cycle_feature_store(cycle_id);

                CREATE TABLE IF NOT EXISTS cycle_market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    instrument_id INTEGER NOT NULL,
                    asset_type TEXT NOT NULL,
                    exchange TEXT,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    mid REAL NOT NULL,
                    last_execution REAL NOT NULL,
                    spread_bps REAL NOT NULL,
                    rate_timestamp TEXT NOT NULL,
                    is_currently_tradable INTEGER NOT NULL,
                    is_exchange_open INTEGER NOT NULL,
                    is_buy_enabled INTEGER NOT NULL,
                    candle_count INTEGER NOT NULL,
                    return_1d_pct REAL NOT NULL,
                    return_5d_pct REAL NOT NULL,
                    return_21d_pct REAL NOT NULL,
                    volatility_20d REAL NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cycle_market_snapshots_cycle_symbol
                ON cycle_market_snapshots(cycle_id, symbol);

                CREATE TABLE IF NOT EXISTS cycle_candle_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    candle_timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cycle_candle_history_cycle_symbol
                ON cycle_candle_history(cycle_id, symbol, candle_timestamp);

                CREATE TABLE IF NOT EXISTS cycle_news_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    sentiment_score REAL NOT NULL,
                    catalyst_score REAL NOT NULL,
                    matched_symbols_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cycle_news_items_cycle_symbol
                ON cycle_news_items(cycle_id, symbol);

                CREATE TABLE IF NOT EXISTS cycle_portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL UNIQUE,
                    nav_usd REAL NOT NULL,
                    available_cash_usd REAL NOT NULL,
                    daily_pnl_pct REAL NOT NULL,
                    rolling_drawdown_pct REAL NOT NULL,
                    gross_exposure_pct REAL NOT NULL,
                    open_order_symbols_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cycle_portfolio_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    instrument_id INTEGER NOT NULL,
                    position_id TEXT NOT NULL,
                    units REAL NOT NULL,
                    invested_usd REAL NOT NULL,
                    current_value_usd REAL NOT NULL,
                    pnl_usd REAL NOT NULL,
                    pnl_pct REAL NOT NULL,
                    open_rate REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cycle_portfolio_positions_cycle
                ON cycle_portfolio_positions(cycle_id, symbol);

                CREATE TABLE IF NOT EXISTS cycle_regime_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cycle_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    stress_score REAL NOT NULL,
                    size_multiplier REAL NOT NULL,
                    summary TEXT NOT NULL,
                    probabilities_json TEXT NOT NULL,
                    features_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS training_examples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    label INTEGER NOT NULL,
                    return_pct REAL NOT NULL,
                    pnl_usd REAL NOT NULL,
                    holding_days INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    entry_features_json TEXT NOT NULL,
                    exit_features_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_training_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    model_version TEXT,
                    model_name TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    train_window TEXT NOT NULL,
                    test_window TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL UNIQUE,
                    artifact_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trained_until TEXT NOT NULL,
                    feature_names_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_promotion_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    previous_active_version TEXT,
                    promoted INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reliability_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trade_root_causes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    outcome_label INTEGER NOT NULL,
                    primary_cause TEXT NOT NULL,
                    severity REAL NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decision_veto_memory (
                    pattern_key TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    pattern_label TEXT NOT NULL,
                    loss_count INTEGER NOT NULL,
                    win_count INTEGER NOT NULL,
                    avg_return_pct REAL NOT NULL,
                    veto_score REAL NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS portfolio_risk_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    var_pct REAL NOT NULL,
                    cvar_pct REAL NOT NULL,
                    var_99_pct REAL DEFAULT 0 NOT NULL,
                    cvar_99_pct REAL DEFAULT 0 NOT NULL,
                    expected_shortfall_pct REAL DEFAULT 0 NOT NULL,
                    expected_shortfall_usd REAL DEFAULT 0 NOT NULL,
                    factor_json TEXT NOT NULL,
                    scenarios_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS committee_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    final_action TEXT NOT NULL,
                    consensus_score REAL NOT NULL,
                    approved INTEGER NOT NULL,
                    votes_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    simulation_id TEXT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    expected_slippage_bps REAL NOT NULL,
                    fill_probability REAL NOT NULL,
                    target_notional_usd REAL DEFAULT 0 NOT NULL,
                    actual_slippage_bps REAL,
                    actual_fill_price REAL,
                    actual_mode TEXT,
                    filled INTEGER,
                    prediction_error_bps REAL,
                    fill_error REAL,
                    learned_adjustment_bps REAL DEFAULT 0 NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_source_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    mentions INTEGER NOT NULL,
                    avg_sentiment REAL NOT NULL,
                    avg_catalyst REAL NOT NULL,
                    credibility_score REAL NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_source_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    return_pct REAL NOT NULL,
                    abs_return_pct REAL NOT NULL,
                    sentiment_score REAL NOT NULL,
                    catalyst_score REAL NOT NULL,
                    item_age_hours REAL NOT NULL,
                    direction_correct INTEGER NOT NULL,
                    catalyst_moved_price INTEGER NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_source_credibility (
                    source TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    hit_rate REAL NOT NULL,
                    catalyst_move_rate REAL NOT NULL,
                    avg_return_pct REAL NOT NULL,
                    avg_abs_return_pct REAL NOT NULL,
                    avg_item_age_hours REAL NOT NULL,
                    reliability_score REAL NOT NULL,
                    speed_score REAL NOT NULL,
                    noise_score REAL NOT NULL,
                    credibility_multiplier REAL NOT NULL,
                    raw_json TEXT NOT NULL
                );
                """
            )

    def record_decision(self, decision: SignalDecision) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions (
                    created_at, symbol, action, confidence, score, reasons_json, features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    decision.symbol,
                    decision.action,
                    decision.confidence,
                    decision.score,
                    json.dumps(decision.reasons, default=_json_default),
                    json.dumps(decision.features, default=_json_default),
                ),
            )
        self.audit("decision", decision)

    def latest_decisions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        output = [dict(row) for row in rows]
        for row in output:
            row["reasons_json"] = _loads(row.get("reasons_json"), [])
            row["features_json"] = _loads(row.get("features_json"), {})
        return output

    def decision_by_id(self, decision_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["reasons_json"] = _loads(record.get("reasons_json"), [])
        record["features_json"] = _loads(record.get("features_json"), {})
        return record

    def record_position_review(self, review: SignalDecision) -> None:
        now = _now_iso()
        urgency_score = float(review.features.get("urgency_score", review.score))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO position_reviews (
                    created_at, symbol, action, confidence, score, urgency_score, reasons_json, features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    review.symbol,
                    review.action,
                    review.confidence,
                    review.score,
                    urgency_score,
                    json.dumps(review.reasons, default=_json_default),
                    json.dumps(review.features, default=_json_default),
                ),
            )
        self.audit("position_review", review)

    def record_risk(self, symbol: str, decision: RiskDecision) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO risk_checks (
                    created_at, symbol, approved, reason, target_notional_usd,
                    stop_loss_rate, take_profit_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    symbol,
                    int(decision.approved),
                    decision.reason,
                    decision.target_notional_usd,
                    decision.stop_loss_rate,
                    decision.take_profit_rate,
                ),
            )
        self.audit("risk", {"symbol": symbol, "decision": decision})

    def latest_risk_checks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM risk_checks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_risk_checks_for_symbol(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM risk_checks
                WHERE symbol = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (symbol.upper(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_order(self, order: OrderResult) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    created_at, symbol, action, accepted, mode, broker_order_id, message, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    order.symbol,
                    order.action,
                    int(order.accepted),
                    order.mode,
                    order.broker_order_id,
                    order.message,
                    json.dumps(order.raw, default=_json_default),
                ),
            )
        self.audit("order", order)

    def record_loss_event(self, symbol: str | None, pnl_usd: float, note: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO loss_events (created_at, symbol, pnl_usd, note)
                VALUES (?, ?, ?, ?)
                """,
                (_now_iso(), symbol, pnl_usd, note),
            )

    def record_trade_outcome(
        self,
        *,
        symbol: str,
        pnl_usd: float,
        return_pct: float,
        holding_days: int,
        source: str,
        entry_order_id: str | None = None,
        exit_order_id: str | None = None,
        entry_time: str | None = None,
        exit_time: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        raw_payload = raw or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_outcomes (
                    created_at, symbol, entry_order_id, exit_order_id, entry_time, exit_time,
                    pnl_usd, return_pct, holding_days, source, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    symbol.upper(),
                    entry_order_id,
                    exit_order_id,
                    entry_time,
                    exit_time,
                    pnl_usd,
                    return_pct,
                    holding_days,
                    source,
                    json.dumps(raw_payload, default=_json_default),
                ),
            )
        entry_features = _extract_nested_features(raw_payload, "entry_context")
        exit_features = raw_payload.get("exit_features", {})
        if isinstance(entry_features, dict) or isinstance(exit_features, dict):
            if isinstance(entry_features, dict):
                self._record_news_source_outcomes_from_trade(
                    symbol=symbol,
                    return_pct=return_pct,
                    entry_features=entry_features,
                    raw=raw_payload,
                )
            self.record_training_example(
                symbol=symbol,
                label=1 if return_pct > 0 else 0,
                return_pct=return_pct,
                pnl_usd=pnl_usd,
                holding_days=holding_days,
                source=source,
                entry_features=entry_features if isinstance(entry_features, dict) else {},
                exit_features=exit_features if isinstance(exit_features, dict) else {},
                raw=raw_payload,
            )
            feature_payload = entry_features if isinstance(entry_features, dict) else {}
            self.record_cycle_features(
                {
                    "cycle_id": exit_time or _now_iso(),
                    "symbol": symbol,
                    "benchmark_symbol": str(feature_payload.get("benchmark_symbol", "")),
                    "action": "OUTCOME",
                    "is_trade": True,
                    "decision_score": feature_payload.get("score", feature_payload.get("decision_score", 0.0)),
                    "decision_confidence": feature_payload.get("confidence", feature_payload.get("decision_confidence", 0.0)),
                    "news_sentiment": feature_payload.get("news_sentiment", 0.0),
                    "news_catalyst": feature_payload.get("news_catalyst", 0.0),
                    "regime_name": feature_payload.get("regime_name", ""),
                    "regime_confidence": feature_payload.get("regime_confidence", 0.0),
                    "regime_stress_score": feature_payload.get("regime_stress_score", 0.0),
                    "allocation_target_notional_usd": feature_payload.get("allocation_target_notional_usd", 0.0),
                    "execution_quality_score": feature_payload.get("execution_sim_quality_score", feature_payload.get("risk_execution_quality_score", 0.0)),
                    "expected_slippage_bps": feature_payload.get("execution_sim_expected_slippage_bps", feature_payload.get("risk_expected_slippage_bps", 0.0)),
                    "committee_consensus_score": feature_payload.get("committee_consensus_score", 0.0),
                    "risk_approved": True,
                    "outcome_label": 1 if return_pct > 0 else 0,
                    "outcome_return_pct": return_pct,
                    "outcome_pnl_usd": pnl_usd,
                    "outcome_holding_days": holding_days,
                    "raw_features": feature_payload,
                }
            )

    def trade_outcome_exists(
        self,
        *,
        source: str,
        entry_order_id: str | None = None,
        exit_order_id: str | None = None,
    ) -> bool:
        clauses = ["source = ?"]
        params: list[Any] = [source]
        if entry_order_id:
            clauses.append("entry_order_id = ?")
            params.append(entry_order_id)
        if exit_order_id:
            clauses.append("exit_order_id = ?")
            params.append(exit_order_id)
        if len(clauses) == 1:
            return False
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT 1 FROM trade_outcomes WHERE {' AND '.join(clauses)} LIMIT 1",
                tuple(params),
            ).fetchone()
        return row is not None

    def record_broker_account_snapshot(
        self,
        *,
        environment: str,
        nav_usd: float,
        available_cash_usd: float,
        daily_pnl_pct: float,
        rolling_drawdown_pct: float,
        gross_exposure_pct: float,
        open_positions: int,
        raw: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO broker_account_snapshots (
                    created_at, environment, nav_usd, available_cash_usd, daily_pnl_pct,
                    rolling_drawdown_pct, gross_exposure_pct, open_positions, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    environment,
                    nav_usd,
                    available_cash_usd,
                    daily_pnl_pct,
                    rolling_drawdown_pct,
                    gross_exposure_pct,
                    open_positions,
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def latest_broker_account_snapshot(self, environment: str | None = None) -> dict[str, Any] | None:
        where = ""
        params: list[Any] = []
        if environment:
            where = "WHERE environment = ?"
            params.append(environment)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT * FROM broker_account_snapshots
                {where}
                ORDER BY id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["raw_json"] = _loads(record.get("raw_json"), {})
        return record

    def record_open_trade_context(
        self,
        *,
        symbol: str,
        broker_order_id: str | None,
        entry_time: str | None,
        entry_price: float | None,
        entry_notional_usd: float,
        features: dict[str, Any],
        risk_details: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO open_trade_contexts (
                    created_at, symbol, broker_order_id, entry_time, entry_price,
                    entry_notional_usd, features_json, risk_details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    symbol.upper(),
                    broker_order_id,
                    entry_time,
                    entry_price,
                    entry_notional_usd,
                    json.dumps(features, default=_json_default),
                    json.dumps(risk_details, default=_json_default),
                ),
            )

    def consume_open_trade_context(self, symbol: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM open_trade_contexts
                WHERE symbol = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM open_trade_contexts WHERE id = ?", (row["id"],))
        record = dict(row)
        for key in ("features_json", "risk_details_json"):
            try:
                record[key] = json.loads(record[key])
            except (TypeError, json.JSONDecodeError):
                record[key] = {}
        return record

    def open_trade_contexts(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM open_trade_contexts
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            for key in ("features_json", "risk_details_json"):
                record[key] = _loads(record.get(key), {})
        return records

    def trade_outcomes(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trade_outcomes ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def trade_outcomes_as_of(self, as_of_iso: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM trade_outcomes
                WHERE created_at <= ?
                  AND (exit_time IS NULL OR exit_time <= ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (as_of_iso, as_of_iso, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_reconciliation(self, status: str, message: str, raw: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliations (created_at, status, message, raw_json)
                VALUES (?, ?, ?, ?)
                """,
                (_now_iso(), status, message, json.dumps(raw or {}, default=_json_default)),
            )
        self.audit("reconciliation", {"status": status, "message": message, "raw": raw or {}})

    def latest_reconciliations(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM reconciliations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        output = [dict(row) for row in rows]
        for row in output:
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return output

    def record_calibration(
        self,
        *,
        source: str,
        sample_count: int,
        suggested_buy_threshold: float,
        suggested_sell_threshold: float,
        metrics: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_calibrations (
                    created_at, source, sample_count, suggested_buy_threshold,
                    suggested_sell_threshold, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    source,
                    sample_count,
                    suggested_buy_threshold,
                    suggested_sell_threshold,
                    json.dumps(metrics, default=_json_default),
                ),
            )

    def record_cycle_health(
        self,
        *,
        halted: bool,
        halt_reason: str,
        decision_count: int,
        risk_check_count: int,
        order_count: int,
        rejected_order_count: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cycle_health (
                    created_at, halted, halt_reason, decision_count, risk_check_count,
                    order_count, rejected_order_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    int(halted),
                    halt_reason,
                    decision_count,
                    risk_check_count,
                    order_count,
                    rejected_order_count,
                ),
            )

    def recent_cycle_health(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM cycle_health ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_loss_event_count(self, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM loss_events WHERE created_at >= ?",
                (since_iso,),
            ).fetchone()
        return int(row[0]) if row else 0

    def recent_orders_for_symbol(self, symbol: str, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE symbol = ? AND created_at >= ?",
                (symbol.upper(), since_iso),
            ).fetchone()
        return int(row[0]) if row else 0

    def latest_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_orders_for_symbol(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM orders
                WHERE symbol = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (symbol.upper(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_position_reviews(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM position_reviews ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_feature_snapshot(
        self,
        *,
        symbol: str,
        action: str,
        score: float,
        confidence: float,
        features: dict[str, Any],
        cycle_id: str | None = None,
        feature_set: str = "decision",
    ) -> int:
        created_at = _now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feature_snapshots (
                    created_at, cycle_id, symbol, action, score, confidence, feature_set, features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    cycle_id,
                    symbol.upper(),
                    action,
                    score,
                    confidence,
                    feature_set,
                    json.dumps(features, default=_json_default),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            rows = []
            for name, value in features.items():
                numeric_value: float | None = None
                text_value: str | None = None
                if isinstance(value, bool):
                    numeric_value = 1.0 if value else 0.0
                elif isinstance(value, (int, float)):
                    numeric_value = float(value)
                elif isinstance(value, str):
                    text_value = value[:500]
                else:
                    text_value = json.dumps(value, default=_json_default)[:500]
                rows.append((snapshot_id, str(name), numeric_value, text_value))
            conn.executemany(
                """
                INSERT INTO feature_values (snapshot_id, feature_name, numeric_value, text_value)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
        return snapshot_id

    def record_cycle_features(self, row: dict[str, Any]) -> int:
        payload: dict[str, Any] = {}
        for column in CYCLE_FEATURE_COLUMNS:
            payload[column] = _cycle_feature_value(column, row.get(column))
        payload["created_at"] = str(payload["created_at"] or _now_iso())
        payload["cycle_id"] = str(payload["cycle_id"] or payload["created_at"])
        payload["symbol"] = str(payload["symbol"] or "").upper()
        payload["benchmark_symbol"] = str(payload["benchmark_symbol"] or "").upper()
        payload["action"] = str(payload["action"] or "HOLD")
        payload["raw_features_json"] = json.dumps(
            row.get("raw_features_json", row.get("raw_features", {})),
            default=_json_default,
        )
        placeholders = ", ".join("?" for _ in CYCLE_FEATURE_COLUMNS)
        columns = ", ".join(CYCLE_FEATURE_COLUMNS)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO cycle_feature_store ({columns}) VALUES ({placeholders})",
                tuple(payload[column] for column in CYCLE_FEATURE_COLUMNS),
            )
        return int(cursor.lastrowid)

    def record_cycle_data_history(
        self,
        *,
        cycle_id: str,
        snapshots: dict[str, Any],
        contexts: dict[str, Any],
        portfolio: Any,
        market_regime: Any,
        candle_tail: int = 30,
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            for symbol, snapshot in snapshots.items():
                symbol_upper = str(symbol).upper()
                rate = snapshot.rate
                instrument = snapshot.instrument
                conn.execute(
                    """
                    INSERT INTO cycle_market_snapshots (
                        created_at, cycle_id, symbol, instrument_id, asset_type, exchange,
                        bid, ask, mid, last_execution, spread_bps, rate_timestamp,
                        is_currently_tradable, is_exchange_open, is_buy_enabled, candle_count,
                        return_1d_pct, return_5d_pct, return_21d_pct, volatility_20d, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        cycle_id,
                        symbol_upper,
                        int(instrument.instrument_id),
                        str(instrument.asset_type),
                        instrument.exchange,
                        float(rate.bid),
                        float(rate.ask),
                        float(rate.mid),
                        float(rate.last_execution),
                        float(rate.spread_bps),
                        rate.timestamp.isoformat(),
                        int(bool(instrument.is_currently_tradable)),
                        int(bool(instrument.is_exchange_open)),
                        int(bool(instrument.is_buy_enabled)),
                        len(snapshot.candles),
                        _history_return(snapshot.candles, 1),
                        _history_return(snapshot.candles, 5),
                        _history_return(snapshot.candles, 21),
                        _history_volatility(snapshot.candles, 20),
                        json.dumps({"instrument_raw": instrument.raw, "rate_raw": rate.raw}, default=_json_default),
                    ),
                )
                for candle in snapshot.candles[-candle_tail:]:
                    conn.execute(
                        """
                        INSERT INTO cycle_candle_history (
                            created_at, cycle_id, symbol, candle_timestamp, open, high, low, close, volume
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            now,
                            cycle_id,
                            symbol_upper,
                            candle.timestamp.isoformat(),
                            candle.open,
                            candle.high,
                            candle.low,
                            candle.close,
                            candle.volume,
                        ),
                    )

            for symbol, context in contexts.items():
                symbol_upper = str(symbol).upper()
                for item in getattr(context, "items", ()):
                    conn.execute(
                        """
                        INSERT INTO cycle_news_items (
                            created_at, cycle_id, symbol, source, title, url, published_at,
                            sentiment_score, catalyst_score, matched_symbols_json, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            now,
                            cycle_id,
                            symbol_upper,
                            item.source or "",
                            item.title,
                            item.url,
                            item.published_at.isoformat() if item.published_at else None,
                            float(getattr(context, "sentiment_score", 0.0)),
                            float(getattr(context, "catalyst_score", 0.0)),
                            json.dumps(item.symbols, default=_json_default),
                            json.dumps(asdict(item), default=_json_default),
                        ),
                    )

            conn.execute(
                """
                INSERT OR REPLACE INTO cycle_portfolio_snapshots (
                    created_at, cycle_id, nav_usd, available_cash_usd, daily_pnl_pct,
                    rolling_drawdown_pct, gross_exposure_pct, open_order_symbols_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    cycle_id,
                    float(portfolio.nav_usd),
                    float(portfolio.available_cash_usd),
                    float(portfolio.daily_pnl_pct),
                    float(portfolio.rolling_drawdown_pct),
                    float(portfolio.gross_exposure_pct),
                    json.dumps(portfolio.open_order_symbols, default=_json_default),
                ),
            )
            for position in portfolio.positions:
                conn.execute(
                    """
                    INSERT INTO cycle_portfolio_positions (
                        created_at, cycle_id, symbol, instrument_id, position_id, units,
                        invested_usd, current_value_usd, pnl_usd, pnl_pct, open_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        cycle_id,
                        position.symbol.upper(),
                        int(position.instrument_id),
                        position.position_id,
                        float(position.units),
                        float(position.invested_usd),
                        float(position.current_value_usd),
                        float(position.pnl_usd),
                        float(position.pnl_pct),
                        float(position.open_rate),
                    ),
                )

            conn.execute(
                """
                INSERT OR REPLACE INTO cycle_regime_history (
                    created_at, cycle_id, name, confidence, stress_score, size_multiplier,
                    summary, probabilities_json, features_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    cycle_id,
                    str(getattr(market_regime, "name", "")),
                    float(getattr(market_regime, "confidence", 0.0)),
                    float(getattr(market_regime, "stress_score", 0.0)),
                    float(getattr(market_regime, "size_multiplier", 1.0)),
                    str(getattr(market_regime, "summary", "")),
                    json.dumps(getattr(market_regime, "probabilities", {}), default=_json_default),
                    json.dumps(getattr(market_regime, "features", {}), default=_json_default),
                ),
            )

    def latest_cycle_data_history(self, *, cycle_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if cycle_id is None:
                row = conn.execute(
                    "SELECT cycle_id FROM cycle_market_snapshots ORDER BY id DESC LIMIT 1"
                ).fetchone()
                cycle_id = row["cycle_id"] if row else ""
            market = conn.execute(
                "SELECT * FROM cycle_market_snapshots WHERE cycle_id = ? ORDER BY symbol LIMIT ?",
                (cycle_id, limit),
            ).fetchall()
            news = conn.execute(
                "SELECT * FROM cycle_news_items WHERE cycle_id = ? ORDER BY id DESC LIMIT ?",
                (cycle_id, limit),
            ).fetchall()
            portfolio = conn.execute(
                "SELECT * FROM cycle_portfolio_snapshots WHERE cycle_id = ?",
                (cycle_id,),
            ).fetchone()
            positions = conn.execute(
                "SELECT * FROM cycle_portfolio_positions WHERE cycle_id = ? ORDER BY symbol",
                (cycle_id,),
            ).fetchall()
            regime = conn.execute(
                "SELECT * FROM cycle_regime_history WHERE cycle_id = ?",
                (cycle_id,),
            ).fetchone()
        return {
            "cycle_id": cycle_id,
            "market_snapshots": [_decode_json_fields(dict(row), ("raw_json",)) for row in market],
            "news_items": [_decode_json_fields(dict(row), ("matched_symbols_json", "raw_json")) for row in news],
            "portfolio": _decode_json_fields(dict(portfolio), ("open_order_symbols_json",)) if portfolio else {},
            "positions": [dict(row) for row in positions],
            "regime": _decode_json_fields(dict(regime), ("probabilities_json", "features_json")) if regime else {},
        }

    def latest_cycle_features(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._latest_rows("cycle_feature_store", limit)
        for row in rows:
            row["raw_features_json"] = _loads(row.get("raw_features_json"), {})
        return rows

    def cycle_feature_training_rows(self, limit: int = 5000, *, as_of: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE outcome_label IS NOT NULL"
        params: list[Any] = []
        if as_of:
            where += " AND created_at <= ?"
            params.append(as_of)
        params.append(limit)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM cycle_feature_store
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            record["raw_features_json"] = _loads(record.get("raw_features_json"), {})
        return list(reversed(records))

    def cycle_features_as_of(
        self,
        as_of_iso: str,
        *,
        symbol: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        where = "created_at <= ?"
        params: list[Any] = [as_of_iso]
        if symbol:
            where += " AND symbol = ?"
            params.append(symbol.upper())
        params.append(limit)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM cycle_feature_store
                WHERE {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            record["raw_features_json"] = _loads(record.get("raw_features_json"), {})
        return records

    def replay_state_as_of(self, as_of_iso: str, *, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        symbol_filter = " AND symbol = ?" if symbol else ""
        params: list[Any] = [as_of_iso]
        if symbol:
            params.append(symbol.upper())
        params_with_limit = tuple(params + [limit])
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            decisions = conn.execute(
                f"""
                SELECT * FROM decisions
                WHERE created_at <= ?{symbol_filter}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params_with_limit,
            ).fetchall()
            risk_checks = conn.execute(
                f"""
                SELECT * FROM risk_checks
                WHERE created_at <= ?{symbol_filter}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params_with_limit,
            ).fetchall()
            orders = conn.execute(
                f"""
                SELECT * FROM orders
                WHERE created_at <= ?{symbol_filter}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params_with_limit,
            ).fetchall()
            news = conn.execute(
                """
                SELECT * FROM news_source_stats
                WHERE created_at <= ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (as_of_iso, limit),
            ).fetchall()
            portfolio_risk = conn.execute(
                """
                SELECT * FROM portfolio_risk_reports
                WHERE created_at <= ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (as_of_iso, limit),
            ).fetchall()
        return {
            "as_of": as_of_iso,
            "symbol": symbol.upper() if symbol else None,
            "cycle_features": self.cycle_features_as_of(as_of_iso, symbol=symbol, limit=limit),
            "decisions": [_decode_json_fields(dict(row), ("reasons_json", "features_json")) for row in decisions],
            "risk_checks": [dict(row) for row in risk_checks],
            "orders": [_decode_json_fields(dict(row), ("raw_json",)) for row in orders],
            "news_source_stats": [_decode_json_fields(dict(row), ("raw_json",)) for row in news],
            "portfolio_risk_reports": [
                _decode_json_fields(dict(row), ("factor_json", "scenarios_json", "raw_json"))
                for row in portfolio_risk
            ],
        }

    def record_training_example(
        self,
        *,
        symbol: str,
        label: int,
        return_pct: float,
        pnl_usd: float,
        holding_days: int,
        source: str,
        entry_features: dict[str, Any],
        exit_features: dict[str, Any],
        raw: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO training_examples (
                    created_at, symbol, label, return_pct, pnl_usd, holding_days, source,
                    entry_features_json, exit_features_json, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    symbol.upper(),
                    int(label),
                    return_pct,
                    pnl_usd,
                    holding_days,
                    source,
                    json.dumps(entry_features, default=_json_default),
                    json.dumps(exit_features, default=_json_default),
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def training_examples(self, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self._latest_rows("training_examples", limit)
        for row in rows:
            for key in ("entry_features_json", "exit_features_json", "raw_json"):
                row[key] = _loads(row.get(key), {})
        return list(reversed(rows))

    def record_model_training_run(
        self,
        *,
        model_name: str,
        sample_count: int,
        train_window: str,
        test_window: str,
        metrics: dict[str, Any],
        parameters: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            _ensure_column(conn, "model_training_runs", "model_version", "TEXT")
            conn.execute(
                """
                INSERT INTO model_training_runs (
                    created_at, model_version, model_name, sample_count, train_window, test_window,
                    metrics_json, parameters_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    parameters.get("model_version"),
                    model_name,
                    sample_count,
                    train_window,
                    test_window,
                    json.dumps(metrics, default=_json_default),
                    json.dumps(parameters, default=_json_default),
                ),
            )

    def latest_model_training_runs(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._latest_rows("model_training_runs", limit)
        for row in rows:
            row["metrics_json"] = _loads(row.get("metrics_json"), {})
            row["parameters_json"] = _loads(row.get("parameters_json"), {})
        return rows

    def register_model_version(
        self,
        *,
        model_name: str,
        model_version: str,
        artifact_path: str,
        status: str,
        trained_until: str,
        feature_names: list[str],
        metrics: dict[str, Any],
        parameters: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO model_registry (
                    created_at, model_name, model_version, artifact_path, status,
                    trained_until, feature_names_json, metrics_json, parameters_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    model_name,
                    model_version,
                    artifact_path,
                    status,
                    trained_until,
                    json.dumps(feature_names, default=_json_default),
                    json.dumps(metrics, default=_json_default),
                    json.dumps(parameters, default=_json_default),
                ),
            )

    def active_model_version(self, model_name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM model_registry
                WHERE model_name = ? AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (model_name,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["feature_names_json"] = _loads(record.get("feature_names_json"), [])
        record["metrics_json"] = _loads(record.get("metrics_json"), {})
        record["parameters_json"] = _loads(record.get("parameters_json"), {})
        return record

    def update_model_status(self, model_version: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE model_registry SET status = ? WHERE model_version = ?",
                (status, model_version),
            )

    def promote_model_version(
        self,
        *,
        model_name: str,
        model_version: str,
        reason: str,
        raw: dict[str, Any] | None = None,
    ) -> None:
        previous = self.active_model_version(model_name)
        previous_version = str(previous["model_version"]) if previous else None
        with self._connect() as conn:
            conn.execute(
                "UPDATE model_registry SET status = 'previous' WHERE model_name = ? AND status = 'active'",
                (model_name,),
            )
            conn.execute(
                "UPDATE model_registry SET status = 'active' WHERE model_name = ? AND model_version = ?",
                (model_name, model_version),
            )
            conn.execute(
                """
                INSERT INTO model_promotion_events (
                    created_at, model_name, model_version, previous_active_version,
                    promoted, reason, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    model_name,
                    model_version,
                    previous_version,
                    1,
                    reason,
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def record_model_promotion_rejection(
        self,
        *,
        model_name: str,
        model_version: str,
        reason: str,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.update_model_status(model_version, "rejected")
        previous = self.active_model_version(model_name)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_promotion_events (
                    created_at, model_name, model_version, previous_active_version,
                    promoted, reason, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    model_name,
                    model_version,
                    str(previous["model_version"]) if previous else None,
                    0,
                    reason,
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def latest_model_promotion_events(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._latest_rows("model_promotion_events", limit)
        for row in rows:
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return rows

    def latest_model_versions(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._latest_rows("model_registry", limit)
        for row in rows:
            row["feature_names_json"] = _loads(row.get("feature_names_json"), [])
            row["metrics_json"] = _loads(row.get("metrics_json"), {})
            row["parameters_json"] = _loads(row.get("parameters_json"), {})
        return rows

    def record_reliability_report(
        self,
        *,
        report_type: str,
        status: str,
        summary: str,
        raw: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reliability_reports (created_at, report_type, status, summary, raw_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_now_iso(), report_type, status, summary, json.dumps(raw, default=_json_default)),
            )

    def latest_reliability_reports(self, report_type: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if report_type:
            where = "WHERE report_type = ?"
            params.append(report_type)
        params.append(limit)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM reliability_reports {where} ORDER BY id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        output = [dict(row) for row in rows]
        for row in output:
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return output

    def record_trade_root_cause(
        self,
        *,
        symbol: str,
        outcome_label: int,
        primary_cause: str,
        severity: float,
        raw: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_root_causes (
                    created_at, symbol, outcome_label, primary_cause, severity, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    symbol.upper(),
                    int(outcome_label),
                    primary_cause,
                    severity,
                    json.dumps(raw, default=_json_default),
                ),
            )

    def update_decision_veto_memory(
        self,
        *,
        pattern_key: str,
        symbol: str,
        pattern_label: str,
        return_pct: float,
        raw: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM decision_veto_memory WHERE pattern_key = ?",
                (pattern_key,),
            ).fetchone()
            if row:
                loss_count = int(row["loss_count"]) + (1 if return_pct < 0 else 0)
                win_count = int(row["win_count"]) + (1 if return_pct >= 0 else 0)
                total = loss_count + win_count
                avg_return = ((float(row["avg_return_pct"]) * (total - 1)) + return_pct) / max(total, 1)
            else:
                loss_count = 1 if return_pct < 0 else 0
                win_count = 1 if return_pct >= 0 else 0
                avg_return = return_pct
            total = loss_count + win_count
            loss_rate = loss_count / max(total, 1)
            veto_score = _clamp(loss_rate * 0.75 + _clamp(-avg_return * 25) * 0.25, 0.0, 1.0)
            conn.execute(
                """
                INSERT OR REPLACE INTO decision_veto_memory (
                    pattern_key, updated_at, symbol, pattern_label, loss_count, win_count,
                    avg_return_pct, veto_score, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern_key,
                    _now_iso(),
                    symbol.upper(),
                    pattern_label,
                    loss_count,
                    win_count,
                    avg_return,
                    veto_score,
                    json.dumps(raw, default=_json_default),
                ),
            )

    def veto_memory_for_features(self, features: dict[str, Any], *, limit: int = 5) -> dict[str, Any] | None:
        keys = _veto_pattern_keys(features)
        if not keys:
            return None
        placeholders = ",".join("?" for _ in keys)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM decision_veto_memory
                WHERE pattern_key IN ({placeholders})
                ORDER BY veto_score DESC, loss_count DESC
                LIMIT ?
                """,
                (*keys, limit),
            ).fetchall()
        if not rows:
            return None
        row = dict(rows[0])
        row["raw_json"] = _loads(row.get("raw_json"), {})
        return row

    def record_portfolio_risk_report(
        self,
        *,
        var_pct: float,
        cvar_pct: float,
        var_99_pct: float = 0.0,
        cvar_99_pct: float = 0.0,
        expected_shortfall_pct: float = 0.0,
        expected_shortfall_usd: float = 0.0,
        factors: dict[str, Any],
        scenarios: dict[str, Any],
        raw: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            for column in (
                ("var_99_pct", "REAL DEFAULT 0 NOT NULL"),
                ("cvar_99_pct", "REAL DEFAULT 0 NOT NULL"),
                ("expected_shortfall_pct", "REAL DEFAULT 0 NOT NULL"),
                ("expected_shortfall_usd", "REAL DEFAULT 0 NOT NULL"),
            ):
                _ensure_column(conn, "portfolio_risk_reports", column[0], column[1])
            conn.execute(
                """
                INSERT INTO portfolio_risk_reports (
                    created_at, var_pct, cvar_pct, var_99_pct, cvar_99_pct,
                    expected_shortfall_pct, expected_shortfall_usd, factor_json, scenarios_json, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    var_pct,
                    cvar_pct,
                    var_99_pct,
                    cvar_99_pct,
                    expected_shortfall_pct,
                    expected_shortfall_usd,
                    json.dumps(factors, default=_json_default),
                    json.dumps(scenarios, default=_json_default),
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def latest_portfolio_risk_reports(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._latest_rows("portfolio_risk_reports", limit)
        for row in rows:
            row["factor_json"] = _loads(row.get("factor_json"), {})
            row["scenarios_json"] = _loads(row.get("scenarios_json"), {})
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return rows

    def record_committee_vote(
        self,
        *,
        symbol: str,
        final_action: str,
        consensus_score: float,
        approved: bool,
        votes: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO committee_votes (
                    created_at, symbol, final_action, consensus_score, approved, votes_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    symbol.upper(),
                    final_action,
                    consensus_score,
                    int(approved),
                    json.dumps(votes, default=_json_default),
                ),
            )

    def latest_committee_votes(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._latest_rows("committee_votes", limit)
        for row in rows:
            row["votes_json"] = _loads(row.get("votes_json"), {})
        return rows

    def record_execution_simulation(
        self,
        *,
        simulation_id: str | None = None,
        symbol: str,
        action: str,
        quality_score: float,
        expected_slippage_bps: float,
        fill_probability: float,
        target_notional_usd: float = 0.0,
        raw: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            _ensure_execution_simulation_columns(conn)
            conn.execute(
                """
                INSERT INTO execution_simulations (
                    created_at, simulation_id, symbol, action, quality_score, expected_slippage_bps,
                    fill_probability, target_notional_usd, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    simulation_id,
                    symbol.upper(),
                    action,
                    quality_score,
                    expected_slippage_bps,
                    fill_probability,
                    target_notional_usd,
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def record_execution_actual(
        self,
        *,
        simulation_id: str,
        filled: bool,
        actual_fill_price: float | None = None,
        actual_slippage_bps: float | None = None,
        mode: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        raw_payload = raw or {}
        with self._connect() as conn:
            _ensure_execution_simulation_columns(conn)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT expected_slippage_bps, fill_probability, raw_json
                FROM execution_simulations
                WHERE simulation_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (simulation_id,),
            ).fetchone()
            if row is None:
                return
            expected_slippage = float(row["expected_slippage_bps"] or 0.0)
            fill_probability = float(row["fill_probability"] or 0.0)
            prediction_error = (
                actual_slippage_bps - expected_slippage
                if actual_slippage_bps is not None
                else None
            )
            fill_error = (1.0 if filled else 0.0) - fill_probability
            previous_raw = _loads(row["raw_json"], {})
            if isinstance(previous_raw, dict):
                previous_raw["actual_execution"] = raw_payload
            else:
                previous_raw = {"actual_execution": raw_payload}
            conn.execute(
                """
                UPDATE execution_simulations
                SET actual_slippage_bps = ?,
                    actual_fill_price = ?,
                    actual_mode = ?,
                    filled = ?,
                    prediction_error_bps = ?,
                    fill_error = ?,
                    learned_adjustment_bps = ?,
                    raw_json = ?
                WHERE simulation_id = ?
                """,
                (
                    actual_slippage_bps,
                    actual_fill_price,
                    mode,
                    int(filled),
                    prediction_error,
                    fill_error,
                    prediction_error or 0.0,
                    json.dumps(previous_raw, default=_json_default),
                    simulation_id,
                ),
            )

    def execution_slippage_profile(
        self,
        *,
        symbol: str | None = None,
        action: str | None = None,
        mode: str | None = None,
        limit: int = 200,
    ) -> dict[str, float | int]:
        clauses = ["filled IS NOT NULL"]
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper())
        if action:
            clauses.append("action = ?")
            params.append(action)
        if mode:
            clauses.append("actual_mode = ?")
            params.append(mode)
        with self._connect() as conn:
            _ensure_execution_simulation_columns(conn)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT actual_slippage_bps, prediction_error_bps, filled
                FROM execution_simulations
                WHERE {' AND '.join(clauses)}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        if not rows:
            return {
                "sample_count": 0,
                "avg_actual_slippage_bps": 0.0,
                "avg_prediction_error_bps": 0.0,
                "fill_rate": 0.85,
            }
        slippages = [float(row["actual_slippage_bps"]) for row in rows if row["actual_slippage_bps"] is not None]
        errors = [float(row["prediction_error_bps"]) for row in rows if row["prediction_error_bps"] is not None]
        filled = [int(row["filled"] or 0) for row in rows]
        return {
            "sample_count": len(rows),
            "avg_actual_slippage_bps": sum(slippages) / len(slippages) if slippages else 0.0,
            "avg_prediction_error_bps": sum(errors) / len(errors) if errors else 0.0,
            "fill_rate": sum(filled) / len(filled) if filled else 0.85,
        }

    def latest_execution_simulations(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._latest_rows("execution_simulations", limit)
        for row in rows:
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return rows

    def record_news_source_stat(
        self,
        *,
        source: str,
        mentions: int,
        avg_sentiment: float,
        avg_catalyst: float,
        credibility_score: float,
        raw: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO news_source_stats (
                    created_at, source, mentions, avg_sentiment, avg_catalyst, credibility_score, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    source,
                    mentions,
                    avg_sentiment,
                    avg_catalyst,
                    credibility_score,
                    json.dumps(raw or {}, default=_json_default),
                ),
            )

    def record_news_source_outcome(
        self,
        *,
        source: str,
        symbol: str,
        return_pct: float,
        sentiment_score: float,
        catalyst_score: float,
        item_age_hours: float = 999.0,
        raw: dict[str, Any] | None = None,
    ) -> None:
        source_key = _normalize_source(source)
        if not source_key:
            return
        direction_correct = _direction_correct(sentiment_score, return_pct)
        catalyst_moved_price = abs(return_pct) >= 0.005 and catalyst_score >= 0.2
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO news_source_outcomes (
                    created_at, source, symbol, return_pct, abs_return_pct, sentiment_score,
                    catalyst_score, item_age_hours, direction_correct, catalyst_moved_price, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    source_key,
                    symbol.upper(),
                    return_pct,
                    abs(return_pct),
                    sentiment_score,
                    catalyst_score,
                    item_age_hours,
                    int(direction_correct),
                    int(catalyst_moved_price),
                    json.dumps(raw or {}, default=_json_default),
                ),
            )
            _refresh_news_source_credibility(conn, source_key)

    def news_source_credibility_profiles(self, limit: int = 500) -> dict[str, dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM news_source_credibility
                ORDER BY reliability_score DESC, sample_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        profiles: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = dict(row)
            payload["raw_json"] = _loads(payload.get("raw_json"), {})
            profiles[str(payload["source"])] = payload
        return profiles

    def latest_news_source_stats(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._latest_rows("news_source_stats", limit)
        for row in rows:
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return rows

    def latest_news_source_credibility(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM news_source_credibility
                ORDER BY reliability_score DESC, sample_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        output = [dict(row) for row in rows]
        for row in output:
            row["raw_json"] = _loads(row.get("raw_json"), {})
        return output

    def _record_news_source_outcomes_from_trade(
        self,
        *,
        symbol: str,
        return_pct: float,
        entry_features: dict[str, Any],
        raw: dict[str, Any],
    ) -> None:
        sources = _split_sources(entry_features.get("news_sources", ""))
        if not sources:
            return
        sentiment = _float(entry_features.get("news_sentiment"), 0.0)
        catalyst = _float(entry_features.get("news_catalyst"), 0.0)
        item_age = _float(entry_features.get("news_avg_item_age_hours"), 999.0)
        for source in sources:
            self.record_news_source_outcome(
                source=source,
                symbol=symbol,
                return_pct=return_pct,
                sentiment_score=sentiment,
                catalyst_score=catalyst,
                item_age_hours=item_age,
                raw={"trade": raw.get("source", "trade_outcome")},
            )

    def latest_feature_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._latest_rows("feature_snapshots", limit)
        for row in rows:
            row["features_json"] = _loads(row.get("features_json"), {})
        return rows

    def feature_snapshot_by_id(self, snapshot_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM feature_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["features_json"] = _loads(record.get("features_json"), {})
        return record

    def model_version_by_version(self, model_version: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM model_registry
                WHERE model_version = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (model_version,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["feature_names_json"] = _loads(record.get("feature_names_json"), [])
        record["metrics_json"] = _loads(record.get("metrics_json"), {})
        record["parameters_json"] = _loads(record.get("parameters_json"), {})
        return record

    def table_count(self, table: str) -> int:
        allowed = {
            "decisions",
            "risk_checks",
            "orders",
            "cycle_health",
            "model_registry",
            "model_training_runs",
            "model_promotion_events",
            "reliability_reports",
            "reconciliations",
            "portfolio_risk_reports",
            "feature_snapshots",
            "committee_votes",
            "execution_simulations",
        }
        if table not in allowed:
            raise ValueError(f"unsupported count table: {table}")
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0

    def _latest_rows(self, table: str, limit: int) -> list[dict[str, Any]]:
        allowed = {
            "feature_snapshots",
            "cycle_feature_store",
            "training_examples",
            "model_training_runs",
            "model_registry",
            "model_promotion_events",
            "portfolio_risk_reports",
            "committee_votes",
            "execution_simulations",
            "news_source_stats",
            "news_source_outcomes",
            "reliability_reports",
        }
        if table not in allowed:
            raise ValueError(f"unsupported table: {table}")
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def audit(self, event_type: str, payload: Any) -> None:
        record = {
            "created_at": _now_iso(),
            "event_type": event_type,
            "payload": payload,
        }
        with self.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=_json_default) + "\n")


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _loads(value: Any, default: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else default
    except json.JSONDecodeError:
        return default


def _extract_nested_features(raw: dict[str, Any], key: str) -> dict[str, Any]:
    nested = raw.get(key, {})
    if not isinstance(nested, dict):
        return {}
    features = nested.get("features_json", nested.get("features", {}))
    return features if isinstance(features, dict) else {}


def _decode_json_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    for field in fields:
        row[field] = _loads(row.get(field), {})
    return row


def _history_return(candles: list[Any], periods: int) -> float:
    if len(candles) <= periods:
        return 0.0
    start = candles[-periods - 1].close
    end = candles[-1].close
    if start <= 0:
        return 0.0
    return (end - start) / start


def _history_volatility(candles: list[Any], periods: int) -> float:
    selected = candles[-periods - 1 :] if len(candles) > periods else candles
    if len(selected) < 3:
        return 0.0
    returns = []
    for previous, current in zip(selected, selected[1:]):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return variance ** 0.5


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_execution_simulation_columns(conn: sqlite3.Connection) -> None:
    for column, definition in (
        ("simulation_id", "TEXT"),
        ("target_notional_usd", "REAL DEFAULT 0 NOT NULL"),
        ("actual_slippage_bps", "REAL"),
        ("actual_fill_price", "REAL"),
        ("actual_mode", "TEXT"),
        ("filled", "INTEGER"),
        ("prediction_error_bps", "REAL"),
        ("fill_error", "REAL"),
        ("learned_adjustment_bps", "REAL DEFAULT 0 NOT NULL"),
    ):
        _ensure_column(conn, "execution_simulations", column, definition)


def _refresh_news_source_credibility(conn: sqlite3.Connection, source: str) -> None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT return_pct, abs_return_pct, item_age_hours, direction_correct, catalyst_moved_price
        FROM news_source_outcomes
        WHERE source = ?
        ORDER BY id DESC
        LIMIT 500
        """,
        (source,),
    ).fetchall()
    if not rows:
        return
    sample_count = len(rows)
    hit_rate = sum(int(row["direction_correct"] or 0) for row in rows) / sample_count
    catalyst_move_rate = sum(int(row["catalyst_moved_price"] or 0) for row in rows) / sample_count
    avg_return = sum(float(row["return_pct"] or 0.0) for row in rows) / sample_count
    avg_abs_return = sum(float(row["abs_return_pct"] or 0.0) for row in rows) / sample_count
    avg_item_age = sum(float(row["item_age_hours"] or 999.0) for row in rows) / sample_count
    speed_score = _clamp(1.0 - avg_item_age / 72.0, 0.0, 1.0)
    noise_score = _clamp(1.0 - hit_rate, 0.0, 1.0)
    move_score = _clamp(avg_abs_return / 0.03, 0.0, 1.0)
    reliability = _clamp(
        0.25
        + 0.34 * hit_rate
        + 0.22 * catalyst_move_rate
        + 0.12 * move_score
        + 0.07 * speed_score
        - 0.18 * noise_score,
        0.05,
        1.0,
    )
    credibility_multiplier = _clamp(0.55 + reliability, 0.45, 1.45)
    raw = {
        "fast_but_unreliable": speed_score >= 0.75 and hit_rate < 0.45,
        "learned_from_samples": sample_count,
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO news_source_credibility (
            source, updated_at, sample_count, hit_rate, catalyst_move_rate,
            avg_return_pct, avg_abs_return_pct, avg_item_age_hours,
            reliability_score, speed_score, noise_score, credibility_multiplier, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            _now_iso(),
            sample_count,
            hit_rate,
            catalyst_move_rate,
            avg_return,
            avg_abs_return,
            avg_item_age,
            reliability,
            speed_score,
            noise_score,
            credibility_multiplier,
            json.dumps(raw, default=_json_default),
        ),
    )


def _normalize_source(source: str) -> str:
    return source.strip().lower()


def _split_sources(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_sources = value.split(",")
    elif isinstance(value, (list, tuple)):
        raw_sources = [str(source) for source in value]
    else:
        raw_sources = []
    output: list[str] = []
    for source in raw_sources:
        source_key = _normalize_source(source)
        if source_key and source_key not in output:
            output.append(source_key)
    return output


def _veto_pattern_keys(features: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    regime = str(features.get("regime_name", features.get("market_regime", ""))).strip().lower()
    if regime:
        keys.append(f"regime:{regime}")
    if _float(features.get("news_sentiment"), 0.0) <= -0.25:
        keys.append("news:negative")
    if _float(features.get("execution_sim_expected_slippage_bps"), 0.0) >= 20:
        keys.append("execution:high_slippage")
    if _float(features.get("allocation_max_stress_loss_pct"), 0.0) >= 0.04:
        keys.append("portfolio:stress")
    if _float(features.get("timing_confidence"), 1.0) <= 0.45:
        keys.append("timing:low_confidence")
    return keys


def _direction_correct(sentiment_score: float, return_pct: float) -> bool:
    if abs(sentiment_score) < 0.05:
        return abs(return_pct) < 0.005
    return (sentiment_score > 0 and return_pct > 0) or (sentiment_score < 0 and return_pct < 0)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(min(value, maximum), minimum)


def _cycle_feature_value(column: str, value: Any) -> Any:
    if column in {"created_at", "cycle_id", "symbol", "benchmark_symbol", "action", "regime_name", "raw_features_json"}:
        return "" if value is None else str(value)
    if column in {
        "is_trade",
        "news_item_count",
        "news_source_count",
        "allocation_approved",
        "committee_approved",
        "risk_approved",
        "outcome_label",
        "outcome_holding_days",
    }:
        if value is None and column in {"allocation_approved", "committee_approved", "risk_approved", "outcome_label", "outcome_holding_days"}:
            return None
        if isinstance(value, bool):
            return 1 if value else 0
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    if value is None and column in {"outcome_return_pct", "outcome_pnl_usd"}:
        return None
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0

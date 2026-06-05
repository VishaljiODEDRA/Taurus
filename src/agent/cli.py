from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from agent.backtest import Backtester, WalkForwardValidator, load_cached_candles
from agent.broker_sync import BrokerAccountSync, broker_research_config
from agent.calibration import ModelCalibrator
from agent.config import load_config
from agent.engine import TradingAgent
from agent.ledger import Ledger
from agent.metrics import PerformanceMetrics, TradeRecord, calculate_metrics
from agent.monitoring import HealthMonitor
from agent.point_in_time import PointInTimeReplayer, RealisticReplayEngine
from agent.reliability import ReliabilityAnalyzer
from agent.reconcile import Reconciler
from agent.reporting import ReportingDashboard
from agent.risk import is_kill_switch_active, set_kill_switch
from agent.training import WalkForwardModelTrainer
from etoro_api import EtoroApiError, EtoroClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Risk-first eToro AutoTrading Agent")
    parser.add_argument("--config", default="config/strategy.toml", help="Path to strategy TOML")
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument("--config", default=argparse.SUPPRESS, help="Path to strategy TOML")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "scan",
        parents=[config_parent],
        help="Rank current candidates without executing",
    )

    subparsers.add_parser(
        "doctor",
        parents=[config_parent],
        help="Check local config and eToro API authentication",
    )

    subparsers.add_parser(
        "data-health",
        parents=[config_parent],
        help="Summarise cached candle coverage for chart scoring",
    )

    run_once = subparsers.add_parser(
        "run-once",
        parents=[config_parent],
        help="Run one decision/risk/execution cycle",
    )
    run_once.add_argument("--allow-live", action="store_true", help="Required second gate for live mode")

    run_loop = subparsers.add_parser(
        "run-loop",
        parents=[config_parent],
        help="Run continuously",
    )
    run_loop.add_argument("--allow-live", action="store_true", help="Required second gate for live mode")
    run_loop.add_argument("--cycles", type=int, default=0, help="Optional number of cycles; 0 = forever")

    run_live = subparsers.add_parser(
        "run-live",
        parents=[config_parent],
        help="Run continuously with graceful Ctrl+C shutdown",
    )
    run_live.add_argument("--allow-live", action="store_true", help="Required second gate for live mode")
    run_live.add_argument("--cycles", type=int, default=0, help="Optional number of cycles; 0 = forever")

    kill = subparsers.add_parser(
        "kill-switch",
        parents=[config_parent],
        help="Manage the local emergency halt",
    )
    kill.add_argument("state", choices=["on", "off", "status"])
    kill.add_argument("--reason", default="manual halt")

    journal = subparsers.add_parser(
        "journal",
        parents=[config_parent],
        help="Show recent order journal rows",
    )
    journal.add_argument("--limit", type=int, default=10)

    position_review_journal = subparsers.add_parser(
        "position-review-journal",
        parents=[config_parent],
        help="Show recent open-position review rows",
    )
    position_review_journal.add_argument("--limit", type=int, default=10)

    backtest = subparsers.add_parser(
        "backtest",
        parents=[config_parent],
        help="Run a local backtest using cached candle data",
    )
    backtest.add_argument("--sync-broker", action="store_true", help="Fetch demo/real account state before running")
    backtest.add_argument(
        "--include-simulation",
        action="store_true",
        help="After broker sync, also run simulated cached-candle backtest",
    )

    walk_forward = subparsers.add_parser(
        "walk-forward",
        parents=[config_parent],
        help="Run walk-forward validation using cached candle data",
    )
    walk_forward.add_argument("--sync-broker", action="store_true", help="Fetch demo/real account state before running")

    calibrate = subparsers.add_parser(
        "calibrate",
        parents=[config_parent],
        help="Calibrate thresholds from trade outcomes or cached backtest data",
    )
    calibrate.add_argument(
        "--source",
        choices=["outcomes", "backtest"],
        default="outcomes",
        help="Calibration source",
    )
    calibrate.add_argument("--as-of", default=None, help="Point-in-time cutoff, e.g. 2026-05-15T10:30:00Z")
    calibrate.add_argument("--sync-broker", action="store_true", help="Import broker history before calibrating")

    train_model = subparsers.add_parser(
        "train-model",
        parents=[config_parent],
        help="Train the normalized meta-label filter from recorded trade outcomes",
    )
    train_model.add_argument("--min-samples", type=int, default=20)
    train_model.add_argument("--as-of", default=None, help="Point-in-time cutoff for training data")
    train_model.add_argument("--sync-broker", action="store_true", help="Import broker history before training")

    subparsers.add_parser(
        "sync-broker",
        parents=[config_parent],
        help="Fetch eToro virtual/real balance, portfolio, and closed trade history into the ledger",
    ).add_argument(
        "--dump-history",
        default=None,
        help="Optional path to save raw broker trade-history JSON for parser diagnostics",
    )

    report = subparsers.add_parser(
        "report",
        parents=[config_parent],
        help="Show the institutional decision/risk/execution dashboard summary",
    )
    report.add_argument("--limit", type=int, default=10)

    replay = subparsers.add_parser(
        "replay-as-of",
        parents=[config_parent],
        help="Replay decisions, features, news, risk, and orders available at a timestamp",
    )
    replay.add_argument("--as-of", required=True, help="Replay cutoff, e.g. 2026-05-15T10:30:00Z")
    replay.add_argument("--symbol", default=None)
    replay.add_argument("--limit", type=int, default=20)

    realistic_replay = subparsers.add_parser(
        "realistic-replay",
        parents=[config_parent],
        help="Replay the historical decision state exactly as-of-time",
    )
    realistic_replay.add_argument("--as-of", required=True)
    realistic_replay.add_argument("--symbol", default=None)
    realistic_replay.add_argument("--limit", type=int, default=20)

    history = subparsers.add_parser(
        "cycle-history",
        parents=[config_parent],
        help="Show structured saved market/news/portfolio/regime history for a cycle",
    )
    history.add_argument("--cycle-id", default=None)
    history.add_argument("--limit", type=int, default=20)

    reliability = subparsers.add_parser(
        "reliability-report",
        parents=[config_parent],
        help="Generate feature ablation, calibration, and paper readiness reports",
    )
    reliability.add_argument(
        "--type",
        choices=["all", "feature-ablation", "calibration", "paper-scorecard", "labeled-dataset", "governance"],
        default="all",
    )

    subparsers.add_parser(
        "reconcile",
        parents=[config_parent],
        help="Fetch broker portfolio state and record reconciliation",
    )

    subparsers.add_parser(
        "monitor",
        parents=[config_parent],
        help="Evaluate recent agent health and alert/kill-switch rules",
    )

    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "scan":
        agent = TradingAgent(config)
        try:
            decisions = agent.scan()
        except EtoroApiError as exc:
            _print_etoro_error(exc)
            return
        _print_decisions(decisions)
        return

    if args.command == "doctor":
        _run_doctor(config)
        return

    if args.command == "data-health":
        _run_data_health(config)
        return

    if args.command == "run-once":
        agent = TradingAgent(config, allow_live_cli=args.allow_live)
        result = agent.run_once()
        _print_cycle_result(result)
        return

    if args.command == "run-loop":
        agent = TradingAgent(config, allow_live_cli=args.allow_live)
        _run_loop(agent, config.agent.loop_interval_seconds, args.cycles)
        return

    if args.command == "run-live":
        agent = TradingAgent(config, allow_live_cli=args.allow_live)
        _run_loop(agent, config.agent.loop_interval_seconds, args.cycles)
        return

    if args.command == "kill-switch":
        if args.state == "status":
            active = is_kill_switch_active(config.risk.kill_switch_path)
            status = "ON" if active else "OFF"
            print(f"Kill switch: {status} ({config.risk.kill_switch_path})")
            if active:
                print(Path(config.risk.kill_switch_path).read_text(encoding="utf-8").strip())
            return
        set_kill_switch(config.risk.kill_switch_path, args.state == "on", args.reason)
        print(f"Kill switch set to {args.state.upper()}")
        return

    if args.command == "journal":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        for row in ledger.latest_orders(limit=args.limit):
            print(
                f"{row['created_at']} {row['mode']} {row['symbol']} {row['action']} "
                f"accepted={bool(row['accepted'])} id={row['broker_order_id']} {row['message']}"
            )
        return

    if args.command == "position-review-journal":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        for row in ledger.latest_position_reviews(limit=args.limit):
            print(
                f"{row['created_at']} {row['symbol']} {row['action']} "
                f"urgency={row['urgency_score']:.3f} score={row['score']:.3f} confidence={row['confidence']:.3f}"
            )
        return

    if args.command == "backtest":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        if args.sync_broker:
            sync_result = BrokerAccountSync(config, ledger).run()
            _print_broker_sync(sync_result)
            _print_broker_history_performance(ledger, sync_result.environment)
            if not args.include_simulation:
                print("Simulation skipped. Add --include-simulation if you intentionally want cached-candle simulated trades.")
                return
        config, account_note = broker_research_config(config, ledger)
        candles = load_cached_candles(config.universe.market_cache_path)
        result = Backtester(config).run(candles)
        print(f"Account basis: {account_note}")
        print("Data basis: simulated backtest trades from cached candles, not broker trading history")
        _print_metrics("Simulated backtest", result.metrics, result.readiness_passed)
        print(f"Simulated trades: {len(result.trades)}")
        return

    if args.command == "walk-forward":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        if args.sync_broker:
            _print_broker_sync(BrokerAccountSync(config, ledger).run())
        config, account_note = broker_research_config(config, ledger)
        candles = load_cached_candles(config.universe.market_cache_path)
        results = WalkForwardValidator(config).run(candles)
        if not results:
            print("No walk-forward windows available. Build candle cache first by running scan/run-once over more cycles.")
            print(f"Account basis: {account_note}")
            return
        passed = sum(1 for result in results if result.readiness_passed)
        print(f"Account basis: {account_note}")
        print(f"Walk-forward windows: {len(results)} passed={passed}")
        for index, result in enumerate(results, start=1):
            _print_metrics(f"Window {index}", result.metrics, result.readiness_passed)
        return

    if args.command == "calibrate":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        if args.sync_broker:
            _print_broker_sync(BrokerAccountSync(config, ledger).run())
        if args.source == "backtest":
            config, account_note = broker_research_config(config, ledger)
        else:
            account_note = "using recorded broker/agent trade outcomes"
        calibrator = ModelCalibrator(config, ledger)
        if args.source == "backtest":
            candles = load_cached_candles(config.universe.market_cache_path)
            result = calibrator.from_backtest(candles, as_of=args.as_of)
        else:
            result = calibrator.from_trade_outcomes(as_of=args.as_of)
        print(f"Account basis: {account_note}")
        if args.source == "backtest":
            print("Data basis: simulated threshold search from cached candles, not broker trading history")
        else:
            print("Data basis: real recorded trade outcomes from broker sync and/or agent-closed positions")
        print(f"Calibration source: {result.source}")
        print(f"Samples: {result.sample_count}")
        print(f"Suggested buy_threshold: {result.suggested_buy_threshold:.3f}")
        print(f"Suggested sell_threshold: {result.suggested_sell_threshold:.3f}")
        print(f"Metrics: {result.metrics}")
        return

    if args.command == "train-model":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        if args.sync_broker:
            _print_broker_sync(BrokerAccountSync(config, ledger).run())
        result = WalkForwardModelTrainer(ledger).train(min_samples=args.min_samples, as_of=args.as_of)
        print("Data basis: real recorded trade outcomes only")
        print(f"Training model: {result.model_name}")
        print(f"Version: {result.model_version}")
        print(
            f"Samples: {result.sample_count} train={result.train_count} "
            f"validation={result.validation_count} test={result.test_count}"
        )
        if result.artifact_path:
            print(f"Artifact: {result.artifact_path}")
        print(f"Metrics: {result.metrics}")
        print(f"Parameters: {result.parameters}")
        return

    if args.command == "sync-broker":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        _print_broker_sync(BrokerAccountSync(config, ledger).run(history_dump_path=args.dump_history))
        if args.dump_history:
            print(f"Raw broker history saved to {args.dump_history}")
        return

    if args.command == "report":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        _print_report(ReportingDashboard(ledger).summary(limit=args.limit))
        return

    if args.command == "replay-as-of":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        replay = PointInTimeReplayer(ledger).replay(args.as_of, symbol=args.symbol, limit=args.limit)
        _print_replay(replay)
        return

    if args.command == "realistic-replay":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        replay = RealisticReplayEngine(ledger).replay_cycle(args.as_of, symbol=args.symbol, limit=args.limit)
        print(json.dumps(replay, indent=2, default=str))
        return

    if args.command == "cycle-history":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        history = ledger.latest_cycle_data_history(cycle_id=args.cycle_id, limit=args.limit)
        print(json.dumps(history, indent=2, default=str))
        return

    if args.command == "reliability-report":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        analyzer = ReliabilityAnalyzer(ledger)
        reports = []
        if args.type in {"all", "feature-ablation"}:
            reports.append(analyzer.feature_ablation_report())
        if args.type in {"all", "calibration"}:
            reports.append(analyzer.calibration_report())
        if args.type in {"all", "paper-scorecard"}:
            reports.append(analyzer.paper_scorecard())
        if args.type in {"all", "labeled-dataset"}:
            reports.append(analyzer.labeled_dataset_report())
        if args.type in {"all", "governance"}:
            reports.append(analyzer.governance_dashboard())
        for report in reports:
            print(f"{report.report_type}: {report.status} - {report.summary}")
        return

    if args.command == "reconcile":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        report = Reconciler(config, ledger).run()
        print(f"Reconciliation: {report.status} - {report.message}")
        print(f"Open positions: {report.open_positions}")
        print(f"Recent local orders: {report.recent_local_orders}")
        for alert in report.alerts:
            symbol = f" {alert.symbol}" if alert.symbol else ""
            print(f"{alert.level.upper()}:{symbol} {alert.code} - {alert.message}")
        return

    if args.command == "monitor":
        ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
        alerts = HealthMonitor(config.monitoring, config.risk, ledger).evaluate()
        if not alerts:
            print("Monitoring: OK")
            return
        for alert in alerts:
            print(f"{alert.level.upper()}: {alert.message} {alert.details}")
        return


def _print_decisions(decisions) -> None:
    if not decisions:
        print("No decisions produced.")
        return
    print(f"{'SYMBOL':8} {'ACTION':6} {'SCORE':>7} {'CONF':>7} REASONS")
    for decision in decisions:
        reasons = "; ".join(decision.reasons[:3])
        print(
            f"{decision.symbol:8} {decision.action:6} {decision.score:7.3f} "
            f"{decision.confidence:7.3f} {reasons}"
        )
        _print_reasoning(decision)


def _print_cycle_result(result) -> None:
    if result.halted:
        print(f"Cycle halted: {result.halt_reason}")
        return
    print(
        f"Cycle complete: decisions={len(result.decisions)} "
        f"risk_checks={len(result.risk_decisions)} orders={len(result.orders)}"
    )
    _print_cycle_dashboard(result.dashboard)
    regime_line = _regime_summary_line(result)
    if regime_line:
        print(regime_line)
    _print_allocation_plan(result.decisions)
    if result.position_reviews:
        print("Open position review:")
        for review in result.position_reviews:
            reasons = "; ".join(review.reasons[:3])
            print(
                f"  {review.symbol} {review.action} "
                f"score={review.score:.3f} confidence={review.confidence:.3f} {reasons}"
            )
            _print_reasoning(review)
    if result.decisions:
        print("Decisions:")
        for decision in result.decisions[:5]:
            reasons = "; ".join(decision.reasons[:2])
            print(
                f"  {decision.symbol} {decision.action} "
                f"score={decision.score:.3f} confidence={decision.confidence:.3f} {reasons}"
            )
            _print_reasoning(decision)
    for order in result.orders:
        print(
            f"  {order.mode} {order.symbol} {order.action} "
            f"accepted={order.accepted} id={order.broker_order_id} {order.message}"
        )
        raw_order = order.raw.get("order") if isinstance(order.raw, dict) else None
        if isinstance(raw_order, dict):
            _print_reasoning_from_features(raw_order.get("features", {}))
    if not result.orders:
        print("No orders submitted.")


def _run_loop(agent: TradingAgent, interval_seconds: int, cycles: int) -> None:
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"Starting live cycle {cycle}")
            result = agent.run_once()
            _print_cycle_result(result)
            if result.halted:
                return
            if cycles and cycle >= cycles:
                return
            print(f"Waiting {interval_seconds}s for next cycle. Press Ctrl+C to stop.")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nLive loop stopped by user. Back at terminal.")


def _print_metrics(label: str, metrics: PerformanceMetrics, passed: bool) -> None:
    print(f"{label}: readiness={'PASS' if passed else 'FAIL'}")
    print(
        f"  trades={metrics.trades} win_rate={metrics.win_rate:.2%} "
        f"total_return={metrics.total_return_pct:.2%} profit_factor={metrics.profit_factor:.2f}"
    )
    print(
        f"  max_drawdown={metrics.max_drawdown_pct:.2%} sharpe={metrics.sharpe:.2f} "
        f"deflated_sharpe={metrics.deflated_sharpe_proxy:.2f} "
        f"sortino={metrics.sortino:.2f} final_equity=${metrics.final_equity_usd:,.2f}"
    )


def _print_broker_sync(result) -> None:
    print(
        f"Broker sync: {result.message} environment={result.environment} "
        f"NAV=${result.nav_usd:,.2f} cash=${result.available_cash_usd:,.2f} "
        f"positions={result.open_positions} history_items={result.history_items_found} "
        f"imported_trades={result.imported_trades} "
        f"skipped={result.skipped_trades}"
    )


def _print_broker_history_performance(ledger: Ledger, environment: str) -> None:
    snapshot = ledger.latest_broker_account_snapshot(environment)
    initial_equity = float(snapshot["nav_usd"]) if snapshot and snapshot.get("nav_usd") else 0.0
    rows = [
        row
        for row in ledger.trade_outcomes(limit=2_000)
        if row.get("source") == "broker_trade_history"
    ]
    if not rows:
        print("Broker history: no closed broker trades imported from eToro API yet.")
        print("Broker history: eToro returned 0 history items, so real wins/losses cannot be calculated here.")
        print("Broker history: run sync-broker --dump-history state/etoro_history_dump.json to inspect the raw endpoint response.")
        return
    rows = list(reversed(rows))
    trades = [
        TradeRecord(
            symbol=str(row.get("symbol", "")),
            entry_time=str(row.get("entry_time") or ""),
            exit_time=str(row.get("exit_time") or ""),
            entry_price=0.0,
            exit_price=0.0,
            notional_usd=0.0,
            pnl_usd=float(row.get("pnl_usd", 0.0) or 0.0),
            return_pct=float(row.get("return_pct", 0.0) or 0.0),
            reason="broker_trade_history",
            holding_days=int(row.get("holding_days", 0) or 0),
        )
        for row in rows
    ]
    equity = initial_equity or max(sum(trade.pnl_usd for trade in trades), 1.0)
    equity_curve = [equity]
    for trade in trades:
        equity_curve.append(equity_curve[-1] + trade.pnl_usd)
    metrics = calculate_metrics(trades, equity_curve, initial_equity_usd=equity_curve[0])
    _print_metrics("Real broker history", metrics, passed=False)
    print(f"Real broker trades imported: {len(trades)}")


def _print_reasoning(decision) -> None:
    _print_reasoning_from_features(decision.features)


def _print_reasoning_from_features(features: dict) -> None:
    summary = features.get("reasoning_summary")
    indicator_summary = features.get("indicator_summary")
    market_summary = features.get("market_summary")
    news_summary = features.get("news_summary")
    meta_summary = features.get("meta_summary")
    meta_reasoning_summary = features.get("meta_reasoning_summary")
    timing_reason = features.get("timing_reason")
    timing_close_action = features.get("timing_close_action")
    timing_earliest = features.get("timing_earliest_days")
    timing_likely = features.get("timing_likely_days")
    timing_latest = features.get("timing_latest_days")
    timing_invalidation = features.get("timing_invalidation_days")
    timing_confidence = features.get("timing_confidence")
    adaptive_stop = features.get("adaptive_stop_loss_pct")
    adaptive_take_profit = features.get("adaptive_take_profit_pct")
    open_rate_source = features.get("open_rate_source")
    urgency_score = features.get("urgency_score")
    review_pnl_pct = features.get("review_pnl_pct")
    hold_strength = features.get("hold_strength")
    market_regime_strength = features.get("market_regime_strength")
    if summary:
        print(f"    Why: {summary}")
    if indicator_summary:
        print(f"    Indicators: {indicator_summary}")
    if market_summary:
        print(f"    Market: {market_summary}")
    if news_summary:
        print(f"    News: {news_summary}")
    if meta_summary:
        print(f"    Meta: {meta_summary}")
    if meta_reasoning_summary:
        print(f"    Meta view: {meta_reasoning_summary}")
    if timing_close_action and all(
        isinstance(value, (int, float))
        for value in (timing_earliest, timing_likely, timing_latest, timing_invalidation, timing_confidence)
    ):
        print(
            f"    Timing: close_action={timing_close_action} "
            f"window={int(timing_earliest)}-{int(timing_latest)} trading_days "
            f"center_day={int(timing_likely)} invalidation_day={int(timing_invalidation)} "
            f"confidence={float(timing_confidence):.3f}"
        )
    if timing_reason:
        print(f"    Timing view: {timing_reason}")
    execution_quality = features.get("risk_execution_quality_score")
    execution_sim_quality = features.get("execution_sim_quality_score")
    execution_sim_slippage = features.get("execution_sim_expected_slippage_bps")
    execution_sim_fill = features.get("execution_sim_fill_probability")
    slippage = features.get("risk_expected_slippage_bps")
    avg_dollar_volume = features.get("risk_avg_dollar_volume")
    volatility_burst = features.get("risk_micro_volatility_burst")
    liquidity_stress = features.get("risk_micro_liquidity_stress")
    if any(isinstance(value, (int, float)) for value in (execution_quality, slippage, avg_dollar_volume)):
        execution_line = "    Execution:"
        if isinstance(execution_quality, (int, float)):
            execution_line += f" quality={execution_quality:.3f}"
        if isinstance(slippage, (int, float)):
            execution_line += f" slippage={slippage:.1f}bps"
        if isinstance(avg_dollar_volume, (int, float)):
            execution_line += f" adv=${avg_dollar_volume:,.0f}"
        if isinstance(volatility_burst, (int, float)):
            execution_line += f" vol_burst={volatility_burst:.3f}"
        if isinstance(liquidity_stress, (int, float)):
            execution_line += f" liquidity_stress={liquidity_stress:.3f}"
        print(execution_line)
    if any(isinstance(value, (int, float)) for value in (execution_sim_quality, execution_sim_slippage, execution_sim_fill)):
        simulation_line = "    Execution simulation:"
        if isinstance(execution_sim_quality, (int, float)):
            simulation_line += f" quality={float(execution_sim_quality):.3f}"
        if isinstance(execution_sim_slippage, (int, float)):
            simulation_line += f" expected_slippage={float(execution_sim_slippage):.1f}bps"
        if isinstance(execution_sim_fill, (int, float)):
            simulation_line += f" fill_probability={float(execution_sim_fill):.2f}"
        print(simulation_line)
    committee_consensus = features.get("committee_consensus_score")
    committee_reason = features.get("committee_reason")
    committee_approved = features.get("committee_approved")
    if isinstance(committee_consensus, (int, float)):
        print(
            f"    Committee: approved={bool(committee_approved)} "
            f"consensus={float(committee_consensus):.3f} {committee_reason or ''}"
        )
    if isinstance(urgency_score, (int, float)):
        pnl_text = f" pnl={review_pnl_pct:.2%}" if isinstance(review_pnl_pct, (int, float)) else ""
        hold_text = (
            f" hold_strength={hold_strength:.3f} market_strength={market_regime_strength:.3f}"
            if isinstance(hold_strength, (int, float)) and isinstance(market_regime_strength, (int, float))
            else ""
        )
        print(f"    Scorecard: urgency={urgency_score:.3f}{pnl_text}{hold_text}")
    if isinstance(adaptive_stop, (int, float)) and isinstance(adaptive_take_profit, (int, float)):
        if adaptive_stop > 0 or adaptive_take_profit > 0:
            source_text = f" source={open_rate_source}" if open_rate_source else ""
            print(
                f"    Protection: adaptive_stop={adaptive_stop:.2%} "
                f"adaptive_take_profit={adaptive_take_profit:.2%}{source_text}"
            )


def _print_allocation_plan(decisions) -> None:
    allocation_rows = []
    for decision in decisions:
        if decision.action != "BUY":
            continue
        target = decision.features.get("allocation_target_notional_usd")
        approved = decision.features.get("allocation_approved")
        if target is None and approved is None:
            continue
        allocation_rows.append(decision)
    if not allocation_rows:
        return

    print("Capital allocation plan:")
    for decision in allocation_rows:
        approved = bool(decision.features.get("allocation_approved"))
        target = float(decision.features.get("allocation_target_notional_usd", 0.0))
        reason = str(decision.features.get("allocation_reason", ""))
        hhi = decision.features.get("allocation_hhi")
        diversification = decision.features.get("allocation_diversification_score")
        stress = decision.features.get("allocation_max_stress_loss_pct")
        edge_size_multiplier = decision.features.get("allocation_edge_size_multiplier")
        priority_score = decision.features.get("allocation_priority_score")
        worst_name = decision.features.get("allocation_worst_scenario")
        worst_loss = decision.features.get("allocation_worst_scenario_loss_pct")
        status = "funded" if approved else "skipped"
        detail = (
            f" hhi={float(hhi):.3f} diversification={float(diversification):.3f} stress={float(stress):.2%}"
            if isinstance(hhi, (int, float))
            and isinstance(diversification, (int, float))
            and isinstance(stress, (int, float))
            else ""
        )
        scenario_text = (
            f" worst_case={worst_name} {float(worst_loss):.2%}"
            if worst_name and isinstance(worst_loss, (int, float))
            else ""
        )
        sizing_text = (
            f" edge_size={float(edge_size_multiplier):.2f} priority={float(priority_score):.3f}"
            if isinstance(edge_size_multiplier, (int, float)) and isinstance(priority_score, (int, float))
            else ""
        )
        print(
            f"  {decision.symbol} {status} target=${target:,.2f} "
            f"score={decision.score:.3f} confidence={decision.confidence:.3f}"
            f"{detail}{scenario_text}{sizing_text}"
        )
        if reason:
            print(f"    Allocation: {reason}")


def _print_cycle_dashboard(dashboard: dict) -> None:
    if not dashboard:
        return
    regime_probabilities = dashboard.get("regime_probabilities", {})
    if isinstance(regime_probabilities, dict) and regime_probabilities:
        ordered = sorted(
            (
                (str(name), float(value))
                for name, value in regime_probabilities.items()
                if isinstance(value, (int, float))
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        if ordered:
            summary = ", ".join(f"{name}={value:.0%}" for name, value in ordered)
            print(f"Regime probabilities: {summary}")
    execution_summary = dashboard.get("execution_summary", {})
    if isinstance(execution_summary, dict) and execution_summary:
        avg_quality = execution_summary.get("average_execution_quality_score")
        min_quality = execution_summary.get("min_execution_quality_score")
        buy_candidates = execution_summary.get("buy_candidates")
        summary = "Execution dashboard:"
        if isinstance(buy_candidates, (int, float)):
            summary += f" buys={int(buy_candidates)}"
        if isinstance(avg_quality, (int, float)):
            summary += f" avg_quality={float(avg_quality):.3f}"
        if isinstance(min_quality, (int, float)):
            summary += f" min_quality={float(min_quality):.3f}"
        print(summary)
    tradability_summary = dashboard.get("tradability_summary", {})
    if isinstance(tradability_summary, dict) and tradability_summary:
        blocked = tradability_summary.get("blocked_count")
        total = tradability_summary.get("total_decisions")
        classification = tradability_summary.get("cycle_classification")
        not_tradable = tradability_summary.get("not_currently_tradable")
        exchange_closed = tradability_summary.get("exchange_closed")
        buying_disabled = tradability_summary.get("buying_disabled")
        if isinstance(blocked, (int, float)) and blocked:
            summary = "Tradability:"
            if isinstance(classification, str):
                summary += f" {classification}"
            if isinstance(total, (int, float)):
                summary += f" blocked={int(blocked)}/{int(total)}"
            else:
                summary += f" blocked={int(blocked)}"
            if isinstance(not_tradable, (int, float)) and not_tradable:
                summary += f" not_tradable={int(not_tradable)}"
            if isinstance(exchange_closed, (int, float)) and exchange_closed:
                summary += f" exchange_closed={int(exchange_closed)}"
            if isinstance(buying_disabled, (int, float)) and buying_disabled:
                summary += f" buying_disabled={int(buying_disabled)}"
            print(summary)
    committee_summary = dashboard.get("committee_summary", {})
    if isinstance(committee_summary, dict) and committee_summary:
        reviewed = committee_summary.get("reviewed")
        total_decisions = committee_summary.get("total_decisions")
        automatic_holds = committee_summary.get("automatic_hold_approvals")
        avg_consensus = committee_summary.get("average_consensus")
        rejected = committee_summary.get("rejected_symbols", [])
        summary = "Decision committee:"
        if isinstance(reviewed, (int, float)):
            summary += f" trade_reviewed={int(reviewed)}"
        if isinstance(total_decisions, (int, float)):
            summary += f" total_decisions={int(total_decisions)}"
        if isinstance(automatic_holds, (int, float)) and automatic_holds:
            summary += f" auto_holds={int(automatic_holds)}"
        if isinstance(avg_consensus, (int, float)) and isinstance(reviewed, (int, float)) and reviewed:
            summary += f" avg_trade_consensus={float(avg_consensus):.3f}"
        elif isinstance(automatic_holds, (int, float)) and automatic_holds:
            summary += " avg_trade_consensus=n/a"
        if isinstance(rejected, list) and rejected:
            summary += f" rejected={','.join(str(symbol) for symbol in rejected[:5])}"
        print(summary)
    portfolio_risk = dashboard.get("portfolio_risk", {})
    if isinstance(portfolio_risk, dict) and portfolio_risk:
        var_95 = portfolio_risk.get("var_95_pct")
        cvar_95 = portfolio_risk.get("cvar_95_pct")
        expected_shortfall = portfolio_risk.get("expected_shortfall_95_pct")
        max_scenario = portfolio_risk.get("max_scenario_loss_pct")
        hhi = portfolio_risk.get("hhi")
        summary = "Portfolio risk:"
        if isinstance(var_95, (int, float)):
            summary += f" VaR95={float(var_95):.2%}"
        if isinstance(cvar_95, (int, float)):
            summary += f" CVaR95={float(cvar_95):.2%}"
        if isinstance(expected_shortfall, (int, float)):
            summary += f" ES95={float(expected_shortfall):.2%}"
        if isinstance(max_scenario, (int, float)):
            summary += f" stress={float(max_scenario):.2%}"
        if isinstance(hhi, (int, float)):
            summary += f" hhi={float(hhi):.3f}"
        print(summary)
    learning_summary = dashboard.get("learning_summary", {})
    if isinstance(learning_summary, dict) and learning_summary:
        samples = learning_summary.get("sample_count")
        win_rate = learning_summary.get("win_rate")
        avg_return = learning_summary.get("average_return")
        holding_days = learning_summary.get("average_holding_days")
        summary = "Closed-trade learning:"
        if isinstance(samples, (int, float)):
            summary += f" samples={int(samples)}"
        if isinstance(win_rate, (int, float)):
            summary += f" win_rate={float(win_rate):.2%}"
        if isinstance(avg_return, (int, float)):
            summary += f" avg_return={float(avg_return):.2%}"
        if isinstance(holding_days, (int, float)):
            summary += f" avg_hold={float(holding_days):.1f}d"
        print(summary)


def _print_report(summary: dict[str, object]) -> None:
    latest_risk = summary.get("latest_portfolio_risk", {})
    if isinstance(latest_risk, dict) and latest_risk:
        scenarios = latest_risk.get("scenarios_json", {})
        worst = ""
        if isinstance(scenarios, dict) and scenarios:
            name, loss = max(scenarios.items(), key=lambda item: float(item[1]))
            worst = f" worst={name} {float(loss):.2%}"
        print(
            f"Portfolio risk: VaR95={float(latest_risk.get('var_pct', 0.0)):.2%} "
            f"CVaR95={float(latest_risk.get('cvar_pct', 0.0)):.2%} "
            f"ES95={float(latest_risk.get('expected_shortfall_pct', 0.0)):.2%}{worst}"
        )
    latest_training = summary.get("latest_training", {})
    if isinstance(latest_training, dict) and latest_training:
        metrics = latest_training.get("metrics_json", {})
        print(
            f"Training: {latest_training.get('model_name')} version={latest_training.get('model_version')} "
            f"samples={latest_training.get('sample_count')} "
            f"metrics={metrics}"
        )
    model_versions = summary.get("model_versions", [])
    if isinstance(model_versions, list) and model_versions:
        print("Model registry:")
        for row in model_versions[:3]:
            print(
                f"  {row['model_version']} status={row['status']} "
                f"artifact={row['artifact_path']}"
            )
    executions = summary.get("recent_execution_simulations", [])
    if isinstance(executions, list) and executions:
        print("Recent execution simulations:")
        for row in executions[:5]:
            actual = ""
            if row.get("actual_slippage_bps") is not None:
                actual = f" actual={float(row['actual_slippage_bps']):.1f}bps"
            elif row.get("filled") is not None:
                actual = f" filled={bool(row['filled'])}"
            print(
                f"  {row['symbol']} {row['action']} quality={float(row['quality_score']):.3f} "
                f"slippage={float(row['expected_slippage_bps']):.1f}bps fill={float(row['fill_probability']):.2f}{actual}"
            )
    committee = summary.get("recent_committee_votes", [])
    if isinstance(committee, list) and committee:
        print("Recent committee votes:")
        for row in committee[:5]:
            print(
                f"  {row['symbol']} {row['final_action']} approved={bool(row['approved'])} "
                f"consensus={float(row['consensus_score']):.3f}"
            )
    news_sources = summary.get("recent_news_sources", [])
    if isinstance(news_sources, list) and news_sources:
        print("News credibility:")
        for row in news_sources[:5]:
            print(
                f"  {row['source']} mentions={row['mentions']} "
                f"credibility={float(row['credibility_score']):.2f} sentiment={float(row['avg_sentiment']):.2f}"
            )
    learned_news = summary.get("learned_news_credibility", [])
    if isinstance(learned_news, list) and learned_news:
        print("Learned source reliability:")
        for row in learned_news[:5]:
            print(
                f"  {row['source']} samples={row['sample_count']} "
                f"reliability={float(row['reliability_score']):.2f} "
                f"hit={float(row['hit_rate']):.2f} noise={float(row['noise_score']):.2f}"
            )


def _print_replay(replay) -> None:
    print(f"Replay as of: {replay.as_of}")
    if replay.symbol:
        print(f"Symbol: {replay.symbol}")
    print(
        f"Rows: features={len(replay.cycle_features)} decisions={len(replay.decisions)} "
        f"risk={len(replay.risk_checks)} orders={len(replay.orders)} news={len(replay.news_source_stats)}"
    )
    for row in replay.cycle_features[:5]:
        print(
            f"  feature {row['created_at']} {row['symbol']} {row['action']} "
            f"score={float(row['decision_score']):.3f} news={float(row['news_sentiment']):.2f} "
            f"regime={row['regime_name']} risk={row['risk_approved']}"
        )
    for row in replay.decisions[:5]:
        print(
            f"  decision {row['created_at']} {row['symbol']} {row['action']} "
            f"score={float(row['score']):.3f} confidence={float(row['confidence']):.3f}"
        )


def _regime_summary_line(result) -> str:
    for collection in (result.decisions, result.position_reviews):
        for item in collection:
            features = getattr(item, "features", {})
            regime_name = features.get("regime_name")
            if regime_name:
                confidence = features.get("regime_confidence", 0.0)
                stress = features.get("regime_stress_score", 0.0)
                multiplier = features.get("regime_size_multiplier", 1.0)
                return (
                    f"Market regime: {regime_name} "
                    f"confidence={float(confidence):.3f} stress={float(stress):.3f} size_multiplier={float(multiplier):.2f}"
                )
    return ""


def _run_doctor(config) -> None:
    print(f"Execution mode: {config.execution.normalized_mode()}")
    print(f"Execution environment: {config.execution.normalized_environment()}")
    print(f"eToro base URL: {config.secrets.etoro_base_url}")
    print(f"eToro user agent: {config.secrets.etoro_user_agent}")
    print(f"ETORO_API_KEY set: {bool(config.secrets.etoro_api_key)}")
    print(f"ETORO_USER_KEY set: {bool(config.secrets.etoro_user_key)}")

    if not config.secrets.etoro_api_key or not config.secrets.etoro_user_key:
        print("Missing eToro credentials in .env.")
        return

    client = EtoroClient(
        api_key=config.secrets.etoro_api_key,
        user_key=config.secrets.etoro_user_key,
        base_url=config.secrets.etoro_base_url,
        user_agent=config.secrets.etoro_user_agent,
    )
    try:
        identity = client.get_identity()
    except EtoroApiError as exc:
        _print_etoro_error(exc)
        return

    print("eToro authentication: OK")
    for key in ("gcid", "realCid", "demoCid", "username"):
        if key in identity:
            print(f"{key}: {identity[key]}")

    probe_symbol = config.universe.benchmark_symbol or next(iter(config.universe.symbols), "SPY")
    try:
        if probe_symbol.upper() in config.universe.instrument_ids:
            instrument_id = config.universe.instrument_ids[probe_symbol.upper()]
            print(f"Market-data search: skipped; using configured {probe_symbol} -> {instrument_id}")
        else:
            instrument = client.search_instrument(probe_symbol)
            if not instrument:
                print(f"Market-data search: no instrument found for {probe_symbol}")
                return
            instrument_id = instrument.instrument_id
            print(f"Market-data search: OK ({probe_symbol} -> instrumentId {instrument_id})")
        rates = client.get_rates([instrument_id])
        if instrument_id in rates:
            print("Market rates: OK")
        else:
            print("Market rates: no rate returned for probe instrument")
    except EtoroApiError as exc:
        print(f"Market-data check failed for {probe_symbol}.")
        _print_etoro_error(exc)

    if not config.universe.instrument_ids:
        print(
            "Tip: if eToro search is intermittent, add known IDs under [universe.instrument_ids] "
            "in config/strategy.toml."
        )


def _run_data_health(config) -> None:
    candles = load_cached_candles(config.universe.market_cache_path)
    minimum = max(
        config.strategy.previous_month_window + 1,
        config.strategy.slow_ma_period,
        config.strategy.volatility_window + 1,
        35,
    )
    ready = {symbol: items for symbol, items in candles.items() if len(items) >= minimum}
    print(f"Candle cache: {config.universe.market_cache_path}")
    print(f"Cached symbols: {len(candles)}")
    print(f"Chart-ready symbols: {len(ready)} / {len(candles)} (minimum candles: {minimum})")

    source_counts = _cache_source_counts(config.universe.market_cache_path)
    if source_counts:
        sources = ", ".join(f"{source}={count}" for source, count in sorted(source_counts.items()))
        print(f"Sources: {sources}")

    weak = sorted((symbol, len(items)) for symbol, items in candles.items() if len(items) < minimum)
    if weak:
        examples = ", ".join(f"{symbol}:{count}" for symbol, count in weak[:10])
        print(f"Needs backfill: {examples}")
        print("Run scan again to refresh these; the agent will try free public daily-history fallback.")


def _cache_source_counts(cache_path: str) -> Counter:
    path = Path(cache_path)
    if not path.exists():
        return Counter()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return Counter()
    counts: Counter = Counter()
    for candle_payload in payload.get("candles", {}).values():
        if isinstance(candle_payload, dict):
            counts[str(candle_payload.get("source", "unknown"))] += 1
    return counts


def _print_etoro_error(exc: EtoroApiError) -> None:
    print(f"eToro API error: {exc}")
    if isinstance(exc.payload, dict) and exc.payload.get("error_code") == 1010:
        print(
            "Cloudflare 1010 means the request was blocked before normal eToro API auth. "
            "This is usually caused by the HTTP client signature or an eToro/API access rule, "
            "not by the trading strategy."
        )
        print(
            "Try setting ETORO_USER_AGENT in .env to a clear app identifier, then rerun doctor. "
            "If it still returns 1010, contact eToro API support with the ray_id from the payload."
        )
        return
    if isinstance(exc.payload, dict) and exc.payload.get("error_code") == 1015:
        retry_after = exc.payload.get("retry_after", 30)
        print(
            f"Cloudflare 1015 means eToro is rate limiting this IP/session. "
            f"Wait at least {retry_after} seconds before retrying. The agent now scans fewer "
            "symbols per cycle and caches market metadata to reduce repeat calls."
        )
        return
    if exc.status == 401:
        print(
            "401 means the request reached eToro, but the API credentials were not accepted. "
            "Check ETORO_API_KEY and ETORO_USER_KEY for copy/paste mistakes, make sure the User Key "
            "was created for the Demo environment, and confirm it has Read permission for market data."
        )
        print(
            "If /me works in doctor but scan fails, the key likely lacks market-data access or your "
            "Public API app has not been approved for that endpoint."
        )
    if exc.status == 403:
        print(
            "403 usually means eToro rejected the API/user-key pair or its access rules. "
            "Check that the User Key was created for Demo, has Read permission, has not expired, "
            "and that any IP whitelist includes your current public IP."
        )
    if exc.payload:
        print(f"Response payload: {exc.payload}")


if __name__ == "__main__":
    main()

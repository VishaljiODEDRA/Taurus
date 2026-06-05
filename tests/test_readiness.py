from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.backtest import Backtester
from agent.calibration import ModelCalibrator
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
from agent.exits import ExitManager
from agent.ledger import Ledger
from agent.monitoring import HealthMonitor
from agent.metrics import calculate_metrics, readiness_pass, TradeRecord
from models import AgentCycleResult, Candle, Instrument, MarketSnapshot, NewsContext, PortfolioPosition, Rate


class ReadinessLayerTest(unittest.TestCase):
    def test_backtester_produces_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            result = Backtester(config).run(
                {
                    "AAPL": _candles(100, [0.003, -0.001, 0.004, 0.002, -0.001] * 30),
                    "SPY": _candles(100, [0.001, -0.001, 0.001, 0.001, 0.0] * 30),
                }
            )

            self.assertGreaterEqual(result.metrics.trades, 0)
            self.assertGreater(result.metrics.final_equity_usd, 0)

    def test_exit_manager_generates_stop_loss_sell(self) -> None:
        position = PortfolioPosition(
            symbol="AAPL",
            instrument_id=1,
            position_id="p1",
            units=1,
            invested_usd=100,
            current_value_usd=96,
            open_rate=100,
        )
        snapshot = MarketSnapshot(
            Instrument("AAPL", 1, "Stock"),
            Rate(1, bid=96, ask=96.1, last_execution=96, timestamp=datetime.now(tz=UTC)),
            _candles(100, [-0.004] * 40),
        )

        decision = ExitManager(ExitSettings(), StrategySettings()).evaluate(
            position,
            snapshot,
            NewsContext("AAPL"),
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "SELL")

    def test_calibrator_handles_insufficient_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
            result = ModelCalibrator(config, ledger).from_trade_outcomes()

            self.assertEqual(result.source, "trade_outcomes")
            self.assertEqual(result.sample_count, 0)

    def test_monitor_alerts_after_halted_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
            monitor = HealthMonitor(config.monitoring, config.risk, ledger)
            halted = AgentCycleResult(
                started_at=datetime.now(tz=UTC),
                finished_at=datetime.now(tz=UTC),
                decisions=(),
                risk_decisions=(),
                orders=(),
                halted=True,
                halt_reason="test",
            )

            alerts = []
            for _ in range(config.monitoring.max_halted_cycles):
                alerts = monitor.record_cycle(halted)

            self.assertTrue(alerts)

    def test_overfitting_defense_uses_deflated_sharpe_proxy(self) -> None:
        metrics = calculate_metrics(
            [
                TradeRecord("AAPL", "2024-01-01", "2024-01-02", 100, 101, 1000, 10, 0.01, "x", 1),
                TradeRecord("AAPL", "2024-01-03", "2024-01-04", 100, 101, 1000, 10, 0.01, "x", 1),
                TradeRecord("AAPL", "2024-01-05", "2024-01-06", 100, 101, 1000, 10, 0.01, "x", 1),
            ],
            [10_000, 10_010, 10_020, 10_030],
            initial_equity_usd=10_000,
            multiple_testing_penalty_trials=100,
        )

        self.assertLess(metrics.deflated_sharpe_proxy, metrics.sharpe)
        self.assertFalse(
            readiness_pass(
                metrics,
                min_trades=1,
                min_profit_factor=1.0,
                min_sharpe=0.0,
                max_drawdown_pct=1.0,
                min_deflated_sharpe_proxy=0.5,
            )
        )


def _config(tmp: str) -> AppConfig:
    return AppConfig(
        agent=AgentSettings(),
        execution=ExecutionSettings(mode="shadow", environment="demo"),
        universe=UniverseSettings(symbols=("AAPL", "SPY"), benchmark_symbol="SPY"),
        risk=RiskSettings(kill_switch_path=str(Path(tmp) / "KILL_SWITCH")),
        exits=ExitSettings(),
        monitoring=MonitoringSettings(
            max_halted_cycles=2,
            alert_log_path=str(Path(tmp) / "alerts.jsonl"),
            auto_kill_switch_on_breach=False,
        ),
        validation=ValidationSettings(min_backtest_trades=1),
        strategy=StrategySettings(buy_threshold=0.58),
        news=NewsSettings(enabled=False),
        storage=StorageSettings(
            sqlite_path=str(Path(tmp) / "ledger.sqlite3"),
            audit_log_path=str(Path(tmp) / "audit.jsonl"),
        ),
        secrets=Secrets(),
    )


def _candles(start: float, returns: list[float]) -> list[Candle]:
    now = datetime.now(tz=UTC)
    price = start
    candles = []
    for index, daily_return in enumerate(returns):
        close = price * (1 + daily_return)
        candles.append(
            Candle(
                timestamp=now - timedelta(days=len(returns) - index),
                open=price,
                high=max(price, close) * 1.01,
                low=min(price, close) * 0.99,
                close=close,
                volume=1_000_000 + index * 10_000,
            )
        )
        price = close
    return candles


if __name__ == "__main__":
    unittest.main()

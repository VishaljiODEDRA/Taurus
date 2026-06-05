from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.broker_sync import _closed_trade_from_history_item, broker_research_config
from agent.committee import DecisionCommittee
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
    StressScenarioSettings,
    UniverseSettings,
    ValidationSettings,
)
from agent.execution import ExecutionSimulator
from agent.ledger import Ledger
from agent.point_in_time import PointInTimeReplayer
from agent.portfolio import PortfolioRiskAnalyzer
from agent.training import WalkForwardModelTrainer
from models import Candle, Instrument, MarketSnapshot, NewsContext, NewsItem, PortfolioPosition, PortfolioState, Rate, SignalDecision


class InstitutionalLayersTest(unittest.TestCase):
    def test_broker_history_trade_import_parser_normalizes_closed_outcome(self) -> None:
        trade = _closed_trade_from_history_item(
            {
                "instrumentID": 1,
                "positionID": "p1",
                "openOrderID": "o1",
                "netProfit": 15.0,
                "investment": 500.0,
                "openDate": "2026-05-01T10:00:00Z",
                "closeDate": "2026-05-04T10:00:00Z",
                "status": "closed",
            },
            {1: "AAPL"},
        )

        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(trade["symbol"], "AAPL")
        self.assertAlmostEqual(trade["return_pct"], 0.03)
        self.assertEqual(trade["holding_days"], 3)
        self.assertEqual(trade["entry_order_id"], "o1")

    def test_broker_research_config_uses_latest_account_nav(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            ledger.record_broker_account_snapshot(
                environment="demo",
                nav_usd=12_345.67,
                available_cash_usd=10_000.0,
                daily_pnl_pct=0.0,
                rolling_drawdown_pct=0.0,
                gross_exposure_pct=0.1,
                open_positions=2,
            )

            config, note = broker_research_config(
                AppConfig(
                    agent=AgentSettings(),
                    execution=ExecutionSettings(mode="shadow", environment="demo"),
                    universe=UniverseSettings(),
                    risk=RiskSettings(),
                    exits=ExitSettings(),
                    monitoring=MonitoringSettings(),
                    validation=ValidationSettings(),
                    strategy=StrategySettings(),
                    news=NewsSettings(),
                    storage=StorageSettings(),
                    secrets=Secrets(),
                ),
                ledger,
            )

            self.assertAlmostEqual(config.validation.backtest_initial_cash_usd, 12_345.67)
            self.assertIn("broker NAV", note)

    def test_ledger_records_normalized_feature_and_training_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            snapshot_id = ledger.record_feature_snapshot(
                symbol="AAPL",
                action="BUY",
                score=0.82,
                confidence=0.76,
                features={"score": 0.82, "reasoning_summary": "Momentum is constructive."},
            )
            cycle_feature_id = ledger.record_cycle_features(
                {
                    "cycle_id": "cycle-1",
                    "symbol": "AAPL",
                    "benchmark_symbol": "SPY",
                    "action": "BUY",
                    "is_trade": True,
                    "decision_score": 0.82,
                    "decision_confidence": 0.76,
                    "symbol_last_price": 190.0,
                    "symbol_spread_bps": 4.0,
                    "symbol_return_21d_pct": 0.05,
                    "benchmark_return_21d_pct": 0.02,
                    "relative_strength_21d": 0.03,
                    "news_sentiment": 0.2,
                    "news_catalyst": 0.5,
                    "news_item_count": 3,
                    "news_source_count": 2,
                    "regime_name": "bullish",
                    "regime_confidence": 0.8,
                    "regime_bullish_probability": 0.7,
                    "allocation_approved": True,
                    "allocation_target_notional_usd": 500,
                    "timing_confidence": 0.65,
                    "execution_quality_score": 0.88,
                    "expected_slippage_bps": 3.5,
                    "fill_probability": 0.95,
                    "committee_approved": True,
                    "committee_consensus_score": 0.74,
                    "risk_approved": True,
                    "risk_target_notional_usd": 500,
                    "raw_features": {"score": 0.82},
                }
            )
            ledger.record_trade_outcome(
                symbol="AAPL",
                pnl_usd=12.5,
                return_pct=0.025,
                holding_days=3,
                source="unit_test",
                raw={
                    "entry_context": {"features_json": {"score": 0.82, "meta_approval_score": 0.70}},
                    "exit_features": {"score": 0.45},
                },
            )

            self.assertGreater(snapshot_id, 0)
            self.assertGreater(cycle_feature_id, 0)
            self.assertEqual(len(ledger.latest_feature_snapshots(limit=5)), 1)
            cycle_rows = ledger.latest_cycle_features(limit=5)
            self.assertGreaterEqual(len(cycle_rows), 1)
            self.assertEqual(cycle_rows[-1]["symbol"], "AAPL")
            self.assertAlmostEqual(cycle_rows[-1]["relative_strength_21d"], 0.03)
            examples = ledger.training_examples(limit=5)
            self.assertEqual(len(examples), 1)
            self.assertEqual(examples[0]["label"], 1)
            self.assertEqual(len(ledger.cycle_feature_training_rows(limit=5)), 1)

    def test_walk_forward_trainer_records_model_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            for index in range(36):
                label = 1 if index % 3 != 0 else 0
                score = 0.72 if label else 0.38
                ledger.record_training_example(
                    symbol="AAPL",
                    label=label,
                    return_pct=0.02 if label else -0.01,
                    pnl_usd=10 if label else -5,
                    holding_days=2,
                    source="unit_test",
                    entry_features={"score": score, "meta_approval_score": score},
                    exit_features={},
                )
                ledger.record_cycle_features(
                    {
                        "cycle_id": f"cycle-{index}",
                        "symbol": "AAPL",
                        "benchmark_symbol": "SPY",
                        "action": "OUTCOME",
                        "is_trade": True,
                        "decision_score": score,
                        "decision_confidence": score,
                        "news_sentiment": 0.1 if label else -0.1,
                        "news_catalyst": 0.4 if label else 0.1,
                        "regime_confidence": 0.7,
                        "execution_quality_score": 0.8 if label else 0.45,
                        "committee_consensus_score": score,
                        "outcome_label": label,
                        "outcome_return_pct": 0.02 if label else -0.01,
                        "outcome_pnl_usd": 10 if label else -5,
                        "outcome_holding_days": 2,
                    }
                )

            result = WalkForwardModelTrainer(ledger).train(min_samples=10)

            self.assertEqual(result.metrics["status"], "trained")
            self.assertGreaterEqual(result.sample_count, 36)
            self.assertNotEqual(result.model_version, "untrained")
            self.assertTrue(Path(result.artifact_path).exists())
            self.assertGreaterEqual(result.metrics["walk_forward"]["windows"], 1)
            self.assertIn("holdout", result.metrics)
            self.assertEqual(len(ledger.latest_model_training_runs(limit=5)), 1)
            versions = ledger.latest_model_versions(limit=5)
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0]["model_version"], result.model_version)

    def test_point_in_time_replay_and_training_cutoff_exclude_future_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            cutoff = "2026-05-15T10:00:00+00:00"
            for index, created_at in enumerate(
                (
                    "2026-05-15T09:00:00+00:00",
                    "2026-05-15T09:30:00+00:00",
                    "2026-05-15T11:00:00+00:00",
                )
            ):
                ledger.record_cycle_features(
                    {
                        "created_at": created_at,
                        "cycle_id": f"cycle-{index}",
                        "symbol": "AAPL",
                        "benchmark_symbol": "SPY",
                        "action": "OUTCOME",
                        "is_trade": True,
                        "decision_score": 0.8 if index < 2 else 0.1,
                        "decision_confidence": 0.7,
                        "news_sentiment": 0.2,
                        "news_catalyst": 0.4,
                        "regime_name": "bullish",
                        "regime_confidence": 0.8,
                        "execution_quality_score": 0.9,
                        "committee_consensus_score": 0.75,
                        "outcome_label": 1 if index < 2 else 0,
                        "outcome_return_pct": 0.02 if index < 2 else -0.05,
                        "outcome_pnl_usd": 10 if index < 2 else -25,
                        "outcome_holding_days": 2,
                    }
                )

            replay = PointInTimeReplayer(ledger).replay(cutoff, symbol="AAPL", limit=10)
            rows = ledger.cycle_feature_training_rows(as_of=cutoff, limit=10)
            result = WalkForwardModelTrainer(ledger).train(min_samples=3, as_of=cutoff)

            self.assertEqual(len(replay.cycle_features), 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(result.metrics["status"], "insufficient_samples")
            self.assertEqual(result.sample_count, 2)

    def test_portfolio_risk_analyzer_returns_var_cvar_and_scenarios(self) -> None:
        analyzer = PortfolioRiskAnalyzer(
            RiskSettings(),
            StrategySettings(),
            UniverseSettings(
                symbols=("AAPL", "XOM", "SPY", "TLT", "UUP", "GLD", "BTC-USD"),
                sector_map={"AAPL": "technology", "XOM": "energy"},
            ),
        )
        portfolio = PortfolioState(
            nav_usd=10_000,
            available_cash_usd=7_000,
            positions=(
                PortfolioPosition("AAPL", 1, "p1", 1, 2_000, 2_200),
                PortfolioPosition("XOM", 2, "p2", 1, 800, 900),
            ),
        )
        snapshots = {
            "AAPL": _snapshot("AAPL", 100, [0.004, -0.002, 0.003, -0.006] * 20),
            "XOM": _snapshot("XOM", 90, [0.003, -0.001, 0.004, -0.002] * 20),
            "SPY": _snapshot("SPY", 100, [0.002, -0.001, 0.002, -0.003] * 20),
            "TLT": _snapshot("TLT", 95, [-0.001, 0.002, -0.001, 0.002] * 20),
            "UUP": _snapshot("UUP", 30, [0.001, -0.001, 0.001, -0.001] * 20),
            "GLD": _snapshot("GLD", 180, [0.001, 0.002, -0.001, 0.002] * 20),
            "BTC-USD": _snapshot("BTC-USD", 60_000, [0.01, -0.015, 0.012, -0.008] * 20),
        }

        report = analyzer.evaluate(
            portfolio=portfolio,
            all_snapshots=snapshots,
            benchmark_symbol="SPY",
            market_regime=None,
        )

        self.assertGreaterEqual(report.var_95_pct, 0.0)
        self.assertGreaterEqual(report.cvar_95_pct, report.var_95_pct)
        self.assertGreaterEqual(report.expected_shortfall_95_pct, report.var_95_pct)
        self.assertGreaterEqual(report.expected_shortfall_95_usd, 0.0)
        self.assertGreaterEqual(report.var_99_pct, report.var_95_pct)
        self.assertIn("AAPL", report.component_expected_shortfall)
        self.assertIn("XOM", report.marginal_expected_shortfall)
        self.assertIn("risk_off_crash", report.scenario_losses)
        self.assertIn("cpi_shock", report.scenario_losses)
        self.assertIn("broker_spread_widening", report.scenario_losses)
        self.assertIn("market_beta", report.factor_exposures)
        self.assertIn("sector_beta", report.factor_exposures)
        self.assertIn("volatility_beta", report.factor_exposures)
        self.assertIn("rates_sensitivity", report.factor_exposures)
        self.assertIn("usd_sensitivity", report.factor_exposures)
        self.assertIn("commodity_sensitivity", report.factor_exposures)
        self.assertIn("crypto_correlation", report.factor_exposures)
        self.assertIn("idiosyncratic_volatility", report.factor_exposures)
        self.assertIn("sector_exposure_technology", report.factor_exposures)
        self.assertIn("sector_beta_energy", report.factor_exposures)

    def test_configured_scenario_book_overrides_default_scenarios(self) -> None:
        analyzer = PortfolioRiskAnalyzer(
            RiskSettings(
                scenarios=(
                    StressScenarioSettings(
                        name="custom_broker_spread_test",
                        benchmark_shock_pct=0.01,
                        spread_widening_bps=100,
                    ),
                )
            ),
            StrategySettings(),
            UniverseSettings(symbols=("AAPL", "SPY"), sector_map={"AAPL": "technology"}),
        )
        portfolio = PortfolioState(
            nav_usd=10_000,
            available_cash_usd=8_000,
            positions=(PortfolioPosition("AAPL", 1, "p1", 1, 1_000, 1_100),),
        )
        snapshots = {
            "AAPL": _snapshot("AAPL", 100, [0.002, -0.001] * 40),
            "SPY": _snapshot("SPY", 100, [0.001, -0.001] * 40),
        }

        report = analyzer.evaluate(
            portfolio=portfolio,
            all_snapshots=snapshots,
            benchmark_symbol="SPY",
            market_regime=None,
        )

        self.assertEqual(set(report.scenario_losses), {"custom_broker_spread_test"})
        self.assertGreater(report.scenario_losses["custom_broker_spread_test"], 0.0)

    def test_committee_and_execution_simulation_attach_auditable_scores(self) -> None:
        decision = SignalDecision(
            "AAPL",
            "BUY",
            confidence=0.8,
            score=0.82,
            features={
                "meta_approval_score": 0.76,
                "market_regime_strength": 0.7,
                "allocation_diversification_score": 0.8,
                "news_catalyst": 0.3,
                "timing_confidence": 0.7,
            },
        )
        portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=8_000)
        simulation = ExecutionSimulator().simulate(
            decision=decision,
            snapshot=_snapshot("AAPL", 100, [0.002] * 40),
            portfolio=portfolio,
            target_notional_usd=500,
        )
        committee_decision = DecisionCommittee().evaluate(
            SignalDecision(
                decision.symbol,
                decision.action,
                decision.confidence,
                decision.score,
                features={**decision.features, **simulation.as_features()},
            )
        )

        self.assertGreater(simulation.quality_score, 0.0)
        self.assertIn("execution_simulation_id", simulation.as_features())
        self.assertGreaterEqual(committee_decision.consensus_score, 0.0)
        self.assertEqual(len(committee_decision.votes), 7)

    def test_execution_simulator_learns_from_actual_fill_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            decision = SignalDecision("AAPL", "BUY", confidence=0.8, score=0.82)
            portfolio = PortfolioState(nav_usd=10_000, available_cash_usd=8_000)
            snapshot = _snapshot("AAPL", 100, [0.002] * 40)
            first = ExecutionSimulator().simulate(
                decision=decision,
                snapshot=snapshot,
                portfolio=portfolio,
                target_notional_usd=500,
            )
            ledger.record_execution_simulation(
                simulation_id=first.simulation_id,
                symbol=first.symbol,
                action=first.action,
                quality_score=first.quality_score,
                expected_slippage_bps=first.expected_slippage_bps,
                fill_probability=first.fill_probability,
                target_notional_usd=first.target_notional_usd,
                raw=first.as_dict(),
            )
            ledger.record_execution_actual(
                simulation_id=first.simulation_id,
                filled=True,
                actual_fill_price=first.reference_price * 1.012,
                actual_slippage_bps=120.0,
                raw={"source": "unit_test"},
            )
            profile = ledger.execution_slippage_profile(symbol="AAPL", action="BUY")
            second = ExecutionSimulator().simulate(
                decision=decision,
                snapshot=snapshot,
                portfolio=portfolio,
                target_notional_usd=500,
                historical_profile=profile,
            )

            self.assertEqual(profile["sample_count"], 1)
            self.assertGreater(second.expected_slippage_bps, first.expected_slippage_bps)
            self.assertGreater(second.historical_slippage_bps, 0.0)

    def test_ledger_records_structured_cycle_data_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            snapshot = _snapshot("AAPL", 100, [0.002] * 40)
            portfolio = PortfolioState(
                nav_usd=10_000,
                available_cash_usd=9_000,
                positions=(
                    PortfolioPosition(
                        symbol="AAPL",
                        instrument_id=1,
                        position_id="p1",
                        units=1,
                        invested_usd=100,
                        current_value_usd=105,
                        pnl_usd=5,
                        open_rate=100,
                    ),
                ),
            )
            regime = type(
                "Regime",
                (),
                {
                    "name": "bullish",
                    "confidence": 0.7,
                    "stress_score": 0.2,
                    "size_multiplier": 1.0,
                    "summary": "test regime",
                    "probabilities": {"bullish": 0.7},
                    "features": {"regime_confidence": 0.7},
                },
            )()
            ledger.record_cycle_data_history(
                cycle_id="cycle-1",
                snapshots={"AAPL": snapshot},
                contexts={
                    "AAPL": NewsContext(
                        "AAPL",
                        sentiment_score=0.4,
                        catalyst_score=0.6,
                        items=(NewsItem(title="Apple raises guidance", source="reuters.com", symbols=("AAPL",)),),
                    )
                },
                portfolio=portfolio,
                market_regime=regime,
            )

            history = ledger.latest_cycle_data_history(cycle_id="cycle-1")

            self.assertEqual(history["market_snapshots"][0]["symbol"], "AAPL")
            self.assertEqual(len(history["news_items"]), 1)
            self.assertEqual(history["positions"][0]["symbol"], "AAPL")
            self.assertEqual(history["regime"]["name"], "bullish")


def _snapshot(symbol: str, start: float, daily_returns: list[float]) -> MarketSnapshot:
    now = datetime.now(tz=UTC)
    candles: list[Candle] = []
    price = start
    for index, daily_return in enumerate(daily_returns):
        close = price * (1 + daily_return)
        candles.append(
            Candle(
                timestamp=now - timedelta(days=len(daily_returns) - index),
                open=price,
                high=max(price, close) * 1.01,
                low=min(price, close) * 0.99,
                close=close,
                volume=2_000_000 + index * 10_000,
            )
        )
        price = close
    return MarketSnapshot(
        Instrument(symbol=symbol, instrument_id=1, asset_type="Stock"),
        Rate(1, bid=price * 0.999, ask=price * 1.001, last_execution=price, timestamp=now),
        candles,
    )


if __name__ == "__main__":
    unittest.main()

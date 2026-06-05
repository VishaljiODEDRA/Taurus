from __future__ import annotations

from dataclasses import dataclass, replace

from agent.backtest import Backtester
from agent.config import AppConfig
from agent.ledger import Ledger
from agent.metrics import PerformanceMetrics
from models import Candle


@dataclass(frozen=True)
class CalibrationResult:
    source: str
    sample_count: int
    suggested_buy_threshold: float
    suggested_sell_threshold: float
    metrics: dict


class ModelCalibrator:
    def __init__(self, config: AppConfig, ledger: Ledger) -> None:
        self.config = config
        self.ledger = ledger

    def from_trade_outcomes(self, *, as_of: str | None = None) -> CalibrationResult:
        outcomes = (
            self.ledger.trade_outcomes_as_of(as_of, limit=500)
            if as_of
            else self.ledger.trade_outcomes(limit=500)
        )
        sample_count = len(outcomes)
        current_buy = self.config.strategy.buy_threshold
        current_sell = self.config.strategy.sell_threshold
        if sample_count < self.config.validation.calibration_min_samples:
            result = CalibrationResult(
                source="trade_outcomes",
                sample_count=sample_count,
                suggested_buy_threshold=current_buy,
                suggested_sell_threshold=current_sell,
                metrics={"status": "insufficient_samples", "as_of": as_of},
            )
            self._record(result)
            return result

        returns = [float(row["return_pct"]) for row in outcomes]
        win_rate = sum(1 for value in returns if value > 0) / len(returns)
        average_return = sum(returns) / len(returns)
        adjustment = 0.0
        if win_rate < 0.48 or average_return < 0:
            adjustment = 0.03
        elif win_rate > 0.56 and average_return > 0.004:
            adjustment = -0.02

        result = CalibrationResult(
            source="trade_outcomes",
            sample_count=sample_count,
            suggested_buy_threshold=_clamp(current_buy + adjustment, 0.55, 0.85),
            suggested_sell_threshold=current_sell,
            metrics={"win_rate": win_rate, "average_return": average_return, "as_of": as_of},
        )
        self._record(result)
        return result

    def from_backtest(
        self,
        candles_by_symbol: dict[str, list[Candle]],
        *,
        as_of: str | None = None,
    ) -> CalibrationResult:
        if as_of:
            candles_by_symbol = _candles_as_of(candles_by_symbol, as_of)
        candidates = [0.58, 0.62, 0.66, 0.70, 0.72, 0.75, 0.78, 0.82]
        best_threshold = self.config.strategy.buy_threshold
        best_metrics: PerformanceMetrics | None = None
        best_score = float("-inf")

        for threshold in candidates:
            strategy = replace(self.config.strategy, buy_threshold=threshold)
            cfg = replace(self.config, strategy=strategy)
            result = Backtester(cfg).run(candles_by_symbol)
            metrics = result.metrics
            if metrics.trades < max(2, self.config.validation.min_backtest_trades // 2):
                continue
            score = (
                metrics.total_return_pct
                + 0.04 * metrics.profit_factor
                + 0.02 * metrics.deflated_sharpe_proxy
                + metrics.max_drawdown_pct
            )
            if score > best_score:
                best_score = score
                best_threshold = threshold
                best_metrics = metrics

        metrics_dict = best_metrics.as_dict() if best_metrics else {"status": "insufficient_backtest_trades"}
        metrics_dict["as_of"] = as_of
        result = CalibrationResult(
            source="simulated_backtest_threshold_search",
            sample_count=int(metrics_dict.get("trades", 0)) if isinstance(metrics_dict.get("trades", 0), int) else 0,
            suggested_buy_threshold=best_threshold,
            suggested_sell_threshold=self.config.strategy.sell_threshold,
            metrics=metrics_dict,
        )
        self._record(result)
        return result

    def _record(self, result: CalibrationResult) -> None:
        self.ledger.record_calibration(
            source=result.source,
            sample_count=result.sample_count,
            suggested_buy_threshold=result.suggested_buy_threshold,
            suggested_sell_threshold=result.suggested_sell_threshold,
            metrics=result.metrics,
        )


def _clamp(value: float, low: float, high: float) -> float:
    return max(min(value, high), low)


def _candles_as_of(candles_by_symbol: dict[str, list[Candle]], as_of: str) -> dict[str, list[Candle]]:
    cutoff = _parse_as_of(as_of)
    return {
        symbol: [candle for candle in candles if candle.timestamp <= cutoff]
        for symbol, candles in candles_by_symbol.items()
    }


def _parse_as_of(value: str):
    from datetime import UTC, datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

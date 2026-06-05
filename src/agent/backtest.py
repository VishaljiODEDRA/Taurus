from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent.config import AppConfig
from agent.metrics import PerformanceMetrics, TradeRecord, calculate_metrics, readiness_pass
from agent.signals import SignalEngine
from models import Candle, Instrument, MarketSnapshot, NewsContext, Rate


@dataclass
class SimPosition:
    symbol: str
    entry_index: int
    entry_time: str
    entry_price: float
    notional_usd: float
    shares: float
    highest_price: float
    fill_ratio: float = 1.0


@dataclass(frozen=True)
class BacktestResult:
    metrics: PerformanceMetrics
    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[float, ...]
    readiness_passed: bool


class Backtester:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.signal_engine = SignalEngine(config.strategy, config.universe)

    def run(self, candles_by_symbol: dict[str, list[Candle]]) -> BacktestResult:
        data = {
            symbol.upper(): sorted(candles, key=lambda candle: candle.timestamp)
            for symbol, candles in candles_by_symbol.items()
            if len(candles) >= self.config.strategy.slow_ma_period + 2
        }
        if not data:
            return _empty_result(self.config.validation.backtest_initial_cash_usd)

        min_length = min(len(candles) for candles in data.values())
        warmup = max(self.config.strategy.slow_ma_period, self.config.strategy.previous_month_window) + 1
        if min_length <= warmup + 1:
            return _empty_result(self.config.validation.backtest_initial_cash_usd)

        cash = self.config.validation.backtest_initial_cash_usd
        positions: dict[str, SimPosition] = {}
        trades: list[TradeRecord] = []
        equity_curve: list[float] = [cash]
        benchmark = self.config.universe.benchmark_symbol.upper()

        for index in range(warmup, min_length):
            closes = {symbol: candles[index].close for symbol, candles in data.items()}
            cash, closed = self._process_exits(index, data, positions, closes, cash)
            trades.extend(closed)

            snapshots = _snapshots_at(data, index)
            if benchmark not in snapshots and data:
                snapshots[benchmark] = next(iter(snapshots.values()))
            contexts = {symbol: NewsContext(symbol=symbol) for symbol in snapshots}
            decisions = self.signal_engine.rank(snapshots, contexts)

            slots = max(self.config.risk.max_positions - len(positions), 0)
            for decision in decisions:
                if slots <= 0:
                    break
                if decision.action != "BUY" or decision.symbol in positions or decision.symbol not in data:
                    continue
                close = data[decision.symbol][index].close
                if close <= 0:
                    continue
                nav = cash + _open_value(positions, closes)
                notional = min(
                    nav * self.config.validation.backtest_position_pct_nav,
                    cash * 0.95,
                )
                if notional < self.config.risk.min_order_usd:
                    continue
                candle = data[decision.symbol][index]
                fill_ratio = _realistic_fill_ratio(candle, notional)
                if fill_ratio < 0.35:
                    continue
                filled_notional = notional * fill_ratio
                slippage_bps = _realistic_slippage_bps(candle, self.config.validation.backtest_slippage_bps, filled_notional)
                entry_price = _apply_buy_cost(close, slippage_bps)
                fee = filled_notional * self.config.validation.backtest_fee_bps / 10_000
                shares = max((filled_notional - fee) / entry_price, 0.0)
                if shares <= 0:
                    continue
                cash -= filled_notional
                positions[decision.symbol] = SimPosition(
                    symbol=decision.symbol,
                    entry_index=index,
                    entry_time=candle.timestamp.isoformat(),
                    entry_price=entry_price,
                    notional_usd=filled_notional,
                    shares=shares,
                    highest_price=entry_price,
                    fill_ratio=fill_ratio,
                )
                slots -= 1

            equity_curve.append(cash + _open_value(positions, closes))

        final_index = min_length - 1
        final_closes = {symbol: candles[final_index].close for symbol, candles in data.items()}
        for symbol in list(positions):
            trade, cash = self._close_position(
                positions.pop(symbol),
                data[symbol][final_index],
                cash,
                "end_of_backtest",
            )
            trades.append(trade)
        equity_curve.append(cash + _open_value(positions, final_closes))

        metrics = calculate_metrics(
            trades,
            equity_curve,
            initial_equity_usd=self.config.validation.backtest_initial_cash_usd,
            multiple_testing_penalty_trials=self.config.validation.multiple_testing_penalty_trials,
        )
        return BacktestResult(
            metrics=metrics,
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            readiness_passed=readiness_pass(
                metrics,
                min_trades=self.config.validation.min_backtest_trades,
                min_profit_factor=self.config.validation.min_profit_factor,
                min_sharpe=self.config.validation.min_sharpe,
                max_drawdown_pct=self.config.validation.max_backtest_drawdown_pct,
                min_deflated_sharpe_proxy=self.config.validation.min_deflated_sharpe_proxy,
            ),
        )

    def _process_exits(
        self,
        index: int,
        data: dict[str, list[Candle]],
        positions: dict[str, SimPosition],
        closes: dict[str, float],
        cash: float,
    ) -> tuple[float, list[TradeRecord]]:
        trades: list[TradeRecord] = []
        for symbol, position in list(positions.items()):
            candle = data[symbol][index]
            position.highest_price = max(position.highest_price, candle.high)
            exit_reason = self._exit_reason(position, candle, index)
            if not exit_reason:
                continue
            trade, cash = self._close_position(positions.pop(symbol), candle, cash, exit_reason)
            trades.append(trade)
        return cash, trades

    def _exit_reason(self, position: SimPosition, candle: Candle, index: int) -> str | None:
        if candle.low <= position.entry_price * (1 - self.config.exits.hard_stop_loss_pct):
            return "stop_loss"
        if candle.high >= position.entry_price * (1 + self.config.exits.take_profit_pct):
            return "take_profit"
        if candle.close <= position.highest_price * (1 - self.config.exits.trailing_stop_pct):
            return "trailing_stop"
        if index - position.entry_index >= self.config.validation.backtest_max_holding_days:
            return "max_holding_days"
        return None

    def _close_position(
        self,
        position: SimPosition,
        candle: Candle,
        cash: float,
        reason: str,
    ) -> tuple[TradeRecord, float]:
        slippage_bps = _realistic_slippage_bps(candle, self.config.validation.backtest_slippage_bps, position.notional_usd)
        exit_price = _apply_sell_cost(candle.close, slippage_bps)
        gross_value = position.shares * exit_price
        fee = gross_value * self.config.validation.backtest_fee_bps / 10_000
        net_value = gross_value - fee
        pnl = net_value - position.notional_usd
        cash += net_value
        trade = TradeRecord(
            symbol=position.symbol,
            entry_time=position.entry_time,
            exit_time=candle.timestamp.isoformat(),
            entry_price=position.entry_price,
            exit_price=exit_price,
            notional_usd=position.notional_usd,
            pnl_usd=pnl,
            return_pct=pnl / position.notional_usd if position.notional_usd else 0.0,
            reason=reason,
            holding_days=max(0, (candle.timestamp.date() - datetime.fromisoformat(position.entry_time).date()).days),
        )
        return trade, cash


class WalkForwardValidator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(self, candles_by_symbol: dict[str, list[Candle]]) -> list[BacktestResult]:
        lengths = [len(candles) for candles in candles_by_symbol.values()]
        if not lengths:
            return []
        min_length = min(lengths)
        train = self.config.validation.walk_forward_train_days
        test = self.config.validation.walk_forward_test_days
        step = self.config.validation.walk_forward_step_days
        results: list[BacktestResult] = []
        start = 0
        while start + train + test <= min_length:
            test_start = start + train
            test_end = test_start + test
            sliced = {
                symbol: candles[max(0, test_start - self.config.strategy.slow_ma_period - 25) : test_end]
                for symbol, candles in candles_by_symbol.items()
            }
            results.append(Backtester(self.config).run(sliced))
            start += step
        return results


def load_cached_candles(cache_path: str) -> dict[str, list[Candle]]:
    path = Path(cache_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    candles_by_symbol: dict[str, list[Candle]] = {}
    instruments = payload.get("instruments", {})
    id_to_symbol = {
        str(value.get("instrument_id")): symbol
        for symbol, value in instruments.items()
        if isinstance(value, dict) and value.get("instrument_id") is not None
    }
    for key, candle_payload in payload.get("candles", {}).items():
        instrument_id = key.split(":", 1)[0]
        symbol = id_to_symbol.get(instrument_id, instrument_id)
        items = candle_payload.get("items", []) if isinstance(candle_payload, dict) else []
        candles = [_candle_from_cache(item) for item in items if isinstance(item, dict)]
        if candles:
            candles_by_symbol[symbol] = candles
    return candles_by_symbol


def _snapshots_at(data: dict[str, list[Candle]], index: int) -> dict[str, MarketSnapshot]:
    snapshots: dict[str, MarketSnapshot] = {}
    for offset, (symbol, candles) in enumerate(data.items(), start=1):
        window = candles[: index + 1]
        candle = candles[index]
        rate = Rate(
            instrument_id=offset,
            bid=candle.close * 0.999,
            ask=candle.close * 1.001,
            last_execution=candle.close,
            timestamp=candle.timestamp,
        )
        instrument = Instrument(symbol=symbol, instrument_id=offset, asset_type="Stock")
        snapshots[symbol] = MarketSnapshot(instrument, rate, window)
    return snapshots


def _open_value(positions: dict[str, SimPosition], closes: dict[str, float]) -> float:
    return sum(position.shares * closes.get(symbol, position.entry_price) for symbol, position in positions.items())


def _apply_buy_cost(price: float, slippage_bps: float) -> float:
    return price * (1 + slippage_bps / 10_000)


def _apply_sell_cost(price: float, slippage_bps: float) -> float:
    return price * (1 - slippage_bps / 10_000)


def _realistic_slippage_bps(candle: Candle, base_slippage_bps: float, notional_usd: float) -> float:
    range_bps = ((candle.high - candle.low) / max(candle.close, 0.01)) * 10_000
    dollar_volume = max(candle.close * candle.volume, 1.0)
    size_impact_bps = (notional_usd / dollar_volume) * 10_000
    liquidity_shock = 12.0 if dollar_volume < 25_000_000 else 0.0
    volatility_shock = min(range_bps * 0.08, 35.0)
    return min(base_slippage_bps + volatility_shock + size_impact_bps + liquidity_shock, 120.0)


def _realistic_fill_ratio(candle: Candle, notional_usd: float) -> float:
    dollar_volume = max(candle.close * candle.volume, 1.0)
    participation = notional_usd / dollar_volume
    range_pct = (candle.high - candle.low) / max(candle.close, 0.01)
    liquidity_score = max(0.0, 1.0 - participation * 80)
    stability_score = max(0.45, 1.0 - range_pct * 8)
    return max(min(liquidity_score * stability_score, 1.0), 0.0)


def _candle_from_cache(item: dict) -> Candle:
    timestamp = datetime.fromisoformat(str(item["timestamp"]))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return Candle(
        timestamp=timestamp.astimezone(UTC),
        open=float(item["open"]),
        high=float(item["high"]),
        low=float(item["low"]),
        close=float(item["close"]),
        volume=float(item.get("volume", 0.0)),
    )


def _empty_result(initial_cash: float) -> BacktestResult:
    metrics = calculate_metrics([], [initial_cash], initial_equity_usd=initial_cash)
    return BacktestResult(metrics=metrics, trades=(), equity_curve=(initial_cash,), readiness_passed=False)

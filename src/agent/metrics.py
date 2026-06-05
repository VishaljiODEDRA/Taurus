from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    notional_usd: float
    pnl_usd: float
    return_pct: float
    reason: str
    holding_days: int


@dataclass(frozen=True)
class PerformanceMetrics:
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_return_pct: float
    average_trade_return_pct: float
    expectancy_pct: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    deflated_sharpe_proxy: float
    final_equity_usd: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "total_return_pct": self.total_return_pct,
            "average_trade_return_pct": self.average_trade_return_pct,
            "expectancy_pct": self.expectancy_pct,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "deflated_sharpe_proxy": self.deflated_sharpe_proxy,
            "final_equity_usd": self.final_equity_usd,
        }


def calculate_metrics(
    trades: list[TradeRecord],
    equity_curve: list[float],
    *,
    initial_equity_usd: float,
    multiple_testing_penalty_trials: int = 1,
) -> PerformanceMetrics:
    wins = [trade for trade in trades if trade.pnl_usd > 0]
    losses = [trade for trade in trades if trade.pnl_usd <= 0]
    returns = [trade.return_pct for trade in trades]
    gross_profit = sum(trade.pnl_usd for trade in wins)
    gross_loss = abs(sum(trade.pnl_usd for trade in losses))
    final_equity = equity_curve[-1] if equity_curve else initial_equity_usd
    downside = [value for value in returns if value < 0]
    return PerformanceMetrics(
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        total_return_pct=(final_equity - initial_equity_usd) / initial_equity_usd
        if initial_equity_usd > 0
        else 0.0,
        average_trade_return_pct=sum(returns) / len(returns) if returns else 0.0,
        expectancy_pct=sum(returns) / len(returns) if returns else 0.0,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        max_drawdown_pct=_max_drawdown(equity_curve),
        sharpe=_ratio(returns),
        sortino=_ratio(returns, downside_only=True),
        deflated_sharpe_proxy=_deflated_sharpe_proxy(
            _ratio(returns),
            returns,
            multiple_testing_penalty_trials,
        ),
        final_equity_usd=final_equity,
    )


def readiness_pass(
    metrics: PerformanceMetrics,
    *,
    min_trades: int,
    min_profit_factor: float,
    min_sharpe: float,
    max_drawdown_pct: float,
    min_deflated_sharpe_proxy: float = 0.0,
) -> bool:
    return (
        metrics.trades >= min_trades
        and metrics.profit_factor >= min_profit_factor
        and metrics.sharpe >= min_sharpe
        and metrics.deflated_sharpe_proxy >= min_deflated_sharpe_proxy
        and abs(metrics.max_drawdown_pct) <= max_drawdown_pct
    )


def _max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, (equity - peak) / peak)
    return worst


def _ratio(returns: list[float], *, downside_only: bool = False) -> float:
    if not returns:
        return 0.0
    selected = [value for value in returns if value < 0] if downside_only else returns
    if not selected:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((value - (sum(selected) / len(selected))) ** 2 for value in selected) / len(selected)
    std = math.sqrt(variance)
    if std <= 0:
        return 0.0
    return mean / std * math.sqrt(252)


def _deflated_sharpe_proxy(sharpe: float, returns: list[float], trials: int) -> float:
    if not returns:
        return 0.0
    sample_penalty = 0.0
    if len(returns) < 30:
        sample_penalty = (30 - len(returns)) / 120
    multiple_testing_penalty = math.sqrt(max(math.log(max(trials, 1)), 0.0)) * 0.12
    non_normal_penalty = 0.0
    if len(returns) >= 3:
        mean = sum(returns) / len(returns)
        centered = [value - mean for value in returns]
        variance = sum(value * value for value in centered) / len(centered)
        if variance > 0:
            std = math.sqrt(variance)
            skew = sum((value / std) ** 3 for value in centered) / len(centered)
            kurtosis = sum((value / std) ** 4 for value in centered) / len(centered)
            non_normal_penalty = 0.04 * abs(skew) + 0.015 * max(kurtosis - 3.0, 0.0)
    return sharpe - sample_penalty - multiple_testing_penalty - non_normal_penalty

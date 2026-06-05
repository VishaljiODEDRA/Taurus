from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


Action = Literal["BUY", "SELL", "HOLD"]
ExecutionMode = Literal["shadow", "demo", "live"]


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Instrument:
    symbol: str
    instrument_id: int
    asset_type: str = "Unknown"
    exchange: str | None = None
    is_currently_tradable: bool = True
    is_exchange_open: bool = True
    is_buy_enabled: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Rate:
    instrument_id: int
    bid: float
    ask: float
    last_execution: float
    timestamp: datetime
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last_execution

    @property
    def spread_bps(self) -> float:
        if self.mid <= 0:
            return 10_000.0
        return ((self.ask - self.bid) / self.mid) * 10_000

    def age_seconds(self, now: datetime | None = None) -> float:
        reference = now or utc_now()
        return max((reference - self.timestamp).total_seconds(), 0.0)


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    instrument: Instrument
    rate: Rate
    candles: list[Candle] = field(default_factory=list)

    @property
    def symbol(self) -> str:
        return self.instrument.symbol


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str = ""
    url: str = ""
    published_at: datetime | None = None
    source: str = ""
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewsContext:
    symbol: str
    sentiment_score: float = 0.0
    catalyst_score: float = 0.0
    summary: str = ""
    items: tuple[NewsItem, ...] = ()


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    instrument_id: int
    position_id: str
    units: float
    invested_usd: float
    current_value_usd: float
    pnl_usd: float = 0.0
    open_rate: float = 0.0

    @property
    def pnl_pct(self) -> float:
        if self.invested_usd <= 0:
            return 0.0
        return self.pnl_usd / self.invested_usd


@dataclass(frozen=True)
class PortfolioState:
    nav_usd: float
    available_cash_usd: float
    daily_pnl_pct: float = 0.0
    rolling_drawdown_pct: float = 0.0
    positions: tuple[PortfolioPosition, ...] = ()
    open_order_symbols: tuple[str, ...] = ()

    @property
    def gross_exposure_pct(self) -> float:
        if self.nav_usd <= 0:
            return 0.0
        return sum(max(position.current_value_usd, 0.0) for position in self.positions) / self.nav_usd

    def position_for_symbol(self, symbol: str) -> PortfolioPosition | None:
        symbol_upper = symbol.upper()
        for position in self.positions:
            if position.symbol.upper() == symbol_upper:
                return position
        return None


@dataclass(frozen=True)
class SignalDecision:
    symbol: str
    action: Action
    confidence: float
    score: float
    reasons: tuple[str, ...] = ()
    features: dict[str, float | str | bool] = field(default_factory=dict)
    news_context: NewsContext | None = None

    @property
    def is_trade(self) -> bool:
        return self.action in {"BUY", "SELL"}


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    target_notional_usd: float = 0.0
    stop_loss_rate: float | None = None
    take_profit_rate: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def reject(reason: str) -> "RiskDecision":
        return RiskDecision(approved=False, reason=reason)


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    instrument_id: int
    action: Action
    amount_usd: float
    leverage: int
    stop_loss_rate: float | None = None
    take_profit_rate: float | None = None
    trailing_stop: bool = False
    position_id: str | None = None
    dry_run: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    mode: ExecutionMode
    symbol: str
    action: Action
    broker_order_id: str | None = None
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentCycleResult:
    started_at: datetime
    finished_at: datetime
    decisions: tuple[SignalDecision, ...]
    risk_decisions: tuple[RiskDecision, ...]
    orders: tuple[OrderResult, ...]
    position_reviews: tuple[SignalDecision, ...] = ()
    dashboard: dict[str, Any] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str = ""

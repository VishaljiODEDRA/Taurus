from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.config import AppConfig
from agent.ledger import Ledger
from etoro_api import EtoroApiError, EtoroClient
from models.trading import PortfolioState, to_float


@dataclass(frozen=True)
class BrokerSyncResult:
    environment: str
    nav_usd: float
    available_cash_usd: float
    open_positions: int
    history_items_found: int
    imported_trades: int
    skipped_trades: int
    message: str


class BrokerAccountSync:
    def __init__(self, config: AppConfig, ledger: Ledger) -> None:
        self.config = config
        self.ledger = ledger

    def run(self, *, history_dump_path: str | None = None) -> BrokerSyncResult:
        if not self.config.secrets.etoro_api_key or not self.config.secrets.etoro_user_key:
            return BrokerSyncResult(
                environment=self._environment(),
                nav_usd=0.0,
                available_cash_usd=0.0,
                open_positions=0,
                history_items_found=0,
                imported_trades=0,
                skipped_trades=0,
                message="eToro credentials are not configured",
            )

        client = EtoroClient(
            api_key=self.config.secrets.etoro_api_key,
            user_key=self.config.secrets.etoro_user_key,
            base_url=self.config.secrets.etoro_base_url,
            user_agent=self.config.secrets.etoro_user_agent,
        )
        environment = self._environment()
        symbol_map = {instrument_id: symbol for symbol, instrument_id in self.config.universe.instrument_ids.items()}
        portfolio = client.get_portfolio_state(environment, symbol_map)
        self._record_portfolio(environment, portfolio)
        imported, skipped, history_items_found = self._import_trade_history(
            client,
            environment,
            symbol_map,
            history_dump_path=history_dump_path,
        )
        return BrokerSyncResult(
            environment=environment,
            nav_usd=portfolio.nav_usd,
            available_cash_usd=portfolio.available_cash_usd,
            open_positions=len(portfolio.positions),
            history_items_found=history_items_found,
            imported_trades=imported,
            skipped_trades=skipped,
            message="broker account synced",
        )

    def _environment(self) -> str:
        mode = self.config.execution.normalized_mode()
        if mode == "live":
            return "real"
        return self.config.execution.normalized_environment()

    def _record_portfolio(self, environment: str, portfolio: PortfolioState) -> None:
        self.ledger.record_broker_account_snapshot(
            environment=environment,
            nav_usd=portfolio.nav_usd,
            available_cash_usd=portfolio.available_cash_usd,
            daily_pnl_pct=portfolio.daily_pnl_pct,
            rolling_drawdown_pct=portfolio.rolling_drawdown_pct,
            gross_exposure_pct=portfolio.gross_exposure_pct,
            open_positions=len(portfolio.positions),
            raw={
                "positions": [position.__dict__ for position in portfolio.positions],
                "open_order_symbols": portfolio.open_order_symbols,
            },
        )

    def _import_trade_history(
        self,
        client: EtoroClient,
        environment: str,
        symbol_map: dict[int, str],
        history_dump_path: str | None = None,
    ) -> tuple[int, int, int]:
        try:
            payload = client.list_trade_history(environment)
        except EtoroApiError as exc:
            return 0, 1 if exc.status else 0, 0
        if history_dump_path:
            _dump_history_payload(history_dump_path, payload)
        items = _history_items(payload)
        imported = 0
        skipped = 0
        for item in items:
            trade = _closed_trade_from_history_item(item, symbol_map)
            if trade is None:
                skipped += 1
                continue
            if self.ledger.trade_outcome_exists(
                source="broker_trade_history",
                entry_order_id=trade["entry_order_id"],
                exit_order_id=trade["exit_order_id"],
            ):
                skipped += 1
                continue
            self.ledger.record_trade_outcome(
                symbol=trade["symbol"],
                pnl_usd=trade["pnl_usd"],
                return_pct=trade["return_pct"],
                holding_days=trade["holding_days"],
                source="broker_trade_history",
                entry_order_id=trade["entry_order_id"],
                exit_order_id=trade["exit_order_id"],
                entry_time=trade["entry_time"],
                exit_time=trade["exit_time"],
                raw={
                    "entry_context": {"features_json": trade["entry_features"]},
                    "exit_features": trade["exit_features"],
                    "broker_history": item,
                    "environment": environment,
                },
            )
            imported += 1
        return imported, skipped, len(items)


def broker_research_config(config: AppConfig, ledger: Ledger) -> tuple[AppConfig, str]:
    from dataclasses import replace

    environment = "real" if config.execution.normalized_mode() == "live" else config.execution.normalized_environment()
    snapshot = ledger.latest_broker_account_snapshot(environment)
    if not snapshot:
        return config, "using configured synthetic backtest_initial_cash_usd"
    nav = to_float(snapshot.get("nav_usd"), config.validation.backtest_initial_cash_usd)
    if nav <= 0:
        return config, "latest broker NAV was unavailable; using configured synthetic backtest_initial_cash_usd"
    validation = replace(config.validation, backtest_initial_cash_usd=nav)
    return replace(config, validation=validation), f"using latest {environment} broker NAV ${nav:,.2f}"


def _history_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_flatten_dict(item) for item in payload if isinstance(item, dict) and _looks_like_history_item(item)]
    if not isinstance(payload, dict):
        return []
    preferred = (
        "trades",
        "history",
        "tradeHistory",
        "closedPositions",
        "positions",
        "items",
        "data",
    )
    for key in preferred:
        value = payload.get(key)
        if isinstance(value, list):
            return [_flatten_dict(item) for item in value if isinstance(item, dict) and _looks_like_history_item(item)]
    for value in payload.values():
        if isinstance(value, list):
            items = [_flatten_dict(item) for item in value if isinstance(item, dict) and _looks_like_history_item(item)]
            if items:
                return items
    return []


def _closed_trade_from_history_item(
    item: dict[str, Any],
    symbol_map: dict[int, str],
) -> dict[str, Any] | None:
    item = _flatten_dict(item)
    status = str(_first(item, "status", "Status", "state", "State", "tradeStatus", "TradeStatus", default="")).lower()
    if status and not any(term in status for term in ("closed", "close", "filled", "realized")):
        return None
    pnl = to_float(
        _first(
            item,
            "netProfit",
            "NetProfit",
            "profit",
            "Profit",
            "pnl",
            "PnL",
            "realizedPnL",
            "realizedPnl",
            "RealizedPnL",
            "profitInDollars",
            "ProfitInDollars",
            "netProfitInUserCurrency",
            "NetProfitInUserCurrency",
            default=None,
        ),
        None,
    )
    invested = to_float(
        _first(
            item,
            "amount",
            "Amount",
            "investment",
            "Investment",
            "initialAmountInDollars",
            "InitialAmountInDollars",
            "initialInvestment",
            "InitialInvestment",
            "openAmount",
            "OpenAmount",
            "invested",
            "Invested",
            default=0.0,
        )
    )
    close_value = to_float(
        _first(
            item,
            "closeAmount",
            "CloseAmount",
            "closedAmount",
            "ClosedAmount",
            "currentValue",
            "CurrentValue",
            "value",
            "Value",
            "netValue",
            "NetValue",
            default=0.0,
        )
    )
    if pnl is None:
        if invested > 0 and close_value > 0:
            pnl = close_value - invested
        else:
            return None
    if invested <= 0:
        invested = max(abs(close_value - pnl), abs(pnl), 0.0)
    if invested <= 0:
        return None

    instrument_id = int(to_float(_first(item, "instrumentID", "InstrumentID", "instrumentId", "InstrumentId", "cid", "CID", default=0)))
    symbol = str(
        _first(
            item,
            "symbol",
            "Symbol",
            "internalSymbolFull",
            "InternalSymbolFull",
            "ticker",
            "Ticker",
            "instrumentSymbol",
            "InstrumentSymbol",
            default=symbol_map.get(instrument_id, str(instrument_id or "UNKNOWN")),
        )
    ).upper()
    if not symbol or symbol == "UNKNOWN":
        return None

    entry_time = _iso_time(
        _first(item, "openDate", "openTime", "entryTime", "createdAt", "OpenDate", "OpenTime", "CreateDate")
    )
    exit_time = _iso_time(
        _first(item, "closeDate", "closeTime", "exitTime", "closedAt", "CloseDate", "CloseTime", "CloseDateTime")
    )
    holding_days = _holding_days(entry_time, exit_time)
    return_pct = to_float(
        _first(item, "returnPct", "ReturnPct", "returnPercentage", "ReturnPercentage", "gainPct", "GainPct", default=None),
        None,
    )
    if return_pct is None:
        return_pct = pnl / invested
    elif abs(return_pct) > 1.0:
        return_pct = return_pct / 100

    entry_order_id = (
        str(_first(item, "openOrderID", "openOrderId", "OpenOrderID", "orderId", "OrderID", default="")).strip()
        or None
    )
    exit_order_id = (
        str(_first(item, "closeOrderID", "closeOrderId", "CloseOrderID", "positionID", "positionId", "PositionID", default="")).strip()
        or None
    )
    if not entry_order_id and not exit_order_id:
        entry_order_id = f"{symbol}:{entry_time}:{exit_time}:{pnl:.4f}"

    return {
        "symbol": symbol,
        "pnl_usd": pnl,
        "return_pct": return_pct,
        "holding_days": holding_days,
        "entry_order_id": entry_order_id,
        "exit_order_id": exit_order_id,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "entry_features": {
            "score": to_float(_first(item, "score", "decisionScore", default=0.0)),
            "confidence": to_float(_first(item, "confidence", "decisionConfidence", default=0.0)),
            "broker_invested_usd": invested,
            "broker_return_pct": return_pct,
        },
        "exit_features": {
            "broker_pnl_usd": pnl,
            "broker_close_value_usd": close_value,
        },
    }


def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _flatten_dict(data: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(data)
    for key, value in data.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                flattened.setdefault(str(nested_key), nested_value)
                flattened.setdefault(f"{key}.{nested_key}", nested_value)
    return flattened


def _looks_like_history_item(item: dict[str, Any]) -> bool:
    flattened = _flatten_dict(item)
    keys = {str(key).lower() for key in flattened}
    return bool(
        keys
        & {
            "instrumentid",
            "instrumentid",
            "symbol",
            "ticker",
            "positionid",
            "positionid",
            "openorderid",
            "closeorderid",
            "netprofit",
            "profit",
            "pnl",
            "realizedpnl",
            "investment",
            "amount",
        }
    )


def _dump_history_payload(path: str, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _iso_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _holding_days(entry_time: str | None, exit_time: str | None) -> int:
    if not entry_time or not exit_time:
        return 0
    try:
        entry = datetime.fromisoformat(entry_time)
        exit_ = datetime.fromisoformat(exit_time)
    except ValueError:
        return 0
    return max((exit_.date() - entry.date()).days, 0)

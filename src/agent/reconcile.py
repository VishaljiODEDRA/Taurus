from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from agent.config import AppConfig
from agent.ledger import Ledger
from etoro_api import EtoroApiError, EtoroClient
from models import PortfolioPosition, PortfolioState


DRIFT_ALERT_PCT = 0.05
PNL_MISMATCH_USD = 10.0
PNL_MISMATCH_PCT = 0.01


@dataclass(frozen=True)
class ReconciliationAlert:
    code: str
    level: str
    message: str
    symbol: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    status: str
    message: str
    open_positions: int = 0
    recent_local_orders: int = 0
    alert_count: int = 0
    alerts: tuple[ReconciliationAlert, ...] = ()
    raw: dict[str, Any] | None = None


class Reconciler:
    def __init__(self, config: AppConfig, ledger: Ledger) -> None:
        self.config = config
        self.ledger = ledger

    def run(self) -> ReconciliationReport:
        if not self.config.secrets.etoro_api_key or not self.config.secrets.etoro_user_key:
            report = ReconciliationReport("skipped", "eToro credentials are not configured")
            self.ledger.record_reconciliation(report.status, report.message)
            return report

        client = EtoroClient(
            api_key=self.config.secrets.etoro_api_key,
            user_key=self.config.secrets.etoro_user_key,
            base_url=self.config.secrets.etoro_base_url,
            user_agent=self.config.secrets.etoro_user_agent,
        )
        environment = "demo" if self.config.execution.normalized_mode() != "live" else "real"
        try:
            portfolio = client.get_portfolio_state(environment)
        except EtoroApiError as exc:
            report = ReconciliationReport(
                "error",
                f"portfolio reconciliation failed: {exc}",
                raw={"status": exc.status, "payload": exc.payload},
            )
            self.ledger.record_reconciliation(report.status, report.message, report.raw)
            return report

        local_orders = self.ledger.latest_orders(limit=100)
        open_contexts = self.ledger.open_trade_contexts(limit=500)
        report = analyze_reconciliation(
            portfolio=portfolio,
            local_orders=local_orders,
            open_contexts=open_contexts,
        )
        self.ledger.record_reconciliation(report.status, report.message, report.raw)
        return report


def analyze_reconciliation(
    *,
    portfolio: PortfolioState,
    local_orders: list[dict[str, Any]],
    open_contexts: list[dict[str, Any]],
) -> ReconciliationReport:
    alerts: list[ReconciliationAlert] = []
    positions_by_symbol: dict[str, list[PortfolioPosition]] = defaultdict(list)
    for position in portfolio.positions:
        positions_by_symbol[position.symbol.upper()].append(position)
    broker_symbols = set(positions_by_symbol)
    context_by_symbol = _latest_contexts_by_symbol(open_contexts)
    accepted_orders = [_normalize_order(row) for row in local_orders if int(row.get("accepted") or 0)]
    local_open_symbols = _local_open_symbols(accepted_orders)

    for symbol, positions in positions_by_symbol.items():
        if len(positions) > 1:
            alerts.append(
                ReconciliationAlert(
                    "duplicate_exposure",
                    "critical",
                    f"Broker has {len(positions)} open exposures for {symbol}.",
                    symbol=symbol,
                    details={"position_ids": [position.position_id for position in positions]},
                )
            )
        context = context_by_symbol.get(symbol)
        if context is None and symbol not in local_open_symbols:
            alerts.append(
                ReconciliationAlert(
                    "missing_local_order",
                    "critical",
                    f"Broker shows {symbol} open, but no local accepted BUY/context was found.",
                    symbol=symbol,
                )
            )
        elif context is not None:
            alerts.extend(_position_drift_alerts(symbol, positions, context))
            protection_alert = _stale_protection_alert(symbol, context)
            if protection_alert is not None:
                alerts.append(protection_alert)
            pnl_alert = _pnl_mismatch_alert(symbol, positions, context, portfolio.nav_usd)
            if pnl_alert is not None:
                alerts.append(pnl_alert)

    for symbol in sorted(local_open_symbols - broker_symbols):
        alerts.append(
            ReconciliationAlert(
                "missing_broker_position",
                "warning",
                f"Local ledger has an accepted BUY for {symbol}, but broker has no open position.",
                symbol=symbol,
            )
        )

    status = "ok"
    if any(alert.level == "critical" for alert in alerts):
        status = "alert"
    elif alerts:
        status = "warning"
    message = "broker and ledger are aligned" if not alerts else f"{len(alerts)} reconciliation alert(s) detected"
    raw = {
        "nav_usd": portfolio.nav_usd,
        "available_cash_usd": portfolio.available_cash_usd,
        "positions": [position.__dict__ for position in portfolio.positions],
        "local_orders": local_orders[:20],
        "open_trade_contexts": open_contexts[:20],
        "alerts": [alert.__dict__ for alert in alerts],
    }
    return ReconciliationReport(
        status,
        message,
        open_positions=len(portfolio.positions),
        recent_local_orders=len(local_orders),
        alert_count=len(alerts),
        alerts=tuple(alerts),
        raw=raw,
    )


def _latest_contexts_by_symbol(open_contexts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for context in open_contexts:
        symbol = str(context.get("symbol", "")).upper()
        if symbol and symbol not in contexts:
            contexts[symbol] = context
    return contexts


def _normalize_order(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["symbol"] = str(row.get("symbol", "")).upper()
    normalized["action"] = str(row.get("action", "")).upper()
    normalized["raw_json"] = _loads(row.get("raw_json"), {})
    return normalized


def _local_open_symbols(accepted_orders: list[dict[str, Any]]) -> set[str]:
    counts: Counter[str] = Counter()
    for order in reversed(accepted_orders):
        symbol = str(order.get("symbol", "")).upper()
        if not symbol:
            continue
        action = str(order.get("action", "")).upper()
        if action == "BUY":
            counts[symbol] += 1
        elif action == "SELL":
            counts[symbol] = max(counts[symbol] - 1, 0)
    return {symbol for symbol, count in counts.items() if count > 0}


def _position_drift_alerts(
    symbol: str,
    positions: list[PortfolioPosition],
    context: dict[str, Any],
) -> list[ReconciliationAlert]:
    expected_notional = _float(context.get("entry_notional_usd"), 0.0)
    broker_invested = sum(max(position.invested_usd, 0.0) for position in positions)
    if expected_notional <= 0 or broker_invested <= 0:
        return []
    drift_pct = abs(broker_invested - expected_notional) / expected_notional
    if drift_pct <= DRIFT_ALERT_PCT:
        return []
    return [
        ReconciliationAlert(
            "position_level_drift",
            "warning",
            f"{symbol} broker invested amount drifted {drift_pct:.1%} from local entry notional.",
            symbol=symbol,
            details={
                "ledger_entry_notional_usd": expected_notional,
                "broker_invested_usd": broker_invested,
                "drift_pct": drift_pct,
            },
        )
    ]


def _stale_protection_alert(symbol: str, context: dict[str, Any]) -> ReconciliationAlert | None:
    risk_details = context.get("risk_details_json", {})
    if not isinstance(risk_details, dict):
        risk_details = {}
    stop_loss = _float(risk_details.get("stop_loss_rate"), 0.0)
    take_profit = _float(risk_details.get("take_profit_rate"), 0.0)
    if stop_loss > 0 and take_profit > 0:
        return None
    return ReconciliationAlert(
        "stale_protection",
        "critical",
        f"{symbol} lacks confirmed stop-loss/take-profit protection in the local ledger.",
        symbol=symbol,
        details={"stop_loss_rate": stop_loss, "take_profit_rate": take_profit},
    )


def _pnl_mismatch_alert(
    symbol: str,
    positions: list[PortfolioPosition],
    context: dict[str, Any],
    nav_usd: float,
) -> ReconciliationAlert | None:
    expected_notional = _float(context.get("entry_notional_usd"), 0.0)
    broker_current_value = sum(position.current_value_usd for position in positions)
    broker_pnl = sum(position.pnl_usd for position in positions)
    if expected_notional <= 0:
        return None
    ledger_implied_pnl = broker_current_value - expected_notional
    mismatch = abs(broker_pnl - ledger_implied_pnl)
    threshold = max(PNL_MISMATCH_USD, max(nav_usd, 0.0) * PNL_MISMATCH_PCT)
    if mismatch <= threshold:
        return None
    return ReconciliationAlert(
        "broker_ledger_pnl_mismatch",
        "warning",
        f"{symbol} broker PnL differs from ledger-implied PnL by ${mismatch:.2f}.",
        symbol=symbol,
        details={
            "broker_pnl_usd": broker_pnl,
            "ledger_implied_pnl_usd": ledger_implied_pnl,
            "mismatch_usd": mismatch,
            "threshold_usd": threshold,
        },
    )


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) if isinstance(value, str) else default
    except json.JSONDecodeError:
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

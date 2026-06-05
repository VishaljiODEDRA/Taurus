from __future__ import annotations

import time
import uuid
from typing import Protocol

from agent.config import AppConfig
from etoro_api import EtoroApiError, EtoroClient
from models import OrderRequest, OrderResult


class Broker(Protocol):
    def execute(self, order: OrderRequest) -> OrderResult:
        ...


class ShadowBroker:
    mode = "shadow"

    def execute(self, order: OrderRequest) -> OrderResult:
        return OrderResult(
            accepted=True,
            mode="shadow",
            symbol=order.symbol,
            action=order.action,
            broker_order_id=f"shadow-{uuid.uuid4()}",
            message="shadow order recorded only; no broker call made",
            raw={"order": order.metadata},
        )


class EtoroBroker:
    def __init__(self, client: EtoroClient, *, mode: str, environment: str, retry_attempts: int = 2) -> None:
        self.client = client
        self.mode = mode
        self.environment = environment
        self.retry_attempts = max(retry_attempts, 1)

    def execute(self, order: OrderRequest) -> OrderResult:
        last_error: EtoroApiError | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                if order.action == "BUY":
                    payload = self.client.open_market_order_by_amount(
                        environment=self.environment,
                        instrument_id=order.instrument_id,
                        is_buy=True,
                        amount_usd=order.amount_usd,
                        leverage=order.leverage,
                        stop_loss_rate=order.stop_loss_rate,
                        take_profit_rate=order.take_profit_rate,
                        trailing_stop=order.trailing_stop,
                    )
                    broker_order_id = _extract_order_id(payload)
                    return OrderResult(
                        accepted=True,
                        mode=self.mode,  # type: ignore[arg-type]
                        symbol=order.symbol,
                        action=order.action,
                        broker_order_id=broker_order_id,
                        message="order submitted to eToro",
                        raw=payload if isinstance(payload, dict) else {"payload": payload},
                    )
                if order.action == "SELL":
                    if not order.position_id:
                        return OrderResult(
                            accepted=False,
                            mode=self.mode,  # type: ignore[arg-type]
                            symbol=order.symbol,
                            action=order.action,
                            message="missing position_id for close order",
                        )
                    payload = self.client.close_position(
                        environment=self.environment,
                        position_id=order.position_id,
                        units_to_deduct=None,
                    )
                    broker_order_id = _extract_order_id(payload)
                    return OrderResult(
                        accepted=True,
                        mode=self.mode,  # type: ignore[arg-type]
                        symbol=order.symbol,
                        action=order.action,
                        broker_order_id=broker_order_id,
                        message="close order submitted to eToro",
                        raw=payload if isinstance(payload, dict) else {"payload": payload},
                    )
            except EtoroApiError as exc:
                last_error = exc
                if attempt < self.retry_attempts and _should_retry_order_error(exc):
                    time.sleep(min(attempt, 3))
                    continue
                return OrderResult(
                    accepted=False,
                    mode=self.mode,  # type: ignore[arg-type]
                    symbol=order.symbol,
                    action=order.action,
                    message=str(exc),
                    raw={"status": exc.status, "payload": exc.payload, "attempts": attempt},
                )

        return OrderResult(
            accepted=False,
            mode=self.mode,  # type: ignore[arg-type]
            symbol=order.symbol,
            action=order.action,
            message=str(last_error) if last_error else "unsupported order action",
        )


def build_broker(config: AppConfig, *, allow_live_cli: bool = False) -> Broker:
    mode = config.execution.normalized_mode()
    if mode == "shadow":
        return ShadowBroker()
    if mode not in {"demo", "live"}:
        raise ValueError(f"Unsupported execution mode: {mode}")
    if mode == "live" and not (allow_live_cli and config.secrets.allow_live):
        raise PermissionError(
            "Live trading requires AUTOTRADER_ALLOW_LIVE=true and the --allow-live CLI flag."
        )
    if not config.secrets.etoro_api_key or not config.secrets.etoro_user_key:
        raise PermissionError("eToro credentials are required for demo/live execution.")

    environment = "demo" if mode == "demo" else "real"
    client = EtoroClient(
        api_key=config.secrets.etoro_api_key,
        user_key=config.secrets.etoro_user_key,
        base_url=config.secrets.etoro_base_url,
        user_agent=config.secrets.etoro_user_agent,
    )
    return EtoroBroker(
        client,
        mode=mode,
        environment=environment,
        retry_attempts=config.risk.execution_retry_attempts,
    )


def _extract_order_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    candidates = [
        payload.get("token"),
        payload.get("orderId"),
        payload.get("orderID"),
        payload.get("id"),
    ]
    order_for_open = payload.get("orderForOpen")
    if isinstance(order_for_open, dict):
        candidates.extend(
            [
                order_for_open.get("token"),
                order_for_open.get("orderId"),
                order_for_open.get("orderID"),
                order_for_open.get("id"),
            ]
        )
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _should_retry_order_error(exc: EtoroApiError) -> bool:
    if exc.status in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return "network error" in message or "timeout" in message or "temporarily" in message

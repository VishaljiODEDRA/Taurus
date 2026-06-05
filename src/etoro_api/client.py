from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from models import Candle, Instrument, PortfolioPosition, PortfolioState, Rate
from models.trading import to_float


class EtoroApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload


def _parse_datetime(value: Any) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_present(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _as_list(payload: Any, preferred_keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for value in payload.values():
        if isinstance(value, list):
            return value
    return []


def _instrument_symbol(data: dict[str, Any]) -> str:
    return str(_first_present(data, "internalSymbolFull", "InternalSymbolFull", "symbol", default="")).upper()


def _instrument_asset_type(data: dict[str, Any]) -> str:
    return str(
        _first_present(
            data,
            "instrumentTypeName",
            "InstrumentTypeName",
            "instrumentType",
            "InstrumentType",
            "internalAssetClassName",
            "InternalAssetClassName",
            "instrumentClass-TTM",
            "instrumentClass-Annual",
            "figiSecurityType",
            default="Unknown",
        )
    )


def _instrument_exchange(data: dict[str, Any]) -> Any:
    return _first_present(
        data,
        "exchangeName",
        "ExchangeName",
        "internalExchangeName",
        "InternalExchangeName",
        default=None,
    )


def _looks_like_stock_or_etf(data: dict[str, Any]) -> bool:
    normalized = _instrument_asset_type(data).lower()
    return any(term in normalized for term in ("stock", "equity", "etf", "exchange traded"))


def _select_search_result(results: list[Any], exact_symbol: str) -> dict[str, Any] | None:
    candidates = [item for item in results if isinstance(item, dict)]
    if not candidates:
        return None

    preferred_symbols = (f"{exact_symbol}.US", f"{exact_symbol}.RTH", exact_symbol)
    for preferred_symbol in preferred_symbols:
        for item in candidates:
            if _instrument_symbol(item) == preferred_symbol and _looks_like_stock_or_etf(item):
                return item

    for item in candidates:
        if _instrument_symbol(item) == exact_symbol:
            return item
    return candidates[0]


class EtoroClient:
    """Small eToro Public API client using only the Python standard library."""

    def __init__(
        self,
        api_key: str,
        user_key: str,
        base_url: str = "https://public-api.etoro.com/api/v1",
        user_agent: str = "AutoTrading-Agent/0.1 (+https://api-portal.etoro.com/)",
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.user_key = user_key
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.user_key)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        if not self.configured:
            raise EtoroApiError("eToro credentials are not configured")

        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{clean_path}"
        query = self._encode_params(params or {})
        if query:
            url = f"{url}?{query}"

        headers = {
            "x-request-id": str(uuid.uuid4()),
            "x-api-key": self.api_key,
            "x-user-key": self.user_key,
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        attempt = 0
        while True:
            request = Request(url=url, data=data, headers=headers, method=method.upper())
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
                    if not raw:
                        return {}
                    return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                payload = self._read_error_payload(exc)
                if exc.code == 429 and attempt < self.max_retries:
                    time.sleep(_retry_delay_seconds(payload, attempt))
                    attempt += 1
                    continue
                raise EtoroApiError(
                    f"eToro API {method.upper()} {clean_path} failed with {exc.code}",
                    status=exc.code,
                    payload=payload,
                ) from exc
            except URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(min(2**attempt, 8))
                    attempt += 1
                    continue
                raise EtoroApiError(f"eToro API network error: {exc.reason}") from exc

    @staticmethod
    def _encode_params(params: dict[str, Any]) -> str:
        encoded: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                encoded.append((key, ",".join(str(item) for item in value)))
            else:
                encoded.append((key, str(value)))
        return urlencode(encoded, quote_via=quote, safe=",")

    @staticmethod
    def _read_error_payload(exc: HTTPError) -> Any:
        try:
            body = exc.read()
        except OSError:
            return None
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return body.decode("utf-8", errors="replace")

    def get_identity(self) -> dict[str, Any]:
        return self.request("GET", "/me")

    def get_agent_portfolios(self) -> dict[str, Any]:
        return self.request("GET", "/agent-portfolios")

    def search_instrument(self, symbol: str) -> Instrument | None:
        payload = self.request(
            "GET",
            "/market-data/search",
            params={"internalSymbolFull": symbol.upper()},
        )
        results = _as_list(payload, ("instruments", "items", "results"))
        if not results:
            return None

        exact_symbol = symbol.upper()
        selected = _select_search_result(results, exact_symbol)
        if not selected:
            return None

        instrument_id = int(
            _first_present(
                selected,
                "instrumentId",
                "InstrumentID",
                "instrumentID",
                "InstrumentId",
                default=0,
            )
        )
        if instrument_id <= 0:
            return None

        return Instrument(
            symbol=exact_symbol,
            instrument_id=instrument_id,
            asset_type=_instrument_asset_type(selected),
            exchange=_instrument_exchange(selected),
            is_currently_tradable=bool(
                _first_present(selected, "isCurrentlyTradable", "IsCurrentlyTradable", default=True)
            ),
            is_exchange_open=bool(
                _first_present(selected, "isExchangeOpen", "IsExchangeOpen", default=True)
            ),
            is_buy_enabled=bool(_first_present(selected, "isBuyEnabled", "IsBuyEnabled", default=True)),
            raw=selected,
        )

    def get_rates(self, instrument_ids: list[int]) -> dict[int, Rate]:
        try:
            payload = self.request(
                "GET",
                "/market-data/instruments/rates",
                params={"instrumentIds": instrument_ids},
            )
        except EtoroApiError as exc:
            if exc.status != 500 or len(instrument_ids) <= 1:
                raise
            rates: dict[int, Rate] = {}
            for instrument_id in instrument_ids:
                try:
                    rates.update(self.get_rates([instrument_id]))
                except EtoroApiError:
                    continue
            if rates:
                return rates
            raise
        return self._parse_rates_payload(payload)

    def _parse_rates_payload(self, payload: Any) -> dict[int, Rate]:
        rates: dict[int, Rate] = {}
        for item in _as_list(payload, ("rates", "items", "results")):
            if not isinstance(item, dict):
                continue
            instrument_id = int(
                _first_present(item, "instrumentID", "InstrumentID", "instrumentId", default=0)
            )
            if instrument_id <= 0:
                continue
            rates[instrument_id] = Rate(
                instrument_id=instrument_id,
                bid=to_float(_first_present(item, "bid", "Bid")),
                ask=to_float(_first_present(item, "ask", "Ask")),
                last_execution=to_float(
                    _first_present(item, "lastExecution", "LastExecution", "last", default=0.0)
                ),
                timestamp=_parse_datetime(_first_present(item, "date", "Date", "timestamp")),
                raw=item,
            )
        return rates

    def get_candles(
        self,
        instrument_id: int,
        *,
        interval: str = "OneDay",
        candles_count: int = 120,
        direction: str = "desc",
    ) -> list[Candle]:
        path = (
            f"/market-data/instruments/{instrument_id}/history/candles/"
            f"{direction}/{interval}/{candles_count}"
        )
        payload = self.request("GET", path)
        raw_candles = _as_list(payload, ("candles", "items", "results"))
        candles: list[Candle] = []
        for item in raw_candles:
            if not isinstance(item, dict):
                continue
            candles.append(
                Candle(
                    timestamp=_parse_datetime(
                        _first_present(item, "date", "Date", "timestamp", "from")
                    ),
                    open=to_float(_first_present(item, "open", "Open")),
                    high=to_float(_first_present(item, "high", "High")),
                    low=to_float(_first_present(item, "low", "Low")),
                    close=to_float(_first_present(item, "close", "Close")),
                    volume=to_float(_first_present(item, "volume", "Volume")),
                )
            )
        return sorted(candles, key=lambda candle: candle.timestamp)

    def get_portfolio_raw(self, environment: str) -> Any:
        if environment == "demo":
            return self.request("GET", "/trading/info/demo/portfolio")
        return self.request("GET", "/trading/info/portfolio")

    def get_pnl_raw(self, environment: str) -> Any:
        if environment == "demo":
            return self.request("GET", "/trading/info/demo/pnl")
        return self.request("GET", "/trading/info/real/pnl")

    def get_portfolio_state(
        self,
        environment: str,
        instrument_symbol_map: dict[int, str] | None = None,
    ) -> PortfolioState:
        instrument_symbol_map = instrument_symbol_map or {}
        portfolio = self.get_portfolio_raw(environment)
        pnl = self.get_pnl_raw(environment)
        return parse_portfolio_state(portfolio, pnl, instrument_symbol_map)

    def open_market_order_by_amount(
        self,
        *,
        environment: str,
        instrument_id: int,
        is_buy: bool,
        amount_usd: float,
        leverage: int = 1,
        stop_loss_rate: float | None = None,
        take_profit_rate: float | None = None,
        trailing_stop: bool = False,
    ) -> Any:
        prefix = "/trading/execution/demo" if environment == "demo" else "/trading/execution"
        body: dict[str, Any] = {
            "InstrumentID": instrument_id,
            "IsBuy": is_buy,
            "Leverage": leverage,
            "Amount": round(amount_usd, 2),
            "IsTslEnabled": trailing_stop,
        }
        if stop_loss_rate is not None:
            body["StopLossRate"] = stop_loss_rate
        else:
            body["IsNoStopLoss"] = True
        if take_profit_rate is not None:
            body["TakeProfitRate"] = take_profit_rate
        else:
            body["IsNoTakeProfit"] = True
        return self.request("POST", f"{prefix}/market-open-orders/by-amount", body=body)

    def close_position(
        self,
        *,
        environment: str,
        position_id: str,
        units_to_deduct: float | None = None,
    ) -> Any:
        prefix = "/trading/execution/demo" if environment == "demo" else "/trading/execution"
        body = {"UnitsToDeduct": units_to_deduct}
        return self.request("POST", f"{prefix}/market-close-orders/positions/{position_id}", body=body)

    def list_trade_history(self, environment: str = "real") -> Any:
        if environment == "demo":
            try:
                return self.request("GET", "/trading/info/demo/trade/history")
            except EtoroApiError as exc:
                if exc.status not in {404, 405}:
                    raise
        return self.request("GET", "/trading/info/trade/history")


def parse_portfolio_state(
    portfolio_payload: Any,
    pnl_payload: Any,
    instrument_symbol_map: dict[int, str] | None = None,
) -> PortfolioState:
    instrument_symbol_map = instrument_symbol_map or {}
    portfolio_root = (
        portfolio_payload.get("clientPortfolio", portfolio_payload)
        if isinstance(portfolio_payload, dict)
        else {}
    )
    pnl_root = pnl_payload.get("clientPortfolio", pnl_payload) if isinstance(pnl_payload, dict) else {}

    credit = to_float(
        _first_present(
            pnl_root,
            "credit",
            "equity",
            "availableCash",
            default=_first_present(portfolio_root, "credit", "equity", default=0.0),
        )
    )
    unrealized = to_float(_first_present(pnl_root, "unrealizedPnL", "unrealizedPnl", default=0.0))
    nav = max(credit + unrealized, credit, 0.0)
    available_cash = to_float(
        _first_present(
            pnl_root,
            "availableCash",
            "availableAmount",
            "credit",
            default=_first_present(portfolio_root, "availableCash", "credit", default=nav),
        )
    )
    daily_pnl_pct = to_float(_first_present(pnl_root, "dailyPnLPercentage", "dailyPnlPct", default=0.0))
    if abs(daily_pnl_pct) > 1.0:
        daily_pnl_pct = daily_pnl_pct / 100
    drawdown_pct = to_float(_first_present(pnl_root, "drawdownPct", "rollingDrawdownPct", default=0.0))
    if abs(drawdown_pct) > 1.0:
        drawdown_pct = drawdown_pct / 100

    positions = _extract_positions(portfolio_root, instrument_symbol_map)
    open_order_symbols = tuple(_extract_open_order_symbols(portfolio_root, instrument_symbol_map))
    return PortfolioState(
        nav_usd=nav,
        available_cash_usd=available_cash,
        daily_pnl_pct=daily_pnl_pct,
        rolling_drawdown_pct=drawdown_pct,
        positions=tuple(positions),
        open_order_symbols=open_order_symbols,
    )


def _extract_positions(
    portfolio_root: dict[str, Any],
    instrument_symbol_map: dict[int, str],
) -> list[PortfolioPosition]:
    position_items: list[Any] = []
    if isinstance(portfolio_root.get("positions"), list):
        position_items.extend(portfolio_root["positions"])
    for mirror in portfolio_root.get("mirrors", []) if isinstance(portfolio_root.get("mirrors"), list) else []:
        if isinstance(mirror, dict) and isinstance(mirror.get("positions"), list):
            position_items.extend(mirror["positions"])

    positions: list[PortfolioPosition] = []
    for item in position_items:
        if not isinstance(item, dict):
            continue
        instrument_id = int(
            _first_present(item, "instrumentID", "InstrumentID", "instrumentId", "InstrumentId", default=0)
        )
        symbol = instrument_symbol_map.get(instrument_id, str(instrument_id))
        invested = to_float(
            _first_present(
                item,
                "amount",
                "investment",
                "initialAmountInDollars",
                "initialInvestment",
                default=0.0,
            )
        )
        pnl = to_float(_first_present(item, "netProfit", "profit", "pnl", default=0.0))
        current_value = to_float(
            _first_present(item, "currentValue", "value", "unitsBaseValueDollars", default=invested + pnl)
        )
        positions.append(
            PortfolioPosition(
                symbol=symbol,
                instrument_id=instrument_id,
                position_id=str(
                    _first_present(item, "positionID", "positionId", "PositionID", default="")
                ),
                units=to_float(_first_present(item, "units", "Units", default=0.0)),
                invested_usd=invested,
                current_value_usd=current_value,
                pnl_usd=pnl,
                open_rate=to_float(_first_present(item, "openRate", "OpenRate", default=0.0)),
            )
        )
    return positions


def _extract_open_order_symbols(
    portfolio_root: dict[str, Any],
    instrument_symbol_map: dict[int, str],
) -> list[str]:
    order_items = []
    for key in ("orders", "openOrders", "ordersForOpen", "ordersForClose"):
        value = portfolio_root.get(key)
        if isinstance(value, list):
            order_items.extend(value)

    symbols: list[str] = []
    for item in order_items:
        if not isinstance(item, dict):
            continue
        instrument_id = int(
            _first_present(item, "instrumentID", "InstrumentID", "instrumentId", "InstrumentId", default=0)
        )
        symbol = instrument_symbol_map.get(instrument_id)
        if symbol:
            symbols.append(symbol)
    return symbols


def _retry_delay_seconds(payload: Any, attempt: int) -> float:
    if isinstance(payload, dict):
        retry_after = payload.get("retry_after") or payload.get("retryAfter")
        try:
            if retry_after is not None:
                return min(float(retry_after) * (2**attempt), 120.0)
        except (TypeError, ValueError):
            pass
    return min(2**attempt, 8)

from __future__ import annotations

import base64
import json
import math
import os
import re
import socket
import ssl
import struct
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from agent.config import AppConfig
from etoro_api import EtoroApiError, EtoroClient
from models import Candle, Instrument, MarketSnapshot, Rate


class MarketDataProvider(Protocol):
    def snapshots(self, symbols: tuple[str, ...]) -> dict[str, MarketSnapshot]:
        ...


class EtoroMarketDataProvider:
    def __init__(
        self,
        client: EtoroClient,
        *,
        instrument_ids: dict[str, int] | None = None,
        cache_path: str = "state/market_cache.json",
        instrument_cache_ttl_days: int = 14,
        candle_cache_ttl_minutes: int = 360,
        candle_interval: str = "OneDay",
        candle_count: int = 120,
        minimum_candles: int = 35,
        allowed_asset_types: tuple[str, ...] = ("Stock", "ETF"),
        chart_data_source: str = "tradingview",
        chart_data_fallback_source: str = "yahoo",
        tradingview_timeout_seconds: float = 8.0,
    ) -> None:
        self.client = client
        self.instrument_ids = {symbol.upper(): value for symbol, value in (instrument_ids or {}).items()}
        self.cache_path = Path(cache_path)
        self.instrument_cache_ttl = timedelta(days=instrument_cache_ttl_days)
        self.candle_cache_ttl = timedelta(minutes=candle_cache_ttl_minutes)
        self.candle_interval = candle_interval
        self.candle_count = candle_count
        self.minimum_candles = minimum_candles
        self.allowed_asset_types = allowed_asset_types
        self.chart_data_source = chart_data_source.lower()
        self.chart_data_fallback_source = chart_data_fallback_source.lower()
        self.tradingview_timeout_seconds = tradingview_timeout_seconds
        self.cache = _load_cache(self.cache_path)

    def snapshots(self, symbols: tuple[str, ...]) -> dict[str, MarketSnapshot]:
        instruments: dict[str, Instrument] = {}
        for symbol in symbols:
            try:
                instrument = self._instrument_for_symbol(symbol)
            except EtoroApiError:
                continue
            if instrument:
                instruments[symbol.upper()] = instrument
        if not instruments:
            return {}
        _save_cache(self.cache_path, self.cache)

        rates = self.client.get_rates([instrument.instrument_id for instrument in instruments.values()])
        snapshots: dict[str, MarketSnapshot] = {}
        for symbol, instrument in instruments.items():
            rate = rates.get(instrument.instrument_id)
            if rate is None:
                continue
            candles = self._candles_for_symbol(symbol, instrument)
            snapshots[symbol] = MarketSnapshot(
                instrument=_instrument_with_live_rate_status(instrument, rate),
                rate=rate,
                candles=candles,
            )
        _save_cache(self.cache_path, self.cache)
        return snapshots

    def _instrument_for_symbol(self, symbol: str) -> Instrument | None:
        symbol_upper = symbol.upper()
        if symbol_upper in self.instrument_ids:
            return Instrument(
                symbol=symbol_upper,
                instrument_id=self.instrument_ids[symbol_upper],
                asset_type="ETF" if symbol_upper in {"SPY", "QQQ"} else "Stock",
                exchange="eToro",
            )
        cached = self.cache.get("instruments", {}).get(symbol_upper)
        if cached and not _expired(cached.get("cached_at"), self.instrument_cache_ttl):
            cached_instrument = _instrument_from_cache(symbol_upper, cached)
            if _asset_type_allowed(cached_instrument.asset_type, self.allowed_asset_types):
                return cached_instrument
        instrument = self.client.search_instrument(symbol_upper)
        if instrument:
            self.cache.setdefault("instruments", {})[symbol_upper] = _instrument_to_cache(instrument)
        return instrument

    def _candles_for_symbol(self, symbol: str, instrument: Instrument) -> list[Candle]:
        cache_key = f"{instrument.instrument_id}:{self.candle_interval}:{self.candle_count}"
        cached = self.cache.get("candles", {}).get(cache_key)
        cached_candles = [_candle_from_cache(item) for item in cached.get("items", [])] if cached else []
        if (
            cached
            and not _expired(cached.get("cached_at"), self.candle_cache_ttl)
            and len(cached_candles) >= self.minimum_candles
            and str(cached.get("source", "")).lower() == self.chart_data_source
        ):
            return cached_candles

        candles, candle_source = self._load_candles_from_sources(symbol, instrument)

        if not candles and cached_candles:
            return cached_candles
        if len(candles) < self.minimum_candles and len(cached_candles) > len(candles):
            return cached_candles

        self.cache.setdefault("candles", {})[cache_key] = {
            "cached_at": datetime.now(tz=UTC).isoformat(),
            "source": candle_source,
            "items": [_candle_to_cache(candle) for candle in candles],
        }
        return candles

    def _load_candles_from_sources(
        self,
        symbol: str,
        instrument: Instrument,
    ) -> tuple[list[Candle], str]:
        candles: list[Candle] = []
        candle_source = "none"
        sources = _ordered_chart_sources(self.chart_data_source, self.chart_data_fallback_source)
        for source in sources:
            if source == "tradingview" and self.candle_interval == "OneDay":
                candidate = _fallback_candles_from_tradingview(
                    symbol,
                    instrument.exchange,
                    self.candle_count,
                    timeout_seconds=self.tradingview_timeout_seconds,
                )
            elif source == "yahoo" and self.candle_interval == "OneDay":
                candidate = _fallback_candles_from_yahoo(symbol, self.candle_count)
            elif source == "etoro":
                try:
                    candidate = self.client.get_candles(
                        instrument.instrument_id,
                        interval=self.candle_interval,
                        candles_count=self.candle_count,
                    )
                except EtoroApiError:
                    candidate = []
            else:
                candidate = []

            if len(candidate) > len(candles):
                candles = candidate
                candle_source = source
            if len(candles) >= self.minimum_candles:
                break
        return candles, candle_source


class OfflineMarketDataProvider:
    """Deterministic local data for tests and no-credential shadow runs."""

    def snapshots(self, symbols: tuple[str, ...]) -> dict[str, MarketSnapshot]:
        now = datetime.now(tz=UTC)
        snapshots: dict[str, MarketSnapshot] = {}
        for index, symbol in enumerate(symbols):
            seed = sum(ord(char) for char in symbol.upper())
            base = 50 + (seed % 250)
            drift = ((seed % 13) - 4) / 10_000
            volatility = 0.012 + (seed % 7) / 1_000
            candles: list[Candle] = []
            price = float(base)
            for day in range(120, 0, -1):
                move = drift + math.sin((day + seed) / 9) * volatility
                open_price = price
                close = max(open_price * (1 + move), 1.0)
                high = max(open_price, close) * (1 + volatility / 2)
                low = min(open_price, close) * (1 - volatility / 2)
                volume = 1_000_000 + (seed % 17) * 50_000 + (120 - day) * 1_500
                candles.append(
                    Candle(
                        timestamp=now - timedelta(days=day),
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                    )
                )
                price = close

            bid = candles[-1].close * 0.999
            ask = candles[-1].close * 1.001
            instrument = Instrument(
                symbol=symbol.upper(),
                instrument_id=10_000 + index,
                asset_type="Stock" if symbol.upper() not in {"SPY", "QQQ"} else "ETF",
                exchange="OFFLINE",
                is_currently_tradable=True,
                is_exchange_open=True,
                is_buy_enabled=True,
            )
            rate = Rate(
                instrument_id=instrument.instrument_id,
                bid=bid,
                ask=ask,
                last_execution=candles[-1].close,
                timestamp=now,
            )
            snapshots[symbol.upper()] = MarketSnapshot(
                instrument=instrument,
                rate=rate,
                candles=candles,
            )
        return snapshots


def build_market_data_provider(config: AppConfig) -> MarketDataProvider:
    if config.secrets.etoro_api_key and config.secrets.etoro_user_key:
        client = EtoroClient(
            api_key=config.secrets.etoro_api_key,
            user_key=config.secrets.etoro_user_key,
            base_url=config.secrets.etoro_base_url,
            user_agent=config.secrets.etoro_user_agent,
        )
        return EtoroMarketDataProvider(
            client,
            instrument_ids=config.universe.instrument_ids,
            cache_path=config.universe.market_cache_path,
            instrument_cache_ttl_days=config.universe.instrument_cache_ttl_days,
            candle_cache_ttl_minutes=config.universe.candle_cache_ttl_minutes,
            allowed_asset_types=config.universe.allowed_asset_types,
            chart_data_source=config.universe.chart_data_source,
            chart_data_fallback_source=config.universe.chart_data_fallback_source,
            tradingview_timeout_seconds=config.universe.tradingview_timeout_seconds,
            minimum_candles=max(
                config.strategy.previous_month_window + 1,
                config.strategy.slow_ma_period,
                config.strategy.volatility_window + 1,
                35,
            ),
        )
    return OfflineMarketDataProvider()


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {"instruments": {}, "candles": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"instruments": {}, "candles": {}}
    if not isinstance(payload, dict):
        return {"instruments": {}, "candles": {}}
    payload.setdefault("instruments", {})
    payload.setdefault("candles", {})
    return payload


def _save_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _expired(cached_at: object, ttl: timedelta) -> bool:
    if not cached_at:
        return True
    try:
        timestamp = datetime.fromisoformat(str(cached_at))
    except ValueError:
        return True
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return datetime.now(tz=UTC) - timestamp.astimezone(UTC) > ttl


def _first_present(data: dict, *keys: str, default=None):
    for key in keys:
        if key in data:
            return data[key]
    return default


def _asset_type_allowed(asset_type: str, allowed: tuple[str, ...]) -> bool:
    normalized = asset_type.lower()
    return any(item.lower() in normalized or normalized in item.lower() for item in allowed)


def _instrument_from_cache(symbol: str, cached: dict) -> Instrument:
    raw = cached.get("raw", {})
    asset_type = str(cached.get("asset_type", "Unknown"))
    if asset_type.lower() in {"", "none", "unknown"} and isinstance(raw, dict):
        asset_type = str(
            _first_present(
                raw,
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
    exchange = cached.get("exchange")
    if not exchange and isinstance(raw, dict):
        exchange = _first_present(
            raw,
            "exchangeName",
            "ExchangeName",
            "internalExchangeName",
            "InternalExchangeName",
            default=None,
        )
    return Instrument(
        symbol=symbol,
        instrument_id=int(cached["instrument_id"]),
        asset_type=asset_type,
        exchange=exchange,
        is_currently_tradable=bool(cached.get("is_currently_tradable", True)),
        is_exchange_open=bool(cached.get("is_exchange_open", True)),
        is_buy_enabled=bool(cached.get("is_buy_enabled", True)),
        raw=raw if isinstance(raw, dict) else {},
    )


def _instrument_to_cache(instrument: Instrument) -> dict:
    return {
        "cached_at": datetime.now(tz=UTC).isoformat(),
        "instrument_id": instrument.instrument_id,
        "asset_type": instrument.asset_type,
        "exchange": instrument.exchange,
        "is_currently_tradable": instrument.is_currently_tradable,
        "is_exchange_open": instrument.is_exchange_open,
        "is_buy_enabled": instrument.is_buy_enabled,
        "raw": instrument.raw,
    }


def _candle_to_cache(candle: Candle) -> dict:
    return {
        "timestamp": candle.timestamp.isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


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


def _instrument_with_live_rate_status(instrument: Instrument, rate: Rate) -> Instrument:
    if (
        rate.bid > 0
        and rate.ask > 0
        and rate.last_execution > 0
        and rate.age_seconds() <= 15 * 60
        and not instrument.is_exchange_open
    ):
        return replace(instrument, is_exchange_open=True)
    return instrument


def _ordered_chart_sources(primary: str, fallback: str) -> list[str]:
    ordered: list[str] = []
    for source in (primary, fallback, "etoro"):
        normalized = source.lower().strip()
        if normalized in {"tv", "trading-view"}:
            normalized = "tradingview"
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def _fallback_candles_from_tradingview(
    symbol: str,
    exchange: str | None,
    count: int,
    *,
    timeout_seconds: float = 8.0,
) -> list[Candle]:
    for tv_symbol in _tradingview_symbol_candidates(symbol, exchange):
        try:
            candles = _tradingview_candles(tv_symbol, count, timeout_seconds=timeout_seconds)
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            continue
        if candles:
            return candles
    return []


def _tradingview_symbol_candidates(symbol: str, exchange: str | None) -> list[str]:
    clean_symbol = symbol.upper().replace("-", ".")
    candidates: list[str] = []
    common_exchanges = ["NASDAQ", "NYSE", "AMEX"]
    if clean_symbol in {"SPY", "IWM", "DIA", "VOO", "IVV", "VTI"}:
        common_exchanges = ["AMEX", "NASDAQ", "NYSE"]
    mapped_exchange = _tradingview_exchange(exchange)
    if mapped_exchange and clean_symbol not in {"SPY", "IWM", "DIA", "VOO", "IVV", "VTI"}:
        candidates.append(f"{mapped_exchange}:{clean_symbol}")
    for tv_exchange in common_exchanges:
        candidates.append(f"{tv_exchange}:{clean_symbol}")

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _tradingview_exchange(exchange: str | None) -> str | None:
    if not exchange:
        return None
    normalized = re.sub(r"[^A-Z]", "", exchange.upper())
    if "NASDAQ" in normalized:
        return "NASDAQ"
    if "AMEX" in normalized:
        return "AMEX"
    if "ARCA" in normalized:
        return "AMEX"
    if "NYSE" in normalized and "RTH" not in normalized:
        return "NYSE"
    return None


def _tradingview_candles(
    tv_symbol: str,
    count: int,
    *,
    timeout_seconds: float,
) -> list[Candle]:
    chart_session = f"cs_{os.urandom(8).hex()}"
    symbol_alias = "symbol_1"
    series_id = "s1"
    symbol_payload = "=" + json.dumps(
        {
            "symbol": tv_symbol,
            "adjustment": "splits",
            "session": "regular",
        },
        separators=(",", ":"),
    )
    messages = [
        _tradingview_message("set_auth_token", ["unauthorized_user_token"]),
        _tradingview_message("chart_create_session", [chart_session, ""]),
        _tradingview_message("resolve_symbol", [chart_session, symbol_alias, symbol_payload]),
        _tradingview_message(
            "create_series",
            [chart_session, series_id, series_id, symbol_alias, "1D", count],
        ),
    ]

    with _TradingViewSocket(timeout_seconds=timeout_seconds) as websocket:
        for message in messages:
            websocket.send_text(message)

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            raw = websocket.recv_text()
            if raw.startswith("~h~"):
                websocket.send_text(raw)
                continue
            for payload in _tradingview_payloads(raw):
                candles = _candles_from_tradingview_message(payload, series_id, count)
                if candles:
                    return candles
        return []


def _tradingview_message(method: str, params: list) -> str:
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~{payload}"


def _tradingview_payloads(raw: str) -> list[str]:
    payloads: list[str] = []
    index = 0
    while index < len(raw):
        if not raw.startswith("~m~", index):
            break
        size_start = index + 3
        size_end = raw.find("~m~", size_start)
        if size_end < 0:
            break
        try:
            size = int(raw[size_start:size_end])
        except ValueError:
            break
        payload_start = size_end + 3
        payload_end = payload_start + size
        payloads.append(raw[payload_start:payload_end])
        index = payload_end
    return payloads


def _candles_from_tradingview_message(payload: str, series_id: str, count: int) -> list[Candle]:
    message = json.loads(payload)
    method = message.get("m")
    if method in {"critical_error", "series_error", "symbol_error"}:
        raise ValueError(f"TradingView returned {method}")
    if method != "timescale_update":
        return []
    params = message.get("p") or []
    if len(params) < 2 or not isinstance(params[1], dict):
        return []
    series = params[1].get(series_id)
    if not isinstance(series, dict):
        return []
    candles = _candles_from_tradingview_series(series)
    return candles[-count:]


def _candles_from_tradingview_series(series: dict) -> list[Candle]:
    candles: list[Candle] = []
    for row in series.get("s", []):
        if not isinstance(row, dict):
            continue
        values = row.get("v", [])
        if len(values) < 5:
            continue
        try:
            close = float(values[4])
            if close <= 0:
                continue
            candles.append(
                Candle(
                    timestamp=_tradingview_timestamp(values[0]),
                    open=float(values[1]),
                    high=float(values[2]),
                    low=float(values[3]),
                    close=close,
                    volume=_float_at(values, 5, 0.0),
                )
            )
        except (TypeError, ValueError, OverflowError):
            continue
    return sorted(candles, key=lambda candle: candle.timestamp)


def _tradingview_timestamp(value: object) -> datetime:
    if isinstance(value, str) and re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
    return datetime.fromtimestamp(int(float(value)), tz=UTC)


class _TradingViewSocket:
    host = "data.tradingview.com"
    path = "/socket.io/websocket"

    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.socket: ssl.SSLSocket | None = None

    def __enter__(self) -> "_TradingViewSocket":
        raw_socket = socket.create_connection((self.host, 443), timeout=self.timeout_seconds)
        raw_socket.settimeout(self.timeout_seconds)
        context = ssl.create_default_context()
        self.socket = context.wrap_socket(raw_socket, server_hostname=self.host)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: https://www.tradingview.com\r\n"
            "User-Agent: Mozilla/5.0 AutoTrading-Agent/0.1\r\n"
            "\r\n"
        )
        self.socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.socket.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise OSError("TradingView websocket handshake failed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.socket:
            self.socket.close()

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_text(self) -> str:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

            if opcode == 0x8:
                raise OSError("TradingView websocket closed")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode in {0x1, 0x0}:
                return payload.decode("utf-8", errors="replace")

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.socket is None:
            raise OSError("TradingView websocket is not connected")
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend((0x80 | 126, *struct.pack("!H", length)))
        else:
            header.extend((0x80 | 127, *struct.pack("!Q", length)))
        mask = os.urandom(4)
        masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.socket.sendall(bytes(header) + mask + masked_payload)

    def _read_exact(self, size: int) -> bytes:
        if self.socket is None:
            raise OSError("TradingView websocket is not connected")
        output = b""
        while len(output) < size:
            chunk = self.socket.recv(size - len(output))
            if not chunk:
                raise OSError("TradingView websocket closed")
            output += chunk
        return output


def _fallback_candles_from_yahoo(symbol: str, count: int) -> list[Candle]:
    yahoo_symbol = quote(symbol.upper().replace(".", "-"), safe="")
    range_name = _yahoo_range_for_count(count)
    query = urlencode(
        {
            "range": range_name,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    request = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?{query}",
        headers={"User-Agent": "Mozilla/5.0 AutoTrading-Agent/0.1"},
    )
    try:
        with urlopen(request, timeout=6.0) as response:
            raw = response.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
    except (OSError, URLError, json.JSONDecodeError):
        return []

    return _candles_from_yahoo_chart_payload(payload, count)


def _yahoo_range_for_count(count: int) -> str:
    if count <= 130:
        return "6mo"
    if count <= 260:
        return "1y"
    if count <= 520:
        return "2y"
    return "5y"


def _candles_from_yahoo_chart_payload(payload: dict, count: int) -> list[Candle]:
    try:
        result = (payload.get("chart", {}).get("result") or [])[0]
        timestamps = result.get("timestamp") or []
        quote_data = (result.get("indicators", {}).get("quote") or [])[0]
    except (AttributeError, IndexError):
        return []

    candles: list[Candle] = []
    opens = quote_data.get("open") or []
    highs = quote_data.get("high") or []
    lows = quote_data.get("low") or []
    closes = quote_data.get("close") or []
    volumes = quote_data.get("volume") or []
    for index, timestamp in enumerate(timestamps):
        try:
            close = float(closes[index])
            if close <= 0:
                continue
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(timestamp), tz=UTC),
                    open=_float_at(opens, index, close),
                    high=_float_at(highs, index, close),
                    low=_float_at(lows, index, close),
                    close=close,
                    volume=_float_at(volumes, index, 0.0),
                )
            )
        except (IndexError, TypeError, ValueError, OverflowError):
            continue
    return sorted(candles, key=lambda candle: candle.timestamp)[-count:]


def _float_at(values: list, index: int, default: float) -> float:
    try:
        value = values[index]
    except IndexError:
        return default
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

from __future__ import annotations

import sys
import tempfile
import unittest
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent.data as data_module
from agent.data import EtoroMarketDataProvider
from models import Candle, Instrument, Rate


class MarketDataProviderTest(unittest.TestCase):
    def test_public_history_fallback_replaces_one_candle_etoro_history(self) -> None:
        original_fallback = data_module._fallback_candles_from_yahoo
        data_module._fallback_candles_from_yahoo = lambda symbol, count: _candles(count)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                provider = EtoroMarketDataProvider(
                    FakeMarketClient(),
                    cache_path=str(Path(tmp) / "market_cache.json"),
                    minimum_candles=35,
                    chart_data_source="yahoo",
                )

                snapshots = provider.snapshots(("AAPL",))

                self.assertEqual(len(snapshots["AAPL"].candles), 120)
        finally:
            data_module._fallback_candles_from_yahoo = original_fallback

    def test_fresh_rate_marks_cached_closed_instrument_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = EtoroMarketDataProvider(
                FakeMarketClient(exchange_open=False, candle_count=40),
                cache_path=str(Path(tmp) / "market_cache.json"),
                minimum_candles=35,
                chart_data_source="etoro",
            )

            snapshots = provider.snapshots(("AAPL",))

            self.assertTrue(snapshots["AAPL"].instrument.is_exchange_open)

    def test_yahoo_chart_payload_parser_skips_empty_rows(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_700_000_000, 1_700_086_400, 1_700_172_800],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10, None, 12],
                                    "high": [11, None, 13],
                                    "low": [9, None, 11],
                                    "close": [10.5, None, 12.5],
                                    "volume": [1000, None, 1200],
                                }
                            ]
                        },
                    }
                ]
            }
        }

        candles = data_module._candles_from_yahoo_chart_payload(payload, count=120)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].close, 10.5)
        self.assertEqual(candles[1].volume, 1200)

    def test_tradingview_chart_payload_parser_reads_ohlcv_rows(self) -> None:
        payload = json.dumps(
            {
                "m": "timescale_update",
                "p": [
                    "cs_123",
                    {
                        "s1": {
                            "s": [
                                {"i": 0, "v": [1_700_000_000, 10, 11, 9, 10.5, 1000]},
                                {"i": 1, "v": [1_700_086_400, 10.5, 12, 10, 11.5, 1200]},
                            ]
                        }
                    },
                ],
            }
        )

        candles = data_module._candles_from_tradingview_message(payload, "s1", count=120)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].open, 10)
        self.assertEqual(candles[1].close, 11.5)
        self.assertEqual(candles[1].volume, 1200)

    def test_tradingview_symbol_candidates_prefer_known_etf_exchange(self) -> None:
        self.assertEqual(data_module._tradingview_symbol_candidates("SPY", "NYSE")[0], "AMEX:SPY")
        self.assertEqual(data_module._tradingview_symbol_candidates("PWR", "NYSE")[0], "NYSE:PWR")

    def test_cached_unknown_asset_type_is_repaired_from_raw_metadata(self) -> None:
        instrument = data_module._instrument_from_cache(
            "PWR",
            {
                "instrument_id": 1743,
                "asset_type": "Unknown",
                "exchange": None,
                "raw": {
                    "internalAssetClassName": "Stocks",
                    "internalExchangeName": "NYSE",
                },
            },
        )

        self.assertEqual(instrument.asset_type, "Stocks")
        self.assertEqual(instrument.exchange, "NYSE")

    def test_cached_disallowed_asset_type_is_refreshed_from_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "market_cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "instruments": {
                            "STX": {
                                "cached_at": datetime.now(tz=UTC).isoformat(),
                                "instrument_id": 100314,
                                "asset_type": "Crypto",
                                "exchange": "Digital Currency",
                                "raw": {"internalAssetClassName": "Crypto"},
                            }
                        },
                        "candles": {},
                    }
                ),
                encoding="utf-8",
            )
            provider = EtoroMarketDataProvider(
                FakeMarketClient(candle_count=40),
                cache_path=str(cache_path),
                minimum_candles=35,
                chart_data_source="etoro",
            )

            snapshots = provider.snapshots(("STX",))

            self.assertEqual(snapshots["STX"].instrument.instrument_id, 1)
            self.assertEqual(snapshots["STX"].instrument.asset_type, "Stock")


class FakeMarketClient:
    def __init__(self, *, exchange_open: bool = True, candle_count: int = 1) -> None:
        self.exchange_open = exchange_open
        self.candle_count = candle_count

    def search_instrument(self, symbol: str) -> Instrument:
        return Instrument(
            symbol=symbol,
            instrument_id=1,
            asset_type="Stock",
            is_exchange_open=self.exchange_open,
        )

    def get_rates(self, instrument_ids: list[int]) -> dict[int, Rate]:
        return {
            1: Rate(
                instrument_id=1,
                bid=99,
                ask=101,
                last_execution=100,
                timestamp=datetime.now(tz=UTC),
            )
        }

    def get_candles(self, instrument_id: int, *, interval: str, candles_count: int) -> list[Candle]:
        return _candles(self.candle_count)


def _candles(count: int) -> list[Candle]:
    now = datetime.now(tz=UTC)
    candles: list[Candle] = []
    price = 100.0
    for days_ago in range(count, 0, -1):
        close = price * 1.001
        candles.append(
            Candle(
                timestamp=now - timedelta(days=days_ago),
                open=price,
                high=close * 1.01,
                low=price * 0.99,
                close=close,
                volume=1_000_000,
            )
        )
        price = close
    return candles


if __name__ == "__main__":
    unittest.main()

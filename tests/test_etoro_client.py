from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etoro_api.client import EtoroApiError, EtoroClient, parse_portfolio_state


class EtoroClientParsingTest(unittest.TestCase):
    def test_encode_params_keeps_comma_separated_instrument_ids(self) -> None:
        query = EtoroClient._encode_params({"instrumentIds": [1, 2, 3]})

        self.assertEqual(query, "instrumentIds=1,2,3")

    def test_get_rates_falls_back_to_single_requests_after_batch_500(self) -> None:
        client = FakeRatesClient()

        rates = client.get_rates([1, 2])

        self.assertEqual(set(rates), {1, 2})
        self.assertEqual(client.calls, [[1, 2], [1], [2]])

    def test_search_instrument_reads_etoro_asset_class_fields(self) -> None:
        client = FakeSearchClient()

        instrument = client.search_instrument("PWR")

        self.assertIsNotNone(instrument)
        assert instrument is not None
        self.assertEqual(instrument.asset_type, "Stocks")
        self.assertEqual(instrument.exchange, "NYSE")

    def test_search_instrument_prefers_us_stock_variant_over_crypto_symbol_collision(self) -> None:
        client = FakeSearchClient(
            [
                {
                    "instrumentId": 100314,
                    "internalSymbolFull": "STX",
                    "internalInstrumentDisplayName": "Stacks",
                    "internalAssetClassName": "Crypto",
                    "internalExchangeName": "Digital Currency",
                },
                {
                    "instrumentId": 4356,
                    "internalSymbolFull": "STX.US",
                    "internalInstrumentDisplayName": "Seagate Technology PLC",
                    "internalAssetClassName": "Stocks",
                    "internalExchangeName": "Nasdaq",
                },
            ]
        )

        instrument = client.search_instrument("STX")

        self.assertIsNotNone(instrument)
        assert instrument is not None
        self.assertEqual(instrument.instrument_id, 4356)
        self.assertEqual(instrument.asset_type, "Stocks")

    def test_parse_portfolio_state_handles_mirror_positions(self) -> None:
        portfolio = {
            "clientPortfolio": {
                "credit": 10_000,
                "mirrors": [
                    {
                        "positions": [
                            {
                                "positionId": 123,
                                "instrumentId": 1,
                                "units": 3,
                                "amount": 300,
                                "netProfit": 12,
                                "openRate": 100,
                            }
                        ]
                    }
                ],
            }
        }
        pnl = {"clientPortfolio": {"credit": 10_000, "unrealizedPnL": 12}}
        state = parse_portfolio_state(portfolio, pnl, {1: "AAPL"})

        self.assertEqual(state.nav_usd, 10_012)
        self.assertEqual(state.positions[0].symbol, "AAPL")
        self.assertAlmostEqual(state.positions[0].pnl_pct, 0.04)


class FakeRatesClient(EtoroClient):
    def __init__(self) -> None:
        super().__init__("api", "user")
        self.calls: list[list[int]] = []

    def request(self, method, path, *, params=None, body=None):
        instrument_ids = params["instrumentIds"]
        self.calls.append(list(instrument_ids))
        if len(instrument_ids) > 1:
            raise EtoroApiError("batch failed", status=500)
        instrument_id = instrument_ids[0]
        return {
            "rates": [
                {
                    "instrumentID": instrument_id,
                    "ask": 101,
                    "bid": 100,
                    "lastExecution": 100.5,
                    "date": "2026-04-27T10:00:00Z",
                }
            ]
        }


class FakeSearchClient(EtoroClient):
    def __init__(self, instruments=None) -> None:
        super().__init__("api", "user")
        self.instruments = instruments or [
            {
                "instrumentId": 1743,
                "internalSymbolFull": "PWR",
                "internalAssetClassName": "Stocks",
                "internalExchangeName": "NYSE",
                "isCurrentlyTradable": True,
                "isExchangeOpen": True,
                "isBuyEnabled": True,
            }
        ]

    def request(self, method, path, *, params=None, body=None):
        return {"instruments": self.instruments}


if __name__ == "__main__":
    unittest.main()

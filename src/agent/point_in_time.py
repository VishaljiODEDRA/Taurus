from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent.ledger import Ledger


@dataclass(frozen=True)
class PointInTimeReplay:
    as_of: str
    symbol: str | None
    cycle_features: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    risk_checks: tuple[dict[str, Any], ...]
    orders: tuple[dict[str, Any], ...]
    news_source_stats: tuple[dict[str, Any], ...]
    portfolio_risk_reports: tuple[dict[str, Any], ...]

    @property
    def latest_feature_by_symbol(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in self.cycle_features:
            symbol = str(row.get("symbol", "")).upper()
            if symbol and symbol not in latest:
                latest[symbol] = row
        return latest

    def as_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "symbol": self.symbol,
            "cycle_features": list(self.cycle_features),
            "decisions": list(self.decisions),
            "risk_checks": list(self.risk_checks),
            "orders": list(self.orders),
            "news_source_stats": list(self.news_source_stats),
            "portfolio_risk_reports": list(self.portfolio_risk_reports),
        }


class PointInTimeReplayer:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def replay(self, as_of: str | datetime, *, symbol: str | None = None, limit: int = 100) -> PointInTimeReplay:
        as_of_iso = _as_iso(as_of)
        state = self.ledger.replay_state_as_of(as_of_iso, symbol=symbol, limit=limit)
        return PointInTimeReplay(
            as_of=as_of_iso,
            symbol=state["symbol"],
            cycle_features=tuple(state["cycle_features"]),
            decisions=tuple(state["decisions"]),
            risk_checks=tuple(state["risk_checks"]),
            orders=tuple(state["orders"]),
            news_source_stats=tuple(state["news_source_stats"]),
            portfolio_risk_reports=tuple(state["portfolio_risk_reports"]),
        )


class RealisticReplayEngine:
    """Replay the auditable decision state exactly as it existed at a cutoff time."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def replay_cycle(self, as_of: str | datetime, *, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        replay = PointInTimeReplayer(self.ledger).replay(as_of, symbol=symbol, limit=limit)
        latest = replay.latest_feature_by_symbol
        decisions = []
        for symbol_key, row in latest.items():
            raw_features = row.get("raw_features_json", {})
            decisions.append(
                {
                    "symbol": symbol_key,
                    "action": row.get("action"),
                    "score": row.get("decision_score"),
                    "confidence": row.get("decision_confidence"),
                    "news": {
                        "sentiment": row.get("news_sentiment"),
                        "catalyst": row.get("news_catalyst"),
                        "items": row.get("news_item_count"),
                        "sources": row.get("news_source_count"),
                    },
                    "execution": {
                        "quality": row.get("execution_quality_score"),
                        "slippage_bps": row.get("expected_slippage_bps"),
                        "fill_probability": row.get("fill_probability"),
                    },
                    "portfolio": {
                        "allocation_target_notional_usd": row.get("allocation_target_notional_usd"),
                        "stress_loss_pct": row.get("allocation_max_stress_loss_pct"),
                    },
                    "raw_features": raw_features,
                }
            )
        return {
            "as_of": replay.as_of,
            "symbol": replay.symbol,
            "point_in_time_safe": True,
            "decisions": decisions,
            "orders_seen_as_of": list(replay.orders),
            "risk_checks_seen_as_of": list(replay.risk_checks),
            "news_seen_as_of": list(replay.news_source_stats),
            "portfolio_risk_seen_as_of": list(replay.portfolio_risk_reports),
        }


def _as_iso(value: str | datetime) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()

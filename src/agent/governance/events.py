from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceEvent:
    timestamp: str
    event_type: str
    title: str
    status: str
    summary: str
    severity: str = "neutral"
    symbol: str = ""
    evidence_link: str = ""


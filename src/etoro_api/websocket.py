from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class EtoroWebSocketClient:
    """Configuration holder for eToro WebSocket subscriptions.

    The runtime service is deliberately REST-first in this scaffold. This class centralizes
    the documented auth/subscription messages so a production WebSocket loop can be added
    without spreading protocol details through the trading engine.
    """

    api_key: str
    user_key: str
    url: str = "wss://ws.etoro.com/ws"

    def auth_message(self) -> str:
        return json.dumps({"type": "auth", "apiKey": self.api_key, "userKey": self.user_key})

    def subscribe_message(self, topics: Iterable[str]) -> str:
        return json.dumps({"type": "subscribe", "topics": list(topics)})

    def instrument_topic(self, instrument_id: int) -> str:
        return f"instrument:{instrument_id}"

    def private_topic(self) -> str:
        return "private"

    @staticmethod
    def decode_event(raw_message: str) -> dict[str, Any]:
        payload = json.loads(raw_message)
        return payload if isinstance(payload, dict) else {"payload": payload}


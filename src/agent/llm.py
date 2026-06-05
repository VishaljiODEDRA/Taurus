from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from models import NewsContext, NewsItem


class OpenAIContextAnalyzer:
    """Optional news-context analyzer.

    The output is deliberately constrained to context fields. It is never an order, size,
    or execution instruction.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4.1-mini",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def analyze(self, symbol: str, items: tuple[NewsItem, ...]) -> NewsContext | None:
        if not self.configured or not items:
            return None

        compact_items = [
            {
                "title": item.title,
                "summary": item.summary[:500],
                "source": item.source,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item in items[:8]
        ]
        prompt = {
            "symbol": symbol,
            "news": compact_items,
            "task": (
                "Return strict JSON with sentiment_score from -1 to 1, catalyst_score from 0 to 1, "
                "and a one sentence summary. Do not recommend a trade."
            ),
        }
        body = {
            "model": self.model,
            "instructions": (
                "You are a financial news extraction component. Extract context only. "
                "Never provide investment advice, order instructions, sizing, or a buy/sell command."
            ),
            "input": json.dumps(prompt),
            "max_output_tokens": 300,
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None

        parsed = _parse_response_json(payload)
        if not parsed:
            return None
        return NewsContext(
            symbol=symbol.upper(),
            sentiment_score=_clamp(float(parsed.get("sentiment_score", 0.0)), -1.0, 1.0),
            catalyst_score=_clamp(float(parsed.get("catalyst_score", 0.0)), 0.0, 1.0),
            summary=str(parsed.get("summary", ""))[:500],
            items=items,
        )


def _parse_response_json(payload: dict) -> dict | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return _loads_json_object(output_text)

    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                parsed = _loads_json_object(text)
                if parsed:
                    return parsed
    return None


def _loads_json_object(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(min(value, high), low)


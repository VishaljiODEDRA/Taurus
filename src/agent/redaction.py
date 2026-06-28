from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


PRIVATE_KEY_MARKERS = (
    "key",
    "secret",
    "token",
    "password",
    "account",
    "account_id",
    "user_key",
    "api_key",
    "raw_json",
)


def redact_value(value: Any) -> Any:
    if is_dataclass(value):
        return redact_value(asdict(value))
    if isinstance(value, Path):
        return value.name
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, raw_value in value.items():
            key_text = str(key)
            if is_private_key(key_text):
                if key_text == "broker_order_id":
                    output[key_text] = redact_identifier(raw_value)
                continue
            output[key_text] = redact_value(raw_value)
        return output
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value


def is_private_key(key: str) -> bool:
    text = key.lower()
    if text == "broker_order_id":
        return True
    return any(marker in text for marker in PRIVATE_KEY_MARKERS)


def redact_identifier(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    if len(text) <= 8:
        return "redacted"
    return f"{text[:4]}...{text[-4:]}"


def basename_only(value: Any) -> str:
    if not value:
        return ""
    return Path(str(value)).name


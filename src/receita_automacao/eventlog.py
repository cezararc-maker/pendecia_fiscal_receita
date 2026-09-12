from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic
from typing import Any

from .models import digits_only


def masked_identifier(value: object) -> str:
    digits = digits_only(value)
    return f"***{digits[-4:]}" if digits else ""


class EventLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, *, company: str = "", identifier: str = "", **fields: Any) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "event": event,
            "company": company,
            "identifier": masked_identifier(identifier),
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def timer(self) -> float:
        return monotonic()

    def elapsed(self, started: float) -> float:
        return round(monotonic() - started, 3)

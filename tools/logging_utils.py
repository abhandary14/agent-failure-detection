"""Structured JSON-lines logging for every tool call, used across all tools."""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def log_tool_call(name: str, args: dict[str, Any], result: Any, duration_ms: float) -> None:
    """Append one JSON line recording a tool call to logs/tool_calls.jsonl."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "function": name,
        "arguments": args,
        "result": result,
        "duration_ms": round(duration_ms, 2),
    }
    with open(config.TOOL_CALL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


class timed_call:
    """Context manager that measures wall-clock duration in milliseconds."""

    def __enter__(self) -> "timed_call":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.duration_ms = (time.perf_counter() - self._start) * 1000
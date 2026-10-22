"""Thread-safe counters and event log shared by the player and the control server."""

from __future__ import annotations

from collections import deque
import threading
import time


class Telemetry:
    def __init__(self, max_events: int = 200):
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._events = deque(maxlen=max_events)
        self._counters = {}
        self._values = {}

    def event(self, kind: str, text: str, ok: bool = True) -> None:
        with self._lock:
            self._events.append({"t": time.time(), "kind": kind, "text": text, "ok": ok})
            key = kind if ok else kind + "_error"
            self._counters[key] = self._counters.get(key, 0) + 1

    def set(self, key: str, value) -> None:
        with self._lock:
            self._values[key] = value

    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            return {
                "now": now,
                "started_at": self.started_at,
                "uptime_s": now - self.started_at,
                "counters": dict(self._counters),
                "values": dict(self._values),
                "events": list(self._events),
            }

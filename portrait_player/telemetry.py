"""Thread-safe counters and event log shared by the player and the control server."""

from __future__ import annotations

from collections import deque
from datetime import date, datetime
import json
from pathlib import Path
import re
import threading
import time

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Telemetry:
    def __init__(self, max_events: int = 200, log_dir: str | Path | None = None):
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._events = deque(maxlen=max_events)
        self._counters = {}
        self._values = {}
        self._log_dir = Path(log_dir) if log_dir is not None else None
        if self._log_dir is not None:
            # Show what already happened today after a restart.
            self._events.extend(self.day_events(date.today().isoformat()))

    def _day_file(self, day: str) -> Path:
        return self._log_dir / f"events-{day}.jsonl"

    def event(self, kind: str, text: str, ok: bool = True) -> None:
        entry = {"t": time.time(), "kind": kind, "text": text, "ok": ok}
        with self._lock:
            self._events.append(entry)
            key = kind if ok else kind + "_error"
            self._counters[key] = self._counters.get(key, 0) + 1
            if self._log_dir is not None:
                # One file per calendar day; a new day starts a new file automatically.
                day = datetime.fromtimestamp(entry["t"]).date().isoformat()
                try:
                    self._log_dir.mkdir(parents=True, exist_ok=True)
                    with open(self._day_file(day), "a", encoding="utf-8") as out:
                        out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except OSError:
                    pass  # logging must never break playback

    def day_events(self, day: str) -> list:
        """All events saved for one day (YYYY-MM-DD)."""
        if self._log_dir is None or not _DAY.fullmatch(day):
            return []
        events = []
        try:
            with self._lock, open(self._day_file(day), encoding="utf-8") as src:
                for line in src:
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        continue  # a line cut short by a crash
        except OSError:
            return []
        return events

    def log_days(self) -> list:
        if self._log_dir is None or not self._log_dir.is_dir():
            return []
        days = (p.stem[len("events-"):] for p in self._log_dir.glob("events-*.jsonl"))
        return sorted((d for d in days if _DAY.fullmatch(d)), reverse=True)

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

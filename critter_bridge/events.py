import threading
import time


class Events:
    """Small in-memory event ring shown in the UI and /api/status."""

    LEVEL_ORDER = ("error", "telegram", "thingspeak", "rule", "poll", "info")

    def __init__(self, cap=200):
        self._cap = cap
        self._lock = threading.Lock()
        self._items = []

    def add(self, level, msg):
        if not isinstance(level, str):
            level = "info"
        item = {"ts": time.time(), "level": level.strip() or "info", "msg": str(msg)}
        with self._lock:
            self._items.append(item)
            if len(self._items) > self._cap:
                self._items = self._items[-self._cap:]

    def as_list(self, n=None):
        """Newest first."""
        with self._lock:
            items = list(self._items)
        items.reverse()
        return items[:n] if n else items

"""Poll loop + worker.

Two threads:
  * poller  — fetches /api/dashboard from every enabled board at its
              interval and records last values / status.
  * worker  — consumes poll results and does everything with upstream
              HTTPS latency (ThingSpeak writes, rule evaluation with
              Telegram sends) so a slow cloud call never stalls polling.
"""

import logging
import queue
import threading
import time

from . import backends
from . import board_client
from . import config
from . import rules

log = logging.getLogger(__name__)

POLL_ERROR_REPEAT_S = 60.0   # don't spam the event log while a board is down
TS_OK_REPEAT_S = 600.0       # log ThingSpeak successes at most this often


class Poller:
    def __init__(self, store, events):
        self.store = store
        self.events = events
        self.engine = rules.RuleEngine(store, events)

        self.status = {}        # board_id -> {last_poll, last_seen, last_error, ok}
        self.panels = {}        # board_id -> [panel meta]
        self.values = {}        # board_id -> {panel_id: value}
        self.device_names = {}  # board_id -> "device" from dashboard JSON

        self._queue = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._logged = {}       # (kind, board_id) -> monotonic time of last log

    # ---------- lifecycle ----------

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="poller").start()
        threading.Thread(target=self._consume, daemon=True, name="worker").start()

    def stop(self):
        self._stop.set()

    def forget(self, board_id):
        self.status.pop(board_id, None)
        self.panels.pop(board_id, None)
        self.values.pop(board_id, None)
        self.device_names.pop(board_id, None)

    # ---------- poll loop ----------

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("poller tick failed")
            self._stop.wait(1.0)

    def _tick(self):
        global_interval = int(self.store.settings().get("poll_interval", 15))
        now = time.time()
        for board in self.store.boards():
            if not board.get("enabled", True):
                continue
            try:
                interval = int(board.get("poll_interval") or global_interval)
            except (TypeError, ValueError):
                interval = global_interval
            interval = max(config.MIN_POLL_INTERVAL, interval)
            st = self.status.setdefault(board["id"], {})
            if now - st.get("last_poll", 0.0) < interval:
                continue
            st["last_poll"] = now
            self._poll_board(board, st)

    def _poll_board(self, board, st):
        name = board.get("name") or board.get("host") or board["id"]
        try:
            dash = board_client.fetch_dashboard(board["host"])
        except Exception as e:
            st["ok"] = False
            st["last_error"] = str(e) or e.__class__.__name__
            if self._throttle(("pollfail", board["id"]), POLL_ERROR_REPEAT_S):
                self.events.add("error", "%s: poll failed (%s)" % (name, st["last_error"]))
            return

        st["ok"] = True
        st["last_seen"] = time.time()
        st["last_error"] = ""

        device = str(dash.get("device") or "")
        self.device_names[board["id"]] = device
        st["direct_cloud"] = bool(dash.get("direct_cloud"))
        values, meta = board_client.extract_values(dash)
        self.panels[board["id"]] = meta
        self.values[board["id"]] = values

        try:
            self._queue.put_nowait((board, device, values, meta))
        except queue.Full:
            self.events.add("error", "%s: worker queue full, cycle skipped" % name)

    # ---------- worker ----------

    def _consume(self):
        while not self._stop.is_set():
            try:
                board, device, values, meta = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self._process(board, device, values, meta)
            except Exception:
                log.exception("worker failed for %s", board.get("id"))
            finally:
                self._queue.task_done()

    def _process(self, board, device, values, meta):
        name = board.get("name") or device or board["id"]

        # Boards in ESP32 direct mode handle their own cloud push; the
        # bridge stays read-only for them (no double writes, no rules).
        if self.status.get(board["id"], {}).get("direct_cloud"):
            return
        ok, detail = backends.forward(board, values)
        if ok is not None:  # None = not configured / deferred, stay quiet
            backend = board.get("backend") or "cloud"
            if ok:
                if self._throttle((backend, board["id"]), TS_OK_REPEAT_S):
                    self.events.add(backend, "%s: %s" % (name, detail))
            else:
                self.events.add("error", "%s: %s %s" % (name, backend, detail))

        self.engine.process(board, values, meta, device)

    def _throttle(self, key, min_gap_s):
        """Return True when we're allowed to log this kind of event again."""
        now = time.monotonic()
        last = self._logged.get(key, 0.0)
        if now - last < min_gap_s:
            return False
        self._logged[key] = now
        return True

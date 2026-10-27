"""ThingSpeak forwarder.

Model (v1): one board = one channel. The board's panel -> field mapping lives
in the bridge config; the board never learns anything about ThingSpeak.
Free tier allows one update per channel every ~15 s; we defer writes that
arrive too soon and count on the 15-30 s poll cadence.
"""

import logging
import time

import requests

log = logging.getLogger(__name__)

UPDATE_URL = "https://api.thingspeak.com/update"
TIMEOUT = 8
MIN_GAP_S = 16.0  # be kind to the free tier's ~15 s window

_last_write = {}  # write_key -> monotonic time of last accepted write


def forward(board, values):
    """Send bound panel values to ThingSpeak.

    Returns (ok, detail); ok is True on success, None when skipped
    (missing key / mapping / cadence), False on failure.
    Values that are not numeric are skipped (ThingSpeak is numeric-only).
    """
    cfg = board.get("backend_cfg") or board.get("thingspeak") or {}
    key = (cfg.get("write_key") or "").strip()
    if not key:
        return None, "no write key configured"

    mapping = cfg.get("fields") or {}
    params = {}
    for pid, field in mapping.items():
        try:
            fnum = int(field)
        except (TypeError, ValueError):
            continue
        if not (1 <= fnum <= 8):
            continue
        v = values.get(pid)
        try:
            params["field%d" % fnum] = float(v)
        except (TypeError, ValueError):
            continue
    if not params:
        return None, "no panels mapped to fields"

    last = _last_write.get(key, 0.0)
    now = time.monotonic()
    if now - last < MIN_GAP_S:
        return None, "deferred (channel cadence)"

    params["api_key"] = key
    try:
        resp = requests.get(UPDATE_URL, params=params, timeout=TIMEOUT)
    except Exception as e:
        return False, "request failed: %s" % e

    body = (resp.text or "").strip()
    # ThingSpeak replies with the created entry id (>0), "0" on rejection.
    if resp.ok and body not in ("", "0"):
        _last_write[key] = now
        return True, "entry %s" % body
    return False, "rejected (%s %s)" % (resp.status_code, body or resp.reason)

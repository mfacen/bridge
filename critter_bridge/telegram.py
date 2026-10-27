"""Telegram sender. The bot token and chat ids live only here, on the bridge."""

import logging

import requests

log = logging.getLogger(__name__)

TIMEOUT = 8


def send(token, chat_id, text):
    """POST a message. Returns (ok, detail)."""
    token = (token or "").strip()
    chat_id = str(chat_id or "").strip()
    if not token or not chat_id:
        return False, "missing bot token or chat id"
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    try:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": str(text)[:4000]},
            timeout=TIMEOUT,
        )
    except Exception as e:
        return False, "request failed: %s" % e
    if not resp.ok:
        detail = "HTTP %s" % resp.status_code
        try:
            description = resp.json().get("description")
            if description:
                detail += ": " + description
        except Exception:
            pass
        return False, detail
    message_id = ""
    try:
        message_id = resp.json().get("result", {}).get("message_id", "")
    except Exception:
        pass
    return True, "delivered" + (" (%s)" % message_id if message_id else "")

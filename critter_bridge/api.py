"""Local web API + static UI."""

import logging

from flask import Flask, jsonify, request, send_from_directory

from . import config
from . import telegram

log = logging.getLogger(__name__)


def create_app(store, poller, events, discovery=None):
    app = Flask("critter-bridge")

    # ---- static UI ----

    @app.get("/")
    def index():
        return send_from_directory(config.STATIC_DIR, "index.html")

    @app.get("/app.js")
    def app_js():
        return send_from_directory(config.STATIC_DIR, "app.js")

    @app.get("/style.css")
    def style():
        return send_from_directory(config.STATIC_DIR, "style.css")

    def err(msg, code=400):
        return jsonify({"error": msg}), code

    # ---- status ----

    @app.get("/api/status")
    def status():
        boards = []
        for b in store.boards():
            entry = dict(b)
            entry["status"] = dict(poller.status.get(b["id"], {}))
            entry["panels"] = list(poller.panels.get(b["id"], []))
            entry["direct_cloud"] = bool(poller.status.get(b["id"], {}).get("direct_cloud"))
            boards.append(entry)
        return jsonify({
            "app": config.APP_NAME,
            "version": config.APP_VERSION,
            "settings": store.settings(),
            "boards": boards,
            "discovered": sorted(discovery.discovered.values(), key=lambda d: d["mac"]) if discovery else [],
            "rules": store.rules(),
            "events": events.as_list(100),
        })

    @app.post("/api/discovery/adopt")
    def adopt_discovered():
        if discovery is None:
            return err("discovery not running", 503)
        mac = (request.get_json(silent=True) or {}).get("mac", "")
        entry = discovery.adopt_lookup(mac)
        if not entry:
            return err("beacon not in discovery cache", 404)
        try:
            board = store.add_board({"name": entry.get("device") or "", "host": entry.get("ip"), "mac": mac})
        except ValueError as e:
            return err(str(e))
        discovery.adopt_done(mac)
        events.add("info", "adopted board: %s (%s at %s)" % (board.get("name") or "unknown", mac, board["host"]))
        return jsonify({"board": board})

    @app.get("/api/boards/<board_id>/values")
    def board_values(board_id):
        return jsonify({
            "values": poller.values.get(board_id, {}),
            "panels": poller.panels.get(board_id, []),
            "status": poller.status.get(board_id, {}),
        })

    # ---- boards ----

    @app.post("/api/boards")
    def add_board():
        try:
            board = store.add_board(request.get_json(silent=True) or {})
        except ValueError as e:
            return err(str(e))
        events.add("info", "board added: %s" % (board.get("name") or board["host"]))
        return jsonify({"board": board})

    @app.post("/api/boards/<board_id>")
    def update_board(board_id):
        try:
            board = store.update_board(board_id, request.get_json(silent=True) or {})
        except (ValueError, TypeError) as e:
            return err(str(e))
        if board is None:
            return err("board not found", 404)
        return jsonify({"board": board})

    @app.delete("/api/boards/<board_id>")
    def remove_board(board_id):
        if not store.remove_board(board_id):
            return err("board not found", 404)
        poller.forget(board_id)
        return jsonify({"ok": True})

    # ---- rules ----

    @app.post("/api/rules")
    def add_rule():
        try:
            rule = store.add_rule(request.get_json(silent=True) or {})
        except (ValueError, TypeError) as e:
            return err(str(e))
        return jsonify({"rule": rule})

    @app.post("/api/rules/<rule_id>")
    def update_rule(rule_id):
        try:
            rule = store.update_rule(rule_id, request.get_json(silent=True) or {})
        except (ValueError, TypeError) as e:
            return err(str(e))
        if rule is None:
            return err("rule not found", 404)
        return jsonify({"rule": rule})

    @app.delete("/api/rules/<rule_id>")
    def remove_rule(rule_id):
        if not store.remove_rule(rule_id):
            return err("rule not found", 404)
        return jsonify({"ok": True})

    # ---- settings ----

    @app.post("/api/settings")
    def update_settings():
        return jsonify({"settings": store.update_settings(request.get_json(silent=True) or {})})

    # ---- diagnostics ----

    @app.post("/api/test/telegram")
    def test_telegram():
        data = request.get_json(silent=True) or {}
        ok, detail = telegram.send(
            store.settings().get("telegram_token", ""),
            data.get("chat_id", ""),
            data.get("text") or "critter-bridge test message",
        )
        events.add("telegram" if ok else "error", "telegram test: %s" % detail)
        return jsonify({"ok": bool(ok), "detail": detail}), (200 if ok else 400)

    return app

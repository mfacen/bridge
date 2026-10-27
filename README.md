# critter-bridge

Companion app for **critterOS / Firefly** boards. It bridges your boards to the
internet over HTTPS — something the ESP8266 cannot do reliably — by *pulling*
state from the boards and pushing it out to cloud services.

**v1 architecture (pull-only):** the bridge polls each board's existing
`/api/dashboard` endpoint on an interval and:

- forwards panel values to **ThingSpeak** (first backend; Adafruit IO / InfluxDB Cloud planned),
- evaluates panel-state **rules** and sends **Telegram** messages on threshold crossings,
- exposes a small local web UI for board registry, ThingSpeak mapping, rules, settings and an event log.

**No firmware changes are required.** Boards run critterOS exactly as shipped;
the bridge is a pure companion layer. Firmware updates and bridge updates are
completely decoupled.

## Quickstart

```bash
./run.sh          # creates .venv on first run, then starts the app
# open http://localhost:8787
```

Equivalent manual steps:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

Configuration is stored in `config.json` next to the app (created on first
save). The web UI writes it for you; you can also edit it while the app is
running (changes are picked up on the next poll cycle).

## Concepts

| Piece | What it does |
|---|---|
| **Boards** | Registered by IP (or `host`), or discovered automatically from the boards' UDP beacon (see below). Status shows last poll time / last error. A board can set its own poll interval (otherwise the global one is used). The beacon keeps the stored IP fresh, so DHCP address changes self-heal. |
| **ThingSpeak** | Per board: a write API key plus a panel → field (1–8) mapping. Default model is *one board = one channel*, so multiple boards never contend for ThingSpeak's free-tier ~15 s update cadence. |
| **Rules** | A rule ties a panel to an operator (`< <= > >= == !=`) and a threshold; when true, a message is sent to a Telegram chat. Messages support `{device}`, `{panel}`, `{value}` placeholders (temperature is strung through the value rendering). Hysteresis and a per-rule cooldown prevent flappy spam. |
| **Events** | Rolling log (last 200) of polls, ThingSpeak results, Telegram deliveries and errors — visible in the UI and at `GET /api/events`-style `/api/status`. |

## Auto-discovery

critterOS boards already broadcast a UDP beacon every `udp_beacon_secs`
(default 10 s) on `udp_port` (default 1234):

```
ID: firefly
IP: http://192.168.2.243
MAC: C8:C9:A3:64:80:C8
Panels:pressure,distance
```

The bridge listens on that port (setting **Beacon port**, `0` disables) and:

- **auto-add on** (default): any beacon from an unregistered board adds it,
  named after its `device_name` (a MAC suffix disambiguates duplicates).
- **auto-add off**: beacons appear under *Discovered* in the UI with an
  *Add* button; nothing is registered without you clicking.
- a beacon from a board you already registered updates its stored IP if it
  changed (DHCP-proof tracking).

Beacons carry identity only — panel state still comes from `/api/dashboard`,
so the pull-only architecture (and its workflows) is untouched. Note that
two boards with the same `device_name` both beacon as `firefly`; the
auto-name disambiguates, but distinct names are still tidier.

## Design notes / assumptions

- **Trusted LAN.** Traffic between the bridge and boards is plaintext HTTP.
  This matches critterOS's documented hobbyist stance: do not expose the board
  or the bridge to networks you don't trust. No tokens are between them.
- **The poll wakes the board's OLED.** `/api/dashboard` counts as a viewer in
  critterOS (`displayService.wake()`), so a polled board intentionally keeps
  its display awake. That is accepted behavior for v1.
- **Rule counters live in memory.** A bridge restart resets re-arm/cooldown
  state; this is fine for hobbyist use.
- **Telegram & ThingSpeak credentials live only here**, never on a board.

## Roadmap

- **Next:** more backends behind the same pull model (Adafruit IO, InfluxDB Cloud),
  value gathering per cycle, config file UX polish.
- **Packaging:** single-file executable (PyInstaller) and/or Docker image; a two-line
  systemd unit for Pi users.
- **Later:** board auto-discovery (v2 nicety), optional board-side push transport
  (`bridge_host`) *only if* a real board-originated-event need appears.

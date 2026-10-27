"""Board HTTP client — reads the existing critterOS API, nothing else."""

import requests

DASHBOARD_TIMEOUT = 6  # LAN; short on purpose so a wedged board never stalls the loop



def normalize_host(raw):
    host = str(raw or "").strip().rstrip("/")
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return "http://" + host


def fetch_dashboard(board_host):
    """GET /api/dashboard from a board. Raises requests exceptions on transport failure."""
    url = normalize_host(board_host) + "/api/dashboard"
    resp = requests.get(url, timeout=DASHBOARD_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_health(board_host):
    """GET /api/health — cheap liveness probe (up/heap/tick counters)."""
    url = normalize_host(board_host) + "/api/health"
    resp = requests.get(url, timeout=DASHBOARD_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def extract_values(dash):
    """dashboard JSON -> ({panelId or panelId.valueName: float}, [panel meta]).

    Value convention matches critterOS JSON:
      * panels carry "values": {"": default, "x": ..., "y": ...}
      * "set" panels carry "checked" (bool) -> 1.0 / 0.0 (stored as values[""])
    """
    values, meta = {}, []
    for p in dash.get("panels", []) or []:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        ptype = p.get("type") or "input"
        if ptype == "set":
            v = 1.0 if p.get("checked") else 0.0
            values[pid] = v
            values["%s." % pid] = v  # bare ref = default
        else:
            vals = p.get("values") or {}
            if isinstance(vals, dict) and vals:
                for vname, v in vals.items():
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        fv = 0.0
                    vname = str(vname or "").strip()
                    if vname:
                        values["%s.%s" % (pid, vname)] = fv
                    else:
                        # default/primary value -> bare panel id
                        values[pid] = fv
            else:
                # fallback for old firmware without "values"
                try:
                    values[pid] = float(p.get("value") or 0.0)
                except (TypeError, ValueError):
                    values[pid] = 0.0
        meta.append({
            "id": pid,
            "name": p.get("name") or pid,
            "type": ptype,
            "unit": "",
            "values": list((p.get("values") or {}).keys()) if isinstance(p.get("values"), dict) else [],
        })
    return values, meta

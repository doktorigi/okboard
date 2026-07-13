#!/usr/bin/env python3
"""okboard — a zero-dependency uptime monitor and status page in one file.

Usage: python okboard.py [config.toml]
Requires Python 3.11+. No pip installs, no database, no build step.
"""
import json
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HISTORY = 288  # samples kept per check (24h at 5-min interval)

# ponytail: reachability check, not cert validation — homelabs run self-signed
_SSL_CTX = ssl._create_unverified_context()


def check_http(target: str, timeout: float) -> bool:
    req = urllib.request.Request(target, headers={"User-Agent": "okboard"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return 200 <= r.status < 400


def check_tcp(target: str, timeout: float) -> bool:
    host, _, port = target.rpartition(":")
    with socket.create_connection((host, int(port)), timeout=timeout):
        return True


def check_ping(target: str, timeout: float) -> bool:
    flag = "-n" if sys.platform == "win32" else "-c"
    r = subprocess.run(
        ["ping", flag, "1", target],
        capture_output=True,
        timeout=timeout + 2,
    )
    return r.returncode == 0


CHECKERS = {"http": check_http, "tcp": check_tcp, "ping": check_ping}


def run_one(check: dict) -> tuple[bool, int]:
    """Run a single check. Returns (ok, latency_ms). Never raises."""
    fn = CHECKERS[check["type"]]
    start = time.monotonic()
    try:
        ok = fn(check["target"], check["timeout"])
    except Exception:
        ok = False
    return ok, int((time.monotonic() - start) * 1000)


def poll_loop(checks: list[dict], interval: float) -> None:
    while True:
        for c in checks:
            ok, ms = run_one(c)
            c["history"].append({"ts": int(time.time()), "ok": ok, "ms": ms})
        time.sleep(interval)


def summarize(checks: list[dict]) -> list[dict]:
    out = []
    for c in checks:
        h = list(c["history"])
        out.append({
            "name": c["name"],
            "type": c["type"],
            "target": c["target"],
            "ok": h[-1]["ok"] if h else None,
            "latency_ms": h[-1]["ms"] if h else None,
            "uptime_pct": round(100 * sum(s["ok"] for s in h) / len(h), 1) if h else None,
            "history": h,
        })
    return out


def render_html(checks: list[dict], interval: float) -> str:
    rows = []
    for s in summarize(checks):
        if s["ok"] is None:
            dot, label = "wait", "checking…"
        elif s["ok"]:
            dot, label = "up", f"up · {s['latency_ms']} ms"
        else:
            dot, label = "down", "down"
        cells = "".join(
            f'<i class="{"up" if h["ok"] else "down"}" title="{h["ms"]} ms"></i>'
            for h in s["history"][-60:]
        )
        rows.append(
            f'<div class="row"><span class="dot {dot}"></span>'
            f'<div class="meta"><b>{s["name"]}</b>'
            f'<small>{s["type"]} · {s["target"]}</small></div>'
            f'<div class="bar">{cells}</div>'
            f'<div class="stat">{label}'
            f'<small>{"" if s["uptime_pct"] is None else str(s["uptime_pct"]) + "% uptime"}</small>'
            f"</div></div>"
        )
    all_up = all(c["history"] and c["history"][-1]["ok"] for c in checks)
    banner = "All systems go" if all_up else "Something is down"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{max(int(interval), 10)}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>okboard</title><style>
body{{background:#0f1117;color:#e6e6e6;font:15px/1.5 system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}}
h1{{font-size:20px;font-weight:600}}
.row{{display:flex;align-items:center;gap:14px;background:#181b23;border-radius:10px;padding:14px 16px;margin:10px 0}}
.dot{{width:12px;height:12px;border-radius:50%;flex:none}}
.dot.up,i.up{{background:#2ecc71}}
.dot.down,i.down{{background:#e74c3c}}
.dot.wait{{background:#7f8c8d}}
.meta{{flex:1;min-width:0}}
.meta b{{display:block}}
.meta small,.stat small{{color:#8a8f98;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar{{display:flex;gap:2px}}
.bar i{{width:4px;height:22px;border-radius:2px}}
.stat{{text-align:right;flex:none;min-width:110px}}
</style></head><body>
<h1>{banner}</h1>
{"".join(rows)}
<p><small style="color:#8a8f98">okboard · refreshes every {max(int(interval), 10)}s · <a href="/api" style="color:#8a8f98">JSON</a></small></p>
</body></html>"""


def make_handler(checks: list[dict], interval: float):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api":
                body = json.dumps(summarize(checks)).encode()
                ctype = "application/json"
            elif self.path == "/":
                body = render_html(checks, interval).encode()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler


def load_config(path: str) -> dict:
    import tomllib

    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    checks = cfg.get("check", [])
    if not checks:
        sys.exit(f"no [[check]] entries in {path}")
    for c in checks:
        for key in ("name", "type", "target"):
            if key not in c:
                sys.exit(f"check missing '{key}': {c}")
        if c["type"] not in CHECKERS:
            sys.exit(f"unknown check type '{c['type']}' (use: {', '.join(CHECKERS)})")
        c.setdefault("timeout", 5)
        c["history"] = deque(maxlen=HISTORY)
    return cfg


def main() -> None:
    if sys.version_info < (3, 11):
        sys.exit("okboard needs Python 3.11+")
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "okboard.toml")
    checks = cfg["check"]
    interval = cfg.get("interval", 60)
    port = cfg.get("port", 8080)
    threading.Thread(target=poll_loop, args=(checks, interval), daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(checks, interval))
    print(f"okboard: {len(checks)} checks every {interval}s → http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

"""Self-check for okboard: python test_okboard.py"""
import json
import socket
import threading
from collections import deque

from okboard import check_tcp, render_html, run_one, summarize


def make_check(type_, target, history=()):
    return {
        "name": "t", "type": type_, "target": target, "timeout": 2,
        "history": deque(history, maxlen=10),
    }


def main():
    # tcp up: listen on an ephemeral port and hit it
    srv = socket.create_server(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept(), daemon=True).start()
    assert check_tcp(f"127.0.0.1:{port}", 2) is True
    srv.close()

    # tcp down: run_one must swallow the error and report failure
    ok, ms = run_one(make_check("tcp", f"127.0.0.1:{port}"))
    assert ok is False and ms >= 0

    # summarize + html + json round-trip
    c = make_check("tcp", "127.0.0.1:1", [
        {"ts": 1, "ok": True, "ms": 5},
        {"ts": 2, "ok": False, "ms": 0},
    ])
    s = summarize([c])[0]
    assert s["uptime_pct"] == 50.0 and s["ok"] is False
    html = render_html([c], 60)
    assert "Something is down" in html and c["name"] in html
    json.dumps(summarize([c]))  # must be serializable

    print("ok: all checks passed")


if __name__ == "__main__":
    main()

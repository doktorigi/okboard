"""Self-check for okboard: python test_okboard.py"""
import json
import os
import socket
import tempfile
import threading
from collections import deque

import okboard
from okboard import check_tcp, load_history, poll_once, render_html, run_one, summarize


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

    # webhook fires only on state transitions
    results = [True, False, True]
    okboard.CHECKERS["fake"] = lambda target, timeout: results.pop(0)
    sent = []
    okboard.notify = lambda url, text: sent.append(text)
    fc = make_check("fake", "x")
    for _ in range(3):
        poll_once([fc], webhook="http://example")
    assert sent == ["DOWN: t (x)", "UP: t (x)"], sent

    # history persists across a "restart" and skips corrupt lines
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        results.extend([True, False])
        pc = make_check("fake", "x")
        poll_once([pc], history_file=path)
        poll_once([pc], history_file=path)
        with open(path, "a") as f:
            f.write('{"broken')  # unclean shutdown
        fresh = make_check("fake", "x")
        load_history(path, [fresh])
        assert [s["ok"] for s in fresh["history"]] == [True, False]
    finally:
        os.unlink(path)

    print("ok: all checks passed")


if __name__ == "__main__":
    main()

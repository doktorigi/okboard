# okboard

A self-hosted uptime monitor and status page in **one file**, with **zero dependencies**.

Uptime Kuma is great, but it's a Node app with a database. Sometimes you just want a
green/red page for your homelab that runs anywhere Python runs.

```
┌──────────────────────────────────────────────┐
│  All systems go                              │
│                                              │
│  ● Router      ping · 192.168.1.1   ▮▮▮▮▮▮  │
│  ● Proxmox     http · https://…     ▮▮▮▮▮▮  │
│  ● NAS SSH     tcp  · …:22          ▮▮▮▯▮▮  │
└──────────────────────────────────────────────┘
```

## Quick start

Needs Python 3.11+. Nothing to install.

```sh
curl -O https://raw.githubusercontent.com/doktorigi/okboard/main/okboard.py
curl -O https://raw.githubusercontent.com/doktorigi/okboard/main/okboard.toml
# edit okboard.toml, then:
python okboard.py
```

Open http://localhost:8080. `/api` serves the same data as JSON.

## Config

```toml
port = 8080
interval = 60          # seconds between check rounds

[[check]]
name = "Proxmox"
type = "http"          # http | tcp | ping
target = "https://192.168.1.10:8006"
timeout = 3            # optional, seconds (default 5)
```

- **http** — GET the URL, up on any 2xx/3xx. TLS certs are *not* verified
  (it's a reachability monitor for homelabs full of self-signed certs).
- **tcp** — up if `host:port` accepts a connection.
- **ping** — up if one ICMP echo comes back (uses the system `ping`).

History is kept in memory (last 288 samples per check — 24h at 5-min interval).
Restart = clean slate, by design.

## Run it as a service

pm2: `pm2 start "python okboard.py" --name okboard`

systemd:

```ini
[Unit]
Description=okboard
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/okboard/okboard.py /opt/okboard/okboard.toml
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Test

```sh
python test_okboard.py
```

## Non-goals

Alerts, auth, persistence, multi-user, plugins. If you need those,
[Uptime Kuma](https://github.com/louislam/uptime-kuma) is excellent.
okboard stays one file you can read in five minutes.

## License

MIT

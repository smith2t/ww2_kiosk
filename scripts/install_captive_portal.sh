#!/bin/bash
# Install the captive-portal pieces for the WW2 Kiosk on a Raspberry Pi 5.
# When a phone or laptop joins WW2-Kiosk-AP, the OS auto-detects "captive"
# (because its built-in internet probe is intercepted) and pops up a
# browser pointed at the kiosk's web UI — no need to type a URL.
#
# Two pieces:
#   1. DNS hijack: NetworkManager's shared-mode dnsmasq resolves every
#      hostname to the AP IP (10.42.0.1). Only active while the AP is up.
#   2. Port-80 redirector: a tiny Python systemd service that 302-redirects
#      every HTTP request to http://10.42.0.1:8080/.
#
# Run with sudo:  sudo bash install_captive_portal.sh
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

# 1) DNS hijack (only takes effect while NM 'shared' mode is active)
cat > /etc/NetworkManager/dnsmasq-shared.d/captive.conf <<'DNS'
# Resolve every hostname to the kiosk AP IP so OS captive-portal probes
# (captive.apple.com, connectivitycheck.gstatic.com, www.msftncsi.com, ...)
# all hit our redirector, triggering the auto-popup browser on phones.
address=/#/10.42.0.1
DNS

# 2) Port-80 redirector
cat > /usr/local/bin/kiosk-captive-portal <<'PY'
#!/usr/bin/env python3
"""Captive-portal redirector. Any HTTP request to port 80 -> 302 to :8080."""
import http.server
import socketserver

REDIRECT_TO = "http://10.42.0.1:8080/"

class RedirectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", REDIRECT_TO)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", "0")
        self.end_headers()
    do_POST = do_HEAD = do_GET
    def log_message(self, *args, **kwargs):
        pass

with socketserver.ThreadingTCPServer(("", 80), RedirectHandler) as httpd:
    httpd.serve_forever()
PY
chmod 755 /usr/local/bin/kiosk-captive-portal

# 3) systemd unit for the redirector
cat > /etc/systemd/system/kiosk-captive-portal.service <<'UNIT'
[Unit]
Description=WW2 Kiosk captive portal redirector (port 80 -> 8080)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/kiosk-captive-portal
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now kiosk-captive-portal.service

echo
echo "Installed. Field behavior on a phone joining WW2-Kiosk-AP:"
echo "  - DNS for any hostname resolves to 10.42.0.1"
echo "  - HTTP request to anything (port 80) returns 302 to :8080"
echo "  - Phone OS pops up a captive-portal browser on the kiosk web UI"

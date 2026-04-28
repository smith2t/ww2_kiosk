#!/bin/bash
# Install the auto-AP-fallback for the WW2 Kiosk on a Raspberry Pi 5
# (Bookworm + NetworkManager). The Pi normally stays on whatever home WiFi
# it knows; if home WiFi is missing for 90 seconds, it brings up its own
# WPA2 access point (SSID WW2-Kiosk-AP, IP 10.42.0.1) so a phone or laptop
# can join and reach http://10.42.0.1:8080 to manage media and buttons.
#
# When home WiFi reappears later, the AP is dropped and the Pi reconnects.
#
# Run on the Pi with sudo:  sudo bash install_ap_fallback.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

AP_NAME="ww2-kiosk-ap"
AP_SSID="WW2-Kiosk-AP"
AP_PSK="ww2kiosk2024"
AP_IP="10.42.0.1/24"

# 1) NetworkManager AP profile (autoconnect off — the watchdog brings it up).
nmcli connection delete "$AP_NAME" 2>/dev/null || true
nmcli connection add type wifi ifname wlan0 con-name "$AP_NAME" autoconnect no \
    ssid "$AP_SSID" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    ipv4.addresses "$AP_IP" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$AP_PSK" >/dev/null

# 2) Watchdog script.
cat > /usr/local/bin/kiosk-net-watchdog <<'SH'
#!/bin/bash
# Drop into AP mode when home WiFi is missing for >90 sec; drop AP when
# home WiFi reappears.

set -u
AP_NAME="ww2-kiosk-ap"
LOG=/var/log/kiosk-net-watchdog.log
CHECK_INTERVAL=10
THRESHOLD=9    # 9 x 10s = 90 seconds without a non-AP wifi connection -> AP up

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

fail_count=0
log "watchdog starting (interval ${CHECK_INTERVAL}s, threshold ${THRESHOLD} cycles)"

while sleep "$CHECK_INTERVAL"; do
    in_ap=$(nmcli -t -f NAME c show --active | grep -c "^${AP_NAME}$" || true)
    has_client=$(nmcli -t -f NAME,TYPE c show --active | grep ":802-11-wireless$" | grep -cv "^${AP_NAME}:" || true)

    if [ "$has_client" -gt 0 ]; then
        fail_count=0
        if [ "$in_ap" -gt 0 ]; then
            log "home WiFi detected, dropping AP"
            nmcli c down "${AP_NAME}" >/dev/null 2>&1 || true
        fi
    else
        fail_count=$((fail_count + 1))
        if [ "$in_ap" -eq 0 ] && [ "$fail_count" -ge "$THRESHOLD" ]; then
            log "no home WiFi for ${THRESHOLD} cycles, activating AP"
            nmcli c up "${AP_NAME}" >/dev/null 2>&1 || true
        fi
    fi
done
SH
chmod 755 /usr/local/bin/kiosk-net-watchdog

# 3) systemd service for the watchdog.
cat > /etc/systemd/system/kiosk-net-watchdog.service <<'UNIT'
[Unit]
Description=WW2 Kiosk network watchdog (auto-AP fallback)
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/kiosk-net-watchdog
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now kiosk-net-watchdog.service

echo
echo "Installed. Field behavior:"
echo "  - 90s without a home WiFi connection -> AP comes up at 10.42.0.1"
echo "  - SSID: $AP_SSID  password: $AP_PSK"
echo "  - When AP is up: SSH sysadmin@10.42.0.1, web UI http://10.42.0.1:8080"
echo "  - Watchdog log: /var/log/kiosk-net-watchdog.log"

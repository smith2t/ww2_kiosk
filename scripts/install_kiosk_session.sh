#!/bin/bash
# Install the WW2 Kiosk as a minimal lightdm-managed X session.
#
# Replaces the prior systemd-service-on-top-of-xfce architecture with a
# dedicated session that runs ONLY the kiosk app + a bare openbox WM.
# Kills the desktop-intrusion problems (xfdesktop, xfce4-panel, nm-applet
# popups, VLC privacy dialogs) at the source.
#
# Run on the Pi with sudo: sudo bash install_kiosk_session.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

# Minimal X session script
cat > /usr/local/bin/kiosk-session <<'SH'
#!/bin/bash
# Minimal X session for the WW2 Kiosk.

xset s off
xset s noblank
xset -dpms

# Bare-bones window manager
openbox &

# Loop the kiosk so a crash, signal, or pkill auto-restarts it.
while true; do
    /home/orangepi/ww2_kiosk-main/venv/bin/python \
        /home/orangepi/ww2_kiosk-main/src/main.py
    EXIT=$?
    echo "[kiosk-session] kiosk exited code=$EXIT, restarting in 2s" >&2
    sleep 2
done
SH
chmod 755 /usr/local/bin/kiosk-session

# X session entry that lightdm can pick
cat > /usr/share/xsessions/ww2-kiosk.desktop <<'DT'
[Desktop Entry]
Name=WW2 Kiosk
Comment=Minimal kiosk session — pygame slideshow + button-triggered videos
Exec=/usr/local/bin/kiosk-session
Type=Application
DesktopNames=KIOSK
DT

# Lightdm autologin into the kiosk session
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-kiosk.conf <<'LDM'
# Auto-login the orangepi user into the WW2 Kiosk session at boot
[Seat:*]
autologin-user=orangepi
autologin-user-timeout=0
autologin-session=ww2-kiosk
user-session=ww2-kiosk
LDM

# Disable any prior systemd service so we don't double-launch
systemctl disable --now ww2-kiosk.service 2>/dev/null || true

echo "Installed. Restart lightdm (or reboot) to switch into the new session:"
echo "    sudo systemctl restart lightdm"

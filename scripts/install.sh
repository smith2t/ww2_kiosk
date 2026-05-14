#!/bin/bash
# WW2 Kiosk — full deployment for Raspberry Pi 5 running Raspberry Pi OS Bookworm.
#
# What it does:
#   * Installs apt prereqs (mpv, openbox, gpiozero, pygame, flask, fitz, ...)
#   * Builds the Python venv and installs requirements.txt
#   * Installs the lightdm kiosk session (kiosk-session script + .desktop + autologin)
#   * Installs the auto-AP-fallback watchdog (NetworkManager profile + service)
#   * Installs the captive-portal redirector (port 80 -> 8080)
#   * Sets the user's session preference so lightdm picks the kiosk session
#   * Restarts lightdm at the end so the kiosk comes up
#
# Idempotent: safe to re-run. Will not destroy media files, button mappings,
# or local config edits.
#
# Usage (run from inside the repo on the Pi):
#     sudo bash scripts/install.sh            # uses $SUDO_USER as the kiosk user
#     sudo bash scripts/install.sh otheruser  # overrides the kiosk user
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

# Resolve the kiosk user (the human who'll own the venv, run the X session,
# and hold the GPIO pins). Default to whoever invoked sudo.
KIOSK_USER="${1:-${SUDO_USER:-sysadmin}}"
if ! id "$KIOSK_USER" >/dev/null 2>&1; then
    echo "User '$KIOSK_USER' does not exist." >&2
    exit 1
fi
KIOSK_HOME=$(getent passwd "$KIOSK_USER" | cut -d: -f6)
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "==> Installing WW2 Kiosk for user '$KIOSK_USER' (home: $KIOSK_HOME)"
echo "==> Repo: $REPO_DIR"

# 1) APT prereqs ---------------------------------------------------------
echo
echo "==> Step 1/8: apt prereqs"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    python3-gpiozero python3-lgpio \
    python3-pygame python3-pil python3-yaml python3-flask \
    mpv ffmpeg \
    openbox \
    wmctrl xdotool x11-xserver-utils \
    lightdm \
    network-manager \
    samba samba-common-bin \
    libreoffice-impress libreoffice-core \
    >/dev/null

# 2) Python venv + requirements -----------------------------------------
echo
echo "==> Step 2/8: Python venv at $REPO_DIR/venv"
if [[ ! -d "$REPO_DIR/venv" ]]; then
    sudo -u "$KIOSK_USER" python3 -m venv --system-site-packages "$REPO_DIR/venv"
fi
sudo -u "$KIOSK_USER" "$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt" || true

# 3) Media + config dirs ------------------------------------------------
echo
echo "==> Step 3/8: media + config directories"
sudo -u "$KIOSK_USER" mkdir -p \
    "$REPO_DIR/media/videos" \
    "$REPO_DIR/media/pictures" \
    "$REPO_DIR/config"
# Initial empty button_mappings.json if missing
if [[ ! -f "$REPO_DIR/config/button_mappings.json" ]]; then
    sudo -u "$KIOSK_USER" tee "$REPO_DIR/config/button_mappings.json" >/dev/null <<'JSON'
{
  "mappings": {"1": "", "2": "", "3": "", "4": ""},
  "descriptions": {"1": "", "2": "", "3": "", "4": ""}
}
JSON
fi

# 4) Kiosk session (X session script + .desktop + lightdm autologin) ----
echo
echo "==> Step 4/8: kiosk session"
cat > /usr/local/bin/kiosk-session <<SH
#!/bin/bash
# Minimal X session for the WW2 Kiosk.
xset s off
xset s noblank
xset -dpms
openbox &
while true; do
    "$REPO_DIR/venv/bin/python" "$REPO_DIR/src/main.py"
    EXIT=\$?
    echo "[kiosk-session] kiosk exited code=\$EXIT, restarting in 2s" >&2
    sleep 2
done
SH
chmod 755 /usr/local/bin/kiosk-session

cat > /usr/share/xsessions/ww2-kiosk.desktop <<'DT'
[Desktop Entry]
Name=WW2 Kiosk
Comment=Minimal kiosk session — pygame slideshow + button-triggered videos
Exec=/usr/local/bin/kiosk-session
Type=Application
DesktopNames=KIOSK
DT

mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-kiosk.conf <<LDM
[Seat:*]
autologin-user=$KIOSK_USER
autologin-user-timeout=0
autologin-session=ww2-kiosk
user-session=ww2-kiosk
# Start X without a mouse cursor — the kiosk is driven by arcade buttons
# only, and a centered pointer is distracting on the slideshow.
xserver-command=X -nocursor
LDM

# Ensure the global lightdm.conf isn't forcing a different session.
if grep -qE "^user-session=" /etc/lightdm/lightdm.conf; then
    sed -i -E "s/^user-session=.*/user-session=ww2-kiosk/" /etc/lightdm/lightdm.conf
fi
if grep -qE "^autologin-session=" /etc/lightdm/lightdm.conf; then
    sed -i -E "s/^autologin-session=.*/autologin-session=ww2-kiosk/" /etc/lightdm/lightdm.conf
fi

# Per-user session preference (.dmrc + AccountsService) — Pi OS sometimes
# pins these to LXDE-pi-labwc and they override the conf.d files.
sudo -u "$KIOSK_USER" tee "$KIOSK_HOME/.dmrc" >/dev/null <<'DMRC'
[Desktop]
Session=ww2-kiosk
DMRC
mkdir -p /var/lib/AccountsService/users
cat > "/var/lib/AccountsService/users/$KIOSK_USER" <<AS
[User]
Session=ww2-kiosk
XSession=ww2-kiosk
SystemAccount=false
AS

# Disable the legacy systemd ww2-kiosk.service if it's enabled — lightdm now
# manages the kiosk lifecycle and a parallel systemd service would
# double-launch and fight for the GPIO pins.
systemctl disable --now ww2-kiosk.service 2>/dev/null || true

# 5) Auto-AP fallback ----------------------------------------------------
echo
echo "==> Step 5/8: auto-AP fallback"
bash "$REPO_DIR/scripts/install_ap_fallback.sh"

# 6) Captive portal ------------------------------------------------------
echo
echo "==> Step 6/8: captive portal"
bash "$REPO_DIR/scripts/install_captive_portal.sh"

# 7) NetworkManager hardening for the in-tree wifi driver --------------
# These tweaks are harmless on Pi 5 and were needed for stability on the
# Allwinner-board fallback. We apply them universally for safety.
echo
echo "==> Step 7/8: NetworkManager wifi tweaks"
ACTIVE_WIFI=$(nmcli -t -f NAME,TYPE,DEVICE c show --active 2>/dev/null \
    | awk -F: '$2=="802-11-wireless" && $3!~/^p2p-/{print $1; exit}')
if [[ -n "${ACTIVE_WIFI:-}" ]]; then
    nmcli c modify "$ACTIVE_WIFI" 802-11-wireless.powersave 2 ipv6.method ignore || true
fi

# 8) Restart lightdm ----------------------------------------------------
echo
echo "==> Step 8/8: restart lightdm to enter kiosk session"
echo "    (this will drop any X session currently on the Pi)"
systemctl daemon-reload
systemctl restart lightdm

echo
echo "Done. The Pi should be booting into the kiosk session now."
echo "  - Web UI:    http://<pi-ip>:8080"
echo "  - Field AP:  WW2-Kiosk-AP / ww2kiosk2024  -> http://10.42.0.1:8080"
echo "  - SSH:       $KIOSK_USER@<pi-ip>"

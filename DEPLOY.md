# Deploying the WW2 Kiosk to a New Raspberry Pi 5

Top-to-bottom procedure for setting up a fresh Pi as a working kiosk.
Estimated total time: **30–45 minutes** (most of it apt-get).

## Hardware checklist

- Raspberry Pi 5 (any RAM size)
- microSD card, **at least 16 GB**, Class 10 / A1 or better (Sandisk Extreme
  or Samsung Evo Plus recommended)
- 5V / 5A USB-C power supply (the official Pi 5 supply is ideal — others
  trigger low-voltage warnings)
- HDMI cable + display
- Network: either ethernet, or your home WiFi credentials handy
- 4 momentary push-buttons with built-in LEDs (arcade-style)
- 4× 220–330 Ω current-limiting resistors (one per LED)
- Hookup wire, breadboard or solder

## 1. Flash the SD card

Use **Raspberry Pi Imager** (https://www.raspberrypi.com/software/) and
choose **Raspberry Pi OS (64-bit) Bookworm — Desktop**. Before clicking
*Write*, open the gear icon and set:

- Hostname: `ww2-kiosk` (or anything memorable)
- **Enable SSH** with public-key authentication (paste your `~/.ssh/id_ed25519.pub`)
- Username: `sysadmin` (the install script defaults to this; pass any other
  name as an arg if you prefer)
- WiFi: your home network SSID and password (so the Pi can reach the
  internet for the apt installs in step 4)
- Locale settings as you like

Insert the card, boot the Pi, give it a minute to come up, then find its IP
on your network (router, `arp -a`, etc.).

## 2. SSH in

```bash
ssh sysadmin@<pi-ip>
```

If your home network is `192.168.86.x` and the Pi got `.64`:

```bash
ssh sysadmin@192.168.86.64
```

## 3. Get the repo onto the Pi

Two equivalent options.

**Option A — clone from a remote:**

```bash
git clone https://github.com/<you>/ww2_kiosk.git ~/ww2_kiosk-main
cd ~/ww2_kiosk-main
```

**Option B — rsync from your dev machine** (skip if the repo isn't pushed
to a remote yet):

On your laptop:

```bash
rsync -av --exclude venv --exclude '__pycache__' --exclude '.git' \
    ~/Documents/ww2_kiosk-main/ sysadmin@<pi-ip>:~/ww2_kiosk-main/
```

## 4. Run the deployment script

On the Pi:

```bash
cd ~/ww2_kiosk-main
sudo bash scripts/install.sh
```

What it does in order:

| Step | What happens |
|---|---|
| 1 | apt-get installs mpv, openbox, gpiozero, pygame, flask, wmctrl, … |
| 2 | Builds a Python venv at `./venv` and installs `requirements.txt` |
| 3 | Creates `media/videos/`, `media/pictures/`, default `button_mappings.json` |
| 4 | Installs the lightdm kiosk session (autologin into `kiosk-session`) |
| 5 | Installs the auto-AP-fallback watchdog + NetworkManager profile |
| 6 | Installs the captive-portal redirector (port 80 → 8080) |
| 7 | Tunes the WiFi connection (no power save, IPv6 off) |
| 8 | Restarts lightdm so the kiosk session starts immediately |

The whole script is idempotent — safe to re-run if anything failed.

## 5. Wire the buttons and LEDs

Power down before wiring (`sudo poweroff`).

| Item | BCM GPIO | Physical Pin | Notes |
|---|---|---|---|
| Button 1 (Blue) switch | 17 | 11 | switch to GND, no resistor needed |
| Button 2 (Green) switch | 27 | 13 | as above |
| Button 3 (Yellow) switch | 22 | 15 | as above |
| Button 4 (Red) switch | 23 | 16 | as above |
| LED 1 (+) with 220–330 Ω | 18 | 12 | LED− to common GND |
| LED 2 (+) with 220–330 Ω | 24 | 18 | as above |
| LED 3 (+) with 220–330 Ω | 25 | 22 | as above |
| LED 4 (+) with 220–330 Ω | 12 | 32 | as above |
| Common ground | — | any GND (6, 9, 14, 20, 25, 30, 34, 39) | one wire is enough |

**Twist each button's signal wire with its return ground wire** along the
whole length of the run. This cancels EMI pickup; without it long unshielded
button wires can fire phantom press events at several per second.

Power back on. Pi should boot straight into the kiosk slideshow.

## 6. Add media

Open the web UI from any device on the same network:

```
http://<pi-ip>:8080
```

- **Manage Media** — list / delete pictures and videos already on the kiosk
- **Upload Files** — multi-file or whole-folder upload, .jpg / .png / .pdf /
  .mp4 / .mkv / etc.
- **Configure Buttons** — pick a video for each colored button and write a
  description that shows on the kiosk's menu screen

## 7. Test

| Action | Expected |
|---|---|
| Wait | Slideshow cycles through `media/pictures/` |
| Press any button | Slideshow stops, 2×2 colored menu appears |
| Press a button on the menu | 3-2-1 countdown, video plays fullscreen |
| Press any button mid-video | Video stops, slideshow resumes |
| Don't press anything for 30 s on the menu | Returns to slideshow |

## Field deployment (no home WiFi available)

When the Pi is somewhere without your home network, after **90 seconds**
the network watchdog brings up the Pi's own access point automatically:

- SSID: `WW2-Kiosk-AP`
- Password: `ww2kiosk2024`
- Pi address on the AP: `10.42.0.1`

A phone or laptop joining that WiFi will get a captive-portal popup
pointing straight at the kiosk web UI — no URL to remember. From there the
operator can upload media, edit button descriptions, or reassign videos.

When the Pi is back on a known home WiFi, the AP automatically goes down
and the Pi rejoins.

## Logs (when something goes wrong)

| Component | File |
|---|---|
| Kiosk app (pygame, mpv, button events) | `~/.xsession-errors` on the Pi |
| AP/network watchdog | `/var/log/kiosk-net-watchdog.log` |
| Lightdm | `/var/log/lightdm/lightdm.log` |
| systemd services | `journalctl -u kiosk-captive-portal -u kiosk-net-watchdog` |

## Common problems

**Kiosk shows the desktop after boot.**
The lightdm session config didn't take. Check:
`/var/lib/AccountsService/users/<user>` should have `XSession=ww2-kiosk`,
and `/etc/lightdm/lightdm.conf` should have
`autologin-session=ww2-kiosk`. Re-run `sudo bash scripts/install.sh`.

**Buttons fire on their own (phantom presses).**
Long, untwisted button wires acting as antennas. Twist each button's
signal wire with its return ground wire end-to-end.

**Video plays but is choppy.**
Source video is probably either >1080p (Pi 5 hardware decode tops out
there comfortably for H.264) or has an unusual codec. Run
`scripts/transcode_and_upload.sh <source_dir>` from your dev machine to
pre-scale to 1920×1080 H.264 with letterbox padding.

**Web UI not reachable.**
Check the kiosk python is up: `pgrep -af main.py`. If not, look at
`~/.xsession-errors` for the crash. Lightdm-managed sessions auto-restart
the kiosk via the loop in `/usr/local/bin/kiosk-session`.

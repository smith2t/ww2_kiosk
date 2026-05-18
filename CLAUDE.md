# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WW2 Kiosk application running on a **Raspberry Pi 5 Model B** (BCM2712, 40-pin header). The kiosk uses a control panel of arcade buttons to choose which video to play. When idle, it flips through a slideshow of pictures after a timeout. The kiosk boots into the main display and starts with the default set of pictures, which can be replaced via the web UI or SMB over the network. The Pi can run as a WiFi access point (auto-fallback when home WiFi is unavailable) so a laptop or phone can join its network to manage it.

The Orange Pi Zero 2 W (Allwinner H618) is kept as an inactive fallback platform. Code auto-detects via `/proc/device-tree/model` and uses `gpiozero` on Pi 5, sysfs poller on Allwinner.

**Deployment facts (current as of 2026-05-18):**
- Project lives at `/home/sysadmin/ww2_kiosk-main/` on the Pi 5
- SSH user is `sysadmin` (alias `pi5` in `~/.ssh/config` on the dev Mac)
- OS is Debian 12 bookworm, Python 3.11
- Kiosk starts via lightdm as a custom X session (`ww2-kiosk.desktop`), NOT a systemd service. Auto-respawn is handled by the `while true` loop in `/usr/local/bin/kiosk-session`.

## Build and Development Commands

### Initial Setup
```bash
# Install system dependencies (run on Raspberry Pi)
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv vlc samba hostapd dnsmasq

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### Development Commands
```bash
# Run the kiosk application
python src/main.py

# Run in debug mode
python src/main.py --debug

# Run tests
pytest tests/

# Run specific test file
pytest tests/test_display.py

# Run with coverage
pytest --cov=src tests/

# Format code
black src/ tests/

# Lint code
pylint src/
flake8 src/

# Type checking
mypy src/
```

### System Service Management
```bash
# Install as systemd service
sudo cp systemd/ww2-kiosk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ww2-kiosk.service

# Start/stop/restart service
sudo systemctl start ww2-kiosk
sudo systemctl stop ww2-kiosk
sudo systemctl restart ww2-kiosk

# View logs
sudo journalctl -u ww2-kiosk -f
```

### Network Configuration
```bash
# Configure Raspberry Pi as Access Point
sudo ./scripts/configure_ap.sh

# Test SMB share
smbclient //localhost/media -U kiosk

# Restart network services
sudo systemctl restart hostapd
sudo systemctl restart smbd
```

## Code Architecture

### System Overview
The WW2 Kiosk is a Python-based multimedia display system running on Raspberry Pi that:
- Displays historical WW2 videos triggered by physical control panel buttons
- Shows picture slideshows during idle periods
- Provides network management capabilities via WiFi AP mode
- Allows media updates through SMB file sharing

### Core Components

#### 1. Main Application (`src/main.py`)
- Entry point that initializes all subsystems
- Manages application lifecycle and graceful shutdown
- Coordinates between display, input, and network services

#### 2. Display Manager (`src/display/`)
- **video_player.py**: Handles video playback using VLC or OMXPlayer
- **slideshow.py**: Manages picture slideshow with configurable transitions
- **display_controller.py**: Switches between video/slideshow modes based on events

#### 3. Input Handler (`src/input/`)
- **gpio_controller.py**: Interfaces with GPIO pins for button detection
- **button_mapper.py**: Maps physical buttons to video files
- **debouncer.py**: Prevents accidental multiple triggers

#### 4. Media Manager (`src/media/`)
- **content_loader.py**: Loads and validates media files
- **playlist_manager.py**: Manages video and picture playlists
- **file_watcher.py**: Monitors for new media via SMB

#### 5. Network Services (`src/network/`)
- **ap_manager.py**: Configures Raspberry Pi as WiFi access point
- **smb_server.py**: Provides SMB/CIFS file sharing for media updates
- **web_interface.py**: Optional web-based management interface

#### 6. Configuration (`src/config/`)
- **settings.py**: Centralized configuration management
- **config.yaml**: User-editable settings file

### Directory Structure
```
ww2_kiosk/
├── src/
│   ├── main.py
│   ├── display/
│   ├── input/
│   ├── media/
│   ├── network/
│   └── config/
├── media/
│   ├── videos/
│   └── pictures/
├── scripts/
│   ├── setup.sh
│   ├── install_dependencies.sh
│   └── configure_boot.sh
├── systemd/
│   └── ww2-kiosk.service
├── config/
│   ├── config.yaml
│   └── button_mappings.json
├── tests/
├── requirements.txt
└── README.md
```

### System Architecture Decisions

#### Display System
- Use **pygame** or **tkinter** for GUI framework
- **VLC Python bindings** for video playback (hardware acceleration)
- **Pillow** for image processing and slideshow transitions

#### Input System
- **RPi.GPIO** library for button input handling
- Hardware debouncing with software backup
- Configurable button-to-video mappings via JSON

#### Network Architecture
- **hostapd** for WiFi AP functionality
- **Samba** for cross-platform file sharing
- Flask or FastAPI for optional web management interface

#### State Management
- Event-driven architecture using Python's `asyncio`
- State machine for mode transitions (idle → video → idle)
- Configurable timeout for returning to slideshow

### Key Design Patterns
- **Observer Pattern**: For event handling between components
- **Singleton Pattern**: For display and GPIO controllers
- **Factory Pattern**: For media player creation
- **Strategy Pattern**: For different display modes

## Deployment Considerations

### Raspberry Pi Configuration
- **Auto-login**: Configure Pi to auto-login and start kiosk on boot
- **Display Settings**: Disable screen blanking and power management
- **GPU Memory Split**: Allocate sufficient GPU memory for video playback (128MB minimum)
- **Boot to Kiosk**: Use systemd service to launch application automatically

### Security Considerations
- SMB share should use basic authentication (username: `kiosk`, configurable password)
- WiFi AP should use WPA2 with a strong password
- Restrict SMB access to media directories only
- Consider read-only filesystem for OS partition

### Performance Optimization
- Pre-load next image during slideshow display
- Use hardware-accelerated video decoding
- Implement lazy loading for large media libraries
- Cache thumbnails for faster browsing

### Error Handling
- Graceful fallback if video file is missing/corrupted
- Auto-restart on application crash
- Logging to persistent storage for debugging
- Network connectivity monitoring

## Hardware Configuration

The GPIO implementation lives in `src/input/orangepi_gpio.py` and uses **Linux sysfs directly** (`/sys/class/gpio/export`). It does NOT use `RPi.GPIO`, `gpiozero`, or `OPi.GPIO` — these libraries are unreliable on the H618. Pin numbers throughout the codebase are **Allwinner H618 Linux GPIO chip numbers**, not Raspberry Pi BCM numbers.

Full pinout details: see [`ORANGEPI_WIRING_GUIDE.md`](ORANGEPI_WIRING_GUIDE.md) and `docs/ORANGEPI_GPIO_PINOUT.md`.

### Button Pin Mappings (active LOW, internal pull-up)
| Button | GPIO # | Physical Pin |
|--------|--------|--------------|
| Button 1 → Video 1 | 229 | Pin 11 |
| Button 2 → Video 2 | 230 | Pin 12 |
| Button 3 → Video 3 | 231 | Pin 13 |
| Button 4 → Video 4 | 232 | Pin 15 |

Wire each button between its GPIO pin and any GND pin. No external resistors needed.

### LED Pin Mappings (active HIGH)
| LED | GPIO # | Physical Pin |
|-----|--------|--------------|
| LED 1 | 78  | Pin 16 |
| LED 2 | 226 | Pin 18 |
| LED 3 | 227 | Pin 22 |
| LED 4 | 228 | Pin 24 |

Wire LED+ → 220–330Ω resistor → GPIO pin; LED− → GND.

### Button Press Detection
- Active LOW (pressed = 0, released = 1)
- Debounce time: 50ms (in `src/input/debouncer.py` and the sysfs monitor loop)
- Detection: 10ms polling of sysfs `value` file with software debounce

### Default Network Configuration
- **AP SSID**: `WW2-Kiosk-AP`
- **AP IP**: `192.168.4.1`
- **SMB Share**: `\\192.168.4.1\media`
- **Web Interface**: `http://192.168.4.1:8080` (if enabled)

### Media Requirements
- **Video Formats**: MP4, AVI, MKV (H.264 recommended)
- **Image Formats**: JPG, PNG, BMP
- **Max Video Resolution**: 1920x1080 (1080p)
- **Slideshow Interval**: 10 seconds (configurable)
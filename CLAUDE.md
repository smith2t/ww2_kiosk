# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a WW2 Kiosk application running on a respberry pi. this kiosk uses input a control panel on which videos it will play. when the kiosk is not in use it will flip through a series of pictures after a timout after the last video played from the button push. this project will be using python to enable the kiosk. the kiosk should boot ino the main display and atart with the default set of pictures that are easily replaced via smb over the network with a simple password to prevent tampering. the raspberry py should be in a stanalone mode that will allow someone to join its network to manage it with a computer.

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

### Button Wiring Schematic (Breadboard Setup)

```
Raspberry Pi GPIO Layout & Button Connections:

         [Raspberry Pi GPIO Header]
         3.3V ----[Pin 1]
         5V   ----[Pin 2]
         GPIO2----[Pin 3]
         5V   ----[Pin 4]
         GPIO3----[Pin 5]
         GND  ----[Pin 6]  ←──┬─── Connect to breadboard ground rail
         GPIO4----[Pin 7]      │
         GPIO14---[Pin 8]      │
         GND  ----[Pin 9]  ←───┤
         GPIO15---[Pin 10]     │
         GPIO17---[Pin 11] ←─┐ │ [Button 1]
         GPIO18---[Pin 12]   │ │
         GPIO27---[Pin 13] ←─┼─┼─ [Button 2]
         GND  ----[Pin 14]   │ │
         GPIO22---[Pin 15] ←─┼─┼─ [Button 3]
         GPIO23---[Pin 16] ←─┼─┼─ [Button 4]
         3.3V ----[Pin 17]   │ │
         GPIO24---[Pin 18]   │ │
                              │ │
Breadboard Wiring:           │ │
                             │ │
    [BREADBOARD]             │ │
    ═══════════════════════════════════════════
    (-) Ground Rail ←────────┘ │ (Connected to GND)
    ═══════════════════════════════════════════
                             │ │
    Button 1:  [GPIO17]──────┘ └──→[Button]───→[GND]
    Button 2:  [GPIO27]────────────→[Button]───→[GND]
    Button 3:  [GPIO22]────────────→[Button]───→[GND]
    Button 4:  [GPIO23]────────────→[Button]───→[GND]
```

### Detailed Wiring Instructions

#### Required Components (from CanaKit):
- 4x Momentary push buttons
- 4x 10kΩ resistors (optional, using internal pull-ups)
- Jumper wires (male-to-male and male-to-female)
- 1x Breadboard

#### Step-by-Step Connection:
1. **Ground Rail Setup**
   - Connect Raspberry Pi GND (Pin 6 or 9) to breadboard negative rail
   
2. **Button Connections** (for each button):
   - Insert button across the center channel of breadboard
   - Connect one side of button to ground rail
   - Connect other side to respective GPIO pin:
     * Button 1 → GPIO 17 (Pin 11)
     * Button 2 → GPIO 27 (Pin 13)
     * Button 3 → GPIO 22 (Pin 15)
     * Button 4 → GPIO 23 (Pin 16)

3. **Pull-up Configuration**
   - Using software pull-ups (recommended):
     ```python
     GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
     GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
     GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_UP)
     GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)
     ```
   - Alternative hardware pull-ups:
     * Add 10kΩ resistor from each GPIO pin to 3.3V

### Button Press Detection
- Buttons are active LOW (pressed = 0, released = 1)
- Debounce time: 50ms (configurable)
- Edge detection: FALLING edge for button press

### GPIO Pin Mappings
- **GPIO 17** (Pin 11): Button 1 → Video 1
- **GPIO 27** (Pin 13): Button 2 → Video 2
- **GPIO 22** (Pin 15): Button 3 → Video 3
- **GPIO 23** (Pin 16): Button 4 → Video 4

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
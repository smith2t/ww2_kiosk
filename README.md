# WW2 Kiosk

A Raspberry Pi-based interactive kiosk system for displaying WW2 historical content through button-triggered videos and picture slideshows.

## Features

- **Interactive Video Playback**: Physical control panel with 4 buttons to trigger specific WW2 videos
- **Picture Slideshow**: Automatic slideshow of historical images during idle periods
- **Network Management**: Built-in WiFi access point for remote administration
- **Media Updates**: SMB file sharing for easy content updates over the network
- **Auto-start**: Boots directly into kiosk mode on power-up

## Hardware Requirements

- Raspberry Pi 4 (recommended) or Pi 3B+
- MicroSD card (16GB minimum)
- HDMI display
- 4x momentary push buttons
- Breadboard and jumper wires
- 5V power supply

## Installation

### Quick Setup

1. Flash Raspberry Pi OS (32-bit) to your SD card
2. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/ww2_kiosk.git
   cd ww2_kiosk
   ```
3. Run the setup script:
   ```bash
   chmod +x scripts/setup.sh
   sudo ./scripts/setup.sh
   ```
4. Add your media files:
   - Videos: `/home/pi/ww2_kiosk/media/videos/`
   - Pictures: `/home/pi/ww2_kiosk/media/pictures/`
5. Reboot the system:
   ```bash
   sudo reboot
   ```

## Hardware Setup

### Button Wiring

Connect buttons to the following GPIO pins:
- Button 1: GPIO 17 (Pin 11)
- Button 2: GPIO 27 (Pin 13)
- Button 3: GPIO 22 (Pin 15)
- Button 4: GPIO 23 (Pin 16)

Each button should connect between its GPIO pin and ground. Internal pull-up resistors are enabled in software.

## Configuration

Edit `/home/pi/ww2_kiosk/config/config.yaml` to customize:
- Display settings (resolution, slideshow timing)
- GPIO pin assignments
- Network configuration (WiFi SSID, passwords)
- Media directories

### Button Mappings

Edit `/home/pi/ww2_kiosk/config/button_mappings.json` to map buttons to specific videos:
```json
{
  "mappings": {
    "1": "dday_normandy.mp4",
    "2": "pearl_harbor.mp4",
    "3": "battle_of_britain.mp4",
    "4": "midway.mp4"
  }
}
```

## Network Access

### WiFi Access Point
- SSID: `WW2-Kiosk-AP`
- Password: `ww2kiosk2024`
- IP: `192.168.4.1`

### SMB File Share
- Path: `\\192.168.4.1\media`
- Username: `kiosk`
- Password: `kiosk123`

## Development

### Running Locally
```bash
cd /home/pi/ww2_kiosk
source venv/bin/activate
python src/main.py --debug
```

### Running Tests
```bash
pytest tests/
```

## Troubleshooting

### View Logs
```bash
sudo journalctl -u ww2-kiosk -f
```

### Restart Service
```bash
sudo systemctl restart ww2-kiosk
```

### Check Service Status
```bash
sudo systemctl status ww2-kiosk
```

## Media Format Support

### Videos
- MP4 (H.264 recommended)
- AVI
- MKV
- Maximum resolution: 1920x1080

### Images
- JPEG/JPG
- PNG
- BMP

## License

MIT License - See LICENSE file for details

## Support

For issues or questions, please open an issue on GitHub.
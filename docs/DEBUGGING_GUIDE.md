# WW2 Kiosk Debugging & Troubleshooting Guide

## 🚪 **How to Exit Kiosk Mode**

### Method 1: Keyboard Shortcuts (Recommended)
When the kiosk is running, use these key combinations:

- **`Ctrl + C`** - Graceful shutdown (if terminal is accessible)
- **`Ctrl + Alt + T`** - Open terminal (Ubuntu/Debian)
- **`Ctrl + Alt + F1`** - Switch to TTY1 console
- **`Ctrl + Alt + F2`** - Switch to TTY2 console
- **`Alt + F4`** - Close current window (if in windowed mode)
- **`Ctrl + Alt + Del`** - System restart menu

### Method 2: Magic Button Combination
Hold **Button 1 + Button 4** simultaneously for **5 seconds** to trigger emergency exit.

### Method 3: SSH Access (Remote)
```bash
# From another computer on the same network
ssh orangepi@192.168.4.1  # WiFi AP mode
ssh orangepi@[IP_ADDRESS]  # If connected to home WiFi

# Stop the kiosk service
sudo systemctl stop ww2-kiosk

# Kill the kiosk process
sudo pkill -f "python.*main.py"
```

### Method 4: Physical Access
```bash
# Connect keyboard and monitor, then:

# Switch to console
Ctrl + Alt + F1

# Login as orangepi
# Stop the service
sudo systemctl stop ww2-kiosk

# Start desktop environment
startx
```

### Method 5: Emergency Boot Mode
```bash
# During boot, edit boot parameters
# Add: systemd.unit=multi-user.target
# This boots to console instead of kiosk
```

---

## 🛠️ **Troubleshooting Commands**

### Check Kiosk Status
```bash
# Service status
sudo systemctl status ww2-kiosk

# View logs
sudo journalctl -u ww2-kiosk -f

# Check if process is running
ps aux | grep python | grep main.py

# Check GPIO status
cat /sys/kernel/debug/gpio
```

### Restart Services
```bash
# Restart kiosk
sudo systemctl restart ww2-kiosk

# Restart network
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq

# Restart SMB
sudo systemctl restart smbd
```

### Manual Testing
```bash
# Test kiosk manually
cd /home/orangepi/ww2_kiosk-main
source venv/bin/activate
python src/main.py --debug

# Test components individually
python test_buttons.py
python test_leds.py
python test_structure.py
```

### Emergency Recovery
```bash
# If kiosk won't start
sudo systemctl disable ww2-kiosk  # Disable auto-start
sudo reboot

# If GPIO issues
sudo systemctl stop ww2-kiosk
echo "65" | sudo tee /sys/class/gpio/unexport  # Cleanup GPIO
echo "69" | sudo tee /sys/class/gpio/unexport
# ... repeat for other pins
```

---

## 🔧 **Common Issues & Solutions**

### Issue: Kiosk won't exit with Ctrl+C
**Solution:** Use emergency button combination or SSH

### Issue: Black screen on boot
**Solution:**
```bash
# SSH in and check logs
sudo journalctl -u ww2-kiosk --no-pager | tail -50

# Try manual start
sudo systemctl stop ww2-kiosk
cd /home/orangepi/ww2_kiosk-main
python src/main.py --debug
```

### Issue: Buttons not responding
**Solution:**
```bash
# Check GPIO permissions
sudo python3 test_buttons.py

# Reset GPIO
sudo systemctl restart ww2-kiosk
```

### Issue: No video playback
**Solution:**
```bash
# Test video player
vlc --version
omxplayer --version

# Check video files
ls -la media/videos/
```

### Issue: No network access
**Solution:**
```bash
# Check WiFi AP
sudo systemctl status hostapd
sudo systemctl status dnsmasq

# Restart network services
sudo systemctl restart hostapd dnsmasq
```

---

## 🚨 **Emergency Recovery Mode**

If the kiosk is completely unresponsive:

### 1. Hard Reset
- Unplug power for 10 seconds
- Plug back in
- Immediately hold Ctrl+Alt+F1 during boot

### 2. Boot to Console
Edit `/boot/armbianEnv.txt` and add:
```
extraargs=systemd.unit=multi-user.target
```

### 3. Disable Kiosk Service
```bash
sudo systemctl disable ww2-kiosk
sudo systemctl mask ww2-kiosk  # Completely prevent startup
```

### 4. Re-enable When Fixed
```bash
sudo systemctl unmask ww2-kiosk
sudo systemctl enable ww2-kiosk
```

---

## 📊 **Monitoring & Logs**

### Real-time Monitoring
```bash
# Watch logs live
sudo journalctl -u ww2-kiosk -f

# Monitor system resources
htop

# Watch GPIO activity
watch -n 1 'cat /sys/kernel/debug/gpio | grep gpio'
```

### Log Locations
```bash
# Systemd logs
/var/log/journal/

# Application logs (if configured)
/home/orangepi/ww2_kiosk-main/logs/

# System logs
/var/log/syslog
```

---

## 🔄 **Maintenance Mode**

### Enter Maintenance Mode
```bash
# Stop kiosk and start maintenance
sudo systemctl stop ww2-kiosk
cd /home/orangepi/ww2_kiosk-main

# Update media files
# Upload new videos/images
# Test configuration changes

# Exit maintenance mode
sudo systemctl start ww2-kiosk
```

### Safe Shutdown
```bash
# Graceful shutdown
sudo systemctl stop ww2-kiosk
sudo shutdown -h now

# Restart
sudo systemctl stop ww2-kiosk
sudo reboot
```

---

## 🎯 **Quick Reference Card**

Print this for emergency access:

```
EMERGENCY KIOSK EXIT METHODS:
══════════════════════════════

1. Keyboard: Ctrl + Alt + F1
2. Buttons: Hold Button 1 + 4 for 5 sec
3. SSH: ssh orangepi@192.168.4.1
4. Stop Service: sudo systemctl stop ww2-kiosk
5. Emergency: Unplug power, reconnect

DEBUG COMMANDS:
═══════════════
sudo journalctl -u ww2-kiosk -f  # View logs
sudo systemctl status ww2-kiosk  # Check status
python test_buttons.py           # Test hardware

DISABLE AUTO-START:
═══════════════════
sudo systemctl disable ww2-kiosk
```
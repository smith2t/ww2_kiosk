#!/bin/bash

# Configure Raspberry Pi boot settings for kiosk mode

set -e

echo "Configuring boot settings..."

# Enable auto-login to console
sudo raspi-config nonint do_boot_behaviour B2

# Disable screen blanking
echo "Disabling screen blanking..."
sudo bash -c 'echo "consoleblank=0" >> /boot/cmdline.txt'

# Configure GPU memory split
echo "Setting GPU memory split..."
sudo raspi-config nonint do_memory_split 128

# Disable overscan
sudo raspi-config nonint do_overscan 1

# Create autostart script
echo "Creating autostart script..."
cat > /home/pi/.bashrc << 'EOF'
# Auto-start WW2 Kiosk on login
if [ -z "$SSH_CLIENT" ] && [ -z "$SSH_TTY" ]; then
    cd /home/pi/ww2_kiosk
    source venv/bin/activate
    python src/main.py
fi
EOF

# Disable WiFi power management
echo "Disabling WiFi power management..."
sudo bash -c 'echo "options 8192cu rtw_power_mgnt=0 rtw_enusbss=0" > /etc/modprobe.d/8192cu.conf'

# Configure HDMI settings
echo "Configuring HDMI settings..."
sudo bash -c 'cat >> /boot/config.txt << EOF

# WW2 Kiosk HDMI Configuration
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=82
hdmi_drive=2
disable_overscan=1
EOF'

echo "Boot configuration complete!"
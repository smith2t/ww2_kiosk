#!/bin/bash

# Configure Raspberry Pi boot settings for kiosk mode

set -e

echo "Configuring boot settings..."

# Check if running on Raspberry Pi
if [ -f /usr/bin/raspi-config ]; then
    echo "Detected Raspberry Pi system"
    
    # Skip raspi-config commands and directly modify config files
    echo "Note: Configuring Raspberry Pi settings directly..."
    
    # Configure GPU memory split directly
    echo "Setting GPU memory split to 128MB..."
    if [ -f /boot/config.txt ]; then
        sudo bash -c 'grep -q "^gpu_mem=" /boot/config.txt && sed -i "s/^gpu_mem=.*/gpu_mem=128/" /boot/config.txt || echo "gpu_mem=128" >> /boot/config.txt'
        echo "GPU memory set via /boot/config.txt"
    elif [ -f /boot/firmware/config.txt ]; then
        # Newer Raspberry Pi OS versions use /boot/firmware/
        sudo bash -c 'grep -q "^gpu_mem=" /boot/firmware/config.txt && sed -i "s/^gpu_mem=.*/gpu_mem=128/" /boot/firmware/config.txt || echo "gpu_mem=128" >> /boot/firmware/config.txt'
        echo "GPU memory set via /boot/firmware/config.txt"
    else
        echo "Warning: Could not find config.txt - GPU memory split may need manual configuration"
    fi
    
    # Disable overscan directly in config
    CONFIG_FILE=""
    if [ -f /boot/config.txt ]; then
        CONFIG_FILE="/boot/config.txt"
    elif [ -f /boot/firmware/config.txt ]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    fi
    
    if [ -n "$CONFIG_FILE" ]; then
        echo "Disabling overscan in $CONFIG_FILE..."
        sudo bash -c "grep -q '^disable_overscan=' $CONFIG_FILE && sed -i 's/^disable_overscan=.*/disable_overscan=1/' $CONFIG_FILE || echo 'disable_overscan=1' >> $CONFIG_FILE"
    fi
    
    # Auto-login configuration
    echo ""
    echo "IMPORTANT: Auto-login must be configured manually:"
    echo "  1. Run: sudo raspi-config"
    echo "  2. Go to: System Options -> Boot / Auto Login"
    echo "  3. Select: Console Autologin"
    echo ""
    
    # Disable screen blanking - check multiple locations
    if [ -f /boot/cmdline.txt ]; then
        echo "Disabling screen blanking..."
        grep -q "consoleblank=0" /boot/cmdline.txt || sudo bash -c 'sed -i "s/$/ consoleblank=0/" /boot/cmdline.txt'
    elif [ -f /boot/firmware/cmdline.txt ]; then
        echo "Disabling screen blanking..."
        grep -q "consoleblank=0" /boot/firmware/cmdline.txt || sudo bash -c 'sed -i "s/$/ consoleblank=0/" /boot/firmware/cmdline.txt'
    fi
else
    echo "Not running on Raspberry Pi - skipping Pi-specific configuration"
    echo "These settings will need to be configured manually on the target Pi"
fi

# Create autostart script
if [ -d /home/pi ]; then
    echo "Creating autostart script..."
    cat >> /home/pi/.bashrc << 'EOF'

# Auto-start WW2 Kiosk on login
if [ -z "$SSH_CLIENT" ] && [ -z "$SSH_TTY" ]; then
    cd /home/pi/ww2_kiosk
    source venv/bin/activate
    python src/main.py
fi
EOF
else
    echo "Skipping autostart configuration - no /home/pi directory"
fi

# Disable WiFi power management (Pi-specific)
if [ -d /etc/modprobe.d ]; then
    echo "Disabling WiFi power management..."
    sudo bash -c 'echo "options 8192cu rtw_power_mgnt=0 rtw_enusbss=0" > /etc/modprobe.d/8192cu.conf' 2>/dev/null || true
fi

# Configure HDMI settings (Pi-specific)
CONFIG_FILE=""
if [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
elif [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
fi

if [ -n "$CONFIG_FILE" ]; then
    echo "Configuring HDMI settings in $CONFIG_FILE..."
    
    # Check if HDMI settings already exist
    if ! grep -q "# WW2 Kiosk HDMI Configuration" "$CONFIG_FILE"; then
        sudo bash -c "cat >> $CONFIG_FILE << EOF

# WW2 Kiosk HDMI Configuration
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=82
hdmi_drive=2
disable_overscan=1
EOF"
    else
        echo "HDMI configuration already present"
    fi
else
    echo "Skipping HDMI configuration - config.txt not found"
fi

echo "Boot configuration complete!"
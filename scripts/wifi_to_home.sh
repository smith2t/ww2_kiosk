#!/bin/bash

# Permanently switch to home WiFi mode
# Disables AP mode and connects to home network

# Configuration
HOME_SSID="HomeFront"
HOME_PASSWORD="thisismyhouse"

echo "================================"
echo "Switch to Home WiFi - Permanent"
echo "================================"

# Disable AP services from starting on boot
echo "Disabling AP services..."
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq

# Configure WiFi using raspi-config method (persistent)
echo "Configuring WiFi connection..."

# Create wpa_supplicant configuration
sudo bash -c "cat > /etc/wpa_supplicant/wpa_supplicant.conf << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
    ssid=\"$HOME_SSID\"
    psk=\"$HOME_PASSWORD\"
    key_mgmt=WPA-PSK
    priority=1
}
EOF"

# Enable and restart networking
echo "Restarting network services..."
sudo systemctl enable wpa_supplicant
sudo systemctl restart wpa_supplicant
sudo systemctl restart dhcpcd

# Wait for connection
echo "Waiting for connection..."
sleep 5

# Get IP address
IP_ADDR=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)

echo ""
echo "================================"
echo "Switched to Home WiFi!"
echo "================================"
echo "Network: $HOME_SSID"
echo "IP Address: $IP_ADDR"
echo ""
echo "The Pi will now connect to your home WiFi on boot."
echo "To re-enable AP mode, run: ./scripts/wifi_to_ap.sh"
echo ""
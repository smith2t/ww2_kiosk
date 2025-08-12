#!/bin/bash

# Switch back to AP mode permanently
# Re-enables the kiosk access point

echo "================================"
echo "Switch to AP Mode - Permanent"
echo "================================"

# Disable WiFi client
echo "Disabling WiFi client mode..."
sudo systemctl stop wpa_supplicant
sudo systemctl disable wpa_supplicant

# Clear WiFi configuration
sudo bash -c "> /etc/wpa_supplicant/wpa_supplicant.conf"

# Re-enable AP services
echo "Enabling AP services..."
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

# Configure static IP
echo "Configuring network..."
sudo ip addr flush dev wlan0
sudo ip link set wlan0 down
sleep 1
sudo ip link set wlan0 up
sudo ip addr add 192.168.4.1/24 dev wlan0

# Start AP services
echo "Starting AP services..."
sudo systemctl start hostapd
sudo systemctl start dnsmasq

echo ""
echo "================================"
echo "Switched to AP Mode!"
echo "================================"
echo "WiFi Network: WW2-Kiosk-AP"
echo "Password: ww2kiosk2024"
echo "IP Address: 192.168.4.1"
echo ""
echo "The Pi will now start in AP mode on boot."
echo "To connect to home WiFi, run: ./scripts/wifi_to_home.sh"
echo ""
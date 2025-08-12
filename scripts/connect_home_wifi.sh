#!/bin/bash

# Simple script to connect to home WiFi (no AP mode)
# This gets you connected so you can download fixes

HOME_SSID="HomeFront"
HOME_PASSWORD="thisismyhouse"

echo "================================"
echo "Connecting to Home WiFi"
echo "================================"

# Stop conflicting services
echo "Stopping conflicting services..."
sudo systemctl stop hostapd 2>/dev/null || true
sudo systemctl stop dnsmasq 2>/dev/null || true
sudo killall wpa_supplicant 2>/dev/null || true

# Reset wlan0
echo "Resetting wlan0..."
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sleep 1
sudo ip link set wlan0 up

# Remove deny interface if it exists
echo "Updating dhcpcd configuration..."
sudo sed -i '/denyinterfaces wlan0/d' /etc/dhcpcd.conf 2>/dev/null || true

# Configure WiFi
echo "Configuring WiFi connection..."
sudo bash -c "cat > /etc/wpa_supplicant/wpa_supplicant.conf << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
    ssid=\"$HOME_SSID\"
    psk=\"$HOME_PASSWORD\"
    key_mgmt=WPA-PSK
}
EOF"

# Restart services
echo "Starting WiFi services..."
sudo systemctl restart dhcpcd
sudo systemctl restart wpa_supplicant

# Wait for connection
echo "Waiting for connection..."
for i in {1..10}; do
    sleep 2
    if ip addr show wlan0 | grep -q "inet "; then
        break
    fi
    echo -n "."
done
echo ""

# Show result
IP_ADDR=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)

if [ -n "$IP_ADDR" ]; then
    echo ""
    echo "================================"
    echo "Connected Successfully!"
    echo "================================"
    echo "Network: $HOME_SSID"
    echo "IP Address: $IP_ADDR"
    echo ""
    echo "You can now SSH to: pi@$IP_ADDR"
else
    echo ""
    echo "Connection failed. Trying alternative method..."
    
    # Alternative method using wpa_supplicant directly
    sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf
    sudo dhclient wlan0
    
    sleep 5
    IP_ADDR=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)
    
    if [ -n "$IP_ADDR" ]; then
        echo "Connected with alternative method!"
        echo "IP Address: $IP_ADDR"
    else
        echo "Failed to connect. Please check:"
        echo "1. WiFi credentials are correct"
        echo "2. Router is in range"
        echo "3. Check logs: sudo journalctl -u wpa_supplicant -n 20"
    fi
fi
#!/bin/bash

# Temporarily connect to home WiFi for 10 minutes, then return to AP mode
# This prevents getting locked out if something goes wrong

# Configuration
HOME_SSID="HomeFront"
HOME_PASSWORD="thisismyhouse"
AP_INTERFACE="wlan0"
TIMEOUT_MINUTES=10

echo "================================"
echo "Temporary Home WiFi Connection"
echo "================================"
echo "Will connect to home WiFi for $TIMEOUT_MINUTES minutes"
echo "Then automatically return to AP mode"
echo ""

# Stop AP services
echo "Stopping AP services..."
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

# Kill any existing wpa_supplicant
sudo killall wpa_supplicant 2>/dev/null || true
sleep 2

# Reset interface
sudo ip addr flush dev $AP_INTERFACE
sudo ip link set $AP_INTERFACE down
sleep 1
sudo ip link set $AP_INTERFACE up

# Configure wpa_supplicant for home network
echo "Configuring home WiFi..."
sudo bash -c "cat > /tmp/wpa_supplicant.conf << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={
    ssid=\"$HOME_SSID\"
    psk=\"$HOME_PASSWORD\"
    key_mgmt=WPA-PSK
}
EOF"

# Start wpa_supplicant
echo "Connecting to $HOME_SSID..."
sudo wpa_supplicant -B -i $AP_INTERFACE -c /tmp/wpa_supplicant.conf
sleep 3

# Get IP address via DHCP
echo "Getting IP address..."
sudo dhclient $AP_INTERFACE
sleep 3

# Show connection info
IP_ADDR=$(ip addr show $AP_INTERFACE | grep "inet " | awk '{print $2}' | cut -d/ -f1)
echo ""
echo "================================"
echo "Connected to Home WiFi!"
echo "================================"
echo "Network: $HOME_SSID"
echo "IP Address: $IP_ADDR"
echo ""
echo "You can now SSH to: pi@$IP_ADDR"
echo ""
echo "IMPORTANT: Will return to AP mode in $TIMEOUT_MINUTES minutes!"
echo "To cancel auto-return: sudo pkill -f wifi_home_temp.sh"
echo ""

# Schedule return to AP mode
(
    sleep $((TIMEOUT_MINUTES * 60))
    
    echo "Timeout reached - returning to AP mode..."
    
    # Kill wpa_supplicant and dhclient
    sudo killall wpa_supplicant 2>/dev/null || true
    sudo killall dhclient 2>/dev/null || true
    sleep 2
    
    # Reset interface
    sudo ip addr flush dev $AP_INTERFACE
    sudo ip link set $AP_INTERFACE down
    sleep 1
    sudo ip link set $AP_INTERFACE up
    
    # Set static IP for AP
    sudo ip addr add 192.168.4.1/24 dev $AP_INTERFACE
    
    # Start AP services
    sudo systemctl start hostapd
    sudo systemctl start dnsmasq
    
    echo "Returned to AP mode - WW2-Kiosk-AP"
) &

echo "Auto-return scheduled. Script complete."
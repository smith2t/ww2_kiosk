#!/bin/bash

# Toggle between AP mode and home WiFi
# This script automatically switches between modes

# Configuration
HOME_SSID="HomeFront"
HOME_PASSWORD="thisismyhouse"
AP_INTERFACE="wlan0"

echo "================================"
echo "WiFi Mode Toggle Script"
echo "================================"

# Check current mode by seeing if hostapd is running
if systemctl is-active --quiet hostapd; then
    echo "Currently in AP mode"
    echo "Switching to Home WiFi mode..."
    
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
    echo "Switched to Home WiFi Mode!"
    echo "================================"
    echo "Connected to: $HOME_SSID"
    echo "IP Address: $IP_ADDR"
    echo ""
    echo "You can now:"
    echo "1. SSH to: pi@$IP_ADDR"
    echo "2. Access from your home network"
    echo ""
    echo "To switch back to AP mode, run this script again"
    
else
    echo "Currently in WiFi client mode"
    echo "Switching to AP mode..."
    
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
    echo "Configuring AP network..."
    sudo ip addr add 192.168.4.1/24 dev $AP_INTERFACE
    
    # Start AP services
    echo "Starting AP services..."
    sudo systemctl start hostapd
    sudo systemctl start dnsmasq
    
    sleep 3
    
    # Show AP info
    echo ""
    echo "================================"
    echo "Switched to AP Mode!"
    echo "================================"
    echo "WiFi Network: WW2-Kiosk-AP"
    echo "Password: ww2kiosk2024"
    echo "IP Address: 192.168.4.1"
    echo ""
    echo "You can now:"
    echo "1. Connect to WiFi: WW2-Kiosk-AP"
    echo "2. SSH to: pi@192.168.4.1"
    echo "3. Access SMB: smb://192.168.4.1/media"
    echo ""
    echo "To switch back to home WiFi, run this script again"
fi

echo ""
echo "Script complete. Network change will take effect in a few seconds."
echo "You may need to reconnect to the new network."
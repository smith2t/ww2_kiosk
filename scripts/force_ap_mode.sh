#!/bin/bash

# Force switch to AP mode from home WiFi

echo "================================"
echo "Forcing AP Mode"
echo "================================"

# Kill all WiFi client connections
echo "Stopping WiFi client mode..."
sudo systemctl stop wpa_supplicant
sudo systemctl disable wpa_supplicant
sudo killall wpa_supplicant 2>/dev/null || true
sudo killall dhclient 2>/dev/null || true
sudo systemctl stop dhcpcd

# Clear WiFi configuration
echo "Clearing WiFi configuration..."
sudo bash -c "> /etc/wpa_supplicant/wpa_supplicant.conf"

# Reset wlan0 completely
echo "Resetting wlan0..."
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sleep 2

# Remove dhcpcd management of wlan0
echo "Configuring dhcpcd to ignore wlan0..."
if ! grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf; then
    echo "denyinterfaces wlan0" | sudo tee -a /etc/dhcpcd.conf
fi

# Restart dhcpcd without wlan0
sudo systemctl restart dhcpcd

# Bring up wlan0 with static IP
echo "Configuring wlan0 for AP mode..."
sudo ip link set wlan0 up
sudo ip addr add 192.168.4.1/24 dev wlan0

# Ensure hostapd config is correct
echo "Verifying hostapd configuration..."
sudo bash -c 'cat > /etc/hostapd/hostapd.conf << EOF
interface=wlan0
driver=nl80211
ssid=WW2-Kiosk-AP
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=ww2kiosk2024
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF'

# Start AP services
echo "Starting AP services..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl start hostapd

sleep 2

sudo systemctl enable dnsmasq
sudo systemctl start dnsmasq

# Check if services started
echo ""
echo "Checking services..."
if systemctl is-active --quiet hostapd; then
    echo "✓ hostapd is running"
else
    echo "✗ hostapd failed - checking why..."
    sudo journalctl -u hostapd -n 10
fi

if systemctl is-active --quiet dnsmasq; then
    echo "✓ dnsmasq is running"
else
    echo "✗ dnsmasq failed"
fi

echo ""
echo "================================"
echo "AP Mode Forced!"
echo "================================"
echo "Network: WW2-Kiosk-AP"
echo "Password: ww2kiosk2024"
echo "IP: 192.168.4.1"
echo ""
echo "Disconnect from HomeFront and connect to WW2-Kiosk-AP"
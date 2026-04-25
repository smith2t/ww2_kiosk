#!/bin/bash

# Fix network configuration issues
echo "================================"
echo "Network Configuration Fix"
echo "================================"

# Stop all network services first
echo "Stopping network services..."
sudo systemctl stop hostapd 2>/dev/null || true
sudo systemctl stop dnsmasq 2>/dev/null || true
sudo systemctl stop dhcpcd 2>/dev/null || true
sudo systemctl stop wpa_supplicant 2>/dev/null || true

# Kill any lingering processes
sudo killall wpa_supplicant 2>/dev/null || true
sudo killall dhclient 2>/dev/null || true

# Reset network interface
echo "Resetting wlan0 interface..."
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sleep 2

# Check if we're on Raspberry Pi OS Bookworm or newer
if [ -f /etc/debian_version ]; then
    DEBIAN_VERSION=$(cat /etc/debian_version)
    echo "Detected Debian version: $DEBIAN_VERSION"
fi

# Fix dhcpcd configuration - prevent it from managing wlan0
echo "Configuring dhcpcd..."
if ! grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf 2>/dev/null; then
    echo "Adding wlan0 to denyinterfaces..."
    echo "" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo "# Prevent dhcpcd from managing wlan0 (for AP mode)" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo "denyinterfaces wlan0" | sudo tee -a /etc/dhcpcd.conf > /dev/null
fi

# Remove any conflicting network configurations
echo "Cleaning up network configurations..."
sudo rm -f /etc/network/interfaces.d/wlan0 2>/dev/null

# Configure hostapd properly
echo "Configuring hostapd..."
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

# Update hostapd default file
sudo bash -c 'echo "DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"" > /etc/default/hostapd'

# Configure dnsmasq
echo "Configuring dnsmasq..."
sudo bash -c 'cat > /etc/dnsmasq.conf << EOF
interface=wlan0
bind-interfaces
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=local
address=/kiosk.local/192.168.4.1
EOF'

# Create systemd service for AP network setup
echo "Creating network setup service..."
sudo bash -c 'cat > /etc/systemd/system/ap-network-setup.service << EOF
[Unit]
Description=Access Point Network Setup
Before=hostapd.service
After=sys-subsystem-net-devices-wlan0.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c "ip link set wlan0 up && ip addr add 192.168.4.1/24 dev wlan0"
ExecStop=/bin/bash -c "ip addr flush dev wlan0 && ip link set wlan0 down"

[Install]
WantedBy=multi-user.target
EOF'

# Enable the services
echo "Enabling services..."
sudo systemctl daemon-reload
sudo systemctl enable ap-network-setup.service

# Unmask hostapd if it was masked
sudo systemctl unmask hostapd 2>/dev/null || true

# Start services in correct order
echo "Starting network services..."
sudo systemctl start dhcpcd
sleep 2
sudo systemctl start ap-network-setup
sleep 2
sudo systemctl start hostapd
sleep 2
sudo systemctl start dnsmasq

# Check status
echo ""
echo "Checking service status..."
echo "------------------------"
systemctl is-active hostapd && echo "✓ hostapd is running" || echo "✗ hostapd failed"
systemctl is-active dnsmasq && echo "✓ dnsmasq is running" || echo "✗ dnsmasq failed"

# Show network info
echo ""
echo "Network configuration:"
echo "------------------------"
ip addr show wlan0 | grep inet

echo ""
echo "================================"
echo "Network Fix Complete!"
echo "================================"
echo ""
echo "AP should be available as:"
echo "  SSID: WW2-Kiosk-AP"
echo "  Password: ww2kiosk2024"
echo "  IP: 192.168.4.1"
echo ""
echo "If services failed, check logs with:"
echo "  sudo journalctl -u hostapd -n 50"
echo "  sudo journalctl -u dnsmasq -n 50"
echo ""
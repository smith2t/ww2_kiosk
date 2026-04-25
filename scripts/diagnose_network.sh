#!/bin/bash

# Diagnose network configuration issues

echo "================================"
echo "Network Diagnostics"
echo "================================"
echo ""

echo "1. System Information:"
echo "----------------------"
uname -a
cat /etc/os-release | grep PRETTY_NAME
echo ""

echo "2. Network Interfaces:"
echo "----------------------"
ip link show
echo ""

echo "3. IP Addresses:"
echo "----------------------"
ip addr show
echo ""

echo "4. Service Status:"
echo "----------------------"
echo -n "hostapd: "
systemctl is-active hostapd || echo "inactive"
echo -n "dnsmasq: "
systemctl is-active dnsmasq || echo "inactive"
echo -n "dhcpcd: "
systemctl is-active dhcpcd || echo "inactive"
echo -n "wpa_supplicant: "
systemctl is-active wpa_supplicant || echo "inactive"
echo ""

echo "5. Process Check:"
echo "----------------------"
ps aux | grep -E "(hostapd|dnsmasq|wpa_supplicant|dhclient)" | grep -v grep || echo "No related processes running"
echo ""

echo "6. dhcpcd.conf (wlan0 settings):"
echo "----------------------"
grep -E "(interface wlan0|denyinterfaces)" /etc/dhcpcd.conf 2>/dev/null || echo "No wlan0 configuration in dhcpcd.conf"
echo ""

echo "7. Hostapd Configuration:"
echo "----------------------"
if [ -f /etc/hostapd/hostapd.conf ]; then
    echo "File exists"
    grep -E "^(interface|ssid|channel)" /etc/hostapd/hostapd.conf
else
    echo "hostapd.conf not found"
fi
echo ""

echo "8. Recent Errors (hostapd):"
echo "----------------------"
sudo journalctl -u hostapd -n 10 --no-pager 2>/dev/null || echo "No hostapd logs"
echo ""

echo "9. Recent Errors (networking):"
echo "----------------------"
sudo journalctl -u networking -n 10 --no-pager 2>/dev/null || echo "No networking logs"
echo ""

echo "10. WiFi Device Info:"
echo "----------------------"
iw dev 2>/dev/null || echo "iw command not available"
echo ""

echo "11. USB Devices (checking for WiFi adapters):"
echo "----------------------"
lsusb | grep -i wireless || echo "No USB wireless adapters found"
echo ""

echo "================================"
echo "Diagnosis Complete"
echo "================================"
echo ""
echo "Common Issues:"
echo "- If hostapd fails: Usually means wlan0 is already in use"
echo "- If dhcpcd active: May conflict with static IP for AP mode"
echo "- If wpa_supplicant active: Conflicts with AP mode"
echo ""
echo "To fix, try running: ./scripts/fix_network.sh"
echo "For simple WiFi connection: ./scripts/connect_home_wifi.sh"
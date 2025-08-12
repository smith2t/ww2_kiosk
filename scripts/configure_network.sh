#!/bin/bash

# Configure network settings for WiFi AP and SMB

echo "Configuring network settings..."

# Stop any conflicting services first
echo "Stopping conflicting services..."
sudo systemctl stop hostapd 2>/dev/null || true
sudo systemctl stop dnsmasq 2>/dev/null || true
sudo systemctl stop wpa_supplicant 2>/dev/null || true

# Configure dhcpcd to ignore wlan0 (only if not already configured)
echo "Configuring dhcpcd..."
if ! grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf 2>/dev/null; then
    echo "Adding wlan0 to denyinterfaces..."
    echo "" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo "# Prevent dhcpcd from managing wlan0 (for AP mode)" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo "denyinterfaces wlan0" | sudo tee -a /etc/dhcpcd.conf > /dev/null
else
    echo "dhcpcd already configured to ignore wlan0"
fi

# Remove old network interface configuration (not needed with systemd)
echo "Cleaning old network configurations..."
sudo rm -f /etc/network/interfaces.d/wlan0 2>/dev/null || true

# Configure hostapd
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

# Point hostapd to config file (replace instead of append)
sudo bash -c 'echo "DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"" > /etc/default/hostapd'

# Configure dnsmasq
echo "Configuring dnsmasq..."
if [ -f /etc/dnsmasq.conf ] && [ ! -f /etc/dnsmasq.conf.orig ]; then
    sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
fi
sudo bash -c 'cat > /etc/dnsmasq.conf << EOF
interface=wlan0
bind-interfaces
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=local
address=/kiosk.local/192.168.4.1
EOF'

# Create systemd service for network setup (instead of using interfaces.d)
echo "Creating AP network setup service..."
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

# Enable the AP network setup service
sudo systemctl daemon-reload
sudo systemctl enable ap-network-setup.service

# Configure Samba
echo "Configuring Samba..."
sudo bash -c 'cat > /etc/samba/smb.conf << EOF
[global]
   workgroup = WORKGROUP
   server string = WW2 Kiosk Media Server
   security = user
   map to guest = Bad User
   dns proxy = no
   min protocol = SMB2
   ntlm auth = yes
   
[media]
   comment = WW2 Kiosk Media Files
   path = /home/pi/ww2_kiosk/media
   browseable = yes
   read only = no
   guest ok = yes
   force user = pi
   force group = pi
   create mask = 0775
   directory mask = 0775
   public = yes
EOF'

# Create SMB user (using pi user for simplicity)
echo "Setting up SMB access..."
# Add pi user to smbpasswd if not already there
sudo smbpasswd -x pi 2>/dev/null || true
echo -e "raspberry\nraspberry" | sudo smbpasswd -a -s pi
sudo smbpasswd -e pi

# Also create kiosk user as alternative
sudo useradd -M -s /sbin/nologin kiosk 2>/dev/null || true
echo -e "kiosk123\nkiosk123" | sudo smbpasswd -a -s kiosk 2>/dev/null || true
sudo smbpasswd -e kiosk 2>/dev/null || true

# Set permissions - make sure pi owns the media directory
sudo mkdir -p /home/pi/ww2_kiosk/media/videos
sudo mkdir -p /home/pi/ww2_kiosk/media/pictures
sudo chown -R pi:pi /home/pi/ww2_kiosk
sudo chmod -R 775 /home/pi/ww2_kiosk/media

# Enable services
echo "Enabling network services..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

echo "Network configuration complete!"
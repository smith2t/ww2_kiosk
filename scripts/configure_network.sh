#!/bin/bash

# Configure network settings for WiFi AP and SMB

set -e

echo "Configuring network settings..."

# Configure dhcpcd to ignore wlan0
echo "Configuring dhcpcd..."
sudo bash -c 'echo "denyinterfaces wlan0" >> /etc/dhcpcd.conf'

# Configure static IP for wlan0
echo "Setting static IP for wlan0..."
sudo bash -c 'cat > /etc/network/interfaces.d/wlan0 << EOF
allow-hotplug wlan0
iface wlan0 inet static
    address 192.168.4.1
    netmask 255.255.255.0
    network 192.168.4.0
    broadcast 192.168.4.255
EOF'

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

# Point hostapd to config file
sudo bash -c 'echo "DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"" >> /etc/default/hostapd'

# Configure dnsmasq
echo "Configuring dnsmasq..."
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
sudo bash -c 'cat > /etc/dnsmasq.conf << EOF
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
EOF'

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
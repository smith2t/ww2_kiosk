#!/bin/bash

# Fix SMB access issues comprehensively

echo "================================"
echo "Fixing SMB Access"
echo "================================"

# Stop SMB service
echo "Stopping SMB service..."
sudo systemctl stop smbd
sudo systemctl stop nmbd

# Fix Samba configuration
echo "Updating Samba configuration..."
sudo bash -c 'cat > /etc/samba/smb.conf << EOF
[global]
   workgroup = WORKGROUP
   server string = WW2 Kiosk Media Server
   security = user
   map to guest = Bad User
   dns proxy = no
   
   # Mac compatibility settings
   min protocol = SMB2
   max protocol = SMB3
   
   # Authentication settings
   ntlm auth = ntlmv1-permitted
   lanman auth = yes
   client ntlmv2 auth = no
   
   # Performance settings
   socket options = TCP_NODELAY IPTOS_LOWDELAY
   
   # Logging
   log file = /var/log/samba/log.%m
   max log size = 1000
   logging = file
   
[media]
   comment = WW2 Kiosk Media Files
   path = /home/pi/ww2_kiosk/media
   browseable = yes
   writable = yes
   read only = no
   guest ok = yes
   public = yes
   force user = pi
   force group = pi
   create mask = 0664
   directory mask = 0775
   force create mode = 0664
   force directory mode = 0775
EOF'

# Ensure media directories exist with correct permissions
echo "Creating and fixing media directories..."
sudo mkdir -p /home/pi/ww2_kiosk/media/videos
sudo mkdir -p /home/pi/ww2_kiosk/media/pictures

# Fix ownership
echo "Fixing ownership..."
sudo chown -R pi:pi /home/pi/ww2_kiosk

# Fix permissions
echo "Fixing permissions..."
sudo chmod 755 /home/pi
sudo chmod 755 /home/pi/ww2_kiosk
sudo chmod 775 /home/pi/ww2_kiosk/media
sudo chmod 775 /home/pi/ww2_kiosk/media/videos
sudo chmod 775 /home/pi/ww2_kiosk/media/pictures

# Reset pi user in Samba
echo "Resetting pi user in Samba..."
sudo smbpasswd -x pi 2>/dev/null || true
sudo smbpasswd -a pi << EOF
raspberry
raspberry
EOF
sudo smbpasswd -e pi

# Also ensure pi user exists in system
echo "Checking pi user..."
if ! id -u pi >/dev/null 2>&1; then
    echo "Creating pi user..."
    sudo useradd -m -G sudo -s /bin/bash pi
    echo "pi:raspberry" | sudo chpasswd
fi

# Test Samba configuration
echo ""
echo "Testing Samba configuration..."
testparm -s 2>/dev/null | head -20

# Restart SMB services
echo ""
echo "Restarting SMB services..."
sudo systemctl restart smbd
sudo systemctl restart nmbd

# Check service status
echo ""
echo "Checking service status..."
if systemctl is-active --quiet smbd; then
    echo "✓ SMB service is running"
else
    echo "✗ SMB service failed to start"
    echo "Check logs: sudo journalctl -u smbd -n 20"
fi

# Get IP address
IP_ADDR=$(ip addr show wlan0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
if [ -z "$IP_ADDR" ]; then
    IP_ADDR=$(ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
fi
if [ -z "$IP_ADDR" ]; then
    IP_ADDR="192.168.4.1"
fi

echo ""
echo "================================"
echo "SMB Access Fixed!"
echo "================================"
echo ""
echo "Connection Methods:"
echo ""
echo "1. AS GUEST (Easiest):"
echo "   Mac: Finder → Cmd+K → smb://$IP_ADDR/media"
echo "   Select: Guest"
echo ""
echo "2. AS USER:"
echo "   Mac: Finder → Cmd+K → smb://$IP_ADDR/media"
echo "   Username: pi"
echo "   Password: raspberry"
echo ""
echo "3. FROM WINDOWS:"
echo "   Explorer → \\\\$IP_ADDR\\media"
echo "   Username: pi (or WORKGROUP\\pi)"
echo "   Password: raspberry"
echo ""
echo "If you still get errors:"
echo "1. Check firewall: sudo ufw status"
echo "2. Check logs: sudo tail -f /var/log/samba/log.smbd"
echo "3. Try: smbclient -L $IP_ADDR -U pi"
echo ""
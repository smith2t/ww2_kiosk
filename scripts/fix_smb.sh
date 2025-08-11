#!/bin/bash

# Fix SMB access issues

echo "Fixing SMB configuration..."

# Update Samba configuration for better Mac compatibility
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

# Make sure media directories exist
echo "Creating media directories..."
sudo mkdir -p /home/pi/ww2_kiosk/media/videos
sudo mkdir -p /home/pi/ww2_kiosk/media/pictures

# Fix permissions
echo "Fixing permissions..."
sudo chown -R pi:pi /home/pi/ww2_kiosk
sudo chmod -R 775 /home/pi/ww2_kiosk/media

# Reset SMB users
echo "Setting up SMB users..."

# Remove and re-add pi user
sudo smbpasswd -x pi 2>/dev/null || true
echo -e "raspberry\nraspberry" | sudo smbpasswd -a -s pi
sudo smbpasswd -e pi

# Restart Samba
echo "Restarting Samba service..."
sudo systemctl restart smbd
sudo systemctl restart nmbd

# Show connection info
echo ""
echo "================================"
echo "SMB Share Fixed!"
echo "================================"
echo ""
echo "Connection details:"
echo "  Address: smb://192.168.4.1/media"
echo ""
echo "You can now connect as:"
echo "  1. Guest (no password needed)"
echo "  2. Username: pi"
echo "     Password: raspberry"
echo ""
echo "From Mac Finder:"
echo "  1. Press Cmd+K"
echo "  2. Enter: smb://192.168.4.1/media"
echo "  3. Connect as Guest or use pi/raspberry"
echo ""

# Test configuration
echo "Testing SMB configuration..."
testparm -s 2>/dev/null | grep -A 10 "\[media\]"
#!/bin/bash

# Quick fix for SMB "media not found" error

echo "================================"
echo "Quick SMB Media Fix"
echo "================================"

# Create the media directory structure
echo "Creating media directories..."
sudo mkdir -p /home/pi/ww2_kiosk/media
sudo mkdir -p /home/pi/ww2_kiosk/media/videos
sudo mkdir -p /home/pi/ww2_kiosk/media/pictures

# Create test files so directory isn't empty
echo "Adding test files..."
sudo touch /home/pi/ww2_kiosk/media/README.txt
echo "WW2 Kiosk Media Directory" | sudo tee /home/pi/ww2_kiosk/media/README.txt > /dev/null
sudo touch /home/pi/ww2_kiosk/media/videos/place_videos_here.txt
sudo touch /home/pi/ww2_kiosk/media/pictures/place_pictures_here.txt

# Fix ownership - CRITICAL
echo "Fixing ownership to pi user..."
sudo chown -R pi:pi /home/pi
sudo chown -R pi:pi /home/pi/ww2_kiosk
sudo chown -R pi:pi /home/pi/ww2_kiosk/media

# Fix permissions
echo "Setting permissions..."
sudo chmod 755 /home/pi
sudo chmod 755 /home/pi/ww2_kiosk  
sudo chmod 777 /home/pi/ww2_kiosk/media
sudo chmod 777 /home/pi/ww2_kiosk/media/videos
sudo chmod 777 /home/pi/ww2_kiosk/media/pictures

# Update SMB to use simpler config
echo "Updating SMB configuration..."
sudo bash -c 'cat > /etc/samba/smb.conf << EOF
[global]
   workgroup = WORKGROUP
   server string = Pi Server
   security = user
   map to guest = Bad User
   
[media]
   path = /home/pi/ww2_kiosk/media
   browseable = yes
   writable = yes
   guest ok = yes
   public = yes
   force user = pi
   force group = pi
EOF'

# Restart Samba
echo "Restarting Samba..."
sudo systemctl restart smbd
sudo systemctl restart nmbd

# Show directory contents
echo ""
echo "Media directory contents:"
ls -la /home/pi/ww2_kiosk/media/

# Get current IP
IP=$(hostname -I | cut -d' ' -f1)

echo ""
echo "================================"
echo "SMB Media Fix Complete!"
echo "================================"
echo ""
echo "Try connecting again:"
echo "1. Mac Finder: Cmd+K"
echo "2. Enter: smb://$IP/media"
echo "3. Connect as: Guest"
echo ""
echo "The media folder should now be visible and accessible."
echo ""
echo "If still having issues, try:"
echo "  smbclient -L $IP -N"
echo "This will list available shares."
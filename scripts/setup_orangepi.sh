#!/bin/bash

# OrangePi WW2 Kiosk Setup Script
# This script sets up the OrangePi for the WW2 kiosk application

set -e

echo "🍊 Setting up WW2 Kiosk for OrangePi..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "This script should not be run as root. Run as orangepi user with sudo access."
   exit 1
fi

# Update system
echo "📦 Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

# Install system dependencies
echo "🔧 Installing system dependencies..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    build-essential \
    swig \
    pkg-config \
    vlc \
    hostapd \
    dnsmasq \
    samba \
    git \
    nginx \
    supervisor \
    curl \
    python3-rpi.gpio \
    wiringpi \
    libgpiod-dev \
    gpiod

# Install uv for faster Python package management
echo "⚡ Installing uv for faster package management..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Install Python packages
echo "🐍 Installing Python dependencies..."
cd /home/orangepi/ww2_kiosk-main

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages excluding problematic GPIO packages
echo "📦 Installing base Python packages..."
if command -v uv &> /dev/null; then
    echo "⚡ Using uv for fast package installation..."
    uv pip install --upgrade pip
    # Install packages without GPIO dependencies first
    uv pip install pygame Pillow PyYAML python-vlc flask python-pptx PyPDF2 PyMuPDF asyncio pytest black pylint flake8 mypy pytest-cov
else
    echo "📦 Using pip for package installation..."
    pip install --upgrade pip
    # Install packages without GPIO dependencies first
    pip install pygame Pillow PyYAML python-vlc flask python-pptx PyPDF2 PyMuPDF asyncio pytest black pylint flake8 mypy pytest-cov
fi

# GPIO support note
echo "🔌 GPIO support configured..."
echo "   ✅ Using custom sysfs GPIO implementation (no compilation needed)"
echo "   📌 GPIO will be accessed directly via /sys/class/gpio"
echo "   🎯 This avoids compilation issues with OrangePi.GPIO"

# Create media directories
echo "📁 Creating media directories..."
mkdir -p media/videos
mkdir -p media/pictures
mkdir -p logs

# Set up SMB shares
echo "🌐 Configuring SMB shares..."
sudo tee -a /etc/samba/smb.conf > /dev/null << 'EOF'

[ww2-media]
    comment = WW2 Kiosk Media Share
    path = /home/orangepi/ww2_kiosk-main/media
    browseable = yes
    read only = no
    guest ok = yes
    create mask = 0777
    directory mask = 0777
    force user = orangepi
    force group = orangepi
EOF

# Set SMB password for orangepi user
echo "Setting up SMB access for orangepi user..."
echo -e "kiosk123\nkiosk123" | sudo smbpasswd -a orangepi -s

# Enable and start SMB service
sudo systemctl enable smbd
sudo systemctl restart smbd

# Configure hostapd for OrangePi
echo "📶 Configuring WiFi Access Point..."
sudo tee /etc/hostapd/hostapd.conf > /dev/null << 'EOF'
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
wpa_passphrase=ww2kiosk123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# Configure dnsmasq
sudo tee /etc/dnsmasq.conf > /dev/null << 'EOF'
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
EOF

# Configure systemd service
echo "⚙️ Setting up systemd service..."
sudo tee /etc/systemd/system/ww2-kiosk.service > /dev/null << 'EOF'
[Unit]
Description=WW2 Kiosk Application
After=network.target

[Service]
Type=simple
User=orangepi
WorkingDirectory=/home/orangepi/ww2_kiosk-main
Environment=PATH=/home/orangepi/ww2_kiosk-main/venv/bin
ExecStart=/home/orangepi/ww2_kiosk-main/venv/bin/python src/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Set up auto-start for the kiosk (disable screen blanking)
echo "🖥️ Configuring display settings..."
sudo tee -a /boot/armbianEnv.txt > /dev/null << 'EOF'
# Disable screen blanking for kiosk
extraargs=consoleblank=0
EOF

# Create start script for manual testing
echo "📝 Creating start script..."
tee start_kiosk.sh > /dev/null << 'EOF'
#!/bin/bash
cd /home/orangepi/ww2_kiosk-main
source venv/bin/activate
export DISPLAY=:0
python src/main.py
EOF
chmod +x start_kiosk.sh

# Enable the kiosk service
echo "🔄 Enabling kiosk service..."
sudo systemctl daemon-reload
sudo systemctl enable ww2-kiosk.service

# Set up log rotation
echo "📋 Setting up log rotation..."
sudo tee /etc/logrotate.d/ww2-kiosk > /dev/null << 'EOF'
/home/orangepi/ww2_kiosk-main/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 orangepi orangepi
}
EOF

# Create default configuration if it doesn't exist
echo "⚙️ Creating default configuration..."
if [ ! -f config/config.yaml ]; then
    cp config/config.yaml.example config/config.yaml 2>/dev/null || echo "No example config found"
fi

# Set permissions
echo "🔐 Setting permissions..."
sudo chown -R orangepi:orangepi /home/orangepi/ww2_kiosk-main
chmod -R 755 /home/orangepi/ww2_kiosk-main

echo "✅ OrangePi WW2 Kiosk setup complete!"
echo ""
echo "Next steps:"
echo "1. Reboot the system: sudo reboot"
echo "2. The kiosk will start automatically on boot"
echo "3. Connect to WiFi network 'WW2-Kiosk-AP' with password 'ww2kiosk123'"
echo "4. Access web interface at: http://192.168.4.1:8080"
echo "5. SMB share available at: \\\\192.168.4.1\\ww2-media (user: orangepi, pass: kiosk123)"
echo ""
echo "Manual start for testing: ./start_kiosk.sh"
echo "Check status: sudo systemctl status ww2-kiosk"
echo "View logs: sudo journalctl -u ww2-kiosk -f"
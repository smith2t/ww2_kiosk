#!/bin/bash

# WW2 Kiosk Setup Script
# Run this script on a fresh Raspberry Pi installation

set -e

echo "================================"
echo "WW2 Kiosk Setup Script"
echo "================================"

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    vlc \
    samba \
    samba-common-bin \
    hostapd \
    dnsmasq \
    git \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev

# Stop services that will be configured later
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

# Create project directory
echo "Creating project directory..."
PROJECT_DIR="/home/pi/ww2_kiosk"
CURRENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Check if we're already in the target directory
if [ "$CURRENT_DIR" = "$PROJECT_DIR" ]; then
    echo "Already in target directory: $PROJECT_DIR"
else
    echo "Setting up project in: $PROJECT_DIR"
    sudo mkdir -p $PROJECT_DIR
    sudo chown -R pi:pi $PROJECT_DIR
    
    # Copy project files (excluding the target directory itself)
    echo "Copying project files..."
    rsync -av --exclude="$PROJECT_DIR" "$CURRENT_DIR/" "$PROJECT_DIR/" || {
        # Fallback to cp if rsync not available
        cp -r "$CURRENT_DIR"/* "$PROJECT_DIR/" 2>/dev/null || true
    }
fi

# Create Python virtual environment
echo "Creating Python virtual environment..."
cd $PROJECT_DIR
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create media directories
echo "Creating media directories..."
mkdir -p $PROJECT_DIR/media/videos
mkdir -p $PROJECT_DIR/media/pictures

# Set up configuration
echo "Setting up configuration..."
if [ -x "$PROJECT_DIR/scripts/configure_boot.sh" ]; then
    $PROJECT_DIR/scripts/configure_boot.sh
else
    echo "Warning: configure_boot.sh not found or not executable"
fi

# Install systemd service
echo "Installing systemd service..."
if [ -f "$PROJECT_DIR/systemd/ww2-kiosk.service" ]; then
    sudo cp $PROJECT_DIR/systemd/ww2-kiosk.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable ww2-kiosk.service
else
    echo "Warning: systemd service file not found"
fi

# Configure network
echo "Configuring network..."
if [ -x "$PROJECT_DIR/scripts/configure_network.sh" ]; then
    $PROJECT_DIR/scripts/configure_network.sh
else
    echo "Warning: configure_network.sh not found or not executable"
fi

echo "================================"
echo "Setup complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Copy your media files to:"
echo "   - Videos: $PROJECT_DIR/media/videos/"
echo "   - Pictures: $PROJECT_DIR/media/pictures/"
echo ""
echo "2. Edit button mappings in:"
echo "   $PROJECT_DIR/config/button_mappings.json"
echo ""
echo "3. Reboot to start the kiosk:"
echo "   sudo reboot"
echo ""
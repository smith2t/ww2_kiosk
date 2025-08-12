#!/bin/bash

# Fix GPIO for Raspberry Pi 5
echo "================================"
echo "Fixing GPIO for Raspberry Pi 5"
echo "================================"

# Stop the kiosk service if running
echo "Stopping kiosk service..."
sudo systemctl stop ww2-kiosk 2>/dev/null || true

# Navigate to project directory
cd /home/pi/ww2_kiosk

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Uninstall old GPIO library
echo "Removing old RPi.GPIO library..."
pip uninstall -y RPi.GPIO 2>/dev/null || true

# Install new GPIO libraries for Pi 5
echo "Installing gpiozero for Pi 5 compatibility..."
pip install gpiozero>=2.0.0
pip install lgpio>=0.2.0

# Update the project files
echo "Updating project files..."
if [ -f ../ww2_kiosk_updated/src/input/gpio_controller.py ]; then
    cp ../ww2_kiosk_updated/src/input/gpio_controller.py src/input/gpio_controller.py
    echo "GPIO controller updated"
fi

# Test GPIO
echo ""
echo "Testing GPIO..."
python -c "
try:
    from gpiozero import Button
    print('✓ gpiozero imported successfully')
    print('✓ GPIO should now work on Raspberry Pi 5')
except Exception as e:
    print('✗ Error:', e)
"

# Restart the service
echo ""
echo "Starting kiosk service..."
sudo systemctl start ww2-kiosk

echo ""
echo "================================"
echo "GPIO Fix Complete!"
echo "================================"
echo ""
echo "The kiosk should now work with Raspberry Pi 5."
echo "Check the status with: sudo systemctl status ww2-kiosk"
echo ""
echo "If you still have issues, check logs with:"
echo "  sudo journalctl -u ww2-kiosk -f"
echo ""
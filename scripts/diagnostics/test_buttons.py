#!/usr/bin/env python3
"""
Test script for button GPIO functionality on OrangePi Zero 2W
"""

import asyncio
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from input.orangepi_gpio import OrangePiButton, is_sysfs_gpio_available
from config.settings import Settings


async def test_button_gpio(pin, name):
    """Test a single button GPIO pin"""
    print(f"Testing {name} (GPIO {pin})...")

    button = OrangePiButton(pin, pull_up=True)

    if button.setup():
        print(f"  ✅ {name} setup successful")

        # Test reading the button state
        value = button.gpio.read_value(pin)
        if value is not None:
            state = "Released" if value == 1 else "Pressed"
            print(f"  📊 {name} current state: {state} (value: {value})")
        else:
            print(f"  ⚠️  Could not read {name} state")

        button.cleanup()
        return True
    else:
        print(f"  ❌ {name} setup failed")
        return False


async def main():
    """Test all button GPIO pins"""
    print("🔍 Testing Button GPIO Pins for WW2 Kiosk")
    print("=" * 50)

    if not is_sysfs_gpio_available():
        print("❌ sysfs GPIO not available")
        return

    print("✅ sysfs GPIO available")

    # Initialize settings to get button pin configuration
    settings = Settings()

    button_pins = {
        1: settings.input.button1_pin,
        2: settings.input.button2_pin,
        3: settings.input.button3_pin,
        4: settings.input.button4_pin,
    }

    print(f"\n📍 Button Pin Configuration:")
    for btn_id, pin in button_pins.items():
        print(f"  Button {btn_id}: GPIO {pin}")

    print(f"\n🧪 Testing Button GPIOs...")

    results = {}
    for btn_id, pin in button_pins.items():
        results[btn_id] = await test_button_gpio(pin, f"Button {btn_id}")

    print(f"\n📊 Test Results Summary:")
    working_buttons = sum(1 for success in results.values() if success)
    total_buttons = len(results)

    for btn_id, success in results.items():
        status = "✅ Working" if success else "❌ Failed"
        print(f"  Button {btn_id}: {status}")

    print(f"\n🎯 Overall Result: {working_buttons}/{total_buttons} buttons working")

    if working_buttons == total_buttons:
        print("🎉 All button GPIOs are working correctly!")
        print("\n💡 Hardware Connection Guide:")
        print("Connect your buttons between the GPIO pin and GND")
        print("The software uses internal pull-up resistors")
        print("Button press = connect GPIO to GND")
    elif working_buttons > 0:
        print("⚠️  Some buttons working - check pin availability")
    else:
        print("❌ No buttons working - check GPIO configuration")

    print(f"\n📖 See docs/ORANGEPI_GPIO_PINOUT.md for detailed pinout information")


if __name__ == "__main__":
    asyncio.run(main())
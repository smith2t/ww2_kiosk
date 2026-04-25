#!/usr/bin/env python3
"""
Test script for LED GPIO functionality on Orange Pi Zero 2W
Tests the lower pins configuration: GPIO 78, 226, 227, 228
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from display.led_controller import LEDController
from input.orangepi_gpio import OrangePiGPIO
from config.settings import Settings


async def test_led_hardware():
    """Test individual LED hardware connections"""
    print("💡 Testing Individual LED Hardware Connections")
    print("=" * 50)

    settings = Settings()
    gpio = OrangePiGPIO()

    led_pins = {
        1: settings.display.led1_pin,  # GPIO 78 (Pin 16)
        2: settings.display.led2_pin,  # GPIO 226 (Pin 18)
        3: settings.display.led3_pin,  # GPIO 227 (Pin 22)
        4: settings.display.led4_pin,  # GPIO 228 (Pin 24)
    }

    print("\n📍 LED Pin Configuration:")
    physical_pins = [16, 18, 22, 24]
    for led_id, pin in led_pins.items():
        print(f"  LED {led_id}: GPIO {pin} (Physical pin {physical_pins[led_id-1]})")

    initialized_leds = []

    print("\n🔧 Setting up LEDs...")
    for led_id, pin in led_pins.items():
        print(f"Setting up LED {led_id} on GPIO {pin}...")

        try:
            # Export and configure as output
            if gpio.export_pin(pin) and gpio.set_direction(pin, "out"):
                # Turn off initially
                value_file = gpio.gpio_base / f"gpio{pin}" / "value"
                with open(value_file, 'w') as f:
                    f.write("0")
                print(f"  ✅ LED {led_id} (GPIO {pin}) setup successful")
                initialized_leds.append((led_id, pin))
            else:
                print(f"  ❌ LED {led_id} (GPIO {pin}) setup failed")
        except Exception as e:
            print(f"  ❌ LED {led_id} (GPIO {pin}) error: {e}")

    print(f"\n📊 Hardware Setup: {len(initialized_leds)}/4 LEDs working")

    if len(initialized_leds) > 0:
        print("\n🧪 Testing individual LEDs...")

        for led_id, pin in initialized_leds:
            print(f"\n💡 Testing LED {led_id} (GPIO {pin}, Physical Pin {physical_pins[led_id-1]}):")

            try:
                value_file = gpio.gpio_base / f"gpio{pin}" / "value"

                # Turn on
                print("  🔆 Turning ON for 2 seconds...")
                with open(value_file, 'w') as f:
                    f.write("1")
                await asyncio.sleep(2)

                # Turn off
                print("  🔅 Turning OFF...")
                with open(value_file, 'w') as f:
                    f.write("0")
                await asyncio.sleep(0.5)

                print(f"  ✅ LED {led_id} test complete")

            except Exception as e:
                print(f"  ❌ LED {led_id} test failed: {e}")

        # Test pattern
        print("\n🎨 Testing LED Pattern (Sequential)...")
        for cycle in range(3):
            print(f"  Cycle {cycle + 1}/3")
            for led_id, pin in initialized_leds:
                try:
                    value_file = gpio.gpio_base / f"gpio{pin}" / "value"
                    with open(value_file, 'w') as f:
                        f.write("1")
                    await asyncio.sleep(0.3)
                    with open(value_file, 'w') as f:
                        f.write("0")
                    await asyncio.sleep(0.1)
                except Exception as e:
                    print(f"    ❌ Pattern error on LED {led_id}: {e}")

    # Cleanup
    print("\n🧹 Cleaning up GPIO...")
    try:
        for led_id, pin in initialized_leds:
            value_file = gpio.gpio_base / f"gpio{pin}" / "value"
            with open(value_file, 'w') as f:
                f.write("0")  # Turn off
        gpio.cleanup()
        print("✅ GPIO cleanup complete")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

    return len(initialized_leds)

async def test_led_controller():
    """Test LED controller functionality"""
    print("\n🎮 Testing LED Controller Software")
    print("=" * 40)

    settings = Settings()
    led_controller = LEDController(settings)

    try:
        print("🔌 Initializing LED controller...")
        if await led_controller.initialize():
            print("✅ LED controller initialized successfully")

            print("\n🎬 Testing boot sequence...")
            await led_controller.boot_sequence()

            print("\n📊 Testing progress indicators...")
            stages = ["Loading", "Hardware", "Services", "Ready"]

            for i, stage in enumerate(stages, 1):
                await led_controller.progress_indicator(stage, len(stages), i)
                await asyncio.sleep(0.8)

            print("\n🎯 Testing button feedback...")
            for button_id in [1, 2, 3, 4]:
                print(f"  Button {button_id} feedback...")
                await led_controller.button_feedback(button_id)
                await asyncio.sleep(0.3)

            print("\n🎭 Testing video indicators...")
            for button_id in [1, 2, 3, 4]:
                print(f"  Video {button_id} playing...")
                await led_controller.video_playing_indicator(button_id)
                await asyncio.sleep(0.8)

            print("\n🌊 Testing slideshow mode (3 seconds)...")
            slideshow_task = asyncio.create_task(led_controller.slideshow_mode_indicator())
            await asyncio.sleep(3)
            await led_controller.stop_animations()

            print("\n✅ LED controller tests completed!")
            return True

        else:
            print("❌ LED controller initialization failed")
            return False

    except Exception as e:
        print(f"❌ LED controller error: {e}")
        return False

    finally:
        await led_controller.cleanup()

async def main():
    """Main LED test function"""
    print("💡 Orange Pi LED Connection Test")
    print("🔧 Lower Pins Configuration (Pins 16, 18, 22, 24)")
    print("=" * 60)

    print("\n⚠️  SAFETY CHECK:")
    print("  ✓ LEDs connected to pins 16, 18, 22, 24")
    print("  ✓ 220Ω-330Ω resistors in series with each LED")
    print("  ✓ LED longer leg (positive) to GPIO pin")
    print("  ✓ LED shorter leg (negative) to GND")
    print("  ✓ Secure connections made")

    input("\nPress ENTER to continue with LED tests...")

    # Test 1: Hardware connections
    working_leds = await test_led_hardware()

    # Test 2: Software controller (if hardware works)
    if working_leds > 0:
        controller_works = await test_led_controller()

        print(f"\n🎉 LED Test Summary:")
        print(f"  Hardware: {working_leds}/4 LEDs working")
        print(f"  Software: {'✅ Working' if controller_works else '❌ Failed'}")

        if working_leds == 4 and controller_works:
            print("\n🏆 Perfect! All LEDs working correctly!")
        elif working_leds > 0:
            print(f"\n👍 Good! {working_leds} LEDs working - check wiring for others")

    else:
        print("\n❌ No LEDs working - check hardware connections")
        print("\n🔧 Troubleshooting Guide:")
        print("  1. Verify wiring: GPIO pin → resistor → LED+ → LED- → GND")
        print("  2. Check LED polarity (longer leg = positive)")
        print("  3. Verify resistor values (220Ω-330Ω)")
        print("  4. Test LEDs with multimeter if available")
        print("  5. Ensure GPIO pins 78, 226, 227, 228 are not used elsewhere")


if __name__ == "__main__":
    asyncio.run(main())
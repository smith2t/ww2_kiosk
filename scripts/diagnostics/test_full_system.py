#!/usr/bin/env python3
"""
Complete system test for buttons and LEDs
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / 'src'))

from config.settings import Settings
from input.gpio_controller import GPIOController
from display.led_controller import LEDController

async def test_full_system():
    """Test complete button and LED system"""
    print("=" * 60)
    print("WW2 Kiosk - Complete System Test")
    print("=" * 60)

    # Load settings
    try:
        settings = Settings()
        print("✅ Settings loaded")
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        return

    # Initialize controllers
    gpio_controller = GPIOController(settings)
    led_controller = LEDController(settings)

    button_presses = []

    async def on_button_press(button_id):
        button_presses.append(button_id)
        print(f"🔘 Button {button_id} pressed! Lighting LED {button_id}")
        # Light up corresponding LED
        await led_controller.button_feedback(button_id)

    gpio_controller.on_button_press = on_button_press

    try:
        # Initialize controllers
        await gpio_controller.initialize()
        print("✅ GPIO controller initialized")

        led_init = await led_controller.initialize()
        print(f"✅ LED controller initialized: {led_init}")

        print("\nSystem mapping:")
        print("Buttons:")
        for button_id, pin in gpio_controller.button_pins.items():
            print(f"  Button {button_id}: GPIO {pin}")

        print("LEDs:")
        for led_id, pin in led_controller.led_pins.items():
            print(f"  LED {led_id}: GPIO {pin}")

        # Test LED patterns
        print("\n🎬 Testing LED boot sequence...")
        await led_controller.boot_sequence()

        print("\n🔄 Testing individual LEDs...")
        for led_id in range(1, 5):
            print(f"Testing LED {led_id}")
            await led_controller.set_led(led_id, True)
            await asyncio.sleep(0.5)
            await led_controller.set_led(led_id, False)
            await asyncio.sleep(0.2)

        print(f"\n🔘 Press buttons to test button+LED functionality...")
        print("Test will run for 15 seconds, press Ctrl+C to stop early")

        # Run test
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 15:
            await asyncio.sleep(0.1)

        print(f"\n📊 Test completed!")
        print(f"Total button presses: {len(button_presses)}")

        if button_presses:
            button_counts = {}
            for button_id in button_presses:
                button_counts[button_id] = button_counts.get(button_id, 0) + 1

            print("Results:")
            for button_id in sorted(button_counts.keys()):
                count = button_counts[button_id]
                print(f"  Button {button_id}: {count} presses")
        else:
            print("❌ No button presses detected")

        # Final LED cleanup
        await led_controller.all_leds_off()

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await gpio_controller.cleanup()
        await led_controller.cleanup()
        print("\n✅ Cleanup completed")

if __name__ == "__main__":
    try:
        asyncio.run(test_full_system())
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
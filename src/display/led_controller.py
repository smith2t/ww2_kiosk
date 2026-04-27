"""
LED Controller for WW2 Kiosk initialization indicators
Provides visual feedback during boot process using button LEDs
"""

import asyncio
import logging
import time
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class LEDController:
    """Control LEDs for visual feedback during initialization"""

    def __init__(self, settings):
        self.settings = settings
        self.led_pins = {
            1: getattr(settings.display, 'led1_pin', 18),  # Default LED pins
            2: getattr(settings.display, 'led2_pin', 19),
            3: getattr(settings.display, 'led3_pin', 20),
            4: getattr(settings.display, 'led4_pin', 21),
        }

        self.gpio_base = Path("/sys/class/gpio")
        self.exported_pins = set()
        self.led_states = {1: False, 2: False, 3: False, 4: False}
        self.animation_running = False
        # Separate flag for the long-lived slideshow breathing animation so
        # boot_sequence's finally-block can't kill it via animation_running.
        self.slideshow_anim_running = False

    async def initialize(self) -> bool:
        """Initialize LED controller"""
        logger.info("Initializing LED controller...")

        try:
            # Export and configure LED pins
            for led_id, pin in self.led_pins.items():
                if await self._export_pin(pin):
                    if await self._set_direction(pin, "out"):
                        await self._set_led(led_id, False)  # Start with LEDs off
                        logger.debug(f"LED {led_id} initialized on GPIO {pin}")
                    else:
                        logger.warning(f"Failed to set direction for LED {led_id} on GPIO {pin}")
                else:
                    logger.warning(f"Failed to export LED {led_id} on GPIO {pin}")

            return len(self.exported_pins) > 0

        except Exception as e:
            logger.error(f"Failed to initialize LED controller: {e}")
            return False

    async def _export_pin(self, pin: int) -> bool:
        """Export a GPIO pin for LED control"""
        # Check if pin is already exported
        pin_dir = self.gpio_base / f"gpio{pin}"
        if pin_dir.exists():
            logger.debug(f"GPIO pin {pin} already exported, reusing")
            self.exported_pins.add(pin)
            return True

        try:
            export_file = self.gpio_base / "export"
            if export_file.exists():
                with open(export_file, 'w') as f:
                    f.write(str(pin))
                self.exported_pins.add(pin)
                await asyncio.sleep(0.1)  # Wait for pin to be available
                return True
        except Exception as e:
            # Check if it was exported by something else during our attempt
            if pin_dir.exists():
                logger.debug(f"GPIO pin {pin} was exported by another process, reusing")
                self.exported_pins.add(pin)
                return True
            logger.debug(f"Failed to export GPIO pin {pin}: {e}")
        return False

    async def _set_direction(self, pin: int, direction: str) -> bool:
        """Set pin direction (in/out)"""
        try:
            direction_file = self.gpio_base / f"gpio{pin}" / "direction"
            if direction_file.exists():
                with open(direction_file, 'w') as f:
                    f.write(direction)
                return True
        except Exception as e:
            logger.debug(f"Failed to set direction for GPIO pin {pin}: {e}")
        return False

    async def _write_value(self, pin: int, value: int) -> bool:
        """Write value to GPIO pin (0 or 1)"""
        try:
            value_file = self.gpio_base / f"gpio{pin}" / "value"
            if value_file.exists():
                with open(value_file, 'w') as f:
                    f.write(str(value))
                return True
        except Exception as e:
            logger.debug(f"Failed to write to GPIO pin {pin}: {e}")
        return False

    async def _set_led(self, led_id: int, state: bool) -> bool:
        """Set LED state (on/off).

        Writes directly to sysfs and trusts _write_value's file-exists check.
        Previously gated on self.exported_pins, but that in-memory set falls
        out of sync with reality when input.led_controller exports the pin
        after we tried and failed — leaving the LED silently dark forever.
        """
        if led_id in self.led_pins:
            pin = self.led_pins[led_id]
            success = await self._write_value(pin, 1 if state else 0)
            if success:
                self.led_states[led_id] = state
            return success
        return False

    async def set_led(self, led_id: int, state: bool):
        """Public method to set LED state"""
        await self._set_led(led_id, state)

    async def all_leds_off(self):
        """Turn off all LEDs"""
        for led_id in self.led_pins.keys():
            await self._set_led(led_id, False)

    async def all_leds_on(self):
        """Turn on all LEDs"""
        for led_id in self.led_pins.keys():
            await self._set_led(led_id, True)

    async def boot_sequence(self):
        """Run the boot initialization LED sequence"""
        logger.info("🔄 Starting boot LED sequence...")
        self.animation_running = True

        try:
            # Stage 1: Quick flash all LEDs to show system is starting
            await self._startup_flash()

            # Stage 2: Rolling sequence to show initialization progress
            await self._rolling_sequence()

            # Stage 3: Success pattern
            await self._success_pattern()

        except Exception as e:
            logger.error(f"Error in boot sequence: {e}")
            # Error pattern - rapid blinking
            await self._error_pattern()

        self.animation_running = False
        logger.info("✅ Boot LED sequence complete")

    async def _startup_flash(self):
        """Quick flash all LEDs to indicate startup"""
        for _ in range(3):
            await self.all_leds_on()
            await asyncio.sleep(0.1)
            await self.all_leds_off()
            await asyncio.sleep(0.1)

    async def _rolling_sequence(self):
        """Rolling LED pattern during initialization"""
        # Multiple passes of rolling pattern
        for pass_num in range(5):
            # Forward roll
            for led_id in [1, 2, 3, 4]:
                await self.all_leds_off()
                await self._set_led(led_id, True)
                await asyncio.sleep(0.2)

            # Backward roll
            for led_id in [4, 3, 2, 1]:
                await self.all_leds_off()
                await self._set_led(led_id, True)
                await asyncio.sleep(0.2)

    async def _success_pattern(self):
        """Success pattern - all LEDs light up in sequence then stay on"""
        await self.all_leds_off()
        await asyncio.sleep(0.2)

        # Light up in sequence
        for led_id in [1, 2, 3, 4]:
            await self._set_led(led_id, True)
            await asyncio.sleep(0.3)

        # Hold for a moment
        await asyncio.sleep(1.0)

        # Fade out
        await self.all_leds_off()

    async def _error_pattern(self):
        """Error pattern - rapid blinking"""
        for _ in range(6):
            await self.all_leds_on()
            await asyncio.sleep(0.15)
            await self.all_leds_off()
            await asyncio.sleep(0.15)

    async def progress_indicator(self, stage: str, total_stages: int, current_stage: int):
        """Show progress using LEDs (1-4 LEDs based on progress)"""
        if not self.animation_running:
            # Calculate how many LEDs should be on
            leds_on = max(1, int((current_stage / total_stages) * 4))

            await self.all_leds_off()
            for led_id in range(1, leds_on + 1):
                await self._set_led(led_id, True)

            logger.info(f"📊 Progress: {stage} ({current_stage}/{total_stages}) - {leds_on} LEDs")

    async def button_feedback(self, button_id: int):
        """Provide LED feedback when a button is pressed"""
        if button_id in self.led_pins:
            # Quick blink to acknowledge button press
            await self._set_led(button_id, True)
            await asyncio.sleep(0.1)
            await self._set_led(button_id, False)

    async def video_playing_indicator(self, button_id: int):
        """Show which video is playing using LED"""
        await self.all_leds_off()
        if button_id in self.led_pins:
            await self._set_led(button_id, True)

    async def slideshow_mode_indicator(self):
        """Gentle breathing pattern to indicate slideshow mode.

        Uses a dedicated slideshow_anim_running flag so the shared
        animation_running flag (toggled by boot_sequence's finally block)
        can't terminate this long-lived loop.
        """
        self.slideshow_anim_running = True
        logger.info("Slideshow LED breathing started")

        try:
            while self.slideshow_anim_running:
                for brightness in range(0, 2):
                    if not self.slideshow_anim_running:
                        break
                    for led_id in [1, 2, 3, 4]:
                        await self._set_led(led_id, brightness == 1)
                    await asyncio.sleep(2.0)

        except Exception as e:
            logger.error(f"Error in slideshow indicator: {e}")

        await self.all_leds_off()
        logger.info("Slideshow LED breathing stopped")

    async def stop_animations(self):
        """Stop all running LED animations"""
        self.animation_running = False
        self.slideshow_anim_running = False
        await asyncio.sleep(0.5)  # Wait for animations to stop
        await self.all_leds_off()

    async def cleanup(self):
        """Clean up LED controller resources"""
        logger.info("Cleaning up LED controller")

        await self.stop_animations()

        # Unexport all pins
        for pin in list(self.exported_pins):
            try:
                unexport_file = self.gpio_base / "unexport"
                if unexport_file.exists():
                    with open(unexport_file, 'w') as f:
                        f.write(str(pin))
                self.exported_pins.discard(pin)
            except Exception as e:
                logger.debug(f"Failed to unexport GPIO pin {pin}: {e}")


# Test function
async def test_led_controller():
    """Test the LED controller"""
    from types import SimpleNamespace

    # Mock settings
    settings = SimpleNamespace()
    settings.display = SimpleNamespace()
    settings.display.led1_pin = 65  # Use available pins
    settings.display.led2_pin = 66
    settings.display.led3_pin = 67
    settings.display.led4_pin = 68

    led_controller = LEDController(settings)

    if await led_controller.initialize():
        print("✅ LED controller initialized")

        print("🎬 Running boot sequence...")
        await led_controller.boot_sequence()

        print("📊 Testing progress indicator...")
        for stage in range(1, 5):
            await led_controller.progress_indicator(f"Stage {stage}", 4, stage)
            await asyncio.sleep(1)

        await led_controller.cleanup()
        print("✅ LED test complete")
    else:
        print("❌ Failed to initialize LED controller")


if __name__ == "__main__":
    asyncio.run(test_led_controller())
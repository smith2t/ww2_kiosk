"""
Direct GPIO control for OrangePi using sysfs interface
This bypasses the need for compiled GPIO libraries
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class OrangePiGPIO:
    """Direct GPIO control using Linux sysfs interface"""

    def __init__(self):
        self.gpio_base = Path("/sys/class/gpio")
        self.exported_pins = set()

    def export_pin(self, pin: int) -> bool:
        """Export a GPIO pin for use (or use existing export)"""
        # Check if pin is already exported
        pin_dir = self.gpio_base / f"gpio{pin}"
        if pin_dir.exists():
            logger.debug(f"GPIO pin {pin} already exported")
            self.exported_pins.add(pin)
            return True

        try:
            export_file = self.gpio_base / "export"
            if export_file.exists():
                with open(export_file, 'w') as f:
                    f.write(str(pin))
                self.exported_pins.add(pin)
                # Wait a bit for the pin to be available
                time.sleep(0.1)
                return True
        except Exception as e:
            logger.debug(f"Failed to export GPIO pin {pin}: {e}")
            # Check again if it exists (might have been exported by someone else)
            if pin_dir.exists():
                logger.debug(f"GPIO pin {pin} available despite export error")
                self.exported_pins.add(pin)
                return True
        return False

    def set_direction(self, pin: int, direction: str) -> bool:
        """Set pin direction (in/out)"""
        try:
            direction_file = self.gpio_base / f"gpio{pin}" / "direction"
            if direction_file.exists():
                with open(direction_file, 'w') as f:
                    f.write(direction)
                return True
        except Exception as e:
            logger.error(f"Failed to set direction for GPIO pin {pin}: {e}")
        return False

    def set_edge(self, pin: int, edge: str) -> bool:
        """Set interrupt edge (rising/falling/both)"""
        try:
            edge_file = self.gpio_base / f"gpio{pin}" / "edge"
            if edge_file.exists():
                with open(edge_file, 'w') as f:
                    f.write(edge)
                return True
        except Exception as e:
            logger.error(f"Failed to set edge for GPIO pin {pin}: {e}")
        return False

    def read_value(self, pin: int) -> Optional[int]:
        """Read pin value (0 or 1)"""
        try:
            value_file = self.gpio_base / f"gpio{pin}" / "value"
            if value_file.exists():
                with open(value_file, 'r') as f:
                    return int(f.read().strip())
        except Exception as e:
            logger.error(f"Failed to read GPIO pin {pin}: {e}")
        return None

    def write_value(self, pin: int, value: int) -> bool:
        """Write pin value (0 or 1)"""
        try:
            value_file = self.gpio_base / f"gpio{pin}" / "value"
            if value_file.exists():
                with open(value_file, 'w') as f:
                    f.write(str(value))
                return True
        except Exception as e:
            logger.error(f"Failed to write GPIO pin {pin}: {e}")
        return False

    def unexport_pin(self, pin: int) -> bool:
        """Unexport a GPIO pin"""
        try:
            unexport_file = self.gpio_base / "unexport"
            if unexport_file.exists():
                with open(unexport_file, 'w') as f:
                    f.write(str(pin))
                self.exported_pins.discard(pin)
                return True
        except Exception as e:
            logger.error(f"Failed to unexport GPIO pin {pin}: {e}")
        return False

    def cleanup(self):
        """Clean up all exported pins"""
        for pin in list(self.exported_pins):
            self.unexport_pin(pin)


class OrangePiButton:
    """Button implementation using direct sysfs GPIO"""

    def __init__(self, pin: int, pull_up: bool = True):
        self.pin = pin
        self.pull_up = pull_up
        self.gpio = OrangePiGPIO()
        self.callback = None
        self.monitoring = False
        self.last_state = None
        self.debounce_time = 0.05  # 50ms debounce
        self.last_press_time = 0

    def setup(self) -> bool:
        """Setup the button GPIO"""
        try:
            # Export the pin
            if not self.gpio.export_pin(self.pin):
                return False

            # Set as input
            if not self.gpio.set_direction(self.pin, "in"):
                return False

            # Set edge detection for falling edge (button press)
            if not self.gpio.set_edge(self.pin, "falling"):
                return False

            # Read initial state
            self.last_state = self.gpio.read_value(self.pin)
            return True

        except Exception as e:
            logger.error(f"Failed to setup button on pin {self.pin}: {e}")
            return False

    async def start_monitoring(self):
        """Start monitoring button presses"""
        if not self.monitoring:
            self.monitoring = True
            asyncio.create_task(self._monitor_button())

    async def _monitor_button(self):
        """Monitor button state changes"""
        while self.monitoring:
            try:
                current_state = self.gpio.read_value(self.pin)
                current_time = time.time()

                # Check for state change (button press)
                if (current_state is not None and
                    current_state != self.last_state and
                    current_state == 0 and  # Falling edge (button pressed)
                    current_time - self.last_press_time > self.debounce_time):

                    self.last_press_time = current_time
                    if self.callback:
                        try:
                            if asyncio.iscoroutinefunction(self.callback):
                                await self.callback()
                            else:
                                self.callback()
                        except Exception as e:
                            logger.error(f"Error in button callback: {e}")

                self.last_state = current_state
                await asyncio.sleep(0.01)  # Check every 10ms

            except Exception as e:
                logger.error(f"Error monitoring button {self.pin}: {e}")
                await asyncio.sleep(0.1)

    def set_callback(self, callback: Callable):
        """Set the callback function for button press"""
        self.callback = callback

    def stop_monitoring(self):
        """Stop monitoring the button"""
        self.monitoring = False

    def cleanup(self):
        """Clean up button resources"""
        self.stop_monitoring()
        self.gpio.cleanup()


class OrangePiLED:
    """LED implementation using direct sysfs GPIO"""

    def __init__(self, pin: int):
        self.pin = pin
        self.gpio = OrangePiGPIO()
        self._state = False

    def setup(self) -> bool:
        """Setup the LED GPIO"""
        try:
            # Export the pin
            if not self.gpio.export_pin(self.pin):
                return False

            # Set as output
            if not self.gpio.set_direction(self.pin, "out"):
                return False

            # Start with LED off
            self.off()
            return True

        except Exception as e:
            logger.error(f"Failed to setup LED on pin {self.pin}: {e}")
            return False

    def on(self):
        """Turn LED on"""
        if self.gpio.write_value(self.pin, 1):
            self._state = True

    def off(self):
        """Turn LED off"""
        if self.gpio.write_value(self.pin, 0):
            self._state = False

    def toggle(self):
        """Toggle LED state"""
        if self._state:
            self.off()
        else:
            self.on()

    @property
    def is_lit(self):
        """Check if LED is on"""
        return self._state

    def cleanup(self):
        """Clean up LED resources"""
        self.off()
        self.gpio.cleanup()


# Test if sysfs GPIO is available
def is_sysfs_gpio_available() -> bool:
    """Check if sysfs GPIO interface is available"""
    return os.path.exists("/sys/class/gpio/export")


# Test function
async def test_orangepi_gpio():
    """Test the OrangePi GPIO implementation"""
    if not is_sysfs_gpio_available():
        print("❌ sysfs GPIO not available")
        return False

    print("✅ sysfs GPIO available")

    # Test basic GPIO operations
    gpio = OrangePiGPIO()

    # Try to export a pin (try different pins)
    test_pins = [65, 233, 234, 235]  # PC1, PH9, PH10, PH11 - commonly available
    success = False

    for test_pin in test_pins:
        print(f"Trying GPIO pin {test_pin}...")
        if gpio.export_pin(test_pin):
            success = True
            break
        else:
            print(f"Pin {test_pin} not available")

    if success:
        print(f"✅ Exported GPIO pin {test_pin}")

        if gpio.set_direction(test_pin, "in"):
            print(f"✅ Set pin {test_pin} as input")

            value = gpio.read_value(test_pin)
            if value is not None:
                print(f"✅ Read pin {test_pin} value: {value}")
            else:
                print(f"⚠️  Could not read pin {test_pin}")

        gpio.unexport_pin(test_pin)
        print(f"✅ Unexported GPIO pin {test_pin}")
        return True
    else:
        print(f"❌ Failed to export GPIO pin {test_pin}")
        return False


if __name__ == "__main__":
    # Run test
    asyncio.run(test_orangepi_gpio())
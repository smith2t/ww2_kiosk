import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Initialize GPIO mode flags
SYSFS_GPIO = False
ORANGEPI_GPIO = False
GPIO_AVAILABLE = False


def _is_raspberry_pi():
    try:
        return "Raspberry Pi" in Path("/proc/device-tree/model").read_text(errors="ignore")
    except Exception:
        return False


_IS_PI = _is_raspberry_pi()

if _IS_PI:
    # Pi: go straight to gpiozero. Skip OrangePi.GPIO and RPi.GPIO — they'd
    # import OK but Pi 5's RP1 chip isn't supported by RPi.GPIO.
    try:
        from gpiozero import LED
        from gpiozero.exc import GPIOZeroError
        GPIO_AVAILABLE = True
        logger.info("Raspberry Pi detected — using gpiozero for LEDs")
    except ImportError:
        logger.error("gpiozero unavailable — install python3-gpiozero")

# Allwinner / non-Pi fallback chain.
try:
    if _IS_PI:
        raise ImportError("Pi already handled above")
    from .orangepi_gpio import OrangePiLED, is_sysfs_gpio_available
    if is_sysfs_gpio_available():
        GPIO_AVAILABLE = True
        SYSFS_GPIO = True
        logger.info("Using custom OrangePi sysfs GPIO for LED control")
    else:
        raise ImportError("No sysfs GPIO access available")
except ImportError:
    try:
        # Try OrangePi GPIO as fallback
        import OrangePi.GPIO as GPIO
        ORANGEPI_GPIO = True
        GPIO_AVAILABLE = True
        logger.info("Using OrangePi.GPIO library for LED control")
    except ImportError:
        try:
            # Try RPi.GPIO as fallback
            import RPi.GPIO as GPIO
            GPIO_AVAILABLE = True
            logger.info("Using RPi.GPIO library for LED control")
        except ImportError:
            try:
                # Fallback to gpiozero
                from gpiozero import LED
                from gpiozero.exc import GPIOZeroError
                GPIO_AVAILABLE = True
                logger.info("Using gpiozero library for LED control")
            except ImportError:
                logger.warning("No GPIO library available for LED control, using mock")
                GPIO_AVAILABLE = False

                class LED:
                    """Mock LED class for development"""
                    def __init__(self, pin):
                        self.pin = pin
                        self._is_on = False

                    def on(self):
                        self._is_on = True

                    def off(self):
                        self._is_on = False

                    def toggle(self):
                        self._is_on = not self._is_on

                    @property
                    def is_lit(self):
                        return self._is_on

                    def close(self):
                        pass


class LEDController:
    """Controls LED feedback for button presses"""

    def __init__(self, settings):
        self.settings = settings

        # LED pin configuration
        self.led_pins = {
            1: settings.display.led1_pin,
            2: settings.display.led2_pin,
            3: settings.display.led3_pin,
            4: settings.display.led4_pin,
        }

        # Store LED objects for cleanup
        self.leds = {}
        self.gpio_initialized = False

    async def initialize(self):
        """Initialize LED pins"""
        logger.info("Initializing LED controller")

        if not GPIO_AVAILABLE:
            logger.warning("GPIO not available - LED control running in mock mode")
            return

        if _IS_PI:
            # On Pi, display.led_controller already owns the LED pins via
            # gpiozero (it ran first in main.initialize). gpiozero requires
            # exclusive ownership, so we'd just collide. Stay out — flash_led
            # becomes a no-op; user-facing button feedback comes from
            # display.led_controller.button_feedback() instead.
            logger.info("Pi detected — input LED controller deferring to display LED controller")
            return

        try:
            if SYSFS_GPIO:
                # Initialize custom sysfs GPIO LEDs
                for led_id, pin in self.led_pins.items():
                    if pin is not None:
                        await self._setup_sysfs_led(led_id, pin)
            elif ORANGEPI_GPIO:
                # Initialize OrangePi GPIO
                GPIO.setmode(GPIO.BOARD)
                # Convert GPIO numbers to physical pins for BOARD mode
                physical_pins = {
                    72: 10,  # GPIO 72 -> Pin 10
                    12: 32,  # GPIO 12 -> Pin 32
                    16: 36,  # GPIO 16 -> Pin 36
                    20: 38   # GPIO 20 -> Pin 38
                }

                for led_id, gpio_pin in self.led_pins.items():
                    if gpio_pin is not None and gpio_pin in physical_pins:
                        physical_pin = physical_pins[gpio_pin]
                        GPIO.setup(physical_pin, GPIO.OUT)
                        GPIO.output(physical_pin, GPIO.LOW)  # Start with LEDs off
                        self.leds[led_id] = {
                            'gpio_pin': gpio_pin,
                            'physical_pin': physical_pin,
                            'state': False
                        }
                        logger.info(f"LED {led_id} configured on GPIO {gpio_pin} (Physical Pin {physical_pin})")
            else:
                # Setup LED pins using gpiozero
                for led_id, pin in self.led_pins.items():
                    if pin is not None:
                        self._setup_led(led_id, pin)

            logger.info(f"Initialized {len(self.led_pins)} LEDs")
            self.gpio_initialized = True

            # Flash all LEDs on startup to test
            await self.test_all_leds()

        except Exception as e:
            logger.error(f"Failed to initialize LED GPIO: {e}")
            # Don't raise - allow kiosk to run without LED control

    def _setup_led(self, led_id: int, pin: int):
        """Setup a single LED pin using gpiozero"""
        logger.debug(f"Setting up LED {led_id} on GPIO {pin}")

        try:
            led = LED(pin)
            led.off()  # Start with LED off
            self.leds[led_id] = led
            logger.info(f"LED {led_id} configured on GPIO {pin}")

        except Exception as e:
            logger.error(f"Failed to setup LED {led_id} on GPIO {pin}: {e}")

    async def _setup_sysfs_led(self, led_id: int, pin: int):
        """Setup an LED using custom sysfs GPIO implementation"""
        logger.debug(f"Setting up sysfs LED {led_id} on GPIO {pin}")

        try:
            from .orangepi_gpio import OrangePiLED

            led = OrangePiLED(pin)
            if led.setup():
                led.off()  # Start with LED off
                self.leds[led_id] = led
                logger.info(f"Sysfs LED {led_id} configured on GPIO {pin}")
            else:
                logger.error(f"Failed to setup sysfs LED {led_id} on GPIO {pin}")

        except Exception as e:
            logger.error(f"Failed to setup sysfs LED {led_id} on GPIO {pin}: {e}")

    async def set_led(self, led_id: int, state: bool):
        """Set LED state (True = on, False = off)"""
        if not self.gpio_initialized:
            logger.debug(f"GPIO not initialized, cannot set LED {led_id}")
            return

        if led_id not in self.leds:
            logger.warning(f"LED {led_id} not configured")
            return

        try:
            if SYSFS_GPIO:
                # Use sysfs LED object
                led = self.leds[led_id]
                if state:
                    led.on()
                else:
                    led.off()
                logger.debug(f"LED {led_id} {'ON' if state else 'OFF'}")
            elif ORANGEPI_GPIO:
                led_info = self.leds[led_id]
                GPIO.output(led_info['physical_pin'], GPIO.HIGH if state else GPIO.LOW)
                led_info['state'] = state
                logger.debug(f"LED {led_id} {'ON' if state else 'OFF'}")
            else:
                # gpiozero or mock
                led = self.leds[led_id]
                if state:
                    led.on()
                else:
                    led.off()
                logger.debug(f"LED {led_id} {'ON' if state else 'OFF'}")

        except Exception as e:
            logger.error(f"Failed to set LED {led_id} state: {e}")

    async def toggle_led(self, led_id: int):
        """Toggle LED state"""
        if not self.gpio_initialized:
            return

        if led_id not in self.leds:
            logger.warning(f"LED {led_id} not configured")
            return

        try:
            if SYSFS_GPIO:
                led = self.leds[led_id]
                led.toggle()
                logger.debug(f"LED {led_id} toggled")
            elif ORANGEPI_GPIO:
                led_info = self.leds[led_id]
                new_state = not led_info['state']
                await self.set_led(led_id, new_state)
            else:
                led = self.leds[led_id]
                led.toggle()
                logger.debug(f"LED {led_id} toggled")

        except Exception as e:
            logger.error(f"Failed to toggle LED {led_id}: {e}")

    async def flash_led(self, led_id: int, duration: float = 0.5, count: int = 1):
        """Flash LED for button press feedback"""
        for _ in range(count):
            await self.set_led(led_id, True)
            await asyncio.sleep(duration / 2)
            await self.set_led(led_id, False)
            if count > 1:
                await asyncio.sleep(duration / 2)

    async def pulse_led(self, led_id: int, duration: float = 2.0):
        """Pulse LED during video playback"""
        pulse_steps = 20
        step_time = duration / (pulse_steps * 2)

        # Fade in
        for i in range(pulse_steps):
            await self.set_led(led_id, True)
            await asyncio.sleep(step_time)
            await self.set_led(led_id, False)
            await asyncio.sleep(step_time * 0.1)

    async def test_all_leds(self):
        """Test all LEDs on startup"""
        logger.info("Testing all LEDs...")

        # Turn all LEDs on
        for led_id in self.leds.keys():
            await self.set_led(led_id, True)

        await asyncio.sleep(0.5)

        # Turn all LEDs off
        for led_id in self.leds.keys():
            await self.set_led(led_id, False)

        await asyncio.sleep(0.2)

        # Flash each LED individually
        for led_id in self.leds.keys():
            await self.flash_led(led_id, 0.3)
            await asyncio.sleep(0.1)

        logger.info("LED test complete")

    async def all_leds_off(self):
        """Turn off all LEDs"""
        for led_id in self.leds.keys():
            await self.set_led(led_id, False)

    async def cleanup(self):
        """Clean up LED GPIO resources"""
        logger.info("Cleaning up LED controller")

        # Turn off all LEDs
        await self.all_leds_off()

        if SYSFS_GPIO:
            # Clean up sysfs LEDs
            for led_id, led in self.leds.items():
                try:
                    led.cleanup()
                except:
                    pass
        elif ORANGEPI_GPIO and self.gpio_initialized:
            try:
                GPIO.cleanup()
            except:
                pass
        else:
            # Clean up gpiozero LEDs
            for led_id, led in self.leds.items():
                try:
                    led.close()
                except:
                    pass

        self.leds.clear()
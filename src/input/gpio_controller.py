import asyncio
import logging
import time
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Try different GPIO libraries in order of preference for OrangePi
ORANGEPI_GPIO = False
SYSFS_GPIO = False
GPIO_AVAILABLE = False


def _is_raspberry_pi():
    """Detect a Raspberry Pi so we skip the Allwinner-specific sysfs path."""
    try:
        return "Raspberry Pi" in Path("/proc/device-tree/model").read_text(errors="ignore")
    except Exception:
        return False


_IS_PI = _is_raspberry_pi()

if _IS_PI:
    # Raspberry Pi: go straight to gpiozero. Don't try OrangePi.GPIO (wrong
    # board) or RPi.GPIO (doesn't support Pi 5's RP1 chip) since they would
    # import successfully but break or use the wrong pin numbering.
    try:
        from gpiozero import Button
        from gpiozero.exc import GPIOZeroError
        GPIO_AVAILABLE = True
        logger.info("Raspberry Pi detected — using gpiozero")
    except ImportError:
        logger.error("gpiozero unavailable on Raspberry Pi — install python3-gpiozero")
        GPIO_AVAILABLE = False
# Allwinner / non-Pi fallback chain (skipped if _IS_PI handled above).
try:
    if _IS_PI:
        raise ImportError("Pi already handled above")
    from .orangepi_gpio import OrangePiButton, is_sysfs_gpio_available
    if is_sysfs_gpio_available():
        GPIO_AVAILABLE = True
        SYSFS_GPIO = True
        logger.info("Using custom OrangePi sysfs GPIO implementation")
    else:
        raise ImportError("No sysfs GPIO access available")
except ImportError:
    try:
        # Try OrangePi GPIO as fallback
        import OrangePi.GPIO as GPIO
        ORANGEPI_GPIO = True
        GPIO_AVAILABLE = True
        logger.info("Using OrangePi.GPIO library")
    except ImportError:
        try:
            # Try RPi.GPIO as fallback (sometimes works on OrangePi)
            import RPi.GPIO as GPIO
            GPIO_AVAILABLE = True
            logger.info("Using RPi.GPIO library")
        except ImportError:
            try:
                # Fallback to gpiozero
                from gpiozero import Button
                from gpiozero.exc import GPIOZeroError
                GPIO_AVAILABLE = True
                logger.info("Using gpiozero library")
            except ImportError:
                logger.warning("No GPIO library available, using mock GPIO")
                GPIO_AVAILABLE = False

                class Button:
                    """Mock Button class for development"""
                    def __init__(self, pin, pull_up=True, bounce_time=None):
                        self.pin = pin

                    @property
                    def when_pressed(self):
                        return None

                    @when_pressed.setter
                    def when_pressed(self, callback):
                        pass

                    def close(self):
                        pass

from .button_mapper import ButtonMapper
from .debouncer import Debouncer
from .led_controller import LEDController

logger = logging.getLogger(__name__)


class GPIOController:
    def __init__(self, settings):
        self.settings = settings
        self.button_mapper = ButtonMapper(settings)
        self.debouncer = Debouncer(settings.input.debounce_time)
        self.led_controller = LEDController(settings)

        # Callback for button press events
        self.on_button_press = None

        # asyncio event loop captured at initialize() time so we can schedule
        # coroutines from gpiozero's background callback thread (where
        # asyncio.create_task() throws because no loop is running there).
        self._loop = None

        # GPIO pin configuration
        self.button_pins = {
            1: settings.input.button1_pin,
            2: settings.input.button2_pin,
            3: settings.input.button3_pin,
            4: settings.input.button4_pin,
        }

        # Store button objects for cleanup
        self.buttons = {}
        self.gpio_initialized = False
        
    async def initialize(self):
        """Initialize GPIO pins"""
        # Capture the running asyncio loop so callbacks fired from gpiozero's
        # background thread can schedule coroutines back onto it.
        self._loop = asyncio.get_running_loop()

        if ORANGEPI_GPIO:
            logger.info("Initializing GPIO controller (OrangePi compatible)")
        else:
            logger.info("Initializing GPIO controller (Raspberry Pi compatible)")

        if not GPIO_AVAILABLE:
            logger.warning("GPIO not available - running in mock mode")
            return

        try:
            if ORANGEPI_GPIO:
                # Initialize OrangePi GPIO
                GPIO.setmode(GPIO.BOARD)
                GPIO.setup([pin for pin in self.button_pins.values() if pin is not None], GPIO.IN, pull_up_down=GPIO.PUD_UP)

                # Setup interrupt callbacks for OrangePi
                for button_id, pin in self.button_pins.items():
                    if pin is not None:
                        GPIO.add_event_detect(pin, GPIO.FALLING, callback=lambda channel, btn_id=button_id: self._orangepi_callback(btn_id, channel), bouncetime=self.settings.input.debounce_time)
            elif SYSFS_GPIO:
                # Initialize custom sysfs GPIO buttons
                for button_id, pin in self.button_pins.items():
                    if pin is not None:
                        await self._setup_sysfs_button(button_id, pin)
            else:
                # Setup button pins using gpiozero for Raspberry Pi
                for button_id, pin in self.button_pins.items():
                    if pin is not None:
                        self._setup_button(button_id, pin)

            logger.info(f"Initialized {len(self.button_pins)} buttons")

            # Initialize LED controller
            await self.led_controller.initialize()

            self.gpio_initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            if ORANGEPI_GPIO:
                logger.error("Make sure OrangePi.GPIO is installed: pip install OrangePi.GPIO")
            else:
                logger.error("Make sure gpiozero is installed: pip install gpiozero")
            # Don't raise - allow kiosk to run without GPIO
            
    def _setup_button(self, button_id: int, pin: int):
        """Setup a single button pin"""
        logger.debug(f"Setting up button {button_id} on GPIO {pin}")
        
        try:
            # Create button with pull-up and debounce
            button = Button(
                pin, 
                pull_up=True, 
                bounce_time=self.settings.input.debounce_time / 1000.0  # Convert ms to seconds
            )
            
            # Set callback for button press
            button.when_pressed = lambda: self._button_callback(button_id, pin)
            
            # Store button object
            self.buttons[button_id] = button
            
            logger.info(f"Button {button_id} configured on GPIO {pin}")
            
        except Exception as e:
            logger.error(f"Failed to setup button {button_id} on GPIO {pin}: {e}")

    async def _setup_sysfs_button(self, button_id: int, pin: int):
        """Setup a button using custom sysfs GPIO implementation"""
        logger.debug(f"Setting up sysfs button {button_id} on GPIO {pin}")

        try:
            from .orangepi_gpio import OrangePiButton

            # Create sysfs button
            button = OrangePiButton(pin, pull_up=True)

            if button.setup():
                # Set callback for button press
                button.set_callback(lambda: self._sysfs_callback(button_id, pin))

                # Start monitoring
                await button.start_monitoring()

                # Store button object
                self.buttons[button_id] = button

                logger.info(f"Sysfs button {button_id} configured on GPIO {pin}")
            else:
                logger.error(f"Failed to setup sysfs button {button_id} on GPIO {pin}")

        except Exception as e:
            logger.error(f"Failed to setup sysfs button {button_id} on GPIO {pin}: {e}")

    def _button_callback(self, button_id: int, pin: int):
        """Handle button press from gpiozero (runs in gpiozero's worker thread)."""
        if not self.debouncer.should_process(button_id):
            return

        logger.info(f"Button {button_id} pressed (GPIO {pin})")

        # We are in a non-asyncio thread; schedule coroutines onto the main
        # event loop with run_coroutine_threadsafe (asyncio.create_task here
        # would throw "no running event loop").
        if self._loop is None:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self.led_controller.flash_led(button_id, 0.3), self._loop)
        except Exception as e:
            logger.error(f"Failed to schedule LED flash for button {button_id}: {e}")

        if self.on_button_press:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.on_button_press(button_id), self._loop)
            except Exception as e:
                logger.error(f"Failed to schedule on_button_press for {button_id}: {e}")

    def _sysfs_callback(self, button_id: int, pin: int):
        """Handle button press for sysfs GPIO"""
        # Check debouncer (additional software debounce)
        if not self.debouncer.should_process(button_id):
            return

        logger.info(f"Button {button_id} pressed (sysfs GPIO {pin})")

        # Flash LED for button feedback
        asyncio.create_task(self.led_controller.flash_led(button_id, 0.3))

        # Call the registered callback
        if self.on_button_press:
            asyncio.create_task(self.on_button_press(button_id))

    def _orangepi_callback(self, button_id: int, channel: int):
        """Handle button press interrupt for OrangePi"""
        # Check debouncer (additional software debounce)
        if not self.debouncer.should_process(button_id):
            return

        logger.info(f"Button {button_id} pressed (GPIO {channel})")

        # Flash LED for button feedback
        asyncio.create_task(self.led_controller.flash_led(button_id, 0.3))

        # Call the registered callback
        if self.on_button_press:
            asyncio.create_task(self.on_button_press(button_id))
            
    async def cleanup(self):
        """Clean up GPIO resources"""
        logger.info("Cleaning up GPIO controller")

        # Clean up LED controller
        await self.led_controller.cleanup()

        if ORANGEPI_GPIO and self.gpio_initialized:
            try:
                GPIO.cleanup()
            except:
                pass
        elif SYSFS_GPIO:
            # Clean up sysfs buttons
            for button_id, button in self.buttons.items():
                try:
                    button.cleanup()
                except:
                    pass
            self.buttons.clear()
        else:
            # Clean up gpiozero buttons
            for button_id, button in self.buttons.items():
                try:
                    button.close()
                except:
                    pass
            self.buttons.clear()
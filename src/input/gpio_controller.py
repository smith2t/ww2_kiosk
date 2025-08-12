import asyncio
import logging
import time
from typing import Callable, Dict, Optional

try:
    # Use gpiozero - works on Pi 5 and older models
    from gpiozero import Button
    from gpiozero.exc import GPIOZeroError
    GPIO_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("gpiozero not available, using mock GPIO")
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

logger = logging.getLogger(__name__)


class GPIOController:
    def __init__(self, settings):
        self.settings = settings
        self.button_mapper = ButtonMapper(settings)
        self.debouncer = Debouncer(settings.input.debounce_time)
        
        # Callback for button press events
        self.on_button_press = None
        
        # GPIO pin configuration
        self.button_pins = {
            1: settings.input.button1_pin,
            2: settings.input.button2_pin,
            3: settings.input.button3_pin,
            4: settings.input.button4_pin,
        }
        
        # Store button objects for cleanup
        self.buttons = {}
        
    async def initialize(self):
        """Initialize GPIO pins"""
        logger.info("Initializing GPIO controller (Pi 5 compatible)")
        
        if not GPIO_AVAILABLE:
            logger.warning("GPIO not available - running in mock mode")
            return
        
        try:
            # Setup button pins using gpiozero
            for button_id, pin in self.button_pins.items():
                if pin is not None:
                    self._setup_button(button_id, pin)
                    
            logger.info(f"Initialized {len(self.buttons)} buttons")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
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
        
    def _button_callback(self, button_id: int, pin: int):
        """Handle button press interrupt"""
        # Check debouncer (additional software debounce)
        if not self.debouncer.should_process(button_id):
            return
            
        logger.info(f"Button {button_id} pressed (GPIO {pin})")
        
        # Call the registered callback
        if self.on_button_press:
            asyncio.create_task(self.on_button_press(button_id))
            
    async def cleanup(self):
        """Clean up GPIO resources"""
        logger.info("Cleaning up GPIO controller")
        for button_id, button in self.buttons.items():
            try:
                button.close()
            except:
                pass
        self.buttons.clear()
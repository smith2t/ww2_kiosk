import asyncio
import logging
import time
from typing import Callable, Dict

try:
    import RPi.GPIO as GPIO
except ImportError:
    # Mock GPIO for development on non-Raspberry Pi systems
    logger = logging.getLogger(__name__)
    logger.warning("RPi.GPIO not available, using mock GPIO")
    
    class MockGPIO:
        BCM = "BCM"
        IN = "IN"
        PUD_UP = "PUD_UP"
        FALLING = "FALLING"
        
        @staticmethod
        def setmode(mode): pass
        
        @staticmethod
        def setup(pin, direction, pull_up_down=None): pass
        
        @staticmethod
        def add_event_detect(pin, edge, callback=None, bouncetime=None): pass
        
        @staticmethod
        def cleanup(): pass
    
    GPIO = MockGPIO()

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
        
    async def initialize(self):
        """Initialize GPIO pins"""
        logger.info("Initializing GPIO controller")
        
        try:
            # Set GPIO mode
            GPIO.setmode(GPIO.BCM)
            
            # Setup button pins
            for button_id, pin in self.button_pins.items():
                if pin is not None:
                    self._setup_button(button_id, pin)
                    
            logger.info(f"Initialized {len(self.button_pins)} buttons")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            raise
            
    def _setup_button(self, button_id: int, pin: int):
        """Setup a single button pin"""
        logger.debug(f"Setting up button {button_id} on GPIO {pin}")
        
        # Configure pin as input with pull-up resistor
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Add falling edge detection (button press)
        GPIO.add_event_detect(
            pin,
            GPIO.FALLING,
            callback=lambda channel: self._button_callback(button_id, channel),
            bouncetime=self.settings.input.debounce_time
        )
        
    def _button_callback(self, button_id: int, channel: int):
        """Handle button press interrupt"""
        # Check debouncer
        if not self.debouncer.should_process(button_id):
            return
            
        logger.info(f"Button {button_id} pressed (GPIO {channel})")
        
        # Call the registered callback
        if self.on_button_press:
            asyncio.create_task(self.on_button_press(button_id))
            
    async def cleanup(self):
        """Clean up GPIO resources"""
        logger.info("Cleaning up GPIO controller")
        GPIO.cleanup()
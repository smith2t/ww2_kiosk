#!/usr/bin/env python3

import asyncio
import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from display.display_controller import DisplayController
from display.led_controller import LEDController
from input.gpio_controller import GPIOController
from media.content_loader import ContentLoader
from network.ap_manager import AccessPointManager
from network.smb_server import SMBServer
from network.web_interface import WebInterface

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WW2Kiosk:
    def __init__(self, debug=False):
        self.debug = debug
        self.settings = Settings()
        self.running = False
        
        self.display_controller = None
        self.led_controller = None
        self.gpio_controller = None
        self.content_loader = None
        self.ap_manager = None
        self.smb_server = None
        self.web_interface = None

        # Thread locking for button presses (inspired by rpi-vidlooper)
        self.button_lock = threading.Lock()
        self.last_button_press = 0
        self.button_debounce_time = 1.0  # 1 second debounce
        
    async def initialize(self):
        """Initialize all subsystems"""
        logger.info("Initializing WW2 Kiosk...")

        try:
            # Initialize LED controller first for boot sequence
            self.led_controller = LEDController(self.settings)
            if await self.led_controller.initialize():
                # Start boot sequence in background
                asyncio.create_task(self.led_controller.boot_sequence())
                await self.led_controller.progress_indicator("Starting initialization", 6, 1)

            # Load media content
            self.content_loader = ContentLoader(self.settings)
            await self.content_loader.scan_media()
            if self.led_controller:
                await self.led_controller.progress_indicator("Loading media content", 6, 2)

            # Initialize display
            self.display_controller = DisplayController(self.settings)
            await self.display_controller.initialize()
            if self.led_controller:
                await self.led_controller.progress_indicator("Initializing display", 6, 3)

            # Initialize GPIO
            self.gpio_controller = GPIOController(self.settings)
            self.gpio_controller.on_button_press = self.handle_button_press
            await self.gpio_controller.initialize()
            if self.led_controller:
                await self.led_controller.progress_indicator("Setting up GPIO controls", 6, 4)
            
            # Initialize network services
            if self.settings.network.enable_ap:
                self.ap_manager = AccessPointManager(self.settings)
                await self.ap_manager.start()
                if self.led_controller:
                    await self.led_controller.progress_indicator("Starting WiFi access point", 6, 5)

            if self.settings.network.enable_smb:
                self.smb_server = SMBServer(self.settings)
                await self.smb_server.start()

            # Initialize web interface
            if self.settings.network.enable_web:
                self.web_interface = WebInterface(self.settings)
                # Start web interface in background
                asyncio.create_task(self.web_interface.start(
                    host=self.settings.network.web_host,
                    port=self.settings.network.web_port
                ))

            if self.led_controller:
                await self.led_controller.progress_indicator("Initialization complete", 6, 6)
                # Wait a moment to show completion
                await asyncio.sleep(2)

            logger.info("Initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            raise
    
    async def handle_button_press(self, button_id):
        """Handle button press events with thread locking to prevent rapid presses"""
        current_time = time.time()

        # Thread locking to prevent issues with rapid button presses
        with self.button_lock:
            # Debounce check - ignore if too soon after last press
            if current_time - self.last_button_press < self.button_debounce_time:
                logger.debug(f"Button {button_id} press ignored (debounce)")
                return

            self.last_button_press = current_time
            logger.info(f"Button {button_id} pressed")

            # Provide LED feedback for button press
            if self.led_controller:
                await self.led_controller.button_feedback(button_id)

            video_file = self.content_loader.get_video_for_button(button_id)
            if video_file:
                # Show which video is playing via LED
                if self.led_controller:
                    await self.led_controller.video_playing_indicator(button_id)

                # Add countdown before video starts (like Alex's design)
                await self._show_countdown(button_id)
                await self.display_controller.play_video(video_file)
            else:
                logger.warning(f"No video mapped to button {button_id}")

    async def _show_countdown(self, button_id):
        """Show countdown before video starts"""
        countdown_time = 3  # 3 second countdown
        logger.info(f"Starting video {button_id} in {countdown_time} seconds...")

        for i in range(countdown_time, 0, -1):
            logger.info(f"Video starting in {i}...")

            # Flash the corresponding LED during countdown
            if self.led_controller:
                await self.led_controller.set_led(button_id, True)
                await asyncio.sleep(0.3)
                await self.led_controller.set_led(button_id, False)
                await asyncio.sleep(0.7)

        logger.info("Starting video now!")
    
    async def run(self):
        """Main run loop"""
        self.running = True
        logger.info("Starting WW2 Kiosk...")
        
        try:
            # Start slideshow by default
            await self.display_controller.start_slideshow()

            # Start slideshow LED indicator
            if self.led_controller:
                asyncio.create_task(self.led_controller.slideshow_mode_indicator())

            # Main event loop
            while self.running:
                await asyncio.sleep(0.1)

                # Check for idle timeout
                if self.display_controller.should_return_to_slideshow():
                    await self.display_controller.start_slideshow()
                    # Restart slideshow LED indicator
                    if self.led_controller:
                        await self.led_controller.stop_animations()
                        asyncio.create_task(self.led_controller.slideshow_mode_indicator())
                    
        except Exception as e:
            logger.error(f"Runtime error: {e}")
            raise
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down WW2 Kiosk...")
        self.running = False
        
        if self.led_controller:
            await self.led_controller.cleanup()

        if self.display_controller:
            await self.display_controller.cleanup()

        if self.gpio_controller:
            await self.gpio_controller.cleanup()

        if self.ap_manager:
            await self.ap_manager.stop()

        if self.smb_server:
            await self.smb_server.stop()

        if self.web_interface:
            await self.web_interface.stop()

        logger.info("Shutdown complete")


async def main():
    parser = argparse.ArgumentParser(description='WW2 Kiosk Application')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--config', type=str, help='Path to config file')
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    kiosk = WW2Kiosk(debug=args.debug)
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(kiosk.shutdown())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await kiosk.initialize()
        await kiosk.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await kiosk.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path

from config.settings import Settings
from display.display_controller import DisplayController
from input.gpio_controller import GPIOController
from media.content_loader import ContentLoader
from network.ap_manager import AccessPointManager
from network.smb_server import SMBServer

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
        self.gpio_controller = None
        self.content_loader = None
        self.ap_manager = None
        self.smb_server = None
        
    async def initialize(self):
        """Initialize all subsystems"""
        logger.info("Initializing WW2 Kiosk...")
        
        try:
            # Load media content
            self.content_loader = ContentLoader(self.settings)
            await self.content_loader.scan_media()
            
            # Initialize display
            self.display_controller = DisplayController(self.settings)
            await self.display_controller.initialize()
            
            # Initialize GPIO
            self.gpio_controller = GPIOController(self.settings)
            self.gpio_controller.on_button_press = self.handle_button_press
            await self.gpio_controller.initialize()
            
            # Initialize network services
            if self.settings.network.enable_ap:
                self.ap_manager = AccessPointManager(self.settings)
                await self.ap_manager.start()
            
            if self.settings.network.enable_smb:
                self.smb_server = SMBServer(self.settings)
                await self.smb_server.start()
            
            logger.info("Initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            raise
    
    async def handle_button_press(self, button_id):
        """Handle button press events"""
        logger.info(f"Button {button_id} pressed")
        
        video_file = self.content_loader.get_video_for_button(button_id)
        if video_file:
            await self.display_controller.play_video(video_file)
        else:
            logger.warning(f"No video mapped to button {button_id}")
    
    async def run(self):
        """Main run loop"""
        self.running = True
        logger.info("Starting WW2 Kiosk...")
        
        try:
            # Start slideshow by default
            await self.display_controller.start_slideshow()
            
            # Main event loop
            while self.running:
                await asyncio.sleep(0.1)
                
                # Check for idle timeout
                if self.display_controller.should_return_to_slideshow():
                    await self.display_controller.start_slideshow()
                    
        except Exception as e:
            logger.error(f"Runtime error: {e}")
            raise
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down WW2 Kiosk...")
        self.running = False
        
        if self.display_controller:
            await self.display_controller.cleanup()
        
        if self.gpio_controller:
            await self.gpio_controller.cleanup()
        
        if self.ap_manager:
            await self.ap_manager.stop()
        
        if self.smb_server:
            await self.smb_server.stop()
        
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
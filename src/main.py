#!/usr/bin/env python3

import asyncio
import argparse
import logging
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from display.display_controller import DisplayController, DisplayMode
from display.led_controller import LEDController
from input.category_store import CategoryStore
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
        # Strong refs for long-running asyncio tasks. Without these, asyncio
        # holds only weak refs and may garbage-collect them mid-execution —
        # symptom: LED animations and the slideshow indicator silently die.
        self._bg_tasks = set()

        # Thread locking for button presses (inspired by rpi-vidlooper)
        self.button_lock = threading.Lock()
        self.last_button_press = 0
        self.button_debounce_time = 1.0  # 1 second debounce

        # Recent button history for the hidden shutdown combo (kept short).
        self._press_history: deque = deque(maxlen=8)
        
    async def initialize(self):
        """Initialize all subsystems"""
        logger.info("Initializing WW2 Kiosk...")

        try:
            # Initialize LED controller first for boot sequence
            self.led_controller = LEDController(self.settings)
            if await self.led_controller.initialize():
                # Start boot sequence in background (keep ref so it isn't GC'd)
                t = asyncio.create_task(self.led_controller.boot_sequence())
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)
                await self.led_controller.progress_indicator("Starting initialization", 6, 1)

            # Load media content
            self.content_loader = ContentLoader(self.settings)
            await self.content_loader.scan_media()
            if self.led_controller:
                await self.led_controller.progress_indicator("Loading media content", 6, 2)

            # CategoryStore replaces the old ButtonMapper — same JSON dir,
            # but a richer schema with N items per category.
            self.store = CategoryStore(self.settings)

            # Initialize display
            self.display_controller = DisplayController(self.settings, self.store)
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
        """Three-state machine:
            slideshow      + any-button -> show CATEGORY_MENU
            CATEGORY_MENU  + button N   -> show ITEM_MENU for category N
            ITEM_MENU      + slot 1..3  -> play that item
            ITEM_MENU      + button 4 (paginated) -> next page
            VIDEO          + any-button -> stop playback
        """
        current_time = time.time()

        # Hidden admin shutdown combo — recorded BEFORE the debounce gate so
        # rapid 1-1-4-1 always counts even when the 1-sec debounce would
        # drop some presses for normal mode-handling purposes.
        self._press_history.append((button_id, current_time))
        if self._is_shutdown_combo():
            await self._initiate_shutdown()
            return

        # Debounce for the regular mode-handling path (menus / playback).
        with self.button_lock:
            if current_time - self.last_button_press < self.button_debounce_time:
                logger.debug(f"Button {button_id} press ignored (debounce)")
                return
            self.last_button_press = current_time

        dc = self.display_controller
        mode = dc.current_mode
        logger.info(f"Button {button_id} pressed (mode={mode.value})")

        if self.led_controller:
            await self.led_controller.button_feedback(button_id)

        if mode == DisplayMode.VIDEO:
            logger.info("Button press during playback — stopping")
            await dc.stop_active_media()
            return

        if mode == DisplayMode.SLIDESHOW or mode == DisplayMode.IDLE:
            await dc.show_category_menu()
            return

        if mode == DisplayMode.CATEGORY_MENU:
            await dc.show_item_menu(button_id)
            return

        if mode == DisplayMode.ITEM_MENU:
            choice = dc.item_menu.selection_for_button(button_id)
            if choice[0] == 'next':
                dc.item_menu.next_page()
                dc.reset_menu_timeout()
                dc.item_menu.draw()
                return
            if choice[0] == 'back_to_topics':
                await dc.show_category_menu()
                return
            if choice[0] == 'play':
                _, item, idx = choice
                resolved = self.store.resolve_item_path(dc.item_menu.cat_id, idx)
                if not resolved:
                    logger.warning(f"Item file missing on disk: {item.file}")
                    return
                if self.led_controller:
                    await self.led_controller.video_playing_indicator(button_id)
                await self._show_countdown(button_id)
                # Route by file extension: PDFs play page-by-page in pygame,
                # videos hand off to mpv.
                if resolved.lower().endswith('.pdf'):
                    await dc.play_pdf(resolved)
                else:
                    await dc.play_video(resolved)
                return
            # 'noop' — empty slot or no items
            return

    def _is_shutdown_combo(self) -> bool:
        """True iff the recent press history ends with the configured shutdown
        combo and all those presses happened within shutdown_window_sec."""
        combo = (self.settings.input.shutdown_combo or "").strip()
        if not combo:
            return False
        window = float(getattr(self.settings.input, 'shutdown_window_sec', 10))
        n = len(combo)
        if len(self._press_history) < n:
            return False
        last_n = list(self._press_history)[-n:]
        # Window check on the wall-clock spread of the matching tail.
        if last_n[-1][1] - last_n[0][1] > window:
            return False
        return ''.join(str(b) for b, _ in last_n) == combo

    async def _initiate_shutdown(self):
        logger.warning("Shutdown combo detected — powering off in 3 seconds")

        # Tear down anything that would keep flipping the pygame surface so
        # our "Shutting down..." overlay actually stays on screen.
        try:
            await self.display_controller.stop_active_media()
        except Exception as e:
            logger.warning(f"stop_active_media on shutdown: {e}")
        try:
            await self.display_controller.slideshow.stop()
        except Exception as e:
            logger.warning(f"slideshow.stop on shutdown: {e}")

        # Show a big "Shutting down..." overlay so an accidental match is
        # visible before the system actually halts.
        try:
            import pygame
            screen = pygame.display.get_surface()
            if screen is not None:
                screen.fill((40, 0, 0))
                font = pygame.font.SysFont('Arial', 96, bold=True)
                msg = font.render("Shutting down...", True, (255, 220, 220))
                screen.blit(msg, msg.get_rect(center=screen.get_rect().center))
                pygame.display.flip()
        except Exception as e:
            logger.warning(f"shutdown overlay failed: {e}")

        # Clear press history so a slow poweroff can't loop into another match.
        self._press_history.clear()

        await asyncio.sleep(3)
        try:
            subprocess.Popen(["sudo", "/sbin/poweroff"])
        except Exception as e:
            logger.error(f"poweroff failed: {e}")

    async def _show_countdown(self, button_id):
        """Show countdown before video starts. Length is set by
        display.countdown_sec in config and editable from /settings."""
        countdown_time = max(0, int(getattr(self.settings.display, 'countdown_sec', 3)))
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

            # Start slideshow LED indicator (keep ref so asyncio doesn't GC it)
            if self.led_controller:
                t = asyncio.create_task(self.led_controller.slideshow_mode_indicator())
                self._bg_tasks.add(t)
                t.add_done_callback(self._bg_tasks.discard)

            # Main event loop
            while self.running:
                await asyncio.sleep(0.1)

                # Auto-return to slideshow if menu has been idle too long.
                if self.display_controller.menu_expired():
                    logger.info("Menu timed out — returning to slideshow")
                    await self.display_controller.start_slideshow()

                # Check for idle timeout
                if self.display_controller.should_return_to_slideshow():
                    await self.display_controller.start_slideshow()
                    # Restart slideshow LED indicator
                    if self.led_controller:
                        await self.led_controller.stop_animations()
                        t = asyncio.create_task(self.led_controller.slideshow_mode_indicator())
                        self._bg_tasks.add(t)
                        t.add_done_callback(self._bg_tasks.discard)
                    
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
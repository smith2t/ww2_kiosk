import asyncio
import logging
import time
from enum import Enum
from pathlib import Path

from .video_player import VideoPlayer
from .pdf_player import PdfPlayer
from .slideshow import Slideshow
from .menu import CategoryMenu, ItemMenu

logger = logging.getLogger(__name__)


class DisplayMode(Enum):
    SLIDESHOW = "slideshow"
    CATEGORY_MENU = "category_menu"
    ITEM_MENU = "item_menu"
    VIDEO = "video"
    IDLE = "idle"


class DisplayController:
    def __init__(self, settings, store=None):
        self.settings = settings
        self.store = store      # CategoryStore — None disables menus
        self.current_mode = DisplayMode.IDLE
        self.last_activity = time.time()
        self.menu_shown_at = 0.0

        self.video_player = VideoPlayer(settings)
        self.pdf_player = PdfPlayer(settings)
        self.slideshow = Slideshow(settings)
        self.category_menu = CategoryMenu(settings, store) if store else None
        self.item_menu = ItemMenu(settings, store) if store else None

        self.idle_timeout = settings.display.idle_timeout

        # Strong refs for background tasks. asyncio holds only weak refs and
        # may garbage-collect orphan tasks at any time — without this, the
        # _video_end_handler dies before the player exits and the slideshow
        # never resumes.
        self._bg_tasks = set()
        # Cancel any prior end-handler before starting a new video so back-to-
        # back presses can't leave a stale task firing extra slideshow restarts.
        self._end_handler_task = None
        
    async def initialize(self):
        """Initialize display subsystems"""
        logger.info("Initializing display controller")

        await self.video_player.initialize()
        await self.pdf_player.initialize()
        await self.slideshow.initialize()
        if self.category_menu:
            await self.category_menu.initialize(screen=self.slideshow.screen)
        if self.item_menu:
            await self.item_menu.initialize(screen=self.slideshow.screen)

    async def start_slideshow(self):
        """Start the picture slideshow"""
        logger.info("Starting slideshow mode")

        if self.current_mode == DisplayMode.VIDEO:
            await self.video_player.stop()

        self.current_mode = DisplayMode.SLIDESHOW
        await self.slideshow.start()

    async def show_category_menu(self):
        """Pause the slideshow and draw the top-level category menu."""
        if self.category_menu is None:
            logger.warning("show_category_menu called but no store available")
            return
        # Re-read categories.json so /categories edits apply without restart.
        if self.store is not None:
            self.store.load()
        logger.info("Showing category menu")
        await self.slideshow.stop()
        self.current_mode = DisplayMode.CATEGORY_MENU
        self.menu_shown_at = time.time()
        self.category_menu.draw()

    async def show_item_menu(self, cat_id):
        """Switch to the per-category item menu."""
        if self.item_menu is None:
            logger.warning("show_item_menu called but no store available")
            return
        if self.store is not None:
            self.store.load()
        logger.info(f"Showing item menu for category {cat_id}")
        # Slideshow already stopped if we came from the category menu, but
        # cover the slideshow->item-menu jump-in case too.
        if self.current_mode == DisplayMode.SLIDESHOW:
            await self.slideshow.stop()
        self.item_menu.open(cat_id)
        self.current_mode = DisplayMode.ITEM_MENU
        self.menu_shown_at = time.time()
        self.item_menu.draw()

    def reset_menu_timeout(self):
        """Called when a menu redraws after a 'Next' press, to keep it open."""
        self.menu_shown_at = time.time()

    def menu_expired(self) -> bool:
        # Read from settings each call so /settings edits take effect live.
        timeout = getattr(self.settings.display, 'menu_timeout_sec', 30)
        return (self.current_mode in (DisplayMode.CATEGORY_MENU, DisplayMode.ITEM_MENU)
                and time.time() - self.menu_shown_at > timeout)
        
    async def play_video(self, video_path):
        """Play a specific video"""
        logger.info(f"Playing video: {video_path}")

        if self.current_mode == DisplayMode.SLIDESHOW:
            await self.slideshow.stop()

        self.current_mode = DisplayMode.VIDEO
        self.last_activity = time.time()

        # Cancel any in-flight end-handler from a previous play so we don't
        # have two handlers racing to restart the slideshow.
        if self._end_handler_task and not self._end_handler_task.done():
            self._end_handler_task.cancel()

        await self.video_player.play(video_path)

        # Save a strong reference so asyncio doesn't GC the handler.
        self._end_handler_task = asyncio.create_task(self._video_end_handler())

    async def play_pdf(self, pdf_path):
        """Play a PDF page-by-page in pygame. Same state semantics as
        play_video — visitor can press any button mid-show to abort, and
        when the PDF finishes (or is aborted) we return to the item menu.
        """
        logger.info(f"Playing PDF: {pdf_path}")

        if self.current_mode == DisplayMode.SLIDESHOW:
            await self.slideshow.stop()

        self.current_mode = DisplayMode.VIDEO   # reuse VIDEO mode — same UX
        self.last_activity = time.time()

        if self._end_handler_task and not self._end_handler_task.done():
            self._end_handler_task.cancel()

        # PdfPlayer.play awaits internally page-by-page; wrap it so the
        # post-play return-to-menu logic runs after it finishes.
        self._end_handler_task = asyncio.create_task(self._pdf_play_handler(pdf_path))

    async def _pdf_play_handler(self, pdf_path):
        await self.pdf_player.play(pdf_path)
        logger.info("PDF playback completed")
        self.last_activity = time.time()
        # No wmctrl raise needed — we never left the pygame window.
        await asyncio.sleep(0.5)
        if self.item_menu is not None and self.item_menu.cat_id is not None:
            await self.show_item_menu(self.item_menu.cat_id)
        else:
            await self.start_slideshow()

    async def stop_active_media(self):
        """Stop whichever player (video or PDF) is currently active."""
        if self.video_player.is_playing:
            await self.video_player.stop()
        if self.pdf_player.is_playing:
            await self.pdf_player.stop()
        
    async def _video_end_handler(self):
        """Handle video playback completion. Returns to the item menu of the
        category we were playing from so the visitor can pick another item;
        the menu's idle timeout will eventually return to slideshow.
        """
        await self.video_player.wait_for_completion()
        logger.info("Video playback completed")
        self.last_activity = time.time()

        # Raise the kiosk pygame window back to the top of the X stack.
        try:
            proc = await asyncio.create_subprocess_exec(
                "wmctrl", "-a", "WW2 Kiosk",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception as e:
            logger.warning(f"wmctrl raise failed: {e}")

        await asyncio.sleep(1)
        # If we know which category the video came from, surface that menu
        # again so the visitor can pick another item without going all the
        # way back to slideshow.
        if self.item_menu is not None and self.item_menu.cat_id is not None:
            await self.show_item_menu(self.item_menu.cat_id)
        else:
            await self.start_slideshow()
        
    def should_return_to_slideshow(self):
        """Idle-timeout return is no longer the right mechanism — _video_end_handler
        already restarts the slideshow when mpv exits naturally. Returning True
        here while a video is playing forcibly killed mpv mid-clip after 30 sec.
        Kept as a no-op so the main run-loop's call site doesn't need to change.
        """
        return False
        
    async def cleanup(self):
        """Clean up display resources"""
        logger.info("Cleaning up display controller")
        
        await self.video_player.cleanup()
        await self.slideshow.cleanup()
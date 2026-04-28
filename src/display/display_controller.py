import asyncio
import logging
import time
from enum import Enum
from pathlib import Path

from .video_player import VideoPlayer
from .slideshow import Slideshow

logger = logging.getLogger(__name__)


class DisplayMode(Enum):
    SLIDESHOW = "slideshow"
    VIDEO = "video"
    IDLE = "idle"


class DisplayController:
    def __init__(self, settings):
        self.settings = settings
        self.current_mode = DisplayMode.IDLE
        self.last_activity = time.time()

        self.video_player = VideoPlayer(settings)
        self.slideshow = Slideshow(settings)

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
        await self.slideshow.initialize()
        
    async def start_slideshow(self):
        """Start the picture slideshow"""
        logger.info("Starting slideshow mode")
        
        if self.current_mode == DisplayMode.VIDEO:
            await self.video_player.stop()
        
        self.current_mode = DisplayMode.SLIDESHOW
        await self.slideshow.start()
        
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
        
    async def _video_end_handler(self):
        """Handle video playback completion"""
        await self.video_player.wait_for_completion()
        logger.info("Video playback completed, returning to slideshow")
        self.last_activity = time.time()

        # mpv ran with --ontop which pushed pygame's window down the X11 stack;
        # xfwm4 does NOT auto-restore on mpv exit, so without this the slideshow
        # renders into a window that's hidden behind xfdesktop. Raise the
        # pygame window back to the top before resuming.
        try:
            proc = await asyncio.create_subprocess_exec(
                "wmctrl", "-a", "WW2 Kiosk",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception as e:
            logger.warning(f"wmctrl raise failed: {e}")

        # Automatically return to slideshow
        await asyncio.sleep(2)  # Brief pause before returning to slideshow
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
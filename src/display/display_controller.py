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
        
        await self.video_player.play(video_path)
        
        # Return to slideshow after video ends
        asyncio.create_task(self._video_end_handler())
        
    async def _video_end_handler(self):
        """Handle video playback completion"""
        await self.video_player.wait_for_completion()
        logger.info("Video playback completed")
        self.last_activity = time.time()
        
    def should_return_to_slideshow(self):
        """Check if idle timeout has been reached"""
        if self.current_mode != DisplayMode.VIDEO:
            return False
            
        time_since_activity = time.time() - self.last_activity
        return time_since_activity > self.idle_timeout
        
    async def cleanup(self):
        """Clean up display resources"""
        logger.info("Cleaning up display controller")
        
        await self.video_player.cleanup()
        await self.slideshow.cleanup()
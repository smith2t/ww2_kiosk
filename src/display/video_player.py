import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class VideoPlayer:
    def __init__(self, settings):
        self.settings = settings
        self.current_process = None
        self.is_playing = False
        
        # Choose player based on platform
        self.player_cmd = settings.display.video_player or "vlc"
        
    async def initialize(self):
        """Initialize video player"""
        logger.info(f"Initializing video player with {self.player_cmd}")
        
        # Test if player is available
        try:
            result = subprocess.run(
                [self.player_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.debug(f"Video player version: {result.stdout[:100]}")
        except Exception as e:
            logger.error(f"Video player not available: {e}")
            raise
            
    async def play(self, video_path):
        """Play a video file"""
        video_file = Path(video_path)
        
        if not video_file.exists():
            logger.error(f"Video file not found: {video_path}")
            return False
            
        # Stop any current playback
        await self.stop()
        
        # Build command based on player
        if self.player_cmd == "vlc":
            cmd = [
                "vlc",
                "--fullscreen",
                "--play-and-exit",
                "--no-video-title-show",
                "--quiet",
                str(video_file)
            ]
        elif self.player_cmd == "omxplayer":
            cmd = [
                "omxplayer",
                "-b",  # Blank background
                "-o", "hdmi",  # Audio output
                str(video_file)
            ]
        else:
            cmd = [self.player_cmd, str(video_file)]
            
        logger.info(f"Starting video playback: {' '.join(cmd)}")
        
        try:
            self.current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            self.is_playing = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to start video playback: {e}")
            return False
            
    async def stop(self):
        """Stop current video playback"""
        if self.current_process and self.is_playing:
            logger.info("Stopping video playback")
            
            try:
                self.current_process.terminate()
                await asyncio.wait_for(
                    self.current_process.wait(),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Video player didn't terminate, forcing kill")
                self.current_process.kill()
                await self.current_process.wait()
            except Exception as e:
                logger.error(f"Error stopping video: {e}")
                
            self.current_process = None
            self.is_playing = False
            
    async def wait_for_completion(self):
        """Wait for current video to finish playing"""
        if self.current_process:
            await self.current_process.wait()
            self.is_playing = False
            self.current_process = None
            
    async def cleanup(self):
        """Clean up video player resources"""
        await self.stop()
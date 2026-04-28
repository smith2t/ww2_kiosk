import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_raspberry_pi():
    try:
        return "Raspberry Pi" in Path("/proc/device-tree/model").read_text(errors="ignore")
    except Exception:
        return False


_IS_PI = _is_raspberry_pi()


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
        
        # Build command based on player. mpv is the recommended choice — no
        # first-run privacy dialog, lighter than VLC, designed for embedded use.
        if self.player_cmd == "mpv":
            if _IS_PI:
                # Raspberry Pi 5: real V4L2 M2M hardware decode + working KMS
                # GPU output. Fullscreen with hwdec is buttery smooth.
                cmd = [
                    "mpv",
                    "--fullscreen",
                    "--ontop",
                    "--hwdec=auto-copy",
                ]
            else:
                # Allwinner H618 / Orange Pi: no usable hwdec, EGL/DRI2 auth
                # fails so we end up on SDL software output. Fullscreen choppy
                # at 1080p; windowed 1280x720 cuts per-frame work ~55%.
                cmd = [
                    "mpv",
                    "--geometry=1280x720+320+180",
                    "--no-border",
                    "--ontop",
                    "--hwdec=auto-copy",
                ]
            cmd.extend([
                "--no-osc",
                "--no-osd-bar",
                "--no-input-default-bindings",
                "--no-input-cursor",
                "--cursor-autohide=always",
                "--msg-level=all=error",
                "--no-terminal",
                str(video_file),
            ])
        elif self.player_cmd == "omxplayer":
            cmd = [
                "omxplayer",
                "-b",
                "-o", "both",
                "--no-osd",
                "--aspect-mode", "letterbox",
                str(video_file),
            ]
        elif self.player_cmd == "vlc":
            cmd = [
                "vlc",
                "--fullscreen",
                "--video-on-top",
                "--play-and-exit",
                "--no-video-title-show",
                "--no-osd",
                str(video_file),
            ]
        else:
            cmd = [self.player_cmd, str(video_file)]
            
        logger.info(f"Starting video playback: {' '.join(cmd)}")
        
        try:
            self.current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,  # capture so we can see why VLC failed
            )
            self.is_playing = True
            asyncio.create_task(self._log_stderr(self.current_process))
            return True

        except Exception as e:
            logger.error(f"Failed to start video playback: {e}")
            return False

    async def _log_stderr(self, proc):
        """Drain the player's stderr to the kiosk log so failures are visible."""
        if proc.stderr is None:
            return
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                logger.warning(f"[player] {line.decode(errors='replace').rstrip()}")
        except Exception as e:
            logger.error(f"Error draining player stderr: {e}")
            
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
import logging
from pathlib import Path
from typing import List, Optional

from .playlist_manager import PlaylistManager

logger = logging.getLogger(__name__)


class ContentLoader:
    def __init__(self, settings):
        self.settings = settings
        self.playlist_manager = PlaylistManager(settings)
        
        self.videos_dir = Path(settings.media.videos_dir)
        self.pictures_dir = Path(settings.media.pictures_dir)
        
        self.videos = []
        self.pictures = []
        
    async def scan_media(self):
        """Scan media directories for content"""
        logger.info("Scanning media directories")
        
        # Create directories if they don't exist
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.pictures_dir.mkdir(parents=True, exist_ok=True)
        
        # Scan for videos
        self.videos = await self._scan_videos()
        logger.info(f"Found {len(self.videos)} videos")
        
        # Scan for pictures
        self.pictures = await self._scan_pictures()
        logger.info(f"Found {len(self.pictures)} pictures")
        
        # Load playlists
        await self.playlist_manager.load_playlists()
        
    async def _scan_videos(self) -> List[Path]:
        """Scan for video files with format validation"""
        videos = []
        # Prioritize h264/mp4 for hardware acceleration (per Alex Lubbock's recommendations)
        preferred_extensions = ['*.mp4']
        other_extensions = ['*.avi', '*.mkv', '*.mov', '*.wmv']

        # Check for h264/mp4 files first
        for ext in preferred_extensions:
            found_videos = list(self.videos_dir.glob(ext)) + list(self.videos_dir.glob(ext.upper()))
            for video in found_videos:
                if await self._validate_video_format(video):
                    videos.append(video)
                else:
                    logger.warning(f"Video {video.name} may not be h264 format - playback issues possible")
                    videos.append(video)  # Still add it but warn

        # Then check other formats
        for ext in other_extensions:
            found_videos = list(self.videos_dir.glob(ext)) + list(self.videos_dir.glob(ext.upper()))
            for video in found_videos:
                videos.append(video)
                logger.info(f"Added video {video.name} (format: {ext})")

        return sorted(videos)

    async def _validate_video_format(self, video_path: Path) -> bool:
        """Validate video format for optimal playback"""
        try:
            # Try to get video info using ffprobe if available
            import subprocess
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries',
                'stream=codec_name', '-of', 'csv=p=0', str(video_path)
            ], capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                codecs = result.stdout.strip().split('\n')
                # Check if h264 codec is present
                has_h264 = 'h264' in codecs
                logger.debug(f"Video {video_path.name} codecs: {codecs}, h264: {has_h264}")
                return has_h264

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Could not validate video format for {video_path.name}: {e}")

        # If we can't validate, assume it's OK
        return True
        
    async def _scan_pictures(self) -> List[Path]:
        """Scan for picture files"""
        pictures = []
        picture_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']
        
        for ext in picture_extensions:
            pictures.extend(self.pictures_dir.glob(ext))
            pictures.extend(self.pictures_dir.glob(ext.upper()))
            
        return sorted(pictures)
        
    def get_video_for_button(self, button_id: int) -> Optional[str]:
        """Get video path for a button press"""
        from input.button_mapper import ButtonMapper
        mapper = ButtonMapper(self.settings)
        return mapper.get_video_for_button(button_id)
        
    def get_video_by_name(self, name: str) -> Optional[Path]:
        """Get video by filename"""
        for video in self.videos:
            if video.name == name:
                return video
        return None
        
    def get_picture_by_name(self, name: str) -> Optional[Path]:
        """Get picture by filename"""
        for picture in self.pictures:
            if picture.name == name:
                return picture
        return None
        
    async def refresh(self):
        """Refresh media content"""
        await self.scan_media()
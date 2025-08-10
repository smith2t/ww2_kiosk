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
        """Scan for video files"""
        videos = []
        video_extensions = ['*.mp4', '*.avi', '*.mkv', '*.mov', '*.wmv']
        
        for ext in video_extensions:
            videos.extend(self.videos_dir.glob(ext))
            videos.extend(self.videos_dir.glob(ext.upper()))
            
        return sorted(videos)
        
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
        # First check button mappings
        from ..input.button_mapper import ButtonMapper
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
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ButtonMapper:
    def __init__(self, settings):
        self.settings = settings
        self.mappings = {}
        self.load_mappings()
        
    def load_mappings(self):
        """Load button-to-video mappings from configuration"""
        mapping_file = Path(self.settings.config.button_mappings_file)
        
        if mapping_file.exists():
            try:
                with open(mapping_file, 'r') as f:
                    data = json.load(f)
                    self.mappings = data.get('mappings', {})
                    logger.info(f"Loaded {len(self.mappings)} button mappings")
            except Exception as e:
                logger.error(f"Failed to load button mappings: {e}")
                self.use_default_mappings()
        else:
            logger.warning(f"Mapping file not found: {mapping_file}")
            self.use_default_mappings()
            
    def use_default_mappings(self):
        """Use default button mappings"""
        self.mappings = {
            "1": "video1.mp4",
            "2": "video2.mp4",
            "3": "video3.mp4",
            "4": "video4.mp4"
        }
        logger.info("Using default button mappings")
        
    def get_video_for_button(self, button_id: int) -> Optional[str]:
        """Get the video file mapped to a button"""
        video_file = self.mappings.get(str(button_id))
        
        if video_file:
            video_path = Path(self.settings.media.videos_dir) / video_file
            if video_path.exists():
                return str(video_path)
            else:
                logger.warning(f"Video file not found: {video_path}")
                
        return None
        
    def update_mapping(self, button_id: int, video_file: str):
        """Update a button mapping"""
        self.mappings[str(button_id)] = video_file
        self.save_mappings()
        
    def save_mappings(self):
        """Save current mappings to file"""
        mapping_file = Path(self.settings.config.button_mappings_file)
        
        try:
            mapping_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(mapping_file, 'w') as f:
                json.dump({'mappings': self.mappings}, f, indent=2)
                
            logger.info("Button mappings saved")
        except Exception as e:
            logger.error(f"Failed to save button mappings: {e}")
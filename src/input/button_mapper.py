import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ButtonMapper:
    """Owns the button -> video filename + per-button description mapping.

    JSON schema (button_mappings.json):
        {
          "mappings":     {"1": "dday.mp4",     ...},
          "descriptions": {"1": "D-Day Normandy", ...}
        }
    """

    def __init__(self, settings):
        self.settings = settings
        self.mappings: Dict[str, str] = {}
        self.descriptions: Dict[str, str] = {}
        self.load_mappings()

    def load_mappings(self):
        mapping_file = Path(self.settings.config.button_mappings_file)

        if mapping_file.exists():
            try:
                with open(mapping_file, 'r') as f:
                    data = json.load(f)
                self.mappings = data.get('mappings', {}) or {}
                self.descriptions = data.get('descriptions', {}) or {}
                logger.info(f"Loaded {len(self.mappings)} button mappings"
                            f" ({sum(1 for d in self.descriptions.values() if d)} with descriptions)")
            except Exception as e:
                logger.error(f"Failed to load button mappings: {e}")
                self.use_default_mappings()
        else:
            logger.warning(f"Mapping file not found: {mapping_file}")
            self.use_default_mappings()

    def use_default_mappings(self):
        self.mappings = {"1": "video1.mp4", "2": "video2.mp4",
                         "3": "video3.mp4", "4": "video4.mp4"}
        self.descriptions = {"1": "", "2": "", "3": "", "4": ""}
        logger.info("Using default button mappings")

    def get_video_for_button(self, button_id: int) -> Optional[str]:
        video_file = self.mappings.get(str(button_id))
        if video_file:
            video_path = Path(self.settings.media.videos_dir) / video_file
            if video_path.exists():
                return str(video_path)
            logger.warning(f"Video file not found: {video_path}")
        return None

    def get_description(self, button_id: int) -> str:
        """Human-readable description for the menu screen."""
        return self.descriptions.get(str(button_id), "") or ""

    def get_filename(self, button_id: int) -> str:
        """Bare filename mapped to a button (no path resolution)."""
        return self.mappings.get(str(button_id), "") or ""

    def update_mapping(self, button_id: int, video_file: str,
                       description: Optional[str] = None):
        """Set or replace a button's video. If description is None, keep
        the existing one; pass empty string to clear it explicitly.
        """
        self.mappings[str(button_id)] = video_file
        if description is not None:
            self.descriptions[str(button_id)] = description
        self.save_mappings()

    def save_mappings(self):
        mapping_file = Path(self.settings.config.button_mappings_file)
        try:
            mapping_file.parent.mkdir(parents=True, exist_ok=True)
            with open(mapping_file, 'w') as f:
                json.dump({'mappings': self.mappings,
                           'descriptions': self.descriptions},
                          f, indent=2)
            logger.info("Button mappings saved")
        except Exception as e:
            logger.error(f"Failed to save button mappings: {e}")

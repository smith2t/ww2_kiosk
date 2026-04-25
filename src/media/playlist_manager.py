import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class PlaylistManager:
    def __init__(self, settings):
        self.settings = settings
        self.playlists = {}
        
    async def load_playlists(self):
        """Load playlist configurations"""
        playlist_file = Path(self.settings.config.playlists_file)
        
        if playlist_file.exists():
            try:
                with open(playlist_file, 'r') as f:
                    data = json.load(f)
                    self.playlists = data.get('playlists', {})
                    logger.info(f"Loaded {len(self.playlists)} playlists")
            except Exception as e:
                logger.error(f"Failed to load playlists: {e}")
                self.create_default_playlists()
        else:
            self.create_default_playlists()
            
    def create_default_playlists(self):
        """Create default playlists"""
        self.playlists = {
            "default": {
                "name": "Default Playlist",
                "videos": [],
                "pictures": []
            }
        }
        logger.info("Created default playlists")
        
    def get_playlist(self, name: str) -> Dict:
        """Get a specific playlist"""
        return self.playlists.get(name, {})
        
    def add_playlist(self, name: str, playlist_data: Dict):
        """Add or update a playlist"""
        self.playlists[name] = playlist_data
        self.save_playlists()
        
    def remove_playlist(self, name: str):
        """Remove a playlist"""
        if name in self.playlists:
            del self.playlists[name]
            self.save_playlists()
            
    def save_playlists(self):
        """Save playlists to file"""
        playlist_file = Path(self.settings.config.playlists_file)
        
        try:
            playlist_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(playlist_file, 'w') as f:
                json.dump({'playlists': self.playlists}, f, indent=2)
                
            logger.info("Playlists saved")
        except Exception as e:
            logger.error(f"Failed to save playlists: {e}")
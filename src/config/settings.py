import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DisplaySettings:
    fullscreen: bool = True
    width: int = 1920
    height: int = 1080
    slideshow_interval: int = 10  # seconds
    transition_duration: float = 1.0  # seconds
    shuffle_slideshow: bool = True
    idle_timeout: int = 30  # seconds to return to slideshow after video
    video_player: str = "vlc"  # vlc or omxplayer


@dataclass
class InputSettings:
    button1_pin: int = 17
    button2_pin: int = 27
    button3_pin: int = 22
    button4_pin: int = 23
    debounce_time: int = 50  # milliseconds


@dataclass
class MediaSettings:
    base_dir: str = "/home/pi/ww2_kiosk/media"
    videos_dir: str = "/home/pi/ww2_kiosk/media/videos"
    pictures_dir: str = "/home/pi/ww2_kiosk/media/pictures"


@dataclass
class NetworkSettings:
    enable_ap: bool = True
    ap_ssid: str = "WW2-Kiosk-AP"
    ap_password: str = "ww2kiosk2024"
    ap_interface: str = "wlan0"
    enable_smb: bool = True
    smb_username: str = "kiosk"
    smb_password: str = "kiosk123"


@dataclass
class ConfigSettings:
    config_file: str = "/home/pi/ww2_kiosk/config/config.yaml"
    button_mappings_file: str = "/home/pi/ww2_kiosk/config/button_mappings.json"
    playlists_file: str = "/home/pi/ww2_kiosk/config/playlists.json"


@dataclass
class Settings:
    display: DisplaySettings = field(default_factory=DisplaySettings)
    input: InputSettings = field(default_factory=InputSettings)
    media: MediaSettings = field(default_factory=MediaSettings)
    network: NetworkSettings = field(default_factory=NetworkSettings)
    config: ConfigSettings = field(default_factory=ConfigSettings)
    
    def __post_init__(self):
        # Override with environment variables if set
        self._load_from_env()
        
        # Load from config file if it exists
        self._load_from_file()
        
    def _load_from_env(self):
        """Load settings from environment variables"""
        # Media paths
        if media_dir := os.getenv("KIOSK_MEDIA_DIR"):
            self.media.base_dir = media_dir
            self.media.videos_dir = f"{media_dir}/videos"
            self.media.pictures_dir = f"{media_dir}/pictures"
            
        # Network settings
        if ap_ssid := os.getenv("KIOSK_AP_SSID"):
            self.network.ap_ssid = ap_ssid
        if ap_password := os.getenv("KIOSK_AP_PASSWORD"):
            self.network.ap_password = ap_password
        if smb_password := os.getenv("KIOSK_SMB_PASSWORD"):
            self.network.smb_password = smb_password
            
    def _load_from_file(self):
        """Load settings from YAML config file"""
        config_path = Path(self.config.config_file)
        
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    
                # Update settings from config
                if 'display' in config:
                    for key, value in config['display'].items():
                        if hasattr(self.display, key):
                            setattr(self.display, key, value)
                            
                if 'input' in config:
                    for key, value in config['input'].items():
                        if hasattr(self.input, key):
                            setattr(self.input, key, value)
                            
                if 'media' in config:
                    for key, value in config['media'].items():
                        if hasattr(self.media, key):
                            setattr(self.media, key, value)
                            
                if 'network' in config:
                    for key, value in config['network'].items():
                        if hasattr(self.network, key):
                            setattr(self.network, key, value)
                            
            except Exception as e:
                print(f"Warning: Failed to load config file: {e}")
                
    def save_to_file(self, path: Optional[str] = None):
        """Save current settings to YAML file"""
        config_path = Path(path or self.config.config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        config = {
            'display': {
                'fullscreen': self.display.fullscreen,
                'width': self.display.width,
                'height': self.display.height,
                'slideshow_interval': self.display.slideshow_interval,
                'transition_duration': self.display.transition_duration,
                'shuffle_slideshow': self.display.shuffle_slideshow,
                'idle_timeout': self.display.idle_timeout,
                'video_player': self.display.video_player,
            },
            'input': {
                'button1_pin': self.input.button1_pin,
                'button2_pin': self.input.button2_pin,
                'button3_pin': self.input.button3_pin,
                'button4_pin': self.input.button4_pin,
                'debounce_time': self.input.debounce_time,
            },
            'media': {
                'base_dir': self.media.base_dir,
                'videos_dir': self.media.videos_dir,
                'pictures_dir': self.media.pictures_dir,
            },
            'network': {
                'enable_ap': self.network.enable_ap,
                'ap_ssid': self.network.ap_ssid,
                'ap_password': self.network.ap_password,
                'ap_interface': self.network.ap_interface,
                'enable_smb': self.network.enable_smb,
                'smb_username': self.network.smb_username,
                'smb_password': self.network.smb_password,
            }
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
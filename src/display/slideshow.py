import asyncio
import logging
import random
from pathlib import Path
from typing import List

import pygame
from PIL import Image

logger = logging.getLogger(__name__)


class Slideshow:
    def __init__(self, settings):
        self.settings = settings
        self.running = False
        self.current_image_index = 0
        self.images = []
        
        self.interval = settings.display.slideshow_interval
        self.transition_duration = settings.display.transition_duration
        self.shuffle = settings.display.shuffle_slideshow
        
        self.screen = None
        self.clock = None
        
    async def initialize(self):
        """Initialize slideshow display"""
        logger.info("Initializing slideshow")
        
        # Initialize pygame
        pygame.init()
        
        # Set up display
        if self.settings.display.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(
                (self.settings.display.width, self.settings.display.height)
            )
        
        pygame.display.set_caption("WW2 Kiosk")
        self.clock = pygame.time.Clock()
        
        # Load image list
        await self.scan_images()
        
    async def scan_images(self):
        """Scan for available images"""
        image_dir = Path(self.settings.media.pictures_dir)
        
        if not image_dir.exists():
            logger.warning(f"Pictures directory not found: {image_dir}")
            return
            
        self.images = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
            self.images.extend(image_dir.glob(ext))
            self.images.extend(image_dir.glob(ext.upper()))
            
        logger.info(f"Found {len(self.images)} images")
        
        if self.shuffle:
            random.shuffle(self.images)
            
    async def start(self):
        """Start the slideshow"""
        if not self.images:
            logger.warning("No images available for slideshow")
            await self.show_default_screen()
            return
            
        self.running = True
        asyncio.create_task(self._slideshow_loop())
        
    async def _slideshow_loop(self):
        """Main slideshow loop"""
        while self.running:
            try:
                # Display current image
                await self.display_image(self.images[self.current_image_index])
                
                # Wait for interval
                await asyncio.sleep(self.interval)
                
                # Move to next image
                self.current_image_index = (self.current_image_index + 1) % len(self.images)
                
                # Handle pygame events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        
            except Exception as e:
                logger.error(f"Error in slideshow loop: {e}")
                await asyncio.sleep(1)
                
    async def display_image(self, image_path):
        """Display a single image"""
        try:
            # Load and scale image
            img = Image.open(image_path)
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
                
            # Scale to fit screen while maintaining aspect ratio
            screen_size = self.screen.get_size()
            img.thumbnail(screen_size, Image.Resampling.LANCZOS)
            
            # Convert to pygame surface
            img_surface = pygame.image.fromstring(
                img.tobytes(), img.size, img.mode
            )
            
            # Center image on screen
            x = (screen_size[0] - img.size[0]) // 2
            y = (screen_size[1] - img.size[1]) // 2
            
            # Clear screen and display image
            self.screen.fill((0, 0, 0))
            self.screen.blit(img_surface, (x, y))
            pygame.display.flip()
            
        except Exception as e:
            logger.error(f"Failed to display image {image_path}: {e}")
            
    async def show_default_screen(self):
        """Show default screen when no images available"""
        self.screen.fill((0, 0, 0))
        
        # Display message
        font = pygame.font.Font(None, 48)
        text = font.render("WW2 Kiosk - No Images Available", True, (255, 255, 255))
        text_rect = text.get_rect(center=(self.screen.get_width() // 2, 
                                         self.screen.get_height() // 2))
        self.screen.blit(text, text_rect)
        pygame.display.flip()
        
    async def stop(self):
        """Stop the slideshow"""
        self.running = False
        await asyncio.sleep(0.1)  # Allow loop to exit
        
    async def cleanup(self):
        """Clean up slideshow resources"""
        await self.stop()
        if pygame.display.get_init():
            pygame.quit()
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
        self.slides = []  # Changed from images to slides to include all media types

        # NOTE: don't cache slideshow_interval / shuffle / transition_duration
        # here — they're read from self.settings at use-time so the /settings
        # web page can change them on a running kiosk without a restart.

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

        # Mark the pygame window as always-above so xfwm4 keeps it on top of
        # xfdesktop / xfce4-panel even after mpv (which uses --ontop) exits.
        # Without this, xfce4-session respawns xfdesktop and it eventually
        # surfaces on top of the slideshow.
        try:
            proc = await asyncio.create_subprocess_exec(
                "wmctrl", "-r", "WW2 Kiosk", "-b", "add,above,fullscreen",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except Exception as e:
            logger.warning(f"wmctrl always-above failed: {e}")

        # Load slides list (images, PDFs, PowerPoint)
        await self.scan_slides()
        
    async def scan_slides(self):
        """Scan the pictures dir for image slides. PDFs and PPTX are
        intentionally excluded — those play only as category items."""
        media_dir = Path(self.settings.media.pictures_dir)

        if not media_dir.exists():
            logger.warning(f"Media directory not found: {media_dir}")
            return

        self.slides = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']:
            self.slides.extend([{'path': p, 'type': 'image'} for p in media_dir.glob(ext)])
            self.slides.extend([{'path': p, 'type': 'image'} for p in media_dir.glob(ext.upper())])

        logger.info(f"Found {len(self.slides)} slides total")

        if self.settings.display.shuffle_slideshow:
            random.shuffle(self.slides)

    async def start(self):
        """Start the slideshow loop.

        Always launches the loop — it re-scans the media directory each time it
        wraps, so newly uploaded files appear automatically and a fresh Pi with
        no media yet recovers as soon as the user uploads something.

        Also re-asserts the pygame display: when mpv ran with --ontop it
        disturbed pygame's X drawable, and a stale surface causes flip() to
        silently render to nowhere (the "kiosk goes blank after a video"
        symptom). Re-calling set_mode reclaims a fresh surface.
        """
        try:
            if self.settings.display.fullscreen:
                self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.screen = pygame.display.set_mode(
                    (self.settings.display.width, self.settings.display.height))
            # Force an immediate paint so the user sees something even before
            # the first slide is decoded.
            self.screen.fill((0, 0, 0))
            pygame.display.flip()
        except Exception as e:
            logger.warning(f"slideshow.start: failed to refresh pygame display: {e}")

        self.running = True
        asyncio.create_task(self._slideshow_loop())

    async def _slideshow_loop(self):
        """Main slideshow loop. Re-scans on cycle wrap to pick up new uploads."""
        while self.running:
            try:
                if not self.slides:
                    # Nothing to show — splash, wait, re-scan, try again
                    await self.show_default_screen()
                    await asyncio.sleep(self.settings.display.slideshow_interval)
                    await self.scan_slides()
                    continue

                # Clamp in case files were deleted since last scan
                if self.current_image_index >= len(self.slides):
                    self.current_image_index = 0

                await self.display_slide(self.slides[self.current_image_index])
                await asyncio.sleep(self.settings.display.slideshow_interval)

                self.current_image_index += 1
                if self.current_image_index >= len(self.slides):
                    # Wrapped — re-scan so newly uploaded files appear in the next cycle
                    await self.scan_slides()
                    self.current_image_index = 0

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False

            except Exception as e:
                logger.error(f"Error in slideshow loop: {e}")
                await asyncio.sleep(1)
                
    async def display_slide(self, slide):
        """Display a single slide (image, PDF page, or PowerPoint slide)"""
        image_path = slide['path']
        try:
            # Load and scale image
            img = Image.open(image_path)
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
                
            # Scale to fit screen while maintaining aspect ratio.
            # PIL.Image.thumbnail only shrinks — use ratio math so small images
            # are also enlarged to fill the screen.
            screen_w, screen_h = self.screen.get_size()
            ratio = min(screen_w / img.width, screen_h / img.height)
            new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to pygame surface
            img_surface = pygame.image.fromstring(
                img.tobytes(), img.size, img.mode
            )
            
            # Center image on screen
            x = (screen_w - img.size[0]) // 2
            y = (screen_h - img.size[1]) // 2
            
            # Clear screen and display image
            self.screen.fill((0, 0, 0))
            self.screen.blit(img_surface, (x, y))
            pygame.display.flip()
            
        except Exception as e:
            logger.error(f"Failed to display image {image_path}: {e}")
            
    async def show_default_screen(self):
        """Show default screen when no images available"""
        await self.show_splash_screen("No Images Available", "Add images to media/pictures directory")

    async def show_splash_screen(self, title="WW2 Kiosk", subtitle="Press any button to play video"):
        """Show splash screen with title and subtitle (inspired by Alex Lubbock's design)"""
        if not self.screen:
            return

        # Clear screen with dark background
        self.screen.fill((20, 20, 20))

        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()

        # Title text
        title_font = pygame.font.Font(None, 72)
        title_color = (255, 255, 255)
        title_text = title_font.render(title, True, title_color)
        title_rect = title_text.get_rect(center=(screen_width // 2, screen_height // 2 - 50))

        # Subtitle text
        subtitle_font = pygame.font.Font(None, 36)
        subtitle_color = (200, 200, 200)
        subtitle_text = subtitle_font.render(subtitle, True, subtitle_color)
        subtitle_rect = subtitle_text.get_rect(center=(screen_width // 2, screen_height // 2 + 30))

        # Instructions text
        instructions = [
            "Button 1 - D-Day Normandy",
            "Button 2 - Pearl Harbor",
            "Button 3 - Battle of Britain",
            "Button 4 - Midway"
        ]

        instruction_font = pygame.font.Font(None, 24)
        instruction_color = (150, 150, 150)

        start_y = screen_height // 2 + 100
        for i, instruction in enumerate(instructions):
            inst_text = instruction_font.render(instruction, True, instruction_color)
            inst_rect = inst_text.get_rect(center=(screen_width // 2, start_y + i * 30))
            self.screen.blit(inst_text, inst_rect)

        # Draw title and subtitle
        self.screen.blit(title_text, title_rect)
        self.screen.blit(subtitle_text, subtitle_rect)

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
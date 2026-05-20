"""Plays a curated picture-set leaf as an auto-advancing slideshow."""
import asyncio
import logging
from pathlib import Path

import pygame
from PIL import Image

logger = logging.getLogger(__name__)


class TopicSlideshow:
    def __init__(self, settings):
        self.settings = settings
        self.screen = None
        self._caption_font = None
        self.leaf = None
        self.current_index = 0
        self.running = False
        self._task = None

    async def initialize(self, screen=None):
        self.screen = screen or pygame.display.get_surface()
        try:
            self._caption_font = pygame.font.SysFont("DejaVu Sans", 28, bold=False)
        except Exception:
            self._caption_font = None

    def open(self, leaf):
        self.leaf = leaf
        self.current_index = 0

    def advance(self):
        if not self.leaf:
            return
        n = len(self.leaf.files)
        if n == 0:
            return
        self.current_index = (self.current_index + 1) % n

    async def start(self):
        if self.running:
            return
        self.running = True
        self.draw()
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            while self.running and self.leaf is not None:
                await asyncio.sleep(max(3, self.leaf.interval_sec))
                if not self.running:
                    return
                self.advance()
                self.draw()
        except asyncio.CancelledError:
            return

    async def stop(self):
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    def draw(self):
        if self.screen is None or self.leaf is None:
            return
        sw, sh = self.screen.get_size()
        self.screen.fill((0, 0, 0))

        file = self.leaf.files[self.current_index] if self.leaf.files else None
        if file:
            src = Path(self.settings.media.pictures_dir) / file
            if src.exists():
                try:
                    img = Image.open(src).convert("RGB")
                    ratio = min(sw / img.width, sh / img.height)
                    new_size = (max(1, int(img.width * ratio)),
                                max(1, int(img.height * ratio)))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    surf = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
                    self.screen.blit(surf, surf.get_rect(center=(sw // 2, sh // 2)))
                except Exception as e:
                    logger.error(f"topic slideshow draw {src}: {e}")
            else:
                logger.warning(f"topic slideshow file missing: {src}")

        if self._caption_font:
            hint = self._caption_font.render("Press Red to go back", True,
                                             (180, 180, 180))
            self.screen.blit(hint, hint.get_rect(midbottom=(sw // 2, sh - 10)))

        pygame.display.flip()

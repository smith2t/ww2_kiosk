"""PDF playback in the kiosk's pygame surface.

Each page is rendered via PyMuPDF (fitz), scaled to fit the screen,
displayed for PAGE_DURATION_SEC, then advanced. Like the video player,
playback can be interrupted at any time via stop() — main.py wires that
to the "any button press during playback" gesture.
"""

import asyncio
import logging
from pathlib import Path

import pygame

logger = logging.getLogger(__name__)


class PdfPlayer:
    def __init__(self, settings):
        self.settings = settings
        self.screen = None
        self.is_playing = False
        self._stop_event: asyncio.Event | None = None

    @property
    def page_duration_sec(self) -> float:
        # Read from settings each play so /settings edits take effect live.
        return max(1.0, float(getattr(self.settings.display, 'pdf_page_duration', 8)))

    async def initialize(self):
        # Surface fetched lazily on each play() because the slideshow may
        # have re-claimed the pygame display in the meantime.
        return

    async def play(self, pdf_path):
        try:
            import fitz   # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF (python3-fitz) not installed — cannot play PDFs")
            return

        self.screen = pygame.display.get_surface() or self.screen
        if self.screen is None:
            logger.warning("PdfPlayer.play: no pygame surface")
            return

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"Failed to open PDF {pdf_path}: {e}")
            return

        self.is_playing = True
        self._stop_event = asyncio.Event()
        logger.info(f"PDF playback start: {Path(pdf_path).name}, {len(doc)} page(s)")

        try:
            for page_index in range(len(doc)):
                if self._stop_event.is_set():
                    break
                self._render_page(doc, page_index)

                try:
                    await asyncio.wait_for(self._stop_event.wait(),
                                           timeout=self.page_duration_sec)
                    break  # got an explicit stop
                except asyncio.TimeoutError:
                    continue  # page duration elapsed, advance
        finally:
            doc.close()
            self.is_playing = False
            self._stop_event = None
            logger.info(f"PDF playback end: {Path(pdf_path).name}")

    def _render_page(self, doc, page_index):
        from PIL import Image
        import fitz

        page = doc[page_index]
        # 2x render for crisper text on the kiosk display.
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        screen_w, screen_h = self.screen.get_size()
        ratio = min(screen_w / img.width, screen_h / img.height)
        new_w = max(1, int(img.width * ratio))
        new_h = max(1, int(img.height * ratio))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        surface = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
        x = (screen_w - new_w) // 2
        y = (screen_h - new_h) // 2

        self.screen.fill((0, 0, 0))
        self.screen.blit(surface, (x, y))

        # Page indicator in the bottom-right corner so the visitor knows
        # there's more coming or that they're on the last page.
        try:
            font = pygame.font.SysFont('Arial', 28, bold=True)
            label = font.render(f"{page_index + 1} / {len(doc)}",
                                True, (240, 240, 240))
            label_rect = label.get_rect()
            label_rect.bottomright = (screen_w - 24, screen_h - 24)
            # Faint dark backdrop so the label is readable on any page.
            backdrop = pygame.Surface((label_rect.width + 20, label_rect.height + 10),
                                      pygame.SRCALPHA)
            backdrop.fill((0, 0, 0, 160))
            self.screen.blit(backdrop, (label_rect.x - 10, label_rect.y - 5))
            self.screen.blit(label, label_rect)
        except Exception:
            pass

        pygame.display.flip()

    async def stop(self):
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()

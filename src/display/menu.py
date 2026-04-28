"""Menu screen: 2x2 grid of colored panels, one per physical button.

Shown when the slideshow is interrupted by a button press. Each tile shows
the button's color (matching the physical arcade button) and the description
of the video assigned to it. Pressing the same button on the menu screen
plays its mapped video.
"""

import asyncio
import logging

import pygame

logger = logging.getLogger(__name__)


# Button id -> (label, RGB color). Order is the physical button order 1..4.
# Tile layout in 2x2 grid: 1 top-left, 2 top-right, 3 bottom-left, 4 bottom-right.
COLORS = {
    1: ("Blue",   (37, 99, 235)),
    2: ("Green",  (22, 163, 74)),
    3: ("Yellow", (202, 138, 4)),
    4: ("Red",    (220, 38, 38)),
}


class Menu:
    def __init__(self, settings, button_mapper):
        self.settings = settings
        self.button_mapper = button_mapper
        self.screen = None
        self.fonts = {}

    async def initialize(self, screen=None):
        """Use the slideshow's existing pygame surface to avoid re-initing
        the display. Caller passes the active screen.
        """
        self.screen = screen or pygame.display.get_surface()
        if self.screen is None:
            logger.warning("Menu.initialize: no pygame surface available")
            return

        # Static fonts for the title/color label/hint. Description font is
        # picked per-tile below using shrink-to-fit so each tile shows the
        # description as large as will fit.
        self.fonts = {
            'title':  pygame.font.SysFont('Arial', 60, bold=True),
            'color':  pygame.font.SysFont('Arial', 48, bold=True),
            'hint':   pygame.font.SysFont('Arial', 28, italic=True),
        }

        # Cache description fonts so we don't re-create them on every redraw.
        self._desc_fonts = {sz: pygame.font.SysFont('Arial', sz, bold=True)
                            for sz in (96, 80, 72, 64, 56, 48, 40, 36, 32)}

    def draw(self):
        """Render the 2x2 menu in the current pygame surface."""
        # Always re-fetch — slideshow.start() may have called pygame.display.set_mode
        # to reclaim the surface after a video, invalidating any cached reference.
        self.screen = pygame.display.get_surface() or self.screen
        if self.screen is None:
            return

        sw, sh = self.screen.get_size()
        self.screen.fill((20, 20, 25))

        title = self.fonts['title'].render("Choose a video", True, (240, 240, 240))
        title_rect = title.get_rect(center=(sw // 2, 50))
        self.screen.blit(title, title_rect)

        # 2x2 grid layout — (col, row) coordinates per button id
        positions = {1: (0, 0), 2: (1, 0), 3: (0, 1), 4: (1, 1)}
        margin = 40
        grid_top = 100
        grid_bottom_pad = 80   # leave room for the hint at bottom
        cell_w = (sw - 3 * margin) // 2
        cell_h = (sh - grid_top - grid_bottom_pad - 2 * margin) // 2

        for button_id, (col, row) in positions.items():
            x = margin + col * (cell_w + margin)
            y = grid_top + margin + row * (cell_h + margin)
            self._draw_tile(button_id, x, y, cell_w, cell_h)

        hint = self.fonts['hint'].render(
            "Press a colored button to play its video", True, (180, 180, 180))
        self.screen.blit(hint, hint.get_rect(center=(sw // 2, sh - 40)))

        pygame.display.flip()

    def _draw_tile(self, button_id, x, y, w, h):
        label, color = COLORS[button_id]
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, color, rect, border_radius=20)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, width=4, border_radius=20)

        # Color label small at the top of the tile.
        label_surf = self.fonts['color'].render(label, True, (255, 255, 255))
        label_rect = label_surf.get_rect(midtop=(x + w // 2, y + 16))
        self.screen.blit(label_surf, label_rect)

        # Pick description text (fall back to filename or "no video assigned").
        description = self.button_mapper.get_description(button_id).strip()
        if not description:
            filename = self.button_mapper.get_filename(button_id)
            description = filename or "— no video assigned —"

        # Available area for the description: full tile minus space used by
        # the color label and tile padding.
        pad_x = 30
        text_top = label_rect.bottom + 24
        text_bottom = y + h - 24
        text_w = w - 2 * pad_x
        text_h = text_bottom - text_top
        if text_h <= 0 or text_w <= 0:
            return

        font, wrapped = self._fit_text(description, text_w, text_h)

        # Vertically center the wrapped text block.
        line_height = font.get_linesize()
        block_h = line_height * len(wrapped)
        cur_y = text_top + max(0, (text_h - block_h) // 2)
        for line in wrapped:
            line_surf = font.render(line, True, (255, 255, 255))
            line_rect = line_surf.get_rect(midtop=(x + w // 2, cur_y))
            self.screen.blit(line_surf, line_rect)
            cur_y += line_height

    def _fit_text(self, text, max_w, max_h):
        """Pick the largest cached font where wrapped(text) fits inside the box."""
        sizes_desc = sorted(self._desc_fonts.keys(), reverse=True)
        for size in sizes_desc:
            font = self._desc_fonts[size]
            wrapped = self._wrap_text(text, font, max_w)
            if font.get_linesize() * len(wrapped) <= max_h and \
               all(font.size(line)[0] <= max_w for line in wrapped):
                return font, wrapped
        # Fallback: smallest font, accept overflow.
        font = self._desc_fonts[min(sizes_desc)]
        return font, self._wrap_text(text, font, max_w)

    @staticmethod
    def _wrap_text(text, font, max_width):
        words = text.split()
        lines, current = [], ""
        for word in words:
            candidate = (current + " " + word).strip()
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]

    async def show(self):
        """Draw the menu and handle pygame events while it's visible.

        This method only renders; the calling state machine decides when to
        leave the menu (button press selects a video, or timeout returns
        to slideshow).
        """
        self.draw()
        # Drain pygame event queue so the window stays responsive.
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
        return True

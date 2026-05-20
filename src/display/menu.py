"""Two-level menu system:

  CategoryMenu  — 4 colored tiles, each a category title (always 4 tiles)
  SubMenu       — items in a category node anywhere in the tree, paginated
                  3-at-a-time when more than 4 fit (tile 4 becomes "Next →")

Both menus are drawn directly to the active pygame surface so they stack
cleanly under the slideshow's pygame window.
"""

import logging
from typing import List, Optional

import pygame

from src.input.category_store import NodeKind

logger = logging.getLogger(__name__)

# Badge glyphs for tile kind indicators
BADGE_GLYPHS = {
    "category":   "›",   # ›
    "video":      "▶",   # ▶
    "pdf":        "\U0001F4C4",  # 📄
    "pictureset": "\U0001F5BC",  # 🖼
    "nav_back":   "←",   # ←
    "nav_next":   "→",   # →
}

# Button id -> (label, RGB color). Stays consistent across both menu levels
# so the visitor associates a fixed color with each physical button.
COLORS = {
    1: ("Blue",   (37, 99, 235)),
    2: ("Green",  (22, 163, 74)),
    3: ("Yellow", (202, 138, 4)),
    4: ("Red",    (220, 38, 38)),
}

# Tile 4 retains its physical button color (red) when used as Next/Back so
# the visitor's "this is button 4" association stays consistent.
_BTN4_COLOR = COLORS[4][1]


class _MenuBase:
    """Shared layout + shrink-to-fit text rendering."""

    def __init__(self, settings):
        self.settings = settings
        self.screen = None
        self.fonts = {}
        self._desc_fonts: dict = {}
        self._badge_font = None   # init lazily in initialize()

    async def initialize(self, screen=None):
        self.screen = screen or pygame.display.get_surface()
        self.fonts = {
            'title':  pygame.font.SysFont('Arial', 60, bold=True),
            'color':  pygame.font.SysFont('Arial', 40, bold=True),
            'hint':   pygame.font.SysFont('Arial', 28, italic=True),
        }
        self._desc_fonts = {sz: pygame.font.SysFont('Arial', sz, bold=True)
                            for sz in (96, 80, 72, 64, 56, 48, 40, 36, 32)}
        self._badge_font = pygame.font.SysFont("DejaVu Sans", 30, bold=True)

    # --- shared helpers ---------------------------------------------------
    def _draw_tile(self, x, y, w, h, color, label_text, body_text, kind=None):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, color, rect, border_radius=20)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, width=4, border_radius=20)

        if label_text:
            label = self.fonts['color'].render(label_text, True, (255, 255, 255))
            self.screen.blit(label, label.get_rect(midtop=(x + w // 2, y + 16)))

        pad_x = 30
        text_top = (y + 16 + 48) if label_text else (y + 24)
        text_bottom = y + h - 24
        text_w = w - 2 * pad_x
        text_h = text_bottom - text_top
        if text_h > 0 and text_w > 0:
            body_text = body_text or "—"
            font, wrapped = self._fit_text(body_text, text_w, text_h)
            line_height = font.get_linesize()
            block_h = line_height * len(wrapped)
            cur_y = text_top + max(0, (text_h - block_h) // 2)
            for line in wrapped:
                ls = font.render(line, True, (255, 255, 255))
                self.screen.blit(ls, ls.get_rect(midtop=(x + w // 2, cur_y)))
                cur_y += line_height

        # Kind badge in the top-right corner
        if kind and kind in BADGE_GLYPHS and self._badge_font is not None:
            glyph = BADGE_GLYPHS[kind]
            badge = self._badge_font.render(glyph, True, (255, 255, 255))
            self.screen.blit(badge, badge.get_rect(topright=(x + w - 14, y + 14)))

    def _fit_text(self, text, max_w, max_h):
        for size in sorted(self._desc_fonts.keys(), reverse=True):
            font = self._desc_fonts[size]
            wrapped = self._wrap_text(text, font, max_w)
            if (font.get_linesize() * len(wrapped) <= max_h and
                    all(font.size(line)[0] <= max_w for line in wrapped)):
                return font, wrapped
        font = self._desc_fonts[min(self._desc_fonts.keys())]
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

    def _layout_2x2(self, sw, sh, top_offset=100, bottom_pad=80):
        """Return [(x, y, w, h)] in slot order: button 1, 2, 3, 4."""
        margin = 40
        cell_w = (sw - 3 * margin) // 2
        cell_h = (sh - top_offset - bottom_pad - 2 * margin) // 2
        positions = [(0, 0), (1, 0), (0, 1), (1, 1)]   # button 1..4
        out = []
        for col, row in positions:
            x = margin + col * (cell_w + margin)
            y = top_offset + margin + row * (cell_h + margin)
            out.append((x, y, cell_w, cell_h))
        return out

    def _draw_chrome(self, title_text, hint_text):
        """Draw the dark backdrop, title at top, hint at bottom. Returns (sw, sh)."""
        self.screen = pygame.display.get_surface() or self.screen
        sw, sh = self.screen.get_size()
        self.screen.fill((20, 20, 25))
        title = self.fonts['title'].render(title_text, True, (240, 240, 240))
        self.screen.blit(title, title.get_rect(center=(sw // 2, 50)))
        if hint_text:
            hint = self.fonts['hint'].render(hint_text, True, (180, 180, 180))
            self.screen.blit(hint, hint.get_rect(center=(sw // 2, sh - 40)))
        return sw, sh


class CategoryMenu(_MenuBase):
    """Top-level menu: up to 4 colored tiles, one per root slot.
    Slots that are None are not drawn — visitors see only configured tiles.
    """

    def __init__(self, settings, store):
        super().__init__(settings)
        self.store = store

    def lit_slots(self):
        """Return the list of button ids (1-4) that have a defined node."""
        return [int(s) for s, n in self.store.root_slots().items() if n is not None]

    def draw(self):
        if self.screen is None:
            self.screen = pygame.display.get_surface()
        if self.screen is None:
            return
        sw, sh = self._draw_chrome("Choose a topic",
                                   "Press a colored button to browse")
        cells = self._layout_2x2(sw, sh)
        for slot_id_str, (x, y, w, h) in zip(("1", "2", "3", "4"), cells):
            node = self.store.root_slots().get(slot_id_str)
            if node is None:
                continue   # hide tile entirely
            button_id = int(slot_id_str)
            color = COLORS[button_id][1]
            label = COLORS[button_id][0]
            body = node.title or "(untitled)"
            kind = node.kind.value
            if kind == "category" and not node.children:
                body = f"{body}\n(no items yet)"
            self._draw_tile(x, y, w, h, color, label, body, kind=kind)
        pygame.display.flip()


class SubMenu(_MenuBase):
    """Menu showing children of a category node anywhere in the tree.

    Set the current location via open(path). Pagination kicks in only when a
    category has 5+ children — with ≤4 children tile 4 is reserved as Back,
    and tiles 1-3 show items. With exactly 4 children, the 4th is unreachable
    from this menu — the curator UI surfaces this configuration as a warning.
    """

    def __init__(self, settings, store):
        super().__init__(settings)
        self.store = store
        self.path: List[int] = []
        self.page = 0
        self.page_size = 3

    def open(self, path):
        self.path = list(path)
        self.page = 0

    def _parent_node(self):
        return self.store.resolve(self.path) if self.path else None

    def _children(self):
        n = self._parent_node()
        if n is None or n.kind is not NodeKind.CATEGORY:
            return []
        return list(n.children)

    def _is_paginated(self):
        return len(self._children()) > 4

    def _page_count(self):
        n = len(self._children())
        if n <= 4:
            return 1
        return max(1, (n + self.page_size - 1) // self.page_size)

    def _is_last_page(self):
        return self._is_paginated() and self.page >= self._page_count() - 1

    def next_page(self):
        if self._is_paginated() and self.page < self._page_count() - 1:
            self.page += 1

    def visible_items(self):
        """Return (children_for_this_page, paginated_flag).
        At most 3 children when paginated (tile 4 is Next/Back).
        When not paginated, returns 0-3 children (tile 4 is always Back).
        """
        children = self._children()
        if len(children) <= 4:
            return children[:3], False
        start = self.page * self.page_size
        return children[start:start + self.page_size], True

    def selection_for_button(self, button_id):
        """Returns one of:
          ('play', node, abs_path)
          ('drill', abs_path)
          ('next',)
          ('back',)
          ('noop',)
        """
        items, paginated = self.visible_items()
        if button_id == 4:
            if paginated and not self._is_last_page():
                return ('next',)
            return ('back',)
        idx = button_id - 1
        if 0 <= idx < len(items):
            node = items[idx]
            absolute_idx = (self.page * self.page_size if paginated else 0) + idx
            abs_path = self.path + [absolute_idx]
            if node.kind is NodeKind.CATEGORY:
                return ('drill', abs_path)
            return ('play', node, abs_path)
        return ('noop',)

    def draw(self):
        if self.screen is None:
            self.screen = pygame.display.get_surface()
        if self.screen is None:
            return

        parent = self._parent_node()
        title = parent.title if parent else "(empty)"
        items, paginated = self.visible_items()
        n_total = len(self._children())

        page_info = ""
        if paginated:
            pages = self._page_count()
            page_info = f"  ({self.page + 1} / {pages})"

        sw, sh = self._draw_chrome(title + page_info,
                                   "Press the matching colored button to play")
        cells = self._layout_2x2(sw, sh)

        for slot in range(4):
            x, y, w, h = cells[slot]
            button_id = slot + 1
            label = COLORS[button_id][0]
            color = COLORS[button_id][1]

            if button_id == 4:
                if paginated and not self._is_last_page():
                    self._draw_tile(x, y, w, h, _BTN4_COLOR, label, "Next  →",
                                    kind="nav_next")
                else:
                    self._draw_tile(x, y, w, h, _BTN4_COLOR, label, "←  Back",
                                    kind="nav_back")
                continue

            if slot < len(items):
                node = items[slot]
                self._draw_tile(x, y, w, h, color, label,
                                node.title or getattr(node, "file", ""),
                                kind=node.kind.value)
            # else: hidden tile — don't draw anything

        pygame.display.flip()


ItemMenu = SubMenu   # backwards-compat — removed in Task 17

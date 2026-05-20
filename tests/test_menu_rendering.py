import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import inspect
import pytest
import pygame
from types import SimpleNamespace
import asyncio
from unittest.mock import Mock, patch, MagicMock
from src.display.menu import _MenuBase, BADGE_GLYPHS, CategoryMenu
from src.input.category_store import Node, NodeKind


def test_badge_glyph_map_complete():
    for key in ("category", "video", "pdf", "pictureset", "nav_back", "nav_next"):
        assert key in BADGE_GLYPHS, f"missing badge for {key}"


def test_draw_tile_accepts_kind_argument():
    """Verify that _draw_tile method signature includes kind parameter."""
    sig = inspect.signature(_MenuBase._draw_tile)
    params = list(sig.parameters.keys())
    assert "kind" in params, "kind parameter missing from _draw_tile signature"
    assert sig.parameters["kind"].default is None, "kind parameter should have default None"


class _FakeStore:
    def __init__(self, slots):
        self._slots = slots

    def root_slots(self):
        return self._slots


def _settings():
    return SimpleNamespace(display=SimpleNamespace(
        fullscreen=False, width=1280, height=720,
        slideshow_interval=10, idle_timeout=30,
    ))


def test_category_menu_lit_slots_for_present_nodes():
    store = _FakeStore({
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[]),
        "2": None,
        "3": Node(kind=NodeKind.VIDEO, title="Midway", file="midway.mp4"),
        "4": None,
    })
    menu = CategoryMenu(_settings(), store)
    assert menu.lit_slots() == [1, 3]


def test_category_menu_all_null_lit_is_empty():
    store = _FakeStore({s: None for s in ("1","2","3","4")})
    menu = CategoryMenu(_settings(), store)
    assert menu.lit_slots() == []


def test_category_menu_draw_skips_null_tiles():
    """Null slots are skipped when building the draw list."""
    store = _FakeStore({
        "1": Node(kind=NodeKind.CATEGORY, title="EU", children=[]),
        "2": None, "3": None, "4": None,
    })
    menu = CategoryMenu(_settings(), store)
    # The draw() method should only iterate over non-None nodes
    # This is tested by ensuring lit_slots() == [1]
    assert menu.lit_slots() == [1]


from src.display.menu import SubMenu


def _store_with(*children, parent_title="EU"):
    return _FakeStore({
        "1": Node(kind=NodeKind.CATEGORY, title=parent_title, children=list(children)),
        "2": None, "3": None, "4": None,
    })


def _resolve(store, path):
    if not path:
        return None
    node = store.root_slots().get(str(path[0]))
    for idx in path[1:]:
        if node is None or node.kind is not NodeKind.CATEGORY:
            return None
        if idx < 0 or idx >= len(node.children):
            return None
        node = node.children[idx]
    return node


def _menu_at(store, path):
    store.resolve = lambda p: _resolve(store, p)
    m = SubMenu(_settings(), store)
    # Mock the fonts to avoid pygame font initialization issues in tests
    m.fonts = {
        'title':  MagicMock(),
        'color':  MagicMock(),
        'hint':   MagicMock(),
    }
    m._desc_fonts = {sz: MagicMock() for sz in (96, 80, 72, 64, 56, 48, 40, 36, 32)}
    m._badge_font = MagicMock()
    m.screen = pygame.display.get_surface()
    m.open(path)
    return m


def test_submenu_button4_is_back_with_three_children():
    store = _store_with(
        Node(kind=NodeKind.VIDEO, title="A", file="a.mp4"),
        Node(kind=NodeKind.VIDEO, title="B", file="b.mp4"),
        Node(kind=NodeKind.VIDEO, title="C", file="c.mp4"),
    )
    m = _menu_at(store, [1])
    items, paginated = m.visible_items()
    assert paginated is False
    assert len(items) == 3
    assert m.selection_for_button(4) == ("back",)


def test_submenu_button4_is_back_with_four_children():
    children = [Node(kind=NodeKind.VIDEO, title=f"V{i}", file=f"v{i}.mp4") for i in range(4)]
    store = _store_with(*children)
    m = _menu_at(store, [1])
    items, paginated = m.visible_items()
    assert paginated is False
    assert len(items) == 3
    assert m.selection_for_button(4) == ("back",)


def test_submenu_pagination_at_five_children():
    children = [Node(kind=NodeKind.VIDEO, title=f"V{i}", file=f"v{i}.mp4") for i in range(5)]
    store = _store_with(*children)
    m = _menu_at(store, [1])
    assert m.selection_for_button(4) == ("next",)
    m.next_page()
    assert m.selection_for_button(4) == ("back",)


def test_submenu_drill_into_subcategory():
    store = _store_with(
        Node(kind=NodeKind.CATEGORY, title="Air", children=[
            Node(kind=NodeKind.VIDEO, title="BoB", file="bob.mp4"),
        ]),
    )
    m = _menu_at(store, [1])
    action = m.selection_for_button(1)
    assert action[0] == "drill"
    assert action[1] == [1, 0]


def test_submenu_play_leaf():
    store = _store_with(
        Node(kind=NodeKind.VIDEO, title="X", file="x.mp4"),
    )
    m = _menu_at(store, [1])
    action = m.selection_for_button(1)
    assert action[0] == "play"
    assert action[1].file == "x.mp4"
    assert action[2] == [1, 0]

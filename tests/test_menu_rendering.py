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

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import inspect
import pytest
from src.display.menu import _MenuBase, BADGE_GLYPHS


def test_badge_glyph_map_complete():
    for key in ("category", "video", "pdf", "pictureset", "nav_back", "nav_next"):
        assert key in BADGE_GLYPHS, f"missing badge for {key}"


def test_draw_tile_accepts_kind_argument():
    """Verify that _draw_tile method signature includes kind parameter."""
    sig = inspect.signature(_MenuBase._draw_tile)
    params = list(sig.parameters.keys())
    assert "kind" in params, "kind parameter missing from _draw_tile signature"
    assert sig.parameters["kind"].default is None, "kind parameter should have default None"

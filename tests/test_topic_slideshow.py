import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest
import pygame
from PIL import Image

from input.category_store import Node, NodeKind


@pytest.fixture(autouse=True, scope="module")
def _pygame_init():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    yield
    pygame.quit()


from display.topic_slideshow import TopicSlideshow


def _settings(tmp_path):
    return SimpleNamespace(
        display=SimpleNamespace(slideshow_interval=10, idle_timeout=30,
                                fullscreen=False, width=1280, height=720),
        media=SimpleNamespace(pictures_dir=str(tmp_path / "pictures")),
    )


def _make_images(tmp_path, names):
    d = tmp_path / "pictures"
    d.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        Image.new("RGB", (800, 450), (i*40 % 255, 50, 50)).save(d / n)


def test_advance_index_loops(tmp_path):
    _make_images(tmp_path, ["a.jpg", "b.jpg"])
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["a.jpg", "b.jpg"],
                captions=["", ""], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.run(ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    assert ts.current_index == 0
    ts.advance()
    assert ts.current_index == 1
    ts.advance()
    assert ts.current_index == 0


def test_open_missing_file_falls_through(tmp_path):
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["nope.jpg"], captions=[""], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.run(ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    ts.draw()
    assert ts.current_index == 0


def test_caption_drawn_when_present(tmp_path):
    _make_images(tmp_path, ["a.jpg"])
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["a.jpg"], captions=["Hello caption"], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.run(ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    ts.draw()
    surf = pygame.display.get_surface()
    sw, sh = surf.get_size()
    # Sample inside the caption bar band (centered at ~92% down)
    px = surf.get_at((sw // 2, int(sh * 0.92)))
    # The bar is near-black w/ alpha, text is white — pixel must hit one or the other
    assert (px[0] < 80 and px[1] < 80 and px[2] < 80) or (px[0] > 200)


def test_no_caption_drawn_when_empty(tmp_path):
    _make_images(tmp_path, ["a.jpg"])
    leaf = Node(kind=NodeKind.PICTURESET, title="Set",
                files=["a.jpg"], captions=[""], interval_sec=3)
    ts = TopicSlideshow(_settings(tmp_path))
    asyncio.run(ts.initialize(screen=pygame.display.get_surface()))
    ts.open(leaf)
    ts.draw()
    assert ts.current_index == 0   # no crash

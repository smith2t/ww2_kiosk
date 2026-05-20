from pathlib import Path
from PIL import Image
import pytest

from src.media.thumbnailer import ensure_thumbnail, THUMB_SIZE


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    """Point the thumbnailer's cache at a temp dir."""
    cache = tmp_path / ".thumbs"
    monkeypatch.setenv("KIOSK_THUMB_CACHE_DIR", str(cache))
    return tmp_path


def _write_image(path: Path, color=(200, 50, 50), size=(800, 450)):
    img = Image.new("RGB", size, color)
    img.save(path)


def test_image_thumbnail_generated(media_root):
    src = media_root / "pictures" / "test.jpg"
    src.parent.mkdir(parents=True)
    _write_image(src)

    thumb = ensure_thumbnail(src)
    assert thumb.exists()
    with Image.open(thumb) as t:
        assert t.size == THUMB_SIZE


def test_thumbnail_is_cached(media_root):
    src = media_root / "pictures" / "test.jpg"
    src.parent.mkdir(parents=True)
    _write_image(src)

    first = ensure_thumbnail(src)
    first_mtime = first.stat().st_mtime
    second = ensure_thumbnail(src)
    assert first == second
    assert second.stat().st_mtime == first_mtime


def test_cache_invalidated_when_source_newer(media_root):
    src = media_root / "pictures" / "test.jpg"
    src.parent.mkdir(parents=True)
    _write_image(src)
    thumb = ensure_thumbnail(src)
    old_mtime = thumb.stat().st_mtime

    import os, time
    time.sleep(0.05)
    _write_image(src, color=(50, 50, 200))
    os.utime(src, None)

    new_thumb = ensure_thumbnail(src)
    assert new_thumb.stat().st_mtime > old_mtime


def test_pdf_thumbnail_generated(media_root):
    import fitz
    src = media_root / "pictures" / "doc.pdf"
    src.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 144), "Hello world", fontsize=24)
    doc.save(src)
    doc.close()

    thumb = ensure_thumbnail(src)
    assert thumb is not None
    assert thumb.exists()
    with Image.open(thumb) as t:
        assert t.size == THUMB_SIZE

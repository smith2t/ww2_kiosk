"""Thumbnail generation + caching for kiosk media."""
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

THUMB_SIZE = (320, 180)   # 16:9


def _cache_dir(media_path: Path) -> Path:
    env = os.environ.get("KIOSK_THUMB_CACHE_DIR")
    if env:
        return Path(env)
    return media_path.parent.parent / ".thumbs"


def _cache_key(media_path: Path) -> str:
    """Stable cache key based on the absolute path."""
    return hashlib.sha1(str(media_path.resolve()).encode("utf-8")).hexdigest()


def _cache_path(media_path: Path) -> Path:
    d = _cache_dir(media_path)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_cache_key(media_path)}.png"


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif"}


def _thumbnail_image(src: Path, dst: Path) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", THUMB_SIZE, (0, 0, 0))
        x = (THUMB_SIZE[0] - img.size[0]) // 2
        y = (THUMB_SIZE[1] - img.size[1]) // 2
        canvas.paste(img, (x, y))
        canvas.save(dst, format="PNG")


def _thumbnail_pdf(src: Path, dst: Path) -> None:
    import fitz   # PyMuPDF, existing project dep
    doc = fitz.open(src)
    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        page = doc.load_page(0)
        zoom = max(1.0, THUMB_SIZE[0] / page.rect.width)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", THUMB_SIZE, (0, 0, 0))
        x = (THUMB_SIZE[0] - img.size[0]) // 2
        y = (THUMB_SIZE[1] - img.size[1]) // 2
        canvas.paste(img, (x, y))
        canvas.save(dst, format="PNG")
    finally:
        doc.close()


def ensure_thumbnail(media_path: Path) -> Optional[Path]:
    """Return cached thumbnail PNG, generating it if missing or stale.

    Returns None on failure (caller may fall back to a placeholder).
    """
    media_path = Path(media_path)
    if not media_path.exists():
        logger.warning(f"thumbnail source missing: {media_path}")
        return None
    dst = _cache_path(media_path)
    if dst.exists() and dst.stat().st_mtime >= media_path.stat().st_mtime:
        return dst
    try:
        ext = media_path.suffix.lower()
        if _is_image(media_path):
            _thumbnail_image(media_path, dst)
        elif ext == ".pdf":
            _thumbnail_pdf(media_path, dst)
        else:
            logger.info(f"no thumbnailer yet for {ext}")
            return None
        return dst
    except Exception as e:
        logger.error(f"thumbnail generation failed for {media_path}: {e}")
        return None

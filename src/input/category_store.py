"""Curator-managed catalog of media items, organized into 4 categories.

Each physical button corresponds to a category (1=Blue, 2=Green, 3=Yellow,
4=Red). Each category has a human-readable title and an ordered list of
items. Each item is a media file (video or PDF) with a display title.

JSON schema (config/categories.json):
    {
      "categories": {
        "1": {
          "title": "European Theater",
          "items": [
            {"file": "dday.mp4",      "title": "D-Day Normandy"},
            {"file": "stalingrad.pdf","title": "Stalingrad: Maps"}
          ]
        },
        "2": {"title": "...", "items": [...]},
        "3": {"title": "...", "items": [...]},
        "4": {"title": "...", "items": [...]}
      }
    }

Auto-migration: if categories.json is missing but the legacy
button_mappings.json exists, each old button becomes a single-item
category seeded with the old description as the category title.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY_TITLES = {
    "1": "Category 1 — Blue",
    "2": "Category 2 — Green",
    "3": "Category 3 — Yellow",
    "4": "Category 4 — Red",
}


@dataclass
class Item:
    file: str
    title: str = ""

    def to_dict(self) -> dict:
        return {"file": self.file, "title": self.title}

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(file=str(d.get("file", "")), title=str(d.get("title", "")))


@dataclass
class Category:
    cat_id: str
    title: str
    items: List[Item] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "items": [i.to_dict() for i in self.items]}


class CategoryStore:
    """Loads/saves the category catalog from config/categories.json."""

    def __init__(self, settings):
        self.settings = settings
        # Settings exposes button_mappings_file (legacy); the categories file
        # sits next to it in the same config dir.
        legacy_path = Path(settings.config.button_mappings_file)
        self.path = legacy_path.parent / "categories.json"
        self.legacy_path = legacy_path
        self.categories: dict[str, Category] = {}
        self.load()

    # ----------------- public API -----------------

    def get_category(self, cat_id) -> Optional[Category]:
        return self.categories.get(str(cat_id))

    def all_categories(self) -> List[Category]:
        """Always returns categories 1..4 in order, creating empty ones if missing."""
        out: List[Category] = []
        for cid in ("1", "2", "3", "4"):
            cat = self.categories.get(cid)
            if cat is None:
                cat = Category(cat_id=cid, title=DEFAULT_CATEGORY_TITLES[cid])
                self.categories[cid] = cat
            out.append(cat)
        return out

    def replace_category(self, cat_id: str, title: str, items: List[Item]) -> None:
        cat_id = str(cat_id)
        if cat_id not in {"1", "2", "3", "4"}:
            raise ValueError(f"invalid cat_id: {cat_id}")
        self.categories[cat_id] = Category(cat_id=cat_id, title=title, items=list(items))
        self.save()

    def resolve_item_path(self, cat_id, index: int) -> Optional[str]:
        """Returns the absolute video path for cat[cat_id].items[index] if it exists on disk."""
        cat = self.get_category(cat_id)
        if cat is None or index < 0 or index >= len(cat.items):
            return None
        item = cat.items[index]
        if not item.file:
            return None
        videos_dir = Path(self.settings.media.videos_dir)
        candidate = videos_dir / item.file
        if candidate.exists():
            return str(candidate)
        # Could also live in pictures (PDFs) — try that too.
        pictures_dir = Path(self.settings.media.pictures_dir)
        candidate = pictures_dir / item.file
        if candidate.exists():
            return str(candidate)
        logger.warning(f"Item file not found: {item.file} (cat={cat_id} idx={index})")
        return None

    # ----------------- persistence -----------------

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    data = json.load(f)
                cats = data.get("categories", {}) or {}
                self.categories = {}
                for cid in ("1", "2", "3", "4"):
                    raw = cats.get(cid, {}) or {}
                    title = str(raw.get("title", DEFAULT_CATEGORY_TITLES[cid]))
                    items = [Item.from_dict(d) for d in (raw.get("items") or [])]
                    self.categories[cid] = Category(cat_id=cid, title=title, items=items)
                logger.info(f"Loaded {sum(len(c.items) for c in self.categories.values())} items "
                            f"across {len(self.categories)} categories")
                return
            except Exception as e:
                logger.error(f"Failed to load categories.json: {e}")

        # Fall through: try legacy button_mappings.json -> single-item categories.
        if self.legacy_path.exists():
            try:
                self._migrate_from_legacy()
                logger.info("Migrated legacy button_mappings.json -> categories.json")
                return
            except Exception as e:
                logger.error(f"Legacy migration failed: {e}")

        # Nothing — start with empty categories.
        for cid in ("1", "2", "3", "4"):
            self.categories[cid] = Category(cat_id=cid, title=DEFAULT_CATEGORY_TITLES[cid])
        logger.info("No catalog on disk; started with empty categories")

    def _migrate_from_legacy(self) -> None:
        with open(self.legacy_path) as f:
            data = json.load(f)
        mappings = data.get("mappings", {}) or {}
        descriptions = data.get("descriptions", {}) or {}
        for cid in ("1", "2", "3", "4"):
            file = (mappings.get(cid) or "").strip()
            desc = (descriptions.get(cid) or "").strip()
            items: List[Item] = []
            if file:
                items.append(Item(file=file, title=desc))
            self.categories[cid] = Category(
                cat_id=cid,
                title=desc or DEFAULT_CATEGORY_TITLES[cid],
                items=items,
            )
        self.save()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {"categories": {cid: cat.to_dict()
                                   for cid, cat in self.categories.items()}}
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {self.path}")
        except Exception as e:
            logger.error(f"Failed to save categories.json: {e}")
